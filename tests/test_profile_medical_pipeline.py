"""Diagnostic profiler partition, numerical timing and publication contracts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
import torch
from torch import nn

from segmentary.medical.geometry import sha256_file
from segmentary.medical.torch_config import TorchConfig

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "profile_medical_pipeline.py"
_SPEC = importlib.util.spec_from_file_location("profile_medical_pipeline_test", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
profiler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(profiler)


def test_profile_selects_only_train_extremes_and_median_without_opening_evaluation(monkeypatch):
    accesses = []
    monkeypatch.setattr(profiler, "validate_splits", lambda *args: None)

    def hash_training_only(path):
        accesses.append(str(path))
        if "heldout" in str(path):
            raise AssertionError("Profiler opened held-out content")
        return "a" * 64

    monkeypatch.setattr(profiler, "sha256_file", hash_training_only)
    cases = [
        {
            "case_id": name,
            "shape": [size, 2, 3],
            "annotation_status": "labeled",
            "image": f"{name}-image",
            "label": f"{name}-label",
            "image_sha256": "a" * 64,
            "label_sha256": "a" * 64,
        }
        for name, size in (("a", 4), ("b", 1), ("c", 9), ("d", 5), ("e", 7), ("heldout", 999))
    ]
    result = profiler._select_cases(
        {"cases": cases}, {"train": ["a", "b", "c", "d", "e"], "val": ["heldout"]}
    )
    assert [case["case_id"] for case in result] == ["b", "d", "c"]
    assert len(accesses) == 6


def _training_case(tmp_path):
    image = np.arange(9 * 8 * 7, dtype=np.float32).reshape(9, 8, 7)
    label = np.zeros(image.shape, np.uint8)
    label[2:7, 2:6, 1:5] = 1
    label[3:5, 3:5, 2:4] = 2
    case = {"case_id": "train", "shape": list(image.shape)}
    for key, array in (("image", image), ("label", label)):
        path = tmp_path / f"{key}.nii.gz"
        volume = nib.Nifti1Image(array, np.eye(4))
        volume.header.set_xyzt_units("mm")
        volume.set_qform(np.eye(4), code=1)
        volume.set_sform(np.eye(4), code=1)
        nib.save(volume, path)
        case[key] = str(path)
        case[f"{key}_sha256"] = sha256_file(path)
    return case


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"foreground_probability": None, "center_probabilities": (0.25, 0.25, 0.5)},
        {"foreground_probability": None, "class_center_weights": (1, 1, 5)},
        {"rotation_probability": 1},
        {"intensity_scale_probability": 1},
    ],
)
def test_real_nifti_data_profile_checks_current_recipe_and_only_applicable_legacy_parity(
    tmp_path, monkeypatch, options
):
    case = _training_case(tmp_path)
    config = TorchConfig(str(tmp_path), gpu="cpu", patch_size=(4, 4, 4), **options)
    if options:

        def forbidden(*args, **kwargs):
            raise AssertionError("Historical sampler must not run with a different recipe")

        monkeypatch.setattr(profiler, "_legacy_sample", forbidden)
    result, mapped = profiler._data_profile(case, config, tmp_path, iterations=2)
    assert result["bitwise_samples_and_rng_equal"]
    assert result["sample"]["optimized"]["count"] == 2
    assert result["sample"]["current_raw"]["count"] == 2
    assert (
        result["sample_parity_reference"] == "current recipe on raw arrays versus mapped NPY arrays"
    )
    comparison = result["legacy_sampler_comparison"]
    assert comparison["applicable"] == (not options)
    if options:
        assert comparison["reason"]
        assert comparison["bitwise_samples_and_rng_equal"] is None
        assert "legacy" not in result["sample"]
    else:
        assert comparison["bitwise_samples_and_rng_equal"]
        assert result["sample"]["legacy"]["count"] == 2
    assert result["load"]["legacy_npz"]["p50_seconds"] > 0
    assert not (tmp_path / "train.npz").exists()
    assert isinstance(mapped["image"], np.memmap)


@pytest.mark.parametrize("mutation", ["array", "rng"])
def test_new_recipe_data_profile_rejects_cached_output_or_rng_disagreement(
    tmp_path, monkeypatch, mutation
):
    case = _training_case(tmp_path)
    config = TorchConfig(
        str(tmp_path),
        gpu="cpu",
        patch_size=(4, 4, 4),
        foreground_probability=None,
        class_center_weights=(1, 1, 5),
    )
    original = profiler.sample_patch

    def corrupted(data, config, rng):
        image, label = original(data, config, rng)
        if isinstance(data["image"], np.memmap):
            if mutation == "array":
                image[0, 0, 0, 0] += 1
            else:
                rng.random()
        return image, label

    monkeypatch.setattr(profiler, "sample_patch", corrupted)
    with pytest.raises(AssertionError if mutation == "array" else ValueError):
        profiler._data_profile(case, config, tmp_path, iterations=1)


def test_model_profile_records_real_updates_trace_and_native_batch_disagreement(
    tmp_path, monkeypatch
):
    model = nn.Conv3d(1, 3, 1)
    before = model.weight.detach().clone()
    monkeypatch.setattr(profiler, "build_model", lambda *args, **kwargs: model)
    batches = []

    def predict_training_image_only(model, case, config, device):
        assert set(case) == {"case_id", "image"}
        batches.append(config.inference_batch_size)
        result = np.zeros((5, 6, 7), np.uint8)
        if config.inference_batch_size == 2:
            result[0, 0, 0] = 1
        return result

    monkeypatch.setattr(profiler, "predict_case", predict_training_image_only)
    rng = np.random.default_rng(7)
    data = {"image": rng.random((7, 6, 5), dtype=np.float32), "label": np.ones((7, 6, 5), np.uint8)}
    config = TorchConfig(
        str(tmp_path), gpu="cpu", patch_size=(4, 4, 4), workers=1, inference_batch_size=2
    )
    previous_threads = torch.get_num_threads()
    previous_determinism = torch.are_deterministic_algorithms_enabled()
    try:
        result = profiler._model_profile(
            {"case_id": "train", "image": "train-only", "label": "forbidden", "shape": [5, 6, 7]},
            data,
            config,
            tmp_path,
            trace=True,
            skip_inference=False,
        )
    finally:
        torch.set_num_threads(previous_threads)
        torch.use_deterministic_algorithms(previous_determinism)
    assert not torch.equal(before, model.weight)
    assert result["measured_steps"] == 5
    assert result["timings"]["forward"]["count"] == 5
    assert result["operators"]
    assert (tmp_path / "trace.json").is_file()
    assert not list(tmp_path.rglob("*.pth"))
    assert batches == [1, 2]
    assert result["native_inference"]["argmax_disagreement_voxels"] == 1
    assert result["checkpoint_serialization"]["retained"] is False


def test_main_publishes_progress_and_final_summary_but_refuses_existing_output(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"backend": "torch", "workspace": "run", "gpu": "cpu"}))
    manifest_path, splits_path = tmp_path / "manifest.json", tmp_path / "splits.json"
    manifest_path.write_text("{}")
    splits_path.write_text('{"fingerprint":"splits"}')
    monkeypatch.setattr(
        profiler, "load_manifest", lambda *args, **kwargs: {"fingerprint": "manifest"}
    )
    monkeypatch.setattr(profiler, "_select_cases", lambda *args: [{"case_id": "train"}])
    monkeypatch.setattr(profiler, "_data_profile", lambda *args: ({"case_id": "train"}, {}))
    monkeypatch.setattr(profiler, "_model_profile", lambda *args: {"measured_steps": 5})
    output = tmp_path / "output"
    monkeypatch.setattr(
        profiler.sys,
        "argv",
        [
            str(_SCRIPT),
            "--config",
            str(config_path),
            "--manifest",
            str(manifest_path),
            "--splits",
            str(splits_path),
            "--output",
            str(output),
        ],
    )
    assert profiler.main() == 0
    result = json.loads((output / "summary.json").read_text())
    assert result["status"] == "completed"
    assert result["data"] == [{"case_id": "train"}]
    assert result["config"]["workspace"] == str(tmp_path / "run")
    with pytest.raises(FileExistsError):
        profiler.main()
