"""Object matching oracles: same-class instances, crowds, void, and gradients."""

from __future__ import annotations

import pytest
import torch

from segmentary.models.outputs import QueryOutput, QueryPrediction
from segmentary.objects.data import ObjectTarget
from segmentary.objects.loss import ObjectQueryLoss


def _target(
    *,
    empty: bool = False,
    valid: torch.Tensor | None = None,
    crowd: torch.Tensor | None = None,
) -> ObjectTarget:
    masks = torch.tensor([[[1, 1, 0, 0]] * 4, [[0, 0, 1, 1]] * 4], dtype=torch.float32)
    return ObjectTarget(
        class_ids=torch.zeros(0 if empty else 2, dtype=torch.long),
        masks=masks[:0] if empty else masks,
        valid=torch.ones(4, 4, dtype=torch.bool) if valid is None else valid,
        iscrowd=torch.zeros(0 if empty else 2, dtype=torch.bool) if crowd is None else crowd,
        image_id=1,
        original_size=(4, 4),
    )


def _prediction(*, gradients: bool = False) -> QueryPrediction:
    classes = torch.tensor([[[6.0, -4, -6], [6.0, -4, -6], [-4.0, -4, 6]]])
    masks = torch.tensor([[[[6.0, 6, -6, -6]] * 4, [[-6.0, -6, 6, 6]] * 4, [[-6.0] * 4] * 4]])
    return QueryPrediction(classes.requires_grad_(gradients), masks.requires_grad_(gradients))


@pytest.mark.parametrize("num_points", [None, 4])
@pytest.mark.parametrize("mask_dtype", [torch.float32, torch.bool])
def test_two_instances_of_same_class_require_distinct_queries(num_points, mask_dtype):
    criterion = ObjectQueryLoss(2, num_points=num_points)
    target = _target()
    target.masks = target.masks.to(mask_dtype)
    prediction = _prediction(gradients=True)
    exact = criterion(QueryOutput(prediction), [target])

    # A single semantic union and a duplicate left instance do not explain the
    # right instance: each object must be matched exactly once.
    changed_masks = prediction.mask_logits.detach().clone()
    changed_masks[:, 0] = 6
    changed_masks[:, 1] = prediction.mask_logits.detach()[:, 0]
    merged = criterion(
        QueryOutput(QueryPrediction(prediction.class_logits, changed_masks)), [target]
    )
    assert exact.item() < 0.05
    assert merged.item() > exact.item() + 2

    exact.backward()
    assert prediction.class_logits.grad is not None
    assert prediction.mask_logits.grad is not None
    for index in (0, 1):
        assert prediction.class_logits.grad[0, index, 0] < 0
        assert torch.count_nonzero(prediction.mask_logits.grad[0, index]) == 16
    assert prediction.class_logits.grad[0, 2, 2] < 0  # extra query learns no-object
    assert torch.count_nonzero(prediction.mask_logits.grad[0, 2]) == 0


def test_permuting_objects_and_queries_preserves_loss():
    prediction = _prediction()
    target = _target()
    reordered = ObjectTarget(
        class_ids=target.class_ids.flip(0),
        masks=target.masks.flip(0),
        valid=target.valid,
        iscrowd=target.iscrowd.flip(0),
        image_id=target.image_id,
        original_size=target.original_size,
    )
    swapped = QueryPrediction(
        prediction.class_logits[:, [2, 1, 0]], prediction.mask_logits[:, [2, 1, 0]]
    )
    criterion = ObjectQueryLoss(2)
    assert criterion(QueryOutput(prediction), [target]).item() == pytest.approx(
        criterion(QueryOutput(swapped), [reordered]).item(), abs=1e-7
    )


