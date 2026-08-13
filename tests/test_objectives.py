"""Numerical, gradient, masking, and config contracts for native objectives."""

from __future__ import annotations

import pytest
import torch
import torch.nn.functional as F

from segmentary.config import ConfigError, LossSpec, from_dict
from segmentary.engine.losses import LossConfig, SegmentationLoss

IGNORE = 255


def _multiclass(term: dict, *, c: int = 4):
    g = torch.Generator().manual_seed(17)
    logits = torch.randn(2, c, 7, 9, generator=g, dtype=torch.float64, requires_grad=True)
    target = torch.randint(0, c, (2, 7, 9), generator=g)
    target[:, :2, :3] = IGNORE
    spec = from_dict(LossSpec, {"terms": [term]})
    return logits, target, SegmentationLoss(LossConfig.from_spec(spec), c, IGNORE).double()


@pytest.mark.parametrize(
    "term",
    [
        {"kind": "cross_entropy"},
        {"kind": "dice"},
        {"kind": "jaccard"},
        {"kind": "lovasz"},
        {"kind": "focal"},
        {"kind": "tversky"},
        {"kind": "ohem_cross_entropy", "fraction": 0.5, "min_kept": 3},
        {"kind": "boundary", "width": 1},
        {"kind": "hausdorff", "max_distance": 3},
    ],
    ids=lambda term: term["kind"],
)
def test_multiclass_terms_are_finite_differentiable_and_ignore_exactly(term):
    logits, target, objective = _multiclass(term)
    loss, parts = objective(logits, target)
    assert torch.isfinite(loss)
    assert term["kind"] in parts
    loss.backward()
    ignored = (target == IGNORE).unsqueeze(1).expand_as(logits)
    assert torch.count_nonzero(logits.grad[ignored]) == 0
    assert torch.count_nonzero(logits.grad[~ignored]) > 0


@pytest.mark.parametrize(
    "term",
    [
        {"kind": "binary_cross_entropy"},
        {"kind": "dice"},
        {"kind": "jaccard"},
        {"kind": "lovasz"},
        {"kind": "focal", "alpha": 0.25},
        {"kind": "tversky", "alpha": 0.3, "beta": 0.7},
        {"kind": "boundary"},
        {"kind": "hausdorff", "max_distance": 2},
    ],
    ids=lambda term: term["kind"],
)
def test_binary_terms_are_finite_differentiable_and_ignore_exactly(term):
    g = torch.Generator().manual_seed(19)
    logits = torch.randn(2, 1, 7, 9, generator=g, dtype=torch.float64, requires_grad=True)
    target = torch.randint(0, 2, (2, 7, 9), generator=g)
    target[:, 0, :4] = IGNORE
    spec = from_dict(LossSpec, {"task": "binary", "terms": [term]})
    objective = SegmentationLoss(LossConfig.from_spec(spec), 1, IGNORE).double()
    loss, _ = objective(logits, target)
    assert torch.isfinite(loss)
    loss.backward()
    ignored = (target == IGNORE).unsqueeze(1)
    assert torch.count_nonzero(logits.grad[ignored]) == 0
    assert torch.count_nonzero(logits.grad[~ignored]) > 0


def test_multilabel_bce_masks_ignored_elements_and_inactive_channels():
    logits = torch.randn(2, 3, 5, 6, dtype=torch.float64, requires_grad=True)
    target = torch.randint(0, 2, logits.shape)
    target[0, :, 0, 0] = IGNORE
    active = torch.tensor([[True, False, True], [False, True, True]])
    spec = from_dict(
        LossSpec,
        {"task": "multilabel", "terms": [{"kind": "binary_cross_entropy"}]},
    )
    objective = SegmentationLoss(LossConfig.from_spec(spec), 3, IGNORE).double()
    loss, _ = objective(logits, target, active=active)
    loss.backward()
    inactive = (~active).view(2, 3, 1, 1).expand_as(logits)
    ignored = target == IGNORE
    assert torch.count_nonzero(logits.grad[inactive | ignored]) == 0
    assert torch.count_nonzero(logits.grad[~inactive & ~ignored]) > 0


