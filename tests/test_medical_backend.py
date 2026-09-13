"""CPU contract tests for the optional medical subprocess backend."""

from __future__ import annotations

import dataclasses
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from segmentary.medical import backend as b


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    cases = []
    for name in ("train_a", "val_b", "test_c", "unknown_d"):
        image = source / f"{name}.nii.gz"
        label = source / f"{name}_label.nii.gz"
        image.write_bytes((name + " image").encode())
        label.write_bytes((name + " label").encode())
        cases.append(
            {
                "case_id": name,
                "patient_id": name,
                "source": "fixture",
                "image": str(image),
                "label": str(label) if name != "unknown_d" else None,
                "image_sha256": b._sha(image),
                "label_sha256": b._sha(label),
                "annotation_status": "unlabeled" if name == "unknown_d" else "labeled",
            }
        )
    manifest = {
        "schema_version": 1,
        "ontology": {"background": 0, "pancreas": 1, "mass": 2},
        "fingerprint": "manifest-fingerprint",
        "audit": {"passed": True},
        "cases": cases,
    }
    splits = {
        "schema_version": 1,
        "fingerprint": "split-fingerprint",
        "manifest_fingerprint": manifest["fingerprint"],
        "train": ["train_a"],
        "val": ["val_b"],
        "test": ["test_c"],
        "seed": 0,
    }
    manifest_path, splits_path = tmp_path / "manifest.json", tmp_path / "splits.json"
    b._atomic_json(manifest_path, manifest)
    b._atomic_json(splits_path, splits)
    monkeypatch.setattr(b, "_documents", lambda m, s: (b._json(Path(m)), b._json(Path(s))))
    monkeypatch.setattr(
        b, "_runtime", lambda config: {"python": "test", "packages": {"nnunetv2": b.NNUNET_VERSION}}
    )
    config = b.NNUNetConfig(str(tmp_path / "workspace"), deterministic=True)
    b.prepare_dataset(manifest_path, splits_path, config)
    return config, manifest, splits, manifest_path, splits_path


def fake_plan(config):
    b._atomic_json(
        config.preprocessed / f"{config.plans}.json",
        {"configurations": {config.configuration: {"data_identifier": "test_data"}}},
    )
    raw = config.root / "nnUNet_raw" / config.dataset
    (config.preprocessed / "dataset.json").write_bytes((raw / "dataset.json").read_bytes())
    (config.preprocessed / "test_data").mkdir()
    (config.preprocessed / "test_data" / "train_a.b2nd").write_bytes(b"prepared data")
    files = {
        str(p.relative_to(config.preprocessed)): b._sha(p)
        for p in config.preprocessed.rglob("*")
        if p.is_file()
    }
    b._atomic_json(
        config.root / "plan-binding.json",
        {
            "binding_digest": b._digest(b._binding(config)),
            "runtime": b._runtime(config),
            "files": files,
        },
    )


def fake_checkpoint(config, name="checkpoint_best.pth", epoch=1):
    config.fold_folder.mkdir(parents=True, exist_ok=True)
    path = config.fold_folder / name
    path.write_bytes(b"trusted experiment checkpoint")
    (config.fold_folder / f"{name}.rng.pt").write_bytes(b"rng state")
    identity = b._digest(
        {"binding": b._binding(config, verify_development=False), "runtime": b._runtime(config)}
    )
    item = {
        "identity": identity,
        "sha256": b._sha(path),
        "rng_sha256": b._sha(config.fold_folder / f"{name}.rng.pt"),
        "epoch": epoch,
        "saved_at": 1,
    }
    index_path = config.root / "checkpoint-index.json"
    index = b._json(index_path) if index_path.exists() else {}
    index[name] = item
    b._atomic_json(index_path, index)
    for target, source in (
        ("plans.json", f"{config.plans}.json"),
        ("dataset.json", "dataset.json"),
    ):
        (config.model_folder / target).write_bytes((config.preprocessed / source).read_bytes())
    return item


