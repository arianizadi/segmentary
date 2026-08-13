"""Hand-computed and fail-closed contracts for dense segmentation losses."""

from __future__ import annotations

import math
from fractions import Fraction

import pytest
import torch

from segmentary.config import LossSpec, from_dict
from segmentary.engine.losses import LossConfig, SegmentationLoss

IGNORE = 255


def _objective(
    term: dict[str, object],
    *,
    classes: int,
    task: str = "multiclass",
) -> SegmentationLoss:
    spec = from_dict(LossSpec, {"task": task, "terms": [term]})
    return SegmentationLoss(LossConfig.from_spec(spec), classes, IGNORE)


@pytest.mark.parametrize(
    ("kind", "channel_losses"),
    [
        ("dice", (Fraction(3, 11), Fraction(5, 17), Fraction(5, 17))),
        ("jaccard", (Fraction(1, 3), Fraction(5, 14), Fraction(5, 17))),
        ("tversky", (Fraction(7, 31), Fraction(11, 47), Fraction(5, 53))),
    ],
)
@pytest.mark.parametrize(
    ("present_only", "include_background", "selected_classes"),
    [
        (True, True, (0, 1)),
        (True, False, (1,)),
        (False, True, (0, 1, 2)),
        (False, False, (1, 2)),
    ],
)
def test_overlap_losses_match_hand_computed_present_and_background_macros(
    kind: str,
    channel_losses: tuple[Fraction, Fraction, Fraction],
    present_only: bool,
    include_background: bool,
    selected_classes: tuple[int, ...],
) -> None:
    # Pixel probabilities are (1/2, 1/3, 1/6) for target 0 and
    # (1/4, 1/2, 1/4) for target 1. Class 2 is deliberately absent.
    probabilities = torch.tensor(
        [[[[1 / 2, 1 / 4]], [[1 / 3, 1 / 2]], [[1 / 6, 1 / 4]]]],
        dtype=torch.float64,
    )
    target = torch.tensor([[[0, 1]]])
    term: dict[str, object] = {
        "kind": kind,
        "smooth": 1.0,
        "present_only": present_only,
        "include_background": include_background,
    }
    if kind == "tversky":
        term.update(alpha=0.25, beta=0.75)

    loss, _ = _objective(term, classes=3)(probabilities.log(), target)

    expected = sum(channel_losses[index] for index in selected_classes) / len(selected_classes)
    assert loss.item() == pytest.approx(float(expected), abs=1e-12)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("dice", Fraction(1, 3)),
        ("jaccard", Fraction(2, 5)),
        ("tversky", Fraction(1, 4)),
    ],
)
def test_overlap_losses_renormalize_over_active_classes_and_drop_inactive_channels(
    kind: str, expected: Fraction
) -> None:
    logits = torch.zeros((1, 3, 1, 2), dtype=torch.float64, requires_grad=True)
    target = torch.tensor([[[0, 1]]])
    active = torch.tensor([True, True, False])
    term: dict[str, object] = {"kind": kind, "present_only": False}
    if kind == "tversky":
        term.update(alpha=0.25, beta=0.75)

    loss, _ = _objective(term, classes=3)(logits, target, active=active)
    loss.backward()

    assert loss.item() == pytest.approx(float(expected), abs=1e-12)
    assert torch.count_nonzero(logits.grad[:, 2]) == 0


def test_present_only_foreground_overlap_returns_safe_zero_when_only_background_exists() -> None:
    logits = torch.full((1, 3, 1, 1), torch.finfo(torch.float32).max, requires_grad=True)
    objective = _objective(
        {"kind": "dice", "present_only": True, "include_background": False}, classes=3
    )

    loss, _ = objective(logits, torch.zeros((1, 1, 1), dtype=torch.long))
    loss.backward()

    assert loss.item() == 0.0
    assert logits.grad is not None and bool(torch.isfinite(logits.grad).all())
    assert torch.count_nonzero(logits.grad) == 0


def test_multiclass_focal_per_class_alpha_matches_hand_computed_value() -> None:
    probabilities = torch.tensor(
        [[[[0.5, 0.25]], [[0.25, 0.25]], [[0.25, 0.5]]]], dtype=torch.float64
    )
    target = torch.tensor([[[0, 1]]])
    term = {"kind": "focal", "gamma": 2.0, "alpha": [2.0, 0.5, 1.0]}

    loss, _ = _objective(term, classes=3)(probabilities.log(), target)

    assert loss.item() == pytest.approx(Fraction(17, 32) * math.log(2), abs=1e-12)


