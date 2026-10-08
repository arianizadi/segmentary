"""LiTS (MSD Task03) and KiTS23 run through audit, split, CV, nnU-Net prepare and scoring.

Task07 artifacts must keep their exact bytes: the first test regenerates a
Task07 manifest, frozen split and CV manifest with the base-commit sources and
with the current ones, and compares the files byte for byte.
"""

from __future__ import annotations

import csv
import importlib
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest

nib = pytest.importorskip("nibabel")

from segmentary.medical import backend as b  # noqa: E402
from segmentary.medical import cv_splits as current_cv  # noqa: E402
from segmentary.medical import data as current_data  # noqa: E402
from segmentary.medical.cli import main  # noqa: E402
from segmentary.medical.cv_splits import make_cv_splits  # noqa: E402
from segmentary.medical.data import (  # noqa: E402
    _group_assignments,
    atomic_write_json,
    audit_kits23,
    audit_msd,
    audit_task07,
    fingerprint,
    lesion_volume_ml,
    load_manifest,
    make_splits,
    subset_manifest,
    validate_splits,
)
from segmentary.medical.dataset_profiles import (  # noqa: E402
    KIDNEY,
    LIVER,
    PANCREAS,
    profile_for_ontology,
)
from segmentary.medical.evaluation import evaluate_predictions, paired_comparison  # noqa: E402
from segmentary.medical.geometry import (  # noqa: E402
    MedicalDataError,
    geometry_policy,
    sha256_file,
    validate_nifti,
)

BASE_COMMIT = "5e8c132b2b8d3b511fc8ad180b6024e68f1430f0"
AFFINE = np.diag([0.75, 1.25, 3.0, 1.0])
RELAXED = {"qform_sform_atol_mm": 1e-3, "unknown_spatial_units_as_mm": True}


def _nifti(
    path: Path,
    data: np.ndarray,
    *,
    units: str | None = "mm",
    qform_shift: float = 0.0,
    description: str = "",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    volume = nib.Nifti1Image(data, AFFINE)
    if units is not None:
        volume.header.set_xyzt_units(units)
    qform = AFFINE.copy()
    qform[0, 3] += qform_shift  # float32 qform rounding as in MSD Task03 labels
    volume.set_qform(qform, code=1)
    volume.set_sform(AFFINE, code=1)
    if description:
        volume.header["descrip"] = description.encode()
    nib.save(volume, path)
    return path


def _mask(index: int, lesion_voxels: int, *, host: int = 1, extra: int | None = None) -> np.ndarray:
    mask = np.zeros((4, 5, 6), dtype=np.uint8)
    mask[1:3, 1:4, 1:5] = host
    flat = mask.reshape(-1)
    for voxel in range(lesion_voxels):
        flat[30 + voxel] = 2
    if extra is not None:
        flat[100] = extra
    return mask


def _ct(index: int) -> np.ndarray:
    return np.arange(120, dtype=np.float32).reshape(4, 5, 6) + index * 100 - 1000


def _msd(
    tmp_path: Path,
    *,
    name: str,
    labels: dict[str, str],
    labeled: int,
    unlabeled: int,
    prefix: str,
    lesion: list[int],
    qform_shift_label: int | None = None,
) -> Path:
    """An MSD-layout release; case 5 duplicates case 6 bytes, test 0 shares case 3 voxels."""
    root = tmp_path / name
    training, testing = [], []
    for index in range(labeled + unlabeled):
        case = f"{prefix}_{index}"
        folder = "imagesTr" if index < labeled else "imagesTs"
        image = f"{folder}/{case}.nii.gz"
        ct = _ct(6 if index == 5 else index)
        if index == labeled:
            # Same decoded voxels as labeled case 3, with a different header.
            _nifti(root / image, _ct(3), description="re-exported")
        else:
            _nifti(root / image, ct)
        if index < labeled:
            label = f"labelsTr/{case}.nii.gz"
            shift = 5e-4 if index == qform_shift_label else 0.0
            _nifti(root / label, _mask(index, lesion[index]), qform_shift=shift)
            training.append({"image": f"./{image}", "label": f"./{label}"})
        else:
            testing.append(f"./{image}")
    (root / "dataset.json").write_text(
        json.dumps(
            {
                "numTraining": labeled,
                "numTest": unlabeled,
                "labels": labels,
                "training": training,
                "test": testing,
            }
        )
    )
    return root


def _task07(tmp_path: Path) -> Path:
    return _msd(
        tmp_path,
        name="Task07_Pancreas",
        labels={"0": "background", "1": "pancreas", "2": "cancer"},
        labeled=24,
        unlabeled=3,
        prefix="pancreas",
        lesion=[1 + (index * 7) % 13 for index in range(24)],
    )


def _lits(tmp_path: Path) -> Path:
    # Cases 0, 4 and 9 are tumor-free; label 2 is the lesion.
    lesion = [0 if index in (0, 4, 9) else 1 + (index * 5) % 11 for index in range(25)]
    return _msd(
        tmp_path,
        name="Task03_Liver",
        labels={"0": "background", "1": "liver", "2": "cancer"},
        labeled=25,
        unlabeled=4,
        prefix="liver",
        lesion=lesion,
        qform_shift_label=7,
    )


def _links(tmp_path: Path, *pairs: tuple[str, str]) -> Path:
    path = tmp_path / f"links-{uuid.uuid4().hex}.json"
    path.write_text(
        json.dumps(
            {"links": [{"cases": list(pair), "evidence": "r=0.99999, +7 HU"} for pair in pairs]}
        )
    )
    return path


def _base_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    repository = Path(__file__).resolve().parents[1]
    package = f"segmentary_base_{uuid.uuid4().hex}"
    folder = tmp_path / "base-sources" / package
    folder.mkdir(parents=True)
    for name in ("data", "geometry", "cv_splits"):
        try:
            completed = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "show",
                    f"{BASE_COMMIT}:src/segmentary/medical/{name}.py",
                ],
                capture_output=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            pytest.skip("git is unavailable; base-commit sources cannot be read")
        if completed.returncode:
            pytest.skip("base-commit sources are not in this checkout's history")
        (folder / f"{name}.py").write_bytes(completed.stdout)
    (folder / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(folder.parent))
    return {name: importlib.import_module(f"{package}.{name}") for name in ("data", "cv_splits")}


