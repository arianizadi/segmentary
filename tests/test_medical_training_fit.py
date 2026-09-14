"""Bounded train-only fit: native scoring, selection and exact CPU resume."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
import torch
from torch import nn

from segmentary.medical import model_registry, torch_backend
from segmentary.medical.data import audit_task07, make_splits
from segmentary.medical.torch_config import TorchConfig

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_medical_training_fit.py"
_SPEC = importlib.util.spec_from_file_location("training_fit_diagnostic_test", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
fit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fit)


def _volume(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = nib.Nifti1Image(values, np.diag([1.0, 1.0, 2.0, 1.0]))
    image.header.set_xyzt_units("mm")
    image.set_qform(image.affine, code=1)
    image.set_sform(image.affine, code=1)
    nib.save(image, path)


@pytest.fixture
def cohort(tmp_path):
    dataset = tmp_path / "dataset"
    entries = []
    for index in range(8):
        image = np.zeros((7 + index, 8, 6), dtype=np.float32)
        image[1:5, 2:6, 1:5] = 100
        image[3:5, 3:5, 2:4] = 200 + index
        labels = np.zeros_like(image, dtype=np.uint8)
        labels[1:5, 2:6, 1:5] = 1
        labels[3:5, 3:5, 2:4] = 2
        image_path = f"imagesTr/case_{index}.nii.gz"
        label_path = f"labelsTr/case_{index}.nii.gz"
        _volume(dataset / image_path, image)
        _volume(dataset / label_path, labels)
        entries.append({"image": image_path, "label": label_path})
    (dataset / "dataset.json").write_text(
        json.dumps(
            {
                "training": entries,
                "test": [],
                "numTraining": 8,
                "numTest": 0,
                "labels": {"0": "background", "1": "pancreas", "2": "mass"},
            }
        )
    )
    manifest_path, splits_path = tmp_path / "manifest.json", tmp_path / "splits.json"
    manifest = audit_task07(dataset, manifest_path)
    splits = make_splits(manifest_path, splits_path, train_fraction=0.5, val_fraction=0.25)
    # Any unintended held-out payload read now causes a real FileNotFoundError.
    for case in manifest["cases"]:
        if case["case_id"] in splits["val"] + splits["test"]:
            Path(case["image"]).unlink()
            Path(case["label"]).unlink()
    return manifest, splits, manifest_path


def test_selection_is_deterministic_training_only_metadata(cohort, monkeypatch):
    manifest, splits, _ = cohort
    monkeypatch.setattr(fit, "_sha", lambda *_: pytest.fail("Selection read a payload"))
    selected = fit.select_cases(manifest, splits, 4)
    assert {case["case_id"] for case in selected} == set(splits["train"])
    assert selected == fit.select_cases(manifest, splits, 4)
    assert [case["shape"][0] for case in selected] == sorted(case["shape"][0] for case in selected)
    with pytest.raises(ValueError, match="at least two"):
        fit.select_cases(manifest, splits, 1)
    with pytest.raises(ValueError, match="at least two"):
        fit.select_cases(manifest, splits, 5)


def test_diagnostic_config_changes_only_declared_fields(tmp_path):
    original = TorchConfig(
        str(tmp_path / "original"),
        model="dynunet",
        gpu="1",
        batch_size=8,
        patch_size=(96, 96, 96),
        precision="bf16",
    )
    updated = fit.fit_config(dataclasses.asdict(original), tmp_path / "fit", "7", 2000, 100)
    assert not updated.augment and updated.purpose == "overfit"
    assert updated.epochs * updated.steps_per_epoch == 2000
    for name in (
        "learning_rate",
        "weight_decay",
        "gradient_clip",
        "batch_size",
        "patch_size",
        "spacing_mm",
        "hu_window",
        "model",
        "foreground_probability",
        "overlap",
        "precision",
    ):
        assert getattr(updated, name) == getattr(original, name)
    with pytest.raises(ValueError, match="GPU 0"):
        fit.fit_config(dataclasses.asdict(original), tmp_path / "fit", "0", 2000, 100)
    with pytest.raises(ValueError, match="divisible"):
        fit.fit_config(dataclasses.asdict(original), tmp_path / "fit", "7", 999, 100)


def test_native_training_evaluation_exports_and_scores_actual_geometry(cohort, tmp_path):
    manifest, splits, manifest_path = cohort
    selected = fit.select_cases(manifest, splits, 2)
    config = TorchConfig(
        workspace=str(tmp_path / "config"),
        gpu="cpu",
        patch_size=(6, 8, 8),
        spacing_mm=(1, 1, 2),
        hu_window=(0, 200),
        workers=1,
    )

    class Threshold(nn.Module):
        def forward(self, value):
            centers = torch.tensor([0, 0.5, 1], device=value.device).reshape(1, 3, 1, 1, 1)
            return -100 * (value - centers).square()

    result = fit.native_evaluate(
        Threshold(),
        selected,
        config,
        manifest_path,
        tmp_path / "eval",
        torch.device("cpu"),
        {"fixed_training_subset": True},
    )
    assert result["mean_mass_dice"] == result["mean_pancreas_dice"] == 1
    assert result["scope"] == "in_sample_training_fit_only_not_generalization"
    for case in selected:
        predicted = nib.load(tmp_path / "eval" / "predictions" / f"{case['case_id']}.nii.gz")
        original = nib.load(case["label"])
        np.testing.assert_array_equal(predicted.affine, original.affine)
        np.testing.assert_array_equal(np.asarray(predicted.dataobj), np.asarray(original.dataobj))
    from PIL import Image

    reviews = list((tmp_path / "eval" / "orthogonal-review").glob("*.png"))
    assert len(reviews) == 2
    with Image.open(reviews[0]) as image:
        assert image.size == (1152, 1648)
        # First CT-only panel stays grayscale while masks tint neighboring panels.
        values = np.asarray(image)
        first = values[72:336, 0:384]
        np.testing.assert_array_equal(first[:, :, 0], first[:, :, 1])
        np.testing.assert_array_equal(first[:, :, 1], first[:, :, 2])


def test_memorization_reuses_real_objective_and_exact_resume(cohort, tmp_path, monkeypatch):
    manifest, splits, manifest_path = cohort
    selected = fit.select_cases(manifest, splits, 2)
    monkeypatch.setattr(model_registry, "build_model", lambda *_args, **_kwargs: nn.Conv3d(1, 3, 1))
    config = TorchConfig(
        workspace=str(tmp_path / "resumed"),
        model="dynunet",
        gpu="cpu",
        workers=1,
        patch_size=(6, 8, 8),
        spacing_mm=(1, 1, 2),
        hu_window=(0, 200),
        augment=False,
        epochs=4,
        steps_per_epoch=1,
        batch_size=2,
        cache_root=str(tmp_path / "cache"),
        prefetch_batches=True,
        purpose="overfit",
    )
    binding = {"test": "diagnostic exact CPU resume"}
    original_save = torch_backend._save_checkpoint

    def interrupted(cfg, state, names):
        original_save(cfg, state, names)
        if state["step"] == 2:
            raise KeyboardInterrupt("injected interruption after committed checkpoint")

    monkeypatch.setattr(torch_backend, "_save_checkpoint", interrupted)
    with pytest.raises(KeyboardInterrupt):
        fit.memorize(config, selected, manifest_path, binding)
    monkeypatch.setattr(torch_backend, "_save_checkpoint", original_save)
    result = fit.memorize(config, selected, manifest_path, binding, resume=True)
    clean = dataclasses.replace(config, workspace=str(tmp_path / "clean"))
    fit.memorize(clean, selected, manifest_path, binding)
    original = json.loads((config.root / "scratch-origin.json").read_text())
    resumed = fit._load_fit_checkpoint(config, fit._digest(binding), original)
    uninterrupted = fit._load_fit_checkpoint(clean, fit._digest(binding), original)
    for name, tensor in resumed["model"].items():
        torch.testing.assert_close(tensor, uninterrupted["model"][name], rtol=0, atol=0)
    for key, state in resumed["optimizer"]["state"].items():
        for name, value in state.items():
            torch.testing.assert_close(
                value, uninterrupted["optimizer"]["state"][key][name], rtol=0, atol=0
            )
    assert result["steps"] == 4 and result["success_threshold"] is None
    assert result["early_stopping"] is False
    assert original["external_weight_loads"] == 0
    assert [row["step"] for row in result["evaluations"]] == [0, 4]
    assert len(list((config.root / "checkpoints").glob("*.pth"))) <= 2
    final = nn.Conv3d(1, 3, 1)
    final.load_state_dict(resumed["model"])
    assert torch_backend._state_hash(final) != original["initial_state_sha256"]
    path = (
        config.root
        / "checkpoints"
        / json.loads((config.root / "checkpoint-index.json").read_text())["files"][
            "checkpoint_latest.pth"
        ]["path"]
    )
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="content changed"):
        fit._load_fit_checkpoint(config, fit._digest(binding), original)


def test_output_cannot_nest_inside_historical_scientific_artifacts(tmp_path):
    workspace, source = tmp_path / "run", tmp_path / "source"
    for output in (workspace, workspace / "nested", source / "new-diagnostic"):
        with pytest.raises(ValueError, match="separate"):
            fit.separate_output(output, workspace, source)
    fit.separate_output(tmp_path / "separate", workspace, source)


def test_completion_not_published_if_historical_immutability_guard_fails(
    cohort, tmp_path, monkeypatch
):
    import contextlib

    import medical_checkpoint_diagnostic

    _, _, manifest_path = cohort
    config = TorchConfig(str(tmp_path / "original"), gpu="cpu", model="dynunet")
    original_model = nn.Conv3d(1, 3, 1)
    receipt = {
        "config": dataclasses.asdict(config),
        "binding": {
            "manifest_path": str(manifest_path),
            "splits_path": str(tmp_path / "splits.json"),
        },
        "checkpoint_sha256": "a" * 64,
        "training_source_commit": "b" * 40,
        "training_source_root": str(tmp_path / "original-source"),
        "state": {"model": original_model.state_dict()},
    }

    @contextlib.contextmanager
    def guard(*_args):
        yield receipt
        raise ValueError("original artifact changed at exit")

    def evaluation(_model, _cases, _config, _manifest, output, _device, _provenance):
        output.mkdir(parents=True)
        summary = {"completed": True}
        (output / "summary.json").write_text(json.dumps(summary))
        return summary

    monkeypatch.setattr(medical_checkpoint_diagnostic, "verified_historical_checkpoint", guard)
    monkeypatch.setattr(model_registry, "build_model", lambda *_args, **_kwargs: nn.Conv3d(1, 3, 1))
    monkeypatch.setattr(fit, "native_evaluate", evaluation)
    monkeypatch.setattr(fit, "source_record", lambda: {"source": "same"})
    monkeypatch.setattr(fit, "memorize", lambda *_args, **_kwargs: {"completed": True})
    output = tmp_path / "diagnostic"
    with pytest.raises(ValueError, match="original artifact changed"):
        fit.main(["--campaign", str(tmp_path), "--output", str(output), "--gpu", "cpu"])
    assert not (output / "summary.json").exists()
