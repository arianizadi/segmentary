"""A compact convolutional head with optional multi-level concatenation."""

from __future__ import annotations

import torch
from torch import Tensor, nn

from ..features import FeatureMaps, FeatureSpec
from ..layers import ActivationKind, ConvNormAct, NormKind
from ..wrappers import reinit_
from .base import DenseHead, resize
from .blocks import checked_dropout


class FCNHead(DenseHead):
    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        *,
        in_indices: tuple[int, ...],
        channels: int,
        num_convs: int = 2,
        kernel_size: int = 3,
        dilation: int = 1,
        dropout: float = 0.1,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__(input_specs, num_classes, in_indices)
        if channels < 1 or num_convs < 1:
            raise ValueError("FCN channels and num_convs must be positive")
        in_channels = sum(spec.channels for spec in self.selected_specs)
        layers: list[nn.Module] = []
        for index in range(num_convs):
            layers.append(
                ConvNormAct(
                    in_channels if index == 0 else channels,
                    channels,
                    kernel_size,
                    dilation=dilation,
                    norm=norm,
                    activation=activation,
                )
            )
        self.convs = nn.Sequential(*layers)
        self.dropout = nn.Dropout2d(checked_dropout(dropout))
        self.classifier = nn.Conv2d(channels, num_classes, 1)

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        selected = self.selected_features(features)
        fusion_size = tuple(selected[0].shape[-2:])
        fused = torch.cat([resize(feature, fusion_size) for feature in selected], dim=1)
        return self.checked_logits(self.classifier(self.dropout(self.convs(fused))), output_size)

    def reset_classifier(self) -> None:
        if reinit_(self.classifier) != 1:
            raise RuntimeError("FCN classifier reset changed no layer")
