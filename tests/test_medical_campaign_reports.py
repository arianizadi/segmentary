"""Reporting must not turn incomplete or incompatible experiments into winners."""

from __future__ import annotations

import copy
import importlib.util
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
