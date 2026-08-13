"""Strict schema tests for Segmentary's native component composition."""

from __future__ import annotations

from typing import Any

import pytest

from segmentary.config import (
    ASPPHeadSpec,
    AuxiliaryHeadSpec,
    ChannelMapperNeckSpec,
    ConfigError,
    DeepLabV3PlusHeadSpec,
    DPTHeadSpec,
    ExperimentConfig,
    FCNHeadSpec,
    FPNNeckSpec,
    IdentityNeckSpec,
    LRASPPHeadSpec,
    ModelConfig,
    NativeModelSpec,
    OCRHeadSpec,
    PSPHeadSpec,
    SegFormerHeadSpec,
    TimmBackboneSpec,
    UPerHeadSpec,
    from_dict,
)


def _experiment(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "native-test",
        "space": "example",
        "model": model,
        "stages": [
            {
                "name": "train",
                "data": [{"name": "example", "root": "data/example"}],
            }
        ],
    }


def test_native_schema_recursively_coerces_every_nested_component() -> None:
    cfg = from_dict(
        ExperimentConfig,
        _experiment(
            {
                "arch": "native",
                "native": {
                    "task": "multiclass",
                    "backbone": {
                        "kind": "timm",
                        "name": "resnet18",
                        "weights": "scratch",
                        "out_indices": [0, 1, 2, 3],
                    },
                    "neck": {
                        "kind": "fpn",
                        "out_channels": 64,
                        "num_outputs": 4,
                        "norm": "group",
                        "activation": "silu",
                    },
                    "head": {
                        "kind": "deeplabv3plus",
                        "low_index": 0,
                        "high_index": 3,
                        "channels": 64,
                        "low_channels": 24,
                        "dilation_rates": [2, 4, 6],
                    },
                    "auxiliary_heads": [
                        {
                            "name": "aux_s16",
                            "loss_weight": 0.4,
                            "head": {
                                "kind": "fcn",
                                "in_indices": [2],
                                "channels": 32,
                            },
                        }
                    ],
                },
            }
        ),
    )

    assert cfg.model.native is not None
    assert isinstance(cfg.model.native.backbone, TimmBackboneSpec)
    assert cfg.model.native.backbone.out_indices == (0, 1, 2, 3)
    assert isinstance(cfg.model.native.neck, FPNNeckSpec)
    assert isinstance(cfg.model.native.head, DeepLabV3PlusHeadSpec)
    assert cfg.model.native.head.dilation_rates == (2, 4, 6)
    assert isinstance(cfg.model.native.auxiliary_heads[0].head, FCNHeadSpec)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"kind": "fcn", "in_indices": [3]}, FCNHeadSpec),
        ({"kind": "segformer", "in_indices": [0, 1]}, SegFormerHeadSpec),
        ({"kind": "psp", "in_index": 3}, PSPHeadSpec),
        ({"kind": "aspp", "in_index": 3}, ASPPHeadSpec),
        (
            {"kind": "deeplabv3plus", "low_index": 0, "high_index": 3},
            DeepLabV3PlusHeadSpec,
        ),
        ({"kind": "uper", "in_indices": [0, 1]}, UPerHeadSpec),
        ({"kind": "dpt", "in_indices": [0, 1, 2, 3]}, DPTHeadSpec),
        (
            {
                "kind": "ocr",
                "in_indices": [0, 1, 2, 3],
                "channels": 512,
                "key_channels": 256,
                "attention_scale": 2,
                "coarse_loss_weight": 0.4,
            },
            OCRHeadSpec,
        ),
    ],
)
def test_every_native_head_has_a_tagged_typed_yaml_arm(
    raw: dict[str, Any], expected: type[Any]
) -> None:
    spec = from_dict(NativeModelSpec, {"head": raw})
    assert isinstance(spec.head, expected)


@pytest.mark.parametrize(
    "neck",
    [
        {"kind": "identity"},
        {"kind": "fpn"},
        {
            "kind": "channel_mapper",
            "out_channels": 96,
            "kernel_size": 3,
            "num_outputs": 5,
        },
    ],
)
def test_every_native_neck_has_a_tagged_typed_yaml_arm(neck: dict[str, Any]) -> None:
    spec = from_dict(NativeModelSpec, {"neck": neck})
    assert isinstance(spec.neck, (IdentityNeckSpec, FPNNeckSpec, ChannelMapperNeckSpec))


