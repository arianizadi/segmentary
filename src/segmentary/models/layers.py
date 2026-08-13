"""Small, typed neural-network building blocks shared by native components."""

from __future__ import annotations

from typing import Literal

import torch.nn.functional as F
from torch import Tensor, nn

ActivationKind = Literal[
    "relu",
    "relu6",
    "leaky_relu",
    "gelu",
    "silu",
    "elu",
    "mish",
    "hardswish",
]
NormKind = Literal["batch", "group", "instance", "layer", "none"]


def build_activation(kind: ActivationKind) -> nn.Module:
    if kind == "relu":
        return nn.ReLU(inplace=False)
    if kind == "relu6":
        return nn.ReLU6(inplace=False)
    if kind == "leaky_relu":
        return nn.LeakyReLU(negative_slope=0.01, inplace=False)
    if kind == "gelu":
        return nn.GELU()
    if kind == "silu":
        return nn.SiLU(inplace=False)
    if kind == "elu":
        return nn.ELU(alpha=1.0, inplace=False)
    if kind == "mish":
        return nn.Mish(inplace=False)
    if kind == "hardswish":
        return nn.Hardswish(inplace=False)
    raise ValueError(
        f"unknown activation {kind!r}; choose relu, relu6, leaky_relu, gelu, silu, "
        "elu, mish, or hardswish"
    )


def _group_count(channels: int) -> int:
    # Keep at least four channels per group when possible.  One-channel groups
    # collapse on a pooled 1x1 feature and provide no useful normalisation.
    limit = min(32, max(1, channels // 4))
    return next(group for group in range(limit, 0, -1) if channels % group == 0)


class LayerNorm2d(nn.Module):
    """Layer-normalize channels independently at every spatial location.

    ``torch.nn.LayerNorm`` expects its normalized dimensions at the end of a
    tensor.  Dense feature maps are NCHW, so this small adapter temporarily
    exposes channels as the trailing dimension and then restores NCHW.  Unlike
    ``GroupNorm(1, C)``, spatial locations do not influence one another.
    """

    def __init__(self, channels: int, *, eps: float = 1e-5) -> None:
        super().__init__()
        if channels < 1:
            raise ValueError(f"LayerNorm2d channels must be positive, got {channels}")
        self.channels = channels
        self.eps = eps
        self.weight = nn.Parameter(Tensor(channels))
        self.bias = nn.Parameter(Tensor(channels))
        nn.init.ones_(self.weight)
        nn.init.zeros_(self.bias)

    def forward(self, values: Tensor) -> Tensor:
        if values.ndim != 4 or int(values.shape[1]) != self.channels:
            raise ValueError(
                f"LayerNorm2d expected N,{self.channels},H,W, got {tuple(values.shape)}"
            )
        channels_last = values.permute(0, 2, 3, 1)
        normalized = F.layer_norm(
            channels_last,
            (self.channels,),
            self.weight,
            self.bias,
            self.eps,
        )
        return normalized.permute(0, 3, 1, 2).contiguous()


def build_norm(kind: NormKind, channels: int) -> nn.Module:
    if channels < 1:
        raise ValueError(f"normalization channels must be positive, got {channels}")
    if kind == "batch":
        return nn.BatchNorm2d(channels)
    if kind == "group":
        return nn.GroupNorm(_group_count(channels), channels)
    if kind == "instance":
        return nn.InstanceNorm2d(channels, affine=True, track_running_stats=False)
    if kind == "layer":
        return LayerNorm2d(channels)
    if kind == "none":
        return nn.Identity()
    raise ValueError(
        f"unknown normalization {kind!r}; choose batch, group, instance, layer, or none"
    )


class ConvNormAct(nn.Sequential):
    """Conv2d followed by a selected normalization and activation."""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 3,
        *,
        stride: int = 1,
        dilation: int = 1,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        if in_channels < 1 or out_channels < 1:
            raise ValueError("ConvNormAct channel counts must be positive")
        if kernel_size < 1 or kernel_size % 2 == 0:
            raise ValueError("ConvNormAct kernel_size must be a positive odd integer")
        if stride < 1 or dilation < 1:
            raise ValueError("ConvNormAct stride and dilation must be positive")
        padding = dilation * (kernel_size // 2)
        super().__init__(
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size,
                stride=stride,
                padding=padding,
                dilation=dilation,
                bias=norm == "none",
            ),
            build_norm(norm, out_channels),
            build_activation(activation),
        )
