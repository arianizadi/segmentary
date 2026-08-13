"""DeepLabV3+ context and low-level boundary-refinement head."""

from __future__ import annotations

import torch
from torch import Tensor, nn

from ..features import FeatureMaps, FeatureSpec
from ..layers import ActivationKind, ConvNormAct, NormKind
from ..wrappers import reinit_
from .base import DenseHead, resize
from .blocks import ASPP, checked_dropout


class DeepLabV3PlusHead(DenseHead):
    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        *,
        low_index: int,
        high_index: int,
        channels: int,
        low_channels: int = 48,
        dilation_rates: tuple[int, ...] = (6, 12, 18),
        dropout: float = 0.1,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__(input_specs, num_classes, (low_index, high_index), minimum_inputs=2)
        low_spec, high_spec = self.selected_specs
        if low_spec.reduction >= high_spec.reduction:
            raise ValueError(
                "DeepLabV3+ low-level feature must have a smaller reduction than high-level"
            )
        if channels < 1 or low_channels < 1:
            raise ValueError("DeepLabV3+ channel counts must be positive")
        self.aspp = ASPP(
            high_spec.channels,
            channels,
            dilation_rates,
            norm=norm,
            activation=activation,
        )
        self.low_projection = ConvNormAct(
            low_spec.channels, low_channels, 1, norm=norm, activation=activation
        )
        self.decoder = nn.Sequential(
            ConvNormAct(
                channels + low_channels,
                channels,
                3,
                norm=norm,
                activation=activation,
            ),
            ConvNormAct(channels, channels, 3, norm=norm, activation=activation),
            nn.Dropout2d(checked_dropout(dropout)),
        )
        self.classifier = nn.Conv2d(channels, num_classes, 1)

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        low, high = self.selected_features(features)
        low = self.low_projection(low)
        context = resize(self.aspp(high), tuple(low.shape[-2:]))
        logits = self.classifier(self.decoder(torch.cat((low, context), dim=1)))
        return self.checked_logits(logits, output_size)

    def reset_classifier(self) -> None:
        if reinit_(self.classifier) != 1:
            raise RuntimeError("DeepLabV3+ classifier reset changed no layer")
