"""Exact numerical and defensive contracts for the native query objective."""

from __future__ import annotations

import math

import pytest
import torch
from torch import Tensor, nn

from segmentary.config import QueryLossSpec
from segmentary.engine.query_loss import (
    QuerySegmentationLoss,
    SemanticMaskTarget,
    _deterministic_points,
    _pairwise_mask_costs,
    hungarian_match,
    query_training_objective,
    semantic_targets_from_dense,
)
from segmentary.models.outputs import QueryOutput, QueryPrediction

IGNORE = 255


def _prediction(
    *,
    batch: int = 1,
    queries: int = 2,
    columns: int = 3,
    dtype: torch.dtype = torch.float32,
    requires_grad: bool = False,
) -> QueryPrediction:
    return QueryPrediction(
        torch.zeros((batch, queries, columns), dtype=dtype, requires_grad=requires_grad),
        torch.zeros((batch, queries, 1, 1), dtype=dtype, requires_grad=requires_grad),
    )


def _loss(spec: QueryLossSpec | None = None) -> QuerySegmentationLoss:
    return QuerySegmentationLoss(spec or QueryLossSpec(), num_classes=2, ignore_index=IGNORE)


def test_semantic_dense_conversion_is_sorted_exact_and_preserves_void_only_samples() -> None:
    target = torch.tensor(
        [
            [[2, IGNORE, 0], [2, 0, IGNORE]],
            [[IGNORE, IGNORE, IGNORE], [IGNORE, IGNORE, IGNORE]],
        ]
    )
    active = torch.tensor([[True, False, True], [False, True, False]])

    converted = semantic_targets_from_dense(
        target, num_classes=3, ignore_index=IGNORE, active=active
    )

    assert converted[0].class_ids.tolist() == [0, 2]
    assert torch.equal(
        converted[0].valid,
        torch.tensor([[True, False, True], [True, True, False]]),
    )
    assert torch.equal(
        converted[0].masks,
        torch.tensor(
            [
                [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0]],
                [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            ]
        ),
    )
    assert converted[1].class_ids.numel() == 0
    assert converted[1].masks.shape == (0, 2, 3)
    assert not bool(converted[1].valid.any())


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"class_ids": torch.tensor([[0]])}, "one-dimensional"),
        ({"masks": torch.zeros((2, 1, 1))}, r"shape \(M,H,W\)"),
        ({"valid": torch.ones((1, 2), dtype=torch.bool)}, "spatial size"),
        ({"class_ids": torch.tensor([0], dtype=torch.int32)}, "torch.long"),
        ({"valid": torch.ones((1, 1), dtype=torch.uint8)}, "torch.bool"),
        ({"masks": torch.zeros((1, 1, 1), dtype=torch.long)}, "floating dtype"),
        ({"class_ids": torch.tensor([-1])}, "cannot be negative"),
        ({"class_ids": torch.tensor([0, 0]), "masks": torch.zeros((2, 1, 1))}, "unique"),
        ({"masks": torch.full((1, 1, 1), float("nan"))}, "finite 0/1"),
        ({"masks": torch.full((1, 1, 1), 0.5)}, "finite 0/1"),
    ],
)
def test_semantic_mask_target_rejects_ambiguous_or_invalid_tensors(
    replacement: dict[str, Tensor], message: str
) -> None:
    values = {
        "class_ids": torch.tensor([0]),
        "masks": torch.ones((1, 1, 1)),
        "valid": torch.ones((1, 1), dtype=torch.bool),
    }
    values.update(replacement)

    with pytest.raises(ValueError, match=message):
        SemanticMaskTarget(**values)


def test_semantic_mask_target_requires_one_shared_device() -> None:
    with pytest.raises(ValueError, match="share one device"):
        SemanticMaskTarget(
            class_ids=torch.tensor([0]),
            masks=torch.ones((1, 1, 1), device="meta"),
            valid=torch.ones((1, 1), dtype=torch.bool, device="meta"),
        )


