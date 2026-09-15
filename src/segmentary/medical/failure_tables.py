"""Readable, create-only tables from already computed failure evidence."""

from __future__ import annotations

import csv
import html
import io
import itertools
import json
import math
from pathlib import Path
from typing import Any


def _md(value: Any) -> str:
    return (
        html.escape(str(value), quote=False)
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("`", "\\`")
        .replace("*", "\\*")
        .replace("_", "\\_")
    )


def _integer(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _number(value: Any, field: str, *, fraction: bool = False) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (fraction and not 0 <= value <= 1)
    ):
        raise ValueError(f"{field} must be a finite scalar" + (" in [0,1]" if fraction else ""))
    return float(value)


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), allow_nan=False)
    # Text stays text when opened in a spreadsheet. Numeric negative deltas
    # remain numeric; formulas in external identifiers must not execute.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv_text(fields: list[str], rows: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_cell(row.get(key)) for key in fields})
    return stream.getvalue()


def _bucket_line(name: str, bucket: dict[str, Any]) -> str:
    counts = {
        key: _integer(bucket[key], key)
        for key in (
            "cases",
            "reference_positive_cases",
            "reference_lesions",
            "matched_lesions",
            "partial_lesions",
            "missed_lesions",
            "mean_mass_dice_denominator_cases",
        )
    }
    if (
        counts["matched_lesions"] + counts["partial_lesions"] + counts["missed_lesions"]
        != counts["reference_lesions"]
    ):
        raise ValueError("Lesion status counts must cover the reference denominator")
    if (
        counts["mean_mass_dice_denominator_cases"] != counts["reference_positive_cases"]
        or counts["reference_positive_cases"] > counts["cases"]
    ):
        raise ValueError("Case Dice denominator differs from eligible positive scans")
    dice = _number(
        bucket.get("mean_positive_case_mass_dice"), "mean_positive_case_mass_dice", fraction=True
    )
    if (dice is None) != (counts["mean_mass_dice_denominator_cases"] == 0):
        raise ValueError("Mean Dice availability contradicts its denominator")
    fp = bucket.get("false_positive_components")
    fp_text = (
        "not assigned to size bins"
        if fp is None
        else str(_integer(fp, "false_positive_components"))
    )
    mean = (
        "unavailable (n=0)"
        if dice is None
        else f"{dice:.4f} (n={counts['mean_mass_dice_denominator_cases']})"
    )
    return f"| {_md(name)} | {counts['cases']} | {counts['reference_lesions']} | {counts['matched_lesions']} | {counts['partial_lesions']} | {counts['missed_lesions']} | {fp_text} | {mean} |"


def _validate_component(item: dict[str, Any], *, reference: bool) -> None:
    if (
        _integer(item.get("component"), "component") < 1
        or _integer(item.get("voxels"), "voxels") < 1
    ):
        raise ValueError("Components must have positive IDs and volumes")
    for key in ("volume_mm3", "equivalent_diameter_mm"):
        value = _number(item.get(key), key)
        if value is None or value <= 0:
            raise ValueError("Component physical dimensions must be positive")
    bbox = item.get("bbox_xyz")
    if (
        not isinstance(bbox, list)
        or len(bbox) != 3
        or any(
            not isinstance(axis, list)
            or len(axis) != 2
            or any(type(v) is not int for v in axis)
            or not 0 <= axis[0] < axis[1]
            for axis in bbox
        )
    ):
        raise ValueError("Component native bounds must be three positive [start,stop] pairs")
    if reference:
        if item.get("status") not in {"matched", "partial", "missed"}:
            raise ValueError("Unknown reference lesion status")
        for key in ("dice", "iou", "coverage_fraction"):
            if _number(item.get(key), key, fraction=True) is None:
                raise ValueError("Reference lesion scores must be present")


