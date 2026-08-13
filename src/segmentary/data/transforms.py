"""Albumentations pipelines. Mask padding is filled with ignore_index, always.

TWO VERIFIED FOOTGUNS this module is built around (both checked empirically
against albumentations 2.0.8, see tests/test_transforms.py):

1. `mask_value=` was renamed to `fill_mask=` in albumentations 2.x, and the old
   name is accepted with nothing but a UserWarning before being IGNORED. Since
   most tutorials and LLM training data predate the rename, copied code silently
   pads masks with 0 -- which is the `road` class. It does not crash, it just
   quietly trains the model to call padding "road". This module therefore
   promotes albumentations' argument warnings to exceptions.

2. Masks must be resized with nearest-neighbour. With INTER_LINEAR a 4-id mask
   comes back holding a dozen interpolated ids that were never labels. The
   library default is already INTER_NEAREST; we pass it explicitly anyway so a
   future default change cannot corrupt the labels silently.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import albumentations as A
import cv2
from albumentations.pytorch import ToTensorV2

# ImageNet statistics. SegFormer, DINOv3 and the timm/smp encoders are all
# pretrained with these; normalization and RGB/BGR order may be overridden per
# model through AugConfig when an audited upstream image processor requires it.
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


@dataclass
class AugConfig:
    """Augmentation recipe. Identical across stages so curricula stay comparable."""

    crop: tuple[int, int] = (1024, 1024)
    scale_min: float = 0.5
    scale_max: float = 2.0
    hflip_p: float = 0.5
    color_jitter_p: float = 0.5
    brightness: float = 0.25
    contrast: float = 0.25
    saturation: float = 0.25
    hue: float = 0.05
    mean: tuple[float, float, float] = IMAGENET_MEAN
    std: tuple[float, float, float] = IMAGENET_STD
    channel_order: str = "rgb"
    ignore_index: int = 255
    # A RAW pixel level, not a normalised one: padding happens before Normalize
    # in every pipeline below, so 0 pads with black and normalises to roughly
    # -2.1 sigma rather than to the dataset mean. That is deliberate and matches
    # the reference recipes. The padded region always carries ignore_index in the
    # mask, so it contributes no loss, but it does still enter the encoder's
    # receptive field and its normalisation statistics -- changing this value
    # changes what the model sees at frame borders, so it is not a free knob.
    # The mask is the thing that must never be padded with a class id.
    image_fill: int = 0

    def __post_init__(self) -> None:
        if self.ignore_index != 255:
            raise ValueError(
                f"ignore_index must be 255 to stay in uint8 masks, got {self.ignore_index}"
            )
        if not 0 < self.scale_min <= self.scale_max:
            raise ValueError(
                f"need 0 < scale_min <= scale_max, got {self.scale_min}..{self.scale_max}"
            )
        h, w = self.crop
        if h <= 0 or w <= 0:
            raise ValueError(f"crop must be positive, got {self.crop}")
        if self.channel_order not in ("rgb", "bgr"):
            raise ValueError(f"channel_order must be 'rgb' or 'bgr', got {self.channel_order!r}")


class StrictAugmentationError(RuntimeError):
    """Raised when albumentations reports an invalid transform argument."""


def _strict():
    """Context manager promoting albumentations argument warnings to errors."""
    ctx = warnings.catch_warnings()
    ctx.__enter__()
    warnings.filterwarnings("error", message=r"Argument\(s\).*are not valid for transform")
    return ctx


def _rgb_to_bgr(image, **_kwargs):
    """Convert the RGB loader output to BGR without leaving a negative stride."""
    return image[..., ::-1].copy()


def _channel_order_ops(cfg: AugConfig) -> list[A.BasicTransform]:
    if cfg.channel_order == "rgb":
        return []
    return [A.Lambda(image=_rgb_to_bgr, name="rgb_to_bgr", p=1.0)]


def build_train_transform(cfg: AugConfig) -> A.Compose:
    """RandomScale -> RandomCrop(pad to 255) -> HFlip -> ColorJitter -> Normalize."""
    h, w = cfg.crop
    ctx = _strict()
    try:
        return A.Compose(
            [
                A.RandomScale(
                    scale_limit=(cfg.scale_min - 1.0, cfg.scale_max - 1.0),
                    interpolation=cv2.INTER_LINEAR,
                    mask_interpolation=cv2.INTER_NEAREST,  # explicit: never blend label ids
                    p=1.0,
                ),
                # pad_if_needed handles the case where downscaling left the image
                # smaller than the crop. fill_mask is the whole point of this file.
                A.RandomCrop(
                    height=h,
                    width=w,
                    pad_if_needed=True,
                    border_mode=cv2.BORDER_CONSTANT,
                    fill=cfg.image_fill,
                    fill_mask=cfg.ignore_index,
                    p=1.0,
                ),
                A.HorizontalFlip(p=cfg.hflip_p),
                A.ColorJitter(
                    brightness=cfg.brightness,
                    contrast=cfg.contrast,
                    saturation=cfg.saturation,
                    hue=cfg.hue,
                    p=cfg.color_jitter_p,
                ),
                *_channel_order_ops(cfg),
                A.Normalize(mean=cfg.mean, std=cfg.std),
                ToTensorV2(),
            ]
        )
    finally:
        ctx.__exit__(None, None, None)


def build_eval_transform(cfg: AugConfig, pad_to_multiple: int | None = None) -> A.Compose:
    """Full-resolution evaluation: normalise only, optionally pad for the model stride.

    No scaling and no cropping -- evaluation happens at native resolution via
    sliding window, so that every arm is scored on identical pixels.
    """
    ops: list[A.BasicTransform] = []
    if pad_to_multiple:
        ops.append(
            A.PadIfNeeded(
                min_height=None,
                min_width=None,
                pad_height_divisor=pad_to_multiple,
                pad_width_divisor=pad_to_multiple,
                position="top_left",  # deterministic, so predictions can be un-padded
                border_mode=cv2.BORDER_CONSTANT,
                fill=cfg.image_fill,
                fill_mask=cfg.ignore_index,
            )
        )
    ops += [
        *_channel_order_ops(cfg),
        A.Normalize(mean=cfg.mean, std=cfg.std),
        ToTensorV2(),
    ]

    ctx = _strict()
    try:
        return A.Compose(ops)
    finally:
        ctx.__exit__(None, None, None)


def build_overfit_transform(cfg: AugConfig) -> A.Compose:
    """No augmentation at all -- used by overfit_check.py.

    If the pipeline cannot drive 8 images to mIoU > 0.95 with augmentation
    disabled, the bug is in the data or the model, not in the recipe.
    """
    h, w = cfg.crop
    ctx = _strict()
    try:
        return A.Compose(
            [
                A.RandomCrop(
                    height=h,
                    width=w,
                    pad_if_needed=True,
                    border_mode=cv2.BORDER_CONSTANT,
                    fill=cfg.image_fill,
                    fill_mask=cfg.ignore_index,
                    p=1.0,
                ),
                *_channel_order_ops(cfg),
                A.Normalize(mean=cfg.mean, std=cfg.std),
                ToTensorV2(),
            ]
        )
    finally:
        ctx.__exit__(None, None, None)


def denormalize(tensor, cfg: AugConfig):
    """Invert Normalize for visual inspection. Returns a uint8 HWC numpy array."""
    import numpy as np

    arr = tensor.detach().cpu().numpy().transpose(1, 2, 0)
    arr = arr * np.asarray(cfg.std) + np.asarray(cfg.mean)
    if cfg.channel_order == "bgr":
        # Overlays and image writers consume RGB even when the model consumes BGR.
        arr = arr[..., ::-1]
    return (np.clip(arr, 0.0, 1.0) * 255.0).round().astype(np.uint8)
