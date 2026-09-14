"""Checkpoint migrations must preserve science and all resume state."""

from __future__ import annotations

import copy
import dataclasses
import random
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

from segmentary.medical import continuation as module
from segmentary.medical import torch_backend as backend
from segmentary.medical.backend import _atomic_json, _digest, _json, _lock, _sha
from segmentary.medical.torch_config import TorchConfig


@pytest.fixture
def migration(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / ".stage.lock").touch()
    (source / "checkpoints").mkdir()
    old_code, new_code = tmp_path / "old-code", tmp_path / "new-code"
    for root in (old_code, new_code):
        root.mkdir()
        (root / "torch_backend.py").write_text("# implementation\n")
        (root / "torch_data.py").write_text(
            "def dice_ce(): return 0\ndef training_loss(): return 1\ndef sample_patch(): return 2\n"
            "def context_image(): return 3\n"
        )
        (root / "model_registry.py").write_text("# protected architecture\n")
    (new_code / "torch_backend.py").write_text("# reviewed logging optimization\n")
    (new_code / "continuation.py").write_text("# migration implementation\n")
    monkeypatch.setattr(module, "__file__", str(new_code / "continuation.py"))
    runtime = {
        "python": "unchanged",
        "executable": sys.executable,
        "packages": {"torch": "same"},
    }
    monkeypatch.setattr(backend, "_runtime", lambda _config: runtime)
    monkeypatch.setattr(module, "_executing_runtime", lambda: copy.deepcopy(runtime))
    monkeypatch.setattr(backend, "_code", lambda: module.code_hashes(new_code))
    original_config = TorchConfig(str(source), gpu="cpu", epochs=2, steps_per_epoch=2)
    config = dataclasses.replace(original_config, workspace=str(tmp_path / "target"))
    image, label = tmp_path / "ct.nii.gz", tmp_path / "label.nii.gz"
    image.write_bytes(b"audited CT content")
    label.write_bytes(b"audited label content")
    case = {
        "case_id": "p1",
        "image": str(image),
        "label": str(label),
        "image_sha256": _sha(image),
        "label_sha256": _sha(label),
    }
    manifest = {"fingerprint": "manifest", "cases": [case]}
    splits = {"fingerprint": "split", "train": ["p1"], "val": [], "test": ["heldout"]}
    manifest_path, splits_path = tmp_path / "manifest.json", tmp_path / "splits.json"
    _atomic_json(manifest_path, manifest)
    _atomic_json(splits_path, splits)
    monkeypatch.setattr(module, "_documents", lambda *_args: (manifest, splits))
    binding = {
        "schema_version": 1,
        "run_id": "original",
        "config": backend._config_record(original_config),
        "code": module.code_hashes(old_code),
        "runtime": runtime,
        "initialization": "scratch",
        "manifest_path": str(manifest_path),
        "splits_path": str(splits_path),
        "manifest_sha256": _sha(manifest_path),
        "splits_sha256": _sha(splits_path),
        "manifest_fingerprint": "manifest",
        "split_fingerprint": "split",
    }
    origin = {
        "identity": _digest(binding),
        "initialization": "scratch",
        "external_weight_loads": 0,
        "initial_state_sha256": "a" * 64,
        "parameters": 6,
    }
    # Real tensor/optimizer state, including initialized Adam moment buffers.
    model = torch.nn.Linear(2, 2)
    optimizer = torch.optim.AdamW(model.parameters())
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, 1)
    model(torch.ones((1, 2))).sum().backward()
    optimizer.step()
    scheduler.step()
    state = {
        "identity": _digest(binding),
        "origin": origin,
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "scaler": {},
        "python_rng": random.Random(5).getstate(),
        "numpy_rng": np.random.RandomState(5).get_state(),
        "sampling_rng": np.random.default_rng(5).bit_generator.state,
        "torch_rng": torch.Generator().manual_seed(5).get_state(),
        "cuda_rng": [],
        "epoch": 1,
        "step": 2,
        "best": 0.4,
    }
    checkpoint = source / "checkpoints/generation-parent.pth"
    torch.save(state, checkpoint)
    index = {
        "identity": _digest(binding),
        "initialization": "scratch",
        "files": {
            name: {"path": checkpoint.name, "sha256": _sha(checkpoint)}
            for name in ("checkpoint_latest.pth", "checkpoint_best.pth")
        },
    }
    for name, value in {
        "binding.json": binding,
        "resolved-config.json": binding["config"],
        "scratch-origin.json": origin,
        "checkpoint-index.json": index,
    }.items():
        _atomic_json(source / name, value)
    verification = tmp_path / "verification.json"
    _atomic_json(verification, {"training_state_equal": True, "validation_masks_equal": True})
    policy = {
        "schema_version": 1,
        "purpose": "performance-only",
        "source_code": binding["code"],
        "target_code": module.code_hashes(new_code),
        "allowed_changed_files": ["torch_backend.py", "continuation.py"],
        "review": "Logging only; objective/sampling unchanged; comparison evidence attached.",
        "verification_evidence": [
            {
                "path": str(verification),
                "sha256": _sha(verification),
                "description": "Numerical equivalence checks",
            }
        ],
    }
    return {
        "source": source,
        "config": config,
        "old_code": old_code,
        "new_code": new_code,
        "policy": policy,
        "state": state,
        "index": index,
        "checkpoint": checkpoint,
        "binding": binding,
        "runtime": runtime,
        "verification": verification,
        "image": image,
    }