@pytest.mark.parametrize("grouped", [False, True])
def test_task07_artifacts_are_byte_identical_to_the_base_commit(tmp_path, monkeypatch, grouped):
    base = _base_sources(tmp_path, monkeypatch)
    root = _task07(tmp_path)
    groups = None
    if grouped:
        ids = [f"pancreas_{index}" for index in range(27)]
        groups = tmp_path / "groups.json"
        groups.write_text(json.dumps({key: f"patient-{int(key[9:]) // 2}" for key in ids}))
    outputs = {}
    for label, data, cv in (
        ("base", base["data"], base["cv_splits"]),
        ("new", current_data, current_cv),
    ):
        folder = tmp_path / label
        manifest, splits, folds = folder / "m.json", folder / "s.json", folder / "cv.json"
        data.audit_task07(root, manifest, groups_path=groups)
        data.make_splits(manifest, splits, seed=0)
        cv.make_cv_splits(manifest, splits, folds, folds=5, seed=0)
        outputs[label] = [path.read_bytes() for path in (manifest, splits, folds)]
    assert outputs["new"] == outputs["base"]
    cv = json.loads(outputs["new"][2])
    assert cv["assignment"]["method"] == "mass_volume_stratified_blocks"
    split = json.loads(outputs["new"][1])
    # Grouped duplicates are exercised: some group holds more than one case.
    assert "assignment" not in split
    assert sum(len(split[name]) for name in ("train", "val", "test")) > sum(
        split["group_counts"].values()
    )
    # The general MSD audit with the Task07 profile is the same artifact.
    again = tmp_path / "again.json"
    audit_msd(root, again, profile="task07", groups_path=groups)
    assert again.read_bytes() == outputs["new"][0]


def test_profiles_resolve_from_the_exact_manifest_ontology():
    assert profile_for_ontology({"background": 0, "pancreas": 1, "mass": 2}) is PANCREAS
    assert profile_for_ontology({"background": 0, "liver": 1, "tumor": 2}) is LIVER
    assert profile_for_ontology({"background": 0, "kidney": 1, "tumor": 2, "cyst": 3}) is KIDNEY
    for bad in (
        {"background": 0, "liver": 1, "tumor": 3},
        {"background": 0, "liver": True, "tumor": 2},
        {"background": 0, "liver": 1},
        None,
    ):
        with pytest.raises(MedicalDataError, match="ontology"):
            profile_for_ontology(bad)
    assert KIDNEY.lesion_labels == (2,) and KIDNEY.host_labels == (1, 2, 3)
    assert KIDNEY.label_regions()[1] == ["masses", [2, 3]]


