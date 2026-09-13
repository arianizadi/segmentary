"""Medical-volume geometry and lossless native-space exports.

Readers are optional imports. Arrays use their NIfTI voxel-axis order, not an
assumed anatomical XYZ order. All accepted NIfTI spatial coordinates are mm.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


class MedicalDataError(ValueError):
    """Data cannot be used without resolving an integrity or geometry problem."""


def _nibabel() -> Any:
    try:
        import nibabel
    except ImportError as exc:
        raise ImportError("NIfTI operations require segmentary[medical] (nibabel).") from exc
    return nibabel


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _affine(value: Any, *, where: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise MedicalDataError(f"{where}: expected a finite 4x4 affine")
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-7, rtol=0):
        raise MedicalDataError(f"{where}: affine has an invalid homogeneous last row")
    if abs(float(np.linalg.det(matrix[:3, :3]))) < 1e-8:
        raise MedicalDataError(f"{where}: singular affine")
    return matrix


def assert_same_geometry(
    left: dict[str, Any], right: dict[str, Any], *, where: str = "image/mask"
) -> None:
    """Reject differing voxel grids; matching dimensions alone is insufficient."""
    if list(left["shape"]) != list(right["shape"]):
        raise MedicalDataError(f"{where}: image/mask shapes differ")
    if not np.allclose(left["affine"], right["affine"], atol=1e-4, rtol=0):
        raise MedicalDataError(f"{where}: image/mask affines differ")


def validate_nifti(
    path: str | Path,
    *,
    is_label: bool = False,
    allowed_labels: tuple[int, ...] | list[int] | None = None,
) -> dict[str, Any]:
    """Fully decode one 3D NIfTI and validate its physical-coordinate contract.

    Unknown spatial units and uncoded fallback affines are rejected; callers
    must resolve those ambiguities from acquisition/source evidence first.
    Stored integer CT values are decoded through the NIfTI scaling proxy.
    """
    source = Path(path).expanduser().resolve()
    if not source.is_file() or not source.name.lower().endswith((".nii", ".nii.gz")):
        raise MedicalDataError(f"not a NIfTI file: {source}")
    nib = _nibabel()
    try:
        source_hash = sha256_file(source)
        volume = nib.load(str(source))
        if len(volume.shape) != 3 or any(int(size) <= 0 for size in volume.shape):
            raise MedicalDataError(f"{source.name}: expected one nonempty 3D volume")
        if volume.header.get_xyzt_units()[0] != "mm":
            raise MedicalDataError(
                f"{source.name}: spatial units must explicitly be mm; resolve/convert source units"
            )
        qform, qcode = volume.get_qform(coded=True)
        sform, scode = volume.get_sform(coded=True)
        if not qcode and not scode:
            raise MedicalDataError(f"{source.name}: no coded qform or sform; geometry is unknown")
        if qcode:
            _affine(qform, where=f"{source.name} qform")
        if scode:
            _affine(sform, where=f"{source.name} sform")
        if qcode and scode and not np.allclose(qform, sform, atol=1e-4, rtol=0):
            raise MedicalDataError(f"{source.name}: conflicting qform/sform affines")
        affine = _affine(volume.affine, where=source.name)
        spacing = np.linalg.norm(affine[:3, :3], axis=0)
        if not np.allclose(volume.header.get_zooms()[:3], spacing, atol=1e-4, rtol=1e-4):
            raise MedicalDataError(f"{source.name}: header spacing disagrees with affine")
        values = np.asanyarray(volume.dataobj)
        if values.dtype.kind not in "biuf" or not np.isfinite(values).all():
            raise MedicalDataError(f"{source.name}: nonnumeric or nonfinite voxel values")
        result: dict[str, Any] = {
            "shape": [int(size) for size in values.shape],
            "spacing_mm": spacing.tolist(),
            "affine": affine.tolist(),
            "spatial_units": "mm",
            "axis_codes": list(nib.aff2axcodes(affine)),
            "sha256": source_hash,
            "intensity_min": float(values.min()),
            "intensity_max": float(values.max()),
        }
        if is_label:
            if not np.equal(values, np.rint(values)).all():
                raise MedicalDataError(f"{source.name}: segmentation contains fractional labels")
            ids, counts = np.unique(values, return_counts=True)
            if allowed_labels is not None and not set(ids.tolist()) <= set(allowed_labels):
                raise MedicalDataError(
                    f"{source.name}: unexpected segmentation labels {ids.tolist()}"
                )
            result["label_counts"] = {
                str(int(label)): int(count) for label, count in zip(ids, counts, strict=True)
            }
        # Standardize decoded scalar representation to identify equal payloads
        # with different gzip/header encodings, without another whole-volume copy.
        digest = hashlib.sha256(str(tuple(values.shape)).encode())
        for plane in values:
            digest.update(np.asarray(plane, dtype="<f8", order="C").tobytes())
        result["voxel_sha256"] = digest.hexdigest()
        if sha256_file(source) != source_hash:
            raise MedicalDataError(f"{source.name}: input changed during full-volume validation")
        return result
    except MedicalDataError:
        raise
    except Exception as exc:
        raise MedicalDataError(
            f"{source.name}: NIfTI decoding/geometry validation failed: {exc}"
        ) from exc


def _save_new_nifti(
    volume: Any,
    destination: Path,
    *,
    allowed_labels: tuple[int, ...] | None,
    expected_geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the saved bytes before an atomic, no-overwrite publication."""
    nib = _nibabel()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to overwrite {destination}")
    if not destination.name.lower().endswith((".nii", ".nii.gz")):
        raise MedicalDataError("NIfTI destination must end in .nii or .nii.gz")
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = ".nii.gz" if destination.name.lower().endswith(".nii.gz") else ".nii"
    fd, temporary = tempfile.mkstemp(prefix=".segmentary-", suffix=suffix, dir=destination.parent)
    os.close(fd)
    try:
        nib.save(volume, temporary)
        result = validate_nifti(
            temporary, is_label=allowed_labels is not None, allowed_labels=allowed_labels
        )
        if expected_geometry is not None:
            assert_same_geometry(expected_geometry, result, where="saved NIfTI geometry round trip")
        with Path(temporary).open("rb") as handle:
            os.fsync(handle.fileno())
        os.link(temporary, destination)  # atomic and fails if another writer won
        result["path"] = str(destination)
        return result
    finally:
        Path(temporary).unlink(missing_ok=True)


