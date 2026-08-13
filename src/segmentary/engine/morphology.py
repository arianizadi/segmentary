"""Binary morphology on label maps, and the contour extraction built on it.

Pure torch (``max_pool2d`` with stride 1), so contour metrics run on the eval
device without a GPU->CPU round trip per image. The structuring element is a
square, i.e. distances are Chebyshev; that is what makes a radius-1 erosion the
8-neighbourhood test ``class_contours`` needs.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import Tensor


def dilate(mask: Tensor, radius: int) -> Tensor:
    """Binary dilation by a (2*radius+1)^2 square, i.e. Chebyshev radius ``radius``."""
    return _morph(mask, radius, erode=False)


def erode(mask: Tensor, radius: int) -> Tensor:
    """Binary erosion by a (2*radius+1)^2 square.

    Pixels outside the image count as foreground, because ``max_pool2d`` pads
    with -inf and erosion is computed as ``-max_pool2d(-x)``. The consequence is
    deliberate: a mask that runs off the edge of the frame is not eroded there,
    so the image border never becomes a contour. An object leaving the frame
    would otherwise contribute a spurious boundary.
    """
    return _morph(mask, radius, erode=True)


def _morph(mask: Tensor, radius: int, erode: bool) -> Tensor:
    if radius < 0:
        raise ValueError(f"morphology radius must be >= 0, got {radius}")
    if mask.ndim < 2:
        raise ValueError(f"mask must have at least 2 dims (H, W), got {tuple(mask.shape)}")
    if radius == 0:
        return mask.to(torch.bool)
    h, w = mask.shape[-2:]
    # Threshold to bool *before* the float cast. Going straight to float would make
    # radius 0 (`!= 0`) and radius >= 1 (`> 0.5`) disagree about what is foreground
    # for any non-boolean mask.
    x = mask.to(torch.bool).to(torch.float32).reshape(-1, 1, h, w)
    if erode:
        x = -x
    out = F.max_pool2d(x, kernel_size=2 * radius + 1, stride=1, padding=radius)
    if erode:
        out = -out
    return (out > 0.5).reshape(mask.shape)


def class_contours(labels: Tensor, valid: Tensor, num_classes: int) -> Tensor:
    """Per-class contour pixels of a label map, immune to ignore regions.

    Args:
        labels: (H, W) int64 class ids. Values under ``~valid`` are not read.
        valid: (H, W) bool, False where the ground truth is ignore_index.
        num_classes: size of the label space.

    Returns:
        (C, H, W) bool. Pixel p is a contour pixel of class c iff it is labelled
        c, is valid, and some 8-neighbour carries a *different known* class.
    """
    if labels.shape != valid.shape:
        raise ValueError(
            f"labels {tuple(labels.shape)} and valid {tuple(valid.shape)} must match; "
            f"mismatched shapes broadcast silently and would give meaningless contours"
        )
    ids = torch.arange(num_classes, device=labels.device).view(num_classes, 1, 1)
    onehot = (labels.unsqueeze(0) == ids) & valid

    # The subtle part. Eroding `onehot` alone would mark every pixel that borders
    # an ignore region as a contour, because ignore reads as background there.
    # Large ignored border regions would manufacture fake contours, and a model
    # would be scored on matching them. Eroding `onehot | unknown` instead treats
    # unknown as possibly belonging to each class, so a pixel survives erosion
    # unless a *known* neighbour
    # disagrees. Applying the same rule to the prediction keeps the two contour
    # sets consistent: a prediction equal to the ground truth on every valid pixel
    # then yields byte-identical contours regardless of what it says under ignore.
    unknown = ~valid
    interior = erode(onehot | unknown, 1)
    return onehot & ~interior
