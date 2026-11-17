"""The paper must retain negative-image errors and the declared seed denominator."""

import numpy as np
import pytest
from scripts.rad_paper_metrics import paper_metrics, pooled_metrics, score_images, seed_summary

from segmentary.engine.metrics import ConfusionMatrix


def test_negative_images_change_pooled_iou_and_false_alarm_count():
    matrices = {
        "positive": np.array([[90, 0], [0, 10]], np.int64),
        "negative": np.array([[50, 50], [0, 0]], np.int64),
    }
    metrics = score_images(matrices, ["background", "mud"])
    assert metrics["class_positive_images"]["per_class"]["mud"]["mean_image_iou"] == 1
    assert metrics["pixel_pooled"]["per_class"]["mud"]["iou"] == pytest.approx(10 / 60)
    negative = metrics["negative_images"]["mud"]
    assert negative["negative_images"] == 1
    assert negative["false_positive_pixels"] == 50
    assert negative["false_positive_pixel_fraction"] == 0.5
    assert negative["image_false_alarm_rate_any_pixel"] == 1


def test_pooled_scores_match_reference_evaluator_for_zero_and_positive_support():
    import torch

    matrix = np.array([[10, 2, 1, 0], [3, 5, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]], np.int64)
    reference = ConfusionMatrix(4, 255, device="cpu")
    reference.mat.copy_(torch.from_numpy(matrix))
    expected = reference.compute()
    result = pooled_metrics(matrix, ["a", "b", "c", "d"])
    assert result["miou"] == pytest.approx(expected.miou)
    assert result["macro_scored_classes"] == 3
    assert result["per_class"]["c"]["iou"] == 0
    assert result["per_class"]["c"]["recall"] is None
    assert result["per_class"]["d"]["iou"] is None
    for index, name in enumerate(["a", "b", "c"]):
        assert result["per_class"][name]["precision"] == pytest.approx(
            float(expected.precision[index])
        )
        assert result["per_class"][name]["dice"] == pytest.approx(float(expected.dice[index]))


def test_block_support_is_explicit_and_leave_one_out_uses_complement():
    matrices = {"a": np.diag([5, 0]), "b": np.diag([0, 3])}
    result = paper_metrics(matrices, ["a", "b"], {"a": "block-a", "b": "block-b"})
    assert result["per_block"]["block-a"]["pixel_pooled"]["ground_truth_present_classes"] == 1
    assert result["leave_one_block_out"]["block-a"]["pixel_pooled"]["per_class"]["b"]["pixels"] == 3
    assert result["negative_images"]["a"]["negative_images"] == 1
    with pytest.raises(ValueError, match="exactly one"):
        paper_metrics(matrices, ["a", "b"], {"a": "block-a"})


def test_false_alarm_thresholds_have_fixed_area_denominator():
    matrices = {"a": np.array([[999, 1], [0, 0]]), "b": np.array([[9999, 1], [0, 0]])}
    result = score_images(matrices, ["background", "mud"])["negative_images"]["mud"]
    assert result["images_with_any_false_positive"] == 2
    assert result["images_with_0_1_percent_false_positive_area"] == 1
    assert result["false_positive_pixel_fraction"] == pytest.approx(2 / 11000)


def test_seed_sd_uses_sample_denominator_and_never_accepts_partial_runs():
    summary = seed_summary({0: 0.5, 1: 0.6, 2: 0.7})
    assert summary["mean"] == pytest.approx(0.6)
    assert summary["sample_sd"] == pytest.approx(0.1)
    assert summary["paired_seed_inference"] is False
    assert summary["test_sampling_interval"] is None
    for bad in ({0: 0.5, 1: 0.6}, {0: 0.5, 1: 0.6, 2: float("nan")}):
        with pytest.raises(ValueError, match="three finite"):
            seed_summary(bad)
