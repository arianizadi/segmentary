"""Shared cache integrity and bit-for-bit patch sampling regression checks."""

from __future__ import annotations

import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor

import nibabel as nib
import numpy as np
import pytest
import torch
from torch import nn

from segmentary.medical import torch_data
from segmentary.medical.geometry import sha256_file
from segmentary.medical.torch_cache import (
    build_cached_case,
    cache_file_records,
    load_cached_case,
)
from segmentary.medical.torch_config import TorchConfig


def _case(tmp_path):
    image = np.arange(9 * 11 * 7, dtype=np.float32).reshape(9, 11, 7) - 100
    label = np.zeros(image.shape, dtype=np.uint8)
    label[2:7, 3:9, 1:6] = 1
    label[4:6, 5:8, 2:4] = 2
    affine = np.diag([0.75, 1.25, 2.5, 1.0])
    result = {"case_id": "synthetic-training-case"}
    for name, array in (("image", image), ("label", label)):
        path = tmp_path / f"{name}.nii.gz"
        volume = nib.Nifti1Image(array, affine)
        volume.header.set_xyzt_units("mm")
        volume.set_qform(affine, code=1)
        volume.set_sform(affine, code=1)
        nib.save(volume, path)
        result[name] = str(path)
        result[f"{name}_sha256"] = sha256_file(path)
    return result


def test_shared_npy_cache_matches_physical_preprocessing_and_reuses_only_equivalent_grid(
    tmp_path, monkeypatch
):
    case = _case(tmp_path)
    config = TorchConfig(str(tmp_path / "run"), gpu="cpu", patch_size=(5, 6, 7))
    expected = torch_data.preprocess_case(case, config, with_label=True)
    first = build_cached_case(case, config, tmp_path / "shared")
    # A run's record survives JSON serialization and contains every backing file.
    first = json.loads(json.dumps(first))
    actual = load_cached_case(first)
    for key in ("image", "label", "affine"):
        assert isinstance(actual[key], np.memmap)
        assert not actual[key].flags.writeable
        np.testing.assert_array_equal(actual[key], expected[key])
    for class_id in (1, 2):
        np.testing.assert_array_equal(
            actual["foreground_coordinates"][class_id], np.argwhere(expected["label"] == class_id)
        )
    assert cache_file_records(first) == first["files"]
    original = torch_data.preprocess_case

    def forbidden(*args, **kwargs):
        raise AssertionError("Equivalent cache should be reused")

    monkeypatch.setattr(torch_data, "preprocess_case", forbidden)
    other_model = dataclasses.replace(
        config, model="segformer_b0", mode="2.5d", context_slices=5, patch_size=(9, 9), seed=9
    )
    assert build_cached_case(case, other_model, tmp_path / "shared") == first
    monkeypatch.setattr(torch_data, "preprocess_case", original)
    changed_window = build_cached_case(
        case, dataclasses.replace(config, hu_window=(-200, 200)), tmp_path / "shared"
    )
    changed_grid = build_cached_case(
        case, dataclasses.replace(config, spacing_mm=(2, 2, 3)), tmp_path / "shared"
    )
    assert len({item["fingerprint"] for item in (first, changed_window, changed_grid)}) == 3


@pytest.mark.parametrize("mutation", ["content", "membership", "symlink"])
def test_corrupt_cache_fails_without_silent_rebuild(tmp_path, mutation):
    from pathlib import Path

    case = _case(tmp_path)
    config = TorchConfig(str(tmp_path / "run"), gpu="cpu")
    record = build_cached_case(case, config, tmp_path / "shared")
    directory = Path(record["path"])
    path = directory / "label.npy"
    if mutation == "content":
        path.chmod(0o644)
        payload = bytearray(path.read_bytes())
        payload[-1] ^= 1
        path.write_bytes(payload)
    elif mutation == "membership":
        (directory / "unexpected.txt").write_text("unexpected")
    else:
        target = tmp_path / "moved-label.npy"
        path.rename(target)
        path.symlink_to(target)
    with pytest.raises(ValueError, match="cache"):
        load_cached_case(record)
    with pytest.raises(ValueError, match="cache"):
        build_cached_case(case, config, tmp_path / "shared")


