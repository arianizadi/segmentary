"""No-op neck used when a backbone already exposes the required feature maps."""

from __future__ import annotations

from ..features import (
    FeatureMaps,
    FeatureNeck,
    FeatureSpec,
    checked_feature_specs,
    validate_feature_maps,
)


class IdentityNeck(FeatureNeck):
    def __init__(self, input_specs: tuple[FeatureSpec, ...]) -> None:
        super().__init__()
        self._input_specs = checked_feature_specs(input_specs, where="identity neck inputs")

    @property
    def input_specs(self) -> tuple[FeatureSpec, ...]:
        return self._input_specs

    @property
    def output_specs(self) -> tuple[FeatureSpec, ...]:
        return self._input_specs

    def forward(self, features: FeatureMaps) -> FeatureMaps:
        return validate_feature_maps(features, self.input_specs, where="identity neck input")