def test_geometry_relaxations_are_opt_in_bounded_and_reported(tmp_path):
    shifted = _nifti(tmp_path / "shifted.nii.gz", _mask(0, 2), qform_shift=5e-4)
    unknown = _nifti(tmp_path / "unknown.nii.gz", _ct(0), units=None)
    with pytest.raises(MedicalDataError, match="conflicting qform/sform"):
        validate_nifti(shifted, is_label=True)
    with pytest.raises(MedicalDataError, match="explicitly be mm"):
        validate_nifti(unknown)
    relaxed = validate_nifti(shifted, is_label=True, qform_sform_atol_mm=1e-3)
    (item,) = relaxed["geometry_relaxations"]
    assert item["relaxation"] == "qform_sform_tolerance"
    assert 1e-4 < item["max_abs_difference_mm"] <= 1e-3
    assert validate_nifti(unknown, unknown_units_as_mm=True)["geometry_relaxations"] == [
        {"relaxation": "unknown_spatial_units_as_mm"}
    ]
    clean = _nifti(tmp_path / "clean.nii.gz", _ct(0))
    assert "geometry_relaxations" not in validate_nifti(
        clean, qform_sform_atol_mm=1e-3, unknown_units_as_mm=True
    )
    assert geometry_policy() is None
    with pytest.raises(MedicalDataError, match="tolerance"):
        geometry_policy(qform_sform_atol_mm=2e-3)
    with pytest.raises(MedicalDataError, match="tolerance"):
        validate_nifti(shifted, qform_sform_atol_mm=1.0)
    metres = _nifti(tmp_path / "metres.nii.gz", _ct(0), units="meter")
    with pytest.raises(MedicalDataError, match="explicitly be mm"):
        validate_nifti(metres, unknown_units_as_mm=True)


def test_lits_audit_records_policy_relaxations_and_duplicate_links(tmp_path):
    root = _lits(tmp_path)
    with pytest.raises(MedicalDataError, match="conflicting qform/sform"):
        audit_msd(root, tmp_path / "strict.json", profile="lits")
    links = _links(tmp_path, ("liver_10", "liver_26"), ("liver_11", "liver_12"))
    manifest = audit_msd(
        root, tmp_path / "m.json", profile="lits", duplicate_links_path=links, geometry=RELAXED
    )
    assert manifest["dataset"] == "Task03_Liver" and manifest["ontology"] == LIVER.ontology
    assert manifest["geometry_policy"] == RELAXED
    assert manifest["audit"]["geometry_relaxation_files"] == {"qform_sform_tolerance": 1}
    cases = {case["case_id"]: case for case in manifest["cases"]}
    assert cases["liver_7"]["geometry_relaxations"]["label"][0]["relaxation"] == (
        "qform_sform_tolerance"
    )
    assert cases["liver_8"]["geometry_relaxations"] == {"image": [], "label": []}
    assert cases["liver_25"]["geometry_relaxations"] == {"image": [], "label": None}
    assert cases["liver_0"]["label_counts"] == {"0": 96, "1": 24}
    assert cases["liver_0"]["patient_id"] == "Task03_Liver:liver_0"
    assert [group["cases"] for group in manifest["duplicate_links"]["groups"]] == [
        ["liver_10", "liver_26"],
        ["liver_11", "liver_12"],
    ]
    assert manifest["duplicate_links"]["source_sha256"] == sha256_file(links)
    groups = _group_assignments(cases)
    assert groups["liver_10"] == groups["liver_26"] and groups["liver_11"] == groups["liver_12"]
    assert groups["liver_3"] == groups["liver_25"]  # same voxels, different header
    assert groups["liver_5"] == groups["liver_6"]  # identical bytes
    assert load_manifest(tmp_path / "m.json", verify_files=True)["fingerprint"]


@pytest.mark.parametrize(
    "fault, message",
    [
        ("orphan_group", "duplicate_links record"),
        ("unrecorded_group", "not a recorded link"),
        ("missing_member", "carry their group"),
        ("relaxation_without_policy", "need a manifest policy"),
        ("loose_policy", "tolerance"),
        ("relaxation_beyond_tolerance", "exceeds its policy"),
        ("units_relaxation_without_policy", "exceeds its policy"),
        ("lesion_label_in_organ_only", "contradicts"),
    ],
)
def test_manifest_validation_rejects_inconsistent_links_and_policies(tmp_path, fault, message):
    links = _links(tmp_path, ("liver_10", "liver_11"))
    manifest = audit_msd(
        _lits(tmp_path),
        tmp_path / "m.json",
        profile="lits",
        duplicate_links_path=links,
        geometry=RELAXED,
    )
    cases = {case["case_id"]: case for case in manifest["cases"]}
    if fault == "orphan_group":
        del manifest["duplicate_links"]
    elif fault == "unrecorded_group":
        cases["liver_1"]["duplicate_group"] = "duplicate:liver_1+liver_2"
    elif fault == "missing_member":
        del cases["liver_11"]["duplicate_group"]
    elif fault == "relaxation_without_policy":
        del manifest["geometry_policy"]
    elif fault == "loose_policy":
        manifest["geometry_policy"]["qform_sform_atol_mm"] = 0.01
    elif fault == "relaxation_beyond_tolerance":
        cases["liver_7"]["geometry_relaxations"]["label"][0]["max_abs_difference_mm"] = 0.005
    elif fault == "units_relaxation_without_policy":
        manifest["geometry_policy"]["unknown_spatial_units_as_mm"] = False
        cases["liver_8"]["geometry_relaxations"]["image"].append(
            {"relaxation": "unknown_spatial_units_as_mm"}
        )
    else:
        cases["liver_1"]["annotation_status"] = "organ_only"
    manifest["fingerprint"] = fingerprint(manifest)
    path = tmp_path / "tampered.json"
    atomic_write_json(path, manifest)
    with pytest.raises(MedicalDataError, match=message):
        load_manifest(path)


