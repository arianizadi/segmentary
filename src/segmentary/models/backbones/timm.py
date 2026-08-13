"""A fail-closed adapter for timm's ``features_only`` interface."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import timm
from torch import Tensor

from ..features import (
    FeatureBackbone,
    FeatureMaps,
    FeatureSpec,
    checked_feature_specs,
    validate_feature_maps,
    validate_image,
)


def _positive_indices(indices: tuple[int, ...]) -> tuple[int, ...]:
    if not isinstance(indices, tuple) or not indices:
        raise ValueError("timm out_indices must be a non-empty tuple")
    if any(isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in indices):
        raise ValueError("timm out_indices must contain non-negative integers")
    if tuple(sorted(set(indices))) != indices:
        raise ValueError("timm out_indices must be unique and strictly increasing")
    return indices


def _triplet(value: object, *, name: str) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"timm pretrained_cfg {name} must contain three values, got {value!r}")
    return tuple(float(item) for item in value)  # type: ignore[return-value]


class TimmBackbone(FeatureBackbone):
    """Expose a timm model only after its real feature metadata is available.

    The adapter deliberately exposes no arbitrary model kwargs.  timm models do
    not share one constructor surface, and several accept unknown keyword
    arguments without applying them.  A family-specific adapter can add a typed
    option later together with an effect test.
    """

    def __init__(
        self,
        name: str,
        *,
        pretrained: bool,
        out_indices: tuple[int, ...] = (0, 1, 2, 3),
        input_channels: int = 3,
    ) -> None:
        super().__init__()
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            raise ValueError("timm backbone name must be a non-empty, trimmed string")
        if not isinstance(pretrained, bool):
            raise TypeError("timm pretrained must be bool")
        if (
            isinstance(input_channels, bool)
            or not isinstance(input_channels, int)
            or input_channels < 1
        ):
            raise ValueError("timm input_channels must be a positive integer")
        if input_channels != 3:
            raise ValueError(
                f"timm backbone {name!r} requests {input_channels} input channels, but "
                "Segmentary's public image pipeline currently emits RGB tensors"
            )
        out_indices = _positive_indices(out_indices)

        self.name = name
        self.pretrained = pretrained
        self.out_indices = out_indices
        self.input_channels = input_channels
        try:
            self.model = timm.create_model(
                name,
                pretrained=pretrained,
                features_only=True,
                out_indices=out_indices,
                in_chans=input_channels,
            )
        except Exception as exc:
            source = "pretrained weights" if pretrained else "scratch initialization"
            raise ValueError(
                f"could not construct timm backbone {name!r} with {source}, "
                f"out_indices={out_indices}, in_chans={input_channels}: {exc}"
            ) from exc

        info = getattr(self.model, "feature_info", None)
        if info is None or not all(hasattr(info, method) for method in ("channels", "reduction")):
            raise ValueError(f"timm backbone {name!r} exposes no usable feature_info")
        channels = tuple(int(value) for value in info.channels())
        reductions = tuple(int(value) for value in info.reduction())
        if len(channels) != len(out_indices) or len(reductions) != len(out_indices):
            raise ValueError(
                f"timm backbone {name!r} reported {len(channels)} feature levels for "
                f"{len(out_indices)} requested indices"
            )

        dictionaries: list[Mapping[str, Any]] = []
        get_dicts = getattr(info, "get_dicts", None)
        if callable(get_dicts):
            raw = get_dicts()
            if isinstance(raw, list) and all(isinstance(item, Mapping) for item in raw):
                dictionaries = raw
        names = [
            str(dictionaries[index].get("module") or f"feature_{source_index}")
            if index < len(dictionaries)
            else f"feature_{source_index}"
            for index, source_index in enumerate(out_indices)
        ]
        self._output_specs = checked_feature_specs(
            tuple(
                FeatureSpec(feature_name, channel_count, reduction)
                for feature_name, channel_count, reduction in zip(
                    names, channels, reductions, strict=True
                )
            ),
            where=f"timm backbone {name!r}",
        )

        raw_format = str(getattr(self.model, "output_fmt", "NCHW"))
        self._output_format = raw_format.rsplit(".", 1)[-1].upper()
        if self._output_format not in ("NCHW", "NHWC"):
            raise ValueError(
                f"timm backbone {name!r} reports unsupported feature format "
                f"{raw_format!r}; only NCHW/NHWC maps can feed dense heads"
            )

        pretrained_cfg = getattr(self.model, "pretrained_cfg", None)
        self.pretrained_cfg = dict(pretrained_cfg) if isinstance(pretrained_cfg, Mapping) else {}
        mean = _triplet(self.pretrained_cfg.get("mean"), name="mean")
        std = _triplet(self.pretrained_cfg.get("std"), name="std")
        if pretrained:
            if mean is None or std is None:
                raise ValueError(
                    f"pretrained timm backbone {name!r} exposes no complete mean/std "
                    "processor contract; Segmentary will not guess its input distribution"
                )
            if any(value <= 0.0 for value in std):
                raise ValueError(f"pretrained timm backbone {name!r} has non-positive std={std!r}")
            self.input_mean = mean
            self.input_std = std
            space = str(self.pretrained_cfg.get("input_space", "RGB")).lower()
            if space not in ("rgb", "bgr"):
                raise ValueError(f"timm backbone {name!r} uses unsupported input_space={space!r}")
            self.input_channel_order = space
            self.input_normalization_source = "timm_pretrained_cfg"
        else:
            self.input_mean = (0.485, 0.456, 0.406)
            self.input_std = (0.229, 0.224, 0.225)
            self.input_channel_order = "rgb"
            self.input_normalization_source = "imagenet_scratch_default"

    @property
    def output_specs(self) -> tuple[FeatureSpec, ...]:
        return self._output_specs

    def forward_features(self, image: Tensor) -> FeatureMaps:
        validate_image(image, channels=self.input_channels, where=f"timm backbone {self.name!r}")
        try:
            raw = self.model(image)
        except Exception as exc:
            raise ValueError(
                f"timm backbone {self.name!r} rejected input {tuple(image.shape)}: {exc}. "
                "The model may require a fixed image size or a larger minimum crop; "
                "probe the exact recipe before training."
            ) from exc
        if not isinstance(raw, (tuple, list)):
            raise ValueError(
                f"timm backbone {self.name!r} returned {type(raw).__name__}, "
                "expected a feature list"
            )
        if self._output_format == "NHWC":
            converted = tuple(item.permute(0, 3, 1, 2).contiguous() for item in raw)
        else:
            converted = tuple(raw)
        return validate_feature_maps(
            converted,
            self.output_specs,
            where=f"timm backbone {self.name!r}",
            batch_size=int(image.shape[0]),
            input_size=(int(image.shape[2]), int(image.shape[3])),
        )
