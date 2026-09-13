"""Independent regression review of checkpoint and physical CT contracts."""

from __future__ import annotations

import json

import nibabel as nib
import numpy as np
import pytest
import torch
from torch import nn

from segmentary.medical import model_registry, torch_backend
from segmentary.medical.torch_config import TorchConfig
from segmentary.medical.torch_data import predict_case


def test_failed_checkpoint_index_publication_preserves_previous_resumable_generation(
    tmp_path, monkeypatch
):
    config = TorchConfig(workspace=str(tmp_path), gpu="cpu")
    binding = {"run_id": "review-fixture"}
    monkeypatch.setattr(torch_backend, "_binding", lambda *args, **kwargs: binding)
    state = {
        "identity": torch_backend._digest(binding),
        "epoch": 1,
        "model": {"weight": torch.tensor([1.0])},
    }
    torch_backend._save_checkpoint(config, state, ["checkpoint_latest.pth", "checkpoint_best.pth"])
    old_index = json.loads((tmp_path / "checkpoint-index.json").read_text())
    writer = torch_backend._atomic_json

    def fail_index(path, value):
        if path.name == "checkpoint-index.json":
            raise OSError("Injected disk/index publication failure")
        return writer(path, value)

    monkeypatch.setattr(torch_backend, "_atomic_json", fail_index)
    with pytest.raises(OSError, match="Injected"):
        torch_backend._save_checkpoint(
            config,
            {**state, "epoch": 2, "model": {"weight": torch.tensor([2.0])}},
            ["checkpoint_latest.pth", "checkpoint_best.pth"],
        )
    assert json.loads((tmp_path / "checkpoint-index.json").read_text()) == old_index
    # Both aliases must remain resolvable to the last committed generation.
    for name in ("checkpoint_latest.pth", "checkpoint_best.pth"):
        checkpoint = torch_backend._checkpoint(config, name)
        loaded = torch.load(checkpoint, weights_only=True)
        assert loaded["epoch"] == 1
        torch.testing.assert_close(loaded["model"]["weight"], torch.tensor([1.0]))


class _IntensityClassifier(nn.Module):
    def forward(self, x):
        centers = torch.tensor([0.0, 0.5, 1.0], device=x.device)[None, :, None, None, None]
        return -100 * (x[:, :1] - centers).square()


def test_native_prediction_keeps_axis_permutations_flips_and_anisotropic_geometry(tmp_path):
    # Native x runs opposite RAS z; native y runs RAS x; native z runs RAS y.
    affine = np.array([[0, 1.25, 0, -15.0], [0, 0, 1.5, 31.5], [-2.5, 0, 0, 55], [0, 0, 0, 1.0]])
    labels = np.zeros((9, 8, 7), dtype=np.uint8)
    labels[3:6] = 1
    labels[6:] = 2
    path = tmp_path / "native.nii.gz"
    volume = nib.Nifti1Image(labels.astype(np.float32) * 100, affine)
    volume.header.set_xyzt_units("mm")
    volume.set_qform(affine, code=1)
    volume.set_sform(affine, code=1)
    nib.save(volume, path)
    config = TorchConfig(
        workspace=str(tmp_path / "run"),
        gpu="cpu",
        patch_size=(4, 5, 6),
        spacing_mm=(1.25, 1.5, 2.5),
        hu_window=(0, 200),
    )
    output = tmp_path / "prediction.nii.gz"
    model = _IntensityClassifier()
    model.train()
    result = predict_case(
        model,
        {"image": str(path), "label": "this-label-must-never-be-opened"},
        config,
        torch.device("cpu"),
        output=output,
    )
    np.testing.assert_array_equal(result, labels)
    saved = nib.load(output)
    np.testing.assert_allclose(saved.affine, nib.load(path).affine, atol=0, rtol=0)
    assert saved.header.get_xyzt_units()[0] == "mm"
    assert model.training