@pytest.mark.parametrize(
    ("target", "error", "message"),
    [
        ([[[0]]], TypeError, "must be a Tensor"),
        (torch.tensor([[0]]), ValueError, r"shape \(N,H,W\)"),
        (torch.empty((0, 1, 1), dtype=torch.long), ValueError, "cannot have an empty"),
        (torch.empty((1, 0, 1), dtype=torch.long), ValueError, "cannot have an empty"),
        (torch.tensor([[[True]]]), ValueError, "integer class-index"),
        (torch.tensor([[[0.0]]]), ValueError, "integer class-index"),
        (torch.tensor([[[-1]]]), ValueError, "must be in"),
        (torch.tensor([[[2]]]), ValueError, "must be in"),
    ],
)
def test_semantic_dense_target_input_shape_dtype_and_range_fail_closed(
    target: object, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        semantic_targets_from_dense(target, num_classes=2, ignore_index=IGNORE)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("active", "error", "message"),
    [
        ([True, True], TypeError, "must be a Tensor"),
        (torch.tensor([True]), ValueError, "does not match 2 classes"),
        (torch.ones((2, 2), dtype=torch.bool), ValueError, "does not match batch"),
        (torch.ones((1, 2, 1), dtype=torch.bool), ValueError, "must be 1-D.*or 2-D"),
        (torch.tensor([False, False]), ValueError, "excludes every"),
    ],
)
def test_query_active_mask_shape_type_and_nonempty_contracts(
    active: object, error: type[Exception], message: str
) -> None:
    output = QueryOutput(_prediction())
    target = torch.full((1, 1, 1), IGNORE)

    with pytest.raises(error, match=message):
        _loss()(output, target, active=active)  # type: ignore[arg-type]


def test_deterministic_matching_points_cover_endpoints_and_middle_exactly() -> None:
    valid = torch.tensor([[True, False, True, True, False, True, False, True]])

    assert _deterministic_points(valid, None).tolist() == [0, 2, 3, 5, 7]
    assert _deterministic_points(valid, 1).tolist() == [3]
    assert _deterministic_points(valid, 3).tolist() == [0, 3, 7]


def test_pairwise_bce_and_dice_cost_matrices_match_hand_computed_values() -> None:
    prediction = torch.tensor([[math.log(3), -math.log(3)], [-math.log(3), math.log(3)]]).view(
        2, 1, 2
    )
    target = torch.tensor([[1.0, 0.0], [0.0, 1.0]]).view(2, 1, 2)

    bce, dice = _pairwise_mask_costs(
        prediction,
        target,
        torch.ones((1, 2), dtype=torch.bool),
        num_points=None,
        dice_smooth=1.0,
    )

    expected_bce = torch.tensor(
        [[-math.log(0.75), -math.log(0.25)], [-math.log(0.25), -math.log(0.75)]]
    )
    expected_dice = torch.tensor([[1 / 6, 1 / 2], [1 / 2, 1 / 6]])
    torch.testing.assert_close(bce, expected_bce, atol=1e-7, rtol=0)
    torch.testing.assert_close(dice, expected_dice, atol=1e-7, rtol=0)


def test_matcher_rejects_nonempty_targets_without_any_supervised_pixel() -> None:
    target = SemanticMaskTarget(
        class_ids=torch.tensor([0]),
        masks=torch.zeros((1, 1, 1)),
        valid=torch.zeros((1, 1), dtype=torch.bool),
    )

    with pytest.raises(ValueError, match="no supervised pixels"):
        hungarian_match(_prediction(), (target,), None, QueryLossSpec(), num_classes=2)


