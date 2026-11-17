"""CPU-only checks for isolated deployment profiling and strict resume evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import run_rad_test_profiles as runner


def fixture_result(tmp_path):
    job = {"name": "model", "final_checkpoint_sha256": "ckpt", "config_sha256": "config"}
    directory = tmp_path / "model"
    directory.mkdir()
    performance = {
        "source": {"checkpoint_sha256": "ckpt", "config_sha256": "config"},
        "contract": {
            "deterministic": False,
            "batch_size": 1,
            "input_shape_nchw": [1, 3, 1024, 1024],
            "measured_iterations": 100,
            "warmup_iterations": 20,
            "precision": "bf16_autocast",
        },
        "measurements": {"latency": {"raw_ms": [20.0] * 100, "mean_ms": 20.0, "fps": 50.0}},
    }
    result = {
        "status": "completed",
        "task": "rad-final-deployment-profile",
        "request_sha256": "request",
        "checkpoint_sha256": "ckpt",
        "performance": performance,
    }
    store(directory, result)
    return job, directory, result


def store(directory, result):
    path = directory / "performance.json"
    path.write_text(json.dumps(result["performance"]))
    result["artifacts"] = {"performance.json": {"path": str(path), "sha256": runner.digest(path)}}
    (directory / "result.json").write_text(json.dumps(result))


def test_deployment_profile_resumes_only_matching_contract(tmp_path):
    job, _, _ = fixture_result(tmp_path)
    assert runner.result_complete(tmp_path, job, "request", [])
    with pytest.raises(ValueError, match="identity"):
        runner.result_complete(tmp_path, job, "other", [])


@pytest.mark.parametrize("change", ["deterministic", "fps", "checkpoint", "samples"])
def test_old_deterministic_or_invalid_profiles_cannot_resume(tmp_path, change):
    job, directory, result = fixture_result(tmp_path)
    perf = result["performance"]
    if change == "deterministic":
        perf["contract"]["deterministic"] = True
    elif change == "fps":
        perf["measurements"]["latency"]["fps"] = 500
    elif change == "checkpoint":
        perf["source"]["checkpoint_sha256"] = "changed"
    elif change == "samples":
        perf["measurements"]["latency"]["raw_ms"].pop()
    store(directory, result)
    with pytest.raises(ValueError):
        runner.result_complete(tmp_path, job, "request", [])


def test_does_not_start_profiling_until_every_frozen_test_job_completed(monkeypatch):
    calls = []

    def complete(output, job, *_, rehearsal=False):
        assert rehearsal is False
        calls.append((output, job["name"]))
        return job["name"] == "a"

    monkeypatch.setattr(runner, "test_result_complete", complete)
    request = {
        "output_root": "/test-results",
        "class_names": [],
        "jobs": [{"name": "a"}, {"name": "b"}],
    }
    with pytest.raises(ValueError, match="All test jobs must complete"):
        runner.require_completed_tests(request, "hash")
    assert calls == [(Path("/test-results"), "a"), (Path("/test-results"), "b")]