def migrate(fixture, **kwargs):
    return module.create_continuation(
        fixture["source"],
        fixture["config"],
        source_code_root=fixture["old_code"],
        policy=fixture["policy"],
        action=kwargs.pop("action", "resume"),
        **kwargs,
    )


def test_new_binding_preserves_every_recorded_state_and_all_aliases(migration):
    before = {
        str(p.relative_to(migration["source"])): _sha(p)
        for p in migration["source"].rglob("*")
        if p.is_file()
    }
    report = migrate(migration)
    root = migration["config"].root
    binding = backend._binding(migration["config"])
    assert binding["continuation_lineage"][-1]["binding_identity"] == _digest(migration["binding"])
    assert report["preprocessing_required_before_execution"] is True
    assert not (root / "plan-binding.json").exists()
    assert not (root / "training-result.json").exists()
    index = _json(root / "checkpoint-index.json")
    assert set(index["files"]) == {"checkpoint_latest.pth", "checkpoint_best.pth"}
    assert index["files"]["checkpoint_latest.pth"] == index["files"]["checkpoint_best.pth"]
    state = torch.load(
        backend._checkpoint(migration["config"], "checkpoint_latest.pth"), weights_only=False
    )
    for key, value in migration["state"].items():
        if key not in {"identity", "origin"}:
            assert module.state_digest(state[key]) == module.state_digest(value), key
    assert state["identity"] == _digest(binding) != migration["state"]["identity"]
    assert (
        state["origin"]["initial_state_sha256"]
        == migration["state"]["origin"]["initial_state_sha256"]
    )
    assert _sha(root / "continuation-parent/generation-parent.pth") == _sha(migration["checkpoint"])
    after = {
        str(p.relative_to(migration["source"])): _sha(p)
        for p in migration["source"].rglob("*")
        if p.is_file()
    }
    assert before == after


def test_dry_run_does_not_create_target_or_side_files(migration):
    parent = migration["config"].root.parent
    before = set(parent.iterdir())
    report = migrate(migration, dry_run=True)
    assert report["dry_run"] and report["resume_epoch"] == 1 and report["resume_step"] == 2
    assert set(parent.iterdir()) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("learning_rate", 0.01),
        ("gpu", "1"),
        ("workers", 3),
        ("batch_size", 4),
        ("epochs", 3),
        ("steps_per_epoch", 4),
        ("validation_interval", 2),
        ("inference_batch_size", 4),
        ("backend_python", "/different/python"),
        ("seed", 25),
        ("overlap", 0.25),
        ("foreground_probability", 0.9),
    ],
)
def test_recipe_and_runtime_location_cannot_be_relabeled(migration, field, value):
    migration["config"] = dataclasses.replace(migration["config"], **{field: value})
    with pytest.raises(ValueError, match="Only workspace"):
        migrate(migration)
    assert not migration["config"].root.exists()


def test_changed_runtime_rejected(migration):
    migration["runtime"]["packages"]["torch"] = "different"
    with pytest.raises(ValueError, match="runtime"):
        migrate(migration)


@pytest.mark.parametrize("field", ["python", "executable", "packages"])
def test_wrong_executing_runtime_rejected_before_checkpoint_decode(migration, monkeypatch, field):
    runtime = copy.deepcopy(migration["runtime"])
    runtime[field] = {"torch": "different"} if field == "packages" else "different"
    monkeypatch.setattr(module, "_executing_runtime", lambda: runtime)
    monkeypatch.setattr(torch, "load", lambda *_a, **_kw: pytest.fail("decoded in wrong runtime"))
    with pytest.raises(ValueError, match="must execute in the recorded"):
        migrate(migration)
    assert not migration["config"].root.exists()


def test_executing_interpreter_symlink_with_identical_inventory_is_accepted(
    migration, monkeypatch, tmp_path
):
    link = tmp_path / "python-alias"
    link.symlink_to(Path(migration["runtime"]["executable"]).resolve())
    original = module._executing_runtime
    monkeypatch.setattr(
        module, "_executing_runtime", lambda: {**original(), "executable": str(link)}
    )
    assert migrate(migration, dry_run=True)["resume_epoch"] == 1


