"""Real CT scratch training survives a bound continuation without state drift."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest
import torch

from segmentary.medical import continuation as module
from segmentary.medical import torch_backend as backend
from segmentary.medical.backend import _atomic_json, _digest, _sha
from test_medical_torch_backend import experiment as medical_experiment  # noqa: F401


def preprocess_in_process(config, request_path):
    binding = backend._binding(config)
    _atomic_json(
        request_path,
        {
            "config": backend._config_record(config),
            "action": "preprocess",
            "payload": {},
            "identity": _digest(binding),
        },
    )
    backend._worker(request_path)


@pytest.mark.parametrize("prefetch", [False, True])
def test_migrated_scratch_checkpoint_matches_uninterrupted_training(
    medical_experiment,  # noqa: F811
    monkeypatch,
    tmp_path,
    prefetch,
):
    config, _, _, manifest_path, splits_path = medical_experiment
    config = dataclasses.replace(config, prefetch_batches=prefetch)
    backend.prepare_dataset(manifest_path, splits_path, config)
    preprocess_in_process(config, tmp_path / "old-preprocess.json")
    (config.root / ".stage.lock").touch()
    binding = backend._binding(config)
    original_save = backend._save_checkpoint

    def stop_after_epoch(cfg, state, names):
        original_save(cfg, state, names)
        if state["epoch"] == 1:
            raise KeyboardInterrupt("saved epoch boundary")

    monkeypatch.setattr(backend, "_save_checkpoint", stop_after_epoch)
    with pytest.raises(KeyboardInterrupt):
        backend._train_worker(config, {"resume": False}, binding)
    monkeypatch.setattr(backend, "_save_checkpoint", original_save)
    source_root, target_root = tmp_path / "old-code", tmp_path / "new-code"
    shutil.copytree(
        Path(backend.__file__).parent, source_root, ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(source_root, target_root)
    # Distinct exact source identity, verified harmless source edit. Core model,
    # training and inference implementation remains the real imported backend.
    target_backend = target_root / "torch_backend.py"
    target_backend.write_text(target_backend.read_text() + "\n# Reviewed logging-only migration.\n")
    monkeypatch.setattr(module, "__file__", str(target_root / "continuation.py"))
    monkeypatch.setattr(backend, "_code", lambda: module.code_hashes(target_root))
    evidence = tmp_path / "equivalence-review.json"
    _atomic_json(evidence, {"review": "Only a source comment changed; AST behavior unchanged"})
    policy = {
        "schema_version": 1,
        "purpose": "performance-only",
        "source_code": module.code_hashes(source_root),
        "target_code": module.code_hashes(target_root),
        "allowed_changed_files": ["torch_backend.py"],
        "review": "Comment-only source change; full checkpoint continuation tested.",
        "verification_evidence": [
            {"path": str(evidence), "sha256": _sha(evidence), "description": "Exact change review"}
        ],
    }
    migrated = dataclasses.replace(config, workspace=str(tmp_path / "migrated"))
    report = module.create_continuation(
        config.root, migrated, source_code_root=source_root, policy=policy, action="resume"
    )
    assert report["resume_step"] == 1
    preprocess_in_process(migrated, tmp_path / "migrated-preprocess.json")
    backend._train_worker(
        migrated,
        {"resume": True, "checkpoint": "checkpoint_latest.pth"},
        backend._binding(migrated),
    )
    clean = dataclasses.replace(config, workspace=str(tmp_path / "uninterrupted"))
    backend.prepare_dataset(manifest_path, splits_path, clean)
    preprocess_in_process(clean, tmp_path / "clean-preprocess.json")
    backend._train_worker(clean, {"resume": False}, backend._binding(clean))
    resumed = torch.load(backend._checkpoint(migrated, "checkpoint_final.pth"), weights_only=False)
    uninterrupted = torch.load(
        backend._checkpoint(clean, "checkpoint_final.pth"), weights_only=False
    )
    assert resumed["step"] == uninterrupted["step"] == 2
    assert (
        resumed["origin"]["initial_state_sha256"] == uninterrupted["origin"]["initial_state_sha256"]
    )
    for field in resumed:
        if field not in {"identity", "origin"}:
            assert module.state_digest(resumed[field]) == module.state_digest(
                uninterrupted[field]
            ), field
