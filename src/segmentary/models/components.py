"""Strict builders for native segmentation components.

The configuration layer owns concrete dataclasses.  These structural protocols
let the model layer consume those dataclasses without importing config.py back
into ``segmentary.models`` and creating a dependency cycle.  Dispatch is exhaustive
on a typed ``kind`` field; no constructor kwargs are forwarded.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol, cast

from .backbones import TimmBackbone
from .features import FeatureBackbone, FeatureNeck, FeatureSpec
from .layers import ActivationKind, NormKind
from .native import AuxiliaryHeadBinding, NativeDenseSegmenter
from .native_heads import (
    ASPPHead,
    DeepLabV3PlusHead,
    DPTHead,
    FCNHead,
    LRASPPHead,
    OCRHead,
    PSPHead,
    SegFormerMLPHead,
    UPerHead,
)
from .native_heads.base import DenseHead
from .necks import ChannelMapper, FPNNeck, IdentityNeck


class TimmBackboneSpecLike(Protocol):
    kind: Literal["timm"]
    name: str
    weights: Literal["pretrained", "scratch"]
    out_indices: tuple[int, ...]
    in_channels: int


class IdentityNeckSpecLike(Protocol):
    kind: Literal["identity"]


class FPNNeckSpecLike(Protocol):
    kind: Literal["fpn"]
    out_channels: int
    num_outputs: int | None
    norm: NormKind
    activation: ActivationKind


class ChannelMapperNeckSpecLike(Protocol):
    kind: Literal["channel_mapper"]
    out_channels: int
    kernel_size: int
    num_outputs: int | None
    norm: NormKind
    activation: ActivationKind


class _HeadSpec(Protocol):
    kind: str


class FCNHeadSpecLike(_HeadSpec, Protocol):
    kind: Literal["fcn"]
    in_indices: tuple[int, ...]
    channels: int
    num_convs: int
    kernel_size: int
    dilation: int
    dropout: float
    norm: NormKind
    activation: ActivationKind


class SegFormerHeadSpecLike(_HeadSpec, Protocol):
    kind: Literal["segformer"]
    in_indices: tuple[int, ...]
    channels: int
    dropout: float
    norm: NormKind
    activation: ActivationKind


class PSPHeadSpecLike(_HeadSpec, Protocol):
    kind: Literal["psp"]
    in_index: int
    channels: int
    pool_bins: tuple[int, ...]
    dropout: float
    norm: NormKind
    activation: ActivationKind


class ASPPHeadSpecLike(_HeadSpec, Protocol):
    kind: Literal["aspp"]
    in_index: int
    channels: int
    dilation_rates: tuple[int, ...]
    dropout: float
    norm: NormKind
    activation: ActivationKind


class DeepLabV3PlusHeadSpecLike(_HeadSpec, Protocol):
    kind: Literal["deeplabv3plus"]
    low_index: int
    high_index: int
    channels: int
    low_channels: int
    dilation_rates: tuple[int, ...]
    dropout: float
    norm: NormKind
    activation: ActivationKind


class LRASPPHeadSpecLike(_HeadSpec, Protocol):
    kind: Literal["lraspp"]
    low_index: int
    high_index: int
    channels: int
    dropout: float
    norm: NormKind
    activation: ActivationKind


class UPerHeadSpecLike(_HeadSpec, Protocol):
    kind: Literal["uper"]
    in_indices: tuple[int, ...]
    channels: int
    pool_bins: tuple[int, ...]
    dropout: float
    norm: NormKind
    activation: ActivationKind


class DPTHeadSpecLike(_HeadSpec, Protocol):
    kind: Literal["dpt"]
    in_indices: tuple[int, ...]
    channels: int
    dropout: float
    norm: NormKind
    activation: ActivationKind


class OCRHeadSpecLike(_HeadSpec, Protocol):
    kind: Literal["ocr"]
    in_indices: tuple[int, ...]
    channels: int
    key_channels: int
    attention_scale: int
    dropout: float
    coarse_loss_weight: float
    norm: NormKind
    activation: ActivationKind


DenseHeadSpecLike = (
    FCNHeadSpecLike
    | SegFormerHeadSpecLike
    | PSPHeadSpecLike
    | ASPPHeadSpecLike
    | DeepLabV3PlusHeadSpecLike
    | LRASPPHeadSpecLike
    | UPerHeadSpecLike
    | DPTHeadSpecLike
    | OCRHeadSpecLike
)


class AuxiliaryHeadSpecLike(Protocol):
    name: str
    loss_weight: float
    head: DenseHeadSpecLike


def build_backbone(spec: TimmBackboneSpecLike) -> FeatureBackbone:
    if getattr(spec, "kind", None) != "timm":
        raise ValueError(f"unknown native backbone kind {getattr(spec, 'kind', None)!r}")
    if spec.weights not in ("pretrained", "scratch"):
        raise ValueError("timm weights must be 'pretrained' or 'scratch'")
    return TimmBackbone(
        spec.name,
        pretrained=spec.weights == "pretrained",
        out_indices=spec.out_indices,
        input_channels=spec.in_channels,
    )


def build_neck(
    spec: IdentityNeckSpecLike | FPNNeckSpecLike | ChannelMapperNeckSpecLike,
    input_specs: tuple[FeatureSpec, ...],
) -> FeatureNeck:
    kind = getattr(spec, "kind", None)
    if kind == "identity":
        return IdentityNeck(input_specs)
    if kind == "fpn":
        fpn = cast(FPNNeckSpecLike, spec)
        return FPNNeck(
            input_specs,
            out_channels=fpn.out_channels,
            num_outputs=fpn.num_outputs,
            norm=fpn.norm,
            activation=fpn.activation,
        )
    if kind == "channel_mapper":
        mapper = cast(ChannelMapperNeckSpecLike, spec)
        return ChannelMapper(
            input_specs,
            out_channels=mapper.out_channels,
            kernel_size=mapper.kernel_size,
            num_outputs=mapper.num_outputs,
            norm=mapper.norm,
            activation=mapper.activation,
        )
    raise ValueError(f"unknown native neck kind {kind!r}")


def build_head(
    spec: DenseHeadSpecLike,
    input_specs: tuple[FeatureSpec, ...],
    num_classes: int,
) -> DenseHead:
    kind = getattr(spec, "kind", None)
    if kind == "fcn":
        item = cast(FCNHeadSpecLike, spec)
        return FCNHead(
            input_specs,
            num_classes,
            in_indices=item.in_indices,
            channels=item.channels,
            num_convs=item.num_convs,
            kernel_size=item.kernel_size,
            dilation=item.dilation,
            dropout=item.dropout,
            norm=item.norm,
            activation=item.activation,
        )
    if kind == "segformer":
        item = cast(SegFormerHeadSpecLike, spec)
        return SegFormerMLPHead(
            input_specs,
            num_classes,
            in_indices=item.in_indices,
            channels=item.channels,
            dropout=item.dropout,
            norm=item.norm,
            activation=item.activation,
        )
    if kind == "psp":
        item = cast(PSPHeadSpecLike, spec)
        return PSPHead(
            input_specs,
            num_classes,
            in_index=item.in_index,
            channels=item.channels,
            pool_bins=item.pool_bins,
            dropout=item.dropout,
            norm=item.norm,
            activation=item.activation,
        )
    if kind == "aspp":
        item = cast(ASPPHeadSpecLike, spec)
        return ASPPHead(
            input_specs,
            num_classes,
            in_index=item.in_index,
            channels=item.channels,
            dilation_rates=item.dilation_rates,
            dropout=item.dropout,
            norm=item.norm,
            activation=item.activation,
        )
    if kind == "deeplabv3plus":
        item = cast(DeepLabV3PlusHeadSpecLike, spec)
        return DeepLabV3PlusHead(
            input_specs,
            num_classes,
            low_index=item.low_index,
            high_index=item.high_index,
            channels=item.channels,
            low_channels=item.low_channels,
            dilation_rates=item.dilation_rates,
            dropout=item.dropout,
            norm=item.norm,
            activation=item.activation,
        )
    if kind == "lraspp":
        item = cast(LRASPPHeadSpecLike, spec)
        return LRASPPHead(
            input_specs,
            num_classes,
            low_index=item.low_index,
            high_index=item.high_index,
            channels=item.channels,
            dropout=item.dropout,
            norm=item.norm,
            activation=item.activation,
        )
    if kind == "uper":
        item = cast(UPerHeadSpecLike, spec)
        return UPerHead(
            input_specs,
            num_classes,
            in_indices=item.in_indices,
            channels=item.channels,
            pool_bins=item.pool_bins,
            dropout=item.dropout,
            norm=item.norm,
            activation=item.activation,
        )
    if kind == "dpt":
        item = cast(DPTHeadSpecLike, spec)
        return DPTHead(
            input_specs,
            num_classes,
            in_indices=item.in_indices,
            channels=item.channels,
            dropout=item.dropout,
            norm=item.norm,
            activation=item.activation,
        )
    if kind == "ocr":
        item = cast(OCRHeadSpecLike, spec)
        return OCRHead(
            input_specs,
            num_classes,
            in_indices=item.in_indices,
            channels=item.channels,
            key_channels=item.key_channels,
            attention_scale=item.attention_scale,
            dropout=item.dropout,
            coarse_loss_weight=item.coarse_loss_weight,
            norm=item.norm,
            activation=item.activation,
        )
    raise ValueError(
        f"unknown native head kind {kind!r}; choose fcn, segformer, psp, aspp, "
        "deeplabv3plus, lraspp, uper, dpt, or ocr"
    )


def build_native_model(
    backbone_spec: TimmBackboneSpecLike,
    neck_spec: IdentityNeckSpecLike | FPNNeckSpecLike | ChannelMapperNeckSpecLike,
    head_spec: DenseHeadSpecLike,
    auxiliary_specs: Sequence[AuxiliaryHeadSpecLike],
    num_classes: int,
    *,
    task: str = "multiclass",
) -> NativeDenseSegmenter:
    if task == "binary":
        if num_classes != 2:
            raise ValueError(
                "native binary models require exactly two canonical classes "
                "(id 0 negative, id 1 positive)"
            )
        output_channels = 1
    elif task == "multiclass":
        output_channels = num_classes
    else:
        raise ValueError(f"unsupported native segmentation task {task!r}")
    backbone = build_backbone(backbone_spec)
    neck = build_neck(neck_spec, backbone.output_specs)
    head = build_head(head_spec, neck.output_specs, output_channels)
    auxiliary = tuple(
        AuxiliaryHeadBinding(
            spec.name,
            build_head(spec.head, neck.output_specs, output_channels),
            spec.loss_weight,
        )
        for spec in auxiliary_specs
    )
    return NativeDenseSegmenter(
        backbone,
        neck,
        head,
        num_classes,
        task=task,
        auxiliary_heads=auxiliary,
    )
