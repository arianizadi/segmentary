"""Numerical proof that ignore_index and inactive classes contribute nothing.

The project spec calls for this to be asserted numerically rather than argued.
Each test constructs a case where a wrong implementation would visibly differ.

Failure modes these catch:
  * ignore_index pixels padded with 0 (the `road` class) leaking into the loss;
  * ignored pixels quietly counted as correct, inflating pixel accuracy;
  * inactive classes acting as implicit negatives, so a later stage unlearns
    classes it no longer sees.
"""

from __future__ import annotations

import pytest
import torch

from segmentary.engine.losses import LossConfig, SegmentationLoss, mask_inactive
from segmentary.engine.metrics import ConfusionMatrix

IGNORE = 255
C, H, W = 6, 12, 16


def _batch(seed: int = 0, ignore_frac: float = 0.4):
    g = torch.Generator().manual_seed(seed)
    logits = torch.randn(2, C, H, W, generator=g, dtype=torch.float64)
    target = torch.randint(0, C, (2, H, W), generator=g)
    ignored = torch.rand(2, H, W, generator=g) < ignore_frac
    target[ignored] = IGNORE
    return logits, target, ignored


# --------------------------------------------------------------------------
# loss
# --------------------------------------------------------------------------


@pytest.mark.parametrize("aux,weight", [("none", 0.0), ("lovasz", 1.0), ("dice", 1.0)])
def test_loss_ignores_logits_under_ignored_pixels(aux, weight):
    """Perturbing logits beneath ignored pixels must not move the loss at all."""
    logits, target, ignored = _batch()
    loss_fn = SegmentationLoss(LossConfig(aux=aux, aux_weight=weight), C, IGNORE).double()

    before, _ = loss_fn(logits, target)

    perturbed = logits.clone()
    noise = torch.randn(
        logits.shape, generator=torch.Generator().manual_seed(99), dtype=torch.float64
    )
    perturbed[ignored.unsqueeze(1).expand_as(logits)] += (
        1000.0 * noise[ignored.unsqueeze(1).expand_as(logits)]
    )
    after, _ = loss_fn(perturbed, target)

    assert torch.equal(before, after), f"{aux}: loss changed by {abs(float(after - before)):.3e}"


@pytest.mark.parametrize("aux,weight", [("none", 0.0), ("lovasz", 1.0), ("dice", 1.0)])
def test_no_gradient_flows_to_ignored_pixels(aux, weight):
    logits, target, ignored = _batch()
    logits.requires_grad_(True)
    loss_fn = SegmentationLoss(LossConfig(aux=aux, aux_weight=weight), C, IGNORE).double()

    loss, _ = loss_fn(logits, target)
    loss.backward()

    grad_at_ignored = logits.grad[ignored.unsqueeze(1).expand_as(logits)]
    assert torch.count_nonzero(grad_at_ignored) == 0, (
        f"{aux}: {int(torch.count_nonzero(grad_at_ignored))} non-zero grads under ignored pixels"
    )
    assert torch.count_nonzero(logits.grad) > 0, "sanity: valid pixels must still receive gradient"


def test_ce_equals_loss_over_valid_pixels_only():
    """CE with ignore_index must equal CE computed on the valid subset alone."""
    import torch.nn.functional as F

    logits, target, _ = _batch()
    loss_fn = SegmentationLoss(LossConfig(), C, IGNORE).double()
    got, _ = loss_fn(logits, target)

    valid = (target != IGNORE).reshape(-1)
    flat_logits = logits.permute(0, 2, 3, 1).reshape(-1, C)[valid]
    flat_target = target.reshape(-1)[valid]
    expected = F.cross_entropy(flat_logits, flat_target)

    assert torch.allclose(got, expected, atol=1e-12), f"{float(got)} != {float(expected)}"


def test_all_ignored_batch_yields_zero_not_nan():
    """A crop that is entirely padding must not poison training with NaN."""
    logits = torch.randn(1, C, H, W, dtype=torch.float64)
    target = torch.full((1, H, W), IGNORE, dtype=torch.long)
    for aux, w in [("none", 0.0), ("lovasz", 1.0), ("dice", 1.0)]:
        loss_fn = SegmentationLoss(LossConfig(aux=aux, aux_weight=w), C, IGNORE).double()
        loss, _ = loss_fn(logits, target)
        assert torch.isfinite(loss), f"{aux}: produced {float(loss)} on an all-ignored batch"


def test_padding_filled_with_zero_would_be_detected():
    """Guard the classic bug: padding masks with 0 turns padding into class 0.

    If a transform ever fills mask padding with 0 instead of ignore_index, the
    loss changes. This test documents the size of that error so the failure is
    recognisable rather than mysterious.
    """
    logits, target, ignored = _batch(ignore_frac=0.5)
    loss_fn = SegmentationLoss(LossConfig(), C, IGNORE).double()

    correct, _ = loss_fn(logits, target)
    wrong_target = target.clone()
    wrong_target[ignored] = 0  # the bug
    wrong, _ = loss_fn(logits, wrong_target)

    assert not torch.allclose(correct, wrong), "zero-filled padding must not be silently equivalent"


# --------------------------------------------------------------------------
# inactive classes (unified_head)
# --------------------------------------------------------------------------


def test_inactive_classes_receive_no_gradient():
    logits, target, _ = _batch()
    target[target == 5] = 4  # ensure class 5 is absent from the labels
    logits.requires_grad_(True)

    active = torch.ones(C, dtype=torch.bool)
    active[5] = False
    loss_fn = SegmentationLoss(LossConfig(), C, IGNORE).double()
    loss, _ = loss_fn(logits, target, active=active)
    loss.backward()

    assert torch.count_nonzero(logits.grad[:, 5]) == 0, (
        "an inactive class received gradient; it would be unlearned during this stage"
    )
    assert torch.count_nonzero(logits.grad[:, 0]) > 0