def test_variant_b_split_and_cv_are_stratified_grouped_and_deterministic(tmp_path):
    links = _links(tmp_path, ("liver_11", "liver_12"), ("liver_10", "liver_26"))
    manifest_path = tmp_path / "m.json"
    manifest = audit_msd(
        _lits(tmp_path),
        manifest_path,
        profile="lits",
        duplicate_links_path=links,
        geometry=RELAXED,
    )
    splits_path = tmp_path / "splits.json"
    splits = make_splits(manifest_path, splits_path, 0.64, 0.16, seed=0, stratify=True)
    again = make_splits(manifest_path, tmp_path / "again.json", 0.64, 0.16, seed=0, stratify=True)
    assert splits == again and splits_path.read_bytes() == (tmp_path / "again.json").read_bytes()
    assert splits["assignment"] == {
        "unit": "connected patient/duplicate group",
        "method": "tumor_volume_stratified_blocks",
        "stratification_variable": "summed annotated tumor volume in mL (label 2 voxels x voxel volume)",
        "block_size": 6,
    }
    # 23 groups: liver_5/6 (bytes) and liver_11/12 (link) are each one group.
    assert splits["group_counts"] == {"train": 15, "val": 4, "test": 4}
    assert any({"liver_11", "liver_12"} <= set(splits[name]) for name in ("train", "val", "test"))
    cases = {case["case_id"]: case for case in manifest["cases"]}
    volume = {key: lesion_volume_ml(case, (2,)) for key, case in cases.items() if case["label"]}
    for name in ("val", "test"):
        assert min(volume[key] for key in splits[name]) < np.median(list(volume.values()))
        assert max(volume[key] for key in splits[name]) > np.median(list(volume.values()))
    assert "liver_26" in splits["excluded_unlabeled_or_partial"]
    cv = make_cv_splits(manifest_path, splits_path, tmp_path / "cv.json", folds=5, seed=0)
    assert cv["assignment"]["method"] == "tumor_volume_stratified_blocks"
    assert cv["folds"][0]["val"] == splits["val"]
    development = set(splits["train"] + splits["val"])
    assert set().union(*(set(fold["val"]) for fold in cv["folds"])) == development
    assert all(not set(fold["train"]) & set(splits["test"]) for fold in cv["folds"])
    # A split separating a confirmed duplicate pair is rejected as leakage.
    leaked = json.loads(splits_path.read_text())
    home = (
        "train"
        if "liver_11" in leaked["train"]
        else "val"
        if "liver_11" in leaked["val"]
        else "test"
    )
    away = "test" if home != "test" else "train"
    leaked[home].remove("liver_12")
    leaked[away] = sorted([*leaked[away], "liver_12"])
    leaked["fingerprint"] = fingerprint(leaked)
    with pytest.raises(MedicalDataError, match="leak"):
        validate_splits(manifest, leaked)
    # Unstratified splitting is unchanged and carries no assignment record.
    assert "assignment" not in make_splits(manifest_path, tmp_path / "plain.json", seed=0)


def test_subset_keeps_only_present_duplicate_members(tmp_path):
    links = _links(tmp_path, ("liver_11", "liver_12"))
    audit_msd(
        _lits(tmp_path),
        tmp_path / "m.json",
        profile="lits",
        duplicate_links_path=links,
        geometry=RELAXED,
    )
    subset = subset_manifest(tmp_path / "m.json", tmp_path / "s.json", ["liver_11", "liver_1"])
    assert subset["duplicate_links"]["groups"] == [
        {
            "group": "duplicate:liver_11+liver_12",
            "cases": ["liver_11"],
            "evidence": ["r=0.99999, +7 HU"],
        }
    ]
    assert load_manifest(tmp_path / "s.json")["geometry_policy"] == RELAXED


def _kits(tmp_path: Path, cases: int = 12) -> Path:
    root = tmp_path / "kits23" / "dataset"
    metadata = []
    for index in range(cases):
        case = f"case_{index:05d}"
        _nifti(root / case / "imaging.nii.gz", _ct(index), units=None)
        _nifti(
            root / case / "segmentation.nii.gz",
            _mask(index, 1 + index % 5, extra=3 if index % 2 else None),
            units=None,
        )
        # Per-annotator instance files are not references and are not audited.
        _nifti(root / case / "instances" / "kidney_instance-1_annotation-1.nii.gz", _mask(0, 0))
        metadata.append({"case_id": case, "malignant": True})
    (root / "kits23.json").write_text(json.dumps(metadata))
    return root