def test_same_run_resume_restores_optimizer_scheduler_and_all_sampling_rng(tmp_path, monkeypatch):
    previous_threads = torch.get_num_threads()
    previous_deterministic = torch.are_deterministic_algorithms_enabled()
    previous_cudnn_deterministic = torch.backends.cudnn.deterministic
    previous_cudnn_benchmark = torch.backends.cudnn.benchmark
    binding = {
        "manifest_path": "unused-manifest",
        "splits_path": "unused-splits",
        "run_id": "review-run",
    }
    manifest = {"cases": [{"case_id": "train"}, {"case_id": "val"}]}
    splits = {"train": ["train"], "val": ["val"], "test": []}
    monkeypatch.setattr(torch_backend, "_documents", lambda *args: (manifest, splits))
    monkeypatch.setattr(torch_backend, "_binding", lambda *args, **kwargs: binding)
    monkeypatch.setattr(
        torch_backend,
        "_validation",
        lambda model, *args: {
            "mean_mass_dice": float(model[0].weight.detach().mean()),
            "cases": [],
            "space": "native_full_volume",
        },
    )
    monkeypatch.setattr(
        model_registry,
        "build_model",
        lambda *args, **kwargs: nn.Sequential(
            nn.Conv3d(1, 4, 1), nn.Dropout3d(0.25), nn.Conv3d(4, 3, 1)
        ),
    )
    configs = [
        TorchConfig(
            workspace=str(tmp_path / name),
            gpu="cpu",
            patch_size=(4, 4, 4),
            workers=1,
            epochs=2,
            steps_per_epoch=3,
            batch_size=2,
            deterministic=True,
            seed=231,
        )
        for name in ("continuous", "resumed")
    ]
    random_source = np.random.default_rng(928)
    image = random_source.random((7, 8, 9), dtype=np.float32)
    label = random_source.integers(0, 3, image.shape, dtype=np.uint8)
    for config in configs:
        directory = config.root / "cache"
        directory.mkdir(parents=True)
        np.savez_compressed(directory / "train.npz", image=image, label=label)
    try:
        torch_backend._train_worker(configs[0], {"resume": False}, binding)
        save = torch_backend._save_checkpoint

        def interrupted_after_complete_epoch(config, state, names):
            save(config, state, names)
            if state["epoch"] == 1:
                raise RuntimeError("Injected completed-epoch interruption")

        monkeypatch.setattr(torch_backend, "_save_checkpoint", interrupted_after_complete_epoch)
        with pytest.raises(RuntimeError, match="Injected"):
            torch_backend._train_worker(configs[1], {"resume": False}, binding)
        monkeypatch.setattr(torch_backend, "_save_checkpoint", save)
        torch_backend._train_worker(
            configs[1], {"resume": True, "checkpoint": "checkpoint_latest.pth"}, binding
        )
        states = [
            torch.load(
                torch_backend._checkpoint(config, "checkpoint_final.pth"), weights_only=False
            )
            for config in configs
        ]
        assert states[0]["epoch"] == states[1]["epoch"] == 2
        assert states[0]["step"] == states[1]["step"] == 6
        for name, tensor in states[0]["model"].items():
            torch.testing.assert_close(tensor, states[1]["model"][name], atol=0, rtol=0)
        assert states[0]["scheduler"] == states[1]["scheduler"]
        assert states[0]["sampling_rng"] == states[1]["sampling_rng"]
        torch.testing.assert_close(states[0]["torch_rng"], states[1]["torch_rng"], atol=0, rtol=0)
        for parameter, optimizer_state in states[0]["optimizer"]["state"].items():
            for key, value in optimizer_state.items():
                torch.testing.assert_close(
                    value, states[1]["optimizer"]["state"][parameter][key], atol=0, rtol=0
                )
    finally:
        torch.set_num_threads(previous_threads)
        torch.use_deterministic_algorithms(previous_deterministic)
        torch.backends.cudnn.deterministic = previous_cudnn_deterministic
        torch.backends.cudnn.benchmark = previous_cudnn_benchmark


