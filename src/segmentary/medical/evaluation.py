"""Evaluate saved native-space medical masks, without loading a model.

Dice summaries average examinations within each patient, then patients. Mass
summaries use annotated, reference-positive cases: empty references are reported
separately, never rewarded with perfect tumor Dice. A failed prediction on a
valid positive reference receives zero Dice; reference failures remain unknown
and reduce reference coverage. Surface distances use DeepMind's area-weighted
surfel implementation, with image-axis spacing in millimetres.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


def _spacing(spacing_mm: Sequence[float]) -> tuple[float, float, float]:
    values = np.asarray(spacing_mm, dtype=float)
    if values.shape != (3,) or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("spacing_mm must contain three finite positive values")
    return tuple(float(v) for v in values)  # type: ignore[return-value]


def _binary_pair(reference: np.ndarray, prediction: np.ndarray) -> None:
    if reference.ndim != 3 or prediction.shape != reference.shape:
        raise ValueError("Reference and prediction must have identical three-dimensional shapes")
    if reference.dtype != np.bool_ or prediction.dtype != np.bool_:
        raise ValueError("Binary metric inputs must be boolean arrays")


def _surface_library() -> Any:
    try:
        from surface_distance import metrics
    except ImportError as exc:
        raise ImportError(
            "Medical surface metrics require segmentary[medical] (surface-distance)"
        ) from exc
    return metrics


def binary_segmentation_metrics(
    reference: np.ndarray,
    prediction: np.ndarray,
    spacing_mm: Sequence[float],
    surface_tolerance_mm: float | None = None,
) -> dict[str, Any]:
    """Return Dice, area-weighted HD95 and optionally tolerance-based surface Dice.

    ``None`` is JSON-safe and denotes an undefined/infinite boundary distance,
    not a perfect boundary. ``hd95_status`` distinguishes that from disabled
    surface Dice. For two empty masks even Dice is undefined by design.
    """
    _binary_pair(reference, prediction)
    spacing = _spacing(spacing_mm)
    if surface_tolerance_mm is not None and (
        not math.isfinite(surface_tolerance_mm) or surface_tolerance_mm < 0
    ):
        raise ValueError("surface_tolerance_mm must be finite and nonnegative")
    ref_count, pred_count = int(reference.sum()), int(prediction.sum())
    result: dict[str, Any] = {
        "reference_voxels": ref_count,
        "prediction_voxels": pred_count,
        "reference_volume_ml": ref_count * math.prod(spacing) / 1000,
        "prediction_volume_ml": pred_count * math.prod(spacing) / 1000,
        "dice": None,
        "surface_dice": None,
        "hd95_mm": None,
        "hd95_status": "undefined_both_empty",
        "empty_status": "both_empty",
    }
    if not ref_count and not pred_count:
        return result
    result["dice"] = 2 * int(np.count_nonzero(reference & prediction)) / (ref_count + pred_count)
    if not ref_count or not pred_count:
        result.update(
            empty_status="reference_empty" if not ref_count else "prediction_empty",
            hd95_status="infinite_one_empty",
            surface_dice=0.0 if surface_tolerance_mm is not None else None,
        )
        return result
    library = _surface_library()
    distances = library.compute_surface_distances(reference, prediction, spacing)
    result.update(
        empty_status="neither_empty",
        hd95_mm=float(library.compute_robust_hausdorff(distances, 95)),
        hd95_status="finite",
    )
    if surface_tolerance_mm is not None:
        result["surface_dice"] = float(
            library.compute_surface_dice_at_tolerance(distances, surface_tolerance_mm)
        )
    return result


def patient_bootstrap(
    values: Mapping[str, Sequence[float] | float],
    bootstrap_samples: int = 1000,
    seed: int = 0,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Percentile CI over patients after equal-weight within-patient averaging.

    Input must contain finite scores only; callers explicitly report exclusions
    before passing them here. An interval is not estimated from one patient.
    """
    if bootstrap_samples < 0 or not isinstance(bootstrap_samples, int):
        raise ValueError("bootstrap_samples must be a nonnegative integer")
    if not 0 < confidence < 1:
        raise ValueError("confidence must lie strictly between zero and one")
    means: list[float] = []
    case_count = 0
    for patient_id in sorted(values):
        array = np.atleast_1d(np.asarray(values[patient_id], dtype=float))
        if array.ndim != 1 or not len(array) or not np.isfinite(array).all():
            raise ValueError("Each patient must have one or more finite scalar scores")
        means.append(float(array.mean()))
        case_count += len(array)
    result: dict[str, Any] = {
        "mean": float(np.mean(means)) if means else None,
        "ci": None,
        "confidence": confidence,
        "patients": len(means),
        "cases": case_count,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "unit": "patient",
        "method": "percentile bootstrap of equal-weight patient means",
    }
    if len(means) > 1 and bootstrap_samples:
        rng = np.random.default_rng(seed)
        data = np.asarray(means)
        # One sample at a time avoids an unbounded samples-by-patients allocation.
        estimates = np.asarray(
            [
                data[rng.integers(0, len(data), size=len(data))].mean()
                for _ in range(bootstrap_samples)
            ]
        )
        alpha = (1 - confidence) / 2
        result["ci"] = [float(v) for v in np.quantile(estimates, [alpha, 1 - alpha])]
    return result