def test_kits23_audit_reads_case_directories_with_undeclared_units(tmp_path):
    root = _kits(tmp_path)
    with pytest.raises(MedicalDataError, match="explicitly be mm"):
        audit_kits23(root, tmp_path / "strict.json")
    manifest = audit_kits23(root, tmp_path / "m.json", geometry=RELAXED)
    assert manifest["dataset"] == "KiTS23" and manifest["ontology"] == KIDNEY.ontology
    assert manifest["source_ontology"] == {
        "0": "background",
        "1": "kidney",
        "2": "tumor",
        "3": "cyst",
    }
    assert manifest["source_metadata_sha256"] == sha256_file(root / "kits23.json")
    assert manifest["audit"]["annotation_counts"] == {"labeled": 12}
    assert manifest["audit"]["geometry_relaxation_files"] == {"unknown_spatial_units_as_mm": 24}
    first = manifest["cases"][1]
    assert first["case_id"] == "case_00001" and first["label_counts"]["3"] == 1
    assert first["image"].endswith("case_00001/imaging.nii.gz")


@pytest.mark.parametrize("fault", ["extra_volume", "missing_case", "label_4", "metadata"])
def test_kits23_audit_refuses_an_inconsistent_release(tmp_path, fault):
    root = _kits(tmp_path, cases=3)
    if fault == "extra_volume":
        _nifti(root / "case_00001" / "other.nii.gz", _ct(0), units=None)
    elif fault == "missing_case":
        (root / "case_00002" / "segmentation.nii.gz").unlink()
    elif fault == "label_4":
        (root / "case_00001" / "segmentation.nii.gz").unlink()
        _nifti(root / "case_00001" / "segmentation.nii.gz", _mask(0, 1, extra=4), units=None)
    else:
        (root / "kits23.json").write_text(json.dumps([{"case_id": "case_00000"}]))
    with pytest.raises(MedicalDataError):
        audit_kits23(root, tmp_path / "m.json", geometry=RELAXED)