def test_preparation_excludes_holdout_and_unlabeled(prepared):
    config, manifest, _, _, _ = prepared
    raw = config.root / "nnUNet_raw" / config.dataset
    assert {p.name for p in (raw / "imagesTr").iterdir()} == {
        "train_a_0000.nii.gz",
        "val_b_0000.nii.gz",
    }
    assert {p.name for p in (raw / "labelsTr").iterdir()} == {"train_a.nii.gz", "val_b.nii.gz"}
    assert b._json(raw / "dataset.json")["numTraining"] == 2
    assert json.loads((config.preprocessed / "splits_final.json").read_text()) == [
        {"train": ["train_a"], "val": ["val_b"]}
    ]
    for c in manifest["cases"]:
        assert Path(c["image"]).read_bytes() == (c["case_id"] + " image").encode()


def test_holdout_payloads_never_read_during_preparation(prepared, tmp_path):
    config, manifest, _, manifest_path, splits_path = prepared
    for c in manifest["cases"][2:]:
        Path(c["image"]).unlink()
        if c["label"]:
            Path(c["label"]).unlink()
    fresh = dataclasses.replace(config, workspace=str(tmp_path / "new"))
    assert b.prepare_dataset(manifest_path, splits_path, fresh)["test_cases_excluded"] == 1


def test_dry_run_is_non_mutating(prepared, tmp_path):
    config, _, _, manifest_path, splits_path = prepared
    fresh = dataclasses.replace(config, workspace=str(tmp_path / "dry-run"))
    assert b.prepare_dataset(manifest_path, splits_path, fresh, dry_run=True)["dry_run"]
    assert not fresh.root.exists()
    assert b.plan_and_preprocess(config, dry_run=True)["planner"] == "nnUNetPlannerResEncL"
    assert not (config.root / "stages").exists()


def test_preparation_rejects_reuse_and_partial_labels(prepared, tmp_path):
    config, manifest, _, manifest_path, splits_path = prepared
    with pytest.raises(FileExistsError):
        b.prepare_dataset(manifest_path, splits_path, config)
    manifest["cases"][0]["annotation_status"] = "organ_only"
    b._atomic_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="fully labeled"):
        b.prepare_dataset(
            manifest_path,
            splits_path,
            dataclasses.replace(config, workspace=str(tmp_path / "organ-only")),
        )


@pytest.mark.parametrize("change", ["source", "split", "raw_extra", "ontology", "config", "code"])
def test_prepared_identity_tampering_fails(prepared, monkeypatch, change):
    config, manifest, splits, _, splits_path = prepared
    raw = config.root / "nnUNet_raw" / config.dataset
    if change == "source":
        Path(manifest["cases"][0]["image"]).write_bytes(b"changed")
    elif change == "split":
        splits["train"], splits["test"] = splits["test"], splits["train"]
        b._atomic_json(splits_path, splits)
    elif change == "raw_extra":
        (raw / "imagesTr" / "test_c_0000.nii.gz").symlink_to(manifest["cases"][2]["image"])
    elif change == "ontology":
        metadata = b._json(raw / "dataset.json")
        metadata["labels"]["mass"] = 9
        b._atomic_json(raw / "dataset.json", metadata)
    elif change == "config":
        config = dataclasses.replace(config, seed=42)
    else:
        monkeypatch.setattr(b, "_code_identity", lambda: {"backend.py": "modified"})
    with pytest.raises(ValueError):
        b.plan_and_preprocess(config, dry_run=True)


def test_cache_tampering_and_unknown_files_block_training(prepared):
    config = prepared[0]
    fake_plan(config)
    assert b.train(config, dry_run=True)["dry_run"]
    (config.preprocessed / "test_data" / "train_a.b2nd").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash changed"):
        b.train(config, dry_run=True)


