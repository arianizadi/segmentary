"""Context modules shared by PSP, ASPP, DeepLabV3+, and UPer heads."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from ..layers import ActivationKind, ConvNormAct, NormKind


def checked_dropout(dropout: float) -> float:
    if not isinstance(dropout, (int, float)) or isinstance(dropout, bool):
        raise TypeError("dropout must be a number")
    dropout = float(dropout)
    if not 0.0 <= dropout < 1.0:
        raise ValueError(f"dropout must be in [0, 1), got {dropout}")
    return dropout


def checked_bins(bins: tuple[int, ...]) -> tuple[int, ...]:
    if not isinstance(bins, tuple) or not bins:
        raise ValueError("pool bins must be a non-empty tuple")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in bins):
        raise ValueError(f"pool bins must be positive integers, got {bins}")
    if len(set(bins)) != len(bins):
        raise ValueError(f"pool bins must be unique, got {bins}")
    return bins


class PyramidPooling(nn.Module):
    """Concatenate an input map with context pooled at several grid sizes."""

    def __init__(
        self,
        in_channels: int,
        bins: tuple[int, ...],
        *,
        branch_channels: int,
        norm: NormKind,
        activation: ActivationKind,
    ) -> None:
        super().__init__()
        self.bins = checked_bins(bins)
        if branch_channels < 1:
            raise ValueError("pyramid-pooling branch_channels must be positive")
        self.branches = nn.ModuleList(
            ConvNormAct(
                in_channels,
                branch_channels,
                1,
                # A bin-1 branch produces one value per channel. BatchNorm
                # cannot estimate variance when the per-device batch is also
                # one, so omit normalization only on that global branch.
                norm="none" if norm == "batch" and bin_size == 1 else norm,
                activation=activation,
            )
            for bin_size in self.bins
        )
        self.out_channels = in_channels + len(self.bins) * branch_channels

    def forward(self, feature: Tensor) -> Tensor:
        size = tuple(feature.shape[-2:])
        context = [feature]
        for bin_size, projection in zip(self.bins, self.branches, strict=True):
            pooled = F.adaptive_avg_pool2d(feature, output_size=(bin_size, bin_size))
            context.append(
                F.interpolate(projection(pooled), size=size, mode="bilinear", align_corners=False)
            )
        return torch.cat(context, dim=1)


class ASPP(nn.Module):
    """Parallel point, dilated, and global-context branches."""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        rates: tuple[int, ...],
        *,
        norm: NormKind,
        activation: ActivationKind,
    ) -> None:
        super().__init__()
        if not isinstance(rates, tuple) or not rates:
            raise ValueError("ASPP rates must be a non-empty tuple")
        if any(isinstance(rate, bool) or not isinstance(rate, int) or rate < 1 for rate in rates):
            raise ValueError(f"ASPP rates must be positive integers, got {rates}")
        if len(set(rates)) != len(rates):
            raise ValueError(f"ASPP rates must be unique, got {rates}")
        self.point = ConvNormAct(in_channels, out_channels, 1, norm=norm, activation=activation)
        self.dilated = nn.ModuleList(
            ConvNormAct(
                in_channels,
                out_channels,
                3,
                dilation=rate,
                norm=norm,
                activation=activation,
            )
            for rate in rates
        )
        # Global pooling always produces 1x1. Keep this branch independent of
        # batch statistics so a valid batch-one segmentation job cannot crash.
        self.image_pool = ConvNormAct(
            in_channels, out_channels, 1, norm="none", activation=activation
        )
        branch_count = 2 + len(rates)
        self.project = ConvNormAct(
            branch_count * out_channels,
            out_channels,
            1,
            norm=norm,
            activation=activation,
        )
        self.out_channels = out_channels

    def forward(self, feature: Tensor) -> Tensor:
        size = tuple(feature.shape[-2:])
        pooled = self.image_pool(F.adaptive_avg_pool2d(feature, output_size=1))
        branches = [self.point(feature), *(branch(feature) for branch in self.dilated)]
        branches.append(F.interpolate(pooled, size=size, mode="bilinear", align_corners=False))
        return self.project(torch.cat(branches, dim=1))