def _kits_development(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest = tmp_path / "m.json"
    audit_kits23(_kits(tmp_path, cases=15), manifest, geometry=RELAXED)
    splits = tmp_path / "splits.json"
    make_splits(manifest, splits, 0.64, 0.16, seed=0, stratify=True)
    cv = tmp_path / "cv.json"
    make_cv_splits(manifest, splits, cv, folds=5, seed=0)
    return manifest, splits, cv


def test_kits23_regions_prepare_for_nnunet_and_task07_regions_are_refused(tmp_path):
    manifest, splits, cv = _kits_development(tmp_path)
    regions = {
        "output_mode": "regions",
        "label_regions": KIDNEY.label_regions(),
        "regions_class_order": list(KIDNEY.nnunet_regions_class_order),
    }
    config = b.NNUNetConfig(
        str(tmp_path / "run"),
        gpu="2",
        dataset_id=723,
        dataset_name="KiTS23",
        fold=1,
        cv_splits=str(cv),
        cv_splits_sha256=sha256_file(cv),
        **regions,
    )
    result = b.prepare_dataset(manifest, splits, config)
    raw = config.root / "nnUNet_raw" / config.dataset
    dataset = json.loads((raw / "dataset.json").read_text())
    assert list(dataset["labels"]) == ["background", "kidney_and_masses", "masses", "tumor"]
    assert dataset["labels"]["masses"] == [2, 3] and dataset["regions_class_order"] == [1, 3, 2]
    binding = b._binding(config)
    assert binding["ontology"] == KIDNEY.ontology
    assert result["train_cases"] + result["val_cases"] == len(binding["development_cases"])
    labels = b.NNUNetConfig(
        str(tmp_path / "labels"), gpu="2", dataset_id=723, dataset_name="KiTS23"
    )
    b.prepare_dataset(manifest, splits, labels, dry_run=True)
    task07 = b.NNUNetConfig(str(tmp_path / "task07"), gpu="2", output_mode="regions")
    with pytest.raises(ValueError, match="reproduce label 3"):
        b.prepare_dataset(manifest, splits, task07, dry_run=True)


def test_prediction_checks_follow_the_manifest_labels_and_units(tmp_path):
    image = _nifti(tmp_path / "ct.nii.gz", _ct(0), units=None)
    prediction = _nifti(tmp_path / "pred.nii.gz", _mask(0, 2, extra=3), units=None)
    with pytest.raises(ValueError, match="invalid class values"):
        b.validate_prediction_geometry(image, prediction)
    assert b.validate_prediction_geometry(image, prediction, (0, 1, 2, 3))["shape"] == [4, 5, 6]
    with pytest.raises(ValueError, match="millimeter"):
        b._finalize_native_prediction(image, prediction, labels=(0, 1, 2, 3))
    record = b._finalize_native_prediction(
        image, prediction, labels=(0, 1, 2, 3), unknown_units_as_mm=True
    )
    assert record["header_action"].startswith("copied_source")
    assert nib.load(str(prediction)).header.get_xyzt_units()[0] == "unknown"


def test_torch_backend_refuses_a_non_pancreas_ontology(tmp_path):
    from segmentary.medical import torch_backend
    from segmentary.medical.torch_config import TorchConfig

    manifest, splits, _ = _kits_development(tmp_path)
    config = TorchConfig(str(tmp_path / "torch"), gpu="cpu")
    with pytest.raises(ValueError, match="pancreas/mass ontology only"):
        torch_backend.prepare_dataset(manifest, splits, config, dry_run=True)


def _predict(manifest: dict, folder: Path, change) -> None:
    for case in manifest["cases"]:
        reference = np.asarray(nib.load(case["label"]).dataobj)
        _nifti(folder / f"{case['case_id']}.nii.gz", change(reference.copy()), units=None)


def test_kits23_evaluation_scores_the_hierarchical_regions(tmp_path):
    manifest_path, splits_path, _ = _kits_development(tmp_path)
    manifest = load_manifest(manifest_path)
    perfect, cyst_as_tumor = tmp_path / "perfect", tmp_path / "cyst-as-tumor"
    _predict(manifest, perfect, lambda labels: labels)
    _predict(manifest, cyst_as_tumor, lambda labels: np.where(labels == 3, 2, labels))
    val = json.loads(splits_path.read_text())["val"]
    report = evaluate_predictions(manifest_path, perfect, tmp_path / "r1", case_ids=val)
    assert list(report["regions"]) == ["kidney_and_masses", "masses", "tumor"]
    assert report["protocol"]["regions"] == {
        "kidney_and_masses": [1, 2, 3],
        "masses": [2, 3],
        "tumor": [2],
    }
    assert "pancreas_include_mass" not in report["protocol"]
    assert report["protocol"]["geometry_policy"] == RELAXED
    assert all(report["regions"][name]["dice"]["mean"] == 1.0 for name in report["regions"])
    other = evaluate_predictions(manifest_path, cyst_as_tumor, tmp_path / "r2", case_ids=val)
    assert other["regions"]["masses"]["dice"]["mean"] == 1.0
    assert other["regions"]["kidney_and_masses"]["dice"]["mean"] == 1.0
    cysts = {case["case_id"] for case in manifest["cases"] if case["label_counts"].get("3")}
    with_cyst = [row for row in other["cases"] if row["case_id"] in cysts]
    assert with_cyst and all(row["metrics"]["tumor"]["dice"] < 1.0 for row in with_cyst)
    header = next(csv.reader((tmp_path / "r1" / "cases.csv").open()))
    assert "masses_dice" in header and "pancreas_dice" not in header
    comparison = paired_comparison(report, other, region="tumor")
    assert comparison["mean"] < 0
    with pytest.raises(ValueError, match="Unsupported paired region"):
        paired_comparison(report, other, region="mass")
    with pytest.raises(ValueError, match="exclusive"):
        evaluate_predictions(
            manifest_path, perfect, tmp_path / "r3", case_ids=val, pancreas_include_mass=False
        )


def test_lits_evaluation_scores_liver_and_tumor_with_lesion_detection(tmp_path):
    manifest_path = tmp_path / "m.json"
    manifest = audit_msd(_lits(tmp_path), manifest_path, profile="lits", geometry=RELAXED)
    labeled = [case for case in manifest["cases"] if case["label"]]
    folder = tmp_path / "pred"
    for case in labeled:
        reference = np.asarray(nib.load(case["label"]).dataobj)
        _nifti(folder / f"{case['case_id']}.nii.gz", reference)
    ids = [case["case_id"] for case in labeled]
    report = evaluate_predictions(
        manifest_path, folder, tmp_path / "report", case_ids=ids, lesion_iou_threshold=0.5
    )
    assert list(report["regions"]) == ["liver", "tumor"]
    assert report["regions"]["tumor"]["reference_empty_cases"] == 3
    assert report["regions"]["liver"]["dice"]["mean"] == 1.0
    assert report["lesions"]["true_positives"] == report["lesions"]["reference_components"]
    assert report["limitations"][-1].startswith("Spatial units and coded affines")


def test_cli_audits_lits_and_kits23_and_writes_a_stratified_split(tmp_path, capsys):
    links = _links(tmp_path, ("liver_11", "liver_12"))
    root = _lits(tmp_path)
    assert (
        main(
            [
                "audit",
                "--dataset",
                "lits",
                "--dataset-root",
                str(root),
                "--output",
                str(tmp_path / "lits.json"),
                "--duplicate-links",
                str(links),
                "--qform-sform-atol-mm",
                "1e-3",
            ]
        )
        == 0
    )
    assert load_manifest(tmp_path / "lits.json")["geometry_policy"] == {
        "qform_sform_atol_mm": 1e-3,
        "unknown_spatial_units_as_mm": False,
    }
    assert (
        main(
            [
                "split",
                "--manifest",
                str(tmp_path / "lits.json"),
                "--output",
                str(tmp_path / "split.json"),
                "--train-fraction",
                "0.64",
                "--val-fraction",
                "0.16",
                "--stratify-lesion-volume",
            ]
        )
        == 0
    )
    assert json.loads((tmp_path / "split.json").read_text())["assignment"]["block_size"] == 6
    kits = _kits(tmp_path, cases=3)
    command = ["audit-kits23", "--dataset-root", str(kits), "--output", str(tmp_path / "k.json")]
    assert main(command) == 1
    assert "explicitly be mm" in capsys.readouterr().err
    assert main([*command, "--unknown-units-as-mm"]) == 0
    assert load_manifest(tmp_path / "k.json")["dataset"] == "KiTS23"
    # A release whose label names are not liver/cancer is refused as LiTS.
    task07 = _task07(tmp_path)
    assert (
        main(
            [
                "audit",
                "--dataset",
                "lits",
                "--dataset-root",
                str(task07),
                "--output",
                str(tmp_path / "t.json"),
            ]
        )
        == 1
    )
    assert "are not the Task03_Liver labels" in capsys.readouterr().err


def test_task07_audit_is_the_default_profile(tmp_path):
    manifest = audit_task07(_task07(tmp_path), tmp_path / "m.json")
    assert "geometry_policy" not in manifest and "duplicate_links" not in manifest
    assert all(
        "duplicate_group" not in case and "geometry_relaxations" not in case
        for case in manifest["cases"]
    )


# ---------------------------------------------------------------------------
# Review fixes: transfer-dataset protocol details
# ---------------------------------------------------------------------------


def test_kidney_host_label_is_the_exclusive_kidney_label():
    assert KIDNEY.host_label == 1 and LIVER.host_label == 1 and PANCREAS.host_label == 1
    assert KIDNEY.host_labels == (1, 2, 3)


def test_unlabeled_copies_of_labelled_cases_are_never_predicted(tmp_path):
    links = _links(tmp_path, ("liver_10", "liver_26"))
    manifest = audit_msd(
        _lits(tmp_path),
        tmp_path / "m.json",
        profile="lits",
        duplicate_links_path=links,
        geometry=RELAXED,
    )
    kept, excluded = current_data.predictable_unlabeled_cases(manifest)
    # liver_25 has liver_3's voxels; liver_26 is a confirmed duplicate of liver_10.
    assert excluded == ["liver_25", "liver_26"]
    assert kept == ["liver_27", "liver_28"]


def test_float_rounding_does_not_request_a_test_set(tmp_path):
    manifest = tmp_path / "m.json"
    audit_msd(_lits(tmp_path), manifest, profile="lits", geometry=RELAXED)
    splits = make_splits(manifest, tmp_path / "s.json", 0.7, 0.3, seed=0)
    assert splits["test"] == [] and splits["requested_group_fractions"]["test"] == 0.0
    assert make_splits(manifest, tmp_path / "s2.json", 0.85, 0.15, seed=0)["test"] == []


def test_task07_cv_without_mass_counts_keeps_the_base_commit_bytes(tmp_path, monkeypatch):
    """A pancreas/mass manifest with mass-free training cases (PanTS-style) is unchanged."""
    base = _base_sources(tmp_path, monkeypatch)
    root = _task07(tmp_path)
    audited = tmp_path / "audited.json"
    current_data.audit_task07(root, audited)
    document = json.loads(audited.read_text())
    for case in document["cases"][:4]:
        if case["label_counts"]:
            case["label_counts"].pop("2", None)
    document["fingerprint"] = fingerprint(document)
    manifest = tmp_path / "m.json"
    atomic_write_json(manifest, document)
    splits = tmp_path / "s.json"
    current_data.make_splits(manifest, splits, seed=0)
    outputs = []
    for label, cv in (("base", base["cv_splits"]), ("new", current_cv)):
        path = tmp_path / f"{label}-cv.json"
        cv.make_cv_splits(manifest, splits, path, folds=5, seed=0)
        outputs.append(path.read_bytes())
    assert outputs[0] == outputs[1]
    assert json.loads(outputs[1])["assignment"]["method"] == "seeded_shuffle_blocks"


def test_lits_reports_the_nnunet_dice_convention_and_neutral_lesion_wording(tmp_path):
    manifest_path = tmp_path / "m.json"
    manifest = audit_msd(_lits(tmp_path), manifest_path, profile="lits", geometry=RELAXED)
    labeled = [case for case in manifest["cases"] if case["label"]]
    folder = tmp_path / "pred"
    for case in labeled:
        reference = np.asarray(nib.load(case["label"]).dataobj)
        if case["case_id"] == "liver_0":  # tumor-free: predict the whole liver as tumor
            reference = np.where(reference == 1, 2, reference)
        _nifti(folder / f"{case['case_id']}.nii.gz", reference)
    ids = [case["case_id"] for case in labeled]
    report = evaluate_predictions(
        manifest_path, folder, tmp_path / "report", case_ids=ids, lesion_iou_threshold=0.5
    )
    tumor = report["regions"]["tumor"]
    assert tumor["dice"]["mean"] == 1.0
    assert tumor["reference_empty_prediction_nonempty_cases"] == 1
    # nnU-Net scores the false-positive tumor-free case 0 and skips both-empty cases.
    assert tumor["dice_nnunet_convention"]["cases"] == 23
    assert tumor["dice_nnunet_convention"]["mean"] == pytest.approx(22 / 23)
    assert report["regions"]["liver"]["dice_nnunet_convention"]["mean"] == 1.0
    wording = {row["lesions"]["interpretation"] for row in report["cases"] if "lesions" in row}
    assert wording == {LIVER.lesion_interpretation} and "PDAC" not in LIVER.lesion_interpretation


def test_kits23_official_surface_tolerances_are_per_region(tmp_path):
    manifest_path, splits_path, _ = _kits_development(tmp_path)
    manifest = load_manifest(manifest_path)
    folder = tmp_path / "perfect"
    _predict(manifest, folder, lambda labels: labels)
    val = json.loads(splits_path.read_text())["val"]
    report = evaluate_predictions(
        manifest_path, folder, tmp_path / "r", case_ids=val, surface_tolerance_mm="official"
    )
    assert report["protocol"]["surface_tolerance_mm"] == "official"
    assert report["protocol"]["surface_tolerances_mm"] == {
        "kidney_and_masses": 1.0330772532390826,
        "masses": 1.1328796488598762,
        "tumor": 1.1498198361434828,
    }
    assert report["regions"]["tumor"]["surface_dice"]["mean"] == 1.0
    lits = tmp_path / "lits.json"
    audit_msd(_lits(tmp_path), lits, profile="lits", geometry=RELAXED)
    with pytest.raises(ValueError, match="no official per-region"):
        evaluate_predictions(lits, folder, tmp_path / "r2", surface_tolerance_mm="official")
    with pytest.raises(ValueError, match="official"):
        evaluate_predictions(manifest_path, folder, tmp_path / "r3", surface_tolerance_mm="loose")


def test_task07_defaults_are_refused_on_other_ontologies(tmp_path):
    lits = tmp_path / "lits.json"
    audit_msd(_lits(tmp_path), lits, profile="lits", geometry=RELAXED)
    lits_splits = tmp_path / "lits-splits.json"
    make_splits(lits, lits_splits, 0.64, 0.16, seed=0, stratify=True)
    default_regions = b.NNUNetConfig(
        str(tmp_path / "lits-regions"), gpu="2", dataset_id=703, output_mode="regions"
    )
    with pytest.raises(ValueError, match="lits regions"):
        b.prepare_dataset(lits, lits_splits, default_regions, dry_run=True)
    liver_regions = b.NNUNetConfig(
        str(tmp_path / "lits-liver"),
        gpu="2",
        dataset_id=703,
        output_mode="regions",
        label_regions=LIVER.label_regions(),
        regions_class_order=list(LIVER.nnunet_regions_class_order),
    )
    b.prepare_dataset(lits, lits_splits, liver_regions, dry_run=True)
    # Label-mode HRC: the default host [1] / lesion [2] channels would ignore KiTS23 cysts.
    from types import SimpleNamespace

    from segmentary.medical.recipe_plan import validate_hrc_options

    def hrc(**options):
        return SimpleNamespace(output_mode="labels", hrc_options=validate_hrc_options(options))

    b._check_ontology_defaults(hrc(), dict(PANCREAS.ontology))
    b._check_ontology_defaults(hrc(), dict(LIVER.ontology))
    with pytest.raises(ValueError, match="cover"):
        b._check_ontology_defaults(hrc(), dict(KIDNEY.ontology))
    b._check_ontology_defaults(hrc(lesion_channels=[2, 3]), dict(KIDNEY.ontology))


def test_cli_accepts_official_surface_tolerances():
    from segmentary.medical.cli import _parser

    command = ["evaluate", "--manifest", "m", "--predictions", "p", "--output", "o"]
    args = _parser().parse_args([*command, "--splits", "s", "--surface-tolerance-mm", "official"])
    assert args.surface_tolerance_mm == "official"