def test_multilabel_overlap_term_uses_independent_sigmoid_channels():
    logits = torch.randn(2, 3, 5, 6, dtype=torch.float64, requires_grad=True)
    target = torch.randint(0, 2, logits.shape)
    target[:, 2, :2, :2] = IGNORE
    spec = from_dict(
        LossSpec,
        {
            "task": "multilabel",
            "terms": [{"kind": "tversky", "alpha": 0.4, "beta": 0.6}],
        },
    )
    loss, _ = SegmentationLoss(LossConfig.from_spec(spec), 3, IGNORE)(logits, target)
    loss.backward()
    assert torch.isfinite(loss)
    assert torch.count_nonzero(logits.grad[target == IGNORE]) == 0


def test_multiclass_target_cannot_name_an_inactive_class():
    logits = torch.randn(1, 3, 2, 2)
    target = torch.tensor([[[0, 1], [2, 0]]])
    active = torch.tensor([True, False, True])
    with pytest.raises(ValueError, match="marked inactive"):
        SegmentationLoss(LossConfig(), 3)(logits, target, active=active)


def test_label_smoothing_distributes_only_over_active_classes():
    logits = torch.randn(2, 4, 3, 5, dtype=torch.float64, requires_grad=True)
    target = torch.randint(0, 3, (2, 3, 5))
    active = torch.tensor([[True, True, True, False], [True, True, True, False]])
    objective = SegmentationLoss(LossConfig(label_smoothing=0.2), 4).double()
    got, _ = objective(logits, target, active=active)
    expected = F.cross_entropy(logits[:, :3], target, label_smoothing=0.2)
    assert torch.allclose(got, expected, atol=1e-12)
    got.backward()
    assert torch.count_nonzero(logits.grad[:, 3]) == 0


@pytest.mark.parametrize("kind", ["dice", "jaccard", "lovasz"])
def test_multiclass_overlap_present_false_matches_per_sample_reduced_spaces(kind):
    logits = torch.randn(2, 4, 3, 5, dtype=torch.float64)
    target = torch.randint(0, 3, (2, 3, 5))
    target[1][target[1] == 0] = 2
    active = torch.tensor([[True, True, True, False], [False, True, True, True]])
    spec = from_dict(
        LossSpec,
        {"terms": [{"kind": kind, "present_only": False, "smooth": 1.0}]}
        if kind in ("dice", "jaccard")
        else {"terms": [{"kind": kind, "present_only": False}]},
    )
    objective = SegmentationLoss(LossConfig.from_spec(spec), 4).double()
    got, _ = objective(logits, target, active=active)

    # Reconstruct a global C-channel view from each sample's reduced softmax.
    # The macro reduction is per canonical class; within a class, only samples
    # where that class is active contribute pixels.
    reduced0 = logits[0:1, :3].softmax(1)
    reduced1 = logits[1:2, 1:].softmax(1)
    onehot0 = F.one_hot(target[0:1], 4).permute(0, 3, 1, 2).to(logits.dtype)
    onehot1 = F.one_hot(target[1:2], 4).permute(0, 3, 1, 2).to(logits.dtype)
    expected_terms = []
    for class_id in range(4):
        pred_parts = []
        truth_parts = []
        if active[0, class_id]:
            pred_parts.append(reduced0[:, class_id].reshape(-1))
            truth_parts.append(onehot0[:, class_id].reshape(-1))
        if active[1, class_id]:
            pred_parts.append(reduced1[:, class_id - 1].reshape(-1))
            truth_parts.append(onehot1[:, class_id].reshape(-1))
        pred = torch.cat(pred_parts)
        truth = torch.cat(truth_parts)
        if kind == "dice":
            expected_terms.append(
                1.0 - (2.0 * (pred * truth).sum() + 1.0) / (pred.sum() + truth.sum() + 1.0)
            )
        elif kind == "jaccard":
            intersection = (pred * truth).sum()
            expected_terms.append(
                1.0 - (intersection + 1.0) / (pred.sum() + truth.sum() - intersection + 1.0)
            )
        else:
            errors = (truth - pred).abs()
            errors, perm = errors.sort(descending=True)
            from segmentary.engine.losses import lovasz_grad

            expected_terms.append(torch.dot(errors, lovasz_grad(truth[perm])))
    expected = torch.stack(expected_terms).mean()
    assert torch.allclose(got, expected, atol=1e-12)

    perturbed = logits.clone()
    perturbed[0, 3] += 1e5
    perturbed[1, 0] -= 1e5
    after, _ = objective(perturbed, target, active=active)
    assert torch.equal(got, after)


