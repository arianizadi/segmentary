"""Comparison must preserve old artifacts, native cohorts and metric definitions."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "medical_blending_comparison_tested", SCRIPTS / "compare_medical_blending.py"
)
assert SPEC is not None and SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def _report():
    return {
        "manifest_fingerprint": "same",
        "protocol": {
            "pancreas_include_mass": True,
            "aggregation": "equal-patient",
            "empty_policy": "explicit",
        },
        "cases": [
            {
                "case_id": "a",
                "status": "ok",
                "reference_sha256": "same-mask",
                "metrics": {"mass": {"dice": 0.3}, "pancreas": {"dice": 0.8}},
            }
        ],
    }


def test_original_uniform_dice_agreement_requires_every_case_and_same_reference():
    actual = _report()
    assert comparison.compare_uniform_reference(actual, copy.deepcopy(actual)) == {
        "cases": 1,
        "maximum_absolute_dice_difference": 0.0,
        "passed": True,
    }
    for change in ("case", "mask", "status", "protocol", "score"):
        old = copy.deepcopy(actual)
        if change == "case":
            old["cases"][0]["case_id"] = "b"
        elif change == "mask":
            old["cases"][0]["reference_sha256"] = "wrong-mask"
        elif change == "status":
            old["cases"][0]["status"] = "failed_prediction"
        elif change == "protocol":
            old["protocol"]["pancreas_include_mass"] = False
        else:
            old["cases"][0]["metrics"]["mass"]["dice"] += 0.001
        with pytest.raises(ValueError):
            comparison.compare_uniform_reference(actual, old)


def test_diagnostic_output_cannot_touch_original_source_or_workspace(tmp_path):
    old = tmp_path / "original"
    source = tmp_path / "source"
    for output in (old, old / "diagnostic", source, source / "diagnostic"):
        with pytest.raises(ValueError, match="separate"):
            comparison.validate_output(output, old, source)
    valid = tmp_path / "new-output"
    comparison.validate_output(valid, old, source)
    valid.mkdir()
    with pytest.raises(FileExistsError):
        comparison.validate_output(valid, old, source)


def test_validation_selection_has_no_path_to_training_or_test_payloads(monkeypatch):
    from segmentary.medical import backend

    manifest = {
        "cases": [
            {
                "case_id": name,
                "annotation_status": "labeled",
                "image": f"/forbidden/{name}",
                "label": f"/forbidden/{name}-label",
            }
            for name in ("train", "val", "test")
        ]
    }
    split = {"train": ["train"], "val": ["val"], "test": ["test"]}
    monkeypatch.setattr(backend, "_documents", lambda *_: (manifest, split))
    cases = comparison.validation_cases({"manifest_path": "metadata", "splits_path": "metadata"})
    assert [case["case_id"] for case in cases] == ["val"]
    split["val"].append("test")
    with pytest.raises(ValueError, match="forbidden partition"):
        comparison.validation_cases({"manifest_path": "metadata", "splits_path": "metadata"})
