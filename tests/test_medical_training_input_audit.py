"""Train-only crop and physical resampling diagnostics."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from segmentary.medical.data import audit_task07, make_splits
from segmentary.medical.geometry import sha256_file
from segmentary.medical.torch_config import TorchConfig

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_medical_training_inputs.py"
_SPEC = importlib.util.spec_from_file_location("training_input_audit_test", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
auditor = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(auditor)


def test_training_resolution_never_reads_evaluation_payloads(monkeypatch):
    monkeypatch.setattr(auditor, "validate_splits", lambda *args: None)
    cases = [
        {"case_id": name, "annotation_status": "labeled", "label": f"/{name}.nii.gz"}
        for name in ["train", "validation", "heldout"]
    ]
    monkeypatch.setattr(
        auditor, "sha256_file", lambda *_: pytest.fail("Metadata selection read a payload")
    )
    result = auditor.training_cases(
        {"cases": cases}, {"train": ["train"], "val": ["validation"], "test": ["heldout"]}
    )
    assert result == [cases[0]]


def test_mass_resampling_tracks_disappearing_component_even_when_case_stays_positive(tmp_path):
    values = np.zeros((7, 7, 7), dtype=np.uint8)
    values[1, 1, 1] = 2
    values[4:6, 4:6, 4:6] = 2
    path = tmp_path / "label.nii.gz"
    image = nib.Nifti1Image(values, np.eye(4))
    image.header.set_xyzt_units("mm")
    image.set_qform(np.eye(4), code=1)
    image.set_sform(np.eye(4), code=1)
    nib.save(image, path)
    sampled = values[::2, ::2, ::2].transpose(2, 1, 0)
    result = auditor.mass_resampling(
        {"label": str(path), "label_sha256": sha256_file(path)},
        {"label": sampled, "affine": np.diag([2.0, 2.0, 2.0, 1.0])},
    )
    assert result["native_components"] == 2
    assert result["resampled_components"] == 1
    assert result["vanished_native_components"] == 1
    assert result["native_mass_mm3"] == 9
    assert result["resampled_mass_mm3"] == pytest.approx(8)
    assert result["native_component_resampled_mm3"] == pytest.approx([0, 8])
    with pytest.raises(ValueError, match="differs"):
        auditor.mass_resampling(
            {"label": str(path), "label_sha256": sha256_file(path)},
            {"label": np.zeros_like(sampled), "affine": np.diag([2.0, 2.0, 2.0, 1.0])},
        )


def test_crop_summary_distinguishes_selected_center_from_actual_contents(tmp_path):
    label = np.zeros((8, 8, 8), dtype=np.uint8)
    label[2:6, 2:6, 2:6] = 1
    label[3:5, 3:5, 3:5] = 2
    data = {"image": np.zeros_like(label, dtype=np.float32), "label": label}
    config = TorchConfig(
        workspace=str(tmp_path),
        patch_size=(8, 8, 8),
        augment=False,
        foreground_probability=None,
        class_center_weights=(1, 0, 0),
    )
    report = auditor.crop_summary(data, config, 5, 12)
    assert report["selected_centers"] == {"background": 5}
    # Whole-image patches contain the mass even with a background center.
    assert report["crop_composition"] == {"mass_present": 5}
    assert report["final_label_voxels"]["2"] == 40
    assert report["rotation_applied"] == 0
    assert report["intensity_scale_applied"] == 0
    assert report["crop_padding_voxels_before_augmentation"] == 0


def test_audit_refuses_empty_partial_and_duplicate_arms(tmp_path, monkeypatch):
    monkeypatch.setattr(auditor, "validate_splits", lambda *args: None)
    with pytest.raises(ValueError, match="fully labeled"):
        auditor.training_cases({"cases": []}, {"train": []})
    with pytest.raises(ValueError, match="fully labeled"):
        auditor.training_cases(
            {"cases": [{"case_id": "partial", "annotation_status": "organ_only", "label": "x"}]},
            {"train": ["partial"]},
        )
    cfg = TorchConfig(workspace=str(tmp_path / "run"), cache_root=str(tmp_path / "cache"))
    monkeypatch.setattr(auditor, "_config", lambda *_: cfg)
    monkeypatch.setattr(auditor, "load_manifest", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(auditor, "training_cases", lambda *_: [{}])
    splits = tmp_path / "splits.json"
    splits.write_text("{}")
    campaign = tmp_path / "campaign.json"
    campaign.write_text(
        json.dumps(
            {
                "manifest": "metadata.json",
                "splits": str(splits),
                "runs": [{"id": "same", "config": "a"}, {"id": "same", "config": "b"}],
            }
        )
    )
    with pytest.raises(ValueError, match="unique"):
        auditor.audit(campaign, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_aggregate_crop_mass_fraction_is_weighted_by_voxels():
    rows = []
    for samples, mass in [(2, 5), (1, 10)]:
        rows.append(
            {
                "samples": samples,
                "requested_centers": {"uniform_volume": samples},
                "selected_centers": {"uniform_volume": samples},
                "crop_composition": {"mass_present": 1},
                "final_label_voxels": {"0": samples * 10 - mass, "1": 0, "2": mass},
                "crop_padding_voxels_before_augmentation": 0,
                "center_fallbacks": 0,
                "rotation_applied": 0,
                "intensity_scale_applied": 0,
                "wall_seconds": 1,
            }
        )
    result = auditor._aggregate_crops(rows, 10)
    assert result["samples"] == 3
    assert result["mean_mass_voxel_fraction"] == pytest.approx(0.5)
    assert result["mass_containing_patch_fraction"] == pytest.approx(2 / 3)


def test_full_audit_succeeds_with_evaluation_payloads_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(auditor, "execution_provenance", lambda *_: {"source_clean": True})
    dataset = tmp_path / "Task07"
    training = []
    for i in range(3):
        entry = {}
        for kind, folder in [("image", "imagesTr"), ("label", "labelsTr")]:
            relative = f"{folder}/case_{i}.nii.gz"
            path = dataset / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            values = np.zeros((8, 8, 8), dtype=np.uint8)
            values[2:6, 2:6, 2:6] = 1
            values[3:5, 3:5, 3:5] = 2
            if kind == "image":
                values = values.astype(np.float32) * 20 + i
            volume = nib.Nifti1Image(values, np.eye(4))
            volume.header.set_xyzt_units("mm")
            volume.set_qform(np.eye(4), code=1)
            volume.set_sform(np.eye(4), code=1)
            nib.save(volume, path)
            entry[kind] = relative
        training.append(entry)
    (dataset / "dataset.json").write_text(
        json.dumps(
            {
                "training": training,
                "test": [],
                "numTraining": 3,
                "numTest": 0,
                "labels": {"0": "background", "1": "pancreas", "2": "cancer"},
            }
        )
    )
    manifest_path, splits_path = tmp_path / "manifest.json", tmp_path / "splits.json"
    manifest = audit_task07(dataset, manifest_path)
    splits = make_splits(manifest_path, splits_path, train_fraction=1 / 3, val_fraction=1 / 3)
    for case in manifest["cases"]:
        if case["case_id"] in splits["val"] + splits["test"]:
            Path(case["image"]).unlink()
            Path(case["label"]).unlink()
    config_path = tmp_path / "recipe.json"
    config = TorchConfig(
        workspace=str(tmp_path / "unused-run"),
        cache_root=str(tmp_path / "cache"),
        patch_size=(8, 8, 8),
        spacing_mm=(1, 1, 1),
        augment=False,
    )
    config_path.write_text(json.dumps(dataclasses.asdict(config)))
    campaign_path = tmp_path / "campaign.json"
    campaign_path.write_text(
        json.dumps(
            {
                "campaign_id": "audit-test",
                "source_commit": "a" * 40,
                "manifest": str(manifest_path),
                "splits": str(splits_path),
                "runs": [{"id": "control", "config": str(config_path)}],
            }
        )
    )
    output = tmp_path / "report"
    report = auditor.audit(campaign_path, output, samples_per_case=2)
    assert report["partition"] == "train"
    assert report["training_cases"] == 1
    assert report["resampling"]["vanished_native_components"] == 0
    assert report["arms"]["control"]["crop_statistics"]["samples"] == 2
    published = (output / "report.json").read_text()
    assert str(tmp_path) not in published
    assert all(case["case_id"] not in published for case in manifest["cases"])
    assert not (tmp_path / "unused-run").exists()
    with pytest.raises(FileExistsError):
        auditor.audit(campaign_path, output)


def test_execution_provenance_rejects_wrong_checkout_commit_dirty_tree_and_interpreter(monkeypatch):
    root = _SCRIPT.parents[1]
    campaign = {"source_root": str(root), "source_commit": "a" * 40}
    config = TorchConfig(workspace="/unused", backend_python=auditor.sys.executable)
    with pytest.raises(ValueError, match="source checkout"):
        auditor.execution_provenance({**campaign, "source_root": "/wrong"}, [("a", config)])
    for commit, status in [("b" * 40, ""), ("a" * 40, " M torch_data.py")]:
        answers = iter([commit, status])
        monkeypatch.setattr(
            auditor.subprocess, "check_output", lambda *_a, answers=answers, **_k: next(answers)
        )
        with pytest.raises(ValueError, match="clean campaign source commit"):
            auditor.execution_provenance(campaign, [("a", config)])
    answers = iter(["a" * 40, ""])
    monkeypatch.setattr(auditor.subprocess, "check_output", lambda *_a, **_k: next(answers))
    with pytest.raises(ValueError, match="configured Python runtime"):
        auditor.execution_provenance(
            campaign, [("a", dataclasses.replace(config, backend_python="/another/env/bin/python"))]
        )
