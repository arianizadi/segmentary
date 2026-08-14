"""Scientific contracts for Segmentary's native query/mask objective."""

from __future__ import annotations

import pytest
import torch
from torch import Tensor, nn

from segmentary.config import (
    ConfigError,
    CrossEntropyTerm,
    EvalConfig,
    LossSpec,
    OptimConfig,
    QueryLossSpec,
    TrainConfig,
    from_dict,
)
from segmentary.engine import query_loss as query_loss_module
from segmentary.engine.losses import LossConfig, SegmentationLoss
from segmentary.engine.module import SegLitModule, dense_training_objective
from segmentary.engine.query_loss import (
    QuerySegmentationLoss,
    SemanticMaskTarget,
    hungarian_match,
    query_training_objective,
    semantic_targets_from_dense,
)
from segmentary.models.mask_classification import MaskClassWrapper
from segmentary.models.outputs import QueryOutput, QueryPrediction, SegmentationOutput
from segmentary.taxonomy import CanonicalClass, LabelSpace


def _semantic_case(*, requires_grad: bool = False) -> tuple[QueryPrediction, Tensor]:
    target = torch.tensor([[[0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 1, 1]]])
    class_logits = torch.tensor(
        [[[8.0, -4.0, -6.0], [-4.0, 8.0, -6.0], [-4.0, -4.0, 8.0]]],
        requires_grad=requires_grad,
    )
    mask_logits = torch.tensor(
        [
            [
                [[8.0, 8.0, -8.0, -8.0]] * 4,
                [[-8.0, -8.0, 8.0, 8.0]] * 4,
                [[-8.0, -8.0, -8.0, -8.0]] * 4,
            ]
        ],
        requires_grad=requires_grad,
    )
    return QueryPrediction(class_logits, mask_logits), target


def _loss(spec: QueryLossSpec | None = None, *, classes: int = 2) -> QuerySegmentationLoss:
    return QuerySegmentationLoss(spec or QueryLossSpec(), classes, ignore_index=255)


@pytest.mark.parametrize("points", [None, 4])
def test_known_hungarian_assignment_is_exact_for_full_and_point_costs(points):
    prediction, target = _semantic_case()
    spec = QueryLossSpec(matching_num_points=points)
    targets = semantic_targets_from_dense(target, num_classes=2, ignore_index=255)

    assignments = hungarian_match(prediction, targets, None, spec, num_classes=2)

    assert assignments[0][0].tolist() == [0, 1]
    assert assignments[0][1].tolist() == [0, 1]


def test_matcher_accepts_an_explicit_empty_object_set():
    prediction, _ = _semantic_case()
    target = SemanticMaskTarget(
        class_ids=torch.empty(0, dtype=torch.long),
        masks=torch.empty(0, 4, 4),
        valid=torch.ones(4, 4, dtype=torch.bool),
    )

    assignments = hungarian_match(prediction, (target,), None, QueryLossSpec(), num_classes=2)

    assert assignments[0][0].numel() == 0
    assert assignments[0][1].numel() == 0


def test_direct_match_targets_reject_out_of_range_and_inactive_classes():
    prediction, _ = _semantic_case()
    out_of_range = SemanticMaskTarget(
        class_ids=torch.tensor([2]),
        masks=torch.ones(1, 4, 4),
        valid=torch.ones(4, 4, dtype=torch.bool),
    )
    with pytest.raises(ValueError, match="outside"):
        hungarian_match(prediction, (out_of_range,), None, QueryLossSpec(), num_classes=2)

    inactive = SemanticMaskTarget(
        class_ids=torch.tensor([1]),
        masks=torch.ones(1, 4, 4),
        valid=torch.ones(4, 4, dtype=torch.bool),
    )
    with pytest.raises(ValueError, match="inactive"):
        hungarian_match(
            prediction,
            (inactive,),
            torch.tensor([True, False]),
            QueryLossSpec(),
            num_classes=2,
        )


def test_all_ignore_crop_is_graph_connected_zero_for_primary_and_auxiliary():
    primary, _ = _semantic_case(requires_grad=True)
    aux_class = primary.class_logits.detach().clone().requires_grad_()
    aux_mask = primary.mask_logits.detach().clone().requires_grad_()
    output = QueryOutput(primary, (QueryPrediction(aux_class, aux_mask),))
    target = torch.full((1, 4, 4), 255)

    loss, parts = _loss()(output, target)
    loss.backward()

    assert loss.item() == 0.0
    assert parts["empty_crop"].item() == 1.0
    for tensor in (primary.class_logits, primary.mask_logits, aux_class, aux_mask):
        assert tensor.grad is not None
        assert torch.count_nonzero(tensor.grad) == 0


