"""Frozen image-only predicted-organ crops, reconstructed onto the full native CT."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from .geometry import sha256_file
from .torch_config import TorchConfig


def roi_document(config: TorchConfig) -> dict[str, Any] | None:
    if config.roi_manifest is None:
        return None
    path = Path(config.roi_manifest)
    if sha256_file(path) != config.roi_manifest_sha256:
        raise ValueError("Frozen ROI manifest changed")
    document = json.loads(path.read_text())
    if (
        document.get("schema_version") != 1
        or document.get("kind") != "predicted_pancreas_native_bbox"
        or document.get("reference_labels_used") is not False
        or document.get("empty_prediction_policy") != "full_ct"
        or not isinstance(document.get("cases"), dict)
    ):
        raise ValueError("Unsupported predicted ROI manifest")
    return document


def crop_image(image: Any, case: dict, config: TorchConfig) -> Any:
    import nibabel as nib

    document = roi_document(config)
    if document is None:
        return image
    record = document["cases"].get(case["case_id"])
    if (
        not isinstance(record, dict)
        or not re.fullmatch(r"[a-f0-9]{64}", str(record.get("image_sha256")))
        or record.get("image_sha256") != case.get("image_sha256")
    ):
        raise ValueError("ROI manifest lacks a matching audited image")
    bounds = record.get("bbox_xyz")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 3
        or any(not isinstance(pair, list) or len(pair) != 2 for pair in bounds)
        or any(type(x) is not int for pair in bounds for x in pair)
        or any(not 0 <= lo < hi <= size for (lo, hi), size in zip(bounds, image.shape, strict=True))
    ):
        raise ValueError("Invalid native ROI bounds")
    affine = image.affine.copy()
    affine[:3, 3] = (image.affine @ np.array([*(pair[0] for pair in bounds), 1]))[:3]
    values = np.asarray(image.dataobj)[tuple(slice(*pair) for pair in bounds)]
    return nib.Nifti1Image(values, affine)


def predicted_bbox(
    prediction: np.ndarray, spacing: np.ndarray, margin_mm: float
) -> tuple[list[list[int]], bool]:
    """Use all predicted organ-union voxels, with millimeter margins and no GT.

    Exclusive Task07 labels 1 (parenchyma) and 2 (mass) together define the
    predicted whole-organ envelope. An empty first stage falls back to the full
    image; no examination is dropped. Bounds are native XYZ, stop-exclusive.
    """
    if prediction.ndim != 3 or not np.isin(prediction, [0, 1, 2]).all():
        raise ValueError("Stage-one prediction must be a native 0/1/2 volume")
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("Invalid native spacing")
    if not np.isfinite(margin_mm) or margin_mm < 0:
        raise ValueError("ROI margin must be finite and nonnegative")
    locations = np.nonzero(prediction > 0)
    if not len(locations[0]):
        return [[0, int(size)] for size in prediction.shape], True
    margins = np.ceil(margin_mm / spacing).astype(int)
    return [
        [max(0, int(axis.min()) - int(margin)), min(size, int(axis.max()) + int(margin) + 1)]
        for axis, margin, size in zip(locations, margins, prediction.shape, strict=True)
    ], False