def test_sampled_matcher_keeps_positive_anchors_for_tiny_same_class_instances():
    masks = torch.zeros(2, 8, 8)
    masks[0, 0, 5] = 1
    masks[1, 1, 1] = 1
    target = ObjectTarget(
        class_ids=torch.zeros(2, dtype=torch.long),
        masks=masks,
        valid=torch.ones(8, 8, dtype=torch.bool),
        iscrowd=torch.zeros(2, dtype=torch.bool),
        image_id=1,
        original_size=(8, 8),
    )
    # Neither object intersects the single uniform point at flattened index 32.
    # Positive anchors must still identify the swapped instance order.
    prediction = QueryPrediction(torch.zeros(1, 2, 2), (masks.flip(0) * 12 - 6).unsqueeze(0))
    criterion = ObjectQueryLoss(1, num_points=1)
    prepared = criterion._prepare_target(target, torch.device("cpu"))
    queries, objects = criterion._match(
        prediction.class_logits[0], prediction.mask_logits[0], prepared
    )
    assert queries.tolist() == [0, 1]
    assert objects.tolist() == [1, 0]


def test_void_and_crowd_pixels_do_not_affect_mask_loss_or_gradients():
    valid = torch.ones(4, 4, dtype=torch.bool)
    valid[0] = False
    # The right object is crowd. Both its mask and the first image row must
    # remain unlabelled even when constructing targets outside the data reader.
    target = _target(valid=valid, crowd=torch.tensor([False, True]))
    prediction = _prediction(gradients=True)
    criterion = ObjectQueryLoss(2, num_points=None)
    original = criterion(QueryOutput(prediction), [target])
    changed = prediction.mask_logits.detach().clone()
    changed[:, :, 0] = 50
    changed[:, :, :, 2:] = -50
    modified = criterion(QueryOutput(QueryPrediction(prediction.class_logits, changed)), [target])
    assert modified.item() == pytest.approx(original.item(), abs=1e-7)
    original.backward()
    gradient = prediction.mask_logits.grad
    assert gradient is not None
    assert torch.count_nonzero(gradient[:, :, 0]) == 0
    assert torch.count_nonzero(gradient[:, :, :, 2:]) == 0
    assert torch.count_nonzero(gradient[:, :, 1:, :2]) > 0
    assert torch.equal(target.valid, valid)  # criterion never edits the annotation


def test_fully_void_and_fully_crowd_images_are_graph_connected_zero():
    for target in (
        _target(valid=torch.zeros(4, 4, dtype=torch.bool)),
        _target(crowd=torch.tensor([True, True])),
    ):
        primary = _prediction(gradients=True)
        auxiliary = _prediction(gradients=True)
        loss = ObjectQueryLoss(2)(QueryOutput(primary, (auxiliary,)), [target])
        assert loss.item() == 0
        loss.backward()
        for tensor in (
            primary.class_logits,
            primary.mask_logits,
            auxiliary.class_logits,
            auxiliary.mask_logits,
        ):
            assert tensor.grad is not None
            assert torch.isfinite(tensor.grad).all()
            assert torch.count_nonzero(tensor.grad) == 0


def test_valid_background_teaches_no_object_but_does_not_supervise_masks():
    prediction = _prediction(gradients=True)
    criterion = ObjectQueryLoss(2)
    loss = criterion(QueryOutput(prediction), [_target(empty=True)])
    loss.backward()
    assert loss.item() > 0
    assert prediction.class_logits.grad is not None
    assert (prediction.class_logits.grad[..., -1] < 0).all()
    assert prediction.mask_logits.grad is not None
    assert torch.count_nonzero(prediction.mask_logits.grad) == 0
    background_logits = prediction.class_logits.detach().clone()
    background_logits[..., -1] = 20
    better = criterion(
        QueryOutput(QueryPrediction(background_logits, prediction.mask_logits)),
        [_target(empty=True)],
    )
    assert better.item() < loss.item()


