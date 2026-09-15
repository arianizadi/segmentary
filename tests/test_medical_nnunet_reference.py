"""Reference cache reuse preserves data identity and cannot import weights/test data."""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from segmentary.medical import backend as b
from segmentary.medical import nnunet_reference as reference


def _freeze(config):
    b._atomic_json(
        config.root / "plan-binding.json",
        {
            "binding_digest": b._digest(b._json(config.root / "binding.json")),
            "runtime": {
                "python": "historical reference environment",
                "packages": {"nnunetv2": "2.8.1", "torch": "2.11.0"},
            },
            "files": {
                path.relative_to(config.preprocessed).as_posix(): b._sha(path)
                for path in config.preprocessed.rglob("*")
                if path.is_file()
            },
        },
    )


@pytest.fixture
def prepared_reference(tmp_path):
    original = b.NNUNetConfig(str(tmp_path / "original"))
    target = b.NNUNetConfig(
        str(tmp_path / "transfer"), reference_workspace=str(original.root), architecture="plainconv"
    )
    manifest = tmp_path / "manifest.json"
    splits = tmp_path / "splits.json"
    b._atomic_json(
        manifest,
        {
            "cases": [
                {"case_id": name, "image": f"/unavailable/{name}.nii.gz"}
                for name in ("train_a", "val_b", "test_c")
            ]
        },
    )
    split = {"train": ["train_a"], "val": ["val_b"], "test": ["test_c"]}
    b._atomic_json(splits, split)
    dataset = {
        "channel_names": {"0": "CT"},
        "labels": {"background": 0, "pancreas": 1, "mass": 2},
        "numTraining": 2,
        "file_ending": ".nii.gz",
        "overwrite_image_reader_writer": "NibabelIO",
    }
    for config in (original, target):
        config.preprocessed.mkdir(parents=True)
        b._atomic_json(
            config.preprocessed / "splits_final.json",
            [{"train": split["train"], "val": split["val"]}],
        )
        raw = config.root / "nnUNet_raw" / config.dataset
        raw.mkdir(parents=True)
        b._atomic_json(raw / "dataset.json", dataset)
        b._atomic_json(
            config.root / "binding.json",
            {
                "schema_version": 1,
                "config": dataclasses.asdict(config),
                "manifest_path": str(manifest),
                "splits_path": str(splits),
                "manifest_sha256": b._sha(manifest),
                "splits_sha256": b._sha(splits),
                "manifest_fingerprint": "fixture-manifest",
                "split_fingerprint": "fixture-split",
                "ontology": dataset["labels"],
                "code": {"backend.py": "old-source" if config is original else "new-source"},
                "planning_scope": "train_and_val_only",
                "development_cases": ["train_a", "val_b"],
                "held_out_cases": ["test_c"],
            },
        )
    plan = {
        "dataset_name": original.dataset,
        "plans_name": original.plans,
        "experiment_planner_used": "nnUNetPlannerResEncL",
        "image_reader_writer": "NibabelIO",
        "label_manager": "LabelManager",
        "transpose_forward": [0, 1, 2],
        "transpose_backward": [0, 1, 2],
        "foreground_intensity_properties_per_channel": {"0": {"mean": 79.7, "std": 71.2}},
        "configurations": {
            "3d_fullres": {
                "architecture": {
                    "network_class_name": "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet"
                },
                "preprocessor_name": "DefaultPreprocessor",
                "data_identifier": "nnUNetPlans_3d_fullres",
                "normalization_schemes": ["CTNormalization"],
                "spacing": [2.5, 0.8125, 0.8125],
                "patch_size": [56, 320, 256],
                "batch_size": 2,
            }
        },
    }
    b._atomic_json(original.preprocessed / f"{original.plans}.json", plan)
    b._atomic_json(original.preprocessed / "dataset.json", dataset)
    b._atomic_json(original.preprocessed / "dataset_fingerprint.json", {"fixture": "fingerprint"})
    data = original.preprocessed / "nnUNetPlans_3d_fullres"
    data.mkdir()
    gt = original.preprocessed / "gt_segmentations"
    gt.mkdir()
    for name in ("train_a", "val_b"):
        for suffix in (".b2nd", "_seg.b2nd", ".pkl"):
            (data / f"{name}{suffix}").write_bytes(f"{name}{suffix}".encode())
        (gt / f"{name}.nii.gz").write_bytes(b"native development segmentation")
    # Active results are outside the imported cache, and deliberately invalid
    # checkpoint bytes must never be interpreted or copied.
    original.fold_folder.mkdir(parents=True)
    (original.fold_folder / "checkpoint_latest.pth").write_bytes(b"never read weights")
    _freeze(original)
    return original, target


def test_import_copies_exact_cache_with_independent_writable_plan(prepared_reference):
    original, target = prepared_reference
    record = b._json(original.root / "plan-binding.json")
    report = reference.import_reference(target)
    assert report["files"] == 12
    assert report["development_cases"] == 2
    assert report["test_cases_excluded"] == 1
    assert report["weights_imported"] is False
    assert report["source_runtime"] == record["runtime"]
    assert report["source_runtime_sha256"] == b._digest(record["runtime"])
    assert report["source_cache_index_sha256"] == b._digest(record["files"])
    assert report["geometry"]["spacing"] == [2.5, 0.8125, 0.8125]
    assert reference._inventory(target.preprocessed) == set(record["files"])
    assert not (target.root / "nnUNet_results").exists()
    for relative, digest in record["files"].items():
        copied, source = target.preprocessed / relative, original.preprocessed / relative
        assert b._sha(copied) == digest
        assert not copied.is_symlink()
        assert not copied.samefile(source)
    (target.preprocessed / f"{target.plans}.json").write_text("changed architecture")
    assert b._sha(original.preprocessed / f"{original.plans}.json") == report["source_plan_sha256"]
    data_file = "nnUNetPlans_3d_fullres/train_a.b2nd"
    (original.preprocessed / data_file).write_bytes(b"source later changed")
    assert b._sha(target.preprocessed / data_file) == record["files"][data_file]


