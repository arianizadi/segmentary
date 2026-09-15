"""Physical CT resampling, same-patient context, and image-only tiled inference.

NIfTI arrays are RAS x/y/z after preprocessing; network arrays are z/y/x.
The fixed HU window/spacing are declared before evaluation, never fitted on test.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable, Generator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from .torch_blending import InferenceBlending, gaussian_weights
from .torch_config import TorchConfig


def preprocess_case(case: dict, config: TorchConfig, *, with_label: bool) -> dict[str, Any]:
    import nibabel as nib
    from nibabel.processing import resample_from_to, resample_to_output

    from .geometry import validate_nifti

    validate_nifti(case["image"])
    original: Any = nib.load(case["image"])
    # scipy preserves the input dtype by default. Promote integer HU payloads
    # before interpolation so half-voxel intensities are not rounded to integers.
    native_values = np.asarray(original.dataobj, dtype=np.float32)
    # Adaptive normalization is image-only and uses the full examination, before
    # any ROI crop or resampling padding; labels never determine intensity bounds.
    bounds = (
        (float(native_values.min()), float(native_values.max()))
        if config.normalization == "volume_minmax"
        else config.hu_window
    )
    continuous = nib.Nifti1Image(native_values, original.affine)
    if config.roi_manifest is not None:
        from .torch_roi import crop_image

        continuous = crop_image(continuous, case, config)
    ct = resample_to_output(continuous, voxel_sizes=config.spacing_mm, order=1, cval=bounds[0])
    values = np.asarray(ct.dataobj, dtype=np.float32)
    lo, hi = config.hu_window if config.normalization == "fixed_window" else bounds
    values = (np.clip(values, lo, hi) - lo) / (hi - lo) if hi > lo else np.zeros_like(values)
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
    data: dict,
    config: TorchConfig,
    rng: np.random.Generator,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample one paired patch; optional audit diagnostics do not advance the RNG.

    The legacy branch retains its original draws and crop/flip sequence exactly.
    Explicit center modes and optional augmentation require a new run identity.
    """
    image, label = data["image"], data["label"]
    center = [int(rng.integers(size)) for size in label.shape]
    if diagnostics is not None:
        diagnostics.update(
            center_mode="legacy_foreground",
            requested_center_branch="uniform_volume",
            selected_center_branch="uniform_volume",
            selected_center_class=None,
            center_fallback=False,
            missing_center_classes=[],
            rotation_applied=False,
            rotation_angle_degrees=0.0,
            intensity_scale_applied=False,
            intensity_scale_factor=1.0,
        )
    if config.foreground_probability is None:
        from .torch_sampling import explicit_center

        center = explicit_center(data, config, rng, center, diagnostics)
    elif rng.random() < config.foreground_probability:
        coordinates = data.get("foreground_coordinates")
        classes = [
            c
            for c in (1, 2)
            if (len(coordinates[c]) if coordinates is not None else np.any(label == c))
        ]
        if classes:
            chosen = rng.choice(classes)
            locations = (
                coordinates[chosen] if coordinates is not None else np.argwhere(label == chosen)
            )
            center = locations[int(rng.integers(len(locations)))].tolist()
        if diagnostics is not None:
            diagnostics.update(
                requested_center_branch="foreground",
                selected_center_branch={1: "pancreas", 2: "mass"}[int(chosen)]
                if classes
                else "uniform_volume",
                selected_center_class=int(chosen) if classes else None,
                center_fallback=not bool(classes),
                missing_center_classes=[c for c in (1, 2) if c not in classes],
            )
    if diagnostics is not None:
        diagnostics["center_zyx"] = center.copy()
    z = center[0]
    if config.mode != "3d":
        label = label[z]
        center = center[1:]
    padding = [
        (max(0, (p - n) // 2), max(0, p - n - (p - n) // 2))
        for n, p in zip(label.shape, config.patch_size, strict=True)
    ]
    # Compute the original padded-volume crop, then intersect it with the
    # unpadded volume. Only a patch is copied/padded, including for 2.5D context.
    # This keeps both the sample distribution and every RNG draw unchanged.
    starts = [
        max(0, min(c + pad[0] - p // 2, n + sum(pad) - p))
        for c, pad, p, n in zip(center, padding, config.patch_size, label.shape, strict=True)
    ]
    source_starts = [start - pad[0] for start, pad in zip(starts, padding, strict=True)]
    crop = tuple(
        slice(max(0, start), min(n, start + p))
        for start, p, n in zip(source_starts, config.patch_size, label.shape, strict=True)
    )
    crop_padding = [
        (max(0, -start), max(0, start + p - n))
        for start, p, n in zip(source_starts, config.patch_size, label.shape, strict=True)
    ]
    if config.mode == "3d":
        image = image[crop][None]
    else:
        image = context_image(image[(slice(None), *crop)], z, config.context_slices)
    label = label[crop]
    if diagnostics is not None:
        diagnostics.update(
            crop_padding_voxels=int(np.prod(config.patch_size)) - label.size,
            patch_voxels=int(np.prod(config.patch_size)),
        )
    if any(before or after for before, after in crop_padding):
        image = np.pad(image, [(0, 0), *crop_padding], constant_values=0)
        label = np.pad(label, crop_padding, constant_values=0)
    if diagnostics is not None:
        diagnostics["label_voxels_before_augmentation"] = {
            str(c): int(np.count_nonzero(label == c)) for c in (0, 1, 2)
        }
    if config.augment:
        for axis in range(label.ndim):
            if rng.random() < 0.5:
                image, label = np.flip(image, axis + 1), np.flip(label, axis)
        if config.rotation_probability or config.intensity_scale_probability:
            from .torch_augmentation import augment_patch

            image, label = augment_patch(image, label, config, rng, diagnostics)
    if diagnostics is not None:
        diagnostics["final_label_voxels"] = {
            str(c): int(np.count_nonzero(label == c)) for c in (0, 1, 2)
        }
    return image.copy(), np.array(label, dtype=np.int64, order="C", copy=True)


def _starts(size: int, patch_size: int, overlap: float) -> list[int]:
    last = max(0, size - patch_size)
    return sorted({*range(0, last + 1, max(1, int(patch_size * (1 - overlap)))), last})


def tiled_probabilities(
    model: nn.Module,
    image: np.ndarray,
    config: TorchConfig,
    device: torch.device,
    *,
    blending: InferenceBlending | None = None,
) -> np.ndarray:
    """Cover every voxel, preserving original arithmetic for uniform blending."""
    weights = (
        gaussian_weights(config.patch_size, blending.sigma_scale)
        if blending is not None and blending.mode == "gaussian"
        else None
    )
    original = image.shape[1:]
    padding = [(0, max(0, p - n)) for p, n in zip(config.patch_size, original, strict=True)]
    padded = np.pad(image, [(0, 0), *padding]) if any(after for _, after in padding) else image
    shape = padded.shape[1:]
    total = np.zeros((3, *shape), dtype=np.float32)
    count = np.zeros(shape, dtype=np.float32)
    dtype = torch.bfloat16 if config.precision == "bf16" else torch.float16
    origins = itertools.product(
        *[_starts(n, p, config.overlap) for n, p in zip(shape, config.patch_size, strict=True)]
    )
    with torch.inference_mode():
        while batch := list(itertools.islice(origins, config.inference_batch_size)):
            regions = [
                tuple(slice(x, x + p) for x, p in zip(origin, config.patch_size, strict=True))
                for origin in batch
            ]
            tensor = torch.from_numpy(
                np.stack([padded[(slice(None), *region)] for region in regions])
            ).to(device)
            with torch.autocast(
                device_type=device.type, dtype=dtype, enabled=config.precision != "fp32"
            ):
                logits = model(tensor)
            if (
                logits.shape != (len(batch), 3, *config.patch_size)
                or not torch.isfinite(logits).all()
            ):
                raise ValueError("Model returned invalid dense logits")
            probabilities = logits.float().softmax(1).cpu().numpy()
            # Preserve the original lexicographic window accumulation order.
            for region, probability in zip(regions, probabilities, strict=True):
                if weights is None:
                    total[(slice(None), *region)] += probability
                    count[region] += 1
                else:
                    total[(slice(None), *region)] += probability * weights[None]
                    count[region] += weights
    crop = tuple(slice(0, n) for n in original)
    return (total / count[None])[(slice(None), *crop)]


def _prepare_prediction(case: dict, config: TorchConfig, cache: Any | None) -> dict[str, Any]:
    import nibabel as nib

    if cache is not None:
        return cache.load(case)
    # No access to case['label'], including during validation inference.
    data = preprocess_case(case, config, with_label=False)
    reference: Any = nib.load(case["image"])
    data.update(native_shape=reference.shape, native_affine=reference.affine)
    return data


def _inference_probabilities(
    model: nn.Module,
    image: np.ndarray,
    config: TorchConfig,
    device: torch.device,
    *,
    blending: InferenceBlending | None = None,
) -> np.ndarray:
    """Run the original tile/slice sequence only on the calling thread."""
    was_training = model.training
    model.eval()
    options = {} if blending is None else {"blending": blending}
    try:
        if config.mode == "3d":
            probabilities = tiled_probabilities(model, image[None], config, device, **options)
        else:
            probabilities = np.stack(
                [
                    tiled_probabilities(
                        model,
                        context_image(image, z, config.context_slices),
                        config,
                        device,
                        **options,
                    )
                    for z in range(image.shape[0])
                ],
                axis=1,
            )
    finally:
        model.train(was_training)
    return probabilities


def _finish_prediction(
    probabilities: np.ndarray,
    geometry: dict[str, Any],
    case: dict,
    config: TorchConfig,
    output: Path | None,
    cache: Any | None,
    workers: int,
    timings: dict[str, float],
    statistics: dict[str, Any] | None = None,
) -> np.ndarray:
    from .geometry import export_native_prediction
    from .torch_geometry import native_argmax, native_probabilities

    started = time.monotonic()
    native = native_probabilities(
        probabilities,
        geometry["affine"],
        tuple(geometry["native_shape"]),
        np.asarray(geometry["native_affine"]),
        workers=workers,
    )
    prediction = native_argmax(native)
    if statistics is not None:
        statistics.update(
            # Image-only continuous scan score, before any lesion postprocessing.
            # AUC still requires both reference classes in the scored cohort.
            mass_probability_max=float(np.max(native[2])),
            mass_score_definition="maximum_native_class2_probability",
            native_voxels=int(prediction.size),
            predicted_mass_voxels=int(np.count_nonzero(prediction == 2)),
        )
    timings["reconstruction_seconds"] = time.monotonic() - started
    if cache is not None:
        cache.check(case)
    started = time.monotonic()
    if output is not None:
        if cache is None:
            export_native_prediction(case["image"], prediction, output)
        else:
            cache.export_prediction(case, prediction, output)
    timings["export_seconds"] = time.monotonic() - started
    return prediction


def predict_case(
    model: nn.Module,
    case: dict,
    config: TorchConfig,
    device: torch.device,
    *,
    output: Path | None = None,
    cache: Any | None = None,
    blending: InferenceBlending | None = None,
) -> np.ndarray:
    """Predict one case with unchanged tiling and exact finite native argmax."""
    data = _prepare_prediction(case, config, cache)
    options = {} if blending is None else {"blending": blending}
    probabilities = _inference_probabilities(model, data["image"], config, device, **options)
    geometry = {key: value for key, value in data.items() if key != "image"}
    del data
    return _finish_prediction(
        probabilities, geometry, case, config, output, cache, config.workers, {}
    )


@dataclass
class PredictionResult:
    """One ordered outcome; callers choose fail-fast or per-case continuation."""

    case: dict
    prediction: np.ndarray | None = None
    error: Exception | None = None
    wall_seconds: float = 0.0
    timings: dict[str, float] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)


def iter_predictions(
    model: nn.Module,
    cases: Sequence[dict],
    config: TorchConfig,
    device: torch.device,
    *,
    output_directory: Path | None = None,
    cache: Any | None = None,
    blending: InferenceBlending | None = None,
) -> Generator[PredictionResult, None, None]:
    """Overlap bounded CPU stages around serial, unchanged model inference.

    At most one next case is prepared and one previous case is reconstructed.
    No worker executes the model or advances an RNG. Results retain case order;
    errors are delivered with their case, never confused with a following case.
    ``workers=1`` stays serial. Otherwise one CPU worker prepares images and at
    most ``min(3, workers-1)`` independent channels reconstruct the prior case.

    Use ``contextlib.closing`` when consuming only part of the iterator: closing
    cancels queued preparation and waits for in-flight CPU work before returning.
    The caller owns any cache and retains it across validation epochs. Prediction
    buffers for a finished case are released before accepting another result.
    Timings include CPU stage work separately; wall time may overlap other cases.
    """
    if not cases:
        return

    def prepare(case: dict) -> tuple[dict | None, PredictionResult, float]:
        started = time.monotonic()
        result = PredictionResult(case)
        try:
            data = _prepare_prediction(case, config, cache)
        except Exception as exc:
            result.error = exc.with_traceback(None)
            data = None
        result.timings["preprocess_seconds"] = time.monotonic() - started
        return data, result, started

    def finish(
        probabilities: np.ndarray | None,
        geometry: dict,
        result: PredictionResult,
        started: float,
        workers: int,
    ) -> PredictionResult:
        if result.error is None:
            try:
                if probabilities is None:
                    raise ValueError("Prediction produced no probabilities")
                output = (
                    output_directory / f"{result.case['case_id']}.nii.gz"
                    if output_directory is not None
                    else None
                )
                result.prediction = _finish_prediction(
                    probabilities,
                    geometry,
                    result.case,
                    config,
                    output,
                    cache,
                    workers,
                    result.timings,
                    result.statistics,
                )
            except Exception as exc:
                result.error = exc.with_traceback(None)
        result.wall_seconds = time.monotonic() - started
        return result

    def infer(data: dict | None, result: PredictionResult) -> tuple[np.ndarray | None, dict]:
        if result.error is not None:
            return None, {}
        started = time.monotonic()
        try:
            if data is None:
                raise ValueError("Prediction produced no preprocessed image")
            options = {} if blending is None else {"blending": blending}
            probabilities = _inference_probabilities(
                model, data["image"], config, device, **options
            )
            return probabilities, {key: value for key, value in data.items() if key != "image"}
        except Exception as exc:
            result.error = exc.with_traceback(None)
            return None, {}
        finally:
            result.timings["inference_seconds"] = time.monotonic() - started

    if config.workers == 1:
        for case in cases:
            data, result, started = prepare(case)
            probabilities, geometry = infer(data, result)
            del data
            yield finish(probabilities, geometry, result, started, 1)
            del probabilities, geometry, result
        return

    preparation = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ct-prepare")
    reconstruction = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ct-reconstruct")
    prepared: Future | None = None
    pending: Future | None = None
    try:
        prepared = preparation.submit(prepare, cases[0])
        for index in range(len(cases)):
            assert prepared is not None
            data, result, started = prepared.result()
            prepared = (
                preparation.submit(prepare, cases[index + 1]) if index + 1 < len(cases) else None
            )
            probabilities, geometry = infer(data, result)
            del data
            previous = pending.result() if pending is not None else None
            pending = reconstruction.submit(
                finish, probabilities, geometry, result, started, max(1, config.workers - 1)
            )
            del probabilities, geometry, result
            if previous is not None:
                yield previous
                del previous
        if pending is not None:
            yield pending.result()
    finally:
        if prepared is not None:
            prepared.cancel()
        if pending is not None:
            pending.cancel()
        preparation.shutdown(wait=True, cancel_futures=True)
        reconstruction.shutdown(wait=True, cancel_futures=True)


def dice_ce(
    logits: torch.Tensor, targets: torch.Tensor, *, dice_reduction: str = "batch"
) -> torch.Tensor:
    """CE plus foreground Dice, pooling the batch or equally weighting patches.

    Per-sample reduction averages Dice over each foreground class in each patch;
    it does not identify patients or exclude reference-empty classes. The default
    preserves the historical batch reduction and smoothing arithmetic exactly.
    """
    if dice_reduction not in ("batch", "per_sample"):
        raise ValueError("dice_reduction must be batch or per_sample")
    probabilities = logits.float().softmax(1)
    truth = torch.nn.functional.one_hot(targets, 3).movedim(-1, 1).float()
    axes = (
        (0, *range(2, logits.ndim)) if dice_reduction == "batch" else tuple(range(2, logits.ndim))
    )
    intersection = (probabilities * truth).sum(axes)
    denominator = (probabilities + truth).sum(axes)
    if dice_reduction == "per_sample":
        intersection, denominator = intersection[:, 1:], denominator[:, 1:]
    else:
        intersection, denominator = intersection[1:], denominator[1:]
    dice = (2 * intersection + 1e-5) / (denominator + 1e-5)
    return torch.nn.functional.cross_entropy(logits.float(), targets) + 1 - dice.mean()


def dice_focal(
    logits: torch.Tensor, targets: torch.Tensor, *, coefficient: float, gamma: float
) -> torch.Tensor:
    """Batch foreground soft Dice + coefficient * unweighted multiclass focal.

    Coefficient is the user's alpha multiplying the whole focal term, not a
    per-class alpha. Mean reduction includes background. Gamma=0 and coefficient=1
    recover CE + Dice. Log-softmax/cross-entropy keep extreme logits finite.
    """
    ce = torch.nn.functional.cross_entropy(logits.float(), targets, reduction="none")
    probabilities = logits.float().softmax(1)
    truth = torch.nn.functional.one_hot(targets, 3).movedim(-1, 1).float()
    axes = (0, *range(2, logits.ndim))
    intersection = (probabilities * truth).sum(axes)
    denominator = (probabilities + truth).sum(axes)
    dice = (2 * intersection[1:] + 1e-5) / (denominator[1:] + 1e-5)
    focal = ((1 - torch.exp(-ce)).pow(gamma) * ce).mean()
    return coefficient * focal + 1 - dice.mean()


def training_loss(
    model: nn.Module,
    images: torch.Tensor,
    labels: torch.Tensor,
    config: TorchConfig | None = None,
) -> torch.Tensor:
    native: Callable[..., torch.Tensor] | None = getattr(model, "training_loss", None)
    if config is not None and config.loss == "dice_focal":
        if native is not None:
            raise ValueError("Focal objective cannot replace a model-native training loss")
        return dice_focal(
            model(images), labels, coefficient=config.focal_coefficient, gamma=config.focal_gamma
        )
    reduction = config.dice_reduction if config is not None else "batch"
    if native is not None:
        if reduction != "batch":
            raise ValueError("Per-sample Dice cannot replace a model-native training loss")
        return native(images, labels)
    return dice_ce(model(images), labels, dice_reduction=reduction)