def lesion_detection_metrics(
    reference: np.ndarray,
    prediction: np.ndarray,
    spacing_mm: Sequence[float],
    iou_threshold: float,
    connectivity: int = 26,
    minimum_prediction_volume_mm3: float = 0,
) -> dict[str, Any]:
    """Match binary-mask connected components, not clinical diagnoses.

    Maximum-cardinality one-to-one assignment is preferred, then higher total
    IoU. This prevents a greedy match from unnecessarily losing a true positive.
    Reference components are never removed by a prediction size filter.
    """
    from scipy import ndimage
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import min_weight_full_bipartite_matching

    _binary_pair(reference, prediction)
    spacing = _spacing(spacing_mm)
    if not math.isfinite(iou_threshold) or not 0 < iou_threshold <= 1:
        raise ValueError("iou_threshold must lie in (0, 1]")
    if connectivity not in {6, 18, 26}:
        raise ValueError("connectivity must be 6, 18 or 26")
    if not math.isfinite(minimum_prediction_volume_mm3) or minimum_prediction_volume_mm3 < 0:
        raise ValueError("minimum_prediction_volume_mm3 must be finite and nonnegative")
    structure = ndimage.generate_binary_structure(3, {6: 1, 18: 2, 26: 3}[connectivity])
    refs, n_refs = ndimage.label(reference, structure)
    preds, n_preds_before = ndimage.label(prediction, structure)
    pred_sizes = np.bincount(preds.ravel(), minlength=n_preds_before + 1)
    keep = pred_sizes * math.prod(spacing) >= minimum_prediction_volume_mm3
    keep[0] = False
    preds, n_preds = ndimage.label(keep[preds], structure)
    matches: list[dict[str, Any]] = []
    if n_refs and n_preds:
        ref_sizes = np.bincount(refs.ravel(), minlength=n_refs + 1)[1:]
        pred_sizes = np.bincount(preds.ravel(), minlength=n_preds + 1)[1:]
        # Only overlapping foreground voxels contribute to the intersection table.
        overlap = (refs > 0) & (preds > 0)
        pairs, counts = np.unique(
            (refs[overlap].astype(np.int64) - 1) * n_preds + preds[overlap] - 1,
            return_counts=True,
        )
        ref_ids, pred_ids = pairs // n_preds, pairs % n_preds
        iou = counts / (ref_sizes[ref_ids] + pred_sizes[pred_ids] - counts)
        valid = iou >= iou_threshold
        ref_ids, pred_ids, iou = ref_ids[valid], pred_ids[valid], iou[valid]
        # Each reference can choose a private dummy (unmatched) column. All
        # weights are positive; an extra real match dominates every possible
        # sum-IoU improvement. Sparse edges avoid refs-by-predictions RAM growth
        # on noisy outputs with thousands of disconnected candidates.
        dummy = np.arange(n_refs)
        costs = coo_matrix(
            (
                np.concatenate((2 - iou, np.full(n_refs, min(n_refs, n_preds) + 3))),
                (np.concatenate((ref_ids, dummy)), np.concatenate((pred_ids, n_preds + dummy))),
            ),
            shape=(n_refs, n_preds + n_refs),
        ).tocsr()
        rows, cols = min_weight_full_bipartite_matching(costs)
        iou_by_pair = {
            (int(r), int(c)): float(value)
            for r, c, value in zip(ref_ids, pred_ids, iou, strict=True)
        }
        matches = [
            {
                "reference_component": int(r + 1),
                "prediction_component": int(c + 1),
                "iou": iou_by_pair[int(r), int(c)],
            }
            for r, c in zip(rows, cols, strict=True)
            if c < n_preds
        ]
    tp = len(matches)
    return {
        "reference_components": int(n_refs),
        "prediction_components": int(n_preds),
        "removed_prediction_components": int(n_preds_before - n_preds),
        "true_positives": tp,
        "false_negatives": int(n_refs - tp),
        "false_positives": int(n_preds - tp),
        "sensitivity": tp / n_refs if n_refs else None,
        "false_positives_per_scan": float(n_preds - tp),
        "matches": matches,
        "iou_threshold": iou_threshold,
        "connectivity": connectivity,
        "minimum_prediction_volume_mm3": minimum_prediction_volume_mm3,
        "interpretation": "connected-component agreement with annotated masses; not PDAC diagnosis",
    }


