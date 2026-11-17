"""CPU-only safety checks for the separate, explicitly authorized test runner."""

from __future__ import annotations

import json

import pytest
from scripts import run_rad_test as runner

from segmentary import gpu_policy


def policy():
    entries = [{"index": i, "uuid": f"GPU-{i}", "pci_bus_id": f"{i:02}"} for i in range(10)]
    return gpu_policy.freeze([0, 1, 2, 3, 7, 8, 9], entries, "test-host")


def freeze_request(tmp_path, gpu=None):
    frozen = policy() if gpu is None else gpu
    campaign = tmp_path / "campaign.json"
    request_path = tmp_path / "request.json"
    request = {
        "schema_version": 1,
        "test_evaluation_authorized": True,
        "campaign_json": str(campaign),
        "output_root": str(tmp_path / "output"),
        "class_names": [str(i) for i in range(21)],
        "jobs": [{"name": "model--recipe"}],
    }
    request_path.write_text(json.dumps(request))
    campaign.write_text(
        json.dumps(
            {
                "gpu_policy": frozen,
                "gpu_policy_sha256": gpu_policy.policy_sha256(frozen),
                "request_sha256": runner.digest(request_path),
            }
        )
    )
    return request_path


def test_frozen_request_refuses_gpu_outside_explicit_user_allowlist(tmp_path):
    frozen = policy()
    forbidden = frozen["forbidden"].pop(0)
    frozen["allowed"].append(forbidden)
    with pytest.raises(ValueError, match="exceeds"):
        runner.validate_request(freeze_request(tmp_path, frozen))


def test_frozen_request_cannot_be_silently_changed(tmp_path):
    path = freeze_request(tmp_path)
    runner.validate_request(path)
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="SHA-256"):
        runner.validate_request(path)


def test_busy_compute_process_blocks_even_zero_memory_telemetry(monkeypatch):
    frozen = policy()
    monkeypatch.setattr(gpu_policy, "verify_inventory", lambda *_: None)
    monkeypatch.setattr(gpu_policy, "compute_apps", lambda: [(10, "GPU-7")])
    monkeypatch.setattr(
        runner.subprocess,
        "check_output",
        lambda *_a, **_k: "\n".join(f"{i}, GPU-{i}, 0, 0" for i in range(10)),
    )
    idle = runner.idle_snapshot(frozen)
    assert set(idle) == {0, 1, 2, 3, 7, 8, 9}
    assert idle[7] is False
    assert idle[0] is True


@pytest.mark.parametrize("telemetry", ["0, GPU-0, 0, 0", "0, GPU-0, N/A, 0", "invalid"])
def test_missing_or_malformed_telemetry_never_implies_idle(monkeypatch, telemetry):
    monkeypatch.setattr(gpu_policy, "verify_inventory", lambda *_: None)
    monkeypatch.setattr(gpu_policy, "compute_apps", lambda: [])
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *_a, **_k: telemetry)
    with pytest.raises(gpu_policy.GpuInspectionError):
        runner.idle_snapshot(policy())


def test_gpu_lock_excludes_competing_launcher_and_releases(tmp_path):
    path = tmp_path / "gpu-0.lock"
    with runner.exclusive_locks([path]) as acquired:
        assert acquired
        with runner.exclusive_locks([path]) as competing:
            assert competing is False
    with runner.exclusive_locks([path]) as acquired:
        assert acquired


def completed_result(tmp_path):
    job = {"name": "model", "final_checkpoint_sha256": "checkpoint"}
    directory = tmp_path / "model"
    directory.mkdir()
    artifacts = {}
    for name in ("metrics.json", "per-image.csv", "per-image-confusion.json.gz", "coverage.json"):
        path = directory / name
        if name == "coverage.json":
            path.write_text(
                json.dumps({str(i): {"positive_images": 2, "pixels": 20} for i in range(21)})
            )
        else:
            path.write_bytes(b"evidence")
        artifacts[name] = {"path": str(path), "sha256": runner.digest(path)}
    result = {
        "status": "completed",
        "request_sha256": "request",
        "checkpoint_sha256": "checkpoint",
        "split": "test",
        "test_evaluated": True,
        "images": 60,
        "artifacts": artifacts,
        "present_image": {
            "images": 60,
            "miou_present_images_classes": 21,
            "per_class": {str(i): {} for i in range(21)},
        },
    }
    (directory / "result.json").write_text(json.dumps(result))
    return job, directory, result


def test_resume_requires_exact_request_checkpoint_and_verified_evidence(tmp_path):
    job, directory, _ = completed_result(tmp_path)
    assert runner.result_complete(tmp_path, job, "request", [str(i) for i in range(21)])
    with pytest.raises(ValueError, match="different request"):
        runner.result_complete(tmp_path, job, "different", [])
    (directory / "metrics.json").write_text("tampered")
    with pytest.raises(ValueError, match="artifact changed"):
        runner.result_complete(tmp_path, job, "request", [])


def test_resume_rejects_completed_result_without_all_class_support(tmp_path):
    job, directory, result = completed_result(tmp_path)
    path = directory / "coverage.json"
    coverage = json.loads(path.read_text())
    coverage["0"]["positive_images"] = 0
    path.write_text(json.dumps(coverage))
    result["artifacts"]["coverage.json"]["sha256"] = runner.digest(path)
    (directory / "result.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="all-21-class"):
        runner.result_complete(tmp_path, job, "request", [str(i) for i in range(21)])