def test_published_cache_never_bypasses_source_hash_verification(tmp_path):
    from pathlib import Path

    case = _case(tmp_path)
    config = TorchConfig(str(tmp_path / "run"), gpu="cpu")
    build_cached_case(case, config, tmp_path / "shared")
    Path(case["image"]).write_bytes(b"changed original scan")
    with pytest.raises(ValueError, match="source image changed"):
        build_cached_case(case, config, tmp_path / "shared")


def test_interrupted_builder_does_not_publish_incomplete_cache(tmp_path, monkeypatch):
    case = _case(tmp_path)
    config = TorchConfig(str(tmp_path / "run"), gpu="cpu")

    def interrupted(*args, **kwargs):
        raise RuntimeError("interrupted resampling")

    monkeypatch.setattr(torch_data, "preprocess_case", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        build_cached_case(case, config, tmp_path / "shared")
    assert not any(path.is_dir() for path in (tmp_path / "shared").iterdir())


def test_concurrent_builders_publish_one_complete_generation(tmp_path, monkeypatch):
    case = _case(tmp_path)
    config = TorchConfig(str(tmp_path / "run"), gpu="cpu")
    original = torch_data.preprocess_case
    calls = []

    def tracked(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(torch_data, "preprocess_case", tracked)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(build_cached_case, case, config, tmp_path / "shared") for _ in range(2)
        ]
        records = [future.result() for future in futures]
    assert records[0] == records[1]
    assert len(calls) == 1
    load_cached_case(records[0])


def _original_sample(data, config, rng):
    """Frozen pre-optimization algorithm: pad whole volume before cropping."""
    image, label = data["image"], data["label"]
    center = [int(rng.integers(size)) for size in label.shape]
    if rng.random() < config.foreground_probability:
        classes = [c for c in (1, 2) if np.any(label == c)]
        if classes:
            locations = np.argwhere(label == rng.choice(classes))
            center = locations[int(rng.integers(len(locations)))].tolist()
    if config.mode == "3d":
        image = image[None]
    else:
        offsets = np.arange(config.context_slices) - config.context_slices // 2
        image = image[np.clip(center[0] + offsets, 0, image.shape[0] - 1)]
        label = label[center[0]]
        center = center[1:]
    padding = [
        (max(0, (p - n) // 2), max(0, p - n - (p - n) // 2))
        for n, p in zip(label.shape, config.patch_size, strict=True)
    ]
    image = np.pad(image, [(0, 0), *padding], constant_values=0)
    label = np.pad(label, padding, constant_values=0)
    starts = [
        max(0, min(c + pad[0] - p // 2, n - p))
        for c, pad, p, n in zip(center, padding, config.patch_size, label.shape, strict=True)
    ]
    crop = tuple(
        slice(start, start + p) for start, p in zip(starts, config.patch_size, strict=True)
    )
    image, label = image[(slice(None), *crop)], label[crop]
    if config.augment:
        for axis in range(label.ndim):
            if rng.random() < 0.5:
                image, label = np.flip(image, axis + 1), np.flip(label, axis)
    return image.copy(), label.astype(np.int64).copy()


@pytest.mark.parametrize("mode,context", [("2d", 1), ("2.5d", 5), ("3d", 1)])
@pytest.mark.parametrize("shape", [(1, 3, 2), (7, 8, 9), (15, 16, 17)])
@pytest.mark.parametrize("foreground", [False, True])
def test_optimized_patch_is_bitwise_equal_and_consumes_identical_rng(
    tmp_path, mode, context, shape, foreground
):
    data_rng = np.random.default_rng(753)
    data = {
        "image": data_rng.random(shape, dtype=np.float32),
        "label": data_rng.integers(0, 3, shape, dtype=np.uint8)
        if foreground
        else np.zeros(shape, dtype=np.uint8),
    }
    prepared = {
        **data,
        "foreground_coordinates": {c: np.argwhere(data["label"] == c) for c in (1, 2)},
    }
    config = TorchConfig(
        str(tmp_path),
        gpu="cpu",
        mode=mode,
        context_slices=context,
        patch_size=(6, 9, 8) if mode == "3d" else (9, 8),
    )
    for seed in range(25):
        expected_rng = np.random.default_rng(seed)
        expected = _original_sample(data, config, expected_rng)
        for source in (data, prepared):
            actual_rng = np.random.default_rng(seed)
            actual = torch_data.sample_patch(source, config, actual_rng)
            for a, b in zip(expected, actual, strict=True):
                np.testing.assert_array_equal(a, b)
                assert b.flags.c_contiguous
            assert actual_rng.bit_generator.state == expected_rng.bit_generator.state


def test_prepared_patch_never_scans_or_pads_full_volume(tmp_path, monkeypatch):
    image = np.zeros((35, 40, 45), dtype=np.float32)
    label = np.zeros(image.shape, dtype=np.uint8)
    label[20, 21, 22] = 2
    data = {
        "image": image,
        "label": label,
        "foreground_coordinates": {c: np.argwhere(label == c) for c in (1, 2)},
    }
    config = TorchConfig(str(tmp_path), gpu="cpu", patch_size=(8, 9, 10), foreground_probability=1)

    def forbidden(*args, **kwargs):
        raise AssertionError("Hot path rescanned or copied/padded the full volume")

    monkeypatch.setattr(np, "argwhere", forbidden)
    monkeypatch.setattr(np, "any", forbidden)
    monkeypatch.setattr(np, "pad", forbidden)
    patch, target = torch_data.sample_patch(data, config, np.random.default_rng(0))
    assert patch.shape == (1, 8, 9, 10)
    assert 2 in target


@pytest.mark.parametrize("mode", ["2d", "3d"])
@pytest.mark.parametrize("small", [False, True])
def test_batched_tiles_preserve_odd_edges_padding_and_eval_batchnorm(tmp_path, mode, small):
    dimensions = 2 if mode == "2d" else 3
    shape = (2,) * dimensions if small else (9, 11, 13)[-dimensions:]
    patch = (4, 5, 6)[-dimensions:]
    image = np.random.default_rng(519).random((1, *shape), dtype=np.float32)
    normalization = nn.BatchNorm2d(1) if mode == "2d" else nn.BatchNorm3d(1)
    normalization.running_mean.fill_(0.7)
    normalization.running_var.fill_(0.3)

    class Pointwise(nn.Module):
        def __init__(self):
            super().__init__()
            self.norm = normalization
            self.batch_sizes = []

        def forward(self, x):
            self.batch_sizes.append(len(x))
            value = self.norm(x)
            return torch.cat([value, -value, value + 0.5], dim=1)

    model = Pointwise().eval()
    with torch.inference_mode():
        expected = model(torch.from_numpy(image[None])).softmax(1)[0].numpy()
    previous = None
    for batch_size in (1, 2, 8):
        model.batch_sizes.clear()
        config = TorchConfig(
            str(tmp_path),
            gpu="cpu",
            mode=mode,
            patch_size=patch,
            inference_batch_size=batch_size,
            overlap=0.5,
        )
        actual = torch_data.tiled_probabilities(model, image, config, torch.device("cpu"))
        np.testing.assert_allclose(actual, expected, atol=2e-7, rtol=2e-7)
        if previous is not None:
            np.testing.assert_allclose(actual, previous, atol=2e-7, rtol=2e-7)
        previous = actual
        assert max(model.batch_sizes) <= batch_size
        if not small:
            assert max(model.batch_sizes) == batch_size
        np.testing.assert_array_equal(model.norm.running_mean.numpy(), np.array([0.7], np.float32))


@pytest.mark.parametrize("invalid", ["shape", "nan"])
def test_batched_inference_rejects_invalid_logits(tmp_path, invalid):
    class Invalid(nn.Module):
        def forward(self, x):
            if invalid == "shape":
                return torch.zeros(1, 3, *x.shape[2:])
            return torch.full((len(x), 3, *x.shape[2:]), float("nan"))

    config = TorchConfig(
        str(tmp_path), gpu="cpu", mode="2d", patch_size=(3, 4), inference_batch_size=2
    )
    with pytest.raises(ValueError, match="invalid dense logits"):
        torch_data.tiled_probabilities(
            Invalid(), np.zeros((1, 7, 8), np.float32), config, torch.device("cpu")
        )
