"""Explicit inference-only window weighting, independent of training identity."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np


@dataclass(frozen=True)
class InferenceBlending:
    """A declared post-training experiment; the ordinary default remains uniform.

    Gaussian sigma is a fraction of each patch axis length. The separable
    Gaussian is normalized to peak one and floored at float32 epsilon, so
    even singly covered corner voxels have a stable nonzero denominator.
    """

    mode: str = "uniform"
    sigma_scale: float = 0.125

    def __post_init__(self) -> None:
        if self.mode not in {"uniform", "gaussian"}:
            raise ValueError("Inference blending must be uniform or gaussian")
        if (
            isinstance(self.sigma_scale, bool)
            or not isinstance(self.sigma_scale, (int, float))
            or not math.isfinite(self.sigma_scale)
            or self.sigma_scale <= 0
        ):
            raise ValueError("Gaussian sigma_scale must be finite and positive")


@lru_cache(maxsize=8)
def gaussian_weights(patch_size: tuple[int, ...], sigma_scale: float = 0.125) -> np.ndarray:
    """Return immutable float32 weights for arbitrary positive 2D/3D patches."""
    InferenceBlending("gaussian", sigma_scale)
    if len(patch_size) not in (2, 3) or any(type(n) is not int or n < 1 for n in patch_size):
        raise ValueError("Gaussian patch_size must contain two or three positive integers")
    # Normalize each 1D log Gaussian before summing. For even lengths the two
    # center voxels share peak one. Clipping in log-space also avoids underflow
    # for unusually small sigma without changing the documented floor.
    floor = float(np.finfo(np.float32).eps)
    log_floor = math.log(floor)
    log_weights = np.zeros(patch_size, dtype=np.float64)
    for axis, length in enumerate(patch_size):
        distances = (np.arange(length, dtype=np.float64) - (length - 1) / 2) ** 2
        distances -= distances.min()
        # Divide successively: tiny positive sigma can underflow when squared.
        with np.errstate(over="ignore", divide="ignore", invalid="raise"):
            normalized = distances / (length * sigma_scale) / (length * sigma_scale)
        axis_log = np.maximum(-0.5 * normalized, log_floor)
        shape = [1] * len(patch_size)
        shape[axis] = length
        log_weights += axis_log.reshape(shape)
    weights = np.exp(np.maximum(log_weights, log_floor)).astype(np.float32)
    np.maximum(weights, np.float32(floor), out=weights)
    weights.flags.writeable = False
    return weights
