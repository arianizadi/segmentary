"""Pyramid scene-parsing head."""

from __future__ import annotations

from torch import Tensor, nn

from ..features import FeatureMaps, FeatureSpec
from ..layers import ActivationKind, ConvNormAct, NormKind
from ..wrappers import reinit_
from .base import DenseHead
from .blocks import PyramidPooling, checked_bins, checked_dropout


class PSPHead(DenseHead):
    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        *,
        in_index: int,
        channels: int,
        pool_bins: tuple[int, ...] = (1, 2, 3, 6),
        dropout: float = 0.1,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__(input_specs, num_classes, (in_index,))
        if channels < 1:
            raise ValueError("PSP channels must be positive")
        pool_bins = checked_bins(pool_bins)
        in_channels = self.selected_specs[0].channels
        branch_channels = max(1, in_channels // len(pool_bins))
        self.pool = PyramidPooling(
            in_channels,
            pool_bins,
            branch_channels=branch_channels,
            norm=norm,
            activation=activation,
        )
        self.bottleneck = ConvNormAct(
            self.pool.out_channels, channels, 3, norm=norm, activation=activation
        )
        self.dropout = nn.Dropout2d(checked_dropout(dropout))
        self.classifier = nn.Conv2d(channels, num_classes, 1)

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        (feature,) = self.selected_features(features)
        logits = self.classifier(self.dropout(self.bottleneck(self.pool(feature))))
        return self.checked_logits(logits, output_size)

    def reset_classifier(self) -> None:
        if reinit_(self.classifier) != 1:
            raise RuntimeError("PSP classifier reset changed no layer")