def test_ignored_pixels_cannot_change_assignment_or_loss():
    prediction, target = _semantic_case()
    target[:, :, 1:3] = 255
    changed_masks = prediction.mask_logits.detach().clone()
    changed_masks[:, :, :, 1:3] = torch.tensor([[[[1000.0, -1000.0]]]])
    changed = QueryPrediction(prediction.class_logits.clone(), changed_masks)

    first, _ = _loss()(QueryOutput(prediction), target)
    second, _ = _loss()(QueryOutput(changed), target)

    torch.testing.assert_close(first, second)


def test_inactive_class_logits_are_removed_from_matching_and_classification():
    prediction, target = _semantic_case()
    class_logits = torch.cat(
        (prediction.class_logits[..., :2], torch.zeros(1, 3, 1), prediction.class_logits[..., 2:]),
        dim=-1,
    )
    changed = class_logits.clone()
    changed[..., 2] = 10000.0
    active = torch.tensor([[True, True, False]])
    output = QueryOutput(QueryPrediction(class_logits, prediction.mask_logits))
    changed_output = QueryOutput(QueryPrediction(changed, prediction.mask_logits))

    baseline, _ = _loss(classes=3)(output, target, active=active)
    perturbed, _ = _loss(classes=3)(changed_output, target, active=active)

    torch.testing.assert_close(baseline, perturbed)


def test_query_loss_backpropagates_to_class_and_mask_logits_in_float32():
    prediction, target = _semantic_case(requires_grad=True)

    with torch.autocast("cpu", dtype=torch.bfloat16):
        loss, parts = _loss()(QueryOutput(prediction), target)
    loss.backward()

    assert loss.dtype == torch.float32
    assert set(parts) == {"classification", "mask_bce", "dice", "total"}
    assert prediction.class_logits.grad is not None
    assert prediction.mask_logits.grad is not None
    assert bool(prediction.class_logits.grad.abs().sum() > 0)
    assert bool(prediction.mask_logits.grad.abs().sum() > 0)


def test_selecting_matched_queries_before_resize_is_value_and_gradient_exact():
    torch.manual_seed(8)
    logits = torch.randn(5, 3, 4, dtype=torch.float64, requires_grad=True)
    matched = torch.tensor([0, 3], dtype=torch.long)
    coefficients = torch.randn(2, 7, 9, dtype=torch.float64)

    resize = query_loss_module._resize_masks
    old = resize(logits, (7, 9))[matched]
    new = resize(logits[matched], (7, 9))
    torch.testing.assert_close(new, old, rtol=0.0, atol=0.0)

    old_gradient = torch.autograd.grad((old * coefficients).sum(), logits, retain_graph=True)[0]
    new_gradient = torch.autograd.grad((new * coefficients).sum(), logits)[0]
    torch.testing.assert_close(new_gradient, old_gradient, rtol=0.0, atol=0.0)


def test_auxiliary_decoder_layers_are_reassigned_and_weighted_independently():
    primary, target = _semantic_case()
    auxiliary = QueryPrediction(
        primary.class_logits.roll(1, dims=1).clone().requires_grad_(),
        primary.mask_logits.roll(1, dims=1).clone().requires_grad_(),
    )
    spec = QueryLossSpec(auxiliary_layer_weight=0.4)
    loss_fn = _loss(spec)

    primary_loss, _ = loss_fn(QueryOutput(primary), target)
    auxiliary_loss, _ = loss_fn(QueryOutput(auxiliary), target)
    combined, parts = loss_fn(QueryOutput(primary, (auxiliary,)), target)

    torch.testing.assert_close(combined, primary_loss + 0.4 * auxiliary_loss)
    assert "aux/0/classification" in parts
    assert "aux/0/mask_bce" in parts
    assert "aux/0/dice" in parts
    assert "aux/0/weighted_loss" in parts


def test_all_ignore_sample_does_not_dilute_or_supervise_a_valid_batch_item():
    prediction, target = _semantic_case()
    class_logits = prediction.class_logits.repeat(2, 1, 1).detach().requires_grad_()
    mask_logits = prediction.mask_logits.repeat(2, 1, 1, 1).detach().requires_grad_()
    mixed_target = torch.cat((target, torch.full_like(target, 255)), dim=0)

    mixed, _ = _loss()(QueryOutput(QueryPrediction(class_logits, mask_logits)), mixed_target)
    single, _ = _loss()(QueryOutput(prediction), target)
    mixed.backward()

    torch.testing.assert_close(mixed, single)
    assert torch.count_nonzero(class_logits.grad[1]) == 0
    assert torch.count_nonzero(mask_logits.grad[1]) == 0


