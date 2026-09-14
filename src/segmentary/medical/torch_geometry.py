"""CPU backprojection of dense probabilities onto an examination's native grid."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

import numpy as np


def native_argmax(channels: Sequence[np.ndarray]) -> np.ndarray:
    """Choose among three finite native channels without a full stacked copy.

    Strict comparisons preserve NumPy argmax's first-channel tie convention,
    including signed zeros. NaNs are rejected rather than silently assigning a
    different class. The input probability arrays are never modified.
    """
    if len(channels) != 3:
        raise ValueError("Native argmax requires exactly three channels")
    shape = channels[0].shape
    if len(shape) != 3 or any(size < 1 for size in shape):
        raise ValueError("Native argmax requires nonempty three-dimensional channels")
    for channel in channels:
        if channel.shape != shape or channel.dtype.kind != "f" or not np.isfinite(channel).all():
            raise ValueError("Native argmax requires same-shape finite floating-point channels")
    background, pancreas, mass = channels
    prediction = (pancreas > background).astype(np.uint8)
    prediction[(mass > background) & (mass > pancreas)] = 2
    return prediction


def native_probabilities(
    probabilities: np.ndarray,
    processed_affine: np.ndarray,
    native_shape: tuple[int, ...],
    native_affine: np.ndarray,
    *,
    workers: int,
) -> list[np.ndarray]:
    """Interpolate independent channels concurrently without changing arithmetic.

    Channels arrive as C/z/y/x and each output uses the native x/y/z axes.
    SciPy's affine interpolation releases the GIL. At most three worker threads
    overlap those independent calls; each channel keeps the serial operation and
    the returned list keeps channel order. The surrounding experiment's CPU
    budget controls concurrency, including a serial path when workers is one.
    No label payload or annotation-derived crop participates in backprojection.
    """
    import nibabel as nib
    from nibabel.processing import resample_from_to

    if type(workers) is not int or workers < 1:
        raise ValueError("Backprojection workers must be a positive integer")
    if probabilities.ndim != 4 or probabilities.shape[0] != 3:
        raise ValueError("Backprojection requires three dense C/z/y/x probability channels")

    def resample(channel: np.ndarray) -> np.ndarray:
        volume = nib.Nifti1Image(channel.transpose(2, 1, 0), processed_affine)
        return np.asarray(
            resample_from_to(volume, (native_shape, native_affine), order=1, cval=0).dataobj
        )

    if workers == 1:
        return [resample(channel) for channel in probabilities]
    with ThreadPoolExecutor(max_workers=min(3, workers)) as pool:
        return list(pool.map(resample, probabilities))
