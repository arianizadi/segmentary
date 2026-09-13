"""Scientific integrity checks for volumes, grouping and physical CT conversion."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

nib = pytest.importorskip("nibabel")
pydicom = pytest.importorskip("pydicom")

from segmentary.medical.data import (  # noqa: E402
    annotation_policy,
    atomic_write_json,
    audit_task07,
    fingerprint,
    load_manifest,
    make_splits,
    subset_manifest,
    validate_splits,
)
from segmentary.medical.geometry import (  # noqa: E402
    MedicalDataError,
    convert_dicom_series,
    export_native_prediction,
    sha256_file,
    validate_nifti,
)


def _nifti(path: Path, data: np.ndarray, affine: np.ndarray | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    matrix = np.diag([0.75, 1.25, 3.0, 1.0]) if affine is None else affine
    volume = nib.Nifti1Image(data, matrix)
    volume.header.set_xyzt_units("mm")
    volume.set_qform(matrix, code=1)
    volume.set_sform(matrix, code=1)
    nib.save(volume, path)
    return path


def _task07(tmp_path: Path, *, labeled: int = 6, unlabeled: int = 2) -> Path:
    root = tmp_path / "Task07_Pancreas"
    training, testing = [], []
    for index in range(labeled + unlabeled):
        case = f"pancreas_{index:03d}"
        image = f"imagesTr/{case}.nii.gz" if index < labeled else f"imagesTs/{case}.nii.gz"
        ct = np.arange(120, dtype=np.float32).reshape(4, 5, 6) + index * 100 - 1000
        _nifti(root / image, ct)
        if index < labeled:
            label = f"labelsTr/{case}.nii.gz"
            mask = np.zeros(ct.shape, dtype=np.uint8)
            mask[1:3, 1:4, 2:5] = 1
            mask[2, 2, 3] = 2
            _nifti(root / label, mask)
            training.append({"image": f"./{image}", "label": f"./{label}"})
        else:
            testing.append(f"./{image}")
    (root / "dataset.json").write_text(
        json.dumps(
            {
                "numTraining": labeled,
                "numTest": unlabeled,
                "labels": {"0": "background", "1": "pancreas", "2": "cancer"},
                "training": training,
                "test": testing,
            }
        )
    )
    return root


def test_task07_audit_decodes_every_volume_and_keeps_unlabeled_unknown(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    output = tmp_path / "manifest.json"
    manifest = audit_task07(root, output)
    assert manifest["audit"]["fully_decoded_images"] == 8
    assert manifest["audit"]["fully_decoded_labels"] == 6
    assert manifest["grouping_status"] == "dataset_case_unverified"
    assert manifest["audit"]["patient_identity_verified"] is False
    assert manifest["ontology"]["mass"] == 2
    assert manifest["source_ontology"]["2"] == "cancer"
    assert load_manifest(output, verify_files=True) == manifest
    unknown = manifest["cases"][-1]
    assert unknown["label"] is None and unknown["label_sha256"] is None
    assert not annotation_policy(unknown)["semantic_training_allowed"]
    assert annotation_policy(unknown)["pdac_diagnosis"] is None
    with pytest.raises(FileExistsError):
        audit_task07(root, output)


@pytest.mark.parametrize("problem", ["nonfinite", "fractional", "unexpected", "affine"])
def test_audit_rejects_payload_label_and_geometry_errors(tmp_path: Path, problem: str) -> None:
    root = _task07(tmp_path)
    source = root / ("imagesTr" if problem == "nonfinite" else "labelsTr") / "pancreas_004.nii.gz"
    volume = nib.load(source)
    values = volume.get_fdata().astype(np.float32)
    affine = volume.affine.copy()
    if problem == "nonfinite":
        values[2, 2, 2] = np.nan
    elif problem == "fractional":
        values[2, 2, 2] = 1.5
    elif problem == "unexpected":
        values[2, 2, 2] = 9
    else:
        affine[0, 3] += 10
    _nifti(source, values, affine)
    output = tmp_path / "invalid.json"
    with pytest.raises(MedicalDataError):
        audit_task07(root, output)
    assert not output.exists()


def test_nifti_coded_affines_must_agree(tmp_path: Path) -> None:
    path = _nifti(tmp_path / "conflict.nii.gz", np.zeros((2, 3, 4), np.float32))
    image = nib.load(path)
    affine = image.affine.copy()
    affine[2, 3] = 10
    image.set_qform(affine, code=1)
    nib.save(image, path)
    with pytest.raises(MedicalDataError, match="conflicting qform/sform"):
        validate_nifti(path)


@pytest.mark.parametrize("problem", ["unknown_units", "uncoded", "four_dimensional", "truncated"])
def test_nifti_rejects_ambiguous_or_broken_inputs(tmp_path: Path, problem: str) -> None:
    shape = (2, 3, 4, 2) if problem == "four_dimensional" else (2, 3, 4)
    path = _nifti(tmp_path / "bad.nii.gz", np.zeros(shape, np.float32))
    image = nib.load(path)
    if problem == "unknown_units":
        image.header.set_xyzt_units("unknown")
        nib.save(image, path)
    elif problem == "uncoded":
        image.set_qform(None, code=0)
        image.set_sform(None, code=0)
        nib.save(image, path)
    elif problem == "truncated":
        path.write_bytes(path.read_bytes()[:30])
    with pytest.raises(MedicalDataError):
        validate_nifti(path)


def test_fingerprint_and_content_changes_are_detected(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    output = tmp_path / "manifest.json"
    manifest = audit_task07(root, output)
    tampered = {**manifest, "dataset": "different"}
    broken = tmp_path / "tampered.json"
    broken.write_text(json.dumps(tampered))
    with pytest.raises(MedicalDataError, match="fingerprint"):
        load_manifest(broken)
    image_path = Path(manifest["cases"][0]["image"])
    _nifti(image_path, np.ones((4, 5, 6), np.float32))
    with pytest.raises(MedicalDataError, match="changed after audit"):
        load_manifest(output, verify_files=True)


def test_group_mapping_must_cover_unlabeled_companions(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    groups_path = tmp_path / "groups.json"
    groups = {f"pancreas_{index:03d}": f"patient-{index // 2}" for index in range(8)}
    groups_path.write_text(json.dumps({"groups": groups}))
    manifest = audit_task07(root, tmp_path / "manifest.json", groups_path)
    assert manifest["cases"][0]["patient_id"] == manifest["cases"][1]["patient_id"]
    assert manifest["grouping_status"] == "provided_patient_mapping"
    del groups["pancreas_007"]
    groups_path.write_text(json.dumps(groups))
    with pytest.raises(MedicalDataError, match="every declared case"):
        audit_task07(root, tmp_path / "invalid.json", groups_path)


def test_splits_are_stable_group_safe_and_exclude_unlabeled(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    groups_path = tmp_path / "groups.json"
    groups = {f"pancreas_{index:03d}": f"patient-{index // 2}" for index in range(8)}
    groups_path.write_text(json.dumps(groups))
    manifest_path = tmp_path / "manifest.json"
    manifest = audit_task07(root, manifest_path, groups_path)
    first = make_splits(manifest_path, tmp_path / "split.json", seed=17)
    repeated = make_splits(manifest_path, tmp_path / "repeat.json", seed=17)
    assert first == repeated
    assert len(first["excluded_unlabeled_or_partial"]) == 2
    assert first["group_counts"] == {"train": 1, "val": 1, "test": 1}
    for part in ("train", "val", "test"):
        assert len(first[part]) == 2
    validate_splits(manifest, first)
    with pytest.raises(FileExistsError):
        make_splits(manifest_path, tmp_path / "split.json")


def test_split_validator_rejects_leakage_even_through_an_unlabeled_bridge(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    manifest = audit_task07(root, tmp_path / "original.json")
    # The excluded scan shares a patient with A and content with B. A and B
    # have different direct identifiers, but must still be one split group.
    a, b, bridge = manifest["cases"][0], manifest["cases"][1], manifest["cases"][-1]
    bridge["patient_id"] = a["patient_id"]
    bridge["image_sha256"] = b["image_sha256"]
    manifest["fingerprint"] = fingerprint(manifest)
    split = {
        "schema_version": 1,
        "manifest_fingerprint": manifest["fingerprint"],
        "seed": 0,
        "train": [a["case_id"]],
        "val": [b["case_id"]],
        "test": [case["case_id"] for case in manifest["cases"][2:6]],
    }
    split["fingerprint"] = fingerprint(split)
    with pytest.raises(MedicalDataError, match="leak"):
        validate_splits(manifest, split)


def test_same_voxel_content_with_different_header_is_kept_together(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    left = nib.load(root / "imagesTr/pancreas_000.nii.gz")
    right_path = root / "imagesTr/pancreas_001.nii.gz"
    right = nib.Nifti1Image(left.get_fdata().astype(np.float32), left.affine, left.header.copy())
    right.header["descrip"] = "different encoding/header"
    nib.save(right, right_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = audit_task07(root, manifest_path)
    a, b = manifest["cases"][:2]
    assert a["image_sha256"] != b["image_sha256"]
    assert a["image_voxel_sha256"] == b["image_voxel_sha256"]
    split = make_splits(manifest_path, tmp_path / "splits.json")
    assert any(
        {a["case_id"], b["case_id"]} <= set(split[part]) for part in ("train", "val", "test")
    )


@pytest.mark.parametrize(
    "train,val", [(0, 0.2), (0.9, 0.2), (-0.1, 0.1), (0.5, -0.1), (float("nan"), 0.1), (True, 0)]
)
def test_bad_fractions_are_rejected(tmp_path: Path, train: float, val: float) -> None:
    with pytest.raises(MedicalDataError):
        make_splits(tmp_path / "unused.json", tmp_path / "split.json", train, val)


def test_audited_subset_preserves_identity_and_allows_zero_test_partition(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    parent = audit_task07(root, manifest_path)
    subset_path = tmp_path / "subset.json"
    subset = subset_manifest(manifest_path, subset_path, ["pancreas_000", "pancreas_001"])
    assert subset["parent_manifest_fingerprint"] == parent["fingerprint"]
    assert subset["cases"] == parent["cases"][:2]
    assert subset["subset_purpose"] == "engineering_smoke_or_overfit_only"
    split = make_splits(subset_path, tmp_path / "split.json", 0.5, 0.5)
    assert [len(split[name]) for name in ("train", "val", "test")] == [1, 1, 0]
    with pytest.raises(MedicalDataError, match="distinct case"):
        subset_manifest(manifest_path, tmp_path / "bad.json", ["pancreas_000", "pancreas_000"])


def test_organ_only_references_never_become_mass_negatives(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    manifest = audit_task07(root, tmp_path / "manifest.json")
    case = manifest["cases"][0]
    case["annotation_status"] = "organ_only"
    mask_path = Path(case["label"])
    mask = np.asanyarray(nib.load(mask_path).dataobj).copy()
    mask[mask == 2] = 1
    _nifti(mask_path, mask)
    case["label_sha256"] = sha256_file(mask_path)
    ids, counts = np.unique(mask, return_counts=True)
    case["label_counts"] = {
        str(int(label)): int(count) for label, count in zip(ids, counts, strict=True)
    }
    policy = annotation_policy(case)
    assert not policy["semantic_training_allowed"]
    assert policy["mass_reference_available"] is False
    assert policy["pdac_diagnosis"] is None
    manifest["fingerprint"] = fingerprint(manifest)
    organ_path = tmp_path / "organ.json"
    atomic_write_json(organ_path, manifest)
    load_manifest(organ_path)
    split = make_splits(organ_path, tmp_path / "split.json")
    assert case["case_id"] in split["excluded_unlabeled_or_partial"]
    split["train"].append(case["case_id"])
    split["fingerprint"] = fingerprint(split)
    with pytest.raises(MedicalDataError, match="not fully labeled"):
        validate_splits(manifest, split)


def test_native_export_preserves_asymmetric_phantom_world_coordinates(tmp_path: Path) -> None:
    affine = np.array(
        [[0, -1.25, 0, 120], [0.75, 0, 0, -40], [0, 0, 3, 25], [0, 0, 0, 1]], dtype=float
    )
    reference = _nifti(tmp_path / "ct.nii.gz", np.zeros((4, 5, 6), np.float32), affine)
    prediction = np.zeros((4, 5, 6), np.uint8)
    prediction[1, 3, 4] = 2
    output = tmp_path / "prediction.nii.gz"
    metadata = export_native_prediction(reference, prediction, output)
    loaded = nib.load(output)
    assert np.array_equal(np.asanyarray(loaded.dataobj), prediction)
    assert np.allclose(loaded.affine @ [1, 3, 4, 1], affine @ [1, 3, 4, 1])
    assert metadata["shape"] == [4, 5, 6]
    with pytest.raises(FileExistsError):
        export_native_prediction(reference, prediction, output)
    with pytest.raises(MedicalDataError, match="original reference grid"):
        export_native_prediction(reference, prediction[:2], tmp_path / "bad.nii.gz")


def _dicom_series(
    root: Path, *, z: tuple[float, ...] = (0, 5, 10)
) -> tuple[Path, np.ndarray, np.ndarray]:
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

    root.mkdir(parents=True, exist_ok=True)
    series, frame = generate_uid(), generate_uid()
    expected = []
    for index, position in enumerate(z):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        path = root / f"{len(z) - index}.dcm"  # reversed file order
        ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.SeriesInstanceUID, ds.FrameOfReferenceUID = series, frame
        ds.Modality = "CT"
        ds.ImagePositionPatient = [10, 20, position]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [2, 3]
        ds.Rows, ds.Columns = 2, 3
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.RescaleSlope, ds.RescaleIntercept, ds.RescaleType = index + 1, -1024, "HU"
        raw = np.arange(6, dtype=np.int16).reshape(2, 3) + 10 * index
        ds.PixelData = raw.tobytes()
        ds.save_as(path, enforce_file_format=True)
        expected.append(raw.astype(np.float32) * (index + 1) - 1024)
    affine = np.array([[0, -3, 0, -10], [-2, 0, 0, -20], [0, 0, 5, 0], [0, 0, 0, 1]], dtype=float)
    return root, np.stack(expected, axis=2), affine


def test_dicom_conversion_orders_physical_slices_and_applies_each_hu_scale(tmp_path: Path) -> None:
    source, expected, affine = _dicom_series(tmp_path / "dicom")
    output = tmp_path / "ct.nii.gz"
    result = convert_dicom_series(source, output)
    volume = nib.load(output)
    assert np.array_equal(np.asanyarray(volume.dataobj), expected)
    assert np.allclose(volume.affine, affine)
    assert result["spacing_mm"] == [2, 3, 5]
    assert result["conversion"]["source_slice_count"] == 3
    assert result["conversion"]["annotation_status"] == "unlabeled"
    with pytest.raises(FileExistsError):
        convert_dicom_series(source, output)


@pytest.mark.parametrize(
    "problem",
    [
        "irregular",
        "duplicate_position",
        "orientation",
        "series",
        "tilt",
        "duplicate_sop",
        "pixel_payload",
    ],
)
def test_dicom_rejects_invalid_geometry_or_payload(tmp_path: Path, problem: str) -> None:
    z = (
        (0, 5, 12)
        if problem == "irregular"
        else (0, 0, 5)
        if problem == "duplicate_position"
        else (0, 5, 10)
    )
    source, _, _ = _dicom_series(tmp_path / "dicom", z=z)
    path = source / "2.dcm"
    item = pydicom.dcmread(path)
    if problem == "orientation":
        item.ImageOrientationPatient = [0, 1, 0, 1, 0, 0]
    elif problem == "series":
        item.SeriesInstanceUID = pydicom.uid.generate_uid()
    elif problem == "tilt":
        item.ImagePositionPatient = [11, 20, 5]
    elif problem == "duplicate_sop":
        item.SOPInstanceUID = pydicom.dcmread(source / "1.dcm").SOPInstanceUID
    elif problem == "pixel_payload":
        item.PixelData = b"\0\0"
    item.save_as(path, enforce_file_format=True)
    output = tmp_path / "invalid.nii.gz"
    with pytest.raises(MedicalDataError):
        convert_dicom_series(source, output)
    assert not output.exists()


def test_dicom_mask_alignment_allows_only_lossless_axis_changes(tmp_path: Path) -> None:
    source, expected, affine = _dicom_series(tmp_path / "dicom")
    # A reference mask stores the same world-space grid after swapping axes.
    transform = np.array([[1, 1], [0, -1], [2, 1]], dtype=float)
    target_data = nib.orientations.apply_orientation(np.ones(expected.shape, np.uint8), transform)
    target_affine = affine @ nib.orientations.inv_ornt_aff(transform, expected.shape)
    mask = _nifti(tmp_path / "mask.nii.gz", target_data, target_affine)
    output = tmp_path / "aligned.nii.gz"
    result = convert_dicom_series(source, output, mask_path=mask)
    actual = nib.load(output)
    assert np.array_equal(
        np.asanyarray(actual.dataobj), nib.orientations.apply_orientation(expected, transform)
    )
    assert np.allclose(actual.affine, target_affine)
    assert result["conversion"]["annotation_status"] == "organ_only"
    wrong_affine = target_affine.copy()
    wrong_affine[0, 3] += 20
    wrong = _nifti(tmp_path / "wrong-mask.nii.gz", target_data, wrong_affine)
    with pytest.raises(MedicalDataError, match="affines differ"):
        convert_dicom_series(source, tmp_path / "wrong.nii.gz", mask_path=wrong)
    assert not (tmp_path / "wrong.nii.gz").exists()


def test_subset_keeps_patient_links_through_excluded_parent_cases(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    manifest = audit_task07(root, tmp_path / "original.json")
    a, b, bridge = manifest["cases"][0], manifest["cases"][1], manifest["cases"][-1]
    bridge["patient_id"] = a["patient_id"]
    # Copy B's image under the bridge's separate path and bind its metadata.
    Path(bridge["image"]).write_bytes(Path(b["image"]).read_bytes())
    bridge["image_sha256"] = b["image_sha256"]
    bridge["image_voxel_sha256"] = b["image_voxel_sha256"]
    manifest["fingerprint"] = fingerprint(manifest)
    parent_path = tmp_path / "parent.json"
    atomic_write_json(parent_path, manifest)
    selected = subset_manifest(parent_path, tmp_path / "subset.json", [a["case_id"], b["case_id"]])
    assert selected["cases"] == [a, b]
    assert len(set(selected["inherited_group_assignments"].values())) == 1
    with pytest.raises(MedicalDataError, match="not enough independent groups"):
        make_splits(tmp_path / "subset.json", tmp_path / "invalid.json", 0.5, 0.5)


def test_unreferenced_nifti_is_not_silently_excluded_from_audit(tmp_path: Path) -> None:
    root = _task07(tmp_path)
    _nifti(root / "imagesTr/extra.nii.gz", np.zeros((4, 5, 6), np.float32))
    with pytest.raises(MedicalDataError, match="inventory"):
        audit_task07(root, tmp_path / "invalid.json")


@pytest.mark.parametrize(
    "field,value", [("patient_id", " patient-0"), ("case_id", "../../outside")]
)
def test_manifest_rejects_unsafe_or_ambiguous_identity(
    tmp_path: Path, field: str, value: str
) -> None:
    root = _task07(tmp_path)
    manifest = audit_task07(root, tmp_path / "original.json")
    manifest["cases"][0][field] = value
    manifest["fingerprint"] = fingerprint(manifest)
    target = tmp_path / "unsafe.json"
    atomic_write_json(target, manifest)
    with pytest.raises(MedicalDataError):
        load_manifest(target)
