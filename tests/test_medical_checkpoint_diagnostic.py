"""Historical diagnostic readers preserve identity and exclude training writers."""

from __future__ import annotations

import fcntl
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "medical_checkpoint_diagnostic_tested", SCRIPTS / "medical_checkpoint_diagnostic.py"
)
assert SPEC is not None and SPEC.loader is not None
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def _fixture(tmp_path, monkeypatch):
    workspace = tmp_path / "run"
    workspace.mkdir()
    (workspace / ".stage.lock").touch()
    (workspace / "checkpoints").mkdir()
    config = {"backend_python": sys.executable, "workspace": str(workspace)}
    origin = {"initialization": "scratch", "external_weight_loads": 0}
    binding = {"config": config, "runtime": {}, "code": {}}
    for kind in ("manifest", "splits"):
        path = tmp_path / f"{kind}.json"
        path.write_text("{}")
        binding[f"{kind}_path"] = str(path)
        binding[f"{kind}_sha256"] = helper.sha256(path)
    state = {
        "identity": "verified-original-identity",
        "origin": origin,
        "model": {"weight": torch.ones(1)},
    }
    checkpoint = workspace / "checkpoints" / "generation-example.pth"
    torch.save(state, checkpoint)
    index = {
        "files": {
            "checkpoint_best.pth": {"path": checkpoint.name, "sha256": helper.sha256(checkpoint)}
        }
    }
    for name, value in [
        ("binding", binding),
        ("resolved-config", config),
        ("scratch-origin", origin),
        ("checkpoint-index", index),
        ("training-result", {"completed": True}),
    ]:
        (workspace / f"{name}.json").write_text(json.dumps(value))
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "campaign.json").write_text(
        json.dumps({"runs": [{"id": "control", "backend": "torch", "workspace": str(workspace)}]})
    )
    receipt = {
        "config": config,
        "binding": binding,
        "origin": origin,
        "checkpoint_path": str(checkpoint),
        "checkpoint_sha256": helper.sha256(checkpoint),
        "training_source_root": str(tmp_path / "historical-source"),
        "verification": {"binding_identity": state["identity"]},
    }
    monkeypatch.setattr(helper, "check_runtime", lambda _: None)
    monkeypatch.setattr(
        helper.subprocess, "run", lambda *_, **__: SimpleNamespace(stdout=json.dumps(receipt))
    )
    return campaign, workspace, receipt


def test_shared_readers_coexist_and_prevent_exclusive_training_writer(tmp_path):
    (tmp_path / ".stage.lock").touch()
    with helper.readonly_workspace(tmp_path), helper.readonly_workspace(tmp_path):
        with (tmp_path / ".stage.lock").open("rb") as writer:
            with pytest.raises(BlockingIOError):
                fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_reader_does_not_create_missing_stage_lock(tmp_path):
    with pytest.raises(ValueError, match="existing stage lock"):
        with helper.readonly_workspace(tmp_path):
            pytest.fail("Must not enter")
    assert list(tmp_path.iterdir()) == []


def test_running_writer_and_unfinished_stage_rejected(tmp_path):
    lock = tmp_path / ".stage.lock"
    lock.touch()
    with lock.open("rb") as writer:
        fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="active writer"):
            with helper.readonly_workspace(tmp_path):
                pytest.fail("Must not enter")
    (tmp_path / "active-stage.json").write_text('{"status":"running"}')
    with pytest.raises(RuntimeError, match="unfinished"):
        with helper.readonly_workspace(tmp_path):
            pytest.fail("Must not enter")


def test_verified_loader_has_exact_weights_and_changes_no_files(tmp_path, monkeypatch):
    campaign, workspace, _ = _fixture(tmp_path, monkeypatch)
    before = {path: helper.sha256(path) for path in tmp_path.rglob("*") if path.is_file()}
    with helper.verified_historical_checkpoint(campaign, "control") as receipt:
        assert torch.equal(receipt["state"]["model"]["weight"], torch.ones(1))
        del receipt["state"]  # Consumers may free optimizer/checkpoint RAM early.
    assert {path: helper.sha256(path) for path in tmp_path.rglob("*") if path.is_file()} == before
    assert not (workspace / "progress.json").exists()


def test_loader_refuses_bytes_changed_after_original_verification(tmp_path, monkeypatch):
    campaign, _, receipt = _fixture(tmp_path, monkeypatch)
    Path(receipt["checkpoint_path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="Checkpoint bytes changed"):
        with helper.verified_historical_checkpoint(campaign, "control"):
            pytest.fail("Must not deserialize modified bytes")


def test_loader_refuses_payload_identity_even_with_matching_bytes(tmp_path, monkeypatch):
    campaign, _, receipt = _fixture(tmp_path, monkeypatch)
    path = Path(receipt["checkpoint_path"])
    state = torch.load(io.BytesIO(path.read_bytes()), weights_only=False)
    state["identity"] = "wrong-identity"
    torch.save(state, path)
    receipt["checkpoint_sha256"] = helper.sha256(path)
    with pytest.raises(ValueError, match="payload identity"):
        with helper.verified_historical_checkpoint(campaign, "control"):
            pytest.fail("Must not accept foreign identity")


def test_immutable_original_artifacts_rechecked_on_exit(tmp_path, monkeypatch):
    campaign, workspace, _ = _fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="original input changed"):
        with helper.verified_historical_checkpoint(campaign, "control"):
            (workspace / "resolved-config.json").write_text("{}")


def test_original_guard_subprocess_failure_is_not_bypassed(tmp_path, monkeypatch):
    campaign, _, _ = _fixture(tmp_path, monkeypatch)

    def fail(*_, **__):
        raise subprocess.CalledProcessError(1, "original verifier")

    monkeypatch.setattr(helper.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        with helper.verified_historical_checkpoint(campaign, "control"):
            pytest.fail("No fallback to unbound checkpoint")


def test_rejects_cuda_initialized_before_original_binding_check(tmp_path, monkeypatch):
    campaign, _, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(torch.cuda, "is_initialized", lambda: True)
    with pytest.raises(RuntimeError, match="before initializing CUDA"):
        with helper.verified_historical_checkpoint(campaign, "control"):
            pytest.fail("Must verify first")