def export_native_prediction(
    reference_path: str | Path,
    prediction: Any,
    output_path: str | Path,
    *,
    allowed_labels: tuple[int, ...] = (0, 1, 2),
) -> dict[str, Any]:
    """Export already restored, discrete predictions on the reference CT grid.

    This intentionally refuses implicit resampling. The model adapter must
    invert its recorded preprocessing before invoking this final export.
    """
    destination = Path(output_path).expanduser().absolute()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    reference = validate_nifti(reference_path)
    labels = np.asarray(prediction)
    if list(labels.shape) != reference["shape"]:
        raise MedicalDataError("prediction shape is not the original reference grid")
    if labels.dtype.kind not in "biuf" or not np.isfinite(labels).all():
        raise MedicalDataError("prediction must contain finite discrete labels")
    if not np.equal(labels, np.rint(labels)).all() or not set(np.unique(labels).tolist()) <= set(
        allowed_labels
    ):
        raise MedicalDataError("prediction contains fractional or unexpected labels")
    if not allowed_labels or min(allowed_labels) < 0 or max(allowed_labels) > 65535:
        raise MedicalDataError("export label IDs must fit unsigned 16-bit storage")
    nib = _nibabel()
    affine = np.asarray(reference["affine"])
    dtype = np.uint8 if max(allowed_labels) <= 255 else np.uint16
    volume = nib.Nifti1Image(labels.astype(dtype), affine)
    volume.header.set_xyzt_units("mm")
    volume.set_sform(affine, code=1)
    # qform cannot encode shear. Leaving it uncoded avoids contradictory forms.
    try:
        volume.set_qform(affine, code=1, strip_shears=False)
    except nib.spatialimages.HeaderDataError:
        volume.set_qform(None, code=0)
    return _save_new_nifti(
        volume, destination, allowed_labels=allowed_labels, expected_geometry=reference
    )


