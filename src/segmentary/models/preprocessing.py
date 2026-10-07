"""Record the pixel normalization a hand-written built-in expects.

``data.loaders.input_normalization`` reads these four attributes from the built
model and writes them into every ``results.json``.  A built-in whose trunk comes
from timm takes the values from the pretrained configuration it actually
loaded; a train-from-scratch built-in records the ImageNet statistics the data
pipeline applies by default, under a source name that says so.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from torch import nn

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def _triplet(raw: object, *, name: str, where: str) -> tuple[float, float, float]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 3:
        raise ValueError(f"{where} pretrained_cfg {name} must contain three values, got {raw!r}")
    values = tuple(float(value) for value in raw)
    if any(not math.isfinite(value) for value in values) or (
        name == "std" and any(value <= 0.0 for value in values)
    ):
        raise ValueError(f"{where} pretrained_cfg has invalid {name}={raw!r}")
    return values  # type: ignore[return-value]


def record_preprocessing(
    target: nn.Module,
    *,
    where: str,
    pretrained_cfg: Mapping[str, Any] | None,
) -> None:
    """Attach the normalization contract to ``target``.

    Args:
        target: the ``SegmentationModel`` that the data pipeline will query.
        where: human-readable model name for error messages.
        pretrained_cfg: the timm configuration of loaded pretrained weights, or
            ``None`` for a model trained from scratch.
    """
    if pretrained_cfg is None:
        mean, std, order, source = IMAGENET_MEAN, IMAGENET_STD, "rgb", "imagenet_scratch_default"
    else:
        mean = _triplet(pretrained_cfg.get("mean"), name="mean", where=where)
        std = _triplet(pretrained_cfg.get("std"), name="std", where=where)
        order = str(pretrained_cfg.get("input_space", "RGB")).lower()
        if order not in ("rgb", "bgr"):
            raise ValueError(f"{where} uses unsupported input_space={order!r}")
        source = "timm_pretrained_cfg"
    # Plain attributes, not buffers: they describe the data pipeline and must
    # not enter state_dict, where they would break checkpoint compatibility.
    for name, value in (
        ("input_mean", mean),
        ("input_std", std),
        ("input_channel_order", order),
        ("input_normalization_source", source),
    ):
        setattr(target, name, value)
