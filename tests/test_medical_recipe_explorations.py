"""Loss identities, physical crop reconstruction, and preprocessing isolation."""

from __future__ import annotations

import dataclasses
import hashlib
import json

import nibabel as nib
import numpy as np
import pytest
import torch

from segmentary.medical.torch_config import TorchConfig
from segmentary.medical.torch_data import dice_ce, dice_focal, preprocess_case
from segmentary.medical.torch_geometry import native_argmax, native_probabilities
from segmentary.medical.torch_inference_cache import _pipeline_identity
from segmentary.medical.torch_roi import crop_image, predicted_bbox


def test_focal_reduces_to_existing_ce_and_dice_and_handles_extreme_logits():
    torch.manual_seed(42)
    targets = torch.randint(0, 3, (2, 4, 5, 6))
    logits = torch.randn(2, 3, 4, 5, 6, requires_grad=True)
    torch.testing.assert_close(
        dice_focal(logits, targets, coefficient=1, gamma=0), dice_ce(logits, targets)
    )
    loss = dice_focal(logits * 1000, targets, coefficient=0.5, gamma=2)
    assert torch.isfinite(loss)
    loss.backward()
    assert torch.isfinite(logits.grad).all() and logits.grad.abs().sum() > 0
    torch.testing.assert_close(
        dice_focal(logits, targets, coefficient=0, gamma=2),
        dice_ce(logits, targets) - torch.nn.functional.cross_entropy(logits, targets),
    )


@pytest.mark.parametrize(
    "options",
    [
        {"focal_gamma": -1},
        {"loss": "dice_focal", "focal_coefficient": float("nan")},
        {"loss": "dice_focal", "model": "maskformer"},
        {"loss": "dice_focal", "model_options": {"deep_supervision": True}},
        {"normalization": "test_fitted"},
        {"roi_manifest": "/tmp/example"},
    ],
)
def test_invalid_exploration_config_rejected(options):
    with pytest.raises(ValueError):
        TorchConfig(workspace="/tmp/config", **({"model": "dynunet"} | options))


def example(tmp_path):
    values = np.linspace(-1000, 1000, 8 * 10 * 12, dtype=np.float32).reshape(8, 10, 12)
    affine = np.diag([2.0, 3.0, 4.0, 1.0])
    affine[:3, 3] = [-4, -9, 16]
    path = tmp_path / "ct.nii.gz"
    volume = nib.Nifti1Image(values, affine)
    volume.header.set_xyzt_units("mm")
    nib.save(volume, path)
    case = {
        "case_id": "case",
        "image": str(path),
        "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "label": "/must-not-open",
    }
    config = TorchConfig(workspace=str(tmp_path / "run"), spacing_mm=(2, 3, 4))
    return values, volume, case, config