def test_resume_never_restarts_silently_and_rejects_corruption(prepared):
    config = prepared[0]
    fake_plan(config)
    with pytest.raises(ValueError, match="cannot start a fresh"):
        b.train(config, resume=True, dry_run=True)
    item = fake_checkpoint(config)
    result = b.train(config, resume=True, dry_run=True)
    assert result["checkpoint_sha256"] == item["sha256"]
    with pytest.raises(FileExistsError):
        b.train(config, dry_run=True)
    (config.fold_folder / "checkpoint_best.pth").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash changed"):
        b.train(config, resume=True, dry_run=True)


def test_resume_rejects_foreign_checkpoint_binding(prepared):
    config = prepared[0]
    fake_plan(config)
    fake_checkpoint(config)
    index = b._json(config.root / "checkpoint-index.json")
    index["checkpoint_best.pth"]["identity"] = "another-experiment"
    b._atomic_json(config.root / "checkpoint-index.json", index)
    with pytest.raises(ValueError, match="different data"):
        b.train(config, resume=True, dry_run=True)


def test_prediction_is_image_only_and_test_requires_explicit_invocation(prepared):
    config, manifest, *_ = prepared
    fake_plan(config)
    fake_checkpoint(config)
    for c in manifest["cases"]:
        if c["label"]:
            Path(c["label"]).unlink()
    assert b.predict(config, dry_run=True)["cases"] == 1
    assert b.predict(config, partition="unlabeled", dry_run=True)["cases"] == 1
    assert b.predict(config, partition="train", dry_run=True)["cases"] == 1
    with pytest.raises(ValueError, match="explicitly"):
        b.predict(config, partition="test", dry_run=True)
    result = b.predict(config, partition="test", final_test=True, dry_run=True)
    assert result["cases"] == 1 and result["final_test"]


class FakeProcess:
    pid = 876543

    def __init__(self, result):
        self.result = result

    def wait(self, timeout=None):
        return self.result

    def poll(self):
        return self.result


@pytest.mark.parametrize(
    ("returncode", "status"), [(0, "completed"), (2, "failed"), (-signal.SIGTERM, "cancelled")]
)
def test_subprocess_lifecycle_and_safe_argv(prepared, monkeypatch, returncode, status):
    config = prepared[0]
    calls = []

    def launch(argv, **kwargs):
        calls.append((argv, kwargs))
        kwargs["stdout"].write(b"fake child evidence\n")
        return FakeProcess(returncode)

    monkeypatch.setattr(b.subprocess, "Popen", launch)
    if returncode:
        with pytest.raises(RuntimeError, match=status):
            b._run(config, "train", {}, gpu=True)
    else:
        assert b._run(config, "train", {}, gpu=True)["status"] == status
    state = b._json(config.root / "active-stage.json")
    assert state["status"] == status
    assert Path(state["log"]).read_text() == "fake child evidence\n"
    argv, kwargs = calls[0]
    assert isinstance(argv, list) and "shell" not in kwargs
    assert argv[1:4] == ["-m", "segmentary.medical.backend", "_worker"]
    assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "0"
    assert kwargs["env"]["nnUNet_n_proc_DA"] == "0"
    assert len(kwargs["pass_fds"]) == 2
    assert state["allocated_gpu_hours"] >= 0


def test_launch_exception_is_durably_recorded(prepared, monkeypatch):
    config = prepared[0]

    def fail(*args, **kwargs):
        raise OSError("execution denied")

    monkeypatch.setattr(b.subprocess, "Popen", fail)
    with pytest.raises(OSError):
        b._run(config, "plan", {})
    state = b._json(config.root / "active-stage.json")
    assert state["status"] == "failed" and "execution denied" in state["error"]