def test_hausdorff_loss_value_ignores_logits_under_ignored_pixels():
    logits, target, objective = _multiclass({"kind": "hausdorff", "max_distance": 4})
    before, _ = objective(logits, target)
    ignored = (target == IGNORE).unsqueeze(1).expand_as(logits)
    perturbed = logits.detach().clone()
    perturbed[ignored] += torch.linspace(-1000, 1000, int(ignored.sum()), dtype=logits.dtype)
    after, _ = objective(perturbed, target)
    assert torch.equal(before, after)


def test_hausdorff_loss_value_ignores_inactive_channel_predictions():
    logits = torch.randn(2, 4, 5, 6, dtype=torch.float64)
    target = torch.randint(0, 3, (2, 5, 6))
    active = torch.tensor([[True, True, True, False], [True, True, True, False]])
    spec = from_dict(LossSpec, {"terms": [{"kind": "hausdorff", "max_distance": 4}]})
    objective = SegmentationLoss(LossConfig.from_spec(spec), 4).double()
    before, _ = objective(logits, target, active=active)
    perturbed = logits.clone()
    perturbed[:, 3] += 1e5
    after, _ = objective(perturbed, target, active=active)
    assert torch.equal(before, after)


@pytest.mark.parametrize("bad_label", [-1, 3])
def test_multiclass_rejects_out_of_range_targets(bad_label):
    logits = torch.randn(1, 3, 2, 2)
    target = torch.zeros(1, 2, 2, dtype=torch.long)
    target[0, 0, 0] = bad_label
    with pytest.raises(ValueError, match="must be in"):
        SegmentationLoss(LossConfig(), 3)(logits, target)


def test_class_weighted_ce_rejects_a_batch_with_zero_total_target_weight():
    logits = torch.randn(1, 3, 2, 2)
    target = torch.zeros(1, 2, 2, dtype=torch.long)
    spec = from_dict(
        LossSpec,
        {"terms": [{"kind": "cross_entropy", "class_weights": [0.0, 1.0, 1.0]}]},
    )
    with pytest.raises(ValueError, match="zero for every valid target"):
        SegmentationLoss(LossConfig.from_spec(spec), 3)(logits, target)


@pytest.mark.parametrize(
    "task,c,target",
    [
        ("binary", 1, torch.tensor([[[0, 2]]])),
        ("multilabel", 2, torch.tensor([[[[0, 1]], [[2, 0]]]])),
    ],
)
def test_sigmoid_objectives_reject_non_binary_targets(task, c, target):
    logits = torch.randn(1, c, 1, 2)
    spec = from_dict(
        LossSpec,
        {"task": task, "terms": [{"kind": "binary_cross_entropy"}]},
    )
    with pytest.raises(ValueError, match="targets must contain only"):
        SegmentationLoss(LossConfig.from_spec(spec), c)(logits, target)


