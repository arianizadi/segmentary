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
        fcn_spec = cast(FCNHeadSpecLike, spec)
        return FCNHead(
            input_specs,
            num_classes,
            in_indices=fcn_spec.in_indices,
            channels=fcn_spec.channels,
            num_convs=fcn_spec.num_convs,
            kernel_size=fcn_spec.kernel_size,
            dilation=fcn_spec.dilation,
            dropout=fcn_spec.dropout,
            norm=fcn_spec.norm,
            activation=fcn_spec.activation,
        )
    if kind == "segformer":
        segformer_spec = cast(SegFormerHeadSpecLike, spec)
        return SegFormerMLPHead(
            input_specs,
            num_classes,
            in_indices=segformer_spec.in_indices,
            channels=segformer_spec.channels,
            dropout=segformer_spec.dropout,
            norm=segformer_spec.norm,
            activation=segformer_spec.activation,
        )
    if kind == "psp":
        psp_spec = cast(PSPHeadSpecLike, spec)
        return PSPHead(
            input_specs,
            num_classes,
            in_index=psp_spec.in_index,
            channels=psp_spec.channels,
            pool_bins=psp_spec.pool_bins,
            dropout=psp_spec.dropout,
            norm=psp_spec.norm,
            activation=psp_spec.activation,
        )
    if kind == "aspp":
        aspp_spec = cast(ASPPHeadSpecLike, spec)
        return ASPPHead(
            input_specs,
            num_classes,
            in_index=aspp_spec.in_index,
            channels=aspp_spec.channels,
            dilation_rates=aspp_spec.dilation_rates,
            dropout=aspp_spec.dropout,
            norm=aspp_spec.norm,
            activation=aspp_spec.activation,
        )
    if kind == "deeplabv3plus":
        deeplab_spec = cast(DeepLabV3PlusHeadSpecLike, spec)
        return DeepLabV3PlusHead(
            input_specs,
            num_classes,
            low_index=deeplab_spec.low_index,
            high_index=deeplab_spec.high_index,
            channels=deeplab_spec.channels,
            low_channels=deeplab_spec.low_channels,
            dilation_rates=deeplab_spec.dilation_rates,
            dropout=deeplab_spec.dropout,
            norm=deeplab_spec.norm,
            activation=deeplab_spec.activation,
        )
    if kind == "lraspp":
        lraspp_spec = cast(LRASPPHeadSpecLike, spec)
        return LRASPPHead(
            input_specs,
            num_classes,
            low_index=lraspp_spec.low_index,
            high_index=lraspp_spec.high_index,
            channels=lraspp_spec.channels,
            dropout=lraspp_spec.dropout,
            norm=lraspp_spec.norm,
            activation=lraspp_spec.activation,
        )
    if kind == "uper":
        uper_spec = cast(UPerHeadSpecLike, spec)
        return UPerHead(
            input_specs,
            num_classes,
            in_indices=uper_spec.in_indices,
            channels=uper_spec.channels,
            pool_bins=uper_spec.pool_bins,
            dropout=uper_spec.dropout,
            norm=uper_spec.norm,
            activation=uper_spec.activation,
        )
    if kind == "dpt":
        dpt_spec = cast(DPTHeadSpecLike, spec)
        return DPTHead(
            input_specs,
            num_classes,
            in_indices=dpt_spec.in_indices,
            channels=dpt_spec.channels,
            dropout=dpt_spec.dropout,
            norm=dpt_spec.norm,
            activation=dpt_spec.activation,
        )
    if kind == "ocr":
        ocr_spec = cast(OCRHeadSpecLike, spec)
        return OCRHead(
            input_specs,
            num_classes,
            in_indices=ocr_spec.in_indices,
            channels=ocr_spec.channels,
            key_channels=ocr_spec.key_channels,
            attention_scale=ocr_spec.attention_scale,
            dropout=ocr_spec.dropout,
            coarse_loss_weight=ocr_spec.coarse_loss_weight,
            norm=ocr_spec.norm,
            activation=ocr_spec.activation,
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
