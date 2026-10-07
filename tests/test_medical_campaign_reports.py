"""Reporting must not turn incomplete or incompatible experiments into winners."""

from __future__ import annotations

import copy
import csv
import importlib.util
import io
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts/report_medical_campaign.py"
_SPEC = importlib.util.spec_from_file_location("medical_campaign_report", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
reporter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reporter)


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_nnunet_report_uses_actual_plan_and_completed_training_without_private_paths(tmp_path):
    workspace = tmp_path / "run"
    config = {
        "workspace": str(workspace),
        "backend": "nnunet",
        "architecture": "dynunet",
        "reference_workspace": "/private/reference",
        "seed": 0,
    }
    config_path = tmp_path / "config.json"
    write(config_path, config)
    write(workspace / "binding.json", {"config": config, "initialization": "scratch"})
    write(workspace / "training-result.json", {"completed": True, "steps": 250000})
    write(
        workspace / "trainer-settings.json",
        {
            "num_epochs": 1000,
            "num_iterations_per_epoch": 250,
        },
    )
    write(workspace / "plan-binding.json", {"runtime": {"packages": {"nnunetv2": "2.8.1"}}})
    write(
        workspace / "nnUNet_preprocessed/Dataset707_Pancreas/nnUNetResEncUNetLPlans.json",
        {
            "configurations": {
                "3d_fullres": {
                    "patch_size": [56, 320, 256],
                    "batch_size": 2,
                    "batch_dice": False,
                }
            },
        },
    )
    write(
        workspace / "training-telemetry.json",
        {
            "status": "completed",
            "peak_allocated_gpu_bytes": 1234,
        },
    )
    row = reporter._collect_run(
        {"id": "dynunet", "model": "nnunet_planned_dynunet", "config": str(config_path)},
        {"status": "completed"},
        tmp_path / "state",
        [],
        0,
    )
    assert row["training_complete"] and row["completed_steps"] == row["budget_steps"] == 250000
    assert row["recipe"]["patch_size"] == [56, 320, 256]
    assert row["recipe"]["batch_size"] == 2 and row["recipe"]["batch_dice"] is False
    assert row["recipe"]["effective_training_budget"]["optimizer_steps"] == 250000
    assert set(row["recipe"]["effective_training_budget"]["sources"].values()) == {
        "trainer-settings"
    }
    assert row["runtime_fingerprint"]
    assert row["peak_allocated_bytes"] == 1234
    assert "/private/reference" not in json.dumps(row)


def evaluation(dice: float) -> dict:
    summary = {
        "dice": {"mean": dice, "ci": [0.2, 0.9]},
        "surface_dice": {"mean": 0.7},
        "hd95_mm": {"mean": 8, "coverage": 1},
        "reference_positive_cases": 1,
        "reference_empty_cases": 0,
        "reference_empty_prediction_nonempty_cases": 0,
    }
    return {
        "manifest_fingerprint": "manifest-fingerprint",
        "protocol": {"aggregation": "equal-weight patient means over reference-positive cases"},
        "coverage": {
            "eligible_cases": 1,
            "annotated_cases": 1,
            "valid_reference_cases": 1,
            "valid_prediction_cases": 1,
        },
        "cases": [
            {
                "case_id": "private-case-A",
                "patient_id": "private-patient-A",
                "reference_sha256": "reference-hash",
                "annotation_status": "labeled",
                "status": "ok",
            }
        ],
        "regions": {"mass": copy.deepcopy(summary), "pancreas": copy.deepcopy(summary)},
    }


