"""Augmentation tests. These catch the bugs that are invisible in a loss curve.

Milestone 1 of the project plan is "dump overlays and look at them" precisely
because misalignment and bad ignore-padding do not show up in training metrics.
These tests automate the parts of that check that can be automated.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
import torch

from segmentary.data.transforms import (
    AugConfig,
    build_eval_transform,
    build_overfit_transform,
    build_train_transform,
    denormalize,
)

IGNORE = 255


def _sample(h=64, w=96, seed=0):
    rng = np.random.default_rng(seed)
    image = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
    mask = rng.choice(np.array([0, 3, 17, 20], dtype=np.uint8), size=(h, w))
    return image, mask


# --------------------------------------------------------------------------
# THE padding bug
# --------------------------------------------------------------------------


def test_crop_padding_fills_mask_with_ignore_not_zero():
    """Downscale a small image so the crop must pad, then inspect the padding."""
    cfg = AugConfig(crop=(128, 128), scale_min=0.5, scale_max=0.5, hflip_p=0.0, color_jitter_p=0.0)
    image, mask = _sample(64, 64)
    mask[:] = 3  # every real pixel is class 3, so 255 can only come from padding

    out = build_train_transform(cfg)(image=image, mask=mask)
    m = out["mask"].numpy()

    assert m.shape == (128, 128)
    ids = set(np.unique(m).tolist())
    assert ids == {3, IGNORE}, f"expected only class 3 and ignore padding, got {sorted(ids)}"
    assert 0 not in ids, "padding leaked in as class 0 (`road`) -- the classic bug"
    assert (m == IGNORE).sum() > 0, "sanity: this config must actually pad"


def test_overfit_transform_also_pads_with_ignore():
    cfg = AugConfig(crop=(96, 96))
    image, mask = _sample(48, 48)
    mask[:] = 7
    m = build_overfit_transform(cfg)(image=image, mask=mask)["mask"].numpy()
    assert set(np.unique(m).tolist()) == {7, IGNORE}


def test_eval_padding_fills_mask_with_ignore():
    cfg = AugConfig()
    image, mask = _sample(70, 70)
    mask[:] = 2
    m = build_eval_transform(cfg, pad_to_multiple=32)(image=image, mask=mask)["mask"].numpy()
    assert m.shape == (96, 96)
    assert set(np.unique(m).tolist()) == {2, IGNORE}


def test_legacy_mask_value_kwarg_is_rejected_loudly():
    """albumentations 2.x only warns about `mask_value`; we must make it fatal.

    Without this, code written against the 1.x API pads with 0 forever and the
    only symptom is a slightly wrong `road` IoU.
    """
    import warnings

    import albumentations as A

    with pytest.warns(UserWarning, match="are not valid for transform"):
        A.PadIfNeeded(min_height=8, min_width=8, mask_value=255)

    # ...and confirm our strict wrapper would turn that into an exception
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message=r"Argument\(s\).*are not valid for transform")
        with pytest.raises(UserWarning):
            A.PadIfNeeded(min_height=8, min_width=8, mask_value=255)


# --------------------------------------------------------------------------
# label integrity
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scale", [0.5, 0.75, 1.5, 2.0])
def test_scaling_never_invents_label_ids(scale):
    cfg = AugConfig(
        crop=(32, 32), scale_min=scale, scale_max=scale, hflip_p=0.0, color_jitter_p=0.0
    )
    image, mask = _sample(64, 64)
    allowed = set(np.unique(mask).tolist()) | {IGNORE}

    for seed in range(5):
        np.random.seed(seed)
        m = build_train_transform(cfg)(image=image, mask=mask)["mask"].numpy()
        got = set(np.unique(m).tolist())
        assert got <= allowed, f"interpolation invented ids {sorted(got - allowed)}"


def test_bilinear_mask_resize_would_corrupt_labels():
    """Document the failure mode the explicit INTER_NEAREST protects against."""
    import albumentations as A

    _, mask = _sample(64, 64)
    bad = A.Compose(
        [A.RandomScale(scale_limit=(0.75, 0.75), mask_interpolation=cv2.INTER_LINEAR, p=1.0)]
    )(image=np.zeros((64, 64, 3), np.uint8), mask=mask)["mask"]
    assert len(np.unique(bad)) > len(np.unique(mask)), "expected blended ids from bilinear masks"


# --------------------------------------------------------------------------
# image/mask geometric alignment
# --------------------------------------------------------------------------


def test_image_and_mask_stay_aligned_through_flip():
    """An asymmetric pattern must move identically in both image and mask."""
    h, w = 32, 48
    mask = np.zeros((h, w), np.uint8)
    mask[:, : w // 2] = 1  # left half = 1, right half = 0
    image = np.stack([mask * 100] * 3, axis=-1).astype(np.uint8)

    cfg = AugConfig(crop=(h, w), scale_min=1.0, scale_max=1.0, hflip_p=1.0, color_jitter_p=0.0)
    out = build_train_transform(cfg)(image=image, mask=mask)
    m = out["mask"].numpy()
    img = denormalize(out["image"], cfg)

    assert (m[:, : w // 2] == 0).all() and (m[:, w // 2 :] == 1).all(), "mask was not flipped"
    left_bright = img[:, : w // 2, 0].mean()
    right_bright = img[:, w // 2 :, 0].mean()
    assert right_bright > left_bright + 50, "image did not flip with the mask"


def test_image_and_mask_stay_aligned_through_scale_and_crop():
    """Mask value must keep predicting image intensity after a random geometry op."""
    h, w = 128, 128
    yy, xx = np.mgrid[0:h, 0:w]
    mask = ((yy // 32) % 2 * 2 + (xx // 32) % 2).astype(np.uint8)  # 4 blocky classes
    image = np.stack([mask * 60] * 3, axis=-1).astype(np.uint8)

    cfg = AugConfig(crop=(64, 64), scale_min=0.75, scale_max=1.5, hflip_p=0.5, color_jitter_p=0.0)
    for seed in range(8):
        np.random.seed(seed)
        out = build_train_transform(cfg)(image=image, mask=mask)
        m = out["mask"].numpy()
        img = denormalize(out["image"], cfg)[:, :, 0].astype(np.float64)

        real = m != IGNORE
        if real.sum() < 100:
            continue
        # interior pixels only: bilinear image resampling smears block boundaries
        interior = real & (cv2.erode(real.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)
        if interior.sum() < 50:
            continue
        expected = m[interior].astype(np.float64) * 60
        assert np.abs(img[interior] - expected).mean() < 12.0, (
            f"seed {seed}: image and mask drifted apart (mean abs err "
            f"{np.abs(img[interior] - expected).mean():.1f})"
        )


# --------------------------------------------------------------------------
# tensor contract
# --------------------------------------------------------------------------


def test_output_tensor_shapes_and_dtypes():
    cfg = AugConfig(crop=(64, 64))
    image, mask = _sample(128, 128)
    out = build_train_transform(cfg)(image=image, mask=mask)

    assert isinstance(out["image"], torch.Tensor) and isinstance(out["mask"], torch.Tensor)
    assert out["image"].shape == (3, 64, 64)
    assert out["image"].dtype == torch.float32
    assert out["mask"].shape == (64, 64)
    # mask must stay integral: a float mask silently breaks ignore_index compares
    assert not out["mask"].dtype.is_floating_point, f"mask became {out['mask'].dtype}"
    assert int(out["mask"].max()) <= 255


def test_eval_transform_preserves_resolution():
    cfg = AugConfig()
    image, mask = _sample(64, 96)
    out = build_eval_transform(cfg)(image=image, mask=mask)
    assert out["image"].shape == (3, 64, 96)
    assert out["mask"].shape == (64, 96)


def test_normalize_roundtrip_is_close():
    cfg = AugConfig()
    image, mask = _sample(32, 32)
    out = build_eval_transform(cfg)(image=image, mask=mask)
    back = denormalize(out["image"], cfg)
    assert np.abs(back.astype(int) - image.astype(int)).max() <= 1


@pytest.mark.parametrize(
    "builder",
    [build_train_transform, build_eval_transform, build_overfit_transform],
)
def test_bgr_channel_order_is_applied_before_normalization(builder):
    cfg = AugConfig(
        crop=(1, 1),
        scale_min=1.0,
        scale_max=1.0,
        hflip_p=0.0,
        color_jitter_p=0.0,
        mean=(0.0, 0.0, 0.0),
        std=(1.0, 1.0, 1.0),
        channel_order="bgr",
    )
    image = np.array([[[10, 20, 30]]], dtype=np.uint8)
    mask = np.zeros((1, 1), dtype=np.uint8)
    tensor = builder(cfg)(image=image, mask=mask)["image"][:, 0, 0]
    assert torch.allclose(tensor, torch.tensor([30, 20, 10]) / 255.0)
    restored = denormalize(tensor[:, None, None], cfg)
    assert restored.tolist() == image.tolist()


def test_config_rejects_bad_values():
    with pytest.raises(ValueError, match="ignore_index must be 255"):
        AugConfig(ignore_index=0)
    with pytest.raises(ValueError, match="scale_min <= scale_max"):
        AugConfig(scale_min=2.0, scale_max=0.5)
    with pytest.raises(ValueError, match="crop must be positive"):
        AugConfig(crop=(0, 512))
    with pytest.raises(ValueError, match="channel_order"):
        AugConfig(channel_order="cmyk")