def _read_volume(path: Path, role: str) -> Any:
    import nibabel as nib

    try:
        volume: Any = nib.load(str(path))
        if len(volume.shape) != 3 or min(volume.shape) <= 0:
            raise ValueError("not a nonempty 3D volume")
        return volume
    except (OSError, ValueError, nib.filebasedimages.ImageFileError) as exc:
        raise ValueError(
            f"Cannot read {role} as a nonempty 3D NIfTI ({type(exc).__name__})"
        ) from exc


def _affine(volume: Any) -> np.ndarray:
    affine = np.asarray(volume.affine, dtype=float)
    if affine.shape != (4, 4) or not np.isfinite(affine).all():
        raise ValueError("Invalid native affine")
    if not np.allclose(affine[3], [0, 0, 0, 1], atol=1e-6, rtol=0):
        raise ValueError("Invalid affine homogeneous row")
    axes = affine[:3, :3]
    spacing = np.linalg.norm(axes, axis=0)
    _spacing(spacing)
    normalized = axes / spacing
    if not np.allclose(normalized.T @ normalized, np.eye(3), atol=1e-4, rtol=0):
        raise ValueError("Sheared affine is unsupported for spacing-based surface metrics")
    if not np.allclose(volume.header.get_zooms()[:3], spacing, atol=1e-4, rtol=1e-4):
        raise ValueError("Header spacing and affine disagree")
    # NIfTI unit codes must not silently turn metres into millimetres.
    if volume.header.get_xyzt_units()[0] != "mm":
        raise ValueError("NIfTI spatial units must explicitly be mm")
    qform, qcode = volume.get_qform(coded=True)
    sform, scode = volume.get_sform(coded=True)
    if not qcode and not scode:
        raise ValueError("NIfTI has no coded native-coordinate affine")
    if qcode and scode and not np.allclose(qform, sform, atol=1e-4, rtol=0):
        raise ValueError("NIfTI has conflicting qform/sform affines")
    return affine


def _same_geometry(first: Any, other: Any) -> None:
    if first.shape != other.shape or not np.allclose(
        _affine(first), _affine(other), atol=1e-4, rtol=0
    ):
        raise ValueError("Native image/reference/prediction geometry mismatch")


def _decode_labels(volume: Any, allowed: set[int]) -> np.ndarray:
    try:
        data = np.asanyarray(volume.dataobj)
    except Exception as exc:
        raise ValueError(f"Cannot decode label voxel payload ({type(exc).__name__})") from exc
    if not np.isfinite(data).all() or not np.isin(data, list(allowed)).all():
        raise ValueError("Nonfinite or unexpected segmentation labels")
    return data


