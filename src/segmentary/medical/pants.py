"""PanTS public-release intake with immutable labels and official test isolation.

The adapter targets the upstream ImageTr/ImageTe and LabelTr/LabelTe layout.
It preserves the binary originals and produces the shared 0/1/2 ontology in a
separate content-addressed directory. Metadata is provenance, never a feature.
"""

from __future__ import annotations

import ast
import gzip
import math
import os
import random
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

import numpy as np

from .data import (
    ONTOLOGY,
    _group_assignments,
    _read_json,
    _text,
    _validate_manifest,
    atomic_write_json,
    fingerprint,
    load_manifest,
    validate_splits,
)
from .geometry import (
    MedicalDataError,
    _nibabel,
    _save_new_nifti,
    assert_same_geometry,
    sha256_file,
    validate_nifti,
)

DATASET = "PanTS"
PUBLIC_COUNTS = {"train": 9000, "test": 901}
METADATA_COLUMNS = (
    "PanTS ID",
    "shape",
    "spacing",
    "ct phase",
    "sex",
    "age",
    "manufacturer",
    "manufacturer model",
    "study type",
    "site",
    "site detail",
    "site nationality",
    "study year",
    "tumor?",
    "structured report",
)
_XLSX_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _audit_implementation() -> dict[str, str]:
    from . import data, geometry

    return {
        "adapter_sha256": sha256_file(__file__),
        "data_sha256": sha256_file(data.__file__),
        "geometry_sha256": sha256_file(geometry.__file__),
        "numpy_version": np.__version__,
        "nibabel_version": _nibabel().__version__,
    }


def official_partition(case_id: str) -> str:
    """The upstream download scripts fix these public-release boundaries."""
    if not re.fullmatch(r"PanTS_[0-9]{8}", case_id):
        raise MedicalDataError(f"invalid PanTS case ID: {case_id!r}")
    number = int(case_id.removeprefix("PanTS_"))
    if not 1 <= number <= 9901:
        raise MedicalDataError(f"PanTS case ID is outside the public release: {case_id}")
    return "train" if number <= 9000 else "test"


def read_metadata(path: str | Path) -> dict[str, dict[str, str | None]]:
    """Read the observed release XLSX schema without a spreadsheet dependency.

    Only cell values are retained; formulas are rejected. Shared and inline
    strings are supported. There is no clinical patient identifier in this
    release's columns, so PanTS IDs remain unverified patient placeholders.
    """
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            worksheets = [
                name for name in names if re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", name)
            ]
            if worksheets != ["xl/worksheets/sheet1.xml"]:
                raise MedicalDataError("PanTS metadata must contain exactly the release worksheet")
            strings = []
            if "xl/sharedStrings.xml" in names:
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                strings = ["".join(item.itertext()) for item in root.findall("s:si", _XLSX_NS)]
            sheet = ET.fromstring(archive.read(worksheets[0]))
    except (OSError, BadZipFile, ET.ParseError, KeyError) as exc:
        raise MedicalDataError(f"cannot read PanTS metadata XLSX: {exc}") from exc
    rows: list[dict[str, str | None]] = []
    headers: dict[str, str] = {}
    for row in sheet.findall("s:sheetData/s:row", _XLSX_NS):
        values: dict[str, str | None] = {}
        for cell in row.findall("s:c", _XLSX_NS):
            reference = cell.get("r", "")
            match = re.fullmatch(r"([A-Z]+)[0-9]+", reference)
            if not match or match[1] in values or cell.find("s:f", _XLSX_NS) is not None:
                raise MedicalDataError("invalid, duplicate or formula metadata cell")
            raw = cell.find("s:v", _XLSX_NS)
            value = raw.text if raw is not None else None
            if cell.get("t") == "s":
                if value is None or not value.isdigit() or int(value) >= len(strings):
                    raise MedicalDataError("invalid shared string reference in metadata")
                value = strings[int(value)]
            elif cell.get("t") == "inlineStr":
                inline = cell.find("s:is", _XLSX_NS)
                value = "".join(inline.itertext()) if inline is not None else None
            elif cell.get("t") not in (None, "n", "str", "b"):
                raise MedicalDataError("unsupported metadata cell value type")
            values[match[1]] = value
        if not headers:
            if set(values.values()) != set(METADATA_COLUMNS) or len(values) != len(
                METADATA_COLUMNS
            ):
                raise MedicalDataError("PanTS metadata columns differ from the supported release")
            headers = {key: str(value) for key, value in values.items()}
        elif any(value is not None for value in values.values()):
            if not set(values) <= set(headers):
                raise MedicalDataError("metadata row extends beyond declared columns")
            rows.append({name: values.get(column) for column, name in headers.items()})
    if not rows:
        raise MedicalDataError("PanTS metadata has no case rows")
    result: dict[str, dict[str, str | None]] = {}
    for metadata_row in rows:
        case_id = _text(metadata_row.get("PanTS ID"), "PanTS ID")
        official_partition(case_id)
        if case_id in result:
            raise MedicalDataError(f"duplicate case in metadata: {case_id}")
        if metadata_row.get("tumor?") not in ("0", "1"):
            raise MedicalDataError(f"{case_id}: tumor? metadata must explicitly be 0 or 1")
        result[case_id] = metadata_row
    return result


