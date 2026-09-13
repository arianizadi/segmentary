"""Shared scratch pipeline checks using independently checkable CT geometry."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest
import torch
from torch import nn

nib = pytest.importorskip("nibabel")
pytest.importorskip("monai")

from segmentary.medical import torch_backend as backend  # noqa: E402
from segmentary.medical.data import audit_task07, make_splits  # noqa: E402
from segmentary.medical.model_registry import catalog, scratch_only  # noqa: E402
from segmentary.medical.torch_config import TorchConfig  # noqa: E402
from segmentary.medical.torch_data import (  # noqa: E402
    context_image,
    predict_case,
    preprocess_case,
    sample_patch,
    tiled_probabilities,
)


def _nifti(path: Path, values: np.ndarray, affine: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    volume = nib.Nifti1Image(values, affine)
    volume.header.set_xyzt_units("mm")
    volume.set_qform(affine, code=1)
    volume.set_sform(affine, code=1)
    nib.save(volume, path)


class Threshold(nn.Module):
    def forward(self, x):
        x = x[:, x.shape[1] // 2 : x.shape[1] // 2 + 1]
        return torch.cat([0.5 - x, torch.full_like(x, -100), x - 0.5], 1) * 100


@pytest.mark.parametrize("mode,context", [("2d", 1), ("2.5d", 5), ("3d", 1)])
def test_native_inference_preserves_flipped_anisotropic_axes_without_labels(
    tmp_path, mode, context
):
    affine = np.array([[0, -1.5, 0, 30], [0.75, 0, 0, -10], [0, 0, -3, 50], [0, 0, 0, 1]], float)
    values = np.zeros((9, 8, 7), np.float32)
    values[2:7, 3:6, 1:5] = 100
    path = tmp_path / "scan.nii.gz"
    _nifti(path, values, affine)
    config = TorchConfig(
        str(tmp_path / "run"),
        mode=mode,
        context_slices=context,
        patch_size=(4, 5, 6) if mode == "3d" else (5, 6),
        spacing_mm=(1.5, 0.75, 3),
        hu_window=(0, 100),
        gpu="cpu",
    )
    out = tmp_path / "prediction.nii.gz"
    prediction = predict_case(
        Threshold(),
        {"image": str(path), "label": "/must/not/be/read"},
        config,
        torch.device("cpu"),
        output=out,
    )
    np.testing.assert_array_equal(prediction, (values > 50).astype(np.uint8) * 2)
    saved = nib.load(out)
    np.testing.assert_array_equal(saved.affine, affine)
    assert saved.shape == values.shape


def test_context_and_foreground_crop_keep_same_patient_and_center_label(tmp_path):
    image = np.broadcast_to(np.arange(7, dtype=np.float32)[:, None, None], (7, 6, 5))
    np.testing.assert_array_equal(context_image(image, 0, 5)[:, 0, 0], [0, 0, 0, 1, 2])
    label = np.zeros_like(image, dtype=np.uint8)
    label[3, 2, 2] = 2
    config = TorchConfig(
        str(tmp_path),
        mode="2.5d",
        context_slices=5,
        patch_size=(4, 4),
        foreground_probability=1,
        augment=False,
    )
    patch, target = sample_patch({"image": image, "label": label}, config, np.random.default_rng(2))
    np.testing.assert_array_equal(patch[:, 1, 1], [1, 2, 3, 4, 5])
    assert target[2, 2] == 2


def test_patch_blending_matches_pointwise_model_for_odd_edges_and_padding(tmp_path):
    config = TorchConfig(str(tmp_path), mode="2d", patch_size=(7, 8), overlap=0.6, gpu="cpu")
    image = np.random.default_rng(4).random((1, 3, 19), dtype=np.float32)
    actual = tiled_probabilities(Threshold(), image, config, torch.device("cpu"))
    expected = Threshold()(torch.from_numpy(image[None])).softmax(1)[0].numpy()
    np.testing.assert_allclose(actual, expected, atol=1e-6)


@pytest.mark.parametrize(
    "change",
    [
        {"initialization": "imagenet"},
        {"context_slices": 3},
        {"epochs": True},
        {"overlap": 1},
        {"spacing_mm": [1, 0, 2]},
        {"mode": "2d"},
        {"gpu": "cpu", "precision": "bf16"},
    ],
)
def test_invalid_recipes_fail(change, tmp_path):
    with pytest.raises(ValueError):
        TorchConfig(str(tmp_path), **change)


def test_scratch_guard_blocks_cached_deserialization_and_restores_api(tmp_path):
    original = torch.load
    path = tmp_path / "weights.pth"
    torch.save({"weight": torch.ones(1)}, path)
    with scratch_only(), pytest.raises(RuntimeError, match="Scratch-only"):
        torch.load(path, weights_only=True)
    assert torch.load is original
    assert torch.load(path, weights_only=True)["weight"].item() == 1
    assert len(catalog()) == 27


def test_cli_json_roundtrip_preserves_scientific_notation_numbers(tmp_path):
    from segmentary.medical.cli import _config

    config = TorchConfig(str(tmp_path / "run"), weight_decay=1e-5, learning_rate=3e-4, gpu="cpu")
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(dataclasses.asdict(config)))
    assert "1e-05" in path.read_text()
    assert _config(path) == config


@pytest.fixture
def experiment(tmp_path):
    root = tmp_path / "dataset"
    entries = []
    affine = np.diag([1.0, 1.0, 2.0, 1.0])
    for i in range(4):
        image, label = f"imagesTr/p_{i}.nii.gz", f"labelsTr/p_{i}.nii.gz"
        values = np.random.default_rng(i).normal(50, 25, (9, 10, 8)).astype(np.float32)
        target = np.zeros(values.shape, np.uint8)
        target[2:7, 2:8, 2:6] = 1
        target[4:6, 4:6, 3:5] = 2
        _nifti(root / image, values, affine)
        _nifti(root / label, target, affine)
        entries.append({"image": image, "label": label})
    (root / "dataset.json").write_text(
        json.dumps(
            {
                "numTraining": 4,
                "numTest": 0,
                "training": entries,
                "test": [],
                "labels": {"0": "background", "1": "pancreas", "2": "mass"},
            }
        )
    )
    manifest_path, splits_path = tmp_path / "manifest.json", tmp_path / "splits.json"
    manifest = audit_task07(root, manifest_path)
    splits = make_splits(manifest_path, splits_path, train_fraction=0.5, val_fraction=0.25)
    config = TorchConfig(
        str(tmp_path / "run"),
        model="unet_3d",
        model_options={"channels": [2, 4, 8]},
        patch_size=(16, 16, 16),
        spacing_mm=(1, 1, 2),
        gpu="cpu",
        epochs=2,
        steps_per_epoch=1,
        batch_size=1,
        workers=1,
        deterministic=True,
        purpose="smoke",
    )
    return config, manifest, splits, manifest_path, splits_path


def test_real_subprocess_prepare_train_resume_native_predict(experiment):
    config, manifest, splits, manifest_path, splits_path = experiment
    backend.prepare_dataset(manifest_path, splits_path, config)
    for case in manifest["cases"]:
        if case["case_id"] in splits["test"]:
            Path(case["image"]).unlink()
            Path(case["label"]).unlink()
    assert backend.plan_and_preprocess(config)["status"] == "completed"
    assert {p.stem for p in (config.root / "cache").glob("*.npz")} == set(splits["train"])
    assert backend.train(config)["status"] == "completed"
    assert backend.train(config, resume=True)["status"] == "completed"
    assert backend.predict(config)["status"] == "completed"
    prediction = nib.load(config.root / "predictions" / "val" / f"{splits['val'][0]}.nii.gz")
    assert prediction.shape == (9, 10, 8)
    with pytest.raises(ValueError, match="Configuration or source"):
        backend.train(dataclasses.replace(config, learning_rate=0.003), resume=True)
    with pytest.raises(ValueError, match="Test prediction"):
        backend.predict(config, partition="test")
    checkpoint = backend._checkpoint(config, "checkpoint_latest.pth")
    checkpoint.write_bytes(b"untrusted weights")
    with pytest.raises(ValueError, match="Content hash"):
        backend.train(config, resume=True)


def test_resumed_epoch_matches_uninterrupted_optimizer_and_rng(experiment, monkeypatch):
    config, _, _, manifest_path, splits_path = experiment
    # In-process interruption injection exercises the exact worker's checkpoint,
    # AdamW moments, schedule, and all sampling/augmentation RNG state.
    backend.prepare_dataset(manifest_path, splits_path, config)
    backend.plan_and_preprocess(config)
    binding = backend._binding(config)
    original = backend._save_checkpoint

    def interrupt_after_epoch(cfg, state, names):
        original(cfg, state, names)
        if state["epoch"] == 1:
            raise KeyboardInterrupt("test interruption")

    monkeypatch.setattr(backend, "_save_checkpoint", interrupt_after_epoch)
    with pytest.raises(KeyboardInterrupt):
        backend._train_worker(config, {"resume": False}, binding)
    monkeypatch.setattr(backend, "_save_checkpoint", original)
    backend._train_worker(config, {"resume": True, "checkpoint": "checkpoint_latest.pth"}, binding)
    resumed = torch.load(backend._checkpoint(config, "checkpoint_final.pth"), weights_only=False)
    clean = dataclasses.replace(config, workspace=str(config.root.with_name("clean")))
    backend.prepare_dataset(manifest_path, splits_path, clean)
    backend.plan_and_preprocess(clean)
    backend._train_worker(clean, {"resume": False}, backend._binding(clean))
    uninterrupted = torch.load(
        backend._checkpoint(clean, "checkpoint_final.pth"), weights_only=False
    )
    assert resumed["step"] == uninterrupted["step"] == 2
    for name, tensor in resumed["model"].items():
        torch.testing.assert_close(tensor, uninterrupted["model"][name], rtol=0, atol=0)
    assert resumed["scheduler"] == uninterrupted["scheduler"]
    assert resumed["sampling_rng"] == uninterrupted["sampling_rng"]


def test_preprocessing_uses_nearest_neighbor_labels_and_fixed_ct_window(tmp_path):
    image, label = tmp_path / "ct.nii.gz", tmp_path / "mask.nii.gz"
    affine = np.diag([1, 2, 3, 1])
    values = np.zeros((3, 4, 5), np.int16)
    values[1] = 101
    mask = (values > 50).astype(np.uint8) * 2
    _nifti(image, values, affine)
    _nifti(label, mask, affine)
    config = TorchConfig(str(tmp_path / "run"), spacing_mm=(0.5, 1, 1.5), hu_window=(0, 101))
    data = preprocess_case({"image": str(image), "label": str(label)}, config, with_label=True)
    assert data["image"].shape == (9, 7, 5)
    assert set(np.unique(data["label"])) == {0, 2}
    assert set(np.unique(data["image"])) == {0, 0.5, 1}