def _verify_hash(path: Path, expected: str | None) -> None:
    if expected is None:
        return
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ValueError("Cannot read manifest source for checksum verification") from exc
    if digest.hexdigest() != expected:
        raise ValueError("Source checksum differs from audited manifest")


def _region_metrics(
    reference: np.ndarray,
    prediction: np.ndarray,
    status: str,
    ontology: Mapping[str, int],
    include_mass: bool,
    spacing: Sequence[float],
    tolerance: float | None,
) -> dict[str, Any]:
    pancreas_labels = [ontology["pancreas"]]
    if include_mass:
        pancreas_labels.append(ontology["mass"])
    metrics = {
        "pancreas": binary_segmentation_metrics(
            np.isin(reference, pancreas_labels),
            np.isin(prediction, pancreas_labels),
            spacing,
            tolerance,
        ),
        "mass": None,
    }
    if status == "labeled":
        metrics["mass"] = binary_segmentation_metrics(
            reference == ontology["mass"], prediction == ontology["mass"], spacing, tolerance
        )
    return metrics


def _summarize_region(
    cases: Sequence[dict[str, Any]], region: str, samples: int, seed: int
) -> dict[str, Any]:
    annotated = [case for case in cases if case.get("metrics", {}).get(region) is not None]
    positives = [case for case in annotated if case["metrics"][region]["reference_voxels"] > 0]
    summary: dict[str, Any] = {
        "reference_known_cases": len(annotated),
        "reference_positive_cases": len(positives),
        "reference_empty_cases": len(annotated) - len(positives),
        "prediction_success_cases": sum(case["status"] == "ok" for case in annotated),
        "prediction_failed_cases": sum(case["status"] == "failed_prediction" for case in annotated),
        "reference_empty_prediction_nonempty_cases": sum(
            case["status"] == "ok"
            and case["metrics"][region]["reference_voxels"] == 0
            and case["metrics"][region]["prediction_voxels"] > 0
            for case in annotated
        ),
        "both_empty_cases": sum(
            case["status"] == "ok" and case["metrics"][region]["empty_status"] == "both_empty"
            for case in annotated
        ),
        "population": "reference-positive annotated cases; failed predictions receive zero Dice",
    }
    for metric in ("dice", "surface_dice", "hd95_mm"):
        values: dict[str, list[float]] = defaultdict(list)
        for case in positives:
            value = case["metrics"][region].get(metric)
            if value is not None:
                values[case["patient_id"]].append(value)
        result = patient_bootstrap(values, samples, seed)
        result["undefined_or_infinite_cases"] = len(positives) - result["cases"]
        result["coverage"] = result["cases"] / len(positives) if positives else None
        if metric == "hd95_mm":
            result["interpretation"] = (
                "finite boundary distances only; misses/failures remain in coverage denominator"
            )
        summary[metric] = result
    return summary


