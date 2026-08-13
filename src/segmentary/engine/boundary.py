"""Contour metrics for thin structures: boundary F1 and trimap IoU.

Region overlap on a structure only a few pixels wide is dominated by whether its
interior is filled, so a model can gain mIoU while its predictions get thicker
and its contours get blurrier. Both metrics here score the contour instead:
boundary F1 matches predicted against ground-truth contours under a distance
tolerance, and trimap IoU restricts ordinary IoU to a band around ground-truth
boundaries.

The morphology and contour extraction both metrics rest on live in
``morphology.py`` and are re-exported here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import torch.distributed as dist
from torch import Tensor

# Re-exported: contour metrics and the morphology they are defined in terms of
# belong to the same public surface.
from .morphology import class_contours, dilate, erode  # noqa: F401

# Rows of BoundaryF1.counts. One tensor keeps the DDP reduction to a single call.
_MATCHED_PRED, _TOTAL_PRED, _MATCHED_GT, _TOTAL_GT = 0, 1, 2, 3


@dataclass
class BoundaryConfig:
    """Contour matching tolerance, expressed as a fraction of the image diagonal.

    0.75% of the diagonal is the Csurka/Perazzi default: 17px at 1024x2048,
    5px at 512x512. Scaling with the diagonal keeps the metric comparable
    across different image resolutions.
    """

    tolerance_frac: float = 0.0075
    min_tolerance: int = 1

    def __post_init__(self) -> None:
        if not 0.0 <= self.tolerance_frac <= 1.0:
            raise ValueError(f"tolerance_frac must be in [0, 1], got {self.tolerance_frac}")
        if self.min_tolerance < 0:
            raise ValueError(f"min_tolerance must be >= 0, got {self.min_tolerance}")

    def tolerance_px(self, height: int, width: int) -> int:
        """Matching radius in pixels for an image of this size."""
        diag = math.sqrt(float(height) ** 2 + float(width) ** 2)
        return max(self.min_tolerance, round(self.tolerance_frac * diag))


def _check_ids(pred: Tensor, target: Tensor, num_classes: int, ignore_index: int) -> None:
    if int(pred.max()) >= num_classes or int(pred.min()) < 0:
        raise ValueError(
            f"predictions outside [0, {num_classes}): min={int(pred.min())} max={int(pred.max())}"
        )
    known = target[target != ignore_index]
    if known.numel() and int(known.max()) >= num_classes:
        raise ValueError(
            f"target contains id {int(known.max())} which is neither a class of the "
            f"{num_classes}-class space nor ignore_index={ignore_index}. "
            f"The taxonomy LUT was probably not applied."
        )


def _nullable(value: float) -> float | None:
    # results.json is written with allow_nan=False, so NaN has to leave as null.
    return None if math.isnan(value) else value


@dataclass(frozen=True)
class BoundaryResult:
    """Per-class and aggregate contour scores. NaN marks a class with no contour."""

    f1: Tensor  # (C,) float64, NaN where the class has no contour in gt or pred
    precision: Tensor  # (C,) float64
    recall: Tensor  # (C,) float64
    macro_f1: float
    macro_precision: float
    macro_recall: float
    gt_contour_pixels: Tensor  # (C,) int64
    pred_contour_pixels: Tensor  # (C,) int64
    tolerance_frac: float

    def as_dict(self, names: list[str]) -> dict[str, object]:
        """Flatten to a JSON-serialisable dict for results.json."""
        return {
            "macro_f1": _nullable(self.macro_f1),
            "macro_precision": _nullable(self.macro_precision),
            "macro_recall": _nullable(self.macro_recall),
            "tolerance_frac": self.tolerance_frac,
            "per_class_f1": {n: _nullable(float(v)) for n, v in zip(names, self.f1, strict=False)},
            "per_class_precision": {
                n: _nullable(float(v)) for n, v in zip(names, self.precision, strict=False)
            },
            "per_class_recall": {
                n: _nullable(float(v)) for n, v in zip(names, self.recall, strict=False)
            },
            "gt_contour_pixels": {
                n: int(v) for n, v in zip(names, self.gt_contour_pixels, strict=False)
            },
            "pred_contour_pixels": {
                n: int(v) for n, v in zip(names, self.pred_contour_pixels, strict=False)
            },
        }


class BoundaryF1:
    """Dataset-level boundary F1 (Csurka et al. contour matching).

    Args:
        num_classes: size of the canonical label space.
        ignore_index: label value excluded from both contour sets.
        cfg: matching tolerance. Defaults to ``BoundaryConfig()``.
        active: optional (C,) bool mask of classes this dataset supervises;
            inactive classes report NaN rather than 0, as in ConfusionMatrix.
    """

    def __init__(
        self,
        num_classes: int,
        ignore_index: int = 255,
        cfg: BoundaryConfig | None = None,
        active: Tensor | None = None,
        device: torch.device | str = "cpu",
    ) -> None:
        if num_classes < 1:
            raise ValueError(f"num_classes must be >= 1, got {num_classes}")
        self.num_classes = num_classes
        self.ignore_index = ignore_index
        self.cfg = cfg if cfg is not None else BoundaryConfig()
        self.device = torch.device(device)
        self.counts = torch.zeros(4, num_classes, dtype=torch.int64, device=self.device)
        if active is None:
            self.active = torch.ones(num_classes, dtype=torch.bool, device=self.device)
        else:
            if active.shape != (num_classes,):
                raise ValueError(
                    f"active must have shape ({num_classes},), got {tuple(active.shape)}"
                )
            self.active = active.to(self.device, torch.bool)

    def reset(self) -> None:
        self.counts.zero_()

    @torch.no_grad()
    def update(self, pred: Tensor, target: Tensor) -> None:
        """Accumulate contour counts for a batch of integer (N, H, W) or (H, W) maps."""
        if pred.shape != target.shape:
            raise ValueError(f"pred {tuple(pred.shape)} != target {tuple(target.shape)}")
        if pred.ndim not in (2, 3):
            raise ValueError(f"expected (H, W) or (N, H, W), got {tuple(pred.shape)}")
        if target.numel() == 0:
            return
        pred = pred.to(self.device, torch.int64).reshape(-1, *pred.shape[-2:])
        target = target.to(self.device, torch.int64).reshape(-1, *target.shape[-2:])
        _check_ids(pred, target, self.num_classes, self.ignore_index)

        h, w = target.shape[-2:]
        theta = self.cfg.tolerance_px(h, w)
        # One image at a time: the per-class one-hot is (C, H, W), which is already
        # This can be hundreds of MB at large class counts and native resolution.
        for i in range(target.shape[0]):
            valid = target[i] != self.ignore_index
            if not bool(valid.any()):
                continue
            gt = class_contours(target[i], valid, self.num_classes)
            pr = class_contours(pred[i], valid, self.num_classes)
            self.counts[_TOTAL_PRED] += pr.flatten(1).sum(1)
            self.counts[_TOTAL_GT] += gt.flatten(1).sum(1)
            self.counts[_MATCHED_PRED] += (pr & dilate(gt, theta)).flatten(1).sum(1)
            self.counts[_MATCHED_GT] += (gt & dilate(pr, theta)).flatten(1).sum(1)

    def all_reduce(self) -> None:
        """Sum contour counts across DDP ranks so every rank computes the same F1."""
        if dist.is_available() and dist.is_initialized():
            dist.all_reduce(self.counts, op=dist.ReduceOp.SUM)

    @torch.no_grad()
    def compute(self) -> BoundaryResult:
        """Per-class precision/recall/F1 plus their macro means over scored classes."""
        # F1 is formed from counts pooled over the whole dataset, never by averaging
        # per-image F1. An image containing three contour pixels would otherwise
        # carry the same weight as one containing thirty thousand, and datasets
        # often have classes absent from most frames. A per-image mean would then
        # be dominated by whatever convention fills those holes. Pooling makes
        # the score a property of the dataset, exactly as mIoU is derived from one
        # accumulated confusion matrix.
        counts = self.counts.double()
        matched_p, total_p = counts[_MATCHED_PRED], counts[_TOTAL_PRED]
        matched_g, total_g = counts[_MATCHED_GT], counts[_TOTAL_GT]

        zero = torch.zeros_like(total_p)
        precision = torch.where(total_p > 0, matched_p / total_p.clamp(min=1), zero)
        recall = torch.where(total_g > 0, matched_g / total_g.clamp(min=1), zero)
        denom = precision + recall
        f1 = torch.where(denom > 0, 2.0 * precision * recall / denom.clamp(min=1e-12), zero)

        # A class with no contour in either map is absent, not wrong: NaN keeps it
        # out of the macro mean. A class present in only one of the two is scored 0.
        seen = ((total_p + total_g) > 0) & self.active
        precision = torch.where(seen, precision, torch.nan)
        recall = torch.where(seen, recall, torch.nan)
        f1 = torch.where(seen, f1, torch.nan)
        any_seen = bool(seen.any())

        return BoundaryResult(
            f1=f1,
            precision=precision,
            recall=recall,
            macro_f1=float(torch.nanmean(f1)) if any_seen else float("nan"),
            macro_precision=float(torch.nanmean(precision)) if any_seen else float("nan"),
            macro_recall=float(torch.nanmean(recall)) if any_seen else float("nan"),
            gt_contour_pixels=total_g.long(),
            pred_contour_pixels=total_p.long(),
            tolerance_frac=self.cfg.tolerance_frac,
        )


@torch.no_grad()
def trimap_iou(
    pred: Tensor,
    target: Tensor,
    num_classes: int,
    band_px: int,
    ignore_index: int = 255,
) -> Tensor:
    """Per-class IoU restricted to a band around the ground-truth boundaries.

    The band is seeded from ground-truth contours only, so it does not move when
    the prediction changes; the metric therefore isolates boundary quality from
    interior filling. Ignore pixels are excluded from the band and from the
    counts, and cannot seed a contour (see ``class_contours``).

    Args:
        pred: (N, H, W) or (H, W) int64 predicted class ids.
        target: same shape, canonical ids possibly containing ``ignore_index``.
        num_classes: size of the label space.
        band_px: half-width of the band in pixels; 0 scores the contour itself.

    Returns:
        (C,) float64 IoU, NaN for classes that never appear inside the band.
    """
    if pred.shape != target.shape:
        raise ValueError(f"pred {tuple(pred.shape)} != target {tuple(target.shape)}")
    if pred.ndim not in (2, 3):
        raise ValueError(f"expected (H, W) or (N, H, W), got {tuple(pred.shape)}")
    if band_px < 0:
        raise ValueError(f"band_px must be >= 0, got {band_px}")
    device = target.device
    if target.numel() == 0:
        return torch.full((num_classes,), torch.nan, dtype=torch.float64, device=device)
    pred = pred.to(device, torch.int64).reshape(-1, *pred.shape[-2:])
    target = target.to(torch.int64).reshape(-1, *target.shape[-2:])
    # Without this the bincount below overflows C*C and dies on `reshape` with a
    # message about tensor sizes rather than about the taxonomy.
    _check_ids(pred, target, num_classes, ignore_index)

    mat = torch.zeros(num_classes, num_classes, dtype=torch.int64, device=device)
    for i in range(target.shape[0]):
        valid = target[i] != ignore_index
        if not bool(valid.any()):
            continue
        seed = class_contours(target[i], valid, num_classes).any(dim=0)
        band = dilate(seed, band_px) & valid
        if not bool(band.any()):
            continue
        t, p = target[i][band], pred[i][band]
        mat += torch.bincount(t * num_classes + p, minlength=num_classes**2).reshape(
            num_classes, num_classes
        )

    mat = mat.double()
    tp = mat.diag()
    union = mat.sum(dim=1) + mat.sum(dim=0) - tp
    return torch.where(union > 0, tp / union.clamp(min=1), torch.nan)
