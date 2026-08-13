"""Confusion-matrix segmentation metrics with exact ignore_index semantics.

Everything is derived from one accumulated confusion matrix, which is the only
way to keep mIoU consistent between single-GPU, DDP and sliding-window eval.
Ignored pixels are dropped *before* the matrix is built, so they cannot influence
any downstream number -- see ``test_ignore_semantics.py`` for the numeric proof.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.distributed as dist
from torch import Tensor


@dataclass(frozen=True)
class MetricResult:
    """Per-class and aggregate scores. NaN marks a class with no support."""

    iou: Tensor  # (C,) float64, NaN where the class is absent from gt and pred
    accuracy: Tensor  # (C,) float64 recall per class; retained compatibility name
    precision: Tensor  # (C,) float64 one-vs-rest precision
    dice: Tensor  # (C,) float64 Dice/F1
    specificity: Tensor  # (C,) float64 one-vs-rest true-negative rate
    miou: float
    macc: float
    mprecision: float
    mdice: float
    mspecificity: float
    pixel_accuracy: float
    freqw_iou: float
    support: Tensor  # (C,) int64 ground-truth pixel count
    confusion: Tensor  # (C, C) int64, rows = ground truth, cols = prediction

    def as_dict(self, names: list[str]) -> dict[str, object]:
        """Flatten to a JSON-serialisable dict for results.json."""
        return {
            "miou": self.miou,
            "macc": self.macc,
            "mprecision": self.mprecision,
            "mdice": self.mdice,
            "mspecificity": self.mspecificity,
            "pixel_accuracy": self.pixel_accuracy,
            "freqw_iou": self.freqw_iou,
            "per_class_iou": {
                n: (None if torch.isnan(v) else float(v))
                for n, v in zip(names, self.iou, strict=False)
            },
            "per_class_acc": {
                n: (None if torch.isnan(v) else float(v))
                for n, v in zip(names, self.accuracy, strict=False)
            },
            "per_class_precision": {
                n: (None if torch.isnan(v) else float(v))
                for n, v in zip(names, self.precision, strict=False)
            },
            "per_class_recall": {
                n: (None if torch.isnan(v) else float(v))
                for n, v in zip(names, self.accuracy, strict=False)
            },
            "per_class_dice": {
                n: (None if torch.isnan(v) else float(v))
                for n, v in zip(names, self.dice, strict=False)
            },
            "per_class_specificity": {
                n: (None if torch.isnan(v) else float(v))
                for n, v in zip(names, self.specificity, strict=False)
            },
            "support": {n: int(v) for n, v in zip(names, self.support, strict=False)},
        }


class ConfusionMatrix:
    """Streaming confusion matrix over canonical class ids.

    Args:
        num_classes: size of the canonical label space.
        ignore_index: label value excluded from every statistic.
        active: optional boolean mask of classes this dataset supervises. Classes
            outside it are reported as NaN rather than as a hard zero, so a class
            the dataset never labels cannot drag the mean down.
    """

    def __init__(
        self,
        num_classes: int,
        ignore_index: int = 255,
        active: Tensor | None = None,
        device: torch.device | str = "cpu",
    ) -> None:
        if num_classes < 1:
            raise ValueError(f"num_classes must be >= 1, got {num_classes}")
        self.num_classes = num_classes
        self.ignore_index = ignore_index
        self.device = torch.device(device)
        self.mat = torch.zeros(num_classes, num_classes, dtype=torch.int64, device=self.device)
        if active is None:
            self.active = torch.ones(num_classes, dtype=torch.bool, device=self.device)
        else:
            if active.shape != (num_classes,):
                raise ValueError(
                    f"active must have shape ({num_classes},), got {tuple(active.shape)}"
                )
            self.active = active.to(self.device, torch.bool)

    def reset(self) -> None:
        self.mat.zero_()

    @torch.no_grad()
    def update(self, pred: Tensor, target: Tensor) -> None:
        """Accumulate one batch. ``pred``/``target`` are integer (N, H, W) or (H, W)."""
        if pred.shape != target.shape:
            raise ValueError(f"pred {tuple(pred.shape)} != target {tuple(target.shape)}")
        pred = pred.reshape(-1).to(self.device, torch.int64)
        target = target.reshape(-1).to(self.device, torch.int64)

        keep = target != self.ignore_index
        if not bool(keep.any()):
            return
        pred, target = pred[keep], target[keep]

        # A prediction outside the label space is a bug in the head, not a class.
        if int(pred.max()) >= self.num_classes or int(pred.min()) < 0:
            raise ValueError(
                f"predictions outside [0, {self.num_classes}): "
                f"min={int(pred.min())} max={int(pred.max())}"
            )
        if int(target.max()) >= self.num_classes:
            raise ValueError(
                f"target contains id {int(target.max())} which is neither a class of the "
                f"{self.num_classes}-class space nor ignore_index={self.ignore_index}. "
                f"The taxonomy LUT was probably not applied."
            )

        idx = target * self.num_classes + pred
        self.mat += torch.bincount(idx, minlength=self.num_classes**2).reshape(
            self.num_classes, self.num_classes
        )

    def all_reduce(self) -> None:
        """Sum the matrix across DDP ranks so every rank computes identical metrics."""
        if dist.is_available() and dist.is_initialized():
            dist.all_reduce(self.mat, op=dist.ReduceOp.SUM)

    @torch.no_grad()
    def compute(self) -> MetricResult:
        mat = self.mat.double()
        tp = mat.diag()
        gt = mat.sum(dim=1)  # ground-truth pixels per class
        pr = mat.sum(dim=0)  # predicted pixels per class
        union = gt + pr - tp
        total = gt.sum()
        fp = pr - tp
        tn = total - gt - fp

        # A class is scored only if it is active for this dataset AND appears in
        # the ground truth or the prediction. Absent classes become NaN, which is
        # excluded from the mean -- a standard semantic-segmentation convention.
        seen = (union > 0) & self.active
        iou = torch.where(seen, tp / union.clamp(min=1), torch.nan)
        acc = torch.where(gt > 0, tp / gt.clamp(min=1), torch.nan)
        acc = torch.where(self.active, acc, torch.nan)
        # For an active class that exists in the ground truth but was never
        # predicted, precision and Dice are real zeros rather than NaN. Only a
        # class absent from both prediction and target is unscored.
        precision = torch.where(seen, tp / pr.clamp(min=1), torch.nan)
        dice = torch.where(seen, 2.0 * tp / (gt + pr).clamp(min=1), torch.nan)
        negative = tn + fp
        specificity_seen = self.active & (negative > 0)
        specificity = torch.where(specificity_seen, tn / negative.clamp(min=1), torch.nan)

        freq = gt / total.clamp(min=1)
        fw = torch.nansum(torch.where(seen, freq * iou, torch.zeros_like(iou)))

        return MetricResult(
            iou=iou,
            accuracy=acc,
            precision=precision,
            dice=dice,
            specificity=specificity,
            miou=float(torch.nanmean(iou)) if bool(seen.any()) else float("nan"),
            macc=float(torch.nanmean(acc)) if bool((gt > 0).any()) else float("nan"),
            mprecision=(float(torch.nanmean(precision)) if bool(seen.any()) else float("nan")),
            mdice=float(torch.nanmean(dice)) if bool(seen.any()) else float("nan"),
            mspecificity=(
                float(torch.nanmean(specificity)) if bool(specificity_seen.any()) else float("nan")
            ),
            pixel_accuracy=float(tp.sum() / total.clamp(min=1)),
            freqw_iou=float(fw),
            support=gt.long(),
            confusion=self.mat.clone(),
        )
