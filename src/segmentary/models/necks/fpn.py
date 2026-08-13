"""A native top-down feature pyramid neck."""

from __future__ import annotations

import torch.nn.functional as F
from torch import nn

from ..features import (
    FeatureMaps,
    FeatureNeck,
    FeatureSpec,
    checked_feature_specs,
    require_increasing_reductions,
    validate_feature_maps,
)
from ..layers import ActivationKind, ConvNormAct, NormKind


class FPNNeck(FeatureNeck):
    """Project, merge top-down, and smooth a fine-to-coarse feature hierarchy."""

    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        *,
        out_channels: int,
        num_outputs: int | None = None,
        norm: NormKind = "none",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__()
        self._input_specs = checked_feature_specs(input_specs, where="FPN inputs")
        if len(self._input_specs) < 2:
            raise ValueError("FPN needs at least two feature levels")
        require_increasing_reductions(self._input_specs, where="FPN")
        if isinstance(out_channels, bool) or not isinstance(out_channels, int) or out_channels < 1:
            raise ValueError("FPN out_channels must be a positive integer")
        if num_outputs is None:
            num_outputs = len(self._input_specs)
        if (
            isinstance(num_outputs, bool)
            or not isinstance(num_outputs, int)
            or num_outputs < len(self._input_specs)
        ):
            raise ValueError(
                f"FPN num_outputs must be at least its {len(self._input_specs)} input levels"
            )
        self.out_channels = out_channels
        self.num_outputs = num_outputs
        self.lateral = nn.ModuleList(
            nn.Conv2d(spec.channels, out_channels, 1) for spec in self._input_specs
        )
        self.smooth = nn.ModuleList(
            ConvNormAct(
                out_channels,
                out_channels,
                3,
                norm=norm,
                activation=activation,
            )
            for _ in self._input_specs
        )

        reductions = [spec.reduction for spec in self._input_specs]
        while len(reductions) < num_outputs:
            reductions.append(reductions[-1] * 2)
        self._output_specs = checked_feature_specs(
            tuple(
                FeatureSpec(f"fpn_{index}", out_channels, reduction)
                for index, reduction in enumerate(reductions)
            ),
            where="FPN outputs",
        )

    @property
    def input_specs(self) -> tuple[FeatureSpec, ...]:
        return self._input_specs

    @property
    def output_specs(self) -> tuple[FeatureSpec, ...]:
        return self._output_specs

    def forward(self, features: FeatureMaps) -> FeatureMaps:
        checked = validate_feature_maps(features, self.input_specs, where="FPN input")
        laterals = [layer(feature) for layer, feature in zip(self.lateral, checked, strict=True)]
        for index in range(len(laterals) - 2, -1, -1):
            laterals[index] = laterals[index] + F.interpolate(
                laterals[index + 1],
                size=tuple(laterals[index].shape[-2:]),
                mode="nearest",
            )
        outputs = [layer(feature) for layer, feature in zip(self.smooth, laterals, strict=True)]
        while len(outputs) < self.num_outputs:
            outputs.append(F.max_pool2d(outputs[-1], kernel_size=1, stride=2))
        return validate_feature_maps(tuple(outputs), self.output_specs, where="FPN output")
