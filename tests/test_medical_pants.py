"""PanTS provenance, geometry, resumability and official test-boundary checks."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import numpy as np
import pytest

nib = pytest.importorskip("nibabel")

from segmentary.medical.cli import _parser, dispatch  # noqa: E402
from segmentary.medical.data import (  # noqa: E402
    atomic_write_json,
    fingerprint,
    load_manifest,
    make_splits,
    validate_splits,
)
from segmentary.medical.geometry import MedicalDataError, sha256_file  # noqa: E402
from segmentary.medical.pants import (  # noqa: E402
    METADATA_COLUMNS,
    _prepare_case,
    audit_pants,
    make_pants_splits,
    official_partition,
    read_metadata,
)


def _write_nifti(path: Path, values: np.ndarray, affine: np.ndarray | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    affine = np.diag([0.75, 1.25, 3.0, 1.0]) if affine is None else affine
    volume = nib.Nifti1Image(values, affine)
    volume.header.set_xyzt_units("mm")
    volume.set_qform(affine, code=1)
    volume.set_sform(affine, code=1)
    nib.save(volume, path)


def _metadata(root: Path, rows: list[tuple[str, str]], spacing: str = "(0.75, 1.25, 3.0)") -> Path:
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet = ET.Element("worksheet", xmlns=namespace)
    data = ET.SubElement(sheet, "sheetData")
    all_rows = [list(METADATA_COLUMNS)]
    for case_id, tumor in rows:
        values = ["" for _ in METADATA_COLUMNS]
        values[0] = case_id
        values[1] = "(4, 5, 6)"
        values[2] = spacing
        values[13] = tumor
        values[14] = "Public structured report retained as provenance only"
        all_rows.append(values)
    for row_index, values in enumerate(all_rows, 1):
        row = ET.SubElement(data, "row", r=str(row_index))
        for column, value in enumerate(values):
            cell = ET.SubElement(row, "c", r=f"{chr(65 + column)}{row_index}", t="inlineStr")
            ET.SubElement(ET.SubElement(cell, "is"), "t").text = value
    path = root / "metadata.xlsx"
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet))
    return path


def _case(root: Path, number: int, *, tumor: bool = True) -> str:
    key = f"PanTS_{number:08d}"
    suffix = "Tr" if number <= 9000 else "Te"
    image = np.arange(120, dtype=np.float32).reshape(4, 5, 6) + number * 200 - 1000
    _write_nifti(root / f"Image{suffix}" / key / "ct.nii.gz", image)
    folder = root / f"Label{suffix}" / key / "segmentations"
    pancreas = np.zeros(image.shape, dtype=np.uint8)
    pancreas[1:3, 1:4, 2:5] = 1
    lesion = np.zeros_like(pancreas)
    if tumor:
        lesion[2, 2, 3] = 1
        lesion[0, 0, 0] = 1  # Lesion outside organ is retained, never clipped.
    _write_nifti(folder / "pancreas.nii.gz", pancreas)
    _write_nifti(folder / "pancreatic_lesion.nii.gz", lesion)
    return key


def _dataset(tmp_path: Path) -> tuple[Path, list[str]]:
    root = tmp_path / "PanTS"
    keys = [_case(root, index, tumor=index != 1) for index in (1, 2, 3)]
    _metadata(root, [(key, "0" if key == keys[0] else "1") for key in keys])
    return root, keys


def test_smoke_audit_preserves_originals_ontology_and_metadata(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    paths = sorted(root.rglob("*.nii.gz"))
    hashes = {path: sha256_file(path) for path in paths}
    output = tmp_path / "smoke.json"
    manifest = audit_pants(root, output, case_ids=keys)
    assert load_manifest(output, verify_files=True) == manifest
    assert manifest["dataset"] == "PanTS"
    assert manifest["ontology"] == {"background": 0, "pancreas": 1, "mass": 2}
    assert not manifest["audit"]["complete_public_release"]
    assert manifest["audit"]["scope"] == "explicit_training_smoke_subset"
    assert manifest["subset_purpose"] == "engineering_smoke_or_overfit_only"
    assert manifest["grouping_status"] == "dataset_case_unverified"
    assert manifest["audit"]["source_metadata_cases"] == 3
    assert hashes == {path: sha256_file(path) for path in paths}
    positive = manifest["cases"][1]
    values = np.asarray(nib.load(positive["label"]).dataobj)
    assert values[2, 2, 3] == 2 and values[0, 0, 0] == 2
    assert positive["label_counts"]["2"] == 2
    assert positive["official_partition"] == "train"
    assert positive["source_metadata"]["tumor?"] == "1"
    assert positive["annotation_provenance"]["pancreas"]["path"].endswith("pancreas.nii.gz")
    assert manifest["cases"][0]["label_counts"].get("2", 0) == 0
    with pytest.raises(FileExistsError):
        audit_pants(root, output, case_ids=keys)


def test_per_case_preparation_resumes_and_reverifies_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, keys = _dataset(tmp_path)
    first = audit_pants(root, tmp_path / "first.json", case_ids=keys)
    import segmentary.medical.pants as pants

    def no_decode(*args: object, **kwargs: object) -> None:
        raise AssertionError("journal resume should not decode unchanged original volumes")

    monkeypatch.setattr(pants, "validate_nifti", no_decode)
    second = audit_pants(root, tmp_path / "second.json", case_ids=keys)
    assert first == second
    label = Path(first["cases"][0]["label"])
    label.write_bytes(label.read_bytes() + b"tampering")
    with pytest.raises(MedicalDataError, match="prepared label changed"):
        audit_pants(root, tmp_path / "third.json", case_ids=keys)


@pytest.mark.parametrize(
    "problem",
    [
        "unknown_mask_label",
        "mask_affine",
        "missing_pancreas",
        "empty_pancreas",
        "missing_lesion",
        "empty_positive",
        "nonfinite_ct",
        "metadata_disagreement",
    ],
)
def test_audit_refuses_uncertain_or_corrupt_supervision(tmp_path: Path, problem: str) -> None:
    root, keys = _dataset(tmp_path)
    folder = root / "LabelTr" / keys[1] / "segmentations"
    path = folder / "pancreatic_lesion.nii.gz"
    volume = nib.load(path)
    values = np.asarray(volume.dataobj).copy()
    if problem == "unknown_mask_label":
        values[0, 0, 0] = 28
        _write_nifti(path, values)
    elif problem == "mask_affine":
        affine = volume.affine.copy()
        affine[0, 3] += 10
        _write_nifti(path, values, affine)
    elif problem == "empty_pancreas":
        _write_nifti(folder / "pancreas.nii.gz", np.zeros_like(values))
    elif problem == "missing_pancreas":
        (folder / "pancreas.nii.gz").unlink()
    elif problem == "missing_lesion":
        path.unlink()
    elif problem == "empty_positive":
        _write_nifti(path, np.zeros_like(values))
    elif problem == "nonfinite_ct":
        path = root / "ImageTr" / keys[1] / "ct.nii.gz"
        values = np.asarray(nib.load(path).dataobj).copy()
        values[0, 0, 0] = np.nan
        _write_nifti(path, values)
    elif problem == "metadata_disagreement":
        _metadata(root, [(key, "0") for key in keys])
    output = tmp_path / "invalid.json"
    with pytest.raises(MedicalDataError):
        audit_pants(root, output, case_ids=keys)
    assert not output.exists()


def test_missing_negative_requires_explicit_metadata_based_opt_in(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    (root / "LabelTr" / keys[0] / "segmentations" / "pancreatic_lesion.nii.gz").unlink()
    with pytest.raises(MedicalDataError, match="absent files are not negative"):
        audit_pants(root, tmp_path / "strict.json", case_ids=keys)
    manifest = audit_pants(
        root, tmp_path / "explicit.json", case_ids=keys, allow_missing_negative_lesion=True
    )
    assert (
        manifest["cases"][0]["annotation_provenance"]["lesion_absence_basis"]
        == "explicit_metadata_tumor_0_opt_in"
    )
    (root / "LabelTr" / keys[1] / "segmentations" / "pancreatic_lesion.nii.gz").unlink()
    with pytest.raises(MedicalDataError, match="absent files are not negative"):
        audit_pants(
            root, tmp_path / "positive.json", case_ids=keys, allow_missing_negative_lesion=True
        )


def _add_test_case(root: Path, manifest: dict, output: Path) -> dict:
    key = _case(root, 9001)
    metadata = {name: None for name in METADATA_COLUMNS}
    metadata.update({"PanTS ID": key, "tumor?": "1"})
    case = _prepare_case(
        root,
        root / "SegmentaryPrepared",
        key,
        metadata,
        manifest["source_metadata_sha256"],
        f"PanTS:{key}",
        "dataset_case_unverified",
        False,
    )
    manifest["cases"].append(case)
    manifest["inherited_group_assignments"][key] = key
    manifest["fingerprint"] = fingerprint(manifest)
    atomic_write_json(output, manifest)
    return manifest


def test_official_test_is_reserved_and_generic_split_cannot_bypass(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    manifest = audit_pants(root, tmp_path / "initial.json", case_ids=keys)
    manifest_path = tmp_path / "with-test.json"
    manifest = _add_test_case(root, manifest, manifest_path)
    splits = make_pants_splits(manifest_path, tmp_path / "splits.json", val_fraction=0.34)
    assert splits["test"] == ["PanTS_00009001"]
    assert set(splits["train"] + splits["val"]) == set(keys)
    assert not splits["official_test_complete"]
    validate_splits(manifest, splits)
    with pytest.raises(MedicalDataError, match="requires split-pants"):
        make_splits(manifest_path, tmp_path / "generic.json")
    for partition in ("train", "val"):
        malicious = json.loads(json.dumps(splits))
        malicious[partition].append(malicious["test"].pop())
        malicious["fingerprint"] = fingerprint(malicious)
        with pytest.raises(MedicalDataError, match="official test cases"):
            validate_splits(manifest, malicious)


def test_official_test_duplicate_fails_closed(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    manifest = audit_pants(root, tmp_path / "initial.json", case_ids=keys)
    manifest_path = tmp_path / "with-test.json"
    manifest = _add_test_case(root, manifest, manifest_path)
    manifest["cases"][-1]["patient_id"] = manifest["cases"][0]["patient_id"]
    manifest["fingerprint"] = fingerprint(manifest)
    path = tmp_path / "overlap.json"
    atomic_write_json(path, manifest)
    with pytest.raises(MedicalDataError, match="spans PanTS official train/test"):
        make_pants_splits(path, tmp_path / "splits.json")


def test_smoke_split_respects_provided_patient_groups(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    groups = tmp_path / "groups.json"
    groups.write_text(
        json.dumps({"groups": {keys[0]: "same-patient", keys[1]: "same-patient", keys[2]: "other"}})
    )
    output = tmp_path / "manifest.json"
    audit_pants(root, output, case_ids=keys, groups_path=groups)
    splits = make_pants_splits(output, tmp_path / "split.json")
    assert any({keys[0], keys[1]} <= set(splits[name]) for name in ("train", "val"))
    assert splits["test"] == []


def test_partial_download_and_test_smoke_do_not_masquerade_as_release(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    with pytest.raises(MedicalDataError, match="all 9,901"):
        audit_pants(root, tmp_path / "full.json")
    test_id = _case(root, 9001)
    _metadata(root, [(key, "1") for key in [*keys, test_id]])
    with pytest.raises(MedicalDataError, match="official training cases only"):
        audit_pants(root, tmp_path / "test-smoke.json", case_ids=[test_id])


def test_exclusions_require_evidence_and_cannot_silently_drop_requested_smoke_case(
    tmp_path: Path,
) -> None:
    root, keys = _dataset(tmp_path)
    path = tmp_path / "exclusions.json"
    path.write_text(
        json.dumps(
            {
                "exclusions": {
                    keys[0]: {
                        "reason": "Confirmed artifact",
                        "source_url": "https://github.com/MrGiovanni/PanTS/issues/12",
                    }
                }
            }
        )
    )
    with pytest.raises(MedicalDataError, match="explicitly excluded"):
        audit_pants(root, tmp_path / "audit.json", case_ids=keys, exclude_cases_path=path)
    manifest = audit_pants(
        root, tmp_path / "selected.json", case_ids=keys[1:], exclude_cases_path=path
    )
    assert manifest["audit"]["excluded_cases"][keys[0]]["reason"] == "Confirmed artifact"
    path.write_text(json.dumps({"exclusions": {keys[0]: {"reason": "No source"}}}))
    with pytest.raises(MedicalDataError, match="source_url"):
        audit_pants(root, tmp_path / "invalid.json", case_ids=keys[1:], exclude_cases_path=path)


@pytest.mark.parametrize(
    "rows",
    [
        [("PanTS_00000001", "0"), ("PanTS_00000001", "1")],
        [("PanTS_00000001", "unknown")],
        [("PanTS_00009902", "1")],
    ],
)
def test_metadata_rejects_duplicate_unknown_and_out_of_release_values(
    tmp_path: Path, rows: list[tuple[str, str]]
) -> None:
    with pytest.raises(MedicalDataError):
        read_metadata(_metadata(tmp_path, rows))


def test_official_bounds_and_cli(tmp_path: Path) -> None:
    assert official_partition("PanTS_00009000") == "train"
    assert official_partition("PanTS_00009001") == "test"
    assert official_partition("PanTS_00009901") == "test"
    root, keys = _dataset(tmp_path)
    args = ["audit-pants", "--dataset-root", str(root), "--output", str(tmp_path / "cli.json")]
    for key in keys:
        args.extend(["--case-id", key])
    manifest = dispatch(_parser().parse_args(args))
    assert manifest["dataset"] == "PanTS"
    result = dispatch(
        _parser().parse_args(
            [
                "split-pants",
                "--manifest",
                str(tmp_path / "cli.json"),
                "--output",
                str(tmp_path / "split.json"),
            ]
        )
    )
    assert result["test"] == []


def test_explicit_units_normalization_preserves_voxel_bytes_and_originals(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    original_files = sorted(root.rglob("*.nii.gz"))
    for path in original_files:
        volume = nib.load(path)
        volume.header.set_xyzt_units("unknown", "sec")
        nib.save(volume, path)
    originals = {path: path.read_bytes() for path in original_files}
    with pytest.raises(MedicalDataError, match="units must explicitly be mm"):
        audit_pants(root, tmp_path / "strict.json", case_ids=keys)
    manifest = audit_pants(
        root,
        tmp_path / "normalized.json",
        case_ids=keys,
        normalize_unknown_units_from_metadata=True,
    )
    assert manifest["audit"]["unit_normalized_files"] == 9
    assert all(path.read_bytes() == original for path, original in originals.items())
    for case in manifest["cases"]:
        assert nib.load(case["image"]).header.get_xyzt_units() == ("mm", "sec")
        for record in case["annotation_provenance"]["unit_normalizations"].values():
            original = gzip.decompress(Path(record["original_path"]).read_bytes())
            normalized = gzip.decompress(Path(record["derived_path"]).read_bytes())
            assert original[:123] == normalized[:123]
            assert original[124:] == normalized[124:]
            assert original[123] == 8 and normalized[123] == 10
            assert record["header_bytes_changed"] == 1
    assert load_manifest(tmp_path / "normalized.json", verify_files=True) == manifest


def test_units_normalization_refuses_metadata_spacing_disagreement(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    for path in root.rglob("*.nii.gz"):
        volume = nib.load(path)
        volume.header.set_xyzt_units("unknown")
        nib.save(volume, path)
    _metadata(root, [(key, "0" if key == keys[0] else "1") for key in keys], spacing="(1, 1, 1)")
    with pytest.raises(MedicalDataError, match="metadata spacing does not agree"):
        audit_pants(
            root,
            tmp_path / "invalid.json",
            case_ids=keys,
            normalize_unknown_units_from_metadata=True,
        )
    assert not (tmp_path / "invalid.json").exists()


def test_units_normalization_does_not_relax_other_geometry_checks(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    path = root / "LabelTr" / keys[0] / "segmentations" / "pancreas.nii.gz"
    volume = nib.load(path)
    affine = volume.affine.copy()
    affine[0, 3] += 10
    _write_nifti(path, np.asarray(volume.dataobj), affine)
    volume = nib.load(path)
    volume.header.set_xyzt_units("unknown")
    nib.save(volume, path)
    with pytest.raises(MedicalDataError, match="image/mask affines differ"):
        audit_pants(
            root,
            tmp_path / "invalid.json",
            case_ids=keys,
            normalize_unknown_units_from_metadata=True,
        )


def test_failure_report_continues_cases_without_publishing_manifest(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    for key in keys[:2]:
        (root / "LabelTr" / key / "segmentations" / "pancreas.nii.gz").unlink()
    output, report = tmp_path / "audit.json", tmp_path / "failures.json"
    with pytest.raises(MedicalDataError, match="failed for 2 of 3 cases"):
        audit_pants(root, output, case_ids=keys, audit_report_path=report)
    assert not output.exists()
    evidence = json.loads(report.read_text())
    assert evidence["passed"] is False
    assert evidence["manifest_written"] is False
    assert evidence["passed_cases"] == [keys[2]]
    assert [item["case_id"] for item in evidence["failed_cases"]] == keys[:2]
    assert evidence["fingerprint"] == fingerprint(evidence)
    assert len(list((root / "SegmentaryPrepared").rglob("*.json"))) == 1
    for index in (1, 2):
        _case(root, index, tumor=index != 1)
    result = audit_pants(root, output, case_ids=keys, audit_report_path=tmp_path / "success.json")
    success = json.loads((tmp_path / "success.json").read_text())
    assert success["passed"] and success["manifest_written"]
    assert success["manifest_fingerprint"] == result["fingerprint"]
    assert not success["failed_cases"]


def test_excluded_series_still_bridges_patient_and_duplicate_groups(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    fourth = _case(root, 4)
    keys.append(fourth)
    _metadata(root, [(key, "0" if key == keys[0] else "1") for key in keys])
    left = root / "ImageTr" / keys[1] / "ct.nii.gz"
    right = root / "ImageTr" / keys[2] / "ct.nii.gz"
    right.write_bytes(left.read_bytes())
    # Case 1 --patient P1-- excluded case 2 --same CT-- case 3.
    groups = tmp_path / "groups.json"
    groups.write_text(
        json.dumps({"groups": dict(zip(keys, ["P1", "P1", "P2", "P3"], strict=True))})
    )
    exclusions = tmp_path / "excluded.json"
    exclusions.write_text(
        json.dumps(
            {
                "exclusions": {
                    keys[1]: {
                        "reason": "Bad reference",
                        "source_url": "https://example.org/annotation-review",
                    }
                }
            }
        )
    )
    (root / "LabelTr" / keys[1] / "segmentations" / "pancreas.nii.gz").unlink()
    output = tmp_path / "manifest.json"
    manifest = audit_pants(
        root,
        output,
        case_ids=[keys[0], keys[2], keys[3]],
        groups_path=groups,
        exclude_cases_path=exclusions,
    )
    assert (
        manifest["inherited_group_assignments"][keys[0]]
        == manifest["inherited_group_assignments"][keys[2]]
    )
    assert manifest["excluded_case_identities"][0]["case_id"] == keys[1]
    splits = make_pants_splits(output, tmp_path / "split.json", seed=0)
    assert any({keys[0], keys[2]} <= set(splits[name]) for name in ("train", "val"))


def test_mixed_dataset_cannot_erase_panTS_official_test_boundary(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    manifest = audit_pants(root, tmp_path / "initial.json", case_ids=keys)
    manifest = _add_test_case(root, manifest, tmp_path / "with-test.json")
    manifest["dataset"] = "Task07+PanTS"
    manifest["fingerprint"] = fingerprint(manifest)
    output = tmp_path / "mixed.json"
    atomic_write_json(output, manifest)
    with pytest.raises(MedicalDataError, match="requires split-pants"):
        make_splits(output, tmp_path / "generic.json", train_fraction=1, val_fraction=0)
    split = {
        "schema_version": 1,
        "manifest_fingerprint": manifest["fingerprint"],
        "train": [case["case_id"] for case in manifest["cases"]],
        "val": [],
        "test": [],
    }
    split["fingerprint"] = fingerprint(split)
    with pytest.raises(MedicalDataError, match="official test cases"):
        validate_splits(manifest, split)


def test_journals_bind_geometry_and_dependency_versions(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    audit_pants(root, tmp_path / "manifest.json", case_ids=keys)
    record = json.loads(next((root / "SegmentaryPrepared").rglob("*.json")).read_text())
    implementation = record["identity"]["audit_implementation"]
    assert set(implementation) == {
        "adapter_sha256",
        "data_sha256",
        "geometry_sha256",
        "numpy_version",
        "nibabel_version",
    }
    assert implementation["numpy_version"] == np.__version__


def test_binary_roundoff_opt_in_preserves_raw_scaling_and_records_correction(
    tmp_path: Path,
) -> None:
    root, keys = _dataset(tmp_path)
    path = root / "LabelTr" / keys[1] / "segmentations" / "pancreatic_lesion.nii.gz"
    source = nib.load(path)
    original_labels = np.asarray(source.dataobj)
    stored = np.where(original_labels == 1, 127, -128).astype(np.int8)
    volume = nib.Nifti1Image(stored, source.affine)
    volume.header.set_xyzt_units("unknown")
    volume.header.set_slope_inter(0.003921568859368563, 0.501960813999176)
    nib.save(volume, path)
    original_bytes = path.read_bytes()
    assert np.max(np.asarray(nib.load(path).dataobj)) == pytest.approx(1.0000000591389835)
    with pytest.raises(MedicalDataError, match="fractional labels"):
        audit_pants(
            root,
            tmp_path / "strict.json",
            case_ids=keys,
            normalize_unknown_units_from_metadata=True,
        )
    result = audit_pants(
        root,
        tmp_path / "normalized.json",
        case_ids=keys,
        normalize_unknown_units_from_metadata=True,
        normalize_binary_roundoff=True,
    )
    assert path.read_bytes() == original_bytes
    assert result["audit"]["binary_roundoff_normalized_masks"] == 1
    case = result["cases"][1]
    record = case["annotation_provenance"]["binary_roundoff_normalizations"]["pancreatic_lesion"]
    assert 0 < record["maximum_absolute_roundoff"] < 1e-6
    assert record["original_scaling_slope"] == 0.003921568859368563
    assert record["original_scaling_intercept"] == 0.501960813999176
    assert record["original_sha256"] == sha256_file(path)
    assert record["relative_tolerance"] == 0
    assert record["absolute_tolerance"] == 1e-6
    derived = nib.load(record["derived_path"])
    assert derived.get_data_dtype() == np.uint8
    assert np.array_equal(np.asarray(derived.dataobj), original_labels)
    assert case["label_counts"]["2"] == 2
    assert load_manifest(tmp_path / "normalized.json", verify_files=True) == result
    assert (
        audit_pants(
            root,
            tmp_path / "resume.json",
            case_ids=keys,
            normalize_unknown_units_from_metadata=True,
            normalize_binary_roundoff=True,
        )
        == result
    )


@pytest.mark.parametrize(
    "value", [0.3, 0.9992, 1.000002, -0.000002, 2.0, float("nan"), float("inf")]
)
def test_binary_roundoff_rejects_fractional_annotations_and_nonfinite_values(
    tmp_path: Path, value: float
) -> None:
    root, keys = _dataset(tmp_path)
    path = root / "LabelTr" / keys[1] / "segmentations" / "pancreatic_lesion.nii.gz"
    original = nib.load(path)
    values = np.asarray(original.dataobj).astype(np.float64)
    values[0, 0, 0] = value
    _write_nifti(path, values)
    with pytest.raises(MedicalDataError, match=r"roundoff tolerance|finite numeric"):
        audit_pants(root, tmp_path / "invalid.json", case_ids=keys, normalize_binary_roundoff=True)
    assert not (tmp_path / "invalid.json").exists()


def test_binary_roundoff_does_not_relax_geometry(tmp_path: Path) -> None:
    root, keys = _dataset(tmp_path)
    path = root / "LabelTr" / keys[1] / "segmentations" / "pancreatic_lesion.nii.gz"
    original = nib.load(path)
    values = np.asarray(original.dataobj).astype(np.float64)
    values[values == 1] += 5e-7
    affine = original.affine.copy()
    affine[1, 3] += 10
    _write_nifti(path, values, affine)
    with pytest.raises(MedicalDataError, match="image/mask affines differ"):
        audit_pants(root, tmp_path / "invalid.json", case_ids=keys, normalize_binary_roundoff=True)