def test_changed_image_and_evidence_rejected(migration):
    migration["image"].write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash changed"):
        migrate(migration)


def test_corrupted_evidence_rejected(migration):
    migration["verification"].write_text("{}")
    with pytest.raises(ValueError, match="hash changed"):
        migrate(migration)


@pytest.mark.parametrize("function", ["dice_ce", "training_loss", "sample_patch", "context_image"])
def test_policy_cannot_allow_objective_or_sampling_changes(migration, function):
    path = migration["new_code"] / "torch_data.py"
    path.write_text(
        path.read_text().replace(f"def {function}():", f"def {function}(changed=True):")
    )
    migration["policy"]["target_code"] = module.code_hashes(migration["new_code"])
    migration["policy"]["allowed_changed_files"].append("torch_data.py")
    with pytest.raises(ValueError, match="objective or sampling"):
        migrate(migration)


def test_policy_cannot_allow_model_implementation_changes(migration):
    (migration["new_code"] / "model_registry.py").write_text("# changed architecture")
    migration["policy"]["target_code"] = module.code_hashes(migration["new_code"])
    migration["policy"]["allowed_changed_files"].append("model_registry.py")
    with pytest.raises(ValueError, match="Protected model"):
        migrate(migration)


def test_unreviewed_target_source_change_rejected(migration):
    (migration["new_code"] / "torch_backend.py").write_text("# post-review mutation")
    with pytest.raises(ValueError, match="Target source"):
        migrate(migration)


def test_parent_source_change_rejected(migration):
    (migration["old_code"] / "torch_backend.py").write_text("# source mutation")
    with pytest.raises(ValueError, match="Original source"):
        migrate(migration)


def test_active_training_lock_rejected(migration):
    with _lock(migration["source"] / ".stage.lock"):
        with pytest.raises(RuntimeError, match="active"):
            migrate(migration)


def test_stale_active_record_requires_explicit_reconciliation(migration):
    _atomic_json(migration["source"] / "active-stage.json", {"status": "running"})
    with pytest.raises(RuntimeError, match="unfinished active"):
        migrate(migration)


def test_corrupt_checkpoint_rejected_before_deserialization(migration, monkeypatch):
    migration["checkpoint"].write_bytes(b"not an authentic checkpoint")
    monkeypatch.setattr(
        torch, "load", lambda *_a, **_kw: pytest.fail("Decoded before hash verification")
    )
    with pytest.raises(ValueError, match="hash changed"):
        migrate(migration)


@pytest.mark.parametrize(
    "missing", ["optimizer", "scheduler", "scaler", "python_rng", "sampling_rng", "cuda_rng"]
)
def test_incomplete_resume_state_rejected(migration, missing):
    state = copy.deepcopy(migration["state"])
    del state[missing]
    torch.save(state, migration["checkpoint"])
    for item in migration["index"]["files"].values():
        item["sha256"] = _sha(migration["checkpoint"])
    _atomic_json(migration["source"] / "checkpoint-index.json", migration["index"])
    with pytest.raises(ValueError, match="complete model"):
        migrate(migration)


def complete_parent(fixture):
    state = copy.deepcopy(fixture["state"])
    state.update(epoch=2, step=4, best=0.4)
    path = fixture["source"] / "checkpoints/generation-final.pth"
    torch.save(state, path)
    for alias in ("checkpoint_latest.pth", "checkpoint_final.pth"):
        fixture["index"]["files"][alias] = {"path": path.name, "sha256": _sha(path)}
    _atomic_json(fixture["source"] / "checkpoint-index.json", fixture["index"])
    _atomic_json(
        fixture["source"] / "training-result.json",
        {
            "identity": state["identity"],
            "initialization": "scratch",
            "completed": True,
            "epochs": 2,
            "steps": 4,
            "best_mass_dice": 0.4,
            "purpose": "baseline",
        },
    )


def test_completed_run_carries_distinct_best_and_final_without_retraining(migration):
    complete_parent(migration)
    report = migrate(migration, action="predict")
    config = migration["config"]
    assert report["action"] == "predict" and report["resume_epoch"] == 1
    best = torch.load(backend._checkpoint(config, "checkpoint_best.pth"), weights_only=False)
    final = torch.load(backend._checkpoint(config, "checkpoint_final.pth"), weights_only=False)
    assert best["epoch"] == 1 and final["epoch"] == 2
    assert _json(config.root / "training-result.json")["completed"] is True
    assert _json(config.root / "training-result.json")["identity"] == _digest(
        backend._binding(config)
    )