@pytest.mark.parametrize("extra", ["test_c.b2nd", "checkpoint_latest.pth"])
def test_rejects_even_indexed_unknown_payload_without_reading_it(
    prepared_reference, monkeypatch, extra
):
    original, target = prepared_reference
    unsafe = original.preprocessed / "nnUNetPlans_3d_fullres" / extra
    unsafe.write_bytes(b"must not inspect held-out or weight payload")
    _freeze(original)
    original_sha = b._sha

    def guarded_sha(path):
        assert Path(path) != unsafe, "Held-out/checkpoint payload must not be read"
        return original_sha(path)

    monkeypatch.setattr(b, "_sha", guarded_sha)
    with pytest.raises(ValueError, match="exactly the development"):
        reference.import_reference(target)
    assert reference._inventory(target.preprocessed) == {"splits_final.json"}


@pytest.mark.parametrize("change", ["corrupt", "extra", "missing", "symlink", "escape"])
def test_reference_cache_corruption_fails_before_committing(prepared_reference, change):
    original, target = prepared_reference
    path = original.preprocessed / "nnUNetPlans_3d_fullres" / "train_a.b2nd"
    if change == "corrupt":
        path.write_bytes(b"corrupt")
    elif change == "extra":
        (original.preprocessed / "extra").write_bytes(b"unknown")
    elif change == "missing":
        path.unlink()
    elif change == "symlink":
        moved = original.root / "moved-data"
        path.replace(moved)
        path.symlink_to(moved)
    else:
        record = b._json(original.root / "plan-binding.json")
        record["files"]["../checkpoint.pth"] = "unknown"
        b._atomic_json(original.root / "plan-binding.json", record)
    with pytest.raises(ValueError):
        reference.import_reference(target)
    assert reference._inventory(target.preprocessed) == {"splits_final.json"}
    assert not list(target.root.glob(".reference-import-*"))


@pytest.mark.parametrize("change", ["version", "model", "planner", "normalization", "split"])
def test_rejects_frozen_but_incompatible_reference(prepared_reference, change):
    original, target = prepared_reference
    plan_path = original.preprocessed / f"{original.plans}.json"
    plan = b._json(plan_path)
    if change == "version":
        record = b._json(original.root / "plan-binding.json")
        record["runtime"]["packages"]["nnunetv2"] = "future"
        b._atomic_json(original.root / "plan-binding.json", record)
    elif change == "split":
        b._atomic_json(
            original.preprocessed / "splits_final.json",
            [{"train": ["train_a", "test_c"], "val": ["val_b"]}],
        )
        _freeze(original)
    else:
        if change == "model":
            plan["configurations"]["3d_fullres"]["architecture"]["network_class_name"] = "other.Net"
        elif change == "planner":
            plan["experiment_planner_used"] = "OtherPlanner"
        else:
            plan["configurations"]["3d_fullres"]["normalization_schemes"] = ["ZScore"]
        b._atomic_json(plan_path, plan)
        _freeze(original)
    with pytest.raises(ValueError):
        reference.import_reference(target)


@pytest.mark.parametrize(
    "key", ["manifest_sha256", "splits_sha256", "ontology", "development_cases"]
)
def test_reference_and_target_data_identity_must_match(prepared_reference, key):
    _, target = prepared_reference
    binding = b._json(target.root / "binding.json")
    binding[key] = "mismatch"
    b._atomic_json(target.root / "binding.json", binding)
    with pytest.raises(ValueError, match="differ"):
        reference.import_reference(target)


def test_reference_binding_digest_must_match(prepared_reference):
    original, target = prepared_reference
    path = original.root / "binding.json"
    binding = b._json(path)
    binding["config"]["resenc"] = "M"
    b._atomic_json(path, binding)
    with pytest.raises(ValueError, match="plan binding"):
        reference.import_reference(target)


@pytest.mark.parametrize("copy_problem", ["hardlink", "corrupt", "metadata_edit"])
def test_copy_cannot_alias_corrupt_or_import_changed_binding(
    prepared_reference, monkeypatch, copy_problem
):
    original, target = prepared_reference
    normal_copy = reference._independent_copy

    def altered_copy(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if copy_problem == "hardlink":
            os.link(source, destination)
        elif copy_problem == "corrupt":
            destination.write_bytes(b"bad copy")
        else:
            normal_copy(source, destination)
            path = original.root / "binding.json"
            path.write_text(path.read_text() + " ")

    monkeypatch.setattr(reference, "_independent_copy", altered_copy)
    with pytest.raises(ValueError):
        reference.import_reference(target)
    assert reference._inventory(target.preprocessed) == {"splits_final.json"}


def test_no_reuse_of_an_already_imported_cache(prepared_reference):
    _, target = prepared_reference
    reference.import_reference(target)
    with pytest.raises(FileExistsError, match="fresh"):
        reference.import_reference(target)


def test_raw_ontology_is_checked(prepared_reference):
    original, target = prepared_reference
    path = original.root / "nnUNet_raw" / original.dataset / "dataset.json"
    metadata = json.loads(path.read_text())
    metadata["labels"]["mass"] = 7
    b._atomic_json(path, metadata)
    with pytest.raises(ValueError, match="ontology"):
        reference.import_reference(target)
