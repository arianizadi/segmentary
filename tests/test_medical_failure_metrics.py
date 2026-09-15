"""Synthetic physical-geometry and lesion-accounting oracles for failure review."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from segmentary.medical.evaluation import lesion_detection_metrics
from segmentary.medical.failure_metrics import (
    aggregate_failure_buckets,
    case_failure_metrics,
    roi_coverage_metrics,
)

pytest.importorskip("scipy")


def test_anisotropic_volume_diameter_union_errors_and_categorical_background() -> None:
    ref = np.zeros((7, 8, 9), dtype=np.uint8)
    ref[1:3, 2:5, 3:5] = 2  # 12 mass voxels.
    ref[5, 5, 5] = 1  # Organ cannot become a mass component.
    pred = np.zeros_like(ref)
    pred[1:2, 2:5, 3:5] = 2  # Six TP voxels.
    pred[5, 5, 5:7] = 2  # Two FP voxels.
    result = case_failure_metrics(ref, pred, (0.5, 2.0, 3.0))
    assert result["voxel_volume_mm3"] == 3
    assert result["lesion_detection"]["true_positives"] == 1
    assert result["lesion_detection"]["false_positives"] == 1
    mass = result["mass"]
    assert mass["reference_voxels"] == 12
    assert mass["prediction_voxels"] == 8
    assert mass["false_negative_voxels"] == 6
    assert mass["false_positive_voxels"] == 2
    assert mass["false_negative_fraction_of_reference"] == 0.5
    assert mass["false_positive_fraction_of_prediction"] == 0.25
    assert mass["dice"] == 0.6
    assert mass["iou"] == pytest.approx(6 / 14)
    lesion = result["lesions"][0]
    assert lesion["volume_mm3"] == 36
    assert lesion["equivalent_diameter_mm"] == pytest.approx((216 / math.pi) ** (1 / 3))
    assert lesion["bbox_xyz"] == [[1, 3], [2, 5], [3, 5]]
    assert lesion["coverage_fraction"] == 0.5
    assert lesion["status"] == "matched"
    assert lesion["dice"] == pytest.approx(2 / 3)
    fp = result["false_positive_components"][0]
    assert fp["voxels"] == 2
    assert fp["volume_mm3"] == 6
    assert fp["status_reason"] == "no_reference_overlap"
    json.dumps(result, allow_nan=False)


def test_merged_prediction_only_matches_one_lesion_and_marks_conflict() -> None:
    ref = np.zeros((3, 3, 8), dtype=np.uint8)
    ref[1, 1, 1] = ref[1, 1, 5] = 2
    pred = np.zeros_like(ref)
    pred[1, 1, 1:6] = 2
    result = case_failure_metrics(ref, pred, (1, 1, 1), iou_threshold=0.1)
    assert result["lesion_detection"] == lesion_detection_metrics(
        ref == 2, pred == 2, (1, 1, 1), 0.1
    )
    assert sorted(item["status"] for item in result["lesions"]) == ["matched", "partial"]
    assert [item["coverage_fraction"] for item in result["lesions"]] == [1, 1]
    partial = next(item for item in result["lesions"] if item["status"] == "partial")
    assert partial["status_reason"] == "one_to_one_conflict"
    assert partial["detected"] is False
    assert partial["iou"] == 0.2
    assert partial["matched_prediction_component"] is None
    assert result["lesion_detection"]["false_negatives"] == 1
    assert result["false_positive_components"] == []


def test_split_prediction_one_match_and_unmatched_overlap_is_fp() -> None:
    ref = np.zeros((3, 3, 12), dtype=np.uint8)
    ref[1, 1, 1:9] = 2
    pred = np.zeros_like(ref)
    pred[1, 1, 1:3] = pred[1, 1, 7:9] = 2
    result = case_failure_metrics(ref, pred, (1, 1, 1), iou_threshold=0.2)
    lesion = result["lesions"][0]
    assert lesion["status"] == "matched"
    assert lesion["coverage_fraction"] == 0.5
    assert lesion["overlapping_prediction_components"] == 2
    assert lesion["iou"] == 0.25
    assert lesion["dice"] == 0.4
    assert len(result["false_positive_components"]) == 1
    fp = result["false_positive_components"][0]
    assert fp["reference_overlap_fraction"] == 1
    assert fp["status_reason"] == "unmatched_with_overlap"


def test_overlap_below_threshold_distinct_from_zero_overlap() -> None:
    ref = np.zeros((5, 5, 12), dtype=np.uint8)
    ref[1, 1, 1:9] = 2
    ref[3, 3, 1:3] = 2
    pred = np.zeros_like(ref)
    pred[1, 1, 1] = 2
    result = case_failure_metrics(ref, pred, (1, 1, 1), iou_threshold=0.2)
    assert result["lesions"][0]["status"] == "partial"
    assert result["lesions"][0]["status_reason"] == "below_iou_threshold"
    assert result["lesions"][1]["status"] == "missed"
    assert result["lesions"][1]["status_reason"] == "no_overlap"
    assert result["lesion_detection"]["false_negatives"] == 2
    assert result["lesion_detection"]["false_positives"] == 1


def test_detection_filter_does_not_hide_voxel_level_false_positives() -> None:
    ref = np.zeros((5, 5, 5), dtype=np.uint8)
    pred = ref.copy()
    pred[1, 1, 1] = 2
    result = case_failure_metrics(ref, pred, (1, 1, 2), minimum_prediction_volume_mm3=3)
    assert result["mass"]["false_positive_voxels"] == 1
    assert result["mass"]["dice"] == 0
    assert result["lesion_detection"]["removed_prediction_components"] == 1
    assert result["false_positive_components"] == []
    at_threshold = case_failure_metrics(ref, pred, (1, 1, 2), minimum_prediction_volume_mm3=2)
    assert len(at_threshold["false_positive_components"]) == 1


def test_empty_reference_and_prediction_denominators_are_undefined_not_perfect() -> None:
    empty = np.zeros((3, 4, 5), dtype=np.uint8)
    result = case_failure_metrics(empty, empty, (1, 1, 1))
    assert result["mass"]["dice"] is None
    assert result["mass"]["iou"] is None
    assert result["mass"]["false_negative_fraction_of_reference"] is None
    assert result["mass"]["false_positive_fraction_of_prediction"] is None
    assert result["lesions"] == result["false_positive_components"] == []
    assert result["lesion_detection"]["sensitivity"] is None
    empty_roi = roi_coverage_metrics(empty, (1, 1, 1), ((0, 1), (0, 1), (0, 1)))
    assert empty_roi["outside_mass_fraction"] is None
    assert empty_roi["reference_lesions"] == 0
    missing = empty.copy()
    missing[1, 1, 1] = 2
    assert case_failure_metrics(missing, empty, (1, 1, 1))["mass"]["dice"] == 0


@pytest.mark.parametrize(
    "spacing", [(1, 2), (1, 1, 0), (1, -1, 1), (1, float("nan"), 1), (float("inf"), 1, 1)]
)
def test_invalid_spacing_fails(spacing: tuple[float, ...]) -> None:
    mask = np.zeros((3, 4, 5), dtype=np.uint8)
    with pytest.raises(ValueError, match="spacing_mm"):
        case_failure_metrics(mask, mask, spacing)
    with pytest.raises(ValueError, match="spacing_mm"):
        roi_coverage_metrics(mask, spacing, ((0, 1), (0, 1), (0, 1)))


@pytest.mark.parametrize("value", [0.5, -1, float("nan"), float("inf")])
def test_invalid_categorical_values_fail(value: float) -> None:
    ref = np.full((3, 4, 5), value)
    with pytest.raises(ValueError, match="integer class values"):
        case_failure_metrics(ref, np.zeros_like(ref), (1, 1, 1))


def test_shape_and_label_errors_fail_and_boolean_mask_requires_explicit_label() -> None:
    ref = np.zeros((3, 4, 5), dtype=np.uint8)
    with pytest.raises(ValueError, match="shapes must match"):
        case_failure_metrics(ref, np.zeros((3, 4, 6), dtype=np.uint8), (1, 1, 1))
    with pytest.raises(ValueError, match="three-dimensional"):
        case_failure_metrics(ref[0], ref[0], (1, 1, 1))
    with pytest.raises(ValueError, match="mass_label"):
        case_failure_metrics(ref, ref, (1, 1, 1), mass_label=0)
    with pytest.raises(ValueError, match="Boolean masks"):
        case_failure_metrics(ref.astype(bool), ref.astype(bool), (1, 1, 1))
    result = case_failure_metrics(ref.astype(bool), ref.astype(bool), (1, 1, 1), mass_label=1)
    assert result["mass"]["empty_status"] == "both_empty"


def test_connectivity_controls_diagonal_components() -> None:
    ref = np.zeros((4, 4, 4), dtype=np.uint8)
    ref[1, 1, 1] = ref[2, 2, 2] = 2
    assert len(case_failure_metrics(ref, ref, (1, 1, 1), connectivity=26)["lesions"]) == 1
    assert len(case_failure_metrics(ref, ref, (1, 1, 1), connectivity=6)["lesions"]) == 2


def test_roi_exclusion_is_native_physical_and_does_not_modify_masks() -> None:
    ref = np.zeros((8, 7, 6), dtype=np.uint8)
    ref[1:3, 1:3, 1:3] = 2  # Eight voxels; half cut by x bound.
    ref[5:7, 1:3, 1:3] = 2  # Eight voxels; entirely excluded.
    before = ref.copy()
    result = roi_coverage_metrics(ref, (0.5, 2, 4), ((0, 2), (0, 7), (0, 6)))
    assert result["reference_mass_voxels"] == 16
    assert result["inside_mass_voxels"] == 4
    assert result["outside_mass_voxels"] == 12
    assert result["outside_mass_fraction"] == 0.75
    assert result["outside_mass_volume_mm3"] == 48
    assert result["completely_excluded_lesions"] == 1
    assert result["partially_excluded_lesions"] == 1
    assert result["fully_contained_lesions"] == 0
    assert [item["outside_fraction"] for item in result["lesions"]] == [0.5, 1]
    np.testing.assert_array_equal(before, ref)
    full = roi_coverage_metrics(ref, (0.5, 2, 4), ((0, 8), (0, 7), (0, 6)))
    assert full["outside_mass_fraction"] == 0
    assert full["fully_contained_lesions"] == 2


@pytest.mark.parametrize(
    "bounds",
    [
        ((0, 0), (0, 7), (0, 6)),
        ((-1, 2), (0, 7), (0, 6)),
        ((0, 9), (0, 7), (0, 6)),
        ((0, 2), (0, 7)),
        ((0.0, 2.0), (0, 7), (0, 6)),
        ((False, True), (False, True), (False, True)),
    ],
)
def test_invalid_roi_bounds_fail(bounds: tuple[tuple[float, ...], ...]) -> None:
    with pytest.raises(ValueError, match="bbox_native"):
        roi_coverage_metrics(np.zeros((8, 7, 6), dtype=np.uint8), (1, 1, 1), bounds)


def test_buckets_have_explicit_denominators_fixed_edges_and_nonadditive_cases() -> None:
    ref = np.zeros((12, 12, 12), dtype=np.uint8)
    ref[1, 1, 1] = 2  # Equivalent diameter approx 1.24 mm.
    ref[5:7, 5:7, 5:7] = 2  # Diameter approx 2.48 mm.
    pred = np.zeros_like(ref)
    pred[1, 1, 1] = 2
    positive = case_failure_metrics(ref, pred, (1, 1, 1))
    empty = np.zeros_like(ref)
    negative_pred = empty.copy()
    negative_pred[1, 1, 1] = 2
    negative = case_failure_metrics(empty, negative_pred, (1, 1, 3))
    result = aggregate_failure_buckets(
        [positive, negative], diameter_edges_mm=(2, 3), slice_spacing_edges_mm=(1, 3)
    )
    small, medium, large = result["diameter_buckets"]
    assert small["reference_lesions"] == medium["reference_lesions"] == 1
    assert small["cases"] == medium["cases"] == 1
    assert large["cases"] == large["reference_lesions"] == 0
    assert small["lesion_sensitivity"] == 1
    assert medium["lesion_sensitivity"] == 0
    assert large["lesion_sensitivity"] is None
    assert large["mean_positive_case_mass_dice"] is None
    assert small["mean_mass_dice_denominator_cases"] == 1
    assert small["mean_positive_case_mass_dice"] == positive["mass"]["dice"]
    thin, intermediate, thick = result["slice_spacing_buckets"]
    assert thin["cases"] == 0  # Equality joins the next bin.
    assert intermediate["cases"] == thick["cases"] == 1
    assert thick["reference_negative_cases"] == 1
    assert thick["mean_mass_dice_denominator_cases"] == 0
    assert thick["false_positive_components_per_scan"] == 1
    assert result["overall"]["lesion_sensitivity_denominator"] == 2
    assert result["overall"]["reference_positive_cases"] == 1
    assert result["overall"]["reference_negative_cases"] == 1
    assert result["overall"]["mean_reference_coverage_fraction"] == 0.5
    assert result["overall"]["voxel_weighted_reference_coverage"] == pytest.approx(1 / 9)
    json.dumps(result, allow_nan=False)


def test_aggregation_empty_policy_mismatch_and_invalid_bucket_boundaries() -> None:
    result = aggregate_failure_buckets([])
    assert result["overall"]["cases"] == 0
    assert result["overall"]["lesion_sensitivity"] is None
    ref = np.zeros((3, 4, 5), dtype=np.uint8)
    a = case_failure_metrics(ref, ref, (1, 1, 1))
    b = case_failure_metrics(ref, ref, (1, 1, 1), iou_threshold=0.5)
    with pytest.raises(ValueError, match="different lesion detection policies"):
        aggregate_failure_buckets([a, b])
    for edges in [(0, 1), (2, 1), (1, 1), (1, float("nan")), (1,)]:
        with pytest.raises(ValueError, match="increasing finite positive"):
            aggregate_failure_buckets([], diameter_edges_mm=edges)
    with pytest.raises(ValueError, match="slice_axis"):
        aggregate_failure_buckets([], slice_axis=3)


def test_maximum_spacing_proxy_explicit_and_axis_reordering_invariant() -> None:
    ref = np.zeros((3, 4, 5), dtype=np.uint8)
    ref[1, 1, 1] = 2
    result = case_failure_metrics(ref, ref, (4, 1, 2))
    buckets = aggregate_failure_buckets([result], slice_axis=None)
    assert buckets["slice_spacing_buckets"][2]["cases"] == 1
    assert "proxy" in buckets["policy"]["spacing_definition"]
    permuted = case_failure_metrics(ref.transpose(2, 0, 1), ref.transpose(2, 0, 1), (2, 4, 1))
    assert aggregate_failure_buckets([permuted], slice_axis=None) == buckets
    assert (
        aggregate_failure_buckets([result], slice_axis=1)["slice_spacing_buckets"][0]["cases"] == 1
    )
    with pytest.raises(ValueError, match="slice_axis"):
        aggregate_failure_buckets([], slice_axis=1.0)