@pytest.mark.parametrize(
    ("alpha", "expected_multiplier"),
    [(None, Fraction(1, 4)), (0.25, Fraction(1, 8))],
)
def test_binary_focal_none_and_scalar_alpha_branches_are_exact(
    alpha: float | None, expected_multiplier: Fraction
) -> None:
    term: dict[str, object] = {"kind": "focal", "gamma": 2.0}
    if alpha is not None:
        term["alpha"] = alpha
    logits = torch.zeros((1, 1, 1, 2), dtype=torch.float64)
    target = torch.tensor([[[1, 0]]])

    loss, _ = _objective(term, classes=1, task="binary")(logits, target)

    assert loss.item() == pytest.approx(expected_multiplier * math.log(2), abs=1e-12)


def test_multilabel_focal_per_channel_alpha_matches_hand_computed_value() -> None:
    logits = torch.zeros((1, 2, 1, 1), dtype=torch.float64)
    target = torch.tensor([[[[1]], [[0]]]])
    term = {"kind": "focal", "gamma": 2.0, "alpha": [2.0, 0.5]}

    loss, _ = _objective(term, classes=2, task="multilabel")(logits, target)

    assert loss.item() == pytest.approx(Fraction(5, 16) * math.log(2), abs=1e-12)


@pytest.mark.parametrize(
    ("threshold", "selected_probabilities"),
    [
        (0.7, (0.6, 0.4, 0.1)),  # threshold branch retains all three hard pixels
        (0.3, (0.4, 0.1)),  # only one crosses threshold, so top-k fallback retains two
    ],
)
def test_ohem_threshold_and_topk_fallback_have_exact_distinct_reductions(
    threshold: float, selected_probabilities: tuple[float, ...]
) -> None:
    true_probabilities = torch.tensor([0.9, 0.6, 0.4, 0.1], dtype=torch.float64)
    probabilities = torch.stack((true_probabilities, 1.0 - true_probabilities)).view(1, 2, 1, 4)
    target = torch.zeros((1, 1, 4), dtype=torch.long)
    term = {
        "kind": "ohem_cross_entropy",
        "fraction": 0.5,
        "min_kept": 1,
        "probability_threshold": threshold,
    }

    loss, _ = _objective(term, classes=2)(probabilities.log(), target)

    expected = -sum(math.log(value) for value in selected_probabilities) / len(
        selected_probabilities
    )
    assert loss.item() == pytest.approx(expected, abs=1e-12)


def test_class_weighted_label_smoothing_uses_only_each_samples_active_classes() -> None:
    logits = torch.zeros((2, 4, 1, 1), dtype=torch.float64, requires_grad=True)
    target = torch.tensor([[[0]], [[2]]])
    active = torch.tensor([[True, True, False, True], [False, True, True, False]])
    term = {
        "kind": "cross_entropy",
        "label_smoothing": 0.2,
        "class_weights": [2.0, 1.0, 4.0, 3.0],
    }

    loss, _ = _objective(term, classes=4)(logits, target, active=active)
    loss.backward()

    # Sample 0 contributes 2*ln(3). Sample 1 contributes
    # 0.8*4*ln(2) + 0.2*((1+4)/2)*ln(2) = 3.7*ln(2).
    expected = (2 * math.log(3) + 3.7 * math.log(2)) / 6
    assert loss.item() == pytest.approx(expected, abs=1e-12)
    assert torch.count_nonzero(logits.grad[~active.view(2, 4, 1, 1)]) == 0


@pytest.mark.parametrize("task", ["multiclass", "binary", "multilabel"])
@pytest.mark.parametrize("detach_teacher", [True, False])
def test_kl_matches_bernoulli_or_categorical_oracle_and_teacher_detach_contract(
    task: str, detach_teacher: bool
) -> None:
    if task == "multiclass":
        student = torch.tensor([[[[math.log(0.75)]], [[math.log(0.25)]]]], requires_grad=True)
        teacher = torch.tensor([[[[math.log(0.5)]], [[math.log(0.5)]]]], requires_grad=True)
        target = torch.tensor([[[0]]])
        classes = 2
    else:
        student = torch.tensor([[[[math.log(1 / 3)]]]], requires_grad=True)
        teacher = torch.zeros((1, 1, 1, 1), requires_grad=True)
        target = torch.tensor([[[1]]]) if task == "binary" else torch.tensor([[[[1]]]])
        classes = 1
    term = {
        "kind": "kl_distillation",
        "temperature": 1.0,
        "detach_teacher": detach_teacher,
    }

    loss, _ = _objective(term, classes=classes, task=task)(student, target, teacher_logits=teacher)
    loss.backward()

    assert loss.item() == pytest.approx(0.5 * math.log(Fraction(4, 3)), abs=2e-7)
    assert student.grad is not None and bool(student.grad.abs().sum() > 0)
    if detach_teacher:
        assert teacher.grad is None
    else:
        assert teacher.grad is not None and bool(teacher.grad.abs().sum() > 0)