def write_review_overlay(
    image: Any,
    reference: np.ndarray,
    prediction: np.ndarray,
    output_path: str | Path,
    ontology: Mapping[str, int],
    window_center: float = 50,
    window_width: float = 350,
) -> str:
    """Write a RAS-reoriented CT/reference/prediction montage without identifiers.

    Select the axial plane containing most reference mass, then predicted mass,
    then reference pancreas. This is a review aid, not comprehensive QC or a
    clinical display. Source labels and filenames never appear on the image.
    """
    import nibabel as nib
    from PIL import Image, ImageDraw

    if not math.isfinite(window_width) or window_width <= 0 or not math.isfinite(window_center):
        raise ValueError("CT window must have a finite center and positive finite width")
    canonical = nib.as_closest_canonical(image)
    ct = np.asarray(canonical.dataobj)
    if not np.isfinite(ct).all():
        raise ValueError("Review CT contains nonfinite intensities")
    ref = np.asarray(
        nib.as_closest_canonical(nib.Nifti1Image(reference.astype(np.int16), image.affine)).dataobj
    )
    pred = np.asarray(
        nib.as_closest_canonical(nib.Nifti1Image(prediction.astype(np.int16), image.affine)).dataobj
    )
    target = ref == ontology["mass"]
    if not target.any():
        target = pred == ontology["mass"]
    if not target.any():
        target = ref == ontology["pancreas"]
    z = int(np.argmax(target.sum(axis=(0, 1)))) if target.any() else ct.shape[2] // 2
    gray = np.clip((ct[:, :, z] - (window_center - window_width / 2)) / window_width, 0, 1)
    gray = (np.rot90(gray) * 255).astype(np.uint8)
    base = np.repeat(gray[:, :, None], 3, axis=2)
    spacing = canonical.header.get_zooms()
    panel_width = 384
    panel_height = max(
        1, min(1536, round(panel_width * ct.shape[1] * spacing[1] / (ct.shape[0] * spacing[0])))
    )
    montage = Image.new("RGB", (panel_width * 3, panel_height + 48), "black")
    for index, (title, mask) in enumerate((("CT", None), ("Reference", ref), ("Prediction", pred))):
        rgb = base.copy()
        if mask is not None:
            plane = np.rot90(mask[:, :, z])
            for label, color in (
                (ontology["pancreas"], [0, 220, 90]),
                (ontology["mass"], [255, 60, 70]),
            ):
                selected = plane == label
                rgb[selected] = np.rint(rgb[selected] * 0.55 + np.asarray(color) * 0.45).astype(
                    np.uint8
                )
        panel = Image.fromarray(rgb).resize((panel_width, panel_height), Image.Resampling.BILINEAR)
        montage.paste(panel, (index * panel_width, 48))
        ImageDraw.Draw(montage).text((index * panel_width + 8, 8), title, fill="white")
    ImageDraw.Draw(montage).text(
        (8, 27), "Green: pancreas   Red: annotated/predicted mass   Axial RAS review", fill="white"
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    montage.save(destination, format="PNG")
    return str(destination)


def evaluate_predictions(
    manifest_path: str | Path,
    prediction_dir: str | Path,
    output_dir: str | Path,
    case_ids: Sequence[str] | None = None,
    pancreas_include_mass: bool = True,
    surface_tolerance_mm: float | None = None,
    bootstrap_samples: int = 1000,
    seed: int = 0,
    review_overlays: bool = False,
    lesion_iou_threshold: float | None = None,
) -> dict[str, Any]:
    """Evaluate ``case_id.nii.gz`` predictions against an audited manifest.

    JSON/CSV and optional review PNGs belong in approved artifact storage. Case
    and patient keys are needed for scientific pairing; hashed PNG filenames
    avoid putting source identifiers on exported images but are not by
    themselves a legal de-identification determination.
    """
    import nibabel  # noqa: F401 -- fail once at preflight, not once per patient

    _surface_library()
    patient_bootstrap({}, bootstrap_samples, seed)
    if surface_tolerance_mm is not None and (
        not math.isfinite(surface_tolerance_mm) or surface_tolerance_mm < 0
    ):
        raise ValueError("surface_tolerance_mm must be finite and nonnegative")
    if lesion_iou_threshold is not None and (
        not math.isfinite(lesion_iou_threshold) or not 0 < lesion_iou_threshold <= 1
    ):
        raise ValueError("lesion_iou_threshold must lie in (0, 1]")
    from .data import load_manifest

    manifest = load_manifest(manifest_path, verify_files=False)
    ontology = manifest.get("ontology", {})
    if set(ontology) != {"background", "pancreas", "mass"} or len(set(ontology.values())) != 3:
        raise ValueError("Manifest must specify distinct background, pancreas and mass labels")
    all_cases = manifest["cases"]
    manifest_ids = [case["case_id"] for case in all_cases]
    if len(set(manifest_ids)) != len(manifest_ids):
        raise ValueError("Duplicate manifest case identifiers")
    selected = set(manifest_ids if case_ids is None else case_ids)
    if case_ids is not None and len(selected) != len(case_ids):
        raise ValueError("Duplicate requested case identifiers")
    if not selected or not selected.issubset(manifest_ids):
        raise ValueError("Requested evaluation cohort is empty or contains unknown cases")
    cases = [case for case in all_cases if case["case_id"] in selected]
    for case in cases:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", case["case_id"]) or not case.get(
            "patient_id"
        ):
            raise ValueError(
                "Cases require safe filename identifiers and explicit patient grouping"
            )
        if case.get("annotation_status") not in {"labeled", "organ_only", "unlabeled"}:
            raise ValueError("Every case requires an explicit supported annotation status")
        if case["annotation_status"] == "organ_only" and not pancreas_include_mass:
            raise ValueError(
                "Organ-only references require the whole-pancreas union of pancreas and mass predictions"
            )
    rows: list[dict[str, Any]] = []
    destination = Path(output_dir)
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(
            "Evaluation output directory must be empty; preserve previous reports"
        )
    destination.mkdir(parents=True, exist_ok=True)
    for case in cases:
        annotation = case["annotation_status"]
        row: dict[str, Any] = {
            "case_id": case["case_id"],
            "patient_id": case["patient_id"],
            "annotation_status": annotation,
            "status": "unlabeled",
            "metrics": {},
            "reference_sha256": case.get("label_sha256"),
        }
        rows.append(row)
        if annotation == "unlabeled":
            row["reason"] = (
                "No reference annotation; excluded from segmentation scoring, never a negative"
            )
            continue
        try:
            if not case.get("label"):
                raise ValueError("Annotated case is missing its reference path")
            image_path, label_path = Path(case["image"]), Path(case["label"])
            _verify_hash(image_path, case.get("image_sha256"))
            _verify_hash(label_path, case.get("label_sha256"))
            image = _read_volume(image_path, "image")
            label = _read_volume(label_path, "reference")
            _same_geometry(image, label)
            affine = _affine(image)
            spacing = _spacing(np.linalg.norm(affine[:3, :3], axis=0))
            if case.get("shape") is not None and tuple(case["shape"]) != image.shape:
                raise ValueError("Image shape differs from audited manifest")
            if case.get("affine") is not None and not np.allclose(
                case["affine"], affine, atol=1e-4, rtol=0
            ):
                raise ValueError("Image affine differs from audited manifest")
            allowed = (
                set(ontology.values())
                if annotation == "labeled"
                else {ontology["background"], ontology["pancreas"]}
            )
            reference = _decode_labels(label, allowed)
        except (ValueError, OSError, KeyError) as exc:
            row.update(status="failed_reference", reason=str(exc))
            continue
        try:
            prediction_path = Path(prediction_dir) / f"{case['case_id']}.nii.gz"
            pred_volume = _read_volume(prediction_path, "prediction")
            _same_geometry(image, pred_volume)
            prediction = _decode_labels(pred_volume, set(ontology.values()))
            from .geometry import sha256_file

            row["prediction_sha256"] = sha256_file(prediction_path)
            row["status"] = "ok"
        except (ValueError, OSError) as exc:
            row.update(status="failed_prediction", reason=str(exc))
            prediction = np.full(reference.shape, ontology["background"], dtype=reference.dtype)
        row["metrics"] = _region_metrics(
            reference,
            prediction,
            annotation,
            ontology,
            pancreas_include_mass,
            spacing,
            surface_tolerance_mm,
        )
        if row["status"] == "failed_prediction":
            for scores in row["metrics"].values():
                if scores is not None:
                    scores.update(
                        prediction_voxels=None,
                        prediction_volume_ml=None,
                        empty_status="prediction_failed",
                    )
                    scores["hd95_status"] = "undefined_prediction_failed"
            if lesion_iou_threshold is not None and annotation == "labeled":
                row["lesions"] = lesion_detection_metrics(
                    reference == ontology["mass"],
                    prediction == ontology["mass"],
                    spacing,
                    lesion_iou_threshold,
                )
                # A failed run misses each known reference component, but its
                # number of false alerts is unknown rather than zero.
                row["lesions"].update(
                    false_positives=None,
                    prediction_components=None,
                    false_positives_per_scan=None,
                    prediction_failed=True,
                )
            continue
        if lesion_iou_threshold is not None and annotation == "labeled":
            row["lesions"] = lesion_detection_metrics(
                reference == ontology["mass"],
                prediction == ontology["mass"],
                spacing,
                lesion_iou_threshold,
            )
        if review_overlays:
            token = hashlib.sha256(
                f"{manifest.get('fingerprint', '')}:{case['case_id']}".encode()
            ).hexdigest()[:20]
            try:
                write_review_overlay(
                    image,
                    reference,
                    prediction,
                    destination / "review" / f"review_{token}.png",
                    ontology,
                )
                row["review_file"] = f"review/review_{token}.png"
            except (OSError, ValueError) as exc:
                row["review_error"] = str(exc)
    status_counts = dict(Counter(row["status"] for row in rows))
    labeled_count = sum(row["annotation_status"] != "unlabeled" for row in rows)
    reference_valid = status_counts.get("ok", 0) + status_counts.get("failed_prediction", 0)
    report: dict[str, Any] = {
        "schema_version": 1,
        "dataset": manifest.get("dataset"),
        "manifest_fingerprint": manifest.get("fingerprint"),
        "protocol": {
            "pancreas_include_mass": pancreas_include_mass,
            "surface_tolerance_mm": surface_tolerance_mm,
            "surface_method": "DeepMind surfel-area-weighted surface-distance",
            "hd95_definition": "maximum of directional area-weighted 95th-percentile distances in mm",
            "prediction_failure_policy": "zero Dice and surface Dice for known positive references; undefined distances; no imputed negatives",
            "empty_policy": "both-empty excluded from Dice means; reference-empty outcomes reported separately",
            "aggregation": "equal-weight patient means over reference-positive annotated cases",
            "lesion_iou_threshold": lesion_iou_threshold,
            "bootstrap_samples": bootstrap_samples,
            "seed": seed,
        },
        "software": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "nibabel", "surface-distance", "scipy")
        },
        "coverage": {
            "eligible_cases": len(rows),
            "annotated_cases": labeled_count,
            "status_counts": status_counts,
            "valid_reference_cases": reference_valid,
            "reference_coverage": reference_valid / labeled_count if labeled_count else None,
            "valid_prediction_cases": status_counts.get("ok", 0),
            "prediction_coverage": status_counts.get("ok", 0) / labeled_count
            if labeled_count
            else None,
            "review_failures": sum("review_error" in row for row in rows),
        },
        "regions": {
            region: _summarize_region(rows, region, bootstrap_samples, seed)
            for region in ("pancreas", "mass")
        },
        "limitations": [
            "Mass-mask agreement does not establish PDAC diagnosis, screening performance or clinical utility.",
            "Organ-only annotations cannot establish absence of a mass; their mass metrics are unknown.",
            "Patient bootstrap assumes independent patient groups; unresolved cross-source identity or site clustering limits interpretation.",
            "Only explicit millimetre spatial units and consistent coded native affines are accepted.",
        ],
        "cases": rows,
    }
    if lesion_iou_threshold is not None:
        lesion_rows = [row["lesions"] for row in rows if "lesions" in row]
        successful_lesion_rows = [row for row in lesion_rows if not row.get("prediction_failed")]
        totals = {
            key: sum(row[key] for row in lesion_rows)
            for key in ("reference_components", "true_positives", "false_negatives")
        }
        known_false_positives = sum(row["false_positives"] for row in successful_lesion_rows)
        success_reference_components = sum(
            row["reference_components"] for row in successful_lesion_rows
        )
        eligible_lesion_cases = sum(row["annotation_status"] == "labeled" for row in rows)
        report["lesions"] = {
            **totals,
            "scored_cases": len(successful_lesion_rows),
            "eligible_annotated_cases": eligible_lesion_cases,
            "valid_reference_cases": len(lesion_rows),
            "failed_prediction_cases": len(lesion_rows) - len(successful_lesion_rows),
            "failed_reference_cases": eligible_lesion_cases - len(lesion_rows),
            "sensitivity_including_failed_predictions": totals["true_positives"]
            / totals["reference_components"]
            if totals["reference_components"]
            else None,
            "sensitivity_on_successful_cases": totals["true_positives"]
            / success_reference_components
            if success_reference_components
            else None,
            "known_false_positives": known_false_positives,
            "false_positive_count_complete": len(successful_lesion_rows) == eligible_lesion_cases,
            "false_positives_per_successful_scan": known_false_positives
            / len(successful_lesion_rows)
            if successful_lesion_rows
            else None,
            "interpretation": "Failed predictions count as misses of known reference components; false alerts on failed scans remain unknown; no clinical diagnosis inference",
        }
    temporary = destination / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(destination / "report.json")
    fields = ["case_id", "patient_id", "annotation_status", "status", "reason"]
    fields += [
        f"{region}_{metric}"
        for region in ("pancreas", "mass")
        for metric in (
            "dice",
            "surface_dice",
            "hd95_mm",
            "hd95_status",
            "empty_status",
            "reference_voxels",
            "prediction_voxels",
        )
    ]
    with (destination / "cases.csv.tmp").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat = {key: row.get(key) for key in fields[:5]}
            for region in ("pancreas", "mass"):
                for key, value in (row["metrics"].get(region) or {}).items():
                    if f"{region}_{key}" in fields:
                        flat[f"{region}_{key}"] = value
            writer.writerow(flat)
    (destination / "cases.csv.tmp").replace(destination / "cases.csv")
    return report