def test_gpu_lock_is_shared_between_workspaces_and_normalizes_device(tmp_path, monkeypatch):
    monkeypatch.setenv("SEGMENTARY_MEDICAL_LOCK_DIR", str(tmp_path / "locks"))
    a = b.NNUNetConfig(str(tmp_path / "a"), gpu="00")
    c = b.NNUNetConfig(str(tmp_path / "b"), gpu=0)
    assert a.gpu == c.gpu == "0" and b._gpu_lock(a) == b._gpu_lock(c)
    with b._lock(b._gpu_lock(a)):
        with pytest.raises(RuntimeError, match="already in use"):
            with b._lock(b._gpu_lock(c)):
                pytest.fail("A second run acquired the same GPU")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dataset_id": True},
        {"dataset_id": 707.0},
        {"seed": False},
        {"workers": 1.0},
        {"fold": True},
        {"deterministic": "false"},
        {"use_mirroring": 1},
        {"save_probabilities": "yes"},
        {"gpu": True},
        {"tile_step_size": True},
        {"num_epochs": 1},
        {"purpose": "smoke", "num_epochs": False},
    ],
)
def test_config_rejects_ambiguous_types_and_undeclared_recipe_changes(tmp_path, kwargs):
    with pytest.raises(ValueError):
        b.NNUNetConfig(str(tmp_path), **kwargs)


def test_native_geometry_validation_catches_orientation_and_classes(tmp_path):
    nib = pytest.importorskip("nibabel")
    image, prediction = tmp_path / "image.nii.gz", tmp_path / "prediction.nii.gz"
    affine = np.diag([0.7, 0.7, 2.5, 1.0])
    nib.save(nib.Nifti1Image(np.zeros((3, 4, 5), dtype=np.float32), affine), image)
    nib.save(nib.Nifti1Image(np.ones((3, 4, 5), dtype=np.uint8), affine), prediction)
    assert b.validate_prediction_geometry(image, prediction)["shape"] == [3, 4, 5]
    wrong = affine.copy()
    wrong[2, 3] = 7
    nib.save(nib.Nifti1Image(np.ones((3, 4, 5), dtype=np.uint8), wrong), prediction)
    with pytest.raises(ValueError, match="native CT geometry"):
        b.validate_prediction_geometry(image, prediction)
    nib.save(nib.Nifti1Image(np.full((3, 4, 5), 3, dtype=np.uint8), affine), prediction)
    with pytest.raises(ValueError, match="invalid class"):
        b.validate_prediction_geometry(image, prediction)


def test_environment_does_not_modify_process_environment(prepared):
    config = prepared[0]
    before = os.environ.copy()
    env = b._environment(config)
    assert env["nnUNet_raw"] == str(config.root / "nnUNet_raw")
    assert env["nnUNet_compile"] == "false"
    assert dict(os.environ) == before


def test_zero_augmentation_workers_are_exclusive_to_deterministic_training(tmp_path):
    config = b.NNUNetConfig(str(tmp_path), workers=3, deterministic=True)
    for action in (None, "plan", "predict"):
        assert b._environment(config, action=action)["nnUNet_n_proc_DA"] == "3"
    assert b._environment(config, action="train")["nnUNet_n_proc_DA"] == "0"
    ordinary = dataclasses.replace(config, deterministic=False)
    assert b._environment(ordinary, action="train")["nnUNet_n_proc_DA"] == "3"


def test_default_recipe_uses_normal_nnunet_gpu_execution(tmp_path):
    config = b.NNUNetConfig(str(tmp_path), workers=2)
    assert config.deterministic is False
    assert b._environment(config, action="train")["nnUNet_n_proc_DA"] == "2"
    strict = dataclasses.replace(config, deterministic=True)
    assert strict.deterministic is True
    assert b._environment(strict, action="train")["nnUNet_n_proc_DA"] == "0"


def test_planning_subprocess_receives_positive_thread_count(prepared, monkeypatch):
    config = prepared[0]
    seen = []

    def launch(argv, **kwargs):
        seen.append(kwargs["env"]["nnUNet_n_proc_DA"])
        return FakeProcess(0)

    monkeypatch.setattr(b.subprocess, "Popen", launch)
    b._run(config, "plan", {})
    assert seen == [str(config.workers)]


