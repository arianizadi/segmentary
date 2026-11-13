"""Pre-launch historical ordering must never mutate a live queue or checkpoint."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from scripts import prioritize_rad_plan as priority_tool


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture
def prepared(tmp_path):
    models = [f"model_{index:02d}" for index in range(41)]
    protocols = [
        "rtis_only",
        "cityscapes_to_rtis",
        "railsem19_to_rtis",
        "cityscapes_to_railsem19_to_rtis",
    ]
    source_jobs = []
    plan_jobs = []
    for model_index, model in enumerate(models):
        for protocol_index, protocol in enumerate(protocols if model_index < 36 else protocols[:1]):
            source_jobs.append(
                {
                    "priority": len(source_jobs) + 1,
                    "model_priority": model_index + 1,
                    "model": model,
                    "protocol": protocol,
                    "old_pdf_validation_miou": 1 - model_index * 0.01 - protocol_index * 0.0001,
                }
            )
            plan_jobs.append(
                {
                    "name": f"{model}--{protocol}--seed-0",
                    "model": model,
                    "protocol": protocol,
                    "seed": 0,
                    "status": "prepared_not_launched",
                    "config_sha256": "b" * 64,
                    "source_checkpoint": {"checkpoint": "/unchanged/non-rad/source.ckpt"},
                }
            )
    priority = {
        "models": models,
        "jobs": source_jobs,
        "source_git_sha": "c" * 40,
        "source_csv_sha256": "a" * 64,
        "ranking_metric": "historical final-checkpoint validation mIoU",
        "rule": "descending best model score, then descending initialization score",
    }
    plan = {
        "launch_status": "not_launched",
        "jobs": list(reversed(plan_jobs)),
        "models": list(reversed(models)),
        "dataset": "new-rad-split",
        "metadata_to_preserve": {"primary_checkpoint": "final", "test": "unseen"},
    }
    root = tmp_path / "new-campaign"
    root.mkdir()
    plan_path, priority_path = root / "plan.json", tmp_path / "training-priority.json"
    write(plan_path, plan)
    write(priority_path, priority)
    return plan_path, priority_path, plan, priority


def test_exact149_order_provenance_and_nonqueue_fields_preserved(prepared):
    plan_path, source_path, old_plan, source = prepared
    source_bytes = source_path.read_bytes()
    outcome = priority_tool.prioritize(plan_path, source_path)
    plan = json.loads(plan_path.read_text())
    assert outcome["jobs"] == 149 and outcome["models"] == 41
    assert [(j["model"], j["protocol"]) for j in plan["jobs"]] == [
        (j["model"], j["protocol"]) for j in source["jobs"]
    ]
    assert [j["queue_priority"] for j in plan["jobs"]] == list(range(1, 150))
    assert plan["models"] == old_plan["models"]  # The helper never rewrites a manifest list.
    assert plan["metadata_to_preserve"] == old_plan["metadata_to_preserve"]
    before = {job["name"]: job for job in old_plan["jobs"]}
    for job in plan["jobs"]:
        core = {key: value for key, value in job.items() if not key.startswith("queue_priority")}
        assert core == before[job["name"]]
    assert (
        plan["queue_priority_provenance"]["source_priority_sha256"]
        == hashlib.sha256(source_bytes).hexdigest()
    )
    assert plan["queue_priority_provenance"]["source_csv_sha256"] == source["source_csv_sha256"]
    assert (
        plan["jobs"][0]["queue_priority_provenance"]["old_pdf_validation_miou"]
        == source["jobs"][0]["old_pdf_validation_miou"]
    )
    assert source_path.read_bytes() == source_bytes
    assert not (plan_path.parent / "campaign.json").exists()
    assert not (plan_path.parent / "state").exists()
    # Repeating the same pre-initialization freeze is byte-identical.
    frozen = plan_path.read_bytes()
    priority_tool.prioritize(plan_path, source_path)
    assert plan_path.read_bytes() == frozen


@pytest.mark.parametrize("marker", ["campaign.json", "state", "broken-state-symlink"])
def test_refuses_initialized_or_state_tree_without_changing_plan(prepared, marker):
    plan_path, source_path, _, _ = prepared
    if marker == "campaign.json":
        (plan_path.parent / marker).write_text("{}")
    elif marker == "state":
        (plan_path.parent / marker).mkdir()
    else:
        (plan_path.parent / "state").symlink_to("not-existing")
    before = plan_path.read_bytes()
    with pytest.raises(priority_tool.PriorityError, match="initialized/live"):
        priority_tool.prioritize(plan_path, source_path)
    assert plan_path.read_bytes() == before


@pytest.mark.parametrize(
    "mutation,pattern",
    [
        ("duplicate_plan", "Duplicate planned"),
        ("duplicate_priority", "Duplicate priority"),
        ("missing_plan", "exactly 149"),
        ("missing_priority", "exactly 149"),
        ("unknown_plan", "exact coverage differs"),
        ("unknown_protocol", "unknown protocol"),
        ("queued_job", "prepared_not_launched"),
        ("launched_plan", "not_launched"),
        ("bad_source_hash", "source_csv_sha256"),
        ("nonfinite_score", "finite"),
        ("unsorted_scores", "Initializations must descend"),
    ],
)
def test_refuses_ambiguous_or_incomplete_priority(prepared, mutation, pattern):
    plan_path, source_path, plan, priority = prepared
    if mutation == "duplicate_plan":
        plan["jobs"][1] = copy.deepcopy(plan["jobs"][0])
    elif mutation == "duplicate_priority":
        priority["jobs"][1]["protocol"] = priority["jobs"][0]["protocol"]
    elif mutation == "missing_plan":
        plan["jobs"].pop()
    elif mutation == "missing_priority":
        priority["jobs"].pop()
    elif mutation == "unknown_plan":
        plan["jobs"][0]["model"] = "unknown_model"
        plan["jobs"][0]["name"] = "unknown_model--rtis_only--seed-0"
    elif mutation == "unknown_protocol":
        plan["jobs"][0]["protocol"] = "old_rad_checkpoint"
    elif mutation == "queued_job":
        plan["jobs"][0]["status"] = "queued"
    elif mutation == "launched_plan":
        plan["launch_status"] = "running"
    elif mutation == "bad_source_hash":
        priority["source_csv_sha256"] = "not-a-hash"
    elif mutation == "nonfinite_score":
        priority["jobs"][0]["old_pdf_validation_miou"] = float("nan")
    elif mutation == "unsorted_scores":
        priority["jobs"][1]["old_pdf_validation_miou"] = 0.1
    write(plan_path, plan)
    write(source_path, priority)
    original = plan_path.read_bytes()
    with pytest.raises(priority_tool.PriorityError, match=pattern):
        priority_tool.prioritize(plan_path, source_path)
    assert plan_path.read_bytes() == original


def test_atomic_replace_failure_keeps_original_and_cleans_temporary_file(prepared, monkeypatch):
    plan_path, source_path, _, _ = prepared
    original = plan_path.read_bytes()

    def fail_replace(*_):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(priority_tool.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        priority_tool.prioritize(plan_path, source_path)
    assert plan_path.read_bytes() == original
    assert not list(plan_path.parent.glob(".plan-priority-*.json"))
