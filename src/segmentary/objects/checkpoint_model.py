"""Reconstruct supported query architectures from checkpoint metadata, offline.

The complete weights are loaded separately with ``load_state_dict(strict=True)``.
Only explicitly supported Transformers constructors are used: architecture
names or remote code in a checkpoint can never trigger an automatic loader.
"""

from __future__ import annotations

import json
from typing import Any, cast

from ..config import ModelConfig
from ..models.mask_classification import MaskClassWrapper
from ..models.tuning import apply_tuning

_SCHEMA = "segmentary-object-model-v1"


def _implementations() -> dict[str, tuple[type[Any], type[Any]]]:
    from transformers import (
        EomtConfig,
        EomtDinov3Config,
        EomtDinov3ForUniversalSegmentation,
        EomtForUniversalSegmentation,
    )

    return {
        "eomt_large": (EomtConfig, EomtForUniversalSegmentation),
        "eomt_dinov3_large": (EomtDinov3Config, EomtDinov3ForUniversalSegmentation),
    }


def model_spec(model: MaskClassWrapper) -> dict[str, Any]:
    """Capture architecture and wrapper layout, including after LoRA injection.

    Segmentary injects LoRA modules in place, preserving the upstream model type
    and its Hugging Face config. Adapter weights and classifier modules live in
    the ordinary state dict; ``restore_model`` reapplies the recorded tuning
    configuration before that state dict is restored.
    """
    if not isinstance(model, MaskClassWrapper):
        raise TypeError("Object checkpoint architecture requires MaskClassWrapper")
    supported = {model_type for _, model_type in _implementations().values()}
    if type(model.model) not in supported:
        raise ValueError(f"Unsupported object checkpoint model type: {type(model.model).__name__}")
    # JSON round-trip ensures the metadata contains plain portable values, not
    # arbitrary Python objects requiring unsafe torch.load deserialization.
    upstream_config = cast(Any, model.model).config
    config = json.loads(json.dumps(upstream_config.to_dict(), allow_nan=False))
    if upstream_config.num_labels != model.num_classes:
        raise ValueError("Upstream configuration and wrapper disagree on class count")
    return {
        "schema": _SCHEMA,
        "model_class": type(model.model).__name__,
        "num_classes": model.num_classes,
        "hf_config": config,
        "wrapper": {
            "backbone_paths": list(model.backbone_paths),
            "head_paths": list(model.head_paths),
            "native_size": list(model.native_size) if model.native_size is not None else None,
            "classifier_component": model.classifier_component,
            "request_auxiliary_logits": model.request_auxiliary_logits,
        },
    }


def _paths(value: Any, name: str) -> tuple[str, ...]:
    if (
        not isinstance(value, (list, tuple))
        or not value
        or any(
            not isinstance(path, str)
            or not path
            or path != path.strip()
            or any(not component for component in path.split("."))
            for path in value
        )
    ):
        raise ValueError(f"Checkpoint wrapper {name} must contain nonempty module paths")
    return tuple(value)


def restore_model(
    spec: dict[str, Any], model_cfg: ModelConfig, num_classes: int
) -> MaskClassWrapper:
    """Create an uninitialized-weight architecture without contacting the Hub.

    The caller must load the checkpoint state dict strictly before using the
    model. The original initialization checkpoint path is deliberately unused.
    Full, frozen-backbone, and LoRA tuning all recreate the same parameter names
    and trainability as the original model.
    """
    if not isinstance(spec, dict) or spec.get("schema") != _SCHEMA:
        raise ValueError("Unsupported object checkpoint model schema")
    implementations = _implementations()
    if model_cfg.arch not in implementations:
        raise ValueError(f"Unsupported object checkpoint architecture: {model_cfg.arch}")
    config_type, model_type = implementations[model_cfg.arch]
    if spec.get("model_class") != model_type.__name__:
        raise ValueError("Checkpoint model type differs from configured architecture")
    if (
        type(num_classes) is not int
        or num_classes < 1
        or type(spec.get("num_classes")) is not int
        or spec["num_classes"] != num_classes
    ):
        raise ValueError("Checkpoint architecture class count differs from categories")
    saved_config = spec.get("hf_config")
    if (
        not isinstance(saved_config, dict)
        or saved_config.get("model_type") != config_type.model_type
    ):
        raise ValueError("Checkpoint Hugging Face configuration has the wrong model type")
    config = config_type.from_dict(saved_config)
    if config.num_labels != num_classes:
        raise ValueError("Checkpoint Hugging Face class count differs from categories")
    wrapper = spec.get("wrapper")
    if not isinstance(wrapper, dict):
        raise ValueError("Checkpoint is missing wrapper configuration")
    backbone_paths = _paths(wrapper.get("backbone_paths"), "backbone_paths")
    head_paths = _paths(wrapper.get("head_paths"), "head_paths")
    classifier = wrapper.get("classifier_component")
    if not isinstance(classifier, str) or not classifier or classifier != classifier.strip():
        raise ValueError("Checkpoint classifier_component must be a nonempty string")
    auxiliary = wrapper.get("request_auxiliary_logits")
    if type(auxiliary) is not bool:
        raise ValueError("Checkpoint request_auxiliary_logits must be boolean")
    size = wrapper.get("native_size")
    if size is not None and (
        not isinstance(size, (list, tuple))
        or len(size) != 2
        or any(type(dimension) is not int or dimension < 1 for dimension in size)
    ):
        raise ValueError("Checkpoint native_size must be null or positive [height, width]")
    native_size = (size[0], size[1]) if size is not None else None
    upstream = model_type(config)
    if native_size is not None:
        patch = config.patch_size
        expected = tuple(dimension * patch for dimension in upstream.grid_size)
        if native_size != expected:
            raise ValueError("Checkpoint native_size differs from the model's fixed token grid")
    model = MaskClassWrapper(
        upstream,
        num_classes,
        backbone_paths=backbone_paths,
        head_paths=head_paths,
        native_size=native_size,
        classifier_component=classifier,
        request_auxiliary_logits=auxiliary,
    )
    apply_tuning(model, model_cfg)
    return model