@pytest.fixture
def campaign(tmp_path: Path) -> tuple[Path, Path]:
    state = tmp_path / "state"
    spec = {
        "schema_version": 1,
        "campaign_id": "test-campaign",
        "source_commit": "source",
        "splits": str(tmp_path / "splits.json"),
        "gpus": ["0", "1"],
        "runs": [],
    }
    write(Path(spec["splits"]), {"train": ["training-case"], "val": ["private-case-A"], "test": []})
    for index, name in enumerate(("a", "b")):
        workspace = tmp_path / name
        config = {
            "model": name,
            "backend": "torch",
            "workspace": str(workspace),
            "seed": 0,
            "epochs": 2,
            "steps_per_epoch": 100,
            "batch_size": 2,
            "initialization": "scratch",
            "mode": "3d",
            "patch_size": [64, 64, 64],
        }
        path = tmp_path / "configs" / f"{name}.json"
        write(path, config)
        write(
            workspace / "binding.json",
            {
                "config": config,
                "initialization": "scratch",
                "split_fingerprint": "split-fingerprint",
                "code": {"file": "same-source-hash"},
                "checkpoint_selection": "maximum validation mass Dice",
                "architecture": {"objective": "dense_ce_dice"},
            },
        )
        write(
            workspace / "scratch-origin.json",
            {
                "initialization": "scratch",
                "external_weight_loads": 0,
                "parameters": 1000,
            },
        )
        write(workspace / "training-result.json", {"completed": True, "steps": 200})
        write(
            workspace / "metrics" / "epoch-00002.json",
            {
                "epoch": 2,
                "step": 200,
                "loss": 0.7,
                "learning_rate": 0.00001,
                "validation": {
                    "mean_mass_dice": 0.5,
                    "mean_pancreas_dice": 0.8,
                    "space": "native_full_volume",
                    "cases": [{"case_id": "private-case-A"}],
                },
                "peak_allocated_bytes": 2**30,
            },
        )
        write(
            state / "runs" / f"{name}.json",
            {
                "status": "completed",
                "stage": "evaluate",
                "config": str(path),
                "workspace": str(workspace),
                "checkpoint": "checkpoint_best.pth",
                "selected_checkpoint_sha256": f"selected-{name}-checkpoint-hash",
            },
        )
        write(state / "evaluations" / name / "report.json", evaluation(0.4 + index * 0.2))
        spec["runs"].append(
            {
                "id": name,
                "config": str(path),
                "model": name,
                "backend": "torch",
                "comparison_group": "torch10k",
            }
        )
    write(tmp_path / "campaign.json", spec)
    return tmp_path / "campaign.json", state


def test_rank_requires_every_planned_run_to_complete(campaign: tuple[Path, Path]) -> None:
    spec, state = campaign
    snapshot = reporter.collect(spec, state, now=1000)
    assert [row["screening_rank"] for row in snapshot["runs"]] == [2, 1]
    run_state = reporter._read(state / "runs/b.json")
    run_state["status"] = "running"
    write(state / "runs/b.json", run_state)
    snapshot = reporter.collect(spec, state, now=1000)
    assert all(row["screening_rank"] is None for row in snapshot["runs"])
    assert "Not all planned runs have completed" in snapshot["groups"]["torch10k"]["reasons"]


@pytest.mark.parametrize(
    "change", ["budget", "reference", "protocol", "patient", "code", "seed", "failure"]
)
def test_incompatible_complete_runs_are_not_ranked(
    campaign: tuple[Path, Path], change: str
) -> None:
    spec, state = campaign
    workspace = spec.parent / "b"
    if change in {"budget", "code", "seed"}:
        path = workspace / "binding.json"
        record = reporter._read(path)
        if change == "budget":
            record["config"]["epochs"] = 3
            write(workspace / "training-result.json", {"completed": True, "steps": 300})
        elif change == "seed":
            record["config"]["seed"] = 1
        else:
            record["code"]["file"] = "different-source"
    else:
        path = state / "evaluations/b/report.json"
        record = reporter._read(path)
        if change == "reference":
            record["cases"][0]["reference_sha256"] = "changed-mask"
        elif change == "patient":
            record["cases"][0]["patient_id"] = "another-patient"
        elif change == "protocol":
            record["protocol"]["aggregation"] = "different-protocol"
        else:
            record["cases"][0]["status"] = "failed_prediction"
            record["coverage"]["valid_prediction_cases"] = 0
    write(path, record)
    snapshot = reporter.collect(spec, state, now=1000)
    assert not snapshot["groups"]["torch10k"]["ranked"]
    assert all(row["screening_rank"] is None for row in snapshot["runs"])


