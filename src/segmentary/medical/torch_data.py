"""Physical CT resampling, same-patient context, and image-only tiled inference.

NIfTI arrays are RAS x/y/z after preprocessing; network arrays are z/y/x.
The fixed HU window/spacing are declared before evaluation, never fitted on test.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from .torch_config import TorchConfig


def preprocess_case(case: dict, config: TorchConfig, *, with_label: bool) -> dict[str, Any]:
    import nibabel as nib
    from nibabel.processing import resample_from_to, resample_to_output

    from .geometry import validate_nifti

    validate_nifti(case["image"])
    original: Any = nib.load(case["image"])
    # scipy preserves the input dtype by default. Promote integer HU payloads
    # before interpolation so half-voxel intensities are not rounded to integers.
    continuous = nib.Nifti1Image(np.asarray(original.dataobj, dtype=np.float32), original.affine)
    ct = resample_to_output(
        continuous, voxel_sizes=config.spacing_mm, order=1, cval=config.hu_window[0]
    )
    values = np.asarray(ct.dataobj, dtype=np.float32)
    lo, hi = config.hu_window
    values = (np.clip(values, lo, hi) - lo) / (hi - lo)
    result: dict[str, Any] = {"image": values.transpose(2, 1, 0).copy(), "affine": ct.affine}
    if with_label:
        validate_nifti(case["label"], is_label=True, allowed_labels=(0, 1, 2))
        label: Any = nib.load(case["label"])
        if label.shape != original.shape or not np.allclose(
            label.affine, original.affine, atol=1e-4, rtol=0
        ):
            raise ValueError("Image/label native geometry differs")
        target = resample_from_to(label, (ct.shape, ct.affine), order=0, cval=0)
        result["label"] = np.asarray(target.dataobj, dtype=np.uint8).transpose(2, 1, 0).copy()
    return result


def context_image(image: np.ndarray, z: int, slices: int) -> np.ndarray:
    """Boundary replication never draws slices from another examination."""
    offsets = np.arange(slices) - slices // 2
    return image[np.clip(z + offsets, 0, image.shape[0] - 1)]


def sample_patch(
    data: dict, config: TorchConfig, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    image, label = data["image"], data["label"]
    center = [int(rng.integers(size)) for size in label.shape]
    if rng.random() < config.foreground_probability:
        classes = [c for c in (1, 2) if np.any(label == c)]
        if classes:
            locations = np.argwhere(label == rng.choice(classes))
            center = locations[int(rng.integers(len(locations)))].tolist()
    if config.mode == "3d":
        image = image[None]
    else:
        image = context_image(image, center[0], config.context_slices)
        label = label[center[0]]
        center = center[1:]
    padding = [
        (max(0, (p - n) // 2), max(0, p - n - (p - n) // 2))
        for n, p in zip(label.shape, config.patch_size, strict=True)
    ]
    image = np.pad(image, [(0, 0), *padding], constant_values=0)
    label = np.pad(label, padding, constant_values=0)
    starts = [
        max(0, min(c + pad[0] - p // 2, n - p))
        for c, pad, p, n in zip(center, padding, config.patch_size, label.shape, strict=True)
    ]
    crop = tuple(
        slice(start, start + p) for start, p in zip(starts, config.patch_size, strict=True)
    )
    image, label = image[(slice(None), *crop)], label[crop]
    if config.augment:
        for axis in range(label.ndim):
            if rng.random() < 0.5:
                image, label = np.flip(image, axis + 1), np.flip(label, axis)
    return image.copy(), label.astype(np.int64).copy()


def _starts(size: int, patch_size: int, overlap: float) -> list[int]:
    last = max(0, size - patch_size)
    return sorted({*range(0, last + 1, max(1, int(patch_size * (1 - overlap)))), last})


def tiled_probabilities(
    model: nn.Module, image: np.ndarray, config: TorchConfig, device: torch.device
) -> np.ndarray:
    """Blend probabilities with uniform weights and cover every voxel exactly."""
    original = image.shape[1:]
    padding = [(0, max(0, p - n)) for p, n in zip(config.patch_size, original, strict=True)]
    padded = np.pad(image, [(0, 0), *padding])
    shape = padded.shape[1:]
    total = np.zeros((3, *shape), dtype=np.float32)
    count = np.zeros(shape, dtype=np.float32)
    dtype = torch.bfloat16 if config.precision == "bf16" else torch.float16
    with torch.inference_mode():
        for origin in itertools.product(
            *[_starts(n, p, config.overlap) for n, p in zip(shape, config.patch_size, strict=True)]
        ):
            region = tuple(slice(x, x + p) for x, p in zip(origin, config.patch_size, strict=True))
            tensor = torch.from_numpy(padded[(slice(None), *region)][None].copy()).to(device)
            with torch.autocast(
                device_type=device.type, dtype=dtype, enabled=config.precision != "fp32"
            ):
                logits = model(tensor)
            if logits.shape != (1, 3, *config.patch_size) or not torch.isfinite(logits).all():
                raise ValueError("Model returned invalid dense logits")
            total[(slice(None), *region)] += logits.float().softmax(1)[0].cpu().numpy()
            count[region] += 1
    crop = tuple(slice(0, n) for n in original)
    return (total / count[None])[(slice(None), *crop)]


def predict_case(
    model: nn.Module,
    case: dict,
    config: TorchConfig,
    device: torch.device,
    *,
    output: Path | None = None,
) -> np.ndarray:
    import nibabel as nib
    from nibabel.processing import resample_from_to

    from .geometry import export_native_prediction

    # No access to case['label'], including during validation inference.
    data = preprocess_case(case, config, with_label=False)
    image = data["image"]
    was_training = model.training
    model.eval()
    try:
        if config.mode == "3d":
            probabilities = tiled_probabilities(model, image[None], config, device)
        else:
            probabilities = np.stack(
                [
                    tiled_probabilities(
                        model, context_image(image, z, config.context_slices), config, device
                    )
                    for z in range(image.shape[0])
                ],
                axis=1,
            )
    finally:
        model.train(was_training)
    reference: Any = nib.load(case["image"])
    native = []
    for channel in probabilities:
        volume = nib.Nifti1Image(channel.transpose(2, 1, 0), data["affine"])
        native.append(
            np.asarray(
                resample_from_to(
                    volume, (reference.shape, reference.affine), order=1, cval=0
                ).dataobj
            )
        )
    prediction = np.stack(native).argmax(0).astype(np.uint8)
    if output is not None:
        export_native_prediction(case["image"], prediction, output)
    return prediction


def dice_ce(logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    probabilities = logits.float().softmax(1)
    truth = torch.nn.functional.one_hot(targets, 3).movedim(-1, 1).float()
    axes = (0, *range(2, logits.ndim))
    intersection = (probabilities * truth).sum(axes)
    denominator = (probabilities + truth).sum(axes)
    dice = (2 * intersection[1:] + 1e-5) / (denominator[1:] + 1e-5)
    return torch.nn.functional.cross_entropy(logits.float(), targets) + 1 - dice.mean()


def training_loss(model: nn.Module, images: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    native: Callable[..., torch.Tensor] | None = getattr(model, "training_loss", None)
    return native(images, labels) if native is not None else dice_ce(model(images), labels)
