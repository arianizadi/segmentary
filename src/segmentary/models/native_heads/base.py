"""Shared contract and validation for native dense heads."""

from __future__ import annotations

from abc import ABC, abstractmethod

import torch.nn.functional as F
from torch import Tensor, nn

from ..features import (
    FeatureMaps,
    FeatureSpec,
    checked_feature_specs,
    checked_indices,
    validate_feature_maps,
)
from ..outputs import SegmentationOutput


def resize(feature: Tensor, size: tuple[int, int]) -> Tensor:
    if tuple(feature.shape[-2:]) == tuple(size):
        return feature
    return F.interpolate(feature, size=size, mode="bilinear", align_corners=False)


class DenseHead(nn.Module, ABC):
    """Feature tuple -> raw dense logits at the requested image size."""

    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        in_indices: tuple[int, ...],
        *,
        minimum_inputs: int = 1,
    ) -> None:
        super().__init__()
        self._input_specs = checked_feature_specs(
            input_specs, where=f"{type(self).__name__} inputs"
        )
        if isinstance(num_classes, bool) or not isinstance(num_classes, int) or num_classes < 1:
            raise ValueError("native dense heads need at least one output channel")
        self.num_classes = num_classes
        self.in_indices = checked_indices(
            in_indices, self._input_specs, where=type(self).__name__, minimum=minimum_inputs
        )

    @property
    def input_specs(self) -> tuple[FeatureSpec, ...]:
        return self._input_specs

    @property
    def selected_specs(self) -> tuple[FeatureSpec, ...]:
        return tuple(self.input_specs[index] for index in self.in_indices)

    def selected_features(self, features: FeatureMaps) -> FeatureMaps:
        checked = validate_feature_maps(
            features, self.input_specs, where=f"{type(self).__name__} input"
        )
        return tuple(checked[index] for index in self.in_indices)

    @property
    def auxiliary_output_names(self) -> tuple[str, ...]:
        """Names emitted intrinsically by this head's richer training path."""

        return ()

    def checked_logits(self, logits: Tensor, output_size: tuple[int, int]) -> Tensor:
        if len(output_size) != 2 or any(size < 1 for size in output_size):
            raise ValueError(f"output_size must be a positive (H, W), got {output_size}")
        logits = resize(logits, output_size)
        if logits.ndim != 4 or logits.shape[1] != self.num_classes:
            raise ValueError(
                f"{type(self).__name__} produced {tuple(logits.shape)}, expected "
                f"(N, {self.num_classes}, H, W)"
            )
        return logits

    @abstractmethod
    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        """Return raw dense logits at ``output_size``."""

    def forward_output(
        self, features: FeatureMaps, output_size: tuple[int, int]
    ) -> SegmentationOutput:
        """Return train-time outputs while adapting ordinary one-output heads."""

        return SegmentationOutput(dense_logits=self(features, output_size))

    @abstractmethod
    def reset_classifier(self) -> None:
        """Reinitialize only class-dependent layers."""