def test_partial_validation_and_invalid_numbers_fail_closed(campaign: tuple[Path, Path]) -> None:
    spec, state = campaign
    path = spec.parent / "a/metrics/epoch-00002.json"
    record = reporter._read(path)
    record["validation"]["cases"] = []
    write(path, record)
    snapshot = reporter.collect(spec, state)
    assert snapshot["runs"][0]["status"] == "invalid_report"
    record["validation"]["cases"] = [{"case_id": "private-case-A"}]
    record["validation"]["mean_mass_dice"] = float("nan")
    write(path, record)
    assert reporter.collect(spec, state)["runs"][0]["status"] == "invalid_report"


def test_generated_records_are_aggregate_only(campaign: tuple[Path, Path]) -> None:
    spec, state = campaign
    files = reporter.render(reporter.collect(spec, state, now=1000))
    combined = "\n".join(files.values())
    assert "private-case-A" not in combined
    assert "private-patient-A" not in combined
    assert str(spec.parent) not in combined
    assert "Final evaluation instead averages patient means" in combined
    assert "Loss magnitudes" in combined
    assert "139 unannotated" in combined
    assert set(files) == {
        "README.md",
        "comparison.md",
        "learning-curves.md",
        "optimization.md",
        "results.csv",
        "status.json",
        "models/a.md",
        "models/b.md",
        "records/a.json",
        "records/b.json",
        "training-cost.md",
        "inference.md",
        "epochs.csv",
        "validation-cases.csv",
        "inference-cases.csv",
        "stage-invocations.csv",
        "clinical-metrics.md",
    }
    assert ",200,200,200," in files["results.csv"]


def test_resume_resource_cost_sums_distinct_stage_records(tmp_path: Path) -> None:
    write(tmp_path / "stages/train-1/outcome.json", {"allocated_gpu_hours": 2})
    write(tmp_path / "stages/train-2/outcome.json", {"allocated_gpu_hours": 3})
    write(
        tmp_path / "active-stage.json", {"status": "running", "action": "train", "started_at": 100}
    )
    resources = reporter._resources(tmp_path, 3700)
    assert resources["finished_stage_gpu_hours"] == 5
    assert resources["active_stage_allocated_hours_estimate"] == 1


def test_unsafe_duplicate_run_ids_are_rejected(campaign: tuple[Path, Path]) -> None:
    path, state = campaign
    spec = reporter._read(path)
    spec["runs"][1]["id"] = spec["runs"][0]["id"]
    write(path, spec)
    with pytest.raises(ValueError, match="unique safe filenames"):
        reporter.collect(path, state)


def test_pipeline_evidence_discards_identifiers_and_rejects_non_numeric_payloads() -> None:
    original = {
        "data": [
            {
                "model": "unet_3d",
                "size_rank": "median",
                "npz_seconds": 0.1,
                "mmap_seconds": 0.001,
                "exact_samples_and_rng": True,
                "case_id": "private-patient",
                "path": "/data/private",
            }
        ],
        "prefetch": {
            "synchronous_seconds": 0.08,
            "prefetched_seconds": 0.04,
            "exact_weights": True,
            "exact_rng": True,
        },
        "inference": [
            {
                "model": "unet_3d",
                "batch_size": 8,
                "argmax_disagreement_voxels": 10,
                "native_voxels": 1000,
            }
        ],
        "source_summaries_sha256": ["a" * 64],
        "trace": {"private": "private-patient"},
    }
    clean = reporter._sanitize_pipeline(original)
    output = reporter._pipeline_markdown(clean)
    assert "private" not in json.dumps(clean)
    assert "2.0000" in output and "1.0000" in output
    assert "not describe all optimizations as bitwise invariant" in output
    original["data"][0]["npz_seconds"] = "/data/private"
    with pytest.raises(ValueError, match="finite nonnegative"):
        reporter._sanitize_pipeline(original)
    original["data"][0]["npz_seconds"] = float("nan")
    with pytest.raises(ValueError, match="finite nonnegative"):
        reporter._sanitize_pipeline(original)


