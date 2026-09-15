"""Physical-aspect, synchronized review panels; no diagnostic image enhancement."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

PLANES = {"axial": 2, "coronal": 1, "sagittal": 0}


def canonical(array: np.ndarray, affine: np.ndarray) -> np.ndarray:
    return np.asarray(nib.as_closest_canonical(nib.Nifti1Image(array, affine)).dataobj)


def select_planes(reference: np.ndarray, predictions: list[np.ndarray], count: int) -> dict:
    """Same indices for every model: lesion/FP extent plus largest shared error plane.

    count=0 exports every slice. Otherwise selection is an explicitly biased review
    aid, not an estimate of error prevalence or a complete volume inspection.
    """
    if type(count) is not int or count < 0:
        raise ValueError("Slice count must be a nonnegative integer")
    target = reference == 2
    error = np.zeros(reference.shape, np.int32)
    for prediction in predictions:
        target |= prediction == 2
        error += (reference == 2) != (prediction == 2)
    if not target.any():
        target = reference > 0
    planes = {}
    for name, axis in PLANES.items():
        other = tuple(i for i in range(3) if i != axis)
        coverage = target.sum(axis=other)
        nonzero = np.flatnonzero(coverage)
        if count == 0:
            chosen = np.arange(reference.shape[axis])
        elif len(nonzero):
            candidates = nonzero[
                np.linspace(0, len(nonzero) - 1, min(count, len(nonzero))).astype(int)
            ]
            errors = error.sum(axis=other)
            chosen = (
                np.unique(np.append(candidates, int(errors.argmax())))
                if errors.max() > 0
                else np.unique(candidates)
            )
            if len(chosen) > count:
                # Preserve the maximum-error slice, replacing the middle quantile.
                candidates[len(candidates) // 2] = int(error.sum(axis=other).argmax())
                chosen = np.unique(candidates)
        else:
            chosen = np.array([reference.shape[axis] // 2])
        planes[name] = [int(i) for i in chosen]
    return planes


def render_panels(
    ct: np.ndarray,
    reference: np.ndarray,
    prediction: np.ndarray,
    spacing: np.ndarray,
    planes: dict,
    output: Path,
    window: tuple[float, float] = (-100, 240),
) -> dict:
    """Inputs already canonical RAS; all models must receive the same planes."""
    lo, hi = window
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        raise ValueError("Invalid display HU window")
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, axis in PLANES.items():
        other = [i for i in range(3) if i != axis]
        paths = []
        for index in planes[name]:
            gray = np.rot90(np.take(ct, index, axis=axis))
            base = np.repeat(
                (np.clip((gray - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)[..., None],
                3,
                axis=2,
            )
            ref = np.rot90(np.take(reference, index, axis=axis))
            pred = np.rot90(np.take(prediction, index, axis=axis))
            width = 300
            height = max(
                40,
                round(
                    width * base.shape[0] * spacing[other[1]] / (base.shape[1] * spacing[other[0]])
                ),
            )
            montage = Image.new("RGB", (width * 4, height + 48), "black")
            draw = ImageDraw.Draw(montage)
            for column, title in enumerate(
                ("CT", "Reference contours", "Prediction contours", "Mass errors: FN red / FP blue")
            ):
                rgb = base.copy()
                if column in (1, 2):
                    mask = ref if column == 1 else pred
                    for selected, color in (
                        (mask > 0, (0, 220, 130)),
                        (mask == 2, (255, 100, 220)),
                    ):
                        contour = selected & ~ndimage.binary_erosion(selected)
                        rgb[contour] = color
                if column == 3:
                    for selected, color in (
                        ((ref == 2) & (pred != 2), (255, 50, 50)),
                        ((pred == 2) & (ref != 2), (40, 160, 255)),
                    ):
                        rgb[selected] = np.rint(
                            0.35 * rgb[selected] + 0.65 * np.array(color)
                        ).astype(np.uint8)
                panel = Image.fromarray(rgb).resize((width, height), Image.Resampling.NEAREST)
                montage.paste(panel, (column * width, 48))
                draw.text((column * width + 4, 5), title, fill="white")
            draw.text(
                (4, 27),
                f"Canonical RAS | {name} slice {index} | HU [{lo:g}, {hi:g}] | green whole pancreas; pink mass",
                fill="white",
            )
            path = output / f"{name}-{index:04d}.png"
            montage.save(path)
            paths.append(path)
        results[name] = paths
    return results
