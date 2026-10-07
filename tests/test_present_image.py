"""Present-image metrics on hand-computed confusion matrices (rows = ground truth)."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from segmentary.engine.metrics import ConfusionMatrix
from segmentary.engine.present_image import present_image_metrics

# Three classes. A: class 0 and class 2 present. B: no class 2 in its ground truth but 8
# pixels predicted as class 2 (false positives that must not count). C: class 2 present and
# nothing of it predicted (IoU 0); its 6 pixels predicted as class 0, which C does not contain.
A = np.array([[5, 0, 1], [0, 0, 0], [1, 0, 3]])
B = np.array([[2, 0, 8], [0, 4, 0], [0, 0, 0]])
C = np.array([[0, 0, 0], [0, 0, 0], [6, 0, 0]])


def test_each_class_is_scored_only_on_the_images_that_contain_it():
    result = present_image_metrics([A, B, C], 3)
    assert result.images == 3
    zero, one, two = result.classes
    # Class 0: A (TP 5, FP 1, FN 1) and B (TP 2, FN 8); C's 6 false positives do not count.
    assert zero.images == 2 and zero.iou == pytest.approx((5 / 7 + 2 / 10) / 2)
    assert (zero.tp, zero.fp, zero.fn) == (7, 1, 9)
    # Class 1: B only, perfect.
    assert one.images == 1 and one.iou == 1.0 and one.precision == 1.0 and one.recall == 1.0
    # Class 2: A (TP 3, FP 1, FN 1 -> 3/5) and C (missed -> 0); B's 8 false positives excluded.
    assert two.images == 2 and two.iou == pytest.approx((3 / 5 + 0) / 2)
    assert (two.tp, two.fp, two.fn) == (3, 1, 7)
    assert two.precision == pytest.approx(3 / 4) and two.recall == pytest.approx(3 / 10)
    # The pixel-pooled IoU of class 2 counts B's false positives: 3 / (3 + 9 + 7).
    pooled = A + B + C
    assert pooled[2, 2] / (pooled[2].sum() + pooled[:, 2].sum() - pooled[2, 2]) == 3 / 19
    assert result.miou == pytest.approx(((5 / 7 + 2 / 10) / 2 + 1.0 + 0.3) / 3)
    assert result.miou_classes == 3


def test_classes_without_a_present_image_are_left_out_of_the_mean():
    result = present_image_metrics([B], 3)
    assert result.classes[2].images == 0 and result.classes[2].iou is None
    assert result.classes[2].precision is None and result.classes[2].recall is None
    assert (result.classes[2].tp, result.classes[2].fp, result.classes[2].fn) == (0, 0, 0)
    assert result.miou_classes == 2 and result.miou == pytest.approx((2 / 10 + 1.0) / 2)


def test_present_but_missed_scores_zero_and_has_no_precision():
    result = present_image_metrics([C], 3)
    two = result.classes[2]
    assert two.images == 1 and two.iou == 0.0 and two.recall == 0.0
    assert two.precision is None  # nothing of class 2 predicted on its images
    assert result.miou == 0.0 and result.miou_classes == 1


def test_ignored_pixels_never_make_a_class_present():
    # Ground truth 255 where class 2 is predicted: ignored before the matrix is built.
    target = torch.tensor([[255, 255], [0, 0]])
    pred = torch.tensor([[2, 2], [0, 0]])
    metric = ConfusionMatrix(3, ignore_index=255)
    metric.update(pred, target)
    matrix = metric.mat.numpy()
    assert matrix.sum() == 2
    result = present_image_metrics([matrix], 3)
    assert result.classes[2].images == 0 and result.classes[2].fp == 0
    assert result.classes[0].iou == 1.0 and result.miou == 1.0 and result.miou_classes == 1


def test_empty_sets():
    result = present_image_metrics([], 3)
    assert result.images == 0 and result.miou is None and result.miou_classes == 0
    assert all(c.images == 0 and c.iou is None and c.precision is None for c in result.classes)
    zero = np.zeros((3, 3), np.int64)
    blank = present_image_metrics([zero, zero], 3)
    assert blank.images == 2 and blank.miou is None and blank.miou_classes == 0


def test_image_order_does_not_change_the_result():
    forward, backward = present_image_metrics([A, B, C], 3), present_image_metrics([C, B, A], 3)
    assert forward.miou == pytest.approx(backward.miou)
    assert forward.classes[2] == backward.classes[2]


@pytest.mark.parametrize(
    ("matrices", "message"),
    [
        ([np.zeros((2, 2), np.int64)], "not 3x3"),
        ([-np.ones((3, 3), np.int64)], "non-negative integer"),
        ([np.zeros((3, 3), np.float64)], "non-negative integer"),
    ],
)
def test_malformed_matrices_are_refused(matrices, message):
    with pytest.raises(ValueError, match=message):
        present_image_metrics(matrices, 3)
    with pytest.raises(ValueError, match="num_classes"):
        present_image_metrics([], 0)