def test_reports_retain_epoch_and_prediction_components_without_false_throughput(campaign):
    spec, state = campaign
    workspace = spec.parent / "a"
    metric_path = workspace / "metrics/epoch-00002.json"
    metric = reporter._read(metric_path)
    metric.update(epoch_training_seconds=10, epoch_validation_seconds=20)
    metric["validation"]["cases"][0].update(
        mass_dice=0.5,
        pancreas_dice=0.8,
        wall_seconds=20,
        component_seconds={
            "preprocess_seconds": 5,
            "inference_seconds": 3,
            "reconstruction_seconds": 12,
        },
    )
    write(metric_path, metric)
    prediction = {
        "partition": "val",
        "checkpoint_sha256": "a" * 64,
        "timing_scope": "Overlapped case/component times are not additive stage wall time",
        "cases": [
            {
                "case_id": "private-case-A",
                "status": "completed",
                "wall_seconds": 20,
                "component_seconds": {"inference_seconds": 3, "export_seconds": 2},
                "error": "/data/private-patient-A",
            }
        ],
        "performance": {
            "completed": True,
            "wall_seconds": 8,
            "scope": "model_ready_to_last_case_including_cache_export",
            "peak_allocated_bytes": 2**30,
            "cache": {"loads": 1, "source_verifications": 1},
        },
    }
    write(workspace / "predictions/val/prediction-status.json", prediction)
    snapshot = reporter.collect(spec, state)
    perf = snapshot["runs"][0]["performance"]
    assert perf["prediction"]["scans_per_second"] == 0.125
    assert perf["prediction"]["complete_cohort"] is True
    assert perf["prediction"]["pipeline_measurement_complete"] is True
    assert perf["prediction"]["case_latency_seconds"]["p50"] == 20
    assert perf["training_segments"][0]["totals"]["epoch_checkpoint_seconds"]["seconds"] is None
    files = reporter.render(snapshot)
    assert "private-case-A" not in "\n".join(files.values())
    assert "private-patient-A" not in "\n".join(files.values())
    assert "inference_seconds" in files["inference-cases.csv"]
    assert "10.0,20.0,," in files["epochs.csv"]
    prediction["performance"]["completed"] = False
    write(workspace / "predictions/val/prediction-status.json", prediction)
    assert (
        reporter.collect(spec, state)["runs"][0]["performance"]["prediction"]["scans_per_second"]
        is None
    )
    prediction["performance"].update(completed=True, scope="unknown")
    write(workspace / "predictions/val/prediction-status.json", prediction)
    unknown = reporter.collect(spec, state)["runs"][0]["performance"]["prediction"]
    assert unknown["pipeline_measurement_complete"] is False
    assert unknown["scans_per_second"] is None
    prediction.pop("performance")
    write(workspace / "predictions/val/prediction-status.json", prediction)
    snapshot = reporter.collect(spec, state)
    legacy = snapshot["runs"][0]["performance"]["prediction"]
    assert legacy["complete_cohort"] is True
    assert legacy["pipeline_measurement_complete"] is False
    assert legacy["scans_per_second"] is None
    summary = list(csv.DictReader(io.StringIO(reporter.render(snapshot)["results.csv"])))
    assert summary[0]["prediction_complete"] == "True"


@pytest.mark.parametrize(
    "corruption", ["duplicate", "outside", "negative", "nan", "wrong_partition"]
)
def test_prediction_timing_integrity_is_checked(campaign, corruption):
    spec, state = campaign
    prediction = {
        "partition": "val",
        "cases": [{"case_id": "private-case-A", "status": "completed", "wall_seconds": 1}],
    }
    if corruption == "duplicate":
        prediction["cases"] *= 2
    elif corruption == "outside":
        prediction["cases"][0]["case_id"] = "other-patient"
    elif corruption == "negative":
        prediction["cases"][0]["wall_seconds"] = -1
    elif corruption == "nan":
        prediction["cases"][0]["wall_seconds"] = float("nan")
    else:
        prediction["partition"] = "test"
    write(spec.parent / "a/predictions/val/prediction-status.json", prediction)
    assert reporter.collect(spec, state)["runs"][0]["status"] == "invalid_report"


def test_prediction_continuation_keeps_parent_training_after_best_checkpoint(campaign):
    import hashlib

    from segmentary.medical_reporting import _digest, metric_history

    spec, _state = campaign
    parent = spec.parent / "a"
    binding = reporter._read(parent / "binding.json")
    child = spec.parent / "continued"
    record = {
        "action": "predict",
        "resume_step": 100,
        "parent": {
            "workspace": str(parent),
            "binding_sha256": hashlib.sha256((parent / "binding.json").read_bytes()).hexdigest(),
            "binding_identity": _digest(binding),
            "artifact_sha256": {
                "training-result.json": hashlib.sha256(
                    (parent / "training-result.json").read_bytes()
                ).hexdigest()
            },
        },
    }
    write(child / "continuation.json", record)
    rows = metric_history(child, {"continuation_lineage": [record["parent"]]})
    assert [(scope, metric["step"]) for scope, metric in rows] == [("parent/current", 200)]
    record["action"] = "resume"
    write(child / "continuation.json", record)
    assert metric_history(child, {"continuation_lineage": [record["parent"]]}) == []