def test_masking_inactive_class_matches_training_without_it():
    """Masking class C-1 must give the same loss as a model that never had it."""
    logits, target, _ = _batch()
    target[target == C - 1] = 0

    active = torch.ones(C, dtype=torch.bool)
    active[C - 1] = False
    full = SegmentationLoss(LossConfig(), C, IGNORE).double()
    masked_loss, _ = full(logits, target, active=active)

    reduced = SegmentationLoss(LossConfig(), C - 1, IGNORE).double()
    reduced_loss, _ = reduced(logits[:, : C - 1], target)

    assert torch.allclose(masked_loss, reduced_loss, atol=1e-10), (
        f"masked {float(masked_loss)} != reduced {float(reduced_loss)}"
    )


def test_mask_inactive_rejects_empty_and_mismatched_masks():
    logits = torch.randn(1, C, 4, 4)
    with pytest.raises(ValueError, match="excludes every class"):
        mask_inactive(logits, torch.zeros(C, dtype=torch.bool))
    with pytest.raises(ValueError, match="does not match"):
        mask_inactive(logits, torch.ones(C + 1, dtype=torch.bool))


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------


def test_ignored_pixels_do_not_enter_the_confusion_matrix():
    g = torch.Generator().manual_seed(3)
    pred = torch.randint(0, C, (2, H, W), generator=g)
    target = torch.randint(0, C, (2, H, W), generator=g)

    clean = ConfusionMatrix(C, IGNORE)
    clean.update(pred, target)

    # Same data, but half the pixels relabelled to ignore and mispredicted.
    ignored = torch.rand(2, H, W, generator=g) < 0.5
    dirty_target = target.clone()
    dirty_target[ignored] = IGNORE
    dirty_pred = pred.clone()
    dirty_pred[ignored] = (pred[ignored] + 1) % C  # deliberately wrong

    subset = ConfusionMatrix(C, IGNORE)
    subset.update(dirty_pred, dirty_target)

    reference = ConfusionMatrix(C, IGNORE)
    reference.update(pred[~ignored], target[~ignored])

    assert torch.equal(subset.mat, reference.mat)
    assert int(subset.mat.sum()) == int((~ignored).sum())
    assert not torch.equal(subset.mat, clean.mat), "sanity: the two matrices should differ"


def test_metrics_are_invariant_to_adding_ignored_pixels():
    g = torch.Generator().manual_seed(4)
    pred = torch.randint(0, C, (1, H, W), generator=g)
    target = torch.randint(0, C, (1, H, W), generator=g)

    base = ConfusionMatrix(C, IGNORE)
    base.update(pred, target)
    before = base.compute()

    pad_pred = torch.randint(0, C, (1, H, W), generator=g)
    pad_target = torch.full((1, H, W), IGNORE, dtype=torch.long)
    base.update(pad_pred, pad_target)
    after = base.compute()

    assert before.miou == after.miou
    assert before.pixel_accuracy == after.pixel_accuracy
    assert torch.equal(before.confusion, after.confusion)


def test_perfect_prediction_scores_one_and_absent_classes_are_nan():
    target = torch.arange(C).repeat_interleave(4).reshape(1, 2, -1)[:, :, :]
    target = target.reshape(1, -1)
    target = target.reshape(1, 1, -1).expand(1, 3, -1).contiguous()
    cm = ConfusionMatrix(C, IGNORE)
    cm.update(target.clone(), target.clone())
    res = cm.compute()
    assert res.miou == pytest.approx(1.0)
    assert res.pixel_accuracy == pytest.approx(1.0)

    # a class that appears nowhere is NaN, not 0, so it cannot drag the mean down
    partial_target = torch.zeros(1, 4, 4, dtype=torch.long)
    cm2 = ConfusionMatrix(C, IGNORE)
    cm2.update(torch.zeros(1, 4, 4, dtype=torch.long), partial_target)
    res2 = cm2.compute()
    assert res2.miou == pytest.approx(1.0)
    assert bool(torch.isnan(res2.iou[1:]).all())


def test_inactive_classes_report_nan_not_zero():
    """A class the dataset cannot label must not be scored as a total failure."""
    active = torch.ones(C, dtype=torch.bool)
    active[C - 1] = False
    cm = ConfusionMatrix(C, IGNORE, active=active)

    target = torch.randint(0, C - 1, (1, H, W))
    cm.update(target.clone(), target.clone())
    res = cm.compute()

    assert bool(torch.isnan(res.iou[C - 1]))
    assert res.miou == pytest.approx(1.0)


def test_out_of_range_prediction_fails_loudly():
    cm = ConfusionMatrix(C, IGNORE)
    with pytest.raises(ValueError, match="predictions outside"):
        cm.update(
            torch.full((1, 4, 4), C, dtype=torch.long), torch.zeros(1, 4, 4, dtype=torch.long)
        )


def test_unmapped_target_fails_loudly():
    """A raw Cityscapes labelId reaching the metric means the LUT was skipped."""
    cm = ConfusionMatrix(C, IGNORE)
    with pytest.raises(ValueError, match="taxonomy LUT was probably not applied"):
        cm.update(
            torch.zeros(1, 4, 4, dtype=torch.long), torch.full((1, 4, 4), 33, dtype=torch.long)
        )
