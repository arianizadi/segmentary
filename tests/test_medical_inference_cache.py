"""Integrity and exactness of stage-verified, image-only inference snapshots."""

from __future__ import annotations

import dataclasses
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

nib = pytest.importorskip("nibabel")
pytest.importorskip("torch")

from segmentary.medical.geometry import (  # noqa: E402
    export_native_prediction,
    validate_nifti,
)
from segmentary.medical.torch_config import TorchConfig  # noqa: E402
from segmentary.medical.torch_data import preprocess_case  # noqa: E402
from segmentary.medical.torch_inference_cache import InferenceImageCache  # noqa: E402


def _case(root: Path, name: str = "one") -> dict:
    path = root / f"{name}.nii.gz"
    matrix = np.array(
        [[0.0, -1.2, 0.0, 12.0], [0.8, 0.0, 0.1, -8.0], [0.0, 0.0, 2.5, 3.0], [0.0, 0.0, 0.0, 1.0]]
    )
    values = (np.arange(9 * 10 * 11).reshape(9, 10, 11) - 200).astype(np.int16)
    image = nib.Nifti1Image(values, matrix)
    image.header.set_xyzt_units("mm")
    image.set_sform(matrix, code=1)
    image.set_qform(None, code=0)
    nib.save(image, path)
    info = validate_nifti(path)
    return {
        "image": str(path),
        "image_sha256": info["sha256"],
        "shape": info["shape"],
        "affine": info["affine"],
        "spacing_mm": info["spacing_mm"],
        "label": str(root / "forbidden-label.nii.gz"),
    }


def _config(root: Path) -> TorchConfig:
    return TorchConfig(
        workspace=str(root / "run"),
        gpu="cpu",
        spacing_mm=(1.3, 1.7, 2.1),
        patch_size=(8, 8, 8),
        workers=1,
    )


