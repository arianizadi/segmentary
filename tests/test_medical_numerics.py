"""Reduction overflow must not be confused with NaN or Inf gradient entries."""

import math

import pytest
import torch

from segmentary.medical.torch_numerics import clip_grad_norm_


def test_finite_large_gradients_clip_to_expected_direction_and_length() -> None:
    first = torch.nn.Parameter(torch.zeros(1))
    second = torch.nn.Parameter(torch.zeros(1))
    first.grad = torch.tensor([1e20])
    second.grad = torch.tensor([2e20])
    norm = clip_grad_norm_(iter((first, second)), 12)
    assert norm.dtype == torch.float64
    assert norm.item() == pytest.approx(math.sqrt(5) * 1e20, rel=1e-6)
    assert first.grad.item() == pytest.approx(12 / math.sqrt(5))
    assert second.grad.item() == pytest.approx(24 / math.sqrt(5))
    assert torch.stack([first.grad, second.grad]).norm().item() == pytest.approx(12)


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), -float("inf")])
def test_invalid_gradient_raises_before_any_gradient_changes(nonfinite: float) -> None:
    valid = torch.nn.Parameter(torch.zeros(2))
    invalid = torch.nn.Parameter(torch.zeros(1))
    valid.grad = torch.tensor([3.0, 4.0])
    invalid.grad = torch.tensor([nonfinite])
    with pytest.raises(RuntimeError, match="non-finite in float64"):
        clip_grad_norm_([valid, invalid], 1)
    assert torch.equal(valid.grad, torch.tensor([3.0, 4.0]))
    if math.isnan(nonfinite):
        assert torch.isnan(invalid.grad).all()
    else:
        assert invalid.grad.item() == nonfinite


@pytest.mark.parametrize("max_norm", [1.0, 10.0])
def test_normal_path_matches_pytorch_exactly(max_norm: float) -> None:
    reference = torch.nn.Parameter(torch.zeros(4))
    actual = torch.nn.Parameter(torch.zeros(4))
    reference.grad = torch.tensor([1.0, -2.0, 3.0, -4.0])
    actual.grad = reference.grad.clone()
    expected = torch.nn.utils.clip_grad_norm_(reference, max_norm, error_if_nonfinite=True)
    observed = clip_grad_norm_(actual, max_norm)
    assert torch.equal(expected, observed)
    assert torch.equal(reference.grad, actual.grad)


def test_no_gradients_is_zero_and_does_not_initialize_gradients() -> None:
    parameter = torch.nn.Parameter(torch.ones(2))
    assert clip_grad_norm_(parameter, 12).item() == 0
    assert parameter.grad is None


@pytest.mark.parametrize("max_norm", [0, -1, float("nan"), float("inf"), True])
def test_invalid_bound_is_rejected(max_norm: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        clip_grad_norm_([], max_norm)
