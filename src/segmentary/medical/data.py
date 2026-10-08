"""Versioned medical data manifests and immutable, group-disjoint splits.

Manifests carry their label ontology (``dataset_profiles``): Task07 and PanTS
use pancreas/mass, MSD Task03 liver/tumor, and KiTS23 kidney/tumor/cyst. Opt-in
geometry relaxations and confirmed content-duplicate links are recorded in the
manifest itself; a manifest without them keeps the original v1 bytes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .dataset_profiles import PANCREAS, DatasetProfile, profile_for_ontology, profile_named
from .geometry import (
    MedicalDataError,
    assert_same_geometry,
    check_geometry_policy,
    sha256_file,
    validate_nifti,
)

ONTOLOGY = dict(PANCREAS.ontology)
SPLIT_NAMES = ("train", "val", "test")


def fingerprint(value: dict[str, Any]) -> str:
    """Hash canonical JSON excluding only its own top-level fingerprint."""
    content = {key: item for key, item in value.items() if key != "fingerprint"}
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def atomic_write_json(path: str | Path, value: dict[str, Any]) -> None:
    """Publish validated JSON atomically without replacing an existing artifact."""
    target = Path(path).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite {target}")
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".segmentary-", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read_json(path: str | Path, *, expect: type = dict) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise MedicalDataError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(Path(path).read_text(), object_pairs_hook=pairs)
    except (OSError, ValueError) as exc:
        raise MedicalDataError(f"cannot read JSON artifact {path}: {exc}") from exc
    if not isinstance(value, expect):
        raise MedicalDataError(f"{path}: expected a JSON {expect.__name__}")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MedicalDataError(f"{where}: expected a nonempty string")
    return value.strip()


def _case_id(path: Path) -> str:
    return path.name[:-7] if path.name.endswith(".nii.gz") else path.stem


def _source_path(root: Path, relative: Any, *, where: str) -> Path:
    path = (root / _text(relative, where)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise MedicalDataError(f"{where}: missing file or path escapes the dataset root")
    return path


def annotation_policy(
    case: dict[str, Any], ontology: dict[str, int] | None = None
) -> dict[str, Any]:
    """Expose supervision availability without inventing a cancer diagnosis.

    Organ-only foreground means whole organ. Its mapping to exclusive
    organ/lesion classes is unresolved and cannot train the semantic task.
    """
    status = case.get("annotation_status")
    if status == "labeled":
        return {
            "semantic_training_allowed": True,
            "known_classes": sorted((ONTOLOGY if ontology is None else ontology).values()),
            "pdac_diagnosis": None,
        }
    if status == "organ_only":
        return {
            "semantic_training_allowed": False,
            "known_classes": [],
            "whole_organ_reference_available": True,
            "mass_reference_available": False,
            "pdac_diagnosis": None,
        }
    if status == "unlabeled":
        return {"semantic_training_allowed": False, "known_classes": [], "pdac_diagnosis": None}
    raise MedicalDataError(f"unknown annotation status {status!r}")


def audit_task07(
    root: str | Path, output: str | Path, groups_path: str | Path | None = None
) -> dict[str, Any]:
    """Fully audit a Task07 release, then save a content-addressed manifest.

    Without a user-supplied patient/group crosswalk, IDs are dataset-case
    grouping placeholders, explicitly not verified patient identities.
    """
    return audit_msd(root, output, profile=PANCREAS, groups_path=groups_path)


def _short_name(profile: DatasetProfile) -> str:
    return profile.dataset.split("_")[0]


def audit_msd(
    root: str | Path,
    output: str | Path,
    *,
    profile: DatasetProfile | str = PANCREAS,
    groups_path: str | Path | None = None,
    duplicate_links_path: str | Path | None = None,
    geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fully audit a Medical Segmentation Decathlon release (``dataset.json`` layout).

    Labeled training cases and unlabeled ``imagesTs`` scans are both recorded,
    so a confirmed duplicate link to an unlabeled scan still groups its
    labeled partner; unlabeled scans never enter a split. ``geometry`` is an
    opt-in ``geometry.geometry_policy`` record, stored in the manifest.
    """
    if Path(output).exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    spec = profile_named(profile) if isinstance(profile, str) else profile
    name = _short_name(spec)
    source = Path(root).expanduser().resolve()
    metadata_path = source / "dataset.json"
    metadata = _read_json(metadata_path)
    training, testing = metadata.get("training"), metadata.get("test")
    if not isinstance(training, list) or not training or not isinstance(testing, list):
        raise MedicalDataError("dataset.json must declare nonempty training and a test list")
    if metadata.get("numTraining") != len(training) or metadata.get("numTest") != len(testing):
        raise MedicalDataError("declared dataset counts disagree with manifest entries")
    label_ids = sorted(spec.ontology.values())
    if not isinstance(metadata.get("labels"), dict) or set(metadata["labels"]) != {
        str(value) for value in label_ids
    }:
        raise MedicalDataError(
            f"{name} must declare exactly {'/'.join(sorted(spec.ontology, key=spec.ontology.__getitem__))} "
            f"label IDs {'/'.join(str(value) for value in label_ids)}"
        )
    if spec is not PANCREAS and {
        key: str(value).lower() for key, value in metadata["labels"].items()
    } != dict(spec.source_labels):
        # The same IDs name other structures in other releases (Task03 liver/cancer).
        # Task07 keeps its original ID-only check.
        raise MedicalDataError(
            f"dataset.json label names {metadata['labels']} are not the {spec.dataset} labels"
        )
    entries: list[tuple[Path, Path | None]] = []
    for entry in training:
        if not isinstance(entry, dict) or "image" not in entry or "label" not in entry:
            raise MedicalDataError(f"each {name} training entry must declare image and label")
        entries.append(
            (
                _source_path(source, entry["image"], where="training image"),
                _source_path(source, entry["label"], where="training label"),
            )
        )
    entries.extend((_source_path(source, entry, where="test image"), None) for entry in testing)
    _check_entries(entries)
    declared_files = {image for image, _ in entries} | {
        label for _, label in entries if label is not None
    }
    found_files = {
        path.resolve()
        for folder in ("imagesTr", "imagesTs", "labelsTr")
        for path in (source / folder).rglob("*")
        if path.is_file() and path.name.lower().endswith((".nii", ".nii.gz"))
    }
    if found_files != declared_files:
        raise MedicalDataError(
            f"NIfTI files on disk do not exactly match the declared {name} image/reference inventory"
        )
    return _publish_audit(
        source,
        entries,
        spec,
        output,
        metadata_path=metadata_path,
        source_ontology=metadata["labels"],
        groups_path=groups_path,
        duplicate_links_path=duplicate_links_path,
        geometry=geometry,
    )