def test_one_pixel_query_loss_matches_class_bce_dice_and_weighted_total_oracle() -> None:
    class_logits = torch.log(
        torch.tensor([[[0.5, 0.25, 0.25], [0.25, 0.5, 0.25]]], dtype=torch.float64)
    )
    mask_logits = torch.zeros((1, 2, 1, 1), dtype=torch.float64)
    prediction = QueryPrediction(class_logits, mask_logits)
    spec = QueryLossSpec(
        classification_weight=2.0,
        mask_bce_weight=3.0,
        dice_weight=5.0,
        no_object_coefficient=0.5,
        match_class_cost=1.0,
        match_mask_bce_cost=0.0,
        match_dice_cost=0.0,
    )

    loss, parts = _loss(spec)(QueryOutput(prediction), torch.zeros((1, 1, 1), dtype=torch.long))

    assert parts["classification"].item() == pytest.approx(4 / 3 * math.log(2), abs=1e-6)
    assert parts["mask_bce"].item() == pytest.approx(math.log(2), abs=1e-6)
    assert parts["dice"].item() == pytest.approx(1 / 5, abs=1e-6)
    assert loss.item() == pytest.approx(1 + 17 / 3 * math.log(2), abs=1e-6)


@pytest.mark.parametrize("dtype", [torch.float16, torch.bfloat16, torch.float32, torch.float64])
def test_query_floating_dtypes_are_differentiable_and_compute_in_float32(
    dtype: torch.dtype,
) -> None:
    prediction = _prediction(dtype=dtype, requires_grad=True)

    loss, _ = _loss()(QueryOutput(prediction), torch.zeros((1, 1, 1), dtype=torch.long))
    loss.backward()

    assert loss.dtype == torch.float32
    assert prediction.class_logits.grad is not None
    assert prediction.mask_logits.grad is not None
    assert bool(torch.isfinite(prediction.class_logits.grad).all())
    assert bool(torch.isfinite(prediction.mask_logits.grad).all())


@pytest.mark.parametrize("field", ["class_logits", "mask_logits"])
def test_query_rejects_nondifferentiable_integer_prediction_dtypes(field: str) -> None:
    class_logits = torch.zeros((1, 2, 3))
    mask_logits = torch.zeros((1, 2, 1, 1))
    if field == "class_logits":
        class_logits = class_logits.long()
    else:
        mask_logits = mask_logits.long()
    output = QueryOutput(QueryPrediction(class_logits, mask_logits))

    with pytest.raises(TypeError, match="must use floating dtypes"):
        _loss()(output, torch.full((1, 1, 1), IGNORE))


def test_query_rejects_class_and_mask_logits_on_different_devices() -> None:
    prediction = QueryPrediction(
        torch.zeros((1, 2, 3)),
        torch.zeros((1, 2, 1, 1), device="meta"),
    )

    with pytest.raises(ValueError, match="must share one device"):
        _loss()(QueryOutput(prediction), torch.full((1, 1, 1), IGNORE))


def test_query_rejects_auxiliary_layers_on_a_different_device() -> None:
    primary = _prediction()
    auxiliary = QueryPrediction(
        torch.zeros((1, 2, 3), device="meta"),
        torch.zeros((1, 2, 1, 1), device="meta"),
    )

    with pytest.raises(ValueError, match="query layer 1 is on meta; expected cpu"):
        _loss()(QueryOutput(primary, (auxiliary,)), torch.full((1, 1, 1), IGNORE))


def test_query_rejects_nonfinite_auxiliary_before_all_ignore_shortcut() -> None:
    primary = _prediction()
    auxiliary = _prediction()
    auxiliary.class_logits[0, 0, 0] = float("nan")

    with pytest.raises(FloatingPointError, match="query layer 1 contains non-finite"):
        _loss()(QueryOutput(primary, (auxiliary,)), torch.full((1, 1, 1), IGNORE))


