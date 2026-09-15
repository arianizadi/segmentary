"""Native-space diagnostics for categorical masks, independent of models and files.

Connected components are annotation proxies, not verified clinical lesions. A
``partial`` lesion has some predicted overlap but fails the declared one-to-one
IoU matching rule; it is still a detection false negative. Pixel-level errors
use every predicted mass voxel, even when a detection size filter is requested.
Bucket summaries are descriptive and do not supply significance tests.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .evaluation import _spacing, lesion_detection_metrics


def _mass_mask(values: np.ndarray, mass_label: int) -> np.ndarray:
    if (
        not isinstance(mass_label, (int, np.integer))
        or isinstance(mass_label, bool)
        or mass_label <= 0
    ):
        raise ValueError("mass_label must be a positive integer")
    array = np.asarray(values)
    if array.ndim != 3 or min(array.shape) <= 0:
        raise ValueError("Masks must be nonempty three-dimensional arrays")
    if array.dtype.kind not in "biuf" or not np.isfinite(array).all():
        raise ValueError("Masks must contain finite nonnegative integer class values")
    if (array < 0).any() or (array.dtype.kind == "f" and (array != np.floor(array)).any()):
        raise ValueError("Masks must contain finite nonnegative integer class values")
    if array.dtype == np.bool_ and mass_label != 1:
        raise ValueError("Boolean masks require mass_label=1")
    return np.asarray(array == mass_label, dtype=bool)


def _components(mask: np.ndarray, connectivity: int) -> tuple[np.ndarray, int]:
    from scipy import ndimage

    if connectivity not in {6, 18, 26}:
        raise ValueError("connectivity must be 6, 18 or 26")
    structure = ndimage.generate_binary_structure(3, {6: 1, 18: 2, 26: 3}[connectivity])
    components, count = ndimage.label(mask, structure)
    return components, int(count)


def _component_records(labels: np.ndarray, count: int, voxel_mm3: float) -> list[dict[str, Any]]:
    from scipy import ndimage

    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    bounds = ndimage.find_objects(labels, max_label=count) if count else []
    records = []
    for component, box in enumerate(bounds, start=1):
        if box is None:
            raise ValueError("Component labels must be contiguous")
        voxels = int(sizes[component])
        volume = voxels * voxel_mm3
        records.append(
            {
                "component": component,
                "voxels": voxels,
                "volume_mm3": volume,
                "equivalent_diameter_mm": (6 * volume / math.pi) ** (1 / 3),
                "bbox_xyz": [[int(axis.start), int(axis.stop)] for axis in box],
            }
        )
    return records


def _overlap_records(
    refs: np.ndarray,
    preds: np.ndarray,
    ref_sizes: np.ndarray,
    pred_sizes: np.ndarray,
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]]]:
    n_preds = len(pred_sizes) - 1
    by_ref: dict[int, list[dict[str, Any]]] = {}
    by_pred: dict[int, list[dict[str, Any]]] = {}
    overlap = (refs > 0) & (preds > 0)
    if n_preds and np.any(overlap):
        pairs, intersections = np.unique(
            (refs[overlap].astype(np.int64) - 1) * n_preds + preds[overlap] - 1,
            return_counts=True,
        )
        for pair, intersection in zip(pairs, intersections, strict=True):
            ref_id, pred_id = int(pair // n_preds + 1), int(pair % n_preds + 1)
            ref_size, pred_size = int(ref_sizes[ref_id]), int(pred_sizes[pred_id])
            record = {
                "reference_component": ref_id,
                "prediction_component": pred_id,
                "intersection_voxels": int(intersection),
                "dice": 2 * int(intersection) / (ref_size + pred_size),
                "iou": int(intersection) / (ref_size + pred_size - int(intersection)),
            }
            by_ref.setdefault(ref_id, []).append(record)
            by_pred.setdefault(pred_id, []).append(record)
    return by_ref, by_pred


def case_failure_metrics(
    reference: np.ndarray,
    prediction: np.ndarray,
    spacing_mm: Sequence[float],
    *,
    mass_label: int = 2,
    iou_threshold: float = 0.1,
    connectivity: int = 26,
    minimum_prediction_volume_mm3: float = 0.0,
) -> dict[str, Any]:
    """Describe mass-union errors and each reference/false-positive component.

    ``lesions[*].dice/iou`` use the assigned prediction component if matched,
    otherwise the overlapping component with highest IoU. ``coverage_fraction``
    measures overlap with the union of retained prediction components. A merged
    prediction can overlap several lesions, but it can only match one of them.
    Physical spacing follows native array axes; no XYZ/ZYX transpose is assumed.
    """
    ref, pred = _mass_mask(reference, mass_label), _mass_mask(prediction, mass_label)
    if ref.shape != pred.shape:
        raise ValueError("Reference and prediction shapes must match")
    spacing = _spacing(spacing_mm)
    detection = lesion_detection_metrics(
        ref, pred, spacing, iou_threshold, connectivity, minimum_prediction_volume_mm3
    )
    voxel_mm3 = math.prod(spacing)
    refs, n_refs = _components(ref, connectivity)
    preds_before, n_preds_before = _components(pred, connectivity)
    pred_sizes_before = np.bincount(preds_before.ravel(), minlength=n_preds_before + 1)
    keep = pred_sizes_before * voxel_mm3 >= minimum_prediction_volume_mm3
    keep[0] = False
    preds, n_preds = _components(keep[preds_before], connectivity)
    ref_sizes = np.bincount(refs.ravel(), minlength=n_refs + 1)
    pred_sizes = np.bincount(preds.ravel(), minlength=n_preds + 1)
    by_ref, by_pred = _overlap_records(refs, preds, ref_sizes, pred_sizes)
    assignments = {
        match["reference_component"]: match["prediction_component"]
        for match in detection["matches"]
    }
    matched_preds = set(assignments.values())
    lesions = _component_records(refs, n_refs, voxel_mm3)
    for lesion in lesions:
        component = lesion["component"]
        overlaps = by_ref.get(component, [])
        # Stable component ID tie break is for diagnostic display; assignment is
        # delegated to the evaluator's maximum-cardinality sparse matcher.
        best = max(
            overlaps, key=lambda item: (item["iou"], -item["prediction_component"]), default=None
        )
        assigned = assignments.get(component)
        selected = next(
            (item for item in overlaps if item["prediction_component"] == assigned), best
        )
        covered = sum(item["intersection_voxels"] for item in overlaps)
        matched = assigned is not None
        status = "matched" if matched else "partial" if covered else "missed"
        reason = (
            "matched_iou_threshold"
            if matched
            else "no_overlap"
            if not covered
            else "one_to_one_conflict"
            if best and best["iou"] >= iou_threshold
            else "below_iou_threshold"
        )
        lesion.update(
            status=status,
            status_reason=reason,
            detected=matched,
            matched_prediction_component=assigned,
            best_prediction_component=best["prediction_component"] if best else None,
            comparison_prediction_component=selected["prediction_component"] if selected else None,
            dice=selected["dice"] if selected else 0.0,
            iou=selected["iou"] if selected else 0.0,
            coverage_voxels=covered,
            coverage_fraction=covered / lesion["voxels"],
            missed_voxels=lesion["voxels"] - covered,
            overlapping_prediction_components=len(overlaps),
        )
    false_positives = []
    for component in _component_records(preds, n_preds, voxel_mm3):
        component_id = component["component"]
        if component_id in matched_preds:
            continue
        overlaps = by_pred.get(component_id, [])
        best = max(
            overlaps, key=lambda item: (item["iou"], -item["reference_component"]), default=None
        )
        overlap_voxels = sum(item["intersection_voxels"] for item in overlaps)
        component.update(
            status="false_positive",
            status_reason="unmatched_with_overlap" if overlaps else "no_reference_overlap",
            reference_overlap_voxels=overlap_voxels,
            reference_overlap_fraction=overlap_voxels / component["voxels"],
            best_reference_component=best["reference_component"] if best else None,
            best_reference_iou=best["iou"] if best else 0.0,
        )
        false_positives.append(component)
    reference_voxels, prediction_voxels = int(ref.sum()), int(pred.sum())
    true_positive_voxels = int(np.count_nonzero(ref & pred))
    false_negative_voxels = reference_voxels - true_positive_voxels
    false_positive_voxels = prediction_voxels - true_positive_voxels
    denominator = reference_voxels + prediction_voxels
    union_voxels = denominator - true_positive_voxels
    return {
        "schema_version": 1,
        "shape": list(ref.shape),
        "spacing_mm": list(spacing),
        "voxel_volume_mm3": voxel_mm3,
        "mass_label": int(mass_label),
        "mass": {
            "reference_voxels": reference_voxels,
            "prediction_voxels": prediction_voxels,
            "reference_volume_mm3": reference_voxels * voxel_mm3,
            "prediction_volume_mm3": prediction_voxels * voxel_mm3,
            "true_positive_voxels": true_positive_voxels,
            "false_negative_voxels": false_negative_voxels,
            "false_positive_voxels": false_positive_voxels,
            "dice": 2 * true_positive_voxels / denominator if denominator else None,
            "iou": true_positive_voxels / union_voxels if union_voxels else None,
            "false_negative_fraction_of_reference": false_negative_voxels / reference_voxels
            if reference_voxels
            else None,
            "false_positive_fraction_of_prediction": false_positive_voxels / prediction_voxels
            if prediction_voxels
            else None,
            "empty_status": "both_empty"
            if not denominator
            else "reference_empty"
            if not reference_voxels
            else "prediction_empty"
            if not prediction_voxels
            else "neither_empty",
            "prediction_size_filter_applied": False,
        },
        "lesion_detection": detection,
        "lesions": lesions,
        "false_positive_components": false_positives,
        "interpretation": "Connected-component agreement, not diagnosis or annotation certainty",
    }


def roi_coverage_metrics(
    reference: np.ndarray,
    spacing_mm: Sequence[float],
    bbox_native: Sequence[Sequence[int]],
    *,
    mass_label: int = 2,
    connectivity: int = 26,
) -> dict[str, Any]:
    """Audit a pre-existing native crop; never construct a crop from labels.

    Bounds are three ``[start, stop]`` pairs in native array order with exclusive
    upper bounds, matching ``torch_roi`` manifests. This is post-hoc evaluation
    of crop loss; labels must never be used to adjust validation/inference crops.
    """
    reference_mass = _mass_mask(reference, mass_label)
    spacing = _spacing(spacing_mm)
    bounds = np.asarray(bbox_native)
    if bounds.shape != (3, 2) or bounds.dtype.kind not in "iu":
        raise ValueError("bbox_native must contain three integer [start, stop] pairs")
    if any(
        not 0 <= int(lo) < int(hi) <= size
        for (lo, hi), size in zip(bounds, reference_mass.shape, strict=True)
    ):
        raise ValueError("bbox_native must be nonempty and within the native volume")
    refs, n_refs = _components(reference_mass, connectivity)
    slices = tuple(slice(int(lo), int(hi)) for lo, hi in bounds)
    inside = np.bincount(refs[slices].ravel(), minlength=n_refs + 1)
    lesions = _component_records(refs, n_refs, math.prod(spacing))
    for lesion in lesions:
        inside_voxels = int(inside[lesion["component"]])
        outside_voxels = lesion["voxels"] - inside_voxels
        lesion.update(
            inside_voxels=inside_voxels,
            outside_voxels=outside_voxels,
            outside_volume_mm3=outside_voxels * math.prod(spacing),
            inside_fraction=inside_voxels / lesion["voxels"],
            outside_fraction=outside_voxels / lesion["voxels"],
            completely_excluded=inside_voxels == 0,
            partially_excluded=0 < inside_voxels < lesion["voxels"],
        )
    reference_voxels = int(reference_mass.sum())
    inside_voxels = int(inside[1:].sum())
    outside_voxels = reference_voxels - inside_voxels
    return {
        "bbox_xyz": bounds.tolist(),
        "spacing_mm": list(spacing),
        "reference_mass_voxels": reference_voxels,
        "inside_mass_voxels": inside_voxels,
        "outside_mass_voxels": outside_voxels,
        "outside_mass_volume_mm3": outside_voxels * math.prod(spacing),
        "outside_mass_fraction": outside_voxels / reference_voxels if reference_voxels else None,
        "reference_lesions": n_refs,
        "completely_excluded_lesions": sum(item["completely_excluded"] for item in lesions),
        "partially_excluded_lesions": sum(item["partially_excluded"] for item in lesions),
        "fully_contained_lesions": sum(item["outside_voxels"] == 0 for item in lesions),
        "lesions": lesions,
        "interpretation": "Post-hoc coverage audit of a fixed crop; never a crop-selection rule",
    }


def _bucket_edges(edges: Sequence[float], label: str) -> tuple[float, float]:
    array = np.asarray(edges, dtype=float)
    if array.shape != (2,) or not np.isfinite(array).all() or not 0 < array[0] < array[1]:
        raise ValueError(f"{label} must contain two increasing finite positive values")
    return float(array[0]), float(array[1])


def _bucket_index(value: float, edges: tuple[float, float]) -> int:
    return 0 if value < edges[0] else 1 if value < edges[1] else 2


def _bucket_specs(edges: tuple[float, float], names: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "bucket": name,
            "lower_inclusive_mm": lower,
            "upper_exclusive_mm": upper,
        }
        for name, lower, upper in zip(names, (0.0, *edges), (*edges, None), strict=True)
    ]


def _summary(
    cases: Sequence[Mapping[str, Any]], lesions: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    statuses = [lesion["status"] for lesion in lesions]
    positives = [case for case in cases if case["mass"]["reference_voxels"] > 0]
    dices = [case["mass"]["dice"] for case in positives]
    voxel_denominator = sum(lesion["voxels"] for lesion in lesions)
    covered_voxels = sum(lesion["coverage_voxels"] for lesion in lesions)
    return {
        "cases": len(cases),
        "reference_positive_cases": len(positives),
        "reference_negative_cases": len(cases) - len(positives),
        "reference_lesions": len(lesions),
        "matched_lesions": statuses.count("matched"),
        "partial_lesions": statuses.count("partial"),
        "missed_lesions": statuses.count("missed"),
        "detection_false_negatives": statuses.count("partial") + statuses.count("missed"),
        "lesion_sensitivity": statuses.count("matched") / len(lesions) if lesions else None,
        "lesion_sensitivity_denominator": len(lesions),
        "mean_reference_coverage_fraction": float(
            np.mean([item["coverage_fraction"] for item in lesions])
        )
        if lesions
        else None,
        "mean_reference_coverage_denominator_lesions": len(lesions),
        "voxel_weighted_reference_coverage": covered_voxels / voxel_denominator
        if voxel_denominator
        else None,
        "voxel_weighted_coverage_denominator_voxels": voxel_denominator,
        "mean_positive_case_mass_dice": float(np.mean(dices)) if dices else None,
        "mean_mass_dice_denominator_cases": len(dices),
        "case_dice_scope": "whole scans contributing to this bucket, not lesion-specific Dice",
    }


def aggregate_failure_buckets(
    cases: Sequence[Mapping[str, Any]],
    *,
    diameter_edges_mm: Sequence[float] = (10.0, 20.0),
    slice_spacing_edges_mm: Sequence[float] = (1.5, 3.0),
    slice_axis: int | None = 2,
) -> dict[str, Any]:
    """Describe diameter and native-axis spacing strata with fixed boundaries.

    Input is a sequence of ``case_failure_metrics`` outputs from ONE model and
    cohort. Each entry counts as one scan; this is not patient-weighted inference.
    A scan with lesions in multiple size strata contributes to each relevant
    stratum, so diameter-bin case counts are nonadditive. Empty-reference scans
    contribute to spacing/overall summaries but not diameter bins. Caller must
    identify the acquisition slice axis: axis 2 is a convention, not a guarantee.
    ``slice_axis=None`` instead uses maximum native spacing as an explicitly
    labeled proxy. Contrast phase, scanner, site and diagnosis are not inferred.
    """
    diameter_edges = _bucket_edges(diameter_edges_mm, "diameter_edges_mm")
    spacing_edges = _bucket_edges(slice_spacing_edges_mm, "slice_spacing_edges_mm")
    if slice_axis is not None and (
        isinstance(slice_axis, bool)
        or not isinstance(slice_axis, (int, np.integer))
        or slice_axis not in {0, 1, 2}
    ):
        raise ValueError("slice_axis must be 0, 1, 2 or None (maximum-spacing proxy)")
    detection_policies = {
        (
            case["mass_label"],
            case["lesion_detection"]["iou_threshold"],
            case["lesion_detection"]["connectivity"],
            case["lesion_detection"]["minimum_prediction_volume_mm3"],
        )
        for case in cases
    }
    if len(detection_policies) > 1:
        raise ValueError("Cannot aggregate cases with different lesion detection policies")
    for case in cases:
        _spacing(case["spacing_mm"])
    diameters = _bucket_specs(diameter_edges, ("small", "medium", "large"))
    spacings = _bucket_specs(spacing_edges, ("thin", "intermediate", "thick"))
    for index, bucket in enumerate(diameters):
        selected_lesions: list[Mapping[str, Any]] = []
        selected_cases = []
        for case in cases:
            matching = [
                lesion
                for lesion in case["lesions"]
                if _bucket_index(lesion["equivalent_diameter_mm"], diameter_edges) == index
            ]
            if matching:
                selected_cases.append(case)
                selected_lesions.extend(matching)
        bucket.update(_summary(selected_cases, selected_lesions))
    for index, bucket in enumerate(spacings):
        selected_cases = [
            case
            for case in cases
            if _bucket_index(
                max(case["spacing_mm"]) if slice_axis is None else case["spacing_mm"][slice_axis],
                spacing_edges,
            )
            == index
        ]
        selected_lesions = [lesion for case in selected_cases for lesion in case["lesions"]]
        bucket.update(_summary(selected_cases, selected_lesions))
        fp_count = sum(case["lesion_detection"]["false_positives"] for case in selected_cases)
        bucket.update(
            false_positive_components=fp_count,
            false_positive_components_per_scan=fp_count / len(selected_cases)
            if selected_cases
            else None,
            false_positive_rate_denominator_scans=len(selected_cases),
        )
    lesions = [lesion for case in cases for lesion in case["lesions"]]
    overall = _summary(cases, lesions)
    fp_count = sum(case["lesion_detection"]["false_positives"] for case in cases)
    overall.update(
        false_positive_components=fp_count,
        false_positive_components_per_scan=fp_count / len(cases) if cases else None,
        false_positive_rate_denominator_scans=len(cases),
    )
    return {
        "diameter_buckets": diameters,
        "slice_spacing_buckets": spacings,
        "overall": overall,
        "policy": {
            "diameter_edges_mm": list(diameter_edges),
            "diameter_definition": "equal-volume sphere from native connected-component volume",
            "slice_spacing_edges_mm": list(spacing_edges),
            "slice_axis": int(slice_axis) if slice_axis is not None else None,
            "spacing_definition": "maximum native spacing proxy; not verified acquisition slice spacing"
            if slice_axis is None
            else "caller-specified native axis; caller must verify acquisition interpretation",
            "acquisition_metadata": "phase, scanner, site and diagnosis are not inferred",
            "boundaries": "lower inclusive, upper exclusive",
            "case_weighting": "equal scan weight, not patient weight",
            "diameter_case_counts": "nonadditive when one scan has multiple lesion sizes",
            "negative_scans": "included in spacing/overall; excluded from diameter buckets",
            "inference": "descriptive only; no independent-patient or model-comparison uncertainty",
        },
    }
