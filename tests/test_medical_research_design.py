"""Study binding, missing-case accounting and patient/seed inference boundaries."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from segmentary.medical.research_design import (
    build_architecture_study,
    compare_failure_reports,
    document_sha256,
    validate_architecture_study,
)


def cohort():
    return {
        "manifest_sha256": "a" * 64,
        "splits_sha256": "b" * 64,
        "partition": "val",
        "reference_fingerprint": "c" * 64,
    }


def study(tmp_path):
    return build_architecture_study(
        base_recipe={"workspace": str(tmp_path / "original"), "model": "dynunet"},
        arms={
            "baseline": {"description": "Original trained recipe", "changes": {}},
            "candidate": {
                "description": "Auxiliary decoder supervision",
                "changes": {"model_options": {"deep_supervision": True}},
            },
            "component_off": {"description": "Candidate without added component", "changes": {}},
            "capacity_control": {
                "description": "Wider ordinary model",
                "changes": {"model_options": {"filters": [40, 80, 160, 256, 320]}},
            },
        },
        hypothesis="Auxiliary heads reduce small-mass misses",
        cohort=cohort(),
        source_commit="a" * 40,
        workspace_root=str(tmp_path / "future"),
    )


def report(baseline, candidate, seed=0):
    assert len(baseline) == len(candidate)
    return {
        "kind": "medical_failure_analysis",
        "cohort": cohort(),
        "report_id": "report",
        "protocol": {"min_overlap": 0.1},
        "models": {"a": {"seed": seed}, "b": {"seed": seed}},
        "cases": [
            {
                "case_key": f"case-{i}",
                "patient_key": "patient-0" if i < 2 else f"patient-{i}",
                "models": {
                    "a": {"status": "completed", "mass_dice": a, "pancreas_dice": a},
                    "b": {"status": "completed", "mass_dice": b, "pancreas_dice": b},
                },
            }
            for i, (a, b) in enumerate(zip(baseline, candidate, strict=True))
        ],
    }


def pair(value, seed=0):
    return {
        "baseline_report": value,
        "candidate_report": value,
        "baseline_model": "a",
        "candidate_model": "b",
        "training_seed": seed,
    }


def test_study_expands_four_roles_and_seeds_without_touching_workspaces(tmp_path):
    value = study(tmp_path)
    assert len(value["runs"]) == 12 and value["seeds"] == [0, 1, 2]
    assert value["runnable_campaign"] is False
    assert not (tmp_path / "future").exists()
    validate_architecture_study(json.loads(json.dumps(value)))
    for run in value["runs"].values():
        assert run["recipe"]["initialization"] == "scratch"
        assert run["recipe"]["seed"] == run["seed"]


@pytest.mark.parametrize("change", ["recipe", "seed", "policy", "hash", "partition"])
def test_study_rejects_drift_even_if_prose_stays_the_same(tmp_path, change):
    value = study(tmp_path)
    if change == "recipe":
        value["runs"]["candidate-seed0"]["recipe"]["learning_rate"] = 0.5
    elif change == "seed":
        value["seeds"] = [0, 0]
    elif change == "policy":
        value["comparison_policy"]["missing_pairs"] = "discard"
    elif change == "partition":
        value["cohort"]["partition"] = "test"
    else:
        value["fingerprint"] = "e" * 64
    with pytest.raises(ValueError):
        validate_architecture_study(value)


def test_study_refuses_pretraining_hidden_in_model_options(tmp_path):
    value = study(tmp_path)
    value["arms"]["candidate"]["changes"]["model_options"]["weights"] = "imagenet"
    with pytest.raises(ValueError, match="weights"):
        validate_architecture_study(value)


def test_patient_weighting_and_seed_variation_are_distinct():
    # Three scans from two patients: first patient's two scans must not double its weight.
    zero = report([0.0, 0.0, 0.0], [0.2, 0.4, 0.9], seed=0)
    one = report([0.0, 0.0, 0.0], [0.4, 0.6, 0.7], seed=1)
    result = compare_failure_reports([pair(zero), pair(one, 1)], bootstrap_samples=200)
    assert result["conditional_patient_bootstrap"]["mean"] == pytest.approx(0.6)
    assert result["conditional_patient_bootstrap"]["patients"] == 2
    assert result["training_seed_variation"]["sample_sd_of_patient_mean_delta"] == pytest.approx(0)
    assert result["complete_pairs"] == result["expected_pairs"] == 6


def test_missing_prediction_withholds_inference_instead_of_disappearing():
    value = report([0.2, 0.3, 0.4], [0.3, 0.4, 0.5])
    value["cases"][1]["models"]["b"] = {"status": "failed"}
    result = compare_failure_reports([pair(value)], bootstrap_samples=20)
    assert result["status"] == "incomplete_inference_withheld"
    assert result["conditional_patient_bootstrap"] is None
    assert result["complete_pairs"] == 2 and result["expected_pairs"] == 3
    assert result["missing_pairs"][0]["case_key"] == "case-1"
    assert result["missing_pairs"][0]["errors"]["candidate"] == "model_status:failed"


@pytest.mark.parametrize(
    "problem", ["case_removed", "duplicate", "patient", "reference", "protocol", "test", "seed"]
)
def test_pairing_rejects_incomparable_reports(problem):
    value = report([0.1, 0.2, 0.3], [0.2, 0.3, 0.4])
    other = copy.deepcopy(value)
    if problem == "case_removed":
        other["cases"].pop()
    elif problem == "duplicate":
        other["cases"].append(other["cases"][0])
    elif problem == "patient":
        other["cases"][0]["patient_key"] = "someone-else"
    elif problem == "reference":
        other["cohort"]["reference_fingerprint"] = "d" * 64
    elif problem == "protocol":
        other["protocol"]["min_overlap"] = 0.9
    elif problem == "seed":
        other["models"]["b"]["seed"] = 1
    else:
        other["cohort"]["partition"] = "test"
    declaration = pair(value) | {"candidate_report": other}
    with pytest.raises(ValueError):
        compare_failure_reports([declaration], bootstrap_samples=20)


@pytest.mark.parametrize("score", [-0.1, 1.1, float("nan"), True])
def test_invalid_scores_are_errors_not_missing(score):
    with pytest.raises(ValueError):
        compare_failure_reports([pair(report([0.2], [score]))], bootstrap_samples=20)


def test_single_patient_no_interval_and_duplicate_seed_rejected():
    value = pair(report([0.2], [0.4]))
    result = compare_failure_reports([value], bootstrap_samples=20)
    assert result["conditional_patient_bootstrap"]["ci"] is None
    assert result["training_seed_variation"]["sample_sd_of_patient_mean_delta"] is None
    with pytest.raises(ValueError, match="distinct"):
        compare_failure_reports([value, value], bootstrap_samples=20)


def test_comparison_cli_writes_create_only_artifacts(tmp_path):
    script = Path(__file__).parents[1] / "scripts/compare_medical_failure_reports.py"
    spec = importlib.util.spec_from_file_location("research_compare_cli", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    (tmp_path / "report.json").write_text(json.dumps(report([0.1, 0.2, 0.3], [0.2, 0.3, 0.4])))
    pairs = [
        {
            "baseline_report": "report.json",
            "candidate_report": "report.json",
            "baseline_model": "a",
            "candidate_model": "b",
            "training_seed": 0,
        }
    ]
    (tmp_path / "pairs.json").write_text(json.dumps(pairs))
    argv = [
        "--pairs",
        str(tmp_path / "pairs.json"),
        "--output",
        str(tmp_path / "out"),
        "--bootstrap-samples",
        "20",
    ]
    cli.main(argv)
    assert (tmp_path / "out/README.md").exists()
    assert json.loads((tmp_path / "out/comparison.json").read_text())["status"] == "completed"
    with pytest.raises(FileExistsError):
        cli.main(argv)


def test_list_model_metadata_checks_seeds_and_checkpoint_reuse():
    zero = report([0.1, 0.2, 0.3], [0.2, 0.3, 0.4])
    zero["models"] = [
        {"id": "a", "seed": None, "checkpoint_sha256": "1" * 64},
        {"id": "b", "seed": None, "checkpoint_sha256": "2" * 64},
    ]
    result = compare_failure_reports([pair(zero)], bootstrap_samples=20)
    assert result["sources"][0]["baseline"]["seed_verified_from_metadata"] is False
    one = copy.deepcopy(zero)
    one["report_id"] = "another-report-with-same-checkpoints"
    with pytest.raises(ValueError, match="masquerade"):
        compare_failure_reports([pair(zero), pair(one, 1)], bootstrap_samples=20)
    zero["models"][1]["seed"] = 5
    with pytest.raises(ValueError, match="metadata"):
        compare_failure_reports([pair(zero)], bootstrap_samples=20)


def test_planner_cli_binds_reference_and_writes_valid_protocol(tmp_path, monkeypatch):
    from segmentary.medical.geometry import sha256_file

    script = Path(__file__).parents[1] / "scripts/plan_medical_architecture_study.py"
    spec = importlib.util.spec_from_file_location("research_plan_cli", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    manifest = {
        "cases": [
            {
                "case_id": "case0",
                "patient_id": "patient0",
                "image_sha256": "1" * 64,
                "label_sha256": "2" * 64,
            }
        ]
    }
    splits = {"val": ["case0"]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "splits.json").write_text(json.dumps(splits))
    # Isolate CLI binding/output behavior; manifest and split validation have dedicated suites.
    monkeypatch.setattr(cli, "load_manifest", lambda _path: manifest)
    monkeypatch.setattr(cli, "validate_splits", lambda *_: None)
    value = study(tmp_path)
    binding = cohort() | {
        "manifest_sha256": sha256_file(tmp_path / "manifest.json"),
        "splits_sha256": sha256_file(tmp_path / "splits.json"),
        "reference_fingerprint": document_sha256([["case0", "patient0", "1" * 64, "2" * 64]]),
    }
    failure = {
        "kind": "medical_failure_analysis",
        "cohort": binding,
        "cases": [{"case_key": "case0"}],
    }
    (tmp_path / "report.json").write_text(json.dumps(failure))
    (tmp_path / "base.json").write_text(json.dumps(value["base_recipe"]))
    definition = {
        "hypothesis": value["hypothesis"],
        "arms": {
            role: {key: arm[key] for key in ("description", "changes")}
            for role, arm in value["arms"].items()
        },
    }
    (tmp_path / "definition.json").write_text(json.dumps(definition))
    argv = [
        "--base-recipe",
        str(tmp_path / "base.json"),
        "--definition",
        str(tmp_path / "definition.json"),
        "--manifest",
        str(tmp_path / "manifest.json"),
        "--splits",
        str(tmp_path / "splits.json"),
        "--cohort-report",
        str(tmp_path / "report.json"),
        "--source-commit",
        "a" * 40,
        "--workspace-root",
        str(tmp_path / "new-workspaces"),
        "--output",
        str(tmp_path / "plan"),
    ]
    cli.main(argv)
    planned = json.loads((tmp_path / "plan/study.json").read_text())
    validate_architecture_study(planned)
    assert len(list((tmp_path / "plan/recipes").glob("*.json"))) == 12
    assert not (tmp_path / "new-workspaces").exists()
    cli.main(["--validate", str(tmp_path / "plan/study.json")])
    failure["cohort"]["reference_fingerprint"] = "e" * 64
    (tmp_path / "report.json").write_text(json.dumps(failure))
    argv[-1] = str(tmp_path / "other-plan")
    with pytest.raises(ValueError, match="bind"):
        cli.main(argv)
    assert not (tmp_path / "other-plan").exists()
