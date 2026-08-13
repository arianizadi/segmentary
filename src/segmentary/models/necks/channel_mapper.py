"""Independent channel projection for a validated feature tuple."""

from __future__ import annotations

from torch import nn

from ..features import (
    FeatureMaps,
    FeatureNeck,
    FeatureSpec,
    checked_feature_specs,
    validate_feature_maps,
)
from ..layers import ActivationKind, ConvNormAct, NormKind


class ChannelMapper(FeatureNeck):
    """Map every feature level to one width without cross-level fusion.

    The separation is intentional: a downstream head can own the aggregation
    strategy, while this neck owns only per-level channel normalization and any
    requested extra coarse levels.
    """

    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        *,
        out_channels: int,
        kernel_size: int = 1,
        num_outputs: int | None = None,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__()
        self._input_specs = checked_feature_specs(input_specs, where="ChannelMapper inputs")
        if isinstance(out_channels, bool) or not isinstance(out_channels, int) or out_channels < 1:
            raise ValueError("ChannelMapper out_channels must be a positive integer")
        if (
            isinstance(kernel_size, bool)
            or not isinstance(kernel_size, int)
            or kernel_size < 1
            or kernel_size % 2 == 0
        ):
            raise ValueError("ChannelMapper kernel_size must be a positive odd integer")
        if num_outputs is None:
            num_outputs = len(self._input_specs)
        if (
            isinstance(num_outputs, bool)
            or not isinstance(num_outputs, int)
            or num_outputs < len(self._input_specs)
        ):
            raise ValueError(
                f"ChannelMapper num_outputs must be at least its "
                f"{len(self._input_specs)} input levels"
            )

        self.out_channels = out_channels
        self.kernel_size = kernel_size
        self.num_outputs = num_outputs
        self.mappers = nn.ModuleList(
            ConvNormAct(
                spec.channels,
                out_channels,
                kernel_size,
                norm=norm,
                activation=activation,
            )
            for spec in self._input_specs
        )
        self.extra_levels = nn.ModuleList(
            ConvNormAct(
                out_channels,
                out_channels,
                3,
                stride=2,
                norm=norm,
                activation=activation,
            )
            for _ in range(num_outputs - len(self._input_specs))
        )

        reductions = [spec.reduction for spec in self._input_specs]
        while len(reductions) < num_outputs:
            reductions.append(reductions[-1] * 2)
        self._output_specs = checked_feature_specs(
            tuple(
                FeatureSpec(f"channel_mapper_{index}", out_channels, reduction)
                for index, reduction in enumerate(reductions)
            ),
            where="ChannelMapper outputs",
        )

    @property
    def input_specs(self) -> tuple[FeatureSpec, ...]:
        return self._input_specs

    @property
    def output_specs(self) -> tuple[FeatureSpec, ...]:
        return self._output_specs

    def forward(self, features: FeatureMaps) -> FeatureMaps:
        checked = validate_feature_maps(features, self.input_specs, where="ChannelMapper input")
        outputs = [mapper(feature) for mapper, feature in zip(self.mappers, checked, strict=True)]
        for extra in self.extra_levels:
            outputs.append(extra(outputs[-1]))
        return validate_feature_maps(
            tuple(outputs), self.output_specs, where="ChannelMapper output"
        )
