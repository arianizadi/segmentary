"""Explicit object-only model families, independent of semantic campaign catalogs."""

from __future__ import annotations

import json
from typing import Any, cast

from ..config import ModelConfig
from ..models.factory import build_model
from ..models.mask_classification import MaskClassWrapper

INITIALIZERS = {
    "mask2former_swin_tiny": "facebook/mask2former-swin-tiny-coco-panoptic",
    "maskformer_swin_tiny": "facebook/maskformer-swin-tiny-coco",
}


def wrap_object_model(model: Any, arch: str, num_classes: int) -> MaskClassWrapper:
    if arch not in INITIALIZERS:
        raise ValueError(f"Unsupported object family: {arch}")
    if arch == "maskformer_swin_tiny":
        # Transformers MaskFormer auxiliary decoder logits require hidden states.
        model.config.output_hidden_states = True
    return MaskClassWrapper(
        model,
        num_classes,
        backbone_paths=("model.pixel_level_module.encoder",),
        head_paths=("pixel_level_module.decoder", "transformer_module", "class_predictor")
        + (("mask_embedder",) if arch == "maskformer_swin_tiny" else ()),
        request_auxiliary_logits=True,
    )


def _loading_json(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Unexpected loading metadata type: {type(value).__name__}")


def build_object_model(config: ModelConfig, num_classes: int) -> MaskClassWrapper:
    if config.arch not in INITIALIZERS:
        return cast(MaskClassWrapper, build_model(config, num_classes))
    from transformers import Mask2FormerForUniversalSegmentation, MaskFormerForInstanceSegmentation

    if config.head != "unified_head":
        raise ValueError("Object Swin families require model.head=unified_head")
    if config.drop_path is not None:
        raise ValueError("Object Swin families do not support overriding drop_path")
    loader = (
        Mask2FormerForUniversalSegmentation
        if config.arch == "mask2former_swin_tiny"
        else MaskFormerForInstanceSegmentation
    )
    model, loading_info = cast(Any, loader).from_pretrained(
        config.checkpoint or INITIALIZERS[config.arch],
        num_labels=num_classes,
        ignore_mismatched_sizes=True,
        revision=config.revision or "main",
        subfolder=config.subfolder or "",
        local_files_only=config.local_files_only,
        use_auxiliary_loss=True,
        output_loading_info=True,
    )
    wrapper = wrap_object_model(model, config.arch, num_classes)
    cast(Any, wrapper).object_initialization = {
        "checkpoint": config.checkpoint or INITIALIZERS[config.arch],
        "requested_revision": config.revision or "main",
        "resolved_revision": getattr(model.config, "_commit_hash", None),
        "loading_info": json.loads(json.dumps(loading_info, default=_loading_json)),
    }
    return wrapper