@pytest.mark.parametrize(
    "raw, message",
    [
        (
            {
                "query": {
                    "classification_weight": 0.0,
                }
            },
            "classification_weight must be positive",
        ),
        (
            {"query": {"mask_bce_weight": 0.0, "dice_weight": 0.0}},
            "at least one positive mask loss",
        ),
        ({"query": {"matching_num_points": 0}}, "positive integer"),
        ({"query": {"matching_num_points": True}}, "expected int"),
        ({"task": "binary", "query": {}}, "requires task: multiclass"),
        (
            {"terms": [{"kind": "cross_entropy"}], "query": {}},
            "cannot be combined",
        ),
        ({"query": {"unknown": 1}}, "unknown key"),
    ],
)
def test_query_config_rejects_ambiguous_or_invalid_settings(raw, message):
    with pytest.raises(ConfigError, match=message):
        from_dict(LossSpec, raw)


def test_query_config_parses_typed_nested_spec_and_dense_legacy_stays_unchanged():
    spec = from_dict(
        LossSpec,
        {
            "query": {
                "kind": "hungarian_query",
                "matching_num_points": 37,
                "auxiliary_layer_weight": 0.25,
            }
        },
    )
    assert isinstance(spec.query, QueryLossSpec)
    assert spec.query.matching_num_points == 37
    assert spec.query.auxiliary_layer_weight == pytest.approx(0.25)

    dense = LossSpec()
    assert dense.query is None
    assert [term.kind for term in dense.resolved_terms()] == ["cross_entropy"]
    dense_loss = SegmentationLoss(LossConfig.from_spec(dense), 2)
    value, _ = dense_loss(torch.randn(1, 2, 3, 4), torch.zeros(1, 3, 4, dtype=torch.long))
    assert torch.isfinite(value)


def test_query_loss_rejects_bad_targets_inactive_labels_and_too_few_queries():
    prediction, target = _semantic_case()
    with pytest.raises(ValueError, match="integer class-index"):
        _loss()(QueryOutput(prediction), target.float())
    with pytest.raises(ValueError, match="marked inactive"):
        _loss()(QueryOutput(prediction), target, active=torch.tensor([True, False]))

    one_query = QueryPrediction(prediction.class_logits[:, :1], prediction.mask_logits[:, :1])
    with pytest.raises(ValueError, match="only 1 queries"):
        _loss()(QueryOutput(one_query), target)


def test_dense_and_query_objective_mismatches_fail_loudly():
    class DenseModel(nn.Module):
        def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
            return SegmentationOutput(dense_logits=torch.randn(pixel_values.shape[0], 2, 4, 4))

    with pytest.raises(ValueError, match="returned dense predictions"):
        query_training_objective(
            DenseModel(),
            _loss(),
            torch.randn(1, 3, 4, 4),
            torch.zeros(1, 4, 4, dtype=torch.long),
        )


class _RawMaskModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder = nn.Conv2d(3, 4, 1)
        self.class_predictor = nn.Linear(4, 3)
        self.mask_predictor = nn.Conv2d(4, 2, 1)

    def forward(self, pixel_values: Tensor):
        features = self.encoder(pixel_values)
        classes = self.class_predictor(features.mean((2, 3))).unsqueeze(1).expand(-1, 2, -1)
        masks = self.mask_predictor(features)
        auxiliary = [
            {
                "class_queries_logits": classes + 0.1,
                "masks_queries_logits": masks - 0.1,
            }
        ]
        return type(
            "RawOutput",
            (),
            {
                "class_queries_logits": classes,
                "masks_queries_logits": masks,
                "auxiliary_logits": auxiliary,
            },
        )()


def test_mask_class_wrapper_preserves_raw_queries_but_public_forward_remains_dense():
    wrapper = MaskClassWrapper(
        _RawMaskModel(),
        2,
        backbone_paths=("encoder",),
        head_paths=("class_predictor", "mask_predictor"),
    )
    image = torch.randn(1, 3, 5, 7)

    rich = wrapper.forward_output(image)
    dense = wrapper(image)

    assert rich.query is not None
    assert rich.query.primary.class_logits.shape == (1, 2, 3)
    assert rich.query.primary.mask_logits.shape == (1, 2, 5, 7)
    assert len(rich.query.auxiliary) == 1
    assert dense.shape == (1, 2, 5, 7)


def test_wrapper_requests_auxiliary_layers_only_on_the_training_output_path():
    class AuxFlagModel(_RawMaskModel):
        def __init__(self) -> None:
            super().__init__()
            self.flags: list[bool] = []

        def forward(self, pixel_values: Tensor, output_auxiliary_logits: bool = False):
            self.flags.append(output_auxiliary_logits)
            output = super().forward(pixel_values)
            if not output_auxiliary_logits:
                output.auxiliary_logits = None
            return output

    raw = AuxFlagModel()
    wrapper = MaskClassWrapper(
        raw,
        2,
        backbone_paths=("encoder",),
        head_paths=("class_predictor", "mask_predictor"),
        request_auxiliary_logits=True,
    )
    image = torch.randn(1, 3, 4, 4)

    rich = wrapper.forward_output(image)
    dense = wrapper(image)

    assert raw.flags == [True, False]
    assert rich.query is not None and len(rich.query.auxiliary) == 1
    assert dense.shape == (1, 2, 4, 4)


