"""Unified perceptual parsing head with pyramid pooling and top-down fusion."""

from __future__ import annotations

import torch
from torch import Tensor, nn

from ..features import (
    FeatureMaps,
    FeatureSpec,
    require_increasing_reductions,
)
from ..layers import ActivationKind, ConvNormAct, NormKind
from ..wrappers import reinit_
from .base import DenseHead, resize
from .blocks import PyramidPooling, checked_bins, checked_dropout


class UPerHead(DenseHead):
    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        *,
        in_indices: tuple[int, ...],
        channels: int,
        pool_bins: tuple[int, ...] = (1, 2, 3, 6),
        dropout: float = 0.1,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__(input_specs, num_classes, in_indices, minimum_inputs=2)
        require_increasing_reductions(self.selected_specs, where="UPer head")
        if channels < 1:
            raise ValueError("UPer channels must be positive")
        pool_bins = checked_bins(pool_bins)
        deep_channels = self.selected_specs[-1].channels
        branch_channels = max(1, deep_channels // len(pool_bins))
        self.pool = PyramidPooling(
            deep_channels,
            pool_bins,
            branch_channels=branch_channels,
            norm=norm,
            activation=activation,
        )
        self.pool_bottleneck = ConvNormAct(
            self.pool.out_channels, channels, 3, norm=norm, activation=activation
        )
        self.lateral = nn.ModuleList(
            ConvNormAct(spec.channels, channels, 1, norm=norm, activation=activation)
            for spec in self.selected_specs[:-1]
        )
        self.fpn_convs = nn.ModuleList(
            ConvNormAct(channels, channels, 3, norm=norm, activation=activation)
            for _ in self.selected_specs
        )
        self.fuse = ConvNormAct(
            len(self.selected_specs) * channels,
            channels,
            3,
            norm=norm,
            activation=activation,
        )
        self.dropout = nn.Dropout2d(checked_dropout(dropout))
        self.classifier = nn.Conv2d(channels, num_classes, 1)

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        selected = self.selected_features(features)
        laterals = [
            layer(feature) for layer, feature in zip(self.lateral, selected[:-1], strict=True)
        ]
        laterals.append(self.pool_bottleneck(self.pool(selected[-1])))
        for index in range(len(laterals) - 2, -1, -1):
            laterals[index] = laterals[index] + resize(
                laterals[index + 1], tuple(laterals[index].shape[-2:])
            )
        pyramid = [layer(feature) for layer, feature in zip(self.fpn_convs, laterals, strict=True)]
        fusion_size = tuple(pyramid[0].shape[-2:])
        fused = self.fuse(torch.cat([resize(item, fusion_size) for item in pyramid], dim=1))
        return self.checked_logits(self.classifier(self.dropout(fused)), output_size)

    def reset_classifier(self) -> None:
        if reinit_(self.classifier) != 1:
            raise RuntimeError("UPer classifier reset changed no layer")
