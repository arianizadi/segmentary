"""Metadata-only overlap evidence; no held-out scan payloads are ever opened."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from segmentary.medical.data import fingerprint

SCRIPT = Path(__file__).parents[1] / "scripts" / "audit_medical_cohort_overlap.py"
SPEC = importlib.util.spec_from_file_location("audit_medical_cohort_overlap", SCRIPT)
assert SPEC and SPEC.loader
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _case(case_id: str, source: str, patient: str, image_hash: str | None = None) -> dict:
    return {
        "case_id": case_id,
        "patient_id": patient,
        "source": source,
        "annotation_status": "labeled",
        "image": f"/never-open-payloads/{source}/{case_id}.nii.gz",
        "label": f"/never-open-payloads/{source}/{case_id}-label.nii.gz",
        "image_sha256": image_hash or _hash(case_id),
        "label_sha256": _hash("identical-empty-label"),
        "shape": [3, 4, 5],
        "spacing_mm": [1, 1, 2],
        "affine": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 2, 0], [0, 0, 0, 1]],
    }


def _manifest(tmp_path: Path, name: str, cases: list[dict], *, groups: dict | None = None) -> Path:
    value = {
        "schema_version": 1,
        "dataset": name,
        "source_root": "/never-open-payloads",
        "ontology": {"background": 0, "pancreas": 1, "mass": 2},
        "audit": {"passed": True, "patient_identity_verified": False},
        "grouping_status": "dataset_case_unverified",
        "cases": cases,
    }
    if groups is not None:
        value["inherited_group_assignments"] = groups
    value["fingerprint"] = fingerprint(value)
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(value))
    return path


def test_exact_file_and_voxel_duplicates_are_separate_bounded_group_evidence(
    tmp_path: Path,
) -> None:
    left = [_case("a1", "A", "p1", _hash("shared-file")), _case("a2", "A", "p2")]
    right = [_case("b1", "B", "q1", _hash("shared-file")), _case("b2", "B", "q2")]
    left[1]["image_voxel_sha256"] = right[1]["image_voxel_sha256"] = _hash("same-decoded-voxels")
    report = helper.audit([_manifest(tmp_path, "a", left), _manifest(tmp_path, "b", right)])
    pair = report["pairs"][0]
    assert pair["status"] == "exact_image_overlap_found"
    assert pair["independence_established"] is False
    assert pair["evidence"]["exact_image_file_hash"]["case_pair_links"] == 1
    assert pair["evidence"]["exact_decoded_image_hash"]["case_pair_links"] == 1
    assert report["cohorts"][0]["decoded_image_hash_cases"] == 1
    assert report["policy"]["payload_reads"] == 0
    assert report == helper.audit([tmp_path / "a.json", tmp_path / "b.json"])


def test_source_patient_and_inherited_links_survive_different_scan_hashes(tmp_path: Path) -> None:
    a = _manifest(
        tmp_path,
        "a",
        [_case("first", "shared-source", "same-patient")],
        groups={"first": "ancestor-group"},
    )
    b = _manifest(
        tmp_path,
        "b",
        [_case("second", "shared-source", "same-patient")],
        groups={"second": "ancestor-group"},
    )
    pair = helper.audit([a, b])["pairs"][0]
    assert pair["status"] == "documented_identifier_overlap_requires_review"
    assert pair["evidence"]["exact_image_file_hash"]["matching_identity_groups"] == 0
    assert pair["evidence"]["same_source_patient_id"]["matching_identity_groups"] == 1
    assert pair["evidence"]["same_source_inherited_group"]["matching_identity_groups"] == 1
    assert pair["cross_source_patient_id_text_collisions"] == []


def test_inherited_bridge_detected_even_when_patient_and_case_ids_differ(tmp_path: Path) -> None:
    a = _manifest(
        tmp_path, "a", [_case("first", "same-source", "p1")], groups={"first": "inherited-bridge"}
    )
    b = _manifest(
        tmp_path, "b", [_case("second", "same-source", "p2")], groups={"second": "inherited-bridge"}
    )
    pair = helper.audit([a, b])["pairs"][0]
    assert pair["evidence"]["same_source_patient_id"]["matching_identity_groups"] == 0
    assert pair["evidence"]["same_source_case_id"]["matching_identity_groups"] == 0
    assert pair["evidence"]["same_source_inherited_group"]["matching_identity_groups"] == 1


def test_bare_cross_source_ids_are_ambiguous_and_not_patient_links(tmp_path: Path) -> None:
    a = _manifest(
        tmp_path, "a", [_case("first", "source-A", "001")], groups={"first": "generic-group"}
    )
    b = _manifest(
        tmp_path, "b", [_case("second", "source-B", "001")], groups={"second": "generic-group"}
    )
    pair = helper.audit([a, b])["pairs"][0]
    assert pair["status"] == "ambiguous_identifier_collision_requires_review"
    assert pair["evidence"]["same_source_patient_id"]["matching_identity_groups"] == 0
    assert pair["evidence"]["same_source_inherited_group"]["matching_identity_groups"] == 0
    assert len(pair["cross_source_patient_id_text_collisions"]) == 1
    assert len(pair["cross_source_inherited_group_text_collisions"]) == 1


def test_no_hits_and_identical_label_hashes_never_clear_independence(tmp_path: Path) -> None:
    a = _manifest(tmp_path, "a", [_case("first", "A", "p1")])
    b = _manifest(tmp_path, "b", [_case("second", "B", "p2")])
    report = helper.audit([a, b])
    pair = report["pairs"][0]
    assert pair["status"] == "no_overlap_found_independence_unresolved"
    assert pair["independence_established"] is False
    assert "Never used" in report["policy"]["label_hashes"]
    assert all(item["matching_identity_groups"] == 0 for item in pair["evidence"].values())
    assert report["cohorts"][0]["dataset_case_identity_placeholders"] is True


def test_payloads_including_heldout_are_never_opened_and_identifiers_not_exported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensitive = "privatePatientXYZ-728"
    source = "privateSourceXYZ-839"
    a_case = _case("privateCaseXYZ-928", source, sensitive)
    a_case.update(annotation_status="unlabeled", label=None, label_sha256=None)
    b_case = _case("privateCaseXYZ-982", source, sensitive, a_case["image_sha256"])
    paths = [_manifest(tmp_path, "cohort-a", [a_case]), _manifest(tmp_path, "cohort-b", [b_case])]
    original = Path.open
    opened = []

    def guard(path, *args, **kwargs):
        assert "never-open-payloads" not in str(path), "Image/reference payload was opened"
        opened.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guard)
    report = helper.audit(paths)
    assert report["pairs"][0]["status"] == "exact_image_overlap_found"
    payload = json.dumps(report, allow_nan=False)
    for private in (
        sensitive,
        source,
        a_case["case_id"],
        b_case["case_id"],
        "never-open-payloads",
        str(tmp_path),
    ):
        assert private not in payload
    assert SCRIPT in opened
    assert report["cohorts"][0]["manifest_sha256"] == _hash(paths[0].read_text())


def test_group_records_do_not_expand_repeated_scans_into_cartesian_rows(tmp_path: Path) -> None:
    a = _manifest(
        tmp_path, "a", [_case(f"a{i}", "A", f"pa{i}", _hash("same-image")) for i in range(30)]
    )
    b = _manifest(
        tmp_path, "b", [_case(f"b{i}", "B", f"pb{i}", _hash("same-image")) for i in range(40)]
    )
    result = helper.audit([a, b])["pairs"][0]["evidence"]["exact_image_file_hash"]
    assert result["matching_identity_groups"] == 1
    assert result["case_pair_links"] == 1200
    assert len(result["groups"]) == 1
    assert len(result["groups"][0]["left_case_keys"]) == 30
    assert len(result["groups"][0]["right_case_keys"]) == 40


def test_every_cohort_pair_compared_without_self_comparisons(tmp_path: Path) -> None:
    paths = [
        _manifest(tmp_path, f"cohort{i}", [_case(f"case{i}", f"source{i}", f"patient{i}")])
        for i in range(4)
    ]
    report = helper.audit(paths)
    assert len(report["pairs"]) == 6
    assert len({(pair["left_cohort"], pair["right_cohort"]) for pair in report["pairs"]}) == 6


def test_invalid_or_changing_metadata_and_duplicate_inputs_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _manifest(tmp_path, "a", [_case("first", "A", "p1")])
    b = _manifest(tmp_path, "b", [_case("second", "B", "p2")])
    with pytest.raises(ValueError, match="At least two"):
        helper.audit([a])
    with pytest.raises(ValueError, match="Repeated manifest"):
        helper.audit([a, a])
    copied = tmp_path / "copy.json"
    copied.write_bytes(a.read_bytes())
    with pytest.raises(ValueError, match="Identical manifest fingerprints"):
        helper.audit([a, copied])
    original = helper.load_manifest

    def mutate(path, *, verify_files):
        assert verify_files is False
        document = original(path, verify_files=False)
        if path == b:
            path.write_text(path.read_text() + "\n")
        return document

    monkeypatch.setattr(helper, "load_manifest", mutate)
    with pytest.raises(ValueError, match="changed during audit"):
        helper.audit([a, b])
    monkeypatch.setattr(helper, "load_manifest", original)
    invalid = copy.deepcopy(json.loads(b.read_text()))
    invalid["audit"]["passed"] = False
    invalid["fingerprint"] = fingerprint(invalid)
    b.write_text(json.dumps(invalid))
    with pytest.raises(ValueError, match="passing audit"):
        helper.audit([a, b])


def test_cli_creates_immutable_local_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _manifest(tmp_path, "a", [_case("first", "A", "p1")])
    b = _manifest(tmp_path, "b", [_case("second", "B", "p2")])
    output = tmp_path / "report" / "overlap.json"
    monkeypatch.setattr(
        "sys.argv", [str(SCRIPT), "--manifests", str(a), str(b), "--output", str(output)]
    )
    helper.main()
    assert json.loads(output.read_text())["kind"] == "medical_cohort_overlap_metadata_audit"
    with pytest.raises(FileExistsError):
        helper.main()