def test_query_training_objective_uses_one_rich_forward_and_updates_both_predictors():
    model = MaskClassWrapper(
        _RawMaskModel(),
        2,
        backbone_paths=("encoder",),
        head_paths=("class_predictor", "mask_predictor"),
    )
    target = torch.tensor([[[0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 1, 1]]])

    loss, _ = query_training_objective(model, _loss(), torch.randn(1, 3, 4, 4), target)
    loss.backward()

    assert model.model.class_predictor.weight.grad is not None
    assert model.model.mask_predictor.weight.grad is not None
    assert bool(model.model.class_predictor.weight.grad.abs().sum() > 0)
    assert bool(model.model.mask_predictor.weight.grad.abs().sum() > 0)


def test_explicit_legacy_dense_ablation_uses_public_collapsed_forward():
    model = MaskClassWrapper(
        _RawMaskModel(),
        2,
        backbone_paths=("encoder",),
        head_paths=("class_predictor", "mask_predictor"),
    )
    target = torch.tensor([[[0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 1, 1]]])
    dense_loss = SegmentationLoss(LossConfig(), 2, ignore_index=255)

    loss, parts = dense_training_objective(model, dense_loss, torch.randn(1, 3, 4, 4), target)
    loss.backward()

    assert torch.isfinite(loss)
    assert set(parts) >= {"cross_entropy", "total"}
    assert model.model.class_predictor.weight.grad is not None
    assert model.model.mask_predictor.weight.grad is not None


def test_lightning_training_step_dispatches_to_query_objective(monkeypatch):
    model = MaskClassWrapper(
        _RawMaskModel(),
        2,
        backbone_paths=("encoder",),
        head_paths=("class_predictor", "mask_predictor"),
    )
    space = LabelSpace(
        name="query-test",
        description="query objective test",
        ignore_index=255,
        classes=(
            CanonicalClass(0, "left", (0, 0, 0)),
            CanonicalClass(1, "right", (255, 255, 255)),
        ),
        thin_classes=(),
    )
    lit = SegLitModule(
        model=model,
        loss_fn=_loss(),
        space=space,
        optim_cfg=OptimConfig(),
        train_cfg=TrainConfig(ema_decay=None),
        eval_cfg=EvalConfig(sliding_window=False),
    )
    logged: dict[str, Tensor | float] = {}
    monkeypatch.setattr(lit, "log", lambda name, value, **kwargs: logged.__setitem__(name, value))
    monkeypatch.setattr(lit, "_current_lr", lambda: 1e-3)
    target = torch.tensor([[[0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 1, 1]]])

    loss = lit.training_step({"image": torch.randn(1, 3, 4, 4), "mask": target}, 0)
    loss.backward()

    assert "train/classification" in logged
    assert "train/mask_bce" in logged
    assert "train/dice" in logged
    assert model.model.class_predictor.weight.grad is not None
    assert model.model.mask_predictor.weight.grad is not None


def test_lightning_module_rejects_query_loss_for_dense_model_at_construction():
    space = LabelSpace(
        name="query-test",
        description="query objective test",
        ignore_index=255,
        classes=(
            CanonicalClass(0, "left", (0, 0, 0)),
            CanonicalClass(1, "right", (255, 255, 255)),
        ),
        thin_classes=(),
    )

    with pytest.raises(ValueError, match=r"dense model.*Hungarian query objective"):
        SegLitModule(
            model=nn.Conv2d(3, 2, 1),
            loss_fn=_loss(),
            space=space,
            optim_cfg=OptimConfig(),
            train_cfg=TrainConfig(ema_decay=None),
            eval_cfg=EvalConfig(sliding_window=False),
        )


def test_loss_spec_cannot_construct_dense_terms_when_query_is_selected():
    spec = LossSpec(query=QueryLossSpec())
    with pytest.raises(ConfigError, match="has no dense loss terms"):
        spec.resolved_terms()


def test_direct_loss_spec_rejects_nondefault_legacy_dense_field_with_query():
    with pytest.raises(ConfigError, match="cannot be combined"):
        LossSpec(query=QueryLossSpec(), ce_weight=0.5)


def test_direct_dense_term_remains_constructible_for_external_callers():
    spec = LossSpec(terms=[CrossEntropyTerm(kind="cross_entropy")])
    assert spec.query is None
