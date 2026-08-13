"""Lightweight reduced atrous spatial-pyramid pooling head."""

from __future__ import annotations

from torch import Tensor, nn

from ..features import FeatureMaps, FeatureSpec
from ..layers import ActivationKind, ConvNormAct, NormKind
from ..wrappers import reinit_
from .base import DenseHead, resize
from .blocks import checked_dropout


class LRASPPHead(DenseHead):
    """Fuse a cheap low-level classifier with gated high-level context.

    The deepest feature is projected once and modulated by an image-level gate.
    A direct classifier on the finer feature restores spatial detail.  Both
    class-dependent projections live under ``classifier`` so stage reset and
    optimizer ownership remain explicit.
    """

    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        *,
        low_index: int,
        high_index: int,
        channels: int = 128,
        dropout: float = 0.1,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__(input_specs, num_classes, (low_index, high_index), minimum_inputs=2)
        low_spec, high_spec = self.selected_specs
        if low_spec.reduction >= high_spec.reduction:
            raise ValueError("LR-ASPP low-level feature must precede its high-level feature")
        if channels < 1:
            raise ValueError("LR-ASPP channels must be positive")

        self.high_projection = ConvNormAct(
            high_spec.channels,
            channels,
            1,
            norm=norm,
            activation=activation,
        )
        # The gate sees a 1x1 map.  It intentionally has no BatchNorm so batch-1
        # training remains valid even when the rest of the head uses BatchNorm.
        self.high_gate = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(high_spec.channels, channels, 1),
            nn.Sigmoid(),
        )
        self.dropout = nn.Dropout2d(checked_dropout(dropout))
        self.classifier = nn.ModuleDict(
            {
                "low": nn.Conv2d(low_spec.channels, num_classes, 1),
                "high": nn.Conv2d(channels, num_classes, 1),
            }
        )

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        low, high = self.selected_features(features)
        gated_high = self.high_projection(high) * self.high_gate(high)
        high_logits = self.classifier["high"](self.dropout(gated_high))
        low_logits = self.classifier["low"](low)
        logits = low_logits + resize(high_logits, tuple(low_logits.shape[-2:]))
        return self.checked_logits(logits, output_size)

    def reset_classifier(self) -> None:
        if reinit_(self.classifier) != 2:
            raise RuntimeError("LR-ASPP classifier reset did not change both class projections")