@pytest.mark.parametrize(
    "fault", ["stale_best", "completion_best", "missing_latest", "newer_best", "final_alias"]
)
def test_inconsistent_selected_checkpoint_or_completion_rejected(migration, fault):
    complete_parent(migration)
    root, index = migration["source"], migration["index"]
    if fault == "stale_best":
        path = root / "checkpoints" / index["files"]["checkpoint_final.pth"]["path"]
        state = torch.load(path, weights_only=False)
        state["best"] = 0.7
        torch.save(state, path)
        for alias in ("checkpoint_latest.pth", "checkpoint_final.pth"):
            index["files"][alias]["sha256"] = _sha(path)
        result = _json(root / "training-result.json")
        result["best_mass_dice"] = 0.7
        _atomic_json(root / "training-result.json", result)
    elif fault == "completion_best":
        result = _json(root / "training-result.json")
        result["best_mass_dice"] = 0.7
        _atomic_json(root / "training-result.json", result)
    elif fault == "missing_latest":
        del index["files"]["checkpoint_latest.pth"]
    elif fault == "newer_best":
        index["files"]["checkpoint_latest.pth"] = index["files"]["checkpoint_best.pth"]
    else:
        original = root / "checkpoints" / index["files"]["checkpoint_final.pth"]["path"]
        duplicate = root / "checkpoints/generation-duplicate.pth"
        duplicate.write_bytes(original.read_bytes())
        index["files"]["checkpoint_latest.pth"] = {
            "path": duplicate.name,
            "sha256": _sha(duplicate),
        }
    _atomic_json(root / "checkpoint-index.json", index)
    with pytest.raises(ValueError, match=r"best score|latest|completed generation"):
        migrate(migration, action="predict")
    assert not migration["config"].root.exists()


def test_validated_latest_requires_best_alias(migration):
    del migration["index"]["files"]["checkpoint_best.pth"]
    _atomic_json(migration["source"] / "checkpoint-index.json", migration["index"])
    with pytest.raises(ValueError, match="requires its selected best"):
        migrate(migration)


def test_epoch_zero_latest_without_best_can_resume(migration):
    state = copy.deepcopy(migration["state"])
    state.update(epoch=0, step=0, best=-1.0)
    torch.save(state, migration["checkpoint"])
    del migration["index"]["files"]["checkpoint_best.pth"]
    migration["index"]["files"]["checkpoint_latest.pth"]["sha256"] = _sha(migration["checkpoint"])
    _atomic_json(migration["source"] / "checkpoint-index.json", migration["index"])
    report = migrate(migration)
    assert report["resume_epoch"] == report["resume_step"] == 0


def test_completed_training_cannot_resume(migration):
    complete_parent(migration)
    with pytest.raises(ValueError, match="already complete"):
        migrate(migration)


def test_incomplete_training_cannot_be_marked_complete_for_prediction(migration):
    with pytest.raises(ValueError, match="completed parent"):
        migrate(migration, action="predict")


def test_atomic_cleanup_on_write_failure_leaves_parent_intact(migration, monkeypatch):
    before = _sha(migration["checkpoint"])
    monkeypatch.setattr(
        torch, "save", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("disk full"))
    )
    with pytest.raises(OSError, match="disk full"):
        migrate(migration)
    assert not migration["config"].root.exists()
    assert not list(migration["config"].root.parent.glob(".target.continuation-*/"))
    assert _sha(migration["checkpoint"]) == before


@pytest.mark.parametrize(
    "filename", ["scratch-origin.json", "resolved-config.json", "training-result.json"]
)
def test_parent_metadata_change_during_capture_prevents_publication(
    migration, monkeypatch, filename
):
    original_save = torch.save

    def mutate_parent(*args, **kwargs):
        original_save(*args, **kwargs)
        _atomic_json(migration["source"] / filename, {"changed": True})

    monkeypatch.setattr(torch, "save", mutate_parent)
    with pytest.raises(ValueError, match=r"hash changed|metadata appeared"):
        migrate(migration)
    assert not migration["config"].root.exists()


def test_recorded_non_scratch_origin_rejected(migration):
    path = migration["source"] / "scratch-origin.json"
    record = _json(path)
    record["external_weight_loads"] = 1
    _atomic_json(path, record)
    with pytest.raises(ValueError, match="scratch origin"):
        migrate(migration)


def test_state_digest_distinguishes_shape_dtype_container_and_scalar_types():
    variants = [
        torch.tensor([1.0]),
        torch.tensor([[1.0]]),
        torch.tensor([1.0], dtype=torch.float64),
        np.array([1.0]),
        [1],
        (1,),
        1,
        1.0,
        True,
        "1",
        b"1",
        None,
    ]
    assert len({module.state_digest(value) for value in variants}) == len(variants)
    assert module.state_digest({"b": 2, "a": 1}) == module.state_digest({"a": 1, "b": 2})