def test_kl_promotes_reduced_precision_student_and_teacher_math_to_float32() -> None:
    student = torch.zeros((1, 2, 1, 1), dtype=torch.bfloat16, requires_grad=True)
    teacher = torch.zeros((1, 2, 1, 1), dtype=torch.float16)
    objective = _objective({"kind": "kl_distillation"}, classes=2)

    loss, parts = objective(student, torch.tensor([[[0]]]), teacher_logits=teacher)

    assert loss.dtype == torch.float32
    assert parts["kl_distillation"].dtype == torch.float32
    assert loss.item() == 0.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("location", ["inactive", "ignored"])
def test_kl_rejects_nonfinite_teacher_values_even_outside_supervision(
    bad: float, location: str
) -> None:
    student = torch.zeros((1, 3, 1, 2))
    teacher = torch.zeros_like(student)
    target = torch.tensor([[[0, IGNORE]]])
    active = torch.tensor([True, True, False])
    index = (0, 2, 0, 0) if location == "inactive" else (0, 0, 0, 1)
    teacher[index] = bad
    objective = _objective({"kind": "kl_distillation"}, classes=3)

    with pytest.raises(FloatingPointError, match="teacher_logits contains non-finite"):
        objective(student, target, active=active, teacher_logits=teacher)


def test_kl_rejects_nonfloating_teacher_logits() -> None:
    objective = _objective({"kind": "kl_distillation"}, classes=2)

    with pytest.raises(ValueError, match="teacher_logits must use a floating dtype"):
        objective(
            torch.zeros((1, 2, 1, 1)),
            torch.tensor([[[0]]]),
            teacher_logits=torch.zeros((1, 2, 1, 1), dtype=torch.long),
        )


def test_multiclass_float_targets_are_rejected_instead_of_silently_truncated() -> None:
    target = torch.tensor([[[0.2, 1.9]]])

    with pytest.raises(ValueError, match="integer class-index dtype"):
        SegmentationLoss(LossConfig(), 2)(torch.zeros((1, 2, 1, 2)), target)


@pytest.mark.parametrize("task", ["binary", "multilabel"])
def test_sigmoid_tasks_preserve_floating_zero_one_target_support(task: str) -> None:
    logits = torch.zeros((1, 1, 1, 2), dtype=torch.float64)
    target = torch.tensor([[[0.0, 1.0]]], dtype=torch.float64)
    if task == "multilabel":
        target = target.unsqueeze(1)

    loss, _ = _objective({"kind": "binary_cross_entropy"}, classes=1, task=task)(logits, target)

    assert loss.item() == pytest.approx(math.log(2), abs=1e-12)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_dense_all_ignore_rejects_nonfinite_logits_before_empty_crop_shortcut(bad: float) -> None:
    logits = torch.zeros((1, 2, 1, 1))
    logits[0, 0, 0, 0] = bad

    with pytest.raises(FloatingPointError, match="non-finite logits"):
        SegmentationLoss(LossConfig(), 2)(logits, torch.full((1, 1, 1), IGNORE))


def test_dense_all_ignore_extreme_finite_logits_return_safe_graph_zero() -> None:
    logits = torch.full((1, 2, 2, 2), torch.finfo(torch.float32).max, requires_grad=True)
    target = torch.full((1, 2, 2), IGNORE)

    loss, parts = SegmentationLoss(LossConfig(), 2)(logits, target)
    loss.backward()

    assert loss.item() == 0.0
    assert parts["empty_crop"].item() == 1.0
    assert logits.grad is not None
    assert bool(torch.isfinite(logits.grad).all())
    assert torch.count_nonzero(logits.grad) == 0


def test_dense_finite_inputs_fail_closed_when_a_term_overflows() -> None:
    limit = torch.finfo(torch.float32).max
    logits = torch.tensor([[[[limit]], [[-limit]]]])

    with pytest.raises(FloatingPointError, match="loss term 'cross_entropy'"):
        SegmentationLoss(LossConfig(), 2)(logits, torch.ones((1, 1, 1), dtype=torch.long))


def test_dense_finite_inputs_fail_closed_when_weighted_total_overflows() -> None:
    objective = _objective({"kind": "cross_entropy", "weight": 1e39}, classes=2)

    with pytest.raises(FloatingPointError, match="weighted loss total"):
        objective(torch.zeros((1, 2, 1, 1)), torch.zeros((1, 1, 1), dtype=torch.long))