def test_preprocessing_cache_contains_only_train_and_never_opens_heldout_payloads(
    tmp_path, monkeypatch
):
    from segmentary.medical import torch_data

    config = TorchConfig(workspace=str(tmp_path), gpu="cpu", patch_size=(4, 4, 4))
    binding = {"manifest_path": "metadata-manifest", "splits_path": "metadata-splits"}
    cases = [
        {
            "case_id": name,
            "image": f"{name}-image-is-not-present",
            "label": f"{name}-label-is-not-present",
            "image_sha256": f"{name}-image-hash",
            "label_sha256": f"{name}-label-hash",
        }
        for name in ("train", "validation", "heldout", "unlabeled")
    ]
    splits = {"train": ["train"], "val": ["validation"], "test": ["heldout"]}
    monkeypatch.setattr(torch_backend, "_binding", lambda *args, **kwargs: binding)
    monkeypatch.setattr(torch_backend, "_documents", lambda *args: ({"cases": cases}, splits))
    accesses = []

    def check_hash(path, digest):
        accesses.append(path)
        if not path.startswith("train-"):
            raise AssertionError("Preprocessing tried to open an evaluation payload")

    def preprocess(case, config, *, with_label):
        assert case["case_id"] == "train" and with_label
        return {
            "image": np.zeros((4, 4, 4), np.float32),
            "label": np.zeros((4, 4, 4), np.uint8),
            "affine": np.eye(4),
        }

    monkeypatch.setattr(torch_backend, "_check_hash", check_hash)
    monkeypatch.setattr(torch_data, "preprocess_case", preprocess)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "config": torch_backend._config_record(config),
                "action": "preprocess",
                "payload": {},
                "identity": torch_backend._digest(binding),
            }
        )
    )
    torch_backend._worker(request)
    assert accesses == ["train-image-is-not-present", "train-label-is-not-present"]
    assert [path.name for path in (tmp_path / "cache").iterdir()] == ["train.npz"]
    plan = json.loads((tmp_path / "plan-binding.json").read_text())
    assert set(plan["files"]) == {"train.npz"}


@pytest.mark.parametrize("name", ("umamba_bot", "umamba_enc", "segmamba"))
def test_mamba_catalog_dimensionality_and_actual_scratch_guard_compatibility(name):
    metadata = model_registry.model_metadata(name)
    assert metadata["dimensions"] == 3
    model = model_registry.build_model(
        name,
        patch_size=tuple(metadata["smoke_patch_size"]),
        model_options=metadata["smoke_options"],
    )
    assert isinstance(model, nn.Module)


def test_gpu_ordinal_normalization_uses_one_lock_identity(tmp_path):
    standard = TorchConfig(workspace=str(tmp_path / "standard"), gpu="0")
    alternate = TorchConfig(workspace=str(tmp_path / "alternate"), gpu="00")
    assert alternate.gpu == standard.gpu == "0"


@pytest.mark.parametrize("entry", ("safe_open", "torch_safe_open", "bytes_load"))
def test_scratch_guard_blocks_cached_safetensors_deserialization(tmp_path, entry):
    import safetensors
    import safetensors.torch

    checkpoint = tmp_path / "cached-pretrained.safetensors"
    safetensors.torch.save_file({"pretrained_weight": torch.ones(2)}, str(checkpoint))
    payload = checkpoint.read_bytes()
    with model_registry.scratch_only(), pytest.raises(RuntimeError, match="Scratch-only"):
        if entry == "bytes_load":
            safetensors.torch.load(payload)
        else:
            reader = safetensors.safe_open if entry == "safe_open" else safetensors.torch.safe_open
            with reader(str(checkpoint), framework="pt") as handle:
                handle.get_tensor("pretrained_weight")
