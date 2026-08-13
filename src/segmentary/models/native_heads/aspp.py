"""Atrous spatial-pyramid pooling head."""

from __future__ import annotations

from torch import Tensor, nn

from ..features import FeatureMaps, FeatureSpec
from ..layers import ActivationKind, NormKind
from ..wrappers import reinit_
from .base import DenseHead
from .blocks import ASPP, checked_dropout


class ASPPHead(DenseHead):
    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        *,
        in_index: int,
        channels: int,
        dilation_rates: tuple[int, ...] = (6, 12, 18),
        dropout: float = 0.1,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__(input_specs, num_classes, (in_index,))
        if channels < 1:
            raise ValueError("ASPP channels must be positive")
        self.aspp = ASPP(
            self.selected_specs[0].channels,
            channels,
            dilation_rates,
            norm=norm,
            activation=activation,
        )
        self.dropout = nn.Dropout2d(checked_dropout(dropout))
        self.classifier = nn.Conv2d(channels, num_classes, 1)

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        (feature,) = self.selected_features(features)
        return self.checked_logits(self.classifier(self.dropout(self.aspp(feature))), output_size)

    def reset_classifier(self) -> None:
        if reinit_(self.classifier) != 1:
            raise RuntimeError("ASPP classifier reset changed no layer")