def audit_kits23(
    root: str | Path,
    output: str | Path,
    *,
    groups_path: str | Path | None = None,
    duplicate_links_path: str | Path | None = None,
    geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit the KiTS23 ``case_*/imaging.nii.gz`` + ``segmentation.nii.gz`` layout.

    ``root`` is the repository's ``dataset`` directory with ``kits23.json``.
    Only the consensus ``segmentation.nii.gz`` is a reference; the per-annotator
    ``instances`` files are not used. KiTS23 declares no label metadata file,
    so the source ontology is the documented 0/1/2/3 background/kidney/tumor/cyst.
    """
    if Path(output).exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    from .dataset_profiles import KIDNEY

    source = Path(root).expanduser().resolve()
    metadata_path = source / "kits23.json"
    metadata = _read_json(metadata_path, expect=list)
    declared = [
        _text(item.get("case_id") if isinstance(item, dict) else None, "case_id")
        for item in metadata
    ]
    if not declared or len(declared) != len(set(declared)):
        raise MedicalDataError("kits23.json must list each case exactly once")
    directories = sorted(path for path in source.iterdir() if path.is_dir())
    if [path.name for path in directories] != sorted(declared) or any(
        not re.fullmatch(r"case_[0-9]{5}", key) for key in declared
    ):
        raise MedicalDataError("case directories do not exactly match the kits23.json case list")
    entries: list[tuple[Path, Path | None]] = []
    for directory in directories:
        volumes = {
            path.name
            for path in directory.iterdir()
            if path.is_file() and path.name.lower().endswith((".nii", ".nii.gz"))
        }
        if volumes != {"imaging.nii.gz", "segmentation.nii.gz"}:
            raise MedicalDataError(
                f"{directory.name}: expected exactly imaging.nii.gz and segmentation.nii.gz"
            )
        entries.append(
            (
                _source_path(source, f"{directory.name}/imaging.nii.gz", where="image"),
                _source_path(source, f"{directory.name}/segmentation.nii.gz", where="label"),
            )
        )
    _check_entries(entries, case_id=lambda image: image.parent.name)
    return _publish_audit(
        source,
        entries,
        KIDNEY,
        output,
        metadata_path=metadata_path,
        source_ontology=dict(KIDNEY.source_labels),
        groups_path=groups_path,
        duplicate_links_path=duplicate_links_path,
        geometry=geometry,
        case_id=lambda image: image.parent.name,
    )


def _check_entries(entries: list[tuple[Path, Path | None]], case_id: Any = None) -> None:
    ids = [(case_id or _case_id)(image) for image, _ in entries]
    if len(ids) != len(set(ids)) or len({image for image, _ in entries}) != len(entries):
        raise MedicalDataError("duplicate case identity or repeated image in source manifest")
    mask_paths = [label for _, label in entries if label is not None]
    if len(mask_paths) != len(set(mask_paths)):
        raise MedicalDataError("a reference mask is reused for more than one case")


def _duplicate_links(path: str | Path, ids: list[str]) -> dict[str, Any]:
    """Union confirmed content-duplicate links into named groups.

    Each link is ``{"cases": [a, b, ...], "evidence": "..."}``. Linked scans
    are kept in one partition even when their bytes and voxels differ, for
    example a re-exported copy with an intensity offset.
    """
    document = _read_json(path)
    links = document.get("links")
    if not isinstance(links, list) or not links:
        raise MedicalDataError("duplicate links need a nonempty links list")
    parents = {key: key for key in ids}

    def find(key: str) -> str:
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    evidence: dict[frozenset[str], str] = {}
    for link in links:
        cases = link.get("cases") if isinstance(link, dict) else None
        if (
            not isinstance(cases, list)
            or len(cases) < 2
            or len(set(cases)) != len(cases)
            or not set(cases) <= set(parents)
        ):
            raise MedicalDataError("each duplicate link needs two or more distinct known cases")
        evidence[frozenset(cases)] = _text(link.get("evidence"), "duplicate link evidence")
        for other in cases[1:]:
            left, right = find(cases[0]), find(other)
            parents[max(left, right)] = min(left, right)
    members: dict[str, list[str]] = {}
    for key in sorted(ids):
        members.setdefault(find(key), []).append(key)
    groups = []
    for cases in sorted(value for value in members.values() if len(value) > 1):
        groups.append(
            {
                "group": "duplicate:" + "+".join(cases),
                "cases": cases,
                "evidence": sorted(text for link, text in evidence.items() if link <= set(cases)),
            }
        )
    return {"source_sha256": sha256_file(path), "groups": groups}


def _publish_audit(
    source: Path,
    entries: list[tuple[Path, Path | None]],
    spec: DatasetProfile,
    output: str | Path,
    *,
    metadata_path: Path,
    source_ontology: dict[str, Any],
    groups_path: str | Path | None,
    duplicate_links_path: str | Path | None,
    geometry: dict[str, Any] | None,
    case_id: Any = None,
) -> dict[str, Any]:
    identify = case_id or _case_id
    ids = [identify(image) for image, _ in entries]
    mask_paths = [label for _, label in entries if label is not None]
    relaxed = check_geometry_policy(geometry)
    groups: dict[str, Any] = {}
    if groups_path is not None:
        group_doc = _read_json(groups_path)
        groups = group_doc.get("groups", group_doc)
        if not isinstance(groups, dict) or set(groups) != set(ids):
            raise MedicalDataError(
                "patient/group mapping must cover every declared case exactly, including unlabeled cases"
            )
        groups = {key: _text(value, f"group for {key}") for key, value in groups.items()}
    grouping = "provided_patient_mapping" if groups_path is not None else "dataset_case_unverified"
    duplicates = (
        None if duplicate_links_path is None else _duplicate_links(duplicate_links_path, ids)
    )
    duplicate_of = {
        key: group["group"]
        for group in (duplicates or {"groups": []})["groups"]
        for key in group["cases"]
    }
    label_ids = tuple(sorted(spec.ontology.values()))
    cases = []
    relaxation_counts: Counter[str] = Counter()
    for image, label in sorted(entries, key=lambda item: identify(item[0])):
        key = identify(image)
        image_info = validate_nifti(image, **relaxed)
        label_info = None
        if label is not None:
            label_info = validate_nifti(label, is_label=True, allowed_labels=label_ids, **relaxed)
            assert_same_geometry(image_info, label_info, where=key)
        case: dict[str, Any] = {
            "case_id": key,
            "patient_id": groups.get(key, f"{spec.dataset}:{key}"),
            "grouping_status": grouping,
            "source": spec.dataset,
            "image": str(image),
            "label": str(label) if label is not None else None,
            "annotation_status": "labeled" if label is not None else "unlabeled",
            "image_sha256": image_info["sha256"],
            "image_voxel_sha256": image_info["voxel_sha256"],
            "label_sha256": label_info["sha256"] if label_info else None,
            "shape": image_info["shape"],
            "spacing_mm": image_info["spacing_mm"],
            "affine": image_info["affine"],
            "label_counts": label_info["label_counts"] if label_info else None,
        }
        if geometry is not None:
            case["geometry_relaxations"] = {
                "image": image_info.get("geometry_relaxations", []),
                "label": label_info.get("geometry_relaxations", []) if label_info else None,
            }
            for info in (image_info, label_info):
                for item in (info or {}).get("geometry_relaxations", []):
                    relaxation_counts[item["relaxation"]] += 1
        if key in duplicate_of:
            case["duplicate_group"] = duplicate_of[key]
        cases.append(case)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset": spec.dataset,
        "source_root": str(source),
        "ontology": dict(spec.ontology),
        "source_ontology": source_ontology,
        "source_metadata_sha256": sha256_file(metadata_path),
        "grouping_status": grouping,
        "cases": cases,
        "audit": {
            "passed": True,
            "fully_decoded_images": len(cases),
            "fully_decoded_labels": len(mask_paths),
            "annotation_counts": dict(Counter(case["annotation_status"] for case in cases)),
            "patient_identity_verified": False,
            "grouping_note": "A supplied mapping is user-provided provenance, not independently verified clinical identity.",
            "clinical_label_note": spec.clinical_label_note,
        },
    }
    if geometry is not None:
        manifest["geometry_policy"] = dict(geometry)
        manifest["audit"]["geometry_relaxation_files"] = dict(sorted(relaxation_counts.items()))
    if duplicates is not None:
        manifest["duplicate_links"] = duplicates
    manifest["fingerprint"] = fingerprint(manifest)
    _validate_manifest(manifest, verify_files=False)
    atomic_write_json(output, manifest)
    return manifest


def _valid_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _validate_manifest(manifest: dict[str, Any], *, verify_files: bool) -> None:
    if type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        raise MedicalDataError("unsupported manifest schema or label ontology")
    profile = profile_for_ontology(manifest.get("ontology"))
    if "geometry_policy" in manifest:
        check_geometry_policy(manifest["geometry_policy"])
    if not _valid_hash(manifest.get("fingerprint")) or manifest["fingerprint"] != fingerprint(
        manifest
    ):
        raise MedicalDataError("manifest fingerprint mismatch")
    if not isinstance(manifest.get("audit"), dict) or manifest["audit"].get("passed") is not True:
        raise MedicalDataError("manifest does not contain a passing audit")
    source = Path(_text(manifest.get("source_root"), "source_root"))
    if not source.is_absolute():
        raise MedicalDataError("source_root must be absolute")
    _text(manifest.get("dataset"), "dataset")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise MedicalDataError("manifest needs a nonempty cases list")
    seen: set[str] = set()
    image_paths: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise MedicalDataError("each case must be an object")
        case_id = _text(case.get("case_id"), "case_id")
        if case_id != case.get("case_id") or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*", case_id
        ):
            raise MedicalDataError("case_id must be a safe normalized filename identifier")
        if case_id in seen:
            raise MedicalDataError(f"duplicate case ID {case_id}")
        seen.add(case_id)
        patient_id = _text(case.get("patient_id"), f"{case_id} patient/group ID")
        if patient_id != case.get("patient_id"):
            raise MedicalDataError(
                "patient/group IDs must be normalized without surrounding whitespace"
            )
        _text(case.get("source"), f"{case_id} source")
        annotation_policy(case, manifest["ontology"])
        relaxations = case.get("geometry_relaxations")
        if relaxations is not None and (
            "geometry_policy" not in manifest
            or not isinstance(relaxations, dict)
            or set(relaxations) != {"image", "label"}
            or not isinstance(relaxations["image"], list)
            or not isinstance(relaxations["label"], (list, type(None)))
        ):
            raise MedicalDataError(f"{case_id}: geometry relaxations need a manifest policy")
        if relaxations is not None:
            _check_case_relaxations(case_id, relaxations, manifest["geometry_policy"])
        if case.get("image_voxel_sha256") is not None and not _valid_hash(
            case["image_voxel_sha256"]
        ):
            raise MedicalDataError("invalid decoded voxel content hash")
        image = _text(case.get("image"), f"{case_id} image")
        if image in image_paths:
            raise MedicalDataError("image path reused by multiple cases")
        image_paths.add(image)
        if case["annotation_status"] == "unlabeled":
            if case.get("label") is not None or case.get("label_sha256") is not None:
                raise MedicalDataError("unlabeled cases cannot carry a segmentation reference")
        elif not case.get("label"):
            raise MedicalDataError("labeled/organ-only case is missing its reference")
        label_counts = case.get("label_counts")
        if label_counts is not None:
            allowed = (
                {"0", str(profile.host_label)}
                if case["annotation_status"] == "organ_only"
                else {str(value) for value in manifest["ontology"].values()}
            )
            if (
                case["annotation_status"] == "unlabeled"
                or not isinstance(label_counts, dict)
                or not set(label_counts) <= allowed
                or any(type(count) is not int or count < 0 for count in label_counts.values())
            ):
                raise MedicalDataError("label count metadata contradicts annotation availability")
        for kind in ("image", "label"):
            value = case.get(kind)
            if value is None:
                continue
            path = Path(_text(value, f"{case_id} {kind}"))
            if not path.is_absolute() or not path.resolve().is_relative_to(source.resolve()):
                raise MedicalDataError("case paths must be absolute and inside source_root")
            if not _valid_hash(case.get(f"{kind}_sha256")):
                raise MedicalDataError(f"{case_id}: missing/invalid {kind} content hash")
            if verify_files and (not path.is_file() or sha256_file(path) != case[f"{kind}_sha256"]):
                raise MedicalDataError(f"{case_id}: {kind} contents changed after audit")
        shape = case.get("shape")
        spacing = case.get("spacing_mm")
        if (
            not isinstance(shape, list)
            or len(shape) != 3
            or any(type(size) is not int or size <= 0 for size in shape)
        ):
            raise MedicalDataError(f"{case_id}: invalid 3D shape")
        if (
            not isinstance(spacing, list)
            or len(spacing) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
                for value in spacing
            )
        ):
            raise MedicalDataError(f"{case_id}: invalid physical spacing")
        # Local import keeps module import light; geometry helpers also validate
        # real-file affines during the full payload audit.
        import numpy as np

        affine = np.asarray(case.get("affine"), dtype=float)
        if (
            affine.shape != (4, 4)
            or not np.isfinite(affine).all()
            or abs(float(np.linalg.det(affine[:3, :3]))) < 1e-8
        ):
            raise MedicalDataError(f"{case_id}: invalid affine")
        if not np.allclose(affine[3], [0, 0, 0, 1], atol=1e-7, rtol=0) or not np.allclose(
            np.linalg.norm(affine[:3, :3], axis=0), spacing, atol=1e-4, rtol=1e-4
        ):
            raise MedicalDataError(f"{case_id}: affine/spacing disagreement")
    _validate_duplicate_links(manifest, cases)
    inherited = manifest.get("inherited_group_assignments")
    if inherited is not None and (
        not isinstance(inherited, dict)
        or set(inherited) != seen
        or any(
            not isinstance(value, str) or not value.strip() or value != value.strip()
            for value in inherited.values()
        )
    ):
        raise MedicalDataError("inherited group assignments must cover all subset cases")


def _check_case_relaxations(case_id: str, relaxations: dict, policy: dict[str, Any]) -> None:
    """Every recorded per-file relaxation must be one the manifest policy allows."""
    for item in [*relaxations["image"], *(relaxations["label"] or [])]:
        kind = item.get("relaxation") if isinstance(item, dict) else None
        if kind == "unknown_spatial_units_as_mm" and set(item) == {"relaxation"}:
            allowed = policy["unknown_spatial_units_as_mm"] is True
        elif kind == "qform_sform_tolerance" and set(item) == {
            "relaxation",
            "max_abs_difference_mm",
        }:
            difference = item["max_abs_difference_mm"]
            allowed = (
                not isinstance(difference, bool)
                and isinstance(difference, (int, float))
                and 0 <= difference <= policy["qform_sform_atol_mm"]
            )
        else:
            allowed = False
        if not allowed:
            raise MedicalDataError(f"{case_id}: geometry relaxation {item!r} exceeds its policy")


def _validate_duplicate_links(manifest: dict[str, Any], cases: list[dict[str, Any]]) -> None:
    """Every case's duplicate group is a recorded link group listing exactly its present members."""
    present = {case["case_id"]: case.get("duplicate_group") for case in cases}
    record = manifest.get("duplicate_links")
    if record is None:
        if any(value is not None for value in present.values()):
            raise MedicalDataError("duplicate groups need a duplicate_links record")
        return
    groups = record.get("groups") if isinstance(record, dict) else None
    if not isinstance(groups, list) or not _valid_hash(record.get("source_sha256")):
        raise MedicalDataError("duplicate_links needs its source hash and a groups list")
    members: dict[str, set[str]] = {}
    for group in groups:
        name = group.get("group") if isinstance(group, dict) else None
        listed = group.get("cases") if isinstance(group, dict) else None
        if (
            not isinstance(name, str)
            or not name.startswith("duplicate:")
            or name in members
            or not isinstance(listed, list)
            or not listed
            or not set(listed) <= set(present)
            or not isinstance(group.get("evidence"), list)
            or not all(isinstance(text, str) and text for text in group["evidence"])
        ):
            raise MedicalDataError("invalid duplicate link group")
        members[name] = set(listed)
    for key, name in present.items():
        if name is not None and (name not in members or key not in members[name]):
            raise MedicalDataError(f"{key}: duplicate group is not a recorded link")
    if any(present[key] != name for name, keys in members.items() for key in keys):
        raise MedicalDataError("duplicate link members must carry their group")


def load_manifest(path: str | Path, verify_files: bool = False) -> dict[str, Any]:
    manifest = _read_json(path)
    _validate_manifest(manifest, verify_files=verify_files)
    return manifest


def subset_manifest(
    manifest_path: str | Path, output: str | Path, case_ids: list[str]
) -> dict[str, Any]:
    """Create a traceable smoke/overfit subset without rewriting case identity."""
    if Path(output).exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    if (
        not case_ids
        or any(not isinstance(key, str) for key in case_ids)
        or len(case_ids) != len(set(case_ids))
    ):
        raise MedicalDataError("subset requires a nonempty list of distinct case IDs")
    parent = load_manifest(manifest_path, verify_files=True)
    cases = {case["case_id"]: case for case in parent["cases"]}
    if not set(case_ids) <= set(cases):
        raise MedicalDataError("subset contains an unknown case ID")
    result = {
        key: value for key, value in parent.items() if key not in ("fingerprint", "audit", "cases")
    }
    result["parent_manifest_fingerprint"] = parent["fingerprint"]
    result["subset_purpose"] = "engineering_smoke_or_overfit_only"
    parent_groups = _group_assignments(cases, parent.get("inherited_group_assignments"))
    result["inherited_group_assignments"] = {key: parent_groups[key] for key in sorted(case_ids)}
    result["cases"] = [cases[key] for key in sorted(case_ids)]
    if "duplicate_links" in parent:
        chosen = set(case_ids)
        result["duplicate_links"] = {
            **parent["duplicate_links"],
            "groups": [
                {**group, "cases": [key for key in group["cases"] if key in chosen]}
                for group in parent["duplicate_links"]["groups"]
                if chosen & set(group["cases"])
            ],
        }
    result["audit"] = {
        **parent["audit"],
        "fully_decoded_images": len(case_ids),
        "fully_decoded_labels": sum(cases[key]["label"] is not None for key in case_ids),
        "annotation_counts": dict(Counter(cases[key]["annotation_status"] for key in case_ids)),
        "scope": "subset of a fully audited parent; file hashes reverified",
    }
    result["fingerprint"] = fingerprint(result)
    _validate_manifest(result, verify_files=False)
    atomic_write_json(output, result)
    return result


def validate_splits(manifest: dict[str, Any], splits: dict[str, Any]) -> None:
    """Reject missing/extra cases and group/content leakage across partitions."""
    _validate_manifest(manifest, verify_files=False)
    if (
        splits.get("schema_version") != 1
        or splits.get("manifest_fingerprint") != manifest["fingerprint"]
    ):
        raise MedicalDataError("split schema/manifest identity mismatch")
    if splits.get("fingerprint") != fingerprint(splits):
        raise MedicalDataError("split fingerprint mismatch")
    cases = {case["case_id"]: case for case in manifest["cases"]}
    eligible = {
        key
        for key, case in cases.items()
        if annotation_policy(case, manifest["ontology"])["semantic_training_allowed"]
    }
    components = _group_assignments(cases, manifest.get("inherited_group_assignments"))
    assigned: dict[str, str] = {}
    owners: dict[tuple[str, str], str] = {}
    for name in SPLIT_NAMES:
        entries = splits.get(name)
        if not isinstance(entries, list) or any(not isinstance(key, str) for key in entries):
            raise MedicalDataError(f"{name}: expected a list of case IDs")
        for key in entries:
            if key not in eligible:
                raise MedicalDataError(f"{name}: unknown or not fully labeled case {key!r}")
            if key in assigned:
                raise MedicalDataError(f"case {key!r} appears more than once in splits")
            assigned[key] = name
            # Components include unlabeled/organ-only companions, so an excluded
            # series cannot bridge two patients/content duplicates across folds.
            for identity in [("component", components[key]), *_identities(cases[key])]:
                if identity in owners and owners[identity] != name:
                    raise MedicalDataError(
                        "patient/group or duplicate image contents leak across splits"
                    )
                owners[identity] = name
    if set(assigned) != eligible:
        raise MedicalDataError("split lists must cover every fully labeled case exactly once")
    if not splits["train"]:
        raise MedicalDataError("training split must not be empty")
    if manifest.get("dataset") == "PanTS" or any(
        case.get("source") == "PanTS" for case in manifest["cases"]
    ):
        from .pants import validate_official_partitions

        validate_official_partitions(manifest, splits)
    # Unlabeled companions remain outside fitting/scoring, but do not constitute
    # an independent future test when they share a patient or image with any split.
    expected_excluded = sorted(set(cases) - eligible)
    if (
        "excluded_unlabeled_or_partial" in splits
        and splits["excluded_unlabeled_or_partial"] != expected_excluded
    ):
        raise MedicalDataError("split excluded-case accounting disagrees with manifest")


def _identities(case: dict[str, Any]) -> list[tuple[str, str]]:
    result = [("patient", case["patient_id"]), ("file", case["image_sha256"])]
    if case.get("image_voxel_sha256"):
        result.append(("voxels", case["image_voxel_sha256"]))
    if case.get("duplicate_group"):
        # A confirmed content duplicate whose bytes and voxels differ.
        result.append(("duplicate", case["duplicate_group"]))
    return result


def predictable_unlabeled_cases(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Unlabeled case IDs safe to predict, and those excluded as copies of labelled cases.

    An unlabeled scan that shares a patient, file, voxel or confirmed duplicate
    identity with any labelled or partial case (development or test) is the same
    data as that case: LiTS ``liver_137`` duplicates training case ``liver_74``.
    Such scans are excluded, never predicted as "unlabeled".
    """
    linked = {
        identity
        for case in manifest["cases"]
        if case["annotation_status"] != "unlabeled"
        for identity in _identities(case)
    }
    kept: list[str] = []
    excluded: list[str] = []
    for case in manifest["cases"]:
        if case["annotation_status"] != "unlabeled":
            continue
        target = excluded if linked.intersection(_identities(case)) else kept
        target.append(case["case_id"])
    return kept, excluded


def _group_assignments(
    cases: dict[str, dict[str, Any]], inherited: dict[str, str] | None = None
) -> dict[str, str]:
    parents = {key: key for key in cases}

    def find(key: str) -> str:
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    owners: dict[tuple[str, str], str] = {}
    for key, case in sorted(cases.items()):
        identities = _identities(case)
        if inherited is not None:
            identities.append(("inherited", inherited[key]))
        for identity in identities:
            if identity in owners:
                left, right = find(key), find(owners[identity])
                parents[max(left, right)] = min(left, right)
            owners[identity] = key
    return {key: find(key) for key in cases}


def make_splits(
    manifest_path: str | Path,
    output: str | Path,
    train_fraction: float = 0.7,
    val_fraction: float = 0.15,
    seed: int = 0,
    *,
    stratify: bool = False,
) -> dict[str, Any]:
    """Split connected patient/duplicate groups, including unlabeled companions.

    Fractions apply to indivisible groups, not slices or necessarily equal case
    counts. Unlabeled and organ-only cases are explicitly excluded from lists.
    ``stratify`` balances the summed annotated lesion volume of each group
    (``stratified_partitions``); the default seeded shuffle is unchanged.
    """
    if type(stratify) is not bool:
        raise MedicalDataError("stratify must be a boolean")
    if Path(output).exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise MedicalDataError("seed must be an integer in [0, 2**32)")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in (train_fraction, val_fraction)
    ):
        raise MedicalDataError("split fractions must be finite numbers")
    if train_fraction <= 0 or val_fraction < 0 or train_fraction + val_fraction > 1:
        raise MedicalDataError("train fraction must be positive and train + val at most 1")
    manifest = load_manifest(manifest_path, verify_files=True)
    if manifest.get("dataset") == "PanTS" or any(
        case.get("source") == "PanTS" for case in manifest["cases"]
    ):
        raise MedicalDataError(
            "PanTS requires split-pants to preserve its official train/test boundary"
        )
    cases = {case["case_id"]: case for case in manifest["cases"]}
    components = _group_assignments(cases, manifest.get("inherited_group_assignments"))
    groups: dict[str, list[str]] = {}
    for key, case in sorted(cases.items()):
        if annotation_policy(case)["semantic_training_allowed"]:
            groups.setdefault(components[key], []).append(key)
    remainder = 1 - train_fraction - val_fraction
    # Float rounding (0.7 + 0.3, 0.85 + 0.15) must not request a one-group test set.
    fractions = [train_fraction, val_fraction, remainder if remainder > 1e-9 else 0.0]
    count = len(groups)
    if count < sum(value > 0 for value in fractions):
        raise MedicalDataError("not enough independent groups for requested nonempty partitions")
    ideal = [count * value for value in fractions]
    sizes = [math.floor(value) for value in ideal]
    for index in sorted(range(3), key=lambda index: (-(ideal[index] - sizes[index]), index))[
        : count - sum(sizes)
    ]:
        sizes[index] += 1
    for index, fraction in enumerate(fractions):
        if fraction > 0 and sizes[index] == 0:
            donor = max(range(3), key=lambda item: sizes[item])
            sizes[donor] -= 1
            sizes[index] += 1
    keys = sorted(groups)
    rng = random.Random(seed)
    rng.shuffle(keys)
    assignment = None
    if stratify:
        profile = profile_for_ontology(manifest["ontology"])
        volumes = {
            group: sum(lesion_volume_ml(cases[key], profile.lesion_labels) for key in members)
            for group, members in groups.items()
        }
        keys, block = stratified_partitions(keys, volumes, sizes, rng)
        assignment = {
            "unit": "connected patient/duplicate group",
            **lesion_stratification(profile),
            "block_size": block,
        }
    splits: dict[str, Any] = {
        "schema_version": 1,
        "manifest_fingerprint": manifest["fingerprint"],
        "seed": seed,
        "requested_group_fractions": dict(zip(SPLIT_NAMES, fractions, strict=True)),
        "grouping_status": manifest.get("grouping_status", "unspecified"),
        "excluded_unlabeled_or_partial": sorted(
            key
            for key, case in cases.items()
            if not annotation_policy(case)["semantic_training_allowed"]
        ),
        "group_counts": dict(zip(SPLIT_NAMES, sizes, strict=True)),
        "group_assignments": {key: components[key] for key in sorted(cases)},
    }
    if assignment is not None:
        splits["assignment"] = assignment
    offset = 0
    for name, size in zip(SPLIT_NAMES, sizes, strict=True):
        splits[name] = sorted(
            case_id for group in keys[offset : offset + size] for case_id in groups[group]
        )
        offset += size
    splits["fingerprint"] = fingerprint(splits)
    validate_splits(manifest, splits)
    atomic_write_json(output, splits)
    return splits


def lesion_volume_ml(case: dict[str, Any], labels: tuple[int, ...]) -> float:
    """Annotated lesion volume in mL from audited label counts; an absent label is zero."""
    counts, spacing = case.get("label_counts"), case.get("spacing_mm")
    if not isinstance(counts, dict) or not isinstance(spacing, list) or len(spacing) != 3:
        raise MedicalDataError(f"{case.get('case_id')}: label counts and spacing are required")
    voxels = [counts.get(str(label), 0) for label in labels]
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in voxels) or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) for v in spacing
    ):
        raise MedicalDataError(f"{case.get('case_id')}: invalid label counts or spacing")
    return sum(voxels) * math.prod(float(value) for value in spacing) / 1000.0


def lesion_stratification(profile: DatasetProfile) -> dict[str, str]:
    """How a lesion-volume stratified assignment is described in split records."""
    labels = "+".join(str(label) for label in profile.lesion_labels)
    return {
        "method": f"{profile.lesion}_volume_stratified_blocks",
        "stratification_variable": f"summed annotated {profile.lesion} volume in mL "
        f"(label {labels} voxels x voxel volume)",
    }


def stratified_partitions(
    keys: list[str], volumes: dict[str, float], sizes: list[int], rng: random.Random
) -> tuple[list[str], int]:
    """Order groups so consecutive train/val/test slices are volume stratified.

    Groups are stably sorted by volume (the seeded shuffle breaks ties) and cut
    into blocks. Within each block the partition counts follow sequential
    apportionment (the partition furthest below its exact running share is
    next), so each partition covers the whole volume range, and the block's
    labels are assigned to its groups in seeded random order. Final counts are
    exactly ``sizes``. The returned key order lists train, then val, then test.
    """
    ordered = sorted(keys, key=lambda key: volumes[key])
    positive = [size for size in sizes if size > 0]
    # About one group of the smallest nonempty partition per block.
    block = max(2, math.ceil(len(ordered) / min(positive)))
    total, assigned = len(ordered), [0] * len(sizes)
    labels: dict[str, int] = {}
    for start in range(0, total, block):
        members = ordered[start : start + block]
        chosen = []
        for offset in range(len(members)):
            step = start + offset + 1
            # Lowest index wins exact ties; a full partition is never chosen.
            _, index = max(
                (sizes[i] * step / total - assigned[i], -i)
                for i in range(len(sizes))
                if assigned[i] < sizes[i]
            )
            index = -index
            assigned[index] += 1
            chosen.append(index)
        rng.shuffle(chosen)
        labels.update(zip(members, chosen, strict=True))
    result = [key for index in range(len(sizes)) for key in ordered if labels[key] == index]
    return result, block