def test_unknown_nested_native_key_is_fatal_with_a_dotted_path() -> None:
    raw = _experiment(
        {
            "arch": "native",
            "native": {"head": {"kind": "fcn", "in_indices": [3], "dropuot": 0.2}},
        }
    )
    with pytest.raises(ConfigError) as caught:
        from_dict(ExperimentConfig, raw)
    assert "model.native.head" in str(caught.value)
    assert "dropuot" in str(caught.value)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "model.native is required"),
        ({"checkpoint": "model.ckpt"}, "checkpoint is not used"),
        ({"drop_path": 0.1}, "not a verified generic native-backbone option"),
    ],
)
def test_native_arch_requires_an_unambiguous_native_construction(
    kwargs: dict[str, Any], message: str
) -> None:
    native = None if not kwargs else NativeModelSpec()
    with pytest.raises(ConfigError, match=message):
        ModelConfig(arch="native", native=native, **kwargs)


def test_native_fields_are_rejected_by_legacy_architectures() -> None:
    with pytest.raises(ConfigError, match="applies only to arch='native'"):
        ModelConfig(arch="segformer_b0", native=NativeModelSpec())


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TimmBackboneSpec(weights="mystery"),
        lambda: TimmBackboneSpec(out_indices=(2, 1)),
        lambda: TimmBackboneSpec(out_indices=(1, 1)),
        lambda: FPNNeckSpec(norm="made_up"),
        lambda: FPNNeckSpec(activation="swish"),
        lambda: ChannelMapperNeckSpec(kernel_size=2),
        lambda: ChannelMapperNeckSpec(out_channels=0),
        lambda: FCNHeadSpec(kernel_size=2),
        lambda: FCNHeadSpec(dropout=float("nan")),
        lambda: PSPHeadSpec(pool_bins=(1, 1)),
        lambda: DeepLabV3PlusHeadSpec(low_index=3, high_index=0),
        lambda: LRASPPHeadSpec(low_index=3, high_index=0),
        lambda: DPTHeadSpec(in_indices=(0, 1, 2)),
        lambda: DPTHeadSpec(in_indices=(0, 1, 2, 3, 4)),
        lambda: OCRHeadSpec(key_channels=0),
        lambda: OCRHeadSpec(attention_scale=0),
        lambda: OCRHeadSpec(coarse_loss_weight=0.0),
        lambda: OCRHeadSpec(coarse_loss_weight=float("inf")),
        lambda: TimmBackboneSpec(in_channels=1),
    ],
)
def test_direct_native_construction_rejects_invalid_values(factory: Any) -> None:
    with pytest.raises(ConfigError):
        factory()


def test_native_binary_task_is_an_explicit_typed_choice() -> None:
    assert NativeModelSpec(task="binary").task == "binary"
    assert isinstance(NativeModelSpec(task="binary", head=OCRHeadSpec()).head, OCRHeadSpec)
    with pytest.raises(ConfigError, match=r"model\.native\.task"):
        NativeModelSpec(task="multilabel")


def test_auxiliary_heads_require_unique_names_and_finite_positive_weights() -> None:
    head = FCNHeadSpec()
    with pytest.raises(ConfigError, match="loss_weight must be positive"):
        AuxiliaryHeadSpec(name="aux", loss_weight=float("inf"), head=head)
    with pytest.raises(ConfigError, match="names must be unique"):
        NativeModelSpec(
            auxiliary_heads=[
                AuxiliaryHeadSpec(name="aux", loss_weight=0.4, head=head),
                AuxiliaryHeadSpec(name="aux", loss_weight=0.2, head=head),
            ]
        )


def test_ocr_is_primary_only_because_its_coarse_classifier_needs_supervision() -> None:
    with pytest.raises(ConfigError, match="OCR is primary-only"):
        AuxiliaryHeadSpec(name="nested_ocr", loss_weight=0.4, head=OCRHeadSpec())