def convert_dicom_series(
    series_dir: str | Path,
    output_path: str | Path,
    *,
    mask_path: str | Path | None = None,
) -> dict[str, Any]:
    """Convert one regular, single-frame CT series, with physical slice ordering.

    DICOM LPS coordinates become NIfTI RAS. A mask may select an equivalent
    voxel-axis permutation/flip, but differing physical grids are rejected.
    Enhanced/multiframe CT and irregular/gantry-tilted grids require a separate
    audited converter; they are never silently approximated here.
    """
    try:
        import pydicom
    except ImportError as exc:
        raise ImportError("DICOM conversion requires segmentary[medical] (pydicom).") from exc
    nib = _nibabel()
    directory = Path(series_dir).expanduser().resolve()
    destination = Path(output_path).expanduser().absolute()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    files = sorted(
        path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() == ".dcm"
    )
    if not files:
        raise MedicalDataError("no .dcm files found in the selected single-series directory")
    rows: list[tuple[Path, Any, np.ndarray]] = []
    input_hashes = {path: sha256_file(path) for path in files}
    for path in files:
        try:
            item = pydicom.dcmread(str(path), stop_before_pixels=True)
            if (
                getattr(item, "Modality", None) != "CT"
                or int(getattr(item, "NumberOfFrames", 1)) != 1
            ):
                raise MedicalDataError("only single-frame CT DICOM is supported")
            position = np.asarray(item.ImagePositionPatient, dtype=float)
            rows.append((path, item, position))
        except Exception as exc:
            raise MedicalDataError(
                f"DICOM header validation failed for {path.name}: {exc}"
            ) from exc
    first = rows[0][1]
    try:
        orientation = np.asarray(first.ImageOrientationPatient, dtype=float)
        pixel_spacing = np.asarray(first.PixelSpacing, dtype=float)
        size = (int(first.Rows), int(first.Columns))
        series_uid = str(first.SeriesInstanceUID)
        frame_uid = str(first.FrameOfReferenceUID)
        if (
            orientation.shape != (6,)
            or pixel_spacing.shape != (2,)
            or not series_uid
            or not frame_uid
        ):
            raise MedicalDataError("missing DICOM orientation, spacing or series/frame identity")
        if (
            not np.isfinite(orientation).all()
            or not np.isfinite(pixel_spacing).all()
            or np.any(pixel_spacing <= 0)
        ):
            raise MedicalDataError("invalid DICOM orientation or pixel spacing")
        x, y = orientation[:3], orientation[3:]
        if not np.allclose(
            [np.linalg.norm(x), np.linalg.norm(y), np.dot(x, y)], [1, 1, 0], atol=1e-5, rtol=0
        ):
            raise MedicalDataError("DICOM orientation must contain orthonormal direction cosines")
        normal = np.cross(x, y)
        seen_sop: set[str] = set()
        for _, item, position in rows:
            if (
                str(item.SeriesInstanceUID) != series_uid
                or str(item.FrameOfReferenceUID) != frame_uid
            ):
                raise MedicalDataError("mixed DICOM series or frame of reference")
            uid = str(item.SOPInstanceUID)
            if not uid or uid in seen_sop:
                raise MedicalDataError("duplicate or missing DICOM SOP instance identity")
            seen_sop.add(uid)
            if position.shape != (3,) or not np.isfinite(position).all():
                raise MedicalDataError("invalid DICOM slice position")
            if (int(item.Rows), int(item.Columns)) != size:
                raise MedicalDataError("inconsistent DICOM rows/columns")
            if not np.allclose(item.ImageOrientationPatient, orientation, atol=1e-5, rtol=0):
                raise MedicalDataError("inconsistent DICOM slice orientation")
            if not np.allclose(item.PixelSpacing, pixel_spacing, atol=1e-5, rtol=0):
                raise MedicalDataError("inconsistent DICOM pixel spacing")
        if len(rows) < 2:
            raise MedicalDataError(
                "at least two physical slices are required to establish slice spacing"
            )
        rows.sort(key=lambda row: float(np.dot(row[2], normal)))
        positions = np.stack([row[2] for row in rows])
        distances = np.diff(positions @ normal)
        slice_spacing = float(np.median(distances))
        if slice_spacing <= 1e-5 or not np.allclose(distances, slice_spacing, atol=0.01, rtol=0.01):
            raise MedicalDataError("duplicate or irregular DICOM physical slice spacing")
        expected = positions[0] + np.arange(len(rows))[:, None] * normal * slice_spacing
        if not np.allclose(positions, expected, atol=0.01, rtol=0):
            raise MedicalDataError(
                "DICOM positions are not a regular orthogonal grid (possible gantry tilt)"
            )
        planes = []
        for path, header, _ in rows:
            item = pydicom.dcmread(str(path))
            if int(getattr(item, "SamplesPerPixel", 1)) != 1:
                raise MedicalDataError("CT pixel payload must be single-channel")
            if str(getattr(item, "PhotometricInterpretation", "MONOCHROME2")) != "MONOCHROME2":
                raise MedicalDataError("unsupported CT photometric interpretation")
            if str(getattr(item, "RescaleType", "HU")).upper() != "HU":
                raise MedicalDataError("CT rescale units are not HU")
            if hasattr(item, "ModalityLUTSequence"):
                raise MedicalDataError(
                    "modality LUT requires an explicitly supported conversion path"
                )
            slope, intercept = float(item.RescaleSlope), float(item.RescaleIntercept)
            if not np.isfinite([slope, intercept]).all() or slope == 0:
                raise MedicalDataError("invalid CT rescale slope/intercept")
            pixels = np.asarray(item.pixel_array)
            if pixels.shape != size:
                raise MedicalDataError("DICOM decoded pixel shape differs from its header")
            plane = pixels.astype(np.float64) * slope + intercept
            if not np.isfinite(plane).all() or np.max(np.abs(plane)) > np.finfo(np.float32).max:
                raise MedicalDataError("nonfinite/out-of-range CT HU payload")
            if str(item.SOPInstanceUID) != str(header.SOPInstanceUID):
                raise MedicalDataError("DICOM input changed during conversion")
            planes.append(plane.astype(np.float32))
        array = np.stack(planes, axis=2)
        lps = np.eye(4)
        lps[:3, 0] = y * pixel_spacing[0]  # array axis 0 is DICOM row
        lps[:3, 1] = x * pixel_spacing[1]  # array axis 1 is DICOM column
        lps[:3, 2] = normal * slice_spacing
        lps[:3, 3] = positions[0]
        affine = np.diag([-1.0, -1.0, 1.0, 1.0]) @ lps
        mask_info = None
        if mask_path is not None:
            mask_info = validate_nifti(mask_path, is_label=True, allowed_labels=(0, 1))
            target = np.asarray(mask_info["affine"])
            transform = nib.orientations.ornt_transform(
                nib.orientations.io_orientation(affine), nib.orientations.io_orientation(target)
            )
            original_shape = array.shape
            array = nib.orientations.apply_orientation(array, transform)
            affine = affine @ nib.orientations.inv_ornt_aff(transform, original_shape)
            assert_same_geometry(
                {"shape": list(array.shape), "affine": affine.tolist()},
                mask_info,
                where="converted CT and supplied NIH mask",
            )
        volume = nib.Nifti1Image(array, affine)
        volume.header.set_xyzt_units("mm")
        volume.set_qform(affine, code=1)
        volume.set_sform(affine, code=1)
        if any(sha256_file(path) != input_hashes[path] for path in files):
            raise MedicalDataError("DICOM input files changed during conversion")
        result = _save_new_nifti(
            volume,
            destination,
            allowed_labels=None,
            expected_geometry=mask_info or {"shape": list(array.shape), "affine": affine.tolist()},
        )
        result["conversion"] = {
            "method": "physical-position-ordered-single-frame-CT",
            "source_slice_count": len(rows),
            "source_sha256": [input_hashes[row[0]] for row in rows],
            "mask_sha256": mask_info["sha256"] if mask_info else None,
            "intensity_units": "HU",
            "annotation_status": "organ_only" if mask_info else "unlabeled",
        }
        return result
    except MedicalDataError:
        raise
    except Exception as exc:
        raise MedicalDataError(f"DICOM conversion failed: {exc}") from exc