def test_readme_distinguishes_prediction_continuation_from_new_training(campaign):
    spec, state = campaign
    snapshot = reporter.collect(spec, state)
    original = reporter.render(snapshot)["README.md"]
    assert original.startswith("# Pancreas Task07: model comparison\n")
    assert "report-directory/" in original
    assert "scratch-screen-20260913/" not in original
    assert "Prediction continuation:" not in original
    for row in snapshot["runs"]:
        row.setdefault("performance", {}).setdefault("lineage", {})["action"] = "predict"
    continued = reporter.render(snapshot)["README.md"]
    assert "retains its parent training and selected scratch-origin checkpoint" in continued
    assert "adds no training steps or independent seeds" in continued
    snapshot["runs"][0]["performance"]["lineage"]["action"] = "resume"
    assert "Prediction continuation:" not in reporter.render(snapshot)["README.md"]


def test_readme_states_the_campaigns_initializations(campaign):
    spec, state = campaign
    snapshot = reporter.collect(spec, state)
    scratch = reporter.render(snapshot)["README.md"]
    assert "No pretrained weights are allowed" in scratch
    snapshot["runs"][0]["initialization"] = "warm_start"
    warm = reporter.render(snapshot)["README.md"]
    assert "No pretrained weights are allowed" not in warm
    assert "Initializations in this campaign: scratch, warm_start." in warm


def test_standardized_inference_requires_matching_provenance_and_measured_samples(tmp_path):
    from segmentary.medical_reporting import _digest, standardized_inference

    binding = {
        "config": {
            "model": "unet",
            "patch_size": [64, 64],
            "context_slices": 5,
            "precision": "bf16",
        },
        "code": {"file": "hash"},
        "runtime": {"python": "3.11"},
    }
    record = {
        "status": "completed",
        "input_scope": "synthetic_model_only",
        "model": "unet",
        "batch_size": 1,
        "patch_size": [64, 64],
        "context_slices": 5,
        "precision": "bf16",
        "warmup_iterations": 10,
        "measured_iterations": 3,
        "sample_latencies_ms": [1, 2, 3],
        "latency_ms": {"mean": 2, "p50": 2, "p95": 2.9, "min": 1, "max": 3},
        "patches_per_second": 500,
        "checkpoint_sha256": "a" * 64,
        **{f"{key}_fingerprint": _digest(binding[key]) for key in ("config", "code", "runtime")},
    }
    write(tmp_path / "standard-inference.json", record)
    assert standardized_inference(tmp_path, binding)["patches_per_second"] == 500
    for key in ("config", "code", "runtime"):
        broken = copy.deepcopy(record)
        broken[f"{key}_fingerprint"] = "b" * 64
        write(tmp_path / "standard-inference.json", broken)
        with pytest.raises(ValueError, match="fingerprint"):
            standardized_inference(tmp_path, binding)
    for samples in ([0, 2, 3], [1, 2], [float("nan"), 2, 3]):
        broken = copy.deepcopy(record)
        broken["sample_latencies_ms"] = samples
        write(tmp_path / "standard-inference.json", broken)
        with pytest.raises(ValueError):
            standardized_inference(tmp_path, binding)