def write_failure_tables(output: Path, report: dict[str, Any]) -> None:
    """Render aggregate/lesion/crop/disagreement tables without image or label I/O.

    Invalid outcomes remain explicit. All-model miss flags describe zero-overlap
    reference components on complete cases; they do not establish a cause.
    """
    if report.get("kind") != "medical_failure_analysis":
        raise ValueError("Expected medical_failure_analysis report")
    files = ("failure-patterns.md", "lesions.csv", "crop-coverage.csv", "model-disagreements.csv")
    if any((output / name).exists() or (output / name).is_symlink() for name in files):
        raise FileExistsError("Failure tables are create-only")
    model_meta, cases = report.get("models"), report.get("cases")
    if (
        not isinstance(model_meta, list)
        or not model_meta
        or not isinstance(cases, list)
        or not cases
    ):
        raise ValueError("Tables require declared models and a complete case inventory")
    models = [item.get("id") for item in model_meta]
    if any(not isinstance(mid, str) or not mid for mid in models) or len(set(models)) != len(
        models
    ):
        raise ValueError("Model IDs must be unique nonempty text")
    case_keys = [row.get("case_key") for row in cases]
    if any(not isinstance(key, str) or not key for key in case_keys) or len(set(case_keys)) != len(
        cases
    ):
        raise ValueError("Case inventory must have unique nonempty keys")
    lesions, crops, disagreements = [], [], []
    valid_counts = dict.fromkeys(models, 0)
    all_missed_cases = 0
    complete_case_count = 0
    for case in cases:
        key, patient = case["case_key"], case.get("patient_key")
        if (
            not isinstance(patient, str)
            or not patient
            or set(case.get("models", {})) != set(models)
        ):
            raise ValueError("Every case needs patient identity and every declared model outcome")
        identities = []
        miss_sets = []
        for mid in models:
            result = case["models"][mid]
            common = {
                "case_key": key,
                "patient_key": patient,
                "model": mid,
                "model_status": result.get("status"),
            }
            if result.get("status") != "ok":
                lesions.append(
                    {
                        **common,
                        "record_type": "unavailable",
                        "status_reason": "No valid prediction/reference diagnostics",
                    }
                )
                continue
            valid_counts[mid] += 1
            _number(result.get("mass_dice"), "mass_dice", fraction=True)
            detail = result["diagnostics"]
            ref_lesions = detail["lesions"]
            fp_components = detail["false_positive_components"]
            if len({item["component"] for item in ref_lesions}) != len(ref_lesions):
                raise ValueError("Duplicate reference lesion component")
            identities.append(
                [
                    (item["component"], item["voxels"], item["volume_mm3"], item["bbox_xyz"])
                    for item in ref_lesions
                ]
            )
            miss_sets.append(
                {item["component"] for item in ref_lesions if item["status"] == "missed"}
            )
            for record_type, entries in (
                ("reference_lesion", ref_lesions),
                ("unmatched_prediction_component", fp_components),
            ):
                for item in entries:
                    _validate_component(item, reference=record_type == "reference_lesion")
                    lesions.append(
                        {
                            **common,
                            "record_type": record_type,
                            "spacing_xyz_mm": detail["spacing_mm"],
                            **{name: item.get(name) for name in LESION_DETAIL_FIELDS},
                        }
                    )
            roi = result.get("roi")
            if roi is not None:
                for name in (
                    "reference_mass_voxels",
                    "inside_mass_voxels",
                    "outside_mass_voxels",
                    "reference_lesions",
                    "completely_excluded_lesions",
                    "partially_excluded_lesions",
                    "fully_contained_lesions",
                ):
                    _integer(roi.get(name), name)
                if (
                    roi["inside_mass_voxels"] + roi["outside_mass_voxels"]
                    != roi["reference_mass_voxels"]
                    or sum(
                        roi[name]
                        for name in (
                            "completely_excluded_lesions",
                            "partially_excluded_lesions",
                            "fully_contained_lesions",
                        )
                    )
                    != roi["reference_lesions"]
                ):
                    raise ValueError("Crop counts do not cover their reference denominators")
                _number(roi.get("outside_mass_fraction"), "outside_mass_fraction", fraction=True)
                crops.append(
                    {
                        **common,
                        "record_type": "case",
                        **{name: roi.get(name) for name in CROP_CASE_FIELDS},
                    }
                )
                for item in roi["lesions"]:
                    crops.append(
                        {
                            **common,
                            "record_type": "reference_lesion",
                            "bbox_xyz": roi["bbox_xyz"],
                            "spacing_mm": roi["spacing_mm"],
                            **{name: item.get(name) for name in CROP_LESION_FIELDS},
                        }
                    )
        if identities and any(identity != identities[0] for identity in identities):
            raise ValueError("Models disagree on reference lesion identities")
        all_valid = len(identities) == len(models)
        complete_case_count += all_valid
        common_missed = len(set.intersection(*miss_sets)) if all_valid and miss_sets else None
        all_missed = bool(
            all_valid and len(models) >= 2 and identities[0] and common_missed == len(identities[0])
        )
        all_missed_cases += all_missed
        for first, second in itertools.combinations(models, 2):
            a, b = case["models"][first], case["models"][second]
            a_score = (
                _number(a.get("mass_dice"), "mass_dice", fraction=True)
                if a.get("status") == "ok"
                else None
            )
            b_score = (
                _number(b.get("mass_dice"), "mass_dice", fraction=True)
                if b.get("status") == "ok"
                else None
            )
            disagreements.append(
                {
                    "case_key": key,
                    "patient_key": patient,
                    "model_a": first,
                    "model_b": second,
                    "status_a": a.get("status"),
                    "status_b": b.get("status"),
                    "mass_dice_a": a_score,
                    "mass_dice_b": b_score,
                    "mass_dice_b_minus_a": b_score - a_score
                    if a_score is not None and b_score is not None
                    else None,
                    "all_models_valid": all_valid,
                    "all_models_missed_all_reference_lesions": all_missed if all_valid else None,
                    "common_zero_overlap_reference_lesions": common_missed,
                    "reference_lesions": len(identities[0]) if identities else None,
                    "flags_a": a.get("flags", []),
                    "flags_b": b.get("flags", []),
                }
            )
    lines = [
        "# Failure patterns",
        "",
        "Descriptive review evidence, not a diagnosis, annotation correction or architecture performance claim.",
        "",
        "Matched/partial/missed counts refer to reference connected components (lesion proxies). Partial overlap below the one-to-one IoU matching rule is still a detection false negative. Missed means zero overlap. Unmatched prediction components are extra detections under that rule.",
        "",
        "Mass Dice means below give equal weight to positive-reference scans, not lesions or patients. Matched/reference is lesion-weighted. Size-bin scan counts can overlap when one scan contains multiple lesion sizes; size-bin Dice is whole-scan Dice, not a lesion Dice. Prediction components are not assigned to reference-size bins. Spacing strata follow the report's declared canonical axis, not inferred scanner/site/contrast metadata.",
        "",
    ]
    for mid in models:
        summary = report["summaries"][mid]
        if (
            summary.get("eligible_cases") != len(cases)
            or summary.get("valid_cases") != valid_counts[mid]
            or summary.get("complete") is not (valid_counts[mid] == len(cases))
        ):
            raise ValueError("Summary completeness differs from explicit case outcomes")
        buckets = summary["buckets"]
        if buckets["overall"].get("cases") != valid_counts[mid]:
            raise ValueError("Summary buckets differ from the valid case denominator")
        lines.extend(
            [
                f"## {_md(mid)}",
                "",
                f"Valid cases: **{valid_counts[mid]}/{len(cases)}**. "
                + (
                    "Complete descriptive cohort."
                    if summary["complete"]
                    else "**Incomplete cohort: available-case patterns only; no aggregate performance inference.**"
                ),
                "",
                "| Stratum | Valid scans | Reference lesions | Matched | Partial (false negative) | Missed (zero overlap) | Extra prediction components | Mean positive-scan mass Dice |",
                "|---|---:|---:|---:|---:|---:|---|---|",
                _bucket_line("Overall", buckets["overall"]),
            ]
        )
        for family, label in (
            ("diameter_buckets", "Equivalent lesion diameter"),
            ("slice_spacing_buckets", "Slice spacing"),
        ):
            for bucket in buckets[family]:
                lo, hi = bucket["lower_inclusive_mm"], bucket["upper_exclusive_mm"]
                extent = f"[{lo}, {hi}) mm" if hi is not None else f"[{lo}, infinity) mm"
                lines.append(_bucket_line(f"{label}: {bucket['bucket']} {extent}", bucket))
        lines.append("")
    lines.extend(
        [
            "## Model agreement and crop coverage",
            "",
            f"Cases with valid diagnostics for every model: {complete_case_count}/{len(cases)}. With at least two models, cases where every model has zero overlap with every reference lesion: {all_missed_cases}/{complete_case_count} complete cases (zero-reference cases cannot trigger this flag).",
            "Pairwise CSV values are scalar Dice differences on the same scan, not spatial disagreement maps or evidence about why a model failed. Missing scores remain blank and carry their status. Common misses do not establish impossible images or incorrect annotations.",
            "",
            f"Fixed-crop coverage records available: {sum(row['record_type'] == 'case' for row in crops)} case/model pairs. Missing crop records are not assumed to have zero excluded tumor. Crop coverage is a post-hoc audit; reference labels must never select or repair inference crops.",
            "",
            "Files: [lesions.csv](lesions.csv), [crop-coverage.csv](crop-coverage.csv), [model-disagreements.csv](model-disagreements.csv). Native bounding-box ends are exclusive; dimensions and spacing follow native array axes. CSVs retain pseudonymous case/patient IDs and are research data.",
            "",
        ]
    )
    contents = {
        "failure-patterns.md": "\n".join(lines),
        "lesions.csv": _csv_text(
            [*COMMON_FIELDS, "record_type", "spacing_xyz_mm", *LESION_DETAIL_FIELDS], lesions
        ),
        "crop-coverage.csv": _csv_text(
            [*COMMON_FIELDS, "record_type", *CROP_CASE_FIELDS, *CROP_LESION_FIELDS], crops
        ),
        "model-disagreements.csv": _csv_text(DISAGREEMENT_FIELDS, disagreements),
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        with (output / name).open("x", newline="") as stream:
            stream.write(content)


COMMON_FIELDS = ["case_key", "patient_key", "model", "model_status"]
LESION_DETAIL_FIELDS = [
    "component",
    "status",
    "status_reason",
    "voxels",
    "volume_mm3",
    "equivalent_diameter_mm",
    "bbox_xyz",
    "detected",
    "matched_prediction_component",
    "best_prediction_component",
    "comparison_prediction_component",
    "dice",
    "iou",
    "coverage_voxels",
    "coverage_fraction",
    "missed_voxels",
    "overlapping_prediction_components",
    "reference_overlap_voxels",
    "reference_overlap_fraction",
    "best_reference_component",
    "best_reference_iou",
]
CROP_CASE_FIELDS = [
    "bbox_xyz",
    "spacing_mm",
    "empty_prediction_fallback",
    "reference_mass_voxels",
    "inside_mass_voxels",
    "outside_mass_voxels",
    "outside_mass_volume_mm3",
    "outside_mass_fraction",
    "reference_lesions",
    "completely_excluded_lesions",
    "partially_excluded_lesions",
    "fully_contained_lesions",
]
CROP_LESION_FIELDS = [
    "component",
    "voxels",
    "volume_mm3",
    "equivalent_diameter_mm",
    "inside_voxels",
    "outside_voxels",
    "outside_volume_mm3",
    "inside_fraction",
    "outside_fraction",
    "completely_excluded",
    "partially_excluded",
]
DISAGREEMENT_FIELDS = [
    "case_key",
    "patient_key",
    "model_a",
    "model_b",
    "status_a",
    "status_b",
    "mass_dice_a",
    "mass_dice_b",
    "mass_dice_b_minus_a",
    "all_models_valid",
    "all_models_missed_all_reference_lesions",
    "common_zero_overlap_reference_lesions",
    "reference_lesions",
    "flags_a",
    "flags_b",
]