def test_external_backend_runtime_is_probed_independently(tmp_path, monkeypatch):
    config = b.NNUNetConfig(str(tmp_path), backend_python="/separate env/bin/python")
    calls = []
    expected = {
        "python": "worker-python",
        "executable": config.backend_python,
        "packages": {"nnunetv2": b.NNUNET_VERSION, "timm": "independent-version"},
    }

    def probe(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(expected), stderr="")

    monkeypatch.setattr(b.subprocess, "run", probe)
    assert b._runtime(config) == expected
    assert calls[0][0][0] == "/separate env/bin/python"
    assert calls[0][1]["env"]["PYTHONNOUSERSITE"] == "1"
    assert calls[0][1]["env"]["PYTHONPATH"].endswith("/src")
    expected["packages"]["nnunetv2"] = "0.0.0"
    with pytest.raises(RuntimeError, match="separate nnU-Net environment"):
        b._runtime(config)


def test_inherited_gpu_restriction_is_respected(tmp_path, monkeypatch):
    config = b.NNUNetConfig(str(tmp_path), gpu="0")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2")
    with pytest.raises(ValueError, match="outside inherited"):
        b._environment(config)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-example")
    with pytest.raises(ValueError, match="unsupported UUID"):
        b._environment(config)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    assert b._environment(config)["CUDA_VISIBLE_DEVICES"] == "0"


def test_parent_state_write_failure_stops_live_child(prepared, monkeypatch):
    config = prepared[0]
    signals = []
    process = FakeProcess(None)
    process.wait = lambda timeout=None: -signal.SIGTERM
    monkeypatch.setattr(b.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(b.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    original_write = b._atomic_json

    def disk_failure(path, value):
        if path.name == "active-stage.json" and value.get("status") == "running":
            raise OSError("disk full")
        return original_write(path, value)

    monkeypatch.setattr(b, "_atomic_json", disk_failure)
    with pytest.raises(OSError, match="disk full"):
        b._run(config, "train", {}, gpu=True)
    assert signals == [(process.pid, signal.SIGTERM)]
    assert b._json(config.root / "active-stage.json")["status"] == "failed"


def test_official_nibabel_output_spatial_metadata_is_restored_without_hiding_misalignment(tmp_path):
    nib = pytest.importorskip("nibabel")
    image, prediction = tmp_path / "ct.nii.gz", tmp_path / "mask.nii.gz"
    affine = np.diag([0.7, 0.7, 2.5, 1.0])
    source = nib.Nifti1Image(np.zeros((3, 4, 5), dtype=np.float32), affine)
    source.header.set_xyzt_units("mm")
    source.set_qform(affine, code=1)
    source.set_sform(affine, code=1)
    nib.save(source, image)
    labels = np.ones((3, 4, 5), dtype=np.uint8)
    # This is the actual nnU-Net 2.8.1 NibabelIO write_seg construction.
    nib.save(nib.Nifti1Image(labels, affine), prediction)
    assert nib.load(prediction).header.get_xyzt_units()[0] == "unknown"
    result = b._finalize_native_prediction(image, prediction)
    output = nib.load(prediction)
    assert output.header.get_xyzt_units()[0] == "mm"
    assert int(output.header["qform_code"]) == int(output.header["sform_code"]) == 1
    assert np.array_equal(np.asanyarray(output.dataobj), labels)
    assert result["backend_output_sha256"] != result["sha256"]
    wrong = affine.copy()
    wrong[0, 3] = 5
    nib.save(nib.Nifti1Image(labels, wrong), prediction)
    bad_hash = b._sha(prediction)
    with pytest.raises(ValueError, match="native CT geometry"):
        b._finalize_native_prediction(image, prediction)
    assert b._sha(prediction) == bad_hash