def test_clinical_report_keeps_specificity_auc_unavailable_and_removes_raw_identifiers(tmp_path):
    from segmentary.medical_reporting import CLINICAL_METRICS, clinical_metrics

    artifact = {
        "schema_version": 1,
        "kind": "medical_detection_diagnostic",
        "partition": "val",
        "cohort_complete": True,
        "counts": {
            "eligible_cases": 1,
            "valid_cases": 1,
            "patient_groups": 1,
            "complete_patient_groups": 1,
            "reference_positive_groups": 1,
            "reference_negative_groups": 0,
        },
        "protocol": {"connectivity": 26, "iou_threshold": 0.1, "minimum_prediction_volume_mm3": 10},
        "provenance": {"prediction_checkpoint_sha256": "a" * 64, "path": "/private-patient"},
        "cases": [{"case_id": "private-case-A", "patient_id": "private-patient-A"}],
        "metrics": {
            name: {
                "value": 0.5,
                "status": "available",
                "numerator": 0.5,
                "denominator": 1,
                "reason_code": None,
            }
            for name in CLINICAL_METRICS
        },
    }
    path = tmp_path / "report.json"
    write(path, artifact)
    result = clinical_metrics(path, 1, "a" * 64)
    assert result["metrics"]["patient_sensitivity"]["value"] == 0.5
    assert result["metrics"]["specificity"]["value"] is None
    assert result["metrics"]["auc"]["value"] is None
    assert result["grouping_status"] == "unverified_case_groups"
    assert "private" not in json.dumps(result)
    with pytest.raises(ValueError, match="checkpoint"):
        clinical_metrics(path, 1, "b" * 64)
    artifact["cohort_complete"] = False
    write(path, artifact)
    assert all(
        metric["value"] is None
        for metric in clinical_metrics(path, 1, "a" * 64)["metrics"].values()
    )


def test_prediction_statistics_are_retained_with_case_ordinals(campaign):
    spec, state = campaign
    stats = {
        "mass_probability_max": 0.85,
        "native_voxels": 100,
        "predicted_mass_voxels": 12,
        "mass_score_definition": "maximum_native_class2_probability",
    }
    write(
        spec.parent / "a/predictions/val/prediction-status.json",
        {
            "partition": "val",
            "cases": [
                {
                    "case_id": "private-case-A",
                    "status": "completed",
                    "wall_seconds": 1,
                    "prediction_statistics": stats,
                }
            ],
        },
    )
    snapshot = reporter.collect(spec, state)
    sample = snapshot["runs"][0]["performance"]["prediction"]["cases"][0]
    assert sample["case_number"] == 1 and sample["mass_probability_max"] == 0.85
    files = reporter.render(snapshot)
    assert "mass_probability_max" in files["inference-cases.csv"]
    assert "private-case-A" not in files["inference-cases.csv"]


def test_final_primary_with_labelled_best_secondary_is_reported_and_rankable(
    campaign: tuple[Path, Path],
) -> None:
    spec, state = campaign
    for index, name in enumerate(("a", "b")):
        run_state = reporter._read(state / f"runs/{name}.json")
        run_state["checkpoint"] = "checkpoint_final.pth"
        run_state["secondary"] = {
            "checkpoint": "checkpoint_best.pth",
            "label": "secondary: selected on this validation fold (optimistic)",
            "checkpoint_sha256": f"best-{name}",
            "evaluation": str(state / "evaluations-checkpoint-best" / name),
        }
        write(state / f"runs/{name}.json", run_state)
        write(
            state / "evaluations-checkpoint-best" / name / "report.json",
            evaluation(0.9 - index * 0.1),
        )
    snapshot = reporter.collect(spec, state, now=1000)
    assert [row["screening_rank"] for row in snapshot["runs"]] == [2, 1]
    secondary = snapshot["runs"][0]["secondary_evaluation"]
    assert secondary["checkpoint"] == "checkpoint_best.pth"
    assert secondary["evaluation"]["mass"]["dice"] == pytest.approx(0.9)
    files = reporter.render(snapshot)
    assert str(spec.parent) not in "\n".join(files.values())
    rows = list(csv.DictReader(io.StringIO(files["results.csv"])))
    assert rows[0]["primary_checkpoint"] == "checkpoint_final.pth"
    assert float(rows[0]["secondary_mass_dice"]) == pytest.approx(0.9)
    assert "Primary scored checkpoint | checkpoint_final.pth" in files["models/a.md"]
    assert snapshot["runs"][0]["checkpoint_selection"].startswith(
        "none: terminal checkpoint_final.pth"
    )
    assert "Checkpoint selection | none: terminal checkpoint_final.pth" in files["models/a.md"]
    assert "Primary scored checkpoint SHA256" in files["models/a.md"]
    assert "Selected checkpoint SHA256" not in files["models/a.md"]
    run_state = reporter._read(state / "runs/b.json")
    run_state["checkpoint"] = "checkpoint_best.pth"
    write(state / "runs/b.json", run_state)
    snapshot = reporter.collect(spec, state, now=1000)
    assert (
        "Evaluation is not bound to one declared checkpoint policy"
        in (snapshot["groups"]["torch10k"]["reasons"])
    )


