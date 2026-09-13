"""Numerically safe operations shared by scratch CT training and verification."""

from __future__ import annotations

import math
from collections.abc import Iterable

import torch
from torch import Tensor


@torch.no_grad()
def clip_grad_norm_(parameters: Iterable[Tensor] | Tensor, max_norm: float) -> Tensor:
    """Clip global L2 gradient norm, retrying an overflowing reduction in float64.

    Standard scratch query models can produce finite float32 gradients whose
    squared L2 sum exceeds float32 range at their first update. Treating that
    *reduction* overflow as an invalid gradient prevents otherwise valid clipping.
    Keep PyTorch's normal fast path and exact clipping formula; use float64 only
    when the first norm is nonfinite. A norm still nonfinite in float64 raises
    before modifying any gradient, including when an actual gradient is NaN/Inf.
    """
    if isinstance(max_norm, bool) or not math.isfinite(max_norm) or max_norm <= 0:
        raise ValueError("max_norm must be finite and positive")
    params = [parameters] if isinstance(parameters, Tensor) else list(parameters)
    gradients = [parameter.grad for parameter in params if parameter.grad is not None]
    total = torch.nn.utils.get_total_norm(gradients, norm_type=2, error_if_nonfinite=False)
    if not torch.isfinite(total):
        device = gradients[0].device
        total = torch.linalg.vector_norm(
            torch.stack(
                [
                    torch.linalg.vector_norm(gradient, ord=2, dtype=torch.float64).to(device)
                    for gradient in gradients
                ]
            ),
            ord=2,
        )
        if not torch.isfinite(total):
            raise RuntimeError(
                "Gradient L2 norm remains non-finite in float64; gradients were not modified"
            )
    torch.nn.utils.clip_grads_with_norm_(params, max_norm, total)
    return total
