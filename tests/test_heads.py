"""Weight-free tests: the mask-classification collapse and the OCR head.

Split from test_models.py because nothing here needs a checkpoint -- these are
pure shape and arithmetic contracts over tiny local modules, and they run in
milliseconds whether or not HuggingFace is reachable.
"""

from __future__ import annotations

import torch
from torch import nn

from segmentary.models.heads import OCRHead
from segmentary.models.mask_classification import MaskClassWrapper

NUM_CLASSES = 21


class _TinyMaskModel(nn.Module):
    """Minimal stand-in for EoMT/Mask2Former: the output shapes are all that matter."""

    def __init__(self, num_classes: int, num_queries: int = 4, grid: int = 8) -> None:
        super().__init__()
        self.embeddings = nn.Conv2d(3, 8, 3, padding=1)
        self.class_predictor = nn.Linear(8, num_classes + 1)
        self.num_queries = num_queries
        # A fixed mask field, so a test can re-derive the expected output by hand.
        self.register_buffer("mask_logits", torch.randn(1, num_queries, grid, grid))

    def forward(self, pixel_values):
        n = pixel_values.shape[0]
        pooled = self.embeddings(pixel_values).mean(dim=(2, 3))
        cls = self.class_predictor(pooled).unsqueeze(1).expand(n, self.num_queries, -1)
        masks = self.mask_logits.expand(n, -1, -1, -1)
        return type("Out", (), {"class_queries_logits": cls, "masks_queries_logits": masks})()


def _tiny_wrapper(native_size=None) -> MaskClassWrapper:
    return MaskClassWrapper(
        _TinyMaskModel(NUM_CLASSES),
        NUM_CLASSES,
        backbone_paths=("embeddings",),
        head_paths=("class_predictor",),
        native_size=native_size,
    )


def test_mask_classification_collapses_to_dense_log_scores():
    model = _tiny_wrapper()
    out = model(torch.randn(2, 3, 32, 32))
    assert out.shape == (2, NUM_CLASSES, 32, 32)
    assert torch.isfinite(out).all()
    assert model.supports_dense_ce is False


def test_mask_classification_matches_the_reference_inference_rule():
    """Re-derive the collapse independently, in the order the HF post-processor uses."""
    model = _tiny_wrapper()
    x = torch.randn(2, 3, 32, 32)
    out = model(x)

    raw = model.model(x)
    cls_probs = raw.class_queries_logits.softmax(dim=-1)[..., :-1]
    upsampled = torch.nn.functional.interpolate(
        raw.masks_queries_logits, size=(32, 32), mode="bilinear", align_corners=False
    )
    expected = torch.einsum("bqc,bqhw->bchw", cls_probs, upsampled.sigmoid())
    assert torch.allclose(out.exp(), expected, atol=1e-6)

    # Sigmoid-then-upsample is the tempting reordering and is measurably different;
    # locking the order here keeps our eval numbers comparable to published ones.
    swapped = torch.einsum(
        "bqc,bqhw->bchw",
        cls_probs,
        torch.nn.functional.interpolate(
            raw.masks_queries_logits.sigmoid(), size=(32, 32), mode="bilinear", align_corners=False
        ),
    )
    assert not torch.allclose(swapped, expected, atol=1e-4)


def test_mask_classification_scores_are_not_probabilities():
    """The query contraction sums Q terms, so log() of it is not sign-constrained."""
    model = _tiny_wrapper()
    with torch.no_grad():
        # Push every query onto one class with a near-1 mask: the sum approaches Q.
        model.model.class_predictor.weight.zero_()
        model.model.class_predictor.bias.zero_()
        model.model.class_predictor.bias[0] = 20.0
        model.model.mask_logits.fill_(10.0)
    out = model(torch.randn(1, 3, 32, 32))
    assert out[:, 0].max() > 0


def test_mask_classification_score_floor_survives_fp16():
    """A floor below the dtype's smallest normal makes log() return -inf, then NaN."""
    model = _tiny_wrapper()
    with torch.no_grad():
        # Every query rejects every pixel: the contracted score hits the floor.
        model.model.mask_logits.fill_(-40.0)
    for dtype in (torch.float32, torch.bfloat16, torch.float16):
        with torch.autocast("cpu", dtype=dtype, enabled=dtype is not torch.float32):
            out = model(torch.randn(1, 3, 32, 32))
        assert torch.isfinite(out).all(), f"{dtype} produced non-finite log-scores"


def test_mask_classification_resizes_to_its_native_grid():
    model = _tiny_wrapper(native_size=(64, 64))
    out = model(torch.randn(1, 3, 32, 48))
    assert out.shape == (1, NUM_CLASSES, 32, 48)


def test_mask_classification_reset_head():
    model = _tiny_wrapper()
    before = model.model.class_predictor.weight.detach().clone()
    model.reset_head()
    assert not torch.equal(model.model.class_predictor.weight.detach(), before)


# ---------------------------------------------------------------- OCR head


def test_ocr_head_shapes():
    head = OCRHead(in_channels=32, num_classes=NUM_CLASSES, ocr_channels=16, key_channels=8)
    logits, aux = head(torch.randn(2, 32, 16, 16))
    assert logits.shape == (2, NUM_CLASSES, 16, 16)
    assert aux.shape == (2, NUM_CLASSES, 16, 16)


def test_ocr_head_is_differentiable():
    head = OCRHead(in_channels=16, num_classes=5, ocr_channels=8, key_channels=4)
    feats = torch.randn(2, 16, 8, 8, requires_grad=True)
    logits, aux = head(feats)
    (logits.mean() + aux.mean()).backward()
    assert feats.grad is not None and torch.isfinite(feats.grad).all()