def _inside(root: Path, path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.is_relative_to(root):
        raise MedicalDataError("PanTS original and prepared paths must remain inside dataset root")
    return path


def _normalize_unknown_units(
    path: Path,
    destination: Path,
    metadata: dict[str, str | None],
    *,
    enabled: bool,
) -> tuple[Path, dict[str, Any] | None]:
    """Explicitly resolve only unknown units, preserving every voxel byte.

    Agreement with the release's numeric spacing is required. Affines are
    subsequently subjected to the normal strict audit; no coordinate, shape,
    qform, sform, scaling, or intensity repair is attempted here.
    """
    if not enabled:
        return path, None
    nib = _nibabel()
    try:
        volume = nib.load(str(path))
    except Exception as exc:
        raise MedicalDataError(f"{path.name}: cannot inspect normalization source: {exc}") from exc
    if volume.header.get_xyzt_units()[0] != "unknown":
        return path, None
    try:
        declared = np.asarray(ast.literal_eval(str(metadata.get("spacing"))), dtype=float)
    except (ValueError, SyntaxError, TypeError) as exc:
        raise MedicalDataError(
            "unknown-unit normalization requires numeric metadata spacing"
        ) from exc
    observed = np.linalg.norm(volume.affine[:3, :3], axis=0)
    if (
        declared.shape != (3,)
        or not np.isfinite(declared).all()
        or np.any(declared <= 0)
        or not np.allclose(declared, observed, atol=1e-5, rtol=1e-4)
        or not np.allclose(volume.header.get_zooms()[:3], observed, atol=1e-5, rtol=1e-4)
    ):
        raise MedicalDataError(
            f"{path.name}: metadata spacing does not agree with unknown-unit NIfTI grid"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".units-", suffix=".nii.gz", dir=destination.parent)
    try:
        with gzip.open(path, "rb") as reader, os.fdopen(fd, "wb") as raw_writer:
            header = type(volume.header).from_fileobj(reader, check=False)
            original_header = header.binaryblock
            reader.seek(len(original_header))  # Header reader may consume extension records.
            header["xyzt_units"] = (int(header["xyzt_units"]) & ~7) | 2
            changed_header = header.binaryblock
            # Only the spatial unit bits are changed. The remaining compressed
            # stream, including extensions and stored scaled voxel bytes, is copied.
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_writer, mtime=0, compresslevel=1
            ) as writer:
                writer.write(changed_header)
                shutil.copyfileobj(reader, writer, length=8 * 1024 * 1024)
            raw_writer.flush()
            os.fsync(raw_writer.fileno())
        if destination.exists():
            if sha256_file(destination) != sha256_file(temporary):
                raise MedicalDataError("existing normalized copy differs from original payload")
        else:
            os.link(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination, {
        "action": "unknown spatial units to mm; original voxel bytes and coordinate fields unchanged",
        "basis": "explicit opt-in and release metadata spacing agreement",
        "metadata_spacing": declared.tolist(),
        "header_bytes_changed": sum(
            left != right for left, right in zip(original_header, changed_header, strict=True)
        ),
        "original_path": str(path),
        "original_sha256": sha256_file(path),
        "derived_path": str(destination),
        "derived_sha256": sha256_file(destination),
    }


def _normalize_binary_roundoff(
    path: Path,
    destination: Path,
    original: Path,
    *,
    enabled: bool,
) -> tuple[Path, dict[str, Any] | None]:
    """Resolve only <=1e-6 numerical residue around binary labels by opt-in."""
    if not enabled:
        return path, None
    nib = _nibabel()
    try:
        volume = nib.load(str(path))
        values = np.asarray(volume.dataobj)
    except Exception as exc:
        raise MedicalDataError(f"{path.name}: cannot inspect binary mask: {exc}") from exc
    if values.dtype.kind not in "biuf" or not np.isfinite(values).all():
        raise MedicalDataError(f"{path.name}: binary normalization requires finite numeric values")
    rounded = (values >= 0.5).astype(np.uint8)
    difference = float(np.max(np.abs(values.astype(np.float64) - rounded)))
    if difference > 1e-6:
        raise MedicalDataError(
            f"{path.name}: binary mask values exceed absolute roundoff tolerance 1e-6"
        )
    if difference == 0:
        return path, None
    # Full strict coordinate/finite-value audit still applies. This opt-in does
    # not resolve unknown units or repair shapes, coordinate fields, or scaling.
    info = validate_nifti(path)
    if destination.exists():
        derived_info = validate_nifti(destination, is_label=True, allowed_labels=(0, 1))
        assert_same_geometry(info, derived_info, where="binary normalization")
        if not np.array_equal(np.asarray(nib.load(str(destination)).dataobj), rounded):
            raise MedicalDataError("existing binary-normalized mask differs from originals")
    else:
        derived = nib.Nifti1Image(rounded, np.asarray(info["affine"]))
        derived.header.set_xyzt_units("mm")
        _save_new_nifti(derived, destination, allowed_labels=(0, 1), expected_geometry=info)
    original_volume = nib.load(str(original))
    return destination, {
        "action": "normalize only finite binary-label encoding residue to uint8 zero/one",
        "absolute_tolerance": 1e-6,
        "relative_tolerance": 0,
        "maximum_absolute_roundoff": difference,
        "original_path": str(original),
        "original_sha256": sha256_file(original),
        "original_scaling_slope": float(original_volume.dataobj.slope),
        "original_scaling_intercept": float(original_volume.dataobj.inter),
        "input_path": str(path),
        "input_sha256": sha256_file(path),
        "derived_path": str(destination),
        "derived_sha256": sha256_file(destination),
    }


def _prepare_case(
    source: Path,
    prepared: Path,
    case_id: str,
    metadata: dict[str, str | None],
    metadata_hash: str,
    patient_id: str,
    grouping: str,
    allow_missing_negative_lesion: bool,
    normalize_unknown_units_from_metadata: bool = False,
    normalize_binary_roundoff: bool = False,
) -> dict[str, Any]:
    partition = official_partition(case_id)
    suffix = "Tr" if partition == "train" else "Te"
    image = _inside(source, source / f"Image{suffix}" / case_id / "ct.nii.gz")
    folder = source / f"Label{suffix}" / case_id / "segmentations"
    pancreas = _inside(source, folder / "pancreas.nii.gz")
    lesion = _inside(source, folder / "pancreatic_lesion.nii.gz")
    if not image.is_file() or not pancreas.is_file():
        raise MedicalDataError(f"{case_id}: CT or pancreas mask is missing")
    if not lesion.is_file() and not (allow_missing_negative_lesion and metadata["tumor?"] == "0"):
        raise MedicalDataError(
            f"{case_id}: lesion mask is missing; absent files are not negative annotations"
        )
    paths = {"image": image, "pancreas": pancreas}
    if lesion.is_file():
        paths["pancreatic_lesion"] = lesion
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    identity = {
        "schema_version": 1,
        "audit_implementation": _audit_implementation(),
        "case_id": case_id,
        "source_sha256": hashes,
        "metadata_sha256": metadata_hash,
        "patient_id": patient_id,
        "grouping_status": grouping,
        "allow_missing_negative_lesion": allow_missing_negative_lesion,
        "normalize_unknown_units_from_metadata": normalize_unknown_units_from_metadata,
        "normalize_binary_roundoff": normalize_binary_roundoff,
    }
    key = fingerprint(identity)
    destination = prepared / key / f"{case_id}.nii.gz"
    record_path = destination.with_name(f"{case_id}.json")
    if record_path.exists():
        record = _read_json(record_path)
        if record.get("fingerprint") != fingerprint(record) or record.get("identity") != identity:
            raise MedicalDataError(f"{case_id}: prepared case journal is invalid")
        case = record["case"]
        if (
            case.get("label") != str(destination)
            or sha256_file(destination) != case["label_sha256"]
        ):
            raise MedicalDataError(f"{case_id}: prepared label changed after audit")
        if sha256_file(case["image"]) != case["image_sha256"]:
            raise MedicalDataError(f"{case_id}: prepared image changed after audit")
        for record in [
            *case["annotation_provenance"]["unit_normalizations"].values(),
            *case["annotation_provenance"]["binary_roundoff_normalizations"].values(),
        ]:
            if sha256_file(record["derived_path"]) != record["derived_sha256"]:
                raise MedicalDataError(f"{case_id}: normalized input changed after audit")
        return dict(case)
    normalized_paths = {}
    unit_records = {}
    for name, original in paths.items():
        normalized_paths[name], normalization = _normalize_unknown_units(
            original,
            prepared / key / "source-mm" / f"{name}.nii.gz",
            metadata,
            enabled=normalize_unknown_units_from_metadata,
        )
        if normalization:
            unit_records[name] = normalization
    binary_records = {}
    for name in ("pancreas", "pancreatic_lesion"):
        if name in normalized_paths:
            normalized_paths[name], normalization = _normalize_binary_roundoff(
                normalized_paths[name],
                prepared / key / "binary-masks" / f"{name}.nii.gz",
                paths[name],
                enabled=normalize_binary_roundoff,
            )
            if normalization:
                binary_records[name] = normalization
    image = normalized_paths["image"]
    pancreas = normalized_paths["pancreas"]
    lesion = normalized_paths.get("pancreatic_lesion", lesion)
    image_info = validate_nifti(image)
    pancreas_info = validate_nifti(pancreas, is_label=True, allowed_labels=(0, 1))
    assert_same_geometry(image_info, pancreas_info, where=f"{case_id} pancreas")
    nib = _nibabel()
    labels = np.asarray(nib.load(str(pancreas)).dataobj).astype(np.uint8)
    if not np.any(labels):
        raise MedicalDataError(f"{case_id}: pancreas mask is empty; resolve annotation coverage")
    lesion_outside_pancreas = 0
    lesion_info = None
    if "pancreatic_lesion" in paths:
        lesion_info = validate_nifti(lesion, is_label=True, allowed_labels=(0, 1))
        assert_same_geometry(image_info, lesion_info, where=f"{case_id} lesion")
        lesion_values = np.asarray(nib.load(str(lesion)).dataobj)
        has_lesion = bool(np.any(lesion_values))
        if has_lesion != (metadata["tumor?"] == "1"):
            raise MedicalDataError(f"{case_id}: lesion mask contradicts tumor? metadata")
        lesion_outside_pancreas = int(np.count_nonzero((lesion_values == 1) & (labels == 0)))
        labels[lesion_values == 1] = 2
    if destination.exists():
        # An interruption between the immutable volume and journal publications
        # is resumable only after rederiving and comparing the entire payload.
        label_info = validate_nifti(destination, is_label=True, allowed_labels=(0, 1, 2))
        assert_same_geometry(image_info, label_info, where=f"{case_id} prepared label")
        if not np.array_equal(np.asarray(nib.load(str(destination)).dataobj), labels):
            raise MedicalDataError(f"{case_id}: existing prepared volume contradicts originals")
    else:
        # The original CT was already fully decoded and validated above. Save
        # the derived label on that audited affine without decompressing it again.
        volume = nib.Nifti1Image(labels, np.asarray(image_info["affine"]))
        volume.header.set_xyzt_units("mm")
        label_info = _save_new_nifti(
            volume, destination, allowed_labels=(0, 1, 2), expected_geometry=image_info
        )
    if any(sha256_file(path) != hashes[name] for name, path in paths.items()):
        raise MedicalDataError(f"{case_id}: source changed while preparing the case")
    case = {
        "case_id": case_id,
        "patient_id": patient_id,
        "grouping_status": grouping,
        "source": DATASET,
        "official_partition": partition,
        "image": str(image),
        "label": str(destination),
        "annotation_status": "labeled",
        "image_sha256": image_info["sha256"],
        "image_voxel_sha256": image_info["voxel_sha256"],
        "label_sha256": label_info["sha256"],
        "shape": image_info["shape"],
        "spacing_mm": image_info["spacing_mm"],
        "affine": image_info["affine"],
        "label_counts": label_info["label_counts"],
        "source_metadata": metadata,
        "source_metadata_sha256": metadata_hash,
        "annotation_provenance": {
            "pancreas": {"path": str(paths["pancreas"]), "sha256": hashes["pancreas"]},
            "pancreatic_lesion": (
                {"path": str(paths["pancreatic_lesion"]), "sha256": hashes["pancreatic_lesion"]}
                if lesion_info
                else None
            ),
            "lesion_absence_basis": (
                "present_binary_mask" if lesion_info else "explicit_metadata_tumor_0_opt_in"
            ),
            "transformation": "binary pancreas to 1; binary pancreatic_lesion to 2 with lesion precedence",
            "diagnosis": "Lesion annotation does not establish PDAC or malignancy",
            "original_image": {"path": str(paths["image"]), "sha256": hashes["image"]},
            "unit_normalizations": unit_records,
            "binary_roundoff_normalizations": binary_records,
            "lesion_voxels_outside_original_pancreas": lesion_outside_pancreas,
            "identity": key,
        },
    }
    record = {"identity": identity, "case": case}
    record["fingerprint"] = fingerprint(record)
    atomic_write_json(record_path, record)
    return case


def _excluded_identity(
    source: Path,
    prepared: Path,
    case_id: str,
    metadata: dict[str, str | None],
    metadata_hash: str,
    patient_id: str,
    normalize_units: bool,
) -> dict[str, Any]:
    """Retain duplicate/patient bridges even when a reference is quarantined."""
    partition = official_partition(case_id)
    suffix = "Tr" if partition == "train" else "Te"
    original = _inside(source, source / f"Image{suffix}" / case_id / "ct.nii.gz")
    if not original.is_file():
        raise MedicalDataError(
            f"{case_id}: excluded CT identity cannot be audited; image is missing"
        )
    source_hash = sha256_file(original)
    identity = {
        "case_id": case_id,
        "source_sha256": source_hash,
        "metadata_sha256": metadata_hash,
        "patient_id": patient_id,
        "normalize_unknown_units": normalize_units,
        "audit_implementation": _audit_implementation(),
    }
    folder = prepared / "excluded-identities" / fingerprint(identity)
    journal = folder / "identity.json"
    if journal.exists():
        record = _read_json(journal)
        if record.get("fingerprint") != fingerprint(record) or record.get("identity") != identity:
            raise MedicalDataError(f"{case_id}: excluded identity journal is invalid")
        case = record["case"]
        if sha256_file(case["image"]) != case["image_sha256"]:
            raise MedicalDataError(f"{case_id}: excluded identity image changed after audit")
        return dict(case)
    image, normalization = _normalize_unknown_units(
        original, folder / "image.nii.gz", metadata, enabled=normalize_units
    )
    info = validate_nifti(image)
    if sha256_file(original) != source_hash:
        raise MedicalDataError(f"{case_id}: excluded CT changed during identity audit")
    case = {
        "case_id": case_id,
        "patient_id": patient_id,
        "source": DATASET,
        "official_partition": partition,
        "image": str(image),
        "image_sha256": info["sha256"],
        "image_voxel_sha256": info["voxel_sha256"],
        "original_image": str(original),
        "original_image_sha256": source_hash,
        "unit_normalization": normalization,
    }
    record = {"identity": identity, "case": case}
    record["fingerprint"] = fingerprint(record)
    atomic_write_json(journal, record)
    return case


def audit_pants(
    root: str | Path,
    output: str | Path,
    *,
    metadata_path: str | Path | None = None,
    prepared_root: str | Path | None = None,
    groups_path: str | Path | None = None,
    exclude_cases_path: str | Path | None = None,
    audit_report_path: str | Path | None = None,
    case_ids: list[str] | None = None,
    allow_missing_negative_lesion: bool = False,
    normalize_unknown_units_from_metadata: bool = False,
    normalize_binary_roundoff: bool = False,
) -> dict[str, Any]:
    """Audit the entire 9,901-case release or an explicit training-only smoke subset.

    Completed per-case journals are reused after checking the raw and prepared
    content hashes. A failed full audit therefore keeps useful verified work.
    No partial download is labeled a complete release. Test cases never enter a
    smoke subset. Original images, masks, reports and metadata are not modified.
    """
    if Path(output).exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    if audit_report_path is not None and Path(audit_report_path).exists():
        raise FileExistsError(f"refusing to overwrite {audit_report_path}")
    source = Path(root).expanduser().resolve()
    metadata_file = _inside(
        source, Path(metadata_path) if metadata_path else source / "metadata.xlsx"
    )
    prepared = _inside(
        source, Path(prepared_root) if prepared_root else source / "SegmentaryPrepared"
    )
    rows = read_metadata(metadata_file)
    metadata_hash = sha256_file(metadata_file)
    partial = case_ids is not None
    if partial:
        assert case_ids is not None
        if not case_ids or len(set(case_ids)) != len(case_ids) or not set(case_ids) <= set(rows):
            raise MedicalDataError("smoke audit requires distinct known explicit case IDs")
        if any(official_partition(key) != "train" for key in case_ids):
            raise MedicalDataError("smoke audit may use official training cases only")
        selected = sorted(case_ids)
    else:
        expected = {f"PanTS_{number:08d}" for number in range(1, 9902)}
        if set(rows) != expected:
            raise MedicalDataError("full PanTS audit requires all 9,901 official metadata cases")
        for partition, suffix in (("train", "Tr"), ("test", "Te")):
            expected_partition = {key for key in expected if official_partition(key) == partition}
            for prefix in ("Image", "Label"):
                folder = source / f"{prefix}{suffix}"
                found = (
                    {path.name for path in folder.iterdir() if path.is_dir()}
                    if folder.is_dir()
                    else set()
                )
                if found != expected_partition:
                    raise MedicalDataError(
                        f"{folder.name}: complete official inventory is missing or contains unexpected cases"
                    )
        selected = sorted(expected)
    scope_ids = selected.copy()
    exclusions: dict[str, Any] = {}
    if exclude_cases_path is not None:
        exclusion_doc = _read_json(exclude_cases_path)
        raw_exclusions = exclusion_doc.get("exclusions")
        if not isinstance(raw_exclusions, dict) or not set(raw_exclusions) <= set(rows):
            raise MedicalDataError("exclusions must be a mapping of known PanTS cases")
        exclusions = raw_exclusions
        for key, evidence in exclusions.items():
            if not isinstance(evidence, dict):
                raise MedicalDataError(f"{key}: exclusion must contain a reason and source_url")
            _text(evidence.get("reason"), f"{key} exclusion reason")
            url = _text(evidence.get("source_url"), f"{key} exclusion source_url")
            if not url.startswith("https://"):
                raise MedicalDataError(
                    "exclusion source_url must be an explicit HTTPS evidence link"
                )
        if partial and set(selected) & set(exclusions):
            raise MedicalDataError("requested smoke cases include an explicitly excluded case")
        scope_ids = sorted(set(scope_ids) | set(exclusions))
        selected = [key for key in selected if key not in exclusions]
        if not selected:
            raise MedicalDataError("exclusions leave no cases to audit")
    groups = {}
    if groups_path is not None:
        group_doc = _read_json(groups_path)
        groups = group_doc.get("groups", group_doc)
        if (
            not isinstance(groups, dict)
            or not set(scope_ids) <= set(groups)
            or not set(groups) <= set(rows)
        ):
            raise MedicalDataError(
                "patient/group mapping must cover audited cases and contain only known cases"
            )
        groups = {key: _text(value, f"group for {key}") for key, value in groups.items()}
    grouping = "provided_patient_mapping" if groups_path else "dataset_case_unverified"
    cases = []
    failures = []
    for key in selected:
        try:
            cases.append(
                _prepare_case(
                    source,
                    prepared,
                    key,
                    rows[key],
                    metadata_hash,
                    groups.get(key, f"PanTS:{key}"),
                    grouping,
                    allow_missing_negative_lesion,
                    normalize_unknown_units_from_metadata,
                    normalize_binary_roundoff,
                )
            )
        except MedicalDataError as exc:
            if audit_report_path is None:
                raise
            failures.append({"case_id": key, "error": str(exc), "type": type(exc).__name__})
    excluded_identities = []
    for key in sorted(set(scope_ids) & set(exclusions)):
        try:
            excluded_identities.append(
                _excluded_identity(
                    source,
                    prepared,
                    key,
                    rows[key],
                    metadata_hash,
                    groups.get(key, f"PanTS:{key}"),
                    normalize_unknown_units_from_metadata,
                )
            )
        except MedicalDataError as exc:
            if audit_report_path is None:
                raise
            failures.append(
                {
                    "case_id": key,
                    "error": str(exc),
                    "type": type(exc).__name__,
                    "stage": "excluded_identity",
                }
            )
    audit_report = {
        "schema_version": 1,
        "dataset": DATASET,
        "source_metadata_sha256": metadata_hash,
        "audit_implementation": _audit_implementation(),
        "scope": "explicit_training_smoke_subset" if partial else "official_public_release",
        "requested_cases": len(scope_ids),
        "excluded_identity_cases": [case["case_id"] for case in excluded_identities],
        "passed_cases": [case["case_id"] for case in cases],
        "failed_cases": failures,
        "excluded_cases": exclusions,
        "passed": not failures,
        "manifest_written": False,
    }
    if failures:
        audit_report["fingerprint"] = fingerprint(audit_report)
        assert audit_report_path is not None
        atomic_write_json(audit_report_path, audit_report)
        raise MedicalDataError(
            f"PanTS audit failed for {len(failures)} of {len(scope_ids)} cases; "
            f"details in {audit_report_path}. No training manifest was published."
        )
    if sha256_file(metadata_file) != metadata_hash:
        raise MedicalDataError("PanTS metadata changed during audit")
    all_identities = {case["case_id"]: case for case in [*cases, *excluded_identities]}
    inherited = _group_assignments(all_identities)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset": DATASET,
        "source_root": str(source),
        "ontology": ONTOLOGY.copy(),
        "source_ontology": {"pancreas.nii.gz": [0, 1], "pancreatic_lesion.nii.gz": [0, 1]},
        "source_metadata_sha256": metadata_hash,
        "audit_implementation": _audit_implementation(),
        "grouping_status": grouping,
        "official_partition_policy": "PanTS-public-9000-train-901-test-v1",
        "official_release_counts": PUBLIC_COUNTS.copy(),
        "inherited_group_assignments": {
            case["case_id"]: inherited[case["case_id"]] for case in cases
        },
        "excluded_case_identities": excluded_identities,
        "cases": cases,
        "audit": {
            "passed": True,
            "scope": (
                "explicit_training_smoke_subset"
                if partial
                else "public_release_with_exclusions"
                if exclusions
                else "complete_public_release"
            ),
            "complete_public_release": not partial and not exclusions,
            "complete_download_inventory": not partial,
            "excluded_cases": exclusions,
            "excluded_identities_audited": len(excluded_identities),
            "exclusions_outside_explicit_smoke_scope": [],
            "exclusions_sha256": sha256_file(exclude_cases_path) if exclude_cases_path else None,
            "fully_decoded_images": len(cases),
            "fully_decoded_labels": len(cases),
            "source_metadata_cases": len(rows),
            "audited_official_partition_counts": dict(
                Counter(case["official_partition"] for case in cases)
            ),
            "annotation_counts": {"labeled": len(cases)},
            "patient_identity_verified": False,
            "grouping_note": "No original patient crosswalk in release metadata; a supplied mapping remains user-provided provenance.",
            "clinical_label_note": "PanTS includes lesion-positive and annotated lesion-negative CTs; tumor? does not establish PDAC diagnosis.",
            "resume_note": "Previously fully decoded cases may be reused only after raw and prepared hashes are reverified.",
            "missing_negative_lesion_opt_in": allow_missing_negative_lesion,
            "unknown_units_normalization_opt_in": normalize_unknown_units_from_metadata,
            "binary_roundoff_normalization_opt_in": normalize_binary_roundoff,
            "binary_roundoff_normalized_masks": sum(
                len(case["annotation_provenance"]["binary_roundoff_normalizations"])
                for case in cases
            ),
            "unit_normalized_files": sum(
                len(case["annotation_provenance"]["unit_normalizations"]) for case in cases
            ),
        },
    }
    if partial:
        manifest["subset_purpose"] = "engineering_smoke_or_overfit_only"
    manifest["fingerprint"] = fingerprint(manifest)
    _validate_manifest(manifest, verify_files=False)
    atomic_write_json(output, manifest)
    if audit_report_path is not None:
        audit_report["manifest_written"] = True
        audit_report["manifest_fingerprint"] = manifest["fingerprint"]
        audit_report["fingerprint"] = fingerprint(audit_report)
        atomic_write_json(audit_report_path, audit_report)
    return manifest


