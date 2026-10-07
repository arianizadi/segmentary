"""Present-image metrics: each class scored only on the images that contain it.

Inputs are per-image confusion matrices (rows = ground truth, columns = prediction), as built
by :class:`segmentary.engine.metrics.ConfusionMatrix`, so ignored pixels (255) are already
excluded. For a set of images S and a class c:

- an image is *present* for c when its ground truth has at least one pixel of c (a non-zero
  row c), the same rule as the stratification specs' ``presence_rule``;
- the present-image IoU of c is the mean over the present images i of
  ``TP_i / (TP_i + FP_i + FN_i)`` from that image's own matrix. Images without c in their
  ground truth are left out entirely, so their false positives of c do not count; a present
  image where nothing of c is predicted contributes 0;
- precision and recall of c sum TP, FP and FN over the present images only;
- the present-image mIoU is the mean of the present-image IoU over the classes that have at
  least one present image in S.

Pixel-pooled metrics (one summed confusion matrix) are a different rule and live in
:mod:`segmentary.engine.metrics`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ClassScore:
    """One class over the images that contain it. ``None`` where nothing is defined."""

    images: int  # images whose ground truth has at least one pixel of the class
    iou: float | None  # mean per-image IoU over those images
    tp: int  # summed over those images only
    fp: int
    fn: int

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None


@dataclass(frozen=True)
class PresentImageMetrics:
    images: int  # images in the set
    classes: tuple[ClassScore, ...]  # indexed by class id
    miou: float | None  # mean IoU over the classes with at least one present image
    miou_classes: int  # number of such classes


def present_image_metrics(matrices: Iterable[np.ndarray], num_classes: int) -> PresentImageMetrics:
    """Present-image IoU, precision and recall of every class, and their mIoU, over a set of
    per-image ``num_classes x num_classes`` confusion matrices (rows ground truth)."""
    if num_classes < 1:
        raise ValueError(f"num_classes must be >= 1, got {num_classes}")
    stack = [np.asarray(m) for m in matrices]
    for m in stack:
        if m.shape != (num_classes, num_classes):
            raise ValueError(f"confusion matrix {m.shape} is not {num_classes}x{num_classes}")
        if not np.issubdtype(m.dtype, np.integer) or (m < 0).any():
            raise ValueError("confusion matrices must hold non-negative integer counts")
    if not stack:
        empty = ClassScore(images=0, iou=None, tp=0, fp=0, fn=0)
        return PresentImageMetrics(0, (empty,) * num_classes, None, 0)
    cube = np.stack(stack).astype(np.int64)  # (images, gt, pred)
    tp = np.diagonal(cube, axis1=1, axis2=2)  # (images, classes)
    support = cube.sum(axis=2)
    predicted = cube.sum(axis=1)
    fp, fn = predicted - tp, support - tp
    present = support > 0
    classes = []
    for c in range(num_classes):
        rows = present[:, c]
        n = int(rows.sum())
        if n:
            # tp + fp + fn >= support > 0 on every present image.
            per_image = tp[rows, c] / (tp[rows, c] + fp[rows, c] + fn[rows, c])
            iou: float | None = sum(per_image.tolist()) / n  # in image order
        else:
            iou = None
        classes.append(
            ClassScore(
                images=n,
                iou=iou,
                tp=int(tp[rows, c].sum()),
                fp=int(fp[rows, c].sum()),
                fn=int(fn[rows, c].sum()),
            )
        )
    scored = [s.iou for s in classes if s.iou is not None]
    miou = sum(scored) / len(scored) if scored else None
    return PresentImageMetrics(len(stack), tuple(classes), miou, len(scored))
