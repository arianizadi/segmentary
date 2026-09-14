"""Paired axial rotations and shared normalized-CT intensity augmentation.

Rotation uses the final y/x voxel-grid axes, never the 2.5D context/channel axis.
TorchConfig requires equal in-plane spacing for physically meaningful angles.
Every slice/channel shares one angle, with fixed output shape, order-1 image
interpolation and order-0 mask interpolation. Out-of-image values use the recipe's
constant normalized intensity; out-of-mask values are always background (0).
Intensity scaling uses one factor for the entire sample, without clipping.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .torch_config import TorchConfig


def augment_patch(
    image: np.ndarray,
    label: np.ndarray,
    config: TorchConfig,
    rng: np.random.Generator,
    diagnostics: dict[str, Any] | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Disabled options consume zero RNG draws and return the original arrays."""
    angle, factor = 0.0, 1.0
    rotated = scaled = False
    if config.rotation_probability and rng.random() < config.rotation_probability:
        from scipy.ndimage import rotate

        angle = float(rng.uniform(*config.rotation_degrees))
        options = {
            "angle": angle,
            "axes": (-2, -1),
            "reshape": False,
            "mode": "constant",
            "prefilter": False,
        }
        image = rotate(image, order=1, cval=config.rotation_padding_value, **options)
        label = rotate(label, order=0, cval=0, **options)
        rotated = True
    if config.intensity_scale_probability and rng.random() < config.intensity_scale_probability:
        factor = float(rng.uniform(*config.intensity_scale_range))
        # A new array avoids writes through views/mmap inputs (including flipped views).
        image = image * np.float32(factor)
        scaled = True
    if diagnostics is not None:
        diagnostics.update(
            rotation_applied=rotated,
            rotation_angle_degrees=angle,
            intensity_scale_applied=scaled,
            intensity_scale_factor=factor,
        )
    return image, label