def test_cv_fold_runs_are_scored_against_their_own_fold(campaign: tuple[Path, Path]) -> None:
    spec, state = campaign
    cv = spec.parent / "cv.json"
    write(cv, {"folds": [{"val": ["other-case"]}, {"val": ["private-case-A"]}]})
    config_path = spec.parent / "configs" / "a.json"
    config = reporter._read(config_path)
    config.update(cv_splits=str(cv), cv_splits_sha256=reporter.sha256_file(cv), fold=1)
    write(config_path, config)
    snapshot = reporter.collect(spec, state, now=1000)
    assert snapshot["runs"][0]["status"] == "completed"
    assert snapshot["runs"][0]["expected_validation_cases"] == 1
    config["fold"] = 0
    write(config_path, config)
    assert reporter.collect(spec, state, now=1000)["runs"][0]["status"] == "invalid_report"
    config.update(fold=1, cv_splits_sha256="0" * 64)
    write(config_path, config)
    assert reporter.collect(spec, state, now=1000)["runs"][0]["status"] == "invalid_report"


def test_single_run_groups_are_not_ranked(campaign: tuple[Path, Path]) -> None:
    spec, state = campaign
    document = reporter._read(spec)
    document["runs"][1]["comparison_group"] = "solo"
    write(spec, document)
    snapshot = reporter.collect(spec, state, now=1000)
    assert all(row["screening_rank"] is None for row in snapshot["runs"])
    for group in snapshot["groups"].values():
        assert group["ranked"] is False
        assert "Only one run in this comparison group; there is nothing to rank" in group["reasons"]


def _warm_start(spec: Path, name: str, sha: str = "a" * 64, origin_sha: str | None = None):
    workspace = spec.parent / name
    binding = reporter._read(workspace / "binding.json")
    binding.update(
        initialization="warm_start",
        initial_checkpoint={"path": "/frozen/checkpoint_final.pth", "sha256": sha},
    )
    write(workspace / "binding.json", binding)
    (workspace / "scratch-origin.json").unlink(missing_ok=True)
    write(
        workspace / "initialization-origin.json",
        {
            "initialization": "warm_start",
            "external_weight_loads": 1,
            "init_checkpoint_sha256": origin_sha or sha,
            "parameters": 1000,
        },
    )


def test_warm_start_groups_rank_only_with_bound_matching_initial_checkpoints(campaign):
    spec, state = campaign
    for name in ("a", "b"):
        _warm_start(spec, name)
    snapshot = reporter.collect(spec, state, now=1000)
    assert snapshot["groups"]["torch10k"]["ranked"], snapshot["groups"]["torch10k"]["reasons"]
    assert all(row["origin_verified"] for row in snapshot["runs"])
    assert {row["initialization"] for row in snapshot["runs"]} == {"warm_start"}
    # The loaded checkpoint must be the bound one.
    _warm_start(spec, "b", origin_sha="b" * 64)
    snapshot = reporter.collect(spec, state, now=1000)
    assert not snapshot["groups"]["torch10k"]["ranked"]
    assert (
        "Complete training-origin evidence is unavailable"
        in (snapshot["groups"]["torch10k"]["reasons"])
    )
    # Arms of one group must start from the same checkpoint.
    _warm_start(spec, "b", sha="c" * 64)
    reasons = reporter.collect(spec, state, now=1000)["groups"]["torch10k"]["reasons"]
    assert any("differs" in reason for reason in reasons)


def test_scratch_and_warm_start_runs_are_never_ranked_together(campaign):
    spec, state = campaign
    _warm_start(spec, "b")
    snapshot = reporter.collect(spec, state, now=1000)
    group = snapshot["groups"]["torch10k"]
    assert not group["ranked"]
    assert any("never ranked together" in reason for reason in group["reasons"])
    assert all(row["screening_rank"] is None for row in snapshot["runs"])
