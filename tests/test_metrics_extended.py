"""Extended dense metrics share the canonical streaming confusion matrix."""

from __future__ import annotations

import math

import pytest
import torch

from segmentary.engine.metrics import ConfusionMatrix


def test_precision_recall_dice_and_specificity_match_confusion_arithmetic() -> None:
    # rows=ground truth, columns=prediction
    expected = torch.tensor([[2, 1, 0], [1, 1, 0], [0, 1, 2]], dtype=torch.int64)
    target: list[int] = []
    pred: list[int] = []
    for truth in range(3):
        for prediction in range(3):
            count = int(expected[truth, prediction])
            target.extend([truth] * count)
            pred.extend([prediction] * count)

    cm = ConfusionMatrix(3)
    cm.update(torch.tensor(pred), torch.tensor(target))
    result = cm.compute()

    assert torch.equal(result.confusion, expected)
    assert result.precision.tolist() == pytest.approx([2 / 3, 1 / 3, 1.0])
    assert result.accuracy.tolist() == pytest.approx([2 / 3, 1 / 2, 2 / 3])
    assert result.dice.tolist() == pytest.approx([2 / 3, 0.4, 0.8])
    assert result.specificity.tolist() == pytest.approx([4 / 5, 2 / 3, 1.0])
    assert result.mprecision == pytest.approx((2 / 3 + 1 / 3 + 1.0) / 3)
    assert result.mdice == pytest.approx((2 / 3 + 0.4 + 0.8) / 3)
    assert result.mspecificity == pytest.approx((4 / 5 + 2 / 3 + 1.0) / 3)


def test_missed_class_has_zero_precision_and_dice_but_absent_class_is_null() -> None:
    cm = ConfusionMatrix(4)
    target = torch.tensor([0, 0, 1, 1])
    pred = torch.tensor([0, 0, 0, 0])
    cm.update(pred, target)
    result = cm.compute()
    record = result.as_dict(["background", "missed", "absent", "also-absent"])

    assert result.precision[1] == 0
    assert result.dice[1] == 0
    assert math.isnan(float(result.precision[2]))
    assert record["per_class_precision"]["missed"] == 0.0
    assert record["per_class_dice"]["missed"] == 0.0
    assert record["per_class_precision"]["absent"] is None
    assert record["per_class_recall"] == record["per_class_acc"]


def test_inactive_class_is_excluded_from_every_new_macro_metric() -> None:
    active = torch.tensor([True, True, False])
    cm = ConfusionMatrix(3, active=active)
    target = torch.tensor([0, 1, 1, 0])
    pred = torch.tensor([0, 1, 2, 2])
    cm.update(pred, target)
    result = cm.compute()

    assert torch.isnan(result.precision[2])
    assert torch.isnan(result.dice[2])
    assert torch.isnan(result.specificity[2])
    assert result.mprecision == pytest.approx((1.0 + 1.0) / 2)
    assert result.mdice == pytest.approx((2 / 3 + 2 / 3) / 2)
