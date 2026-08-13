"""SegFormer-style all-MLP multi-level fusion head."""

from __future__ import annotations

import torch
from torch import Tensor, nn

from ..features import FeatureMaps, FeatureSpec
from ..layers import ActivationKind, ConvNormAct, NormKind
from ..wrappers import reinit_
from .base import DenseHead, resize
from .blocks import checked_dropout


class SegFormerMLPHead(DenseHead):
    """Project every feature independently, resize, concatenate, and fuse."""

    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        *,
        in_indices: tuple[int, ...],
        channels: int,
        dropout: float = 0.1,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__(input_specs, num_classes, in_indices, minimum_inputs=2)
        if channels < 1:
            raise ValueError("SegFormer head channels must be positive")
        self.projections = nn.ModuleList(
            nn.Conv2d(spec.channels, channels, 1) for spec in self.selected_specs
        )
        self.fuse = ConvNormAct(
            len(self.selected_specs) * channels,
            channels,
            1,
            norm=norm,
            activation=activation,
        )
        self.dropout = nn.Dropout2d(checked_dropout(dropout))
        self.classifier = nn.Conv2d(channels, num_classes, 1)

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        selected = self.selected_features(features)
        fusion_size = tuple(selected[0].shape[-2:])
        projected = [
            resize(layer(feature), fusion_size)
            for layer, feature in zip(self.projections, selected, strict=True)
        ]
        fused = self.fuse(torch.cat(projected, dim=1))
        return self.checked_logits(self.classifier(self.dropout(fused)), output_size)

    def reset_classifier(self) -> None:
        if reinit_(self.classifier) != 1:
            raise RuntimeError("SegFormer classifier reset changed no layer")