def _directory(root: Path) -> Path:
    return next(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


def test_cache_exactly_matches_existing_preprocessing_and_never_reads_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _case(tmp_path)
    config = _config(tmp_path)
    expected = preprocess_case(original, config, with_label=False)
    allowed = {"image", "image_sha256", "shape", "spacing_mm", "affine"}

    class ImageOnly(dict):
        def __getitem__(self, key):
            assert key in allowed, f"Accessed supervision key {key}"
            return super().__getitem__(key)

        def get(self, key, default=None):
            assert key in allowed, f"Accessed supervision key {key}"
            return super().get(key, default)

    case = ImageOnly(original)
    actual_load = nib.load
    opened = []

    def load(path, *args, **kwargs):
        assert "label" not in str(path)
        opened.append(str(path))
        return actual_load(path, *args, **kwargs)

    monkeypatch.setattr(nib, "load", load)
    with InferenceImageCache(tmp_path / "cache", config) as cache:
        data = cache.load(case)
        np.testing.assert_array_equal(data["image"], expected["image"])
        np.testing.assert_array_equal(data["affine"], expected["affine"])
        np.testing.assert_array_equal(data["native_affine"], original["affine"])
        assert data["native_shape"] == tuple(original["shape"])
        assert isinstance(data["image"], np.memmap) and not data["image"].flags.writeable
        assert not data["affine"].flags.writeable
        assert cache.stats["builds"] == 1
        assert cache.stats["source_verifications"] == 1
        assert cache.stats["cache_verifications"] == 1
    assert opened and all("label" not in name for name in opened)
    assert {path.name for path in _directory(tmp_path / "cache").iterdir()} == {
        "image.npy",
        "affine.npy",
        "cache.json",
    }


def test_repeated_epochs_reuse_mapping_without_hashing_or_decoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from segmentary.medical import torch_inference_cache as module

    case, config = _case(tmp_path), _config(tmp_path)
    with InferenceImageCache(tmp_path / "cache", config) as cache:
        first = cache.load(case)

        def forbidden(*args, **kwargs):
            raise AssertionError("Hot reuse must use signatures, not full hashing or decoding")

        monkeypatch.setattr(module, "sha256_file", forbidden)
        monkeypatch.setattr(nib, "load", forbidden)
        for _ in range(3):
            again = cache.load(case)
            assert again["image"] is first["image"]
            cache.check(case)
        assert cache.stats["source_verifications"] == 1
        assert cache.stats["memory_hits"] == 3


def test_next_stage_reverifies_bytes_without_reprocessing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from segmentary.medical import torch_data
    from segmentary.medical import torch_inference_cache as module

    case, config = _case(tmp_path), _config(tmp_path)
    with InferenceImageCache(tmp_path / "cache", config) as first:
        first.load(case)
    hashes = []
    original_hash = module.sha256_file

    def track(path):
        hashes.append(str(path))
        return original_hash(path)

    def forbidden(*args, **kwargs):
        raise AssertionError("Valid persistent cache must not rerun preprocessing")

    monkeypatch.setattr(module, "sha256_file", track)
    monkeypatch.setattr(torch_data, "preprocess_case", forbidden)
    with InferenceImageCache(tmp_path / "cache", config) as second:
        second.load(case)
        second.load(case)
        assert second.stats["source_verifications"] == 1
        assert second.stats["cache_verifications"] == 1
        assert second.stats["disk_hits"] == 1
        assert second.stats["builds"] == 0
    assert hashes.count(case["image"]) == 1
    assert any(path.endswith("image.npy") for path in hashes)
    assert any(path.endswith("affine.npy") for path in hashes)


@pytest.mark.parametrize("kind", ["source", "image.npy", "affine.npy", "cache.json", "extra-file"])
def test_instage_change_guards_reject_source_or_cache_even_if_mtime_restored(
    tmp_path: Path, kind: str
) -> None:
    case, config = _case(tmp_path), _config(tmp_path)
    with InferenceImageCache(tmp_path / "cache", config) as cache:
        cache.load(case)
        directory = _directory(tmp_path / "cache")
        if kind == "extra-file":
            (directory / "unexpected").write_text("not a valid member")
        else:
            path = Path(case["image"]) if kind == "source" else directory / kind
            before = path.stat()
            path.chmod(0o644)
            value = path.read_bytes()
            path.write_bytes(value[:-1] + bytes([value[-1] ^ 1]))
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with pytest.raises(ValueError, match=r"changed|membership"):
            cache.check(case)
        with pytest.raises(ValueError, match=r"changed|membership"):
            cache.load(case)


@pytest.mark.parametrize("kind", ["source", "image.npy", "affine.npy", "cache.json", "symlink"])
def test_new_stage_rejects_corrupted_published_input_instead_of_rebuilding(
    tmp_path: Path, kind: str
) -> None:
    case, config = _case(tmp_path), _config(tmp_path)
    with InferenceImageCache(tmp_path / "cache", config) as cache:
        cache.load(case)
    directory = _directory(tmp_path / "cache")
    path = (
        Path(case["image"])
        if kind == "source"
        else directory / ("image.npy" if kind == "symlink" else kind)
    )
    if kind == "symlink":
        moved = tmp_path / "moved.npy"
        path.rename(moved)
        path.symlink_to(moved)
    else:
        path.chmod(0o644)
        path.write_bytes(path.read_bytes() + b"corrupt")
    with InferenceImageCache(tmp_path / "cache", config) as next_stage:
        with pytest.raises((ValueError, json.JSONDecodeError)):
            next_stage.load(case)
        assert next_stage.stats["builds"] == 0


def test_source_mutation_while_building_never_publishes_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from segmentary.medical import torch_data

    case, config = _case(tmp_path), _config(tmp_path)
    original = torch_data.preprocess_case

    def changed(*args, **kwargs):
        data = original(*args, **kwargs)
        path = Path(case["image"])
        os.utime(path, None)
        return data

    monkeypatch.setattr(torch_data, "preprocess_case", changed)
    with InferenceImageCache(tmp_path / "cache", config) as cache:
        with pytest.raises(ValueError, match="changed during preprocessing"):
            cache.load(case)
    assert not [path for path in (tmp_path / "cache").iterdir() if path.is_dir()]


def test_bounded_lru_does_not_close_inflight_mappings(tmp_path: Path) -> None:
    config = _config(tmp_path)
    cases = [_case(tmp_path, name) for name in ("one", "two", "three")]
    with InferenceImageCache(tmp_path / "cache", config, max_open_cases=1) as cache:
        one = cache.load(cases[0])
        expected = np.array(one["image"])
        for case in cases[1:]:
            cache.load(case)
        assert cache.stats["open_cases"] == 1
        assert cache.stats["verified_cases"] == 3
        np.testing.assert_array_equal(one["image"], expected)
        cache.check(cases[0])
        np.testing.assert_array_equal(cache.load(cases[0])["image"], expected)
    # External users own their references; cache.close must not invalidate them.
    np.testing.assert_array_equal(one["image"], expected)
    with pytest.raises(RuntimeError, match="closed"):
        cache.load(cases[0])


def test_concurrent_prep_and_postprocess_are_safe_and_reverify_once(tmp_path: Path) -> None:
    case, config = _case(tmp_path), _config(tmp_path)
    with (
        InferenceImageCache(tmp_path / "cache", config) as cache,
        ThreadPoolExecutor(max_workers=4) as pool,
    ):
        arrays = list(pool.map(lambda _: cache.load(case)["image"], range(8)))
        assert cache.stats["source_verifications"] == 1
        assert cache.stats["builds"] == 1
        assert all(array is arrays[0] for array in arrays)
        list(pool.map(lambda _: cache.check(case), range(8)))


def test_cache_identity_ignores_architecture_but_binds_preprocessing(tmp_path: Path) -> None:
    case, config = _case(tmp_path), _config(tmp_path)
    root = tmp_path / "cache"
    with InferenceImageCache(root, config) as cache:
        cache.load(case)
    changed_model = dataclasses.replace(
        config, model="segresnet", batch_size=7, patch_size=(16, 16, 16), seed=3
    )
    with InferenceImageCache(root, changed_model) as cache:
        cache.load(case)
        assert cache.stats["builds"] == 0
    with InferenceImageCache(
        root, dataclasses.replace(config, spacing_mm=(2.0, 2.0, 2.0))
    ) as cache:
        cache.load(case)
        assert cache.stats["builds"] == 1
    assert len([p for p in root.iterdir() if p.is_dir()]) == 2


def test_export_uses_private_verified_geometry_and_matches_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from segmentary.medical import torch_inference_cache as module

    case, config = _case(tmp_path), _config(tmp_path)
    prediction = np.zeros(case["shape"], dtype=np.uint8)
    prediction[2:6, 3:8, 3:7] = 1
    prediction[3, 4, 5] = 2
    legacy = tmp_path / "legacy.nii.gz"
    export_native_prediction(case["image"], prediction, legacy)
    with InferenceImageCache(tmp_path / "cache", config) as cache:
        visible = cache.load(case)
        visible["reference"]["shape"][0] = 999
        visible["reference"]["affine"][0][3] = 999
        visible["native_affine"][1, 3] = 999
        original_hash = module.sha256_file

        def no_source_hash(path):
            assert str(path) != case["image"], "Export rehashed the entire raw CT"
            return original_hash(path)

        monkeypatch.setattr(module, "sha256_file", no_source_hash)
        output = tmp_path / "cached.nii.gz"
        cache.export_prediction(case, prediction, output)
        reference, actual = nib.load(legacy), nib.load(output)
        np.testing.assert_array_equal(actual.dataobj, reference.dataobj)
        np.testing.assert_array_equal(actual.affine, reference.affine)
        assert actual.header.get_xyzt_units() == reference.header.get_xyzt_units()
        with pytest.raises(FileExistsError):
            cache.export_prediction(case, prediction, output)
        with pytest.raises(ValueError, match="shape"):
            cache.export_prediction(case, prediction[:2], tmp_path / "shape.nii.gz")
        with pytest.raises(ValueError, match="fractional"):
            cache.export_prediction(
                case, prediction.astype(float) + 0.1, tmp_path / "fraction.nii.gz"
            )


def test_export_fails_if_raw_source_changed_after_inference(tmp_path: Path) -> None:
    case, config = _case(tmp_path), _config(tmp_path)
    with InferenceImageCache(tmp_path / "cache", config) as cache:
        cache.load(case)
        os.utime(case["image"], None)
        output = tmp_path / "invalid.nii.gz"
        with pytest.raises(ValueError, match="source changed"):
            cache.export_prediction(case, np.zeros(case["shape"], np.uint8), output)
        assert not output.exists()