def roi_config(tmp_path, case, config, bounds):
    path = tmp_path / "roi.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "predicted_pancreas_native_bbox",
                "reference_labels_used": False,
                "empty_prediction_policy": "full_ct",
                "cases": {"case": {"image_sha256": case["image_sha256"], "bbox_xyz": bounds}},
            }
        )
    )
    return dataclasses.replace(
        config,
        roi_manifest=str(path),
        roi_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_normalization_has_no_label_dependency_and_cache_keys_differ(tmp_path):
    values, _, case, config = example(tmp_path)
    fixed = preprocess_case(case, config, with_label=False)["image"]
    np.testing.assert_array_equal(
        fixed, ((np.clip(values, -100, 240) + 100) / 340).transpose(2, 1, 0)
    )
    adaptive = dataclasses.replace(config, normalization="volume_minmax")
    np.testing.assert_array_equal(
        preprocess_case(case, adaptive, with_label=False)["image"],
        ((values + 1000) / 2000).transpose(2, 1, 0),
    )
    assert _pipeline_identity(config) != _pipeline_identity(adaptive)
    assert _pipeline_identity(config) != _pipeline_identity(
        dataclasses.replace(config, hu_window=(-175, 250))
    )


def test_cascade_native_translation_and_full_scan_missed_mass(tmp_path):
    _, volume, case, config = example(tmp_path)
    roi = roi_config(tmp_path, case, config, [[2, 6], [3, 8], [4, 9]])
    cropped = crop_image(volume, case, roi)
    assert cropped.shape == (4, 5, 5)
    np.testing.assert_array_equal(cropped.affine[:3, 3], (volume.affine @ [2, 3, 4, 1])[:3])
    data = preprocess_case(case, roi, with_label=False)
    probabilities = np.zeros((3, *data["image"].shape), dtype=np.float32)
    probabilities[2] = 1
    native = native_argmax(
        native_probabilities(probabilities, data["affine"], volume.shape, volume.affine, workers=1)
    )
    expected = np.zeros(volume.shape, np.uint8)
    expected[2:6, 3:8, 4:9] = 2
    np.testing.assert_array_equal(native, expected)
    # A reference mass outside the crop remains a false negative on the full grid.
    truth = np.zeros_like(expected)
    truth[0, 0, 0] = 2
    assert not np.any((truth == 2) & (native == 2))
    assert _pipeline_identity(roi) != _pipeline_identity(config)
    with open(roi.roi_manifest, "a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="changed"):
        _pipeline_identity(roi)


def test_bbox_millimeter_margin_and_empty_fallback():
    prediction = np.zeros((20, 30, 40), np.uint8)
    assert predicted_bbox(prediction, np.array([1.0, 2.0, 4.0]), 4) == (
        [[0, 20], [0, 30], [0, 40]],
        True,
    )
    prediction[10, 15, 20] = 1
    assert predicted_bbox(prediction, np.array([1.0, 2.0, 4.0]), 4) == (
        [[6, 15], [13, 18], [19, 22]],
        False,
    )


@pytest.mark.parametrize(
    "bounds", [[[0, 9], [0, 10], [0, 12]], [[-1, 2], [0, 10], [0, 12]], [[0, 0], [0, 10], [0, 12]]]
)
def test_roi_bounds_fail_closed(tmp_path, bounds):
    _, volume, case, config = example(tmp_path)
    with pytest.raises(ValueError, match="bounds"):
        crop_image(volume, case, roi_config(tmp_path, case, config, bounds))


def test_roi_manifest_builder_reads_predictions_and_images_never_reference_labels(
    tmp_path, monkeypatch
):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "roi_builder", Path(__file__).resolve().parents[1] / "scripts/build_medical_roi_manifest.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    _, volume, case, _ = example(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    splits = tmp_path / "split.json"
    splits.write_text(json.dumps({"train": ["case"], "val": [], "test": ["never-open"]}))
    monkeypatch.setattr(
        builder,
        "load_manifest",
        lambda *_a, **_k: {
            "cases": [
                case,
                {"case_id": "never-open", "image": "/do-not-read", "label": "/do-not-read"},
            ]
        },
    )
    monkeypatch.setattr(builder, "validate_splits", lambda *_: None)
    predictions = tmp_path / "predictions"
    predictions.mkdir()
    prediction = np.zeros(volume.shape, np.uint8)
    prediction[3:5, 4:6, 5:7] = 1
    image = nib.Nifti1Image(prediction, volume.affine)
    image.header.set_xyzt_units("mm")
    nib.save(image, predictions / "case.nii.gz")
    provenance = {
        "initialization": "scratch",
        "training_prediction_policy": "in_sample_exploratory",
        "prediction_case_ids": ["case"],
    }
    for key in ("checkpoint", "binding", "resolved_config"):
        path = tmp_path / key
        path.write_text("frozen")
        provenance[key] = str(path)
        provenance[f"{key}_sha256"] = builder.sha256_file(path)
    source = tmp_path / "provenance.json"
    source.write_text(json.dumps(provenance))
    output = tmp_path / "roi.json"
    result = builder.build(manifest, splits, predictions, source, 0, output)
    assert result["cases"] == 1 and result["fallback_cases"] == 0
    saved = json.loads(output.read_text())
    assert set(saved["cases"]) == {"case"}
    assert saved["cases"]["case"]["bbox_xyz"] == [[3, 5], [4, 6], [5, 7]]
    assert saved["reference_labels_used"] is False


def test_localizer_progress_can_advance_past_the_first_case(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "localizer_progress_test", scripts / "predict_medical_localizer.py"
    )
    localizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(localizer)
    for count in (1, 2, 239):
        localizer.write_progress(
            tmp_path,
            {"completed_cases": count, "status": "completed" if count == 239 else "running"},
        )
        assert json.loads((tmp_path / "progress.json").read_text())["completed_cases"] == count
    assert json.loads((tmp_path / "progress.json").read_text())["status"] == "completed"
