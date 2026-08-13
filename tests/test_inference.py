"""Sliding-window / TTA tests, all against deterministic fake models.

The point of a fake model here is that stitching is pure arithmetic: with a
pixelwise model producing small integers, every assertion below can be *exact*
equality rather than allclose. A tolerance would hide precisely the bug this
file exists to catch -- an off-by-one in the window grid that leaves a seam or a
row of NaN at the image edge.
"""

from __future__ import annotations

import pytest
import torch

from segmentary.engine.inference import (
    InferenceConfig,
    _window_grid,
    inference,
    slide_inference,
    whole_inference,
)

C = 4


class PixelwiseModel:
    """logits[n, c, y, x] depends only on image[n, :, y, x], with integer values.

    Pixelwise means the full-image answer and every tiled answer agree exactly at
    each pixel, so overlap-averaging must be the identity. Integer values keep the
    sum-then-divide exact in float32 for the small overlap counts used here.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, image: torch.Tensor) -> torch.Tensor:
        self.calls += 1
        chans = [image[:, c % image.shape[1]] * (c + 1) - c for c in range(C)]
        return torch.stack(chans, dim=1)


class ConvModel:
    """A 3x3 conv: context-dependent, so tiles genuinely differ from the whole."""

    def __init__(self, seed: int = 0) -> None:
        g = torch.Generator().manual_seed(seed)
        self.weight = torch.randn(C, 3, 3, 3, generator=g)
        self.calls = 0

    def __call__(self, image: torch.Tensor) -> torch.Tensor:
        self.calls += 1
        return torch.nn.functional.conv2d(image, self.weight, padding=1)


class OnesModel:
    def __call__(self, image: torch.Tensor) -> torch.Tensor:
        return torch.ones(image.shape[0], C, image.shape[2], image.shape[3])


class SymmetricPixelModel:
    """Pixelwise and therefore flip-equivariant: f(flip(x)) == flip(f(x))."""

    def __call__(self, image: torch.Tensor) -> torch.Tensor:
        return torch.stack(
            [image[:, c % image.shape[1]] * (0.5 * c + 1.0) for c in range(C)], dim=1
        )


def _image(h: int, w: int, n: int = 2, seed: int = 0) -> torch.Tensor:
    """Small integer-valued pixels: keeps every downstream sum exact in float32."""
    g = torch.Generator().manual_seed(seed)
    return torch.randint(0, 8, (n, 3, h, w), generator=g).float()


# --------------------------------------------------------------------------
# window grid
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "h,w,win,stride",
    [
        (1080, 1920, (1024, 1024), (768, 768)),
        (1024, 2048, (512, 512), (341, 341)),
        (1080, 1920, (1024, 1024), (1024, 1024)),
        (129, 131, (64, 64), (63, 61)),
        (1024, 1024, (1024, 1024), (768, 768)),
    ],
)
def test_window_grid_covers_every_pixel_and_never_overruns(h, w, win, stride):
    cells = _window_grid(h, w, win, stride)
    cover = torch.zeros(h, w, dtype=torch.int32)
    for y1, y2, x1, x2 in cells:
        assert 0 <= y1 < y2 <= h and 0 <= x1 < x2 <= w, f"tile {(y1, y2, x1, x2)} outside {h}x{w}"
        assert (y2 - y1, x2 - x1) == win, "clamped tile must keep the full window size"
        cover[y1:y2, x1:x2] += 1
    assert int(cover.min()) >= 1, "some pixel is in no window; averaging would divide by zero"
    assert (y2, x2) == (h, w), "the last tile must end exactly on the bottom-right corner"


def test_awkward_size_coverage_end_to_end():
    """1080x1920 with window 1024 stride 768: the real eval geometry."""
    cfg = InferenceConfig(window=(1024, 1024), stride=(768, 768))
    out = slide_inference(OnesModel(), torch.zeros(1, 3, 1080, 1920), C, cfg)
    assert out.shape == (1, C, 1080, 1920)
    assert torch.isnan(out).sum() == 0
    assert torch.equal(out, torch.ones_like(out)), (
        "averaging a constant model must return that constant"
    )


# --------------------------------------------------------------------------
# slide vs whole
# --------------------------------------------------------------------------


def test_slide_with_window_equal_to_image_equals_whole():
    image = _image(96, 128)
    model = ConvModel()
    cfg = InferenceConfig(window=(96, 128), stride=(64, 64))
    slide = slide_inference(model, image, C, cfg)
    assert model.calls == 1, "one window must cover the image exactly"
    assert torch.equal(slide, whole_inference(model, image, C))


def test_pixelwise_model_slide_reproduces_exact_logits():
    image = _image(150, 213)
    model = PixelwiseModel()
    cfg = InferenceConfig(window=(64, 64), stride=(48, 40))
    slide = slide_inference(model, image, C, cfg)
    assert model.calls == len(_window_grid(150, 213, (64, 64), (48, 40))) == 3 * 5
    cover = torch.zeros(150, 213, dtype=torch.int32)
    for y1, y2, x1, x2 in _window_grid(150, 213, (64, 64), (48, 40)):
        cover[y1:y2, x1:x2] += 1
    assert int(cover.max()) > 1, (
        "sanity: this geometry must actually overlap, or the test is vacuous"
    )
    assert torch.equal(slide, whole_inference(model, image, C)), "overlap averaging must be a no-op"


def test_slide_falls_back_to_whole_when_image_is_smaller_than_window():
    image = _image(64, 512)  # short in H only -- the fallback must trigger on either axis
    model = ConvModel()
    cfg = InferenceConfig(window=(128, 128), stride=(96, 96))
    out = slide_inference(model, image, C, cfg)
    assert model.calls == 1, "fallback must run the image once, unpadded"
    assert torch.equal(out, whole_inference(model, image, C))


def test_slide_accumulates_in_float32_under_bf16_model():
    class BF16Model:
        def __call__(self, image):
            return torch.ones(
                image.shape[0], C, image.shape[2], image.shape[3], dtype=torch.bfloat16
            )

    cfg = InferenceConfig(window=(128, 128), stride=(64, 64))
    out = slide_inference(BF16Model(), torch.zeros(1, 3, 200, 200), C, cfg)
    assert out.dtype == torch.float32

    # The fallback branch must honour the same contract: a return dtype that depends
    # on the image size is exactly the kind of thing that only shows up in one dataset.
    small = slide_inference(BF16Model(), torch.zeros(1, 3, 64, 200), C, cfg)
    assert small.dtype == torch.float32


def test_bad_logit_shape_is_loud():
    class WrongClasses:
        def __call__(self, image):
            return torch.zeros(image.shape[0], C + 1, image.shape[2], image.shape[3])

    # A channel mismatch is a label-space bug, and must not be diagnosed as an
    # upsampling bug -- the two live in different files.
    with pytest.raises(ValueError, match="different label space"):
        whole_inference(WrongClasses(), _image(32, 32), C)

    class Stride4:
        def __call__(self, image):
            return torch.zeros(image.shape[0], C, image.shape[2] // 4, image.shape[3] // 4)

    with pytest.raises(ValueError, match="upsample inside the model wrapper"):
        slide_inference(
            Stride4(), _image(160, 160), C, InferenceConfig(window=(64, 64), stride=(32, 32))
        )


# --------------------------------------------------------------------------
# TTA
# --------------------------------------------------------------------------


def test_single_scale_no_flip_is_exactly_a_plain_pass():
    image = _image(150, 213)
    model = ConvModel()
    cfg = InferenceConfig(window=(64, 64), stride=(48, 48), scales=(1.0,), flip=False)
    tta = inference(model, image, C, cfg)
    assert torch.equal(tta, slide_inference(model, image, C, cfg)), (
        "TTA must not touch the single-view path"
    )

    whole_cfg = InferenceConfig(sliding_window=False, scales=(1.0,), flip=False)
    assert torch.equal(inference(model, image, C, whole_cfg), whole_inference(model, image, C))


def test_flip_tta_on_symmetric_input_equals_no_tta():
    base = _image(64, 48, n=1, seed=3)
    image = torch.cat([base, base.flip(3)], dim=3)  # exactly mirror-symmetric
    assert torch.equal(image, image.flip(3))

    model = SymmetricPixelModel()
    cfg = InferenceConfig(sliding_window=False, scales=(1.0,), flip=True)
    tta = inference(model, image, C, cfg)
    plain = whole_inference(model, image, C).softmax(dim=1)
    assert torch.equal(tta, plain), "two identical views must average back to the single view"


def test_multi_scale_tta_returns_probabilities_at_original_size():
    image = _image(96, 160)
    cfg = InferenceConfig(sliding_window=False, scales=(0.5, 1.0, 1.75), flip=True)
    out = inference(ConvModel(), image, C, cfg)
    assert out.shape == (2, C, 96, 160)
    assert torch.allclose(out.sum(dim=1), torch.ones(2, 96, 160), atol=1e-5)
    assert bool((out >= 0).all())


def test_multi_scale_runs_every_view():
    model = ConvModel()
    cfg = InferenceConfig(sliding_window=False, scales=(0.5, 1.0), flip=True)
    inference(model, _image(64, 64, n=1), C, cfg)
    assert model.calls == 4


def test_scaled_view_shapes_are_resized_back_from_odd_sizes():
    image = _image(101, 67, n=1)
    cfg = InferenceConfig(window=(64, 64), stride=(48, 48), scales=(0.33, 1.0), flip=False)
    out = inference(PixelwiseModel(), image, C, cfg)
    assert out.shape == (1, C, 101, 67)
    assert torch.isnan(out).sum() == 0


# --------------------------------------------------------------------------
# config validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stride": (1024, 1025)},
        {"stride": (0, 768)},
        {"window": (0, 512)},
        {"scales": ()},
        {"scales": (1.0, -0.5)},
    ],
)
def test_invalid_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        InferenceConfig(**kwargs)