def test_weighted_composition_equals_explicit_sum():
    logits = torch.tensor([[[[2.0, -1.0]], [[-1.0, 2.0]]]], dtype=torch.float64, requires_grad=True)
    target = torch.tensor([[[0, 1]]])
    spec = from_dict(
        LossSpec,
        {
            "terms": [
                {"kind": "cross_entropy", "weight": 2.0},
                {"kind": "dice", "weight": 0.5},
            ]
        },
    )
    got, parts = SegmentationLoss(LossConfig.from_spec(spec), 2)(logits, target)
    expected = 2.0 * parts["cross_entropy"] + 0.5 * parts["dice"]
    assert torch.allclose(got.detach(), expected)


def test_ohem_keeps_the_hardest_requested_fraction():
    logits = torch.tensor([[[[4.0, -3.0, 0.0, 2.0]], [[-4.0, 3.0, 0.0, -2.0]]]])
    target = torch.zeros((1, 1, 4), dtype=torch.long)
    spec = from_dict(
        LossSpec,
        {"terms": [{"kind": "ohem_cross_entropy", "fraction": 0.5, "min_kept": 1}]},
    )
    got, _ = SegmentationLoss(LossConfig.from_spec(spec), 2)(logits, target)
    raw = F.cross_entropy(logits, target, reduction="none").reshape(-1)
    assert torch.allclose(got, raw.topk(2).values.mean())


def test_per_sample_inactive_mask_matches_reduced_softmax_for_each_sample():
    logits = torch.randn(2, 4, 3, 5, dtype=torch.float64)
    target = torch.randint(0, 3, (2, 3, 5))
    target[1][target[1] == 0] = 2
    active = torch.tensor([[True, True, True, False], [False, True, True, True]])
    objective = SegmentationLoss(LossConfig(), 4, IGNORE).double()
    got, _ = objective(logits, target, active=active)

    loss0 = F.cross_entropy(logits[0:1, :3], target[0:1], reduction="sum")
    loss1 = F.cross_entropy(logits[1:2, 1:], target[1:2] - 1, reduction="sum")
    expected = (loss0 + loss1) / target.numel()
    assert torch.allclose(got, expected, atol=1e-12)


@pytest.mark.parametrize("task,c", [("multiclass", 3), ("binary", 1), ("multilabel", 3)])
def test_all_ignore_is_graph_connected_zero_for_every_task(task, c):
    logits = torch.randn(2, c, 4, 5, requires_grad=True)
    target_shape = (2, 4, 5) if task != "multilabel" else logits.shape
    target = torch.full(target_shape, IGNORE, dtype=torch.long)
    term = "cross_entropy" if task == "multiclass" else "binary_cross_entropy"
    spec = from_dict(LossSpec, {"task": task, "terms": [{"kind": term}]})
    loss, parts = SegmentationLoss(LossConfig.from_spec(spec), c, IGNORE)(logits, target)
    assert loss.item() == 0.0 and parts["empty_crop"].item() == 1.0
    loss.backward()
    assert torch.count_nonzero(logits.grad) == 0


def test_kl_requires_same_shape_teacher_and_detaches_it_by_default():
    logits = torch.randn(1, 3, 4, 5, requires_grad=True)
    target = torch.randint(0, 3, (1, 4, 5))
    teacher = torch.randn_like(logits, requires_grad=True)
    spec = from_dict(
        LossSpec,
        {"terms": [{"kind": "kl_distillation", "temperature": 2.0}]},
    )
    objective = SegmentationLoss(LossConfig.from_spec(spec), 3)
    with pytest.raises(ValueError, match="not provided"):
        objective(logits, target)
    with pytest.raises(ValueError, match="exactly match"):
        objective(logits, target, teacher_logits=teacher[:, :, :-1])
    loss, _ = objective(logits, target, teacher_logits=teacher)
    loss.backward()
    assert torch.count_nonzero(logits.grad) > 0
    assert teacher.grad is None