def paired_comparison(
    report_a: Mapping[str, Any],
    report_b: Mapping[str, Any],
    region: str = "mass",
    metric: str = "dice",
    bootstrap_samples: int = 1000,
    seed: int = 0,
) -> dict[str, Any]:
    """Patient-bootstrap paired differences B minus A on the identical cohort.

    Matching finite metrics are required; one-sided missingness fails loudly.
    Both-missing metrics are reported as excluded, with no complete-case claim
    for undefined boundary distances. Failed-prediction Dice is already zero.
    """
    if region not in {"pancreas", "mass"} or metric not in {"dice", "surface_dice", "hd95_mm"}:
        raise ValueError("Unsupported paired region or metric")
    if not report_a.get("manifest_fingerprint") or report_a.get(
        "manifest_fingerprint"
    ) != report_b.get("manifest_fingerprint"):
        raise ValueError("Paired comparisons require the same nonempty manifest fingerprint")
    for key in (
        "pancreas_include_mass",
        "surface_tolerance_mm",
        "surface_method",
        "hd95_definition",
        "prediction_failure_policy",
        "empty_policy",
        "aggregation",
    ):
        if report_a["protocol"].get(key) != report_b["protocol"].get(key):
            raise ValueError(f"Paired evaluation protocols differ: {key}")
    left = {row["case_id"]: row for row in report_a["cases"]}
    right = {row["case_id"]: row for row in report_b["cases"]}
    if (
        len(left) != len(report_a["cases"])
        or len(right) != len(report_b["cases"])
        or left.keys() != right.keys()
    ):
        raise ValueError("Paired comparisons require identical, unique eligible case identifiers")
    differences: dict[str, list[float]] = defaultdict(list)
    excluded: list[str] = []
    for case_id in sorted(left):
        a, b = left[case_id], right[case_id]
        if a["patient_id"] != b["patient_id"] or a["annotation_status"] != b["annotation_status"]:
            raise ValueError("Paired patient grouping or reference annotation status differs")
        ma, mb = a.get("metrics", {}).get(region), b.get("metrics", {}).get(region)
        if (ma is None) != (mb is None):
            raise ValueError("Paired reference availability differs")
        if ma is None or mb is None:
            excluded.append(case_id)
            continue
        if ma["reference_voxels"] != mb["reference_voxels"]:
            raise ValueError("Paired reference masks differ")
        if ma["reference_voxels"] == 0:
            excluded.append(case_id)
            continue
        va, vb = ma.get(metric), mb.get(metric)
        if (va is None) != (vb is None):
            raise ValueError("One-sided undefined paired metric; cannot silently drop failed cases")
        if va is None or vb is None:
            excluded.append(case_id)
            continue
        differences[a["patient_id"]].append(float(vb) - float(va))
    result = patient_bootstrap(differences, bootstrap_samples, seed)
    result.update(
        region=region,
        metric=metric,
        difference="B minus A",
        eligible_cases=len(left),
        excluded_cases=excluded,
        interpretation="Positive differences favor B for Dice; negative differences favor B for HD95",
    )
    return result
