"""Recomputable RAD paper statistics from native-image confusion matrices.

Rows are ground truth, columns are predictions. Ignore pixels have already been
excluded by the inference collector. No image or pixel is resampled here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from segmentary.engine.present_image import present_image_metrics


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def pooled_metrics(matrix: np.ndarray, names: Sequence[str]) -> dict[str, Any]:
    """Match ConfusionMatrix's union-positive macro denominator and retain support."""
    classes = {}
    total = int(matrix.sum())
    for index, name in enumerate(names):
        tp = int(matrix[index, index])
        support = int(matrix[index].sum())
        predicted = int(matrix[:, index].sum())
        fp, fn = predicted - tp, support - tp
        union = tp + fp + fn
        classes[name] = {
            "pixels": support,
            "predicted_pixels": predicted,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "iou": ratio(tp, union),
            "precision": tp / max(predicted, 1) if union else None,
            "recall": ratio(tp, support),
            "dice": ratio(2 * tp, support + predicted),
            "pixel_false_positive_rate": ratio(fp, total - support),
        }
    scored = [value["iou"] for value in classes.values() if value["iou"] is not None]
    return {
        "miou": sum(scored) / len(scored) if scored else None,
        "macro_scored_classes": len(scored),
        "ground_truth_present_classes": sum(value["pixels"] > 0 for value in classes.values()),
        "valid_pixels": total,
        "pixel_accuracy": ratio(int(np.trace(matrix)), total),
        "per_class": classes,
        "confusion": matrix.tolist(),
    }


def score_images(matrices: Mapping[str, np.ndarray], names: Sequence[str]) -> dict[str, Any]:
    """Pooled scores, the earlier conditional scores and negative-image false alarms."""
    if not matrices or not names or len(set(names)) != len(names):
        raise ValueError("Nonempty images and unique class names are required")
    # Existing implementation validates matrix shape, integer counts and nonnegativity.
    conditional = present_image_metrics(matrices.values(), len(names))
    cube = np.stack(list(matrices.values())).astype(np.int64)
    supports = cube.sum(axis=2)
    predictions = cube.sum(axis=1)
    valid_pixels = cube.sum(axis=(1, 2))
    negatives = {}
    for index, name in enumerate(names):
        absent = supports[:, index] == 0
        predicted_pixels = predictions[absent, index]
        available_pixels = valid_pixels[absent]
        # Two prespecified descriptive thresholds. Neither is selected using test scores.
        any_alarm = predicted_pixels > 0
        area_alarm = (predicted_pixels > 0) & (predicted_pixels >= 0.001 * available_pixels)
        count = int(absent.sum())
        negatives[name] = {
            "negative_images": count,
            "negative_valid_pixels": int(available_pixels.sum()),
            "false_positive_pixels": int(predicted_pixels.sum()),
            "false_positive_pixel_fraction": ratio(
                int(predicted_pixels.sum()), int(available_pixels.sum())
            ),
            "images_with_any_false_positive": int(any_alarm.sum()),
            "image_false_alarm_rate_any_pixel": ratio(int(any_alarm.sum()), count),
            "images_with_0_1_percent_false_positive_area": int(area_alarm.sum()),
            "image_false_alarm_rate_0_1_percent_area": ratio(int(area_alarm.sum()), count),
        }
    return {
        "images": len(matrices),
        "pixel_pooled": pooled_metrics(cube.sum(axis=0), names),
        "class_positive_images": {
            "miou": conditional.miou,
            "macro_scored_classes": conditional.miou_classes,
            "per_class": {
                name: {
                    "positive_images": score.images,
                    "mean_image_iou": score.iou,
                    "precision": score.precision,
                    "recall": score.recall,
                    "dice": ratio(2 * score.tp, 2 * score.tp + score.fp + score.fn),
                    "tp": score.tp,
                    "fp": score.fp,
                    "fn": score.fn,
                }
                for name, score in zip(names, conditional.classes, strict=True)
            },
        },
        "negative_images": negatives,
    }


def paper_metrics(
    matrices: Mapping[str, np.ndarray], names: Sequence[str], groups: Mapping[str, str]
) -> dict[str, Any]:
    """Include block diagnostics without treating four inferred blocks as a large sample."""
    if set(matrices) != set(groups) or any(not value for value in groups.values()):
        raise ValueError("Every scored image must have exactly one nonempty scene block")
    blocks = sorted(set(groups.values()))
    result = score_images(matrices, names)
    result["per_block"] = {
        block: score_images(
            {key: value for key, value in matrices.items() if groups[key] == block}, names
        )
        for block in blocks
    }
    result["leave_one_block_out"] = {
        block: score_images(
            {key: value for key, value in matrices.items() if groups[key] != block}, names
        )
        for block in blocks
        if len(blocks) > 1
    }
    result["definitions"] = {
        "primary": "sum image confusions, IoU_c=TP_c/(TP_c+FP_c+FN_c), macro mean over union-positive classes",
        "conditional": "mean image IoU only on images with ground-truth pixels of each class, then macro mean",
        "ignore_pixels": "excluded before forming every confusion matrix",
        "negative_image_alarm_thresholds": [
            "at least one predicted pixel",
            "at least 0.1 percent of valid image pixels",
        ],
        "block_intervals": "none; report per-block and leave-one-block-out sensitivity descriptively",
    }
    return result


def seed_summary(values: Mapping[int, float]) -> dict[str, Any]:
    """Adaptation variation, conditional on the fixed source checkpoints and test images."""
    if sorted(values) != [0, 1, 2] or any(not np.isfinite(value) for value in values.values()):
        raise ValueError("Exactly three finite results for seeds 0, 1 and 2 are required")
    samples = np.array([values[seed] for seed in range(3)], dtype=np.float64)
    return {
        "seeds": {str(seed): float(values[seed]) for seed in range(3)},
        "mean": float(samples.mean()),
        "sample_sd": float(samples.std(ddof=1)),
        "minimum": float(samples.min()),
        "maximum": float(samples.max()),
        "n": 3,
        "uncertainty_scope": "RAD adaptation seeds conditional on fixed source runs and test images",
        "paired_seed_inference": False,
        "test_sampling_interval": None,
    }
