"""Strict feature-pyramid contracts for native segmentation components.

The existing architecture wrappers intentionally expose only final dense logits.
Native composition needs one additional boundary: a backbone must describe each
feature map before a neck or head is allowed to consume it.  The metadata here is
small on purpose.  Channels and spatial reduction are facts Segmentary can verify;
an open-ended constructor dictionary is not.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import pairwise
from typing import TypeAlias

from torch import Tensor, nn

FeatureMaps: TypeAlias = tuple[Tensor, ...]


@dataclass(frozen=True)
class FeatureSpec:
    """One NCHW feature map emitted by a backbone or neck.

    ``reduction`` is the nominal input-to-feature stride.  Odd input dimensions
    may round either up or down, so runtime validation accepts floor or ceiling
    division while still rejecting an incorrect feature level.
    """

    name: str
    channels: int
    reduction: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or self.name != self.name.strip()
        ):
            raise ValueError("feature name must be a non-empty, trimmed string")
        if (
            isinstance(self.channels, bool)
            or not isinstance(self.channels, int)
            or self.channels < 1
        ):
            raise ValueError(f"feature {self.name!r} channels must be a positive integer")
        if (
            isinstance(self.reduction, bool)
            or not isinstance(self.reduction, int)
            or self.reduction < 1
        ):
            raise ValueError(f"feature {self.name!r} reduction must be a positive integer")


def checked_feature_specs(specs: tuple[FeatureSpec, ...], *, where: str) -> tuple[FeatureSpec, ...]:
    """Validate a non-empty, uniquely named feature contract."""

    if not isinstance(specs, tuple) or not specs:
        raise ValueError(f"{where} must declare at least one feature")
    if not all(isinstance(spec, FeatureSpec) for spec in specs):
        raise TypeError(f"{where} must be a tuple of FeatureSpec values")
    names = [spec.name for spec in specs]
    if len(names) != len(set(names)):
        raise ValueError(f"{where} contains duplicate feature names: {names}")
    return specs


def checked_indices(
    indices: tuple[int, ...], specs: tuple[FeatureSpec, ...], *, where: str, minimum: int = 1
) -> tuple[int, ...]:
    """Validate an ordered selection into a feature tuple."""

    if not isinstance(indices, tuple) or len(indices) < minimum:
        raise ValueError(f"{where} needs at least {minimum} feature index/indices")
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
        raise TypeError(f"{where} feature indices must be integers")
    if tuple(sorted(set(indices))) != indices:
        raise ValueError(f"{where} feature indices must be unique and strictly increasing")
    if indices[0] < 0 or indices[-1] >= len(specs):
        raise ValueError(
            f"{where} feature indices {indices} are outside the available range 0..{len(specs) - 1}"
        )
    return indices


def require_increasing_reductions(specs: tuple[FeatureSpec, ...], *, where: str) -> None:
    """Require a genuine fine-to-coarse pyramid."""

    reductions = tuple(spec.reduction for spec in specs)
    if any(right <= left for left, right in pairwise(reductions)):
        raise ValueError(
            f"{where} needs strictly increasing feature reductions, got {reductions}. "
            "Equal-stride transformer features need an explicit pyramid-producing neck."
        )


def validate_image(image: Tensor, *, channels: int, where: str) -> None:
    """Validate the image side of the component contract."""

    if not isinstance(image, Tensor) or image.ndim != 4:
        shape = tuple(image.shape) if isinstance(image, Tensor) else type(image).__name__
        raise ValueError(f"{where} expects an NCHW Tensor, got {shape}")
    if image.shape[0] < 1 or image.shape[2] < 1 or image.shape[3] < 1:
        raise ValueError(f"{where} received an empty image dimension: {tuple(image.shape)}")
    if image.shape[1] != channels:
        raise ValueError(
            f"{where} expects {channels} input channels, got image shape {tuple(image.shape)}"
        )


def validate_feature_maps(
    features: tuple[Tensor, ...] | list[Tensor],
    specs: tuple[FeatureSpec, ...],
    *,
    where: str,
    batch_size: int | None = None,
    input_size: tuple[int, int] | None = None,
) -> FeatureMaps:
    """Prove that runtime tensors satisfy a declared feature contract."""

    checked_feature_specs(specs, where=f"{where} specs")
    if not isinstance(features, (tuple, list)):
        raise TypeError(f"{where} must return a tuple/list of feature tensors")
    if len(features) != len(specs):
        raise ValueError(f"{where} returned {len(features)} features, expected {len(specs)}")

    out: list[Tensor] = []
    observed_batch = batch_size
    for index, (feature, spec) in enumerate(zip(features, specs, strict=True)):
        if not isinstance(feature, Tensor) or feature.ndim != 4:
            shape = tuple(feature.shape) if isinstance(feature, Tensor) else type(feature).__name__
            raise ValueError(f"{where}[{index}] ({spec.name}) must be NCHW, got {shape}")
        if observed_batch is None:
            observed_batch = int(feature.shape[0])
        if feature.shape[0] != observed_batch:
            raise ValueError(
                f"{where}[{index}] ({spec.name}) batch {feature.shape[0]} != {observed_batch}"
            )
        if feature.shape[1] != spec.channels:
            raise ValueError(
                f"{where}[{index}] ({spec.name}) has {feature.shape[1]} channels, "
                f"declared {spec.channels}"
            )
        if feature.shape[2] < 1 or feature.shape[3] < 1:
            raise ValueError(f"{where}[{index}] ({spec.name}) has an empty spatial dimension")

        if input_size is not None:
            for axis, full, actual in (
                ("height", input_size[0], int(feature.shape[2])),
                ("width", input_size[1], int(feature.shape[3])),
            ):
                floor = max(1, full // spec.reduction)
                ceil = max(1, math.ceil(full / spec.reduction))
                if actual not in {floor, ceil}:
                    raise ValueError(
                        f"{where}[{index}] ({spec.name}) {axis}={actual} is inconsistent "
                        f"with input {full} and declared reduction {spec.reduction}; "
                        f"expected {floor} or {ceil}"
                    )
        out.append(feature)
    return tuple(out)


class FeatureBackbone(nn.Module, ABC):
    """Backbone protocol: image -> an explicitly described feature tuple."""

    input_channels: int

    @property
    @abstractmethod
    def output_specs(self) -> tuple[FeatureSpec, ...]:
        """The exact feature tuple returned by :meth:`forward_features`."""

    @abstractmethod
    def forward_features(self, image: Tensor) -> FeatureMaps:
        """Return NCHW features in the same order as ``output_specs``."""

    def forward(self, image: Tensor) -> FeatureMaps:
        return self.forward_features(image)


class FeatureNeck(nn.Module, ABC):
    """Neck protocol: a validated feature tuple -> another feature tuple."""

    @property
    @abstractmethod
    def input_specs(self) -> tuple[FeatureSpec, ...]:
        """Feature contract accepted by the neck."""

    @property
    @abstractmethod
    def output_specs(self) -> tuple[FeatureSpec, ...]:
        """Feature contract emitted by the neck."""

    @abstractmethod
    def forward(self, features: FeatureMaps) -> FeatureMaps:
        """Transform one feature tuple into another."""
