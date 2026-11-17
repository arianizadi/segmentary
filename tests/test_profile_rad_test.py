"""CPU checks for profiling identity, timing mode and test-result preservation."""

import json

import pytest
from scripts import evaluate_rad_test as evaluate
from scripts import profile_rad_test as profile


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_requires_matching_completed_test_without_needing_test_scores(tmp_path):
    request = {"output_root": str(tmp_path / "results")}
    job = {"name": "a", "final_checkpoint_sha256": "checkpoint"}
    path = tmp_path / "results/a/result.json"
    identity = {
        "status": "completed",
        "test_evaluated": True,
        "split": "test",
        "name": "a",
        "request_sha256": "request",
        "checkpoint_sha256": "checkpoint",
        "images": 60,
    }
    write(path, identity)
    before = path.read_bytes()
    assert profile.require_finished_test(request, job, "request")[1] == identity
    assert path.read_bytes() == before
    identity["checkpoint_sha256"] = "different"
    write(path, identity)
    with pytest.raises(evaluate.TestEvaluationError, match="matching completed"):
        profile.require_finished_test(request, job, "request")


def test_output_is_separate_from_test_predictions(tmp_path):
    request = {"output_root": str(tmp_path / "test-evaluation")}
    assert profile.output_directory(request, "a") == tmp_path / "deployment-performance/a"


def test_profile_mode_resets_deterministic_evaluation_settings(monkeypatch):
    import torch

    from segmentary.utils import seed

    calls = []
    monkeypatch.setattr(
        seed, "seed_everything", lambda value, deterministic: calls.append((value, deterministic))
    )
    prior = (torch.are_deterministic_algorithms_enabled(), torch.backends.cudnn.deterministic)
    try:
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.deterministic = True
        profile.configure_deployment_seed(3)
        assert calls == [(3, False)]
        assert not torch.are_deterministic_algorithms_enabled()
        assert not torch.backends.cudnn.deterministic
    finally:
        torch.use_deterministic_algorithms(prior[0])
        torch.backends.cudnn.deterministic = prior[1]


def test_completed_profile_rejects_different_contract_and_modified_artifact(tmp_path):
    artifact = tmp_path / "performance.json"
    payload = {"contract": profile.deployment_contract(), "status": "complete"}
    write(artifact, payload)
    value = {
        "status": "completed",
        "task": profile.TASK,
        "request_sha256": "request",
        "checkpoint_sha256": "checkpoint",
        "performance": payload,
        "artifacts": {
            "performance.json": {"path": str(artifact), "sha256": evaluate.digest(artifact)}
        },
    }
    write(tmp_path / "result.json", value)
    assert profile.completed_profile(tmp_path, "request", "checkpoint") == value
    payload["contract"]["deterministic"] = True
    write(tmp_path / "result.json", value)
    with pytest.raises(evaluate.TestEvaluationError, match="timing contract"):
        profile.completed_profile(tmp_path, "request", "checkpoint")
    payload["contract"]["deterministic"] = False
    write(tmp_path / "result.json", value)
    artifact.write_text("modified")
    with pytest.raises(evaluate.TestEvaluationError, match="SHA-256"):
        profile.completed_profile(tmp_path, "request", "checkpoint")
