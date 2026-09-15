"""Readable summaries preserve lesion/case denominators and missing outcomes."""

import copy
import csv

import numpy as np
import pytest

from segmentary.medical.failure_metrics import (
    aggregate_failure_buckets,
    case_failure_metrics,
    roi_coverage_metrics,
)
from segmentary.medical.failure_tables import write_failure_tables


def fixture_report(*, all_missed=False):
    reference = np.zeros((20, 20, 20), dtype=np.uint8)
    reference[1:3, 1:3, 1:3] = 2
    reference[6:9, 6:9, 6:9] = 2
    reference[14:16, 14:16, 14:16] = 2
    pred = np.zeros_like(reference)
    if not all_missed:
        pred[1:3, 1:3, 1:3] = 2
        pred[6, 6, 6] = 2
        pred[1:3, 15:17, 1:3] = 2
    models = ["=unsafe|model", "b"]
    values = {}
    summaries = {}
    for mid, prediction in zip(models, (pred, np.zeros_like(pred)), strict=True):
        detail = case_failure_metrics(reference, prediction, [1, 1, 2])
        values[mid] = {
            "status": "ok",
            "mass_dice": detail["mass"]["dice"],
            "diagnostics": detail,
            "flags": ["review"],
        }
        summaries[mid] = {
            "eligible_cases": 2,
            "valid_cases": 1,
            "complete": False,
            "buckets": aggregate_failure_buckets([detail]),
        }
    values[models[0]]["roi"] = roi_coverage_metrics(
        reference, [1, 1, 2], [[0, 10], [0, 10], [0, 10]]
    )
    values[models[0]]["roi"]["empty_prediction_fallback"] = False
    return {
        "kind": "medical_failure_analysis",
        "models": [{"id": mid} for mid in models],
        "cases": [
            {"case_key": "c1", "patient_key": "p1", "models": values},
            {
                "case_key": "c2",
                "patient_key": "p2",
                "models": {mid: {"status": "invalid_prediction"} for mid in models},
            },
        ],
        "summaries": summaries,
    }


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def test_native_lesions_crop_and_disagreements_keep_explicit_denominators(tmp_path):
    report = fixture_report()
    write_failure_tables(tmp_path, report)
    text = (tmp_path / "failure-patterns.md").read_text()
    assert "Valid cases: **1/2**" in text and "Incomplete cohort" in text
    assert "| Overall | 1 | 3 | 1 | 1 | 1 | 2 |" in text
    assert "=unsafe\\|model" in text
    lesions = rows(tmp_path / "lesions.csv")
    assert len([row for row in lesions if row["record_type"] == "reference_lesion"]) == 6
    assert (
        len([row for row in lesions if row["record_type"] == "unmatched_prediction_component"]) == 2
    )
    assert len([row for row in lesions if row["record_type"] == "unavailable"]) == 2
    assert lesions[0]["model"].startswith("'=unsafe")
    assert float(lesions[0]["volume_mm3"]) == 16
    crop = rows(tmp_path / "crop-coverage.csv")
    assert len(crop) == 4
    assert crop[0]["completely_excluded_lesions"] == "1"
    assert crop[0]["outside_mass_voxels"] == "8"
    diff = rows(tmp_path / "model-disagreements.csv")
    assert len(diff) == 2
    assert float(diff[0]["mass_dice_b_minus_a"]) < 0
    assert diff[0]["common_zero_overlap_reference_lesions"] == "1"
    assert diff[0]["all_models_missed_all_reference_lesions"] == "False"
    assert diff[1]["mass_dice_b_minus_a"] == ""
    assert diff[1]["all_models_missed_all_reference_lesions"] == ""
    with pytest.raises(FileExistsError):
        write_failure_tables(tmp_path, report)


def test_shared_miss_flag_requires_complete_models_and_zero_overlap(tmp_path):
    report = fixture_report(all_missed=True)
    write_failure_tables(tmp_path, report)
    diff = rows(tmp_path / "model-disagreements.csv")
    assert diff[0]["all_models_missed_all_reference_lesions"] == "True"
    assert diff[0]["common_zero_overlap_reference_lesions"] == "3"
    assert diff[1]["all_models_missed_all_reference_lesions"] == ""
    assert "1/1 complete cases" in (tmp_path / "failure-patterns.md").read_text()


@pytest.mark.parametrize(
    "corruption", ["summary", "lesions", "crop", "score", "inventory", "reference"]
)
def test_invalid_counts_or_evidence_fail_before_writing(tmp_path, corruption):
    report = copy.deepcopy(fixture_report())
    mid = report["models"][0]["id"]
    if corruption == "summary":
        report["summaries"][mid]["valid_cases"] = 2
    elif corruption == "lesions":
        report["summaries"][mid]["buckets"]["overall"]["matched_lesions"] = 5
    elif corruption == "crop":
        report["cases"][0]["models"][mid]["roi"]["outside_mass_voxels"] = 100
    elif corruption == "score":
        report["cases"][0]["models"][mid]["mass_dice"] = float("nan")
    elif corruption == "inventory":
        del report["cases"][1]["models"][mid]
    else:
        report["cases"][0]["models"][mid]["diagnostics"]["lesions"][0]["volume_mm3"] = 99
    with pytest.raises(ValueError):
        write_failure_tables(tmp_path / "new", report)
    assert not (tmp_path / "new").exists()