@pytest.mark.parametrize("field", ["class_logits", "mask_logits"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_query_all_ignore_rejects_nonfinite_raw_predictions_before_zero_shortcut(
    field: str, bad: float
) -> None:
    class_logits = torch.zeros((1, 2, 3))
    mask_logits = torch.zeros((1, 2, 1, 1))
    tensor = class_logits if field == "class_logits" else mask_logits
    tensor.reshape(-1)[0] = bad
    output = QueryOutput(QueryPrediction(class_logits, mask_logits))

    with pytest.raises(FloatingPointError, match="non-finite class or mask logits"):
        _loss()(output, torch.full((1, 1, 1), IGNORE))


def test_query_all_ignore_extreme_finite_predictions_return_safe_graph_zero() -> None:
    limit = torch.finfo(torch.float32).max
    class_logits = torch.full((1, 2, 3), limit, requires_grad=True)
    mask_logits = torch.full((1, 2, 1, 1), limit, requires_grad=True)
    output = QueryOutput(QueryPrediction(class_logits, mask_logits))

    loss, parts = _loss()(output, torch.full((1, 1, 1), IGNORE))
    loss.backward()

    assert loss.item() == 0.0
    assert parts["empty_crop"].item() == 1.0
    for tensor in (class_logits, mask_logits):
        assert tensor.grad is not None
        assert bool(torch.isfinite(tensor.grad).all())
        assert torch.count_nonzero(tensor.grad) == 0


@pytest.mark.parametrize(
    ("output", "target", "error", "message"),
    [
        (_prediction(), torch.zeros((2, 1, 1), dtype=torch.long), ValueError, "batch size"),
        (
            _prediction(columns=4),
            torch.zeros((1, 1, 1), dtype=torch.long),
            ValueError,
            "expected 3 including no-object",
        ),
    ],
)
def test_query_prediction_and_target_shape_mismatches_fail_closed(
    output: QueryPrediction, target: Tensor, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        _loss()(QueryOutput(output), target)


def test_query_rejects_wrong_output_target_and_active_input_types() -> None:
    with pytest.raises(TypeError, match="requires QueryOutput"):
        _loss()(object(), torch.zeros((1, 1, 1), dtype=torch.long))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="query target must be a Tensor"):
        _loss()(QueryOutput(_prediction()), [[[0]]])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="active mask must be a Tensor"):
        _loss()(QueryOutput(_prediction()), torch.zeros((1, 1, 1), dtype=torch.long), [True, True])  # type: ignore[arg-type]


def test_query_rejects_target_and_active_masks_on_the_wrong_device() -> None:
    output = QueryOutput(_prediction())
    with pytest.raises(ValueError, match=r"query target is on meta.*predictions are on cpu"):
        _loss()(output, torch.zeros((1, 1, 1), dtype=torch.long, device="meta"))
    with pytest.raises(ValueError, match=r"active mask is on meta.*target is on cpu"):
        _loss()(
            output,
            torch.zeros((1, 1, 1), dtype=torch.long),
            active=torch.ones(2, dtype=torch.bool, device="meta"),
        )


def test_nonfinite_hungarian_cost_from_finite_inputs_fails_closed() -> None:
    target = semantic_targets_from_dense(
        torch.zeros((1, 1, 1), dtype=torch.long), num_classes=2, ignore_index=IGNORE
    )
    spec = QueryLossSpec(
        match_class_cost=1e39,
        match_mask_bce_cost=0.0,
        match_dice_cost=0.0,
    )

    with pytest.raises(FloatingPointError, match="matching cost contains non-finite"):
        hungarian_match(_prediction(), target, None, spec, num_classes=2)


def test_query_weighted_total_overflow_fails_closed() -> None:
    spec = QueryLossSpec(classification_weight=1e39)

    with pytest.raises(FloatingPointError, match="weighted query loss total"):
        _loss(spec)(QueryOutput(_prediction()), torch.zeros((1, 1, 1), dtype=torch.long))


def test_query_training_objective_rejects_missing_or_wrong_rich_forward_contract() -> None:
    class NoRichForward(nn.Module):
        pass

    class WrongRichForward(nn.Module):
        def forward_output(self, pixel_values: Tensor) -> Tensor:
            return pixel_values

    image = torch.zeros((1, 3, 1, 1))
    target = torch.zeros((1, 1, 1), dtype=torch.long)
    with pytest.raises(TypeError, match="has no forward_output"):
        query_training_objective(NoRichForward(), _loss(), image, target)
    with pytest.raises(TypeError, match="expected SegmentationOutput"):
        query_training_objective(WrongRichForward(), _loss(), image, target)
