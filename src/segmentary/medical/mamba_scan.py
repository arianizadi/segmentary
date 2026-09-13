"""Portable Mamba selective scan, preserving the original recurrence and gradients.

Adapted from Tri Dao and Albert Gu's Apache-2.0 Mamba implementation and
SegMamba's three-direction extension; see mamba_vendor/NOTICE.md. The Torch
backend is an associative affine scan in checkpointed chunks. It has the same
recurrence as selective_scan_ref, without installing or silently substituting a
CUDA kernel. Parallel reassociation can differ in floating-point rounding.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import torch
from torch import Tensor, nn
from torch.nn import functional as F
from torch.utils.checkpoint import checkpoint


def _scan_chunk(
    u: Tensor, delta: Tensor, a: Tensor, b: Tensor, c: Tensor, initial: Tensor
) -> tuple[Tensor, Tensor]:
    # Layout B,L,D,N. Affine composition is associative: (a,b)o(c,d)=(ac,b+ad).
    transition = torch.exp(delta.transpose(1, 2).unsqueeze(-1) * a)
    drive = (
        delta.transpose(1, 2).unsqueeze(-1)
        * u.transpose(1, 2).unsqueeze(-1)
        * b.transpose(1, 2).unsqueeze(2)
    )
    step = 1
    while step < u.shape[-1]:
        drive = torch.cat(
            (drive[:, :step], drive[:, step:] + transition[:, step:] * drive[:, :-step]),
            dim=1,
        )
        transition = torch.cat(
            (transition[:, :step], transition[:, step:] * transition[:, :-step]), dim=1
        )
        step *= 2
    states = drive + transition * initial.unsqueeze(1)
    y = (states * c.transpose(1, 2).unsqueeze(2)).sum(-1).transpose(1, 2)
    return y, states[:, -1]


def selective_scan_torch(
    u: Tensor,
    delta: Tensor,
    a: Tensor,
    b: Tensor,
    c: Tensor,
    d: Tensor | None = None,
    z: Tensor | None = None,
    delta_bias: Tensor | None = None,
    delta_softplus: bool = True,
    *,
    chunk_size: int = 256,
    checkpoint_chunks: bool = True,
) -> Tensor:
    """Real-valued input-dependent B/C Mamba scan with bounded chunk memory.

    u/delta/z: B,D,L; A: D,N; B/C: B,N,L; D/delta_bias: D.
    Reduced precision inputs accumulate in FP32, matching the upstream reference.
    Double precision is retained for numerical verification and gradcheck.
    """
    if type(chunk_size) is not int or chunk_size < 1:
        raise ValueError("scan chunk_size must be a positive integer")
    if u.ndim != 3 or delta.shape != u.shape or a.ndim != 2:
        raise ValueError("Expected u/delta B,D,L and A D,N")
    if u.shape[-1] < 1 or a.shape[0] != u.shape[1]:
        raise ValueError("Invalid scan channel or sequence dimensions")
    expected = (u.shape[0], a.shape[1], u.shape[2])
    if b.shape != expected or c.shape != expected:
        raise ValueError("Input-dependent B/C must have shape B,N,L")
    if any(t.is_complex() for t in (u, delta, a, b, c)):
        raise ValueError("This implementation supports real-valued Mamba states only")
    original_dtype = u.dtype
    dtype = torch.float64 if u.dtype == torch.float64 else torch.float32
    u, delta, a, b, c = (t.to(dtype) for t in (u, delta, a, b, c))
    if delta_bias is not None:
        delta = delta + delta_bias.to(dtype)[None, :, None]
    if delta_softplus:
        delta = F.softplus(delta)
    state = u.new_zeros((u.shape[0], u.shape[1], a.shape[1]))
    outputs = []
    for start in range(0, u.shape[-1], chunk_size):
        end = start + chunk_size
        args = (
            u[..., start:end],
            delta[..., start:end],
            a,
            b[..., start:end],
            c[..., start:end],
            state,
        )
        if checkpoint_chunks and torch.is_grad_enabled() and any(t.requires_grad for t in args):
            out, state = checkpoint(_scan_chunk, *args, use_reentrant=False)
        else:
            out, state = _scan_chunk(*args)
        outputs.append(out)
    result = torch.cat(outputs, dim=-1)
    if d is not None:
        result = result + u * d.to(dtype)[None, :, None]
    if z is not None:
        result = result * F.silu(z.to(dtype))
    return result.to(original_dtype)


class MambaBranch(nn.Module):
    """One causal convolution and input-dependent selective SSM branch."""

    def __init__(
        self,
        channels: int,
        state_size: int,
        conv_size: int,
        dt_rank: int,
        *,
        special_dt_init: bool,
        scan_backend: str,
        chunk_size: int,
    ) -> None:
        super().__init__()
        self.dt_rank = dt_rank
        self.state_size = state_size
        self.scan_backend = scan_backend
        self.chunk_size = chunk_size
        self.conv1d = nn.Conv1d(
            channels, channels, conv_size, groups=channels, padding=conv_size - 1
        )
        self.x_proj = nn.Linear(channels, dt_rank + 2 * state_size, bias=False)
        self.dt_proj = nn.Linear(dt_rank, channels)
        if special_dt_init:
            nn.init.uniform_(self.dt_proj.weight, -(dt_rank**-0.5), dt_rank**-0.5)
            dt = torch.exp(torch.rand(channels) * math.log(100) + math.log(0.001)).clamp_min(1e-4)
            with torch.no_grad():
                self.dt_proj.bias.copy_(dt + torch.log(-torch.expm1(-dt)))
        self.a_log = nn.Parameter(torch.arange(1, state_size + 1).float().log().repeat(channels, 1))
        self.d = nn.Parameter(torch.ones(channels))
        # These attributes follow the original Mamba optimizer contract.
        self.a_log._no_weight_decay = True  # type: ignore[attr-defined]
        self.d._no_weight_decay = True  # type: ignore[attr-defined]
        self.dt_proj.bias._no_reinit = True  # type: ignore[attr-defined]

    def forward(self, xz: Tensor) -> Tensor:
        x, z = xz.chunk(2, dim=1)
        x = F.silu(self.conv1d(x)[..., : x.shape[-1]])
        projected = self.x_proj(x.transpose(1, 2))
        dt, b, c = torch.split(projected, [self.dt_rank, self.state_size, self.state_size], dim=-1)
        delta = F.linear(dt, self.dt_proj.weight).transpose(1, 2)
        a = -torch.exp(self.a_log.to(torch.float64 if x.dtype == torch.float64 else torch.float32))
        args = (x, delta, a, b.transpose(1, 2), c.transpose(1, 2), self.d, z, self.dt_proj.bias)
        if self.scan_backend == "native":
            if not x.is_cuda:
                raise ValueError("The explicitly selected native Mamba scan requires CUDA")
            scan: Callable[..., Tensor]
            try:
                from mamba_ssm.ops.selective_scan_interface import selective_scan_fn
            except ImportError as exc:
                raise RuntimeError(
                    "scan_backend=native requires a compatible mamba-ssm CUDA installation"
                ) from exc
            scan = selective_scan_fn
            return scan(*args, delta_softplus=True)
        return selective_scan_torch(*args, chunk_size=self.chunk_size)


class Mamba(nn.Module):
    """Original Mamba v1 or SegMamba v3 forward/reverse/interleaved mixer."""

    def __init__(
        self,
        d_model: int,
        *,
        d_state: int = 16,
        d_conv: int = 4,
        expand: int = 2,
        three_direction: bool = False,
        nslices: int = 1,
        scan_backend: str = "torch",
        chunk_size: int = 256,
    ) -> None:
        super().__init__()
        if scan_backend not in {"torch", "native"}:
            raise ValueError("scan_backend must be torch or native; no automatic fallback is used")
        for name, value in {
            "d_model": d_model,
            "d_state": d_state,
            "d_conv": d_conv,
            "expand": expand,
            "nslices": nslices,
            "chunk_size": chunk_size,
        }.items():
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        self.d_model = d_model
        self.d_inner = d_model * expand
        self.nslices = nslices
        self.three_direction = three_direction
        self.in_proj = nn.Linear(d_model, self.d_inner * 2, bias=False)
        branch_options: dict[str, Any] = {
            "channels": self.d_inner,
            "state_size": d_state,
            "conv_size": d_conv,
            "dt_rank": math.ceil(d_model / 16),
            "scan_backend": scan_backend,
            "chunk_size": chunk_size,
        }
        self.forward_branch = MambaBranch(**branch_options, special_dt_init=True)
        if three_direction:
            # The official SegMamba code leaves the reverse/spatial dt projections
            # at Linear's default initialization; preserve that asymmetric choice.
            self.reverse_branch = MambaBranch(**branch_options, special_dt_init=False)
            self.spatial_branch = MambaBranch(**branch_options, special_dt_init=False)
        self.out_proj = nn.Linear(self.d_inner, d_model, bias=False)

    def forward(self, x: Tensor) -> Tensor:
        if x.ndim != 3 or x.shape[-1] != self.d_model:
            raise ValueError("Mamba expects B,L,d_model")
        xz = self.in_proj(x).transpose(1, 2)
        output = self.forward_branch(xz)
        if self.three_direction:
            if x.shape[1] % self.nslices:
                raise ValueError("SegMamba sequence length must be divisible by nslices")
            output = output + self.reverse_branch(xz.flip(-1)).flip(-1)
            # Exact permutation used by SegMamba: chunk -> stack -> flatten.
            length = x.shape[1]
            spatial = xz.reshape(x.shape[0], 2 * self.d_inner, self.nslices, length // self.nslices)
            spatial = spatial.transpose(-1, -2).flatten(-2)
            spatial = self.spatial_branch(spatial)
            spatial = spatial.reshape(
                x.shape[0], self.d_inner, length // self.nslices, self.nslices
            )
            output = output + spatial.transpose(-1, -2).flatten(-2)
        return self.out_proj(output.transpose(1, 2))