def test_reduced_precision_promotes_objective_math_to_float32():
    logits = torch.randn(1, 3, 5, 5, dtype=torch.bfloat16, requires_grad=True)
    target = torch.randint(0, 3, (1, 5, 5))
    loss, parts = SegmentationLoss(LossConfig(aux="lovasz", aux_weight=0.5), 3)(logits, target)
    assert loss.dtype == torch.float32
    assert all(value.dtype == torch.float32 for value in parts.values())


def test_legacy_loss_fields_migrate_to_the_canonical_terms():
    cfg = LossConfig(aux="lovasz", aux_weight=0.5, ce_weight=2.0, label_smoothing=0.1)
    assert [term.kind for term in cfg.terms] == ["cross_entropy", "lovasz"]
    assert cfg.terms[0].weight == 2.0
    assert cfg.terms[1].weight == 0.5


@pytest.mark.parametrize(
    "raw,message",
    [
        ({"terms": [{"kind": "unknown"}]}, "expected one of"),
        ({"terms": [{"kind": "dice", "weight": 0}]}, "weight must be positive"),
        ({"terms": [{"kind": "focal", "gamma": -1}]}, "gamma"),
        ({"terms": [{"kind": "ohem_cross_entropy", "fraction": 0}]}, "fraction"),
        ({"task": "multiclass", "activation": "sigmoid"}, "requires softmax"),
        ({"task": "binary", "terms": [{"kind": "cross_entropy"}]}, "cannot use"),
        (
            {
                "terms": [{"kind": "dice"}],
                "aux": "lovasz",
                "aux_weight": 0.5,
            },
            "cannot be combined",
        ),
    ],
)
def test_invalid_objective_configs_fail_closed(raw, message):
    with pytest.raises(ConfigError, match=message):
        from_dict(LossSpec, raw)


def test_multiclass_focal_rejects_scalar_alpha_but_accepts_per_class_alpha():
    with pytest.raises(ConfigError, match="per-class list"):
        from_dict(LossSpec, {"terms": [{"kind": "focal", "alpha": 0.25}]})
    spec = from_dict(LossSpec, {"terms": [{"kind": "focal", "alpha": [1.0, 0.5, 2.0]}]})
    SegmentationLoss(LossConfig.from_spec(spec), 3)


@pytest.mark.parametrize("bad", [True, "1", float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize(
    "raw",
    [
        {"terms": [{"kind": "cross_entropy", "class_weights": [1.0, "BAD"]}]},
        {"task": "binary", "terms": [{"kind": "binary_cross_entropy", "pos_weights": ["BAD"]}]},
        {"terms": [{"kind": "focal", "alpha": [1.0, "BAD"]}]},
    ],
)
def test_direct_weight_list_values_fail_with_config_error(raw, bad):
    term = raw["terms"][0]
    key = next(key for key in ("class_weights", "pos_weights", "alpha") if key in term)
    term[key][-1] = bad
    with pytest.raises(ConfigError):
        from_dict(LossSpec, raw)


@pytest.mark.parametrize(
    "raw",
    [
        {"terms": [{"kind": "cross_entropy", "weight": float("nan")}]},
        {"terms": [{"kind": "dice", "smooth": float("inf")}]},
        {"terms": [{"kind": "jaccard", "smooth": float("inf")}]},
        {"terms": [{"kind": "focal", "gamma": float("nan")}]},
        {"terms": [{"kind": "tversky", "alpha": float("inf")}]},
        {"terms": [{"kind": "ohem_cross_entropy", "fraction": float("nan")}]},
        {"terms": [{"kind": "boundary", "smooth": float("inf")}]},
        {"terms": [{"kind": "hausdorff", "power": float("nan")}]},
        {"terms": [{"kind": "kl_distillation", "temperature": float("inf")}]},
        {"ce_weight": float("nan")},
    ],
)
def test_nonfinite_objective_numbers_fail_closed(raw):
    with pytest.raises(ConfigError, match="finite"):
        from_dict(LossSpec, raw)