def validate_official_partitions(manifest: dict[str, Any], splits: dict[str, Any]) -> None:
    """Enforce the release boundary even for handcrafted generic split files."""
    for case in manifest["cases"]:
        if case.get("source") != DATASET and manifest.get("dataset") != DATASET:
            continue
        key = case["case_id"]
        partition = official_partition(key)
        if case.get("source") != DATASET or case.get("official_partition") != partition:
            raise MedicalDataError(
                f"{key}: PanTS official partition provenance is missing or invalid"
            )
        if partition == "test" and (key in splits["train"] or key in splits["val"]):
            raise MedicalDataError("PanTS official test cases cannot enter training or validation")
        if partition == "train" and key in splits["test"]:
            raise MedicalDataError(
                "PanTS official training cases cannot replace the official test cohort"
            )


def make_pants_splits(
    manifest_path: str | Path,
    output: str | Path,
    *,
    val_fraction: float = 0.15,
    seed: int = 0,
) -> dict[str, Any]:
    """Split only official training groups; reserve every official test case."""
    if Path(output).exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise MedicalDataError("seed must be an integer in [0, 2**32)")
    if (
        isinstance(val_fraction, bool)
        or not isinstance(val_fraction, (int, float))
        or not math.isfinite(val_fraction)
        or not 0 < val_fraction < 1
    ):
        raise MedicalDataError(
            "validation fraction must be finite and strictly between zero and one"
        )
    manifest = load_manifest(manifest_path, verify_files=True)
    if manifest.get("dataset") != DATASET:
        raise MedicalDataError("split-pants requires an audited PanTS manifest")
    cases = {case["case_id"]: case for case in manifest["cases"]}
    components = _group_assignments(cases, manifest.get("inherited_group_assignments"))
    groups: dict[str, list[str]] = {}
    test = []
    component_partition: dict[str, str] = {}
    for key in sorted(cases):
        partition = official_partition(key)
        component = components[key]
        if component in component_partition and component_partition[component] != partition:
            raise MedicalDataError(
                "patient or duplicate image spans PanTS official train/test; resolve provenance before splitting"
            )
        component_partition[component] = partition
        if partition == "test":
            test.append(key)
        else:
            groups.setdefault(component, []).append(key)
    if len(groups) < 2:
        raise MedicalDataError("need at least two independent official training groups")
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    val_count = min(len(keys) - 1, max(1, round(len(keys) * val_fraction)))
    splits: dict[str, Any] = {
        "schema_version": 1,
        "manifest_fingerprint": manifest["fingerprint"],
        "seed": seed,
        "split_policy": "train/val within official PanTS train; official test reserved",
        "official_training_validation_group_fraction": val_fraction,
        "grouping_status": manifest.get("grouping_status"),
        "group_assignments": components,
        "group_counts": {
            "train": len(keys) - val_count,
            "val": val_count,
            "test": len({components[key] for key in test}),
        },
        "train": sorted(key for group in keys[val_count:] for key in groups[group]),
        "val": sorted(key for group in keys[:val_count] for key in groups[group]),
        "test": test,
        "excluded_unlabeled_or_partial": [],
        "official_test_complete": len(test) == PUBLIC_COUNTS["test"],
        "external_patient_independence_verified": False,
    }
    splits["fingerprint"] = fingerprint(splits)
    validate_splits(manifest, splits)
    atomic_write_json(output, splits)
    return splits