def test_auxiliary_supervision_is_additive_with_independent_gradients():
    primary = _prediction(gradients=True)
    auxiliary = QueryPrediction(
        torch.zeros_like(primary.class_logits, requires_grad=True),
        torch.zeros_like(primary.mask_logits, requires_grad=True),
    )
    criterion = ObjectQueryLoss(2, auxiliary_weight=0.4)
    target = [_target()]
    expected = criterion(QueryOutput(primary), target) + 0.4 * criterion(
        QueryOutput(auxiliary), target
    )
    actual = criterion(QueryOutput(primary, (auxiliary,)), target)
    assert actual.item() == pytest.approx(expected.item())
    actual.backward()
    for tensor in (
        primary.class_logits,
        primary.mask_logits,
        auxiliary.class_logits,
        auxiliary.mask_logits,
    ):
        assert tensor.grad is not None
        assert torch.isfinite(tensor.grad).all()
        assert torch.count_nonzero(tensor.grad) > 0


def test_void_batch_items_do_not_dilute_supervised_loss():
    prediction = _prediction()
    batch = QueryPrediction(
        prediction.class_logits.repeat(2, 1, 1), prediction.mask_logits.repeat(2, 1, 1, 1)
    )
    criterion = ObjectQueryLoss(2)
    single = criterion(QueryOutput(prediction), [_target()])
    mixed = criterion(
        QueryOutput(batch), [_target(), _target(valid=torch.zeros(4, 4, dtype=torch.bool))]
    )
    assert mixed.item() == pytest.approx(single.item())


def test_capacity_counts_instances_not_unique_classes_and_excludes_crowds():
    prediction = _prediction()
    one_query = QueryOutput(
        QueryPrediction(prediction.class_logits[:, :1], prediction.mask_logits[:, :1])
    )
    criterion = ObjectQueryLoss(2)
    with pytest.raises(ValueError, match="2 non-crowd segments but only 1 queries"):
        criterion(one_query, [_target()])
    assert torch.isfinite(criterion(one_query, [_target(crowd=torch.tensor([False, True]))]))


def test_single_foreground_class_and_lower_resolution_masks_are_supported():
    classes = torch.zeros(1, 3, 2, requires_grad=True)
    masks = torch.zeros(1, 3, 2, 2, requires_grad=True)
    loss = ObjectQueryLoss(1)(QueryOutput(QueryPrediction(classes, masks)), [_target()])
    loss.backward()
    assert torch.isfinite(loss)
    assert classes.grad is not None and torch.count_nonzero(classes.grad) > 0
    assert masks.grad is not None and torch.count_nonzero(masks.grad) > 0


def test_nonfinite_auxiliary_predictions_are_rejected_even_for_void_crop():
    prediction = _prediction()
    bad_classes = prediction.class_logits.clone()
    bad_classes[0, 0, 0] = float("nan")
    auxiliary = QueryPrediction(bad_classes, prediction.mask_logits)
    with pytest.raises(FloatingPointError, match="non-finite"):
        ObjectQueryLoss(2, auxiliary_weight=0)(
            QueryOutput(prediction, (auxiliary,)),
            [_target(valid=torch.zeros(4, 4, dtype=torch.bool))],
        )


def test_invalid_class_and_batch_contracts_are_rejected():
    prediction = _prediction()
    with pytest.raises(ValueError, match="class columns"):
        ObjectQueryLoss(3)(QueryOutput(prediction), [_target()])
    with pytest.raises(ValueError, match="batch size"):
        ObjectQueryLoss(2)(QueryOutput(prediction), [])
    target = _target()
    target.class_ids[0] = 2
    with pytest.raises(ValueError, match="class IDs"):
        ObjectQueryLoss(2)(QueryOutput(prediction), [target])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_classes": 0},
        {"num_classes": True},
        {"class_weight": float("nan")},
        {"mask_weight": -1},
        {"dice_weight": float("inf")},
        {"no_object_weight": 0},
        {"num_points": 0},
        {"num_points": 1.5},
        {"auxiliary_weight": -1},
        {"class_weight": 0, "mask_weight": 0, "dice_weight": 0},
    ],
)
def test_invalid_loss_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        ObjectQueryLoss(**({"num_classes": 2} | kwargs))
