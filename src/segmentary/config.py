"""Typed dataclass configs loaded from YAML. No **kwargs pass-through anywhere.

Unknown keys are a hard error. A silently-ignored typo in a config is how an
ablation ends up secretly being a duplicate of its baseline, which is worse than
a crash because the numbers look plausible.

Configs compose by recursive merge: base.yaml <- stage yaml <- CLI overrides. The
merged dict is hashed into results.json so a run can always be traced back to the
exact settings that produced it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from types import UnionType
from typing import Any, Literal, TypeVar, Union, cast, get_args, get_origin, get_type_hints

import yaml

T = TypeVar("T")

TuningMode = Literal["frozen", "lora", "full"]
HeadStrategy = Literal["per_stage_head", "unified_head"]
SMPDecoder = Literal[
    "Unet",
    "UnetPlusPlus",
    "FPN",
    "PSPNet",
    "DeepLabV3",
    "DeepLabV3Plus",
    "MAnet",
    "Linknet",
    "PAN",
    "UPerNet",
]
_AUX_KINDS = Literal["none", "lovasz", "dice"]
LossTask = Literal["multiclass", "binary", "multilabel"]
LossActivation = Literal["auto", "softmax", "sigmoid"]
ActivationKind = Literal[
    "relu",
    "relu6",
    "leaky_relu",
    "gelu",
    "silu",
    "elu",
    "mish",
    "hardswish",
]
NormKind = Literal["batch", "group", "instance", "layer", "none"]


class ConfigError(ValueError):
    """Raised for unknown keys, bad types, or invalid combinations."""


# --------------------------------------------------------------------------
# leaf configs
# --------------------------------------------------------------------------


@dataclass
class DataConfig:
    """One dataset within a stage."""

    name: str  # logical name used in batches, sample weights, and result records
    root: str
    variant: str | None = None  # taxonomy mapping variant, e.g. "railbridge"
    split_file: str | None = None  # required for railsem19
    train_split: str = "train"
    val_split: str = "val"
    limit: int | None = None
    # Generic-loader fields are appended after the legacy positional surface.
    loader: str | None = None  # built-in id or ``package.module:SegDatasetSubclass``
    mapping: str | None = None  # taxonomy mapping filename stem; defaults to ``name``
    loader_options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name, value in (
            ("name", self.name),
            ("root", self.root),
            ("train_split", self.train_split),
            ("val_split", self.val_split),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"data.{field_name} must be a non-empty string")
        for optional_name, optional in (("loader", self.loader), ("mapping", self.mapping)):
            if optional is not None and (not isinstance(optional, str) or not optional.strip()):
                raise ConfigError(f"data.{optional_name} cannot be empty or whitespace")
        if not isinstance(self.loader_options, dict) or any(
            not isinstance(key, str) or not key for key in self.loader_options
        ):
            raise ConfigError("data.loader_options must be a mapping with non-empty string keys")
        if self.limit is not None and self.limit < 1:
            raise ConfigError(f"data.limit must be at least 1, got {self.limit}")


@dataclass
class AugConfigSpec:
    crop: tuple[int, int] = (1024, 1024)
    scale_min: float = 0.5
    scale_max: float = 2.0
    hflip_p: float = 0.5
    color_jitter_p: float = 0.5
    brightness: float = 0.25
    contrast: float = 0.25
    saturation: float = 0.25
    hue: float = 0.05

    def __post_init__(self) -> None:
        if len(self.crop) != 2 or any(size <= 0 for size in self.crop):
            raise ConfigError(f"aug.crop must contain two positive sizes, got {self.crop}")
        if not 0 < self.scale_min <= self.scale_max:
            raise ConfigError(
                f"aug scales must satisfy 0 < scale_min <= scale_max, got "
                f"{self.scale_min}, {self.scale_max}"
            )
        for name, value in (
            ("hflip_p", self.hflip_p),
            ("color_jitter_p", self.color_jitter_p),
        ):
            if not 0.0 <= value <= 1.0:
                raise ConfigError(f"aug.{name} must be in [0, 1], got {value}")


def _positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{name} must be a positive integer, got {value!r}")


def _probability(name: str, value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value < 1.0
    ):
        raise ConfigError(f"{name} must be in [0, 1), got {value!r}")


def _choice(name: str, value: str, choices: tuple[str, ...]) -> None:
    if value not in choices:
        raise ConfigError(f"{name} must be one of {choices}, got {value!r}")


def _block_options(name: str, norm: str, activation: str) -> None:
    _choice(f"{name}.norm", norm, get_args(NormKind))
    _choice(f"{name}.activation", activation, get_args(ActivationKind))


def _indices(name: str, values: tuple[int, ...], *, minimum: int = 1) -> None:
    if len(values) < minimum:
        raise ConfigError(f"{name} needs at least {minimum} feature index/indices")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise ConfigError(f"{name} must contain non-negative integers, got {values}")
    if tuple(sorted(set(values))) != values:
        raise ConfigError(f"{name} must be unique and strictly increasing, got {values}")


def _positive_tuple(name: str, values: tuple[int, ...]) -> None:
    if not values or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values
    ):
        raise ConfigError(f"{name} must contain positive integers, got {values}")
    if len(set(values)) != len(values):
        raise ConfigError(f"{name} must contain unique values, got {values}")


@dataclass
class TimmBackboneSpec:
    kind: Literal["timm"] = "timm"
    name: str = "resnet50"
    weights: Literal["pretrained", "scratch"] = "pretrained"
    out_indices: tuple[int, ...] = (1, 2, 3, 4)
    in_channels: int = 3

    def __post_init__(self) -> None:
        _choice("model.native.backbone.kind", self.kind, ("timm",))
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or self.name != self.name.strip()
        ):
            raise ConfigError("model.native.backbone.name must be a non-empty, trimmed string")
        _choice("model.native.backbone.weights", self.weights, ("pretrained", "scratch"))
        _indices("model.native.backbone.out_indices", self.out_indices)
        _positive_int("model.native.backbone.in_channels", self.in_channels)
        if self.in_channels != 3:
            raise ConfigError(
                "model.native.backbone.in_channels currently must be 3 because the public "
                "dataset pipeline decodes RGB images; accepting another value would fail "
                "only after the first batch"
            )


@dataclass
class IdentityNeckSpec:
    kind: Literal["identity"] = "identity"

    def __post_init__(self) -> None:
        _choice("model.native.neck.kind", self.kind, ("identity",))


@dataclass
class FPNNeckSpec:
    kind: Literal["fpn"] = "fpn"
    out_channels: int = 256
    num_outputs: int | None = None
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.neck.kind", self.kind, ("fpn",))
        _positive_int("model.native.neck.out_channels", self.out_channels)
        if self.num_outputs is not None:
            _positive_int("model.native.neck.num_outputs", self.num_outputs)
        _block_options("model.native.neck", self.norm, self.activation)


@dataclass
class ChannelMapperNeckSpec:
    kind: Literal["channel_mapper"] = "channel_mapper"
    out_channels: int = 256
    kernel_size: int = 1
    num_outputs: int | None = None
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.neck.kind", self.kind, ("channel_mapper",))
        _positive_int("model.native.neck.out_channels", self.out_channels)
        _positive_int("model.native.neck.kernel_size", self.kernel_size)
        if self.kernel_size % 2 == 0:
            raise ConfigError("model.native.neck.kernel_size must be odd")
        if self.num_outputs is not None:
            _positive_int("model.native.neck.num_outputs", self.num_outputs)
        _block_options("model.native.neck", self.norm, self.activation)


@dataclass
class FCNHeadSpec:
    kind: Literal["fcn"] = "fcn"
    in_indices: tuple[int, ...] = (3,)
    channels: int = 256
    num_convs: int = 2
    kernel_size: int = 3
    dilation: int = 1
    dropout: float = 0.1
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.head.kind", self.kind, ("fcn",))
        _indices("model.native.head.in_indices", self.in_indices)
        _positive_int("model.native.head.channels", self.channels)
        _positive_int("model.native.head.num_convs", self.num_convs)
        _positive_int("model.native.head.kernel_size", self.kernel_size)
        if self.kernel_size % 2 == 0:
            raise ConfigError("model.native.head.kernel_size must be odd")
        _positive_int("model.native.head.dilation", self.dilation)
        _probability("model.native.head.dropout", self.dropout)
        _block_options("model.native.head", self.norm, self.activation)


@dataclass
class SegFormerHeadSpec:
    kind: Literal["segformer"] = "segformer"
    in_indices: tuple[int, ...] = (0, 1, 2, 3)
    channels: int = 256
    dropout: float = 0.1
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.head.kind", self.kind, ("segformer",))
        _indices("model.native.head.in_indices", self.in_indices, minimum=2)
        _positive_int("model.native.head.channels", self.channels)
        _probability("model.native.head.dropout", self.dropout)
        _block_options("model.native.head", self.norm, self.activation)


@dataclass
class PSPHeadSpec:
    kind: Literal["psp"] = "psp"
    in_index: int = 3
    channels: int = 256
    pool_bins: tuple[int, ...] = (1, 2, 3, 6)
    dropout: float = 0.1
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.head.kind", self.kind, ("psp",))
        _indices("model.native.head.in_index", (self.in_index,))
        _positive_int("model.native.head.channels", self.channels)
        _positive_tuple("model.native.head.pool_bins", self.pool_bins)
        _probability("model.native.head.dropout", self.dropout)
        _block_options("model.native.head", self.norm, self.activation)


@dataclass
class ASPPHeadSpec:
    kind: Literal["aspp"] = "aspp"
    in_index: int = 3
    channels: int = 256
    dilation_rates: tuple[int, ...] = (6, 12, 18)
    dropout: float = 0.1
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.head.kind", self.kind, ("aspp",))
        _indices("model.native.head.in_index", (self.in_index,))
        _positive_int("model.native.head.channels", self.channels)
        _positive_tuple("model.native.head.dilation_rates", self.dilation_rates)
        _probability("model.native.head.dropout", self.dropout)
        _block_options("model.native.head", self.norm, self.activation)


@dataclass
class DeepLabV3PlusHeadSpec:
    kind: Literal["deeplabv3plus"] = "deeplabv3plus"
    low_index: int = 0
    high_index: int = 3
    channels: int = 256
    low_channels: int = 48
    dilation_rates: tuple[int, ...] = (6, 12, 18)
    dropout: float = 0.1
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.head.kind", self.kind, ("deeplabv3plus",))
        _indices("model.native.head indices", (self.low_index, self.high_index), minimum=2)
        _positive_int("model.native.head.channels", self.channels)
        _positive_int("model.native.head.low_channels", self.low_channels)
        _positive_tuple("model.native.head.dilation_rates", self.dilation_rates)
        _probability("model.native.head.dropout", self.dropout)
        _block_options("model.native.head", self.norm, self.activation)


@dataclass
class LRASPPHeadSpec:
    kind: Literal["lraspp"] = "lraspp"
    low_index: int = 0
    high_index: int = 3
    channels: int = 128
    dropout: float = 0.1
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.head.kind", self.kind, ("lraspp",))
        _indices("model.native.head indices", (self.low_index, self.high_index), minimum=2)
        _positive_int("model.native.head.channels", self.channels)
        _probability("model.native.head.dropout", self.dropout)
        _block_options("model.native.head", self.norm, self.activation)


@dataclass
class UPerHeadSpec:
    kind: Literal["uper"] = "uper"
    in_indices: tuple[int, ...] = (0, 1, 2, 3)
    channels: int = 256
    pool_bins: tuple[int, ...] = (1, 2, 3, 6)
    dropout: float = 0.1
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.head.kind", self.kind, ("uper",))
        _indices("model.native.head.in_indices", self.in_indices, minimum=2)
        _positive_int("model.native.head.channels", self.channels)
        _positive_tuple("model.native.head.pool_bins", self.pool_bins)
        _probability("model.native.head.dropout", self.dropout)
        _block_options("model.native.head", self.norm, self.activation)


@dataclass
class DPTHeadSpec:
    kind: Literal["dpt"] = "dpt"
    in_indices: tuple[int, ...] = (0, 1, 2, 3)
    channels: int = 256
    dropout: float = 0.1
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.head.kind", self.kind, ("dpt",))
        _indices("model.native.head.in_indices", self.in_indices, minimum=4)
        if len(self.in_indices) != 4:
            raise ConfigError(
                "model.native.head.in_indices for DPT must select exactly four feature levels"
            )
        _positive_int("model.native.head.channels", self.channels)
        _probability("model.native.head.dropout", self.dropout)
        _block_options("model.native.head", self.norm, self.activation)


@dataclass
class OCRHeadSpec:
    kind: Literal["ocr"] = "ocr"
    in_indices: tuple[int, ...] = (0, 1, 2, 3)
    channels: int = 512
    key_channels: int = 256
    attention_scale: int = 1
    dropout: float = 0.05
    coarse_loss_weight: float = 0.4
    norm: NormKind = "group"
    activation: ActivationKind = "relu"

    def __post_init__(self) -> None:
        _choice("model.native.head.kind", self.kind, ("ocr",))
        _indices("model.native.head.in_indices", self.in_indices)
        _positive_int("model.native.head.channels", self.channels)
        _positive_int("model.native.head.key_channels", self.key_channels)
        _positive_int("model.native.head.attention_scale", self.attention_scale)
        _probability("model.native.head.dropout", self.dropout)
        if (
            isinstance(self.coarse_loss_weight, bool)
            or not isinstance(self.coarse_loss_weight, (int, float))
            or not math.isfinite(self.coarse_loss_weight)
            or self.coarse_loss_weight <= 0.0
        ):
            raise ConfigError("model.native.head.coarse_loss_weight must be finite and positive")
        _block_options("model.native.head", self.norm, self.activation)


DenseHeadSpec = (
    FCNHeadSpec
    | SegFormerHeadSpec
    | PSPHeadSpec
    | ASPPHeadSpec
    | DeepLabV3PlusHeadSpec
    | LRASPPHeadSpec
    | UPerHeadSpec
    | DPTHeadSpec
    | OCRHeadSpec
)
NeckSpec = IdentityNeckSpec | FPNNeckSpec | ChannelMapperNeckSpec


@dataclass
class AuxiliaryHeadSpec:
    name: str
    loss_weight: float
    head: DenseHeadSpec

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or self.name != self.name.strip()
        ):
            raise ConfigError("model.native auxiliary head name must be non-empty and trimmed")
        if (
            isinstance(self.loss_weight, bool)
            or not isinstance(self.loss_weight, (int, float))
            or not math.isfinite(self.loss_weight)
            or self.loss_weight <= 0
        ):
            raise ConfigError("model.native auxiliary loss_weight must be positive")
        if not isinstance(
            self.head,
            (
                FCNHeadSpec,
                SegFormerHeadSpec,
                PSPHeadSpec,
                ASPPHeadSpec,
                DeepLabV3PlusHeadSpec,
                LRASPPHeadSpec,
                UPerHeadSpec,
                DPTHeadSpec,
            ),
        ):
            raise ConfigError(
                "model.native auxiliary head must be a typed ordinary dense-head "
                "specification; OCR is primary-only because it already owns a supervised "
                "coarse output"
            )


@dataclass
class NativeModelSpec:
    task: Literal["multiclass", "binary"] = "multiclass"
    backbone: TimmBackboneSpec = field(default_factory=TimmBackboneSpec)
    neck: NeckSpec = field(default_factory=IdentityNeckSpec)
    head: DenseHeadSpec = field(default_factory=SegFormerHeadSpec)
    auxiliary_heads: list[AuxiliaryHeadSpec] = field(default_factory=list)

    def __post_init__(self) -> None:
        _choice("model.native.task", self.task, ("multiclass", "binary"))
        if not isinstance(self.backbone, TimmBackboneSpec):
            raise ConfigError("model.native.backbone must be a typed timm backbone specification")
        if not isinstance(self.neck, (IdentityNeckSpec, FPNNeckSpec, ChannelMapperNeckSpec)):
            raise ConfigError("model.native.neck must be a typed neck specification")
        if not isinstance(
            self.head,
            (
                FCNHeadSpec,
                SegFormerHeadSpec,
                PSPHeadSpec,
                ASPPHeadSpec,
                DeepLabV3PlusHeadSpec,
                LRASPPHeadSpec,
                UPerHeadSpec,
                DPTHeadSpec,
                OCRHeadSpec,
            ),
        ):
            raise ConfigError("model.native.head must be a typed dense-head specification")
        if not isinstance(self.auxiliary_heads, list) or not all(
            isinstance(item, AuxiliaryHeadSpec) for item in self.auxiliary_heads
        ):
            raise ConfigError("model.native.auxiliary_heads must contain typed auxiliary heads")
        names = [item.name for item in self.auxiliary_heads]
        if len(names) != len(set(names)):
            raise ConfigError(f"model.native auxiliary head names must be unique, got {names}")


@dataclass
class ModelConfig:
    arch: str  # key into models.factory.build_model
    checkpoint: str | None = None  # HF id or local path for backbone init
    # Preserve the original positional API; generic-HF options are appended.
    tuning: TuningMode = "full"
    head: HeadStrategy = "unified_head"
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_targets: list[str] = field(default_factory=list)
    drop_path: float | None = None
    # ``hf_auto`` is the generic Hugging Face semantic-segmentation path.  These
    # fields are deliberately typed rather than accepted as arbitrary kwargs:
    # every value is recorded in results.json and an unsupported option fails
    # before a model or dataset is opened.
    revision: str | None = None
    subfolder: str | None = None
    local_files_only: bool = False
    trust_remote_code: Literal[False] = False
    # Leave all three layout fields unset for conservative auto-discovery.  Set
    # the complete triplet for an otherwise-supported upstream module layout the
    # discovery code cannot prove unambiguously.
    backbone_path: str | None = None
    head_paths: list[str] = field(default_factory=list)
    classifier_path: str | None = None
    # Exact upstream modules that the primary dense output cannot reach. These
    # are revision-pinned, audited exceptions—not runtime unused-grad guesses.
    inactive_parameter_paths: list[str] = field(default_factory=list)
    # ``smp`` composes a reviewed decoder with any encoder supported by the
    # installed segmentation-models-pytorch release.  Keep these fields after
    # the original/HF surface so older positional construction retains meaning.
    smp_arch: SMPDecoder | None = None
    encoder_name: str | None = None
    # A weight tag (usually ``imagenet``) or the explicit ``scratch`` sentinel.
    # ``None`` means this SMP-only field was not supplied.
    encoder_weights: str | None = None
    # Segmentary-native independently composable backbone -> neck -> head stack.
    # It is nested so no component field can be mistaken for a legacy model arm.
    native: NativeModelSpec | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.arch, str) or not self.arch.strip():
            raise ConfigError("model.arch must be a non-empty string")
        if self.checkpoint is not None and (
            not isinstance(self.checkpoint, str) or not self.checkpoint.strip()
        ):
            raise ConfigError("model.checkpoint cannot be empty or whitespace")
        if self.tuning not in get_args(TuningMode):
            raise ConfigError(f"tuning must be one of {get_args(TuningMode)}, got {self.tuning!r}")
        if self.head not in get_args(HeadStrategy):
            raise ConfigError(f"head must be one of {get_args(HeadStrategy)}, got {self.head!r}")
        if self.tuning == "lora" and self.lora_r <= 0:
            raise ConfigError(f"lora tuning needs lora_r > 0, got {self.lora_r}")
        if self.lora_alpha <= 0:
            raise ConfigError(f"model.lora_alpha must be positive, got {self.lora_alpha}")
        if not 0.0 <= self.lora_dropout < 1.0:
            raise ConfigError(f"model.lora_dropout must be in [0, 1), got {self.lora_dropout}")
        if self.trust_remote_code is not False:
            raise ConfigError(
                "model.trust_remote_code must stay false: loading repository-defined Python "
                "would execute unreviewed code during config/model construction"
            )
        for path in self.inactive_parameter_paths:
            if (
                not isinstance(path, str)
                or not path
                or path != path.strip()
                or path.startswith(".")
                or path.endswith(".")
                or ".." in path
            ):
                raise ConfigError(f"invalid model.inactive_parameter_paths entry {path!r}")
        if len(set(self.inactive_parameter_paths)) != len(self.inactive_parameter_paths):
            raise ConfigError("model.inactive_parameter_paths contains duplicates")
        for outer in self.inactive_parameter_paths:
            for inner in self.inactive_parameter_paths:
                if outer != inner and inner.startswith(outer + "."):
                    raise ConfigError(
                        "model.inactive_parameter_paths contains overlapping paths "
                        f"{outer!r} and {inner!r}"
                    )
        if self.inactive_parameter_paths and self.arch not in ("hf_auto", "smp"):
            raise ConfigError(
                "model.inactive_parameter_paths applies only to audited hf_auto or smp "
                f"recipes; refusing it for arch={self.arch!r}"
            )

        smp_decoders = get_args(SMPDecoder)
        if self.smp_arch is not None and self.smp_arch not in smp_decoders:
            raise ConfigError(
                f"model.smp_arch must be one of {smp_decoders}, got {self.smp_arch!r}"
            )
        if self.encoder_name is not None and (
            not isinstance(self.encoder_name, str) or not self.encoder_name.strip()
        ):
            raise ConfigError("model.encoder_name cannot be empty or whitespace")
        if self.encoder_weights is not None and (
            not isinstance(self.encoder_weights, str) or not self.encoder_weights.strip()
        ):
            raise ConfigError("model.encoder_weights cannot be empty or whitespace")

        if self.arch == "smp":
            if self.smp_arch is None:
                raise ConfigError(
                    f"model.smp_arch is required for arch='smp'; choose one of {smp_decoders}"
                )
            if self.encoder_name is None:
                raise ConfigError(
                    "model.encoder_name is required for arch='smp' (for example, resnet34)"
                )
            if self.encoder_weights is None:
                raise ConfigError(
                    "model.encoder_weights is required for arch='smp'; use a pretrained "
                    "weight tag such as 'imagenet' or the explicit value 'scratch'"
                )
            if self.checkpoint is not None:
                raise ConfigError(
                    "model.checkpoint is not used by arch='smp'; set model.encoder_name and "
                    "model.encoder_weights explicitly"
                )
            if self.drop_path is not None:
                raise ConfigError(
                    "arch='smp' does not expose a portable stochastic-depth option; "
                    "model.drop_path would be ignored by the standard decoder constructor"
                )
        elif (
            self.smp_arch is not None
            or self.encoder_name is not None
            or self.encoder_weights is not None
        ):
            used = [
                name
                for name, value, default in (
                    ("smp_arch", self.smp_arch, None),
                    ("encoder_name", self.encoder_name, None),
                    ("encoder_weights", self.encoder_weights, None),
                )
                if value != default
            ]
            raise ConfigError(
                f"model fields {used} apply only to arch='smp'; refusing to silently "
                f"ignore them for arch={self.arch!r}"
            )

        if self.arch == "native":
            if self.native is None:
                raise ConfigError("model.native is required when model.arch='native'")
            if self.checkpoint is not None:
                raise ConfigError(
                    "model.checkpoint is not used by arch='native'; select pretrained or "
                    "scratch in model.native.backbone.weights and use stage.init_from for "
                    "a full Segmentary checkpoint"
                )
            if self.drop_path is not None:
                raise ConfigError(
                    "model.drop_path is not a verified generic native-backbone option; "
                    "Segmentary refuses settings that a timm constructor might ignore"
                )
        elif self.native is not None:
            raise ConfigError(
                f"model.native applies only to arch='native'; refusing to ignore it for "
                f"arch={self.arch!r}"
            )

        hf_options = {
            "revision": self.revision,
            "subfolder": self.subfolder,
            "local_files_only": self.local_files_only,
            "backbone_path": self.backbone_path,
            "head_paths": self.head_paths,
            "classifier_path": self.classifier_path,
        }
        if self.arch != "hf_auto":
            used = [key for key, value in hf_options.items() if value not in (None, False, [])]
            if used:
                raise ConfigError(
                    f"model fields {used} apply only to arch='hf_auto'; refusing to "
                    f"silently ignore them for arch={self.arch!r}"
                )
            return

        if not isinstance(self.checkpoint, str) or not self.checkpoint.strip():
            raise ConfigError(
                "model.checkpoint is required for arch='hf_auto' and must be a Hugging "
                "Face model id or local pretrained-model directory"
            )
        for name, value in (("revision", self.revision), ("subfolder", self.subfolder)):
            if value is not None and not value.strip():
                raise ConfigError(f"model.{name} cannot be empty or whitespace")
        if self.drop_path is not None:
            raise ConfigError(
                "model.drop_path is not portable across AutoModelForSemanticSegmentation "
                "configs; use a supported explicit architecture arm instead"
            )

        paths_set = (
            self.backbone_path is not None,
            bool(self.head_paths),
            self.classifier_path is not None,
        )
        if any(paths_set) and not all(paths_set):
            raise ConfigError(
                "advanced hf_auto layout overrides are all-or-nothing: set backbone_path, "
                "a non-empty head_paths list, and classifier_path together"
            )
        if all(paths_set):
            assert self.backbone_path is not None and self.classifier_path is not None
            paths = [self.backbone_path, *self.head_paths, self.classifier_path]
            for path in paths:
                if (
                    not path
                    or path != path.strip()
                    or path.startswith(".")
                    or path.endswith(".")
                    or ".." in path
                ):
                    raise ConfigError(f"invalid hf_auto module path {path!r}")
            if len(set(self.head_paths)) != len(self.head_paths):
                raise ConfigError("model.head_paths contains duplicates")
            if not any(
                self.classifier_path == head or self.classifier_path.startswith(head + ".")
                for head in self.head_paths
            ):
                raise ConfigError(
                    "model.classifier_path must be the selected head or a descendant of one "
                    "of model.head_paths"
                )
            for head in self.head_paths:
                if (
                    head == self.backbone_path
                    or head.startswith(self.backbone_path + ".")
                    or self.backbone_path.startswith(head + ".")
                ):
                    raise ConfigError(
                        f"hf_auto backbone_path {self.backbone_path!r} overlaps head path {head!r}"
                    )
        if self.inactive_parameter_paths and (
            self.revision is None
            or len(self.revision) != 40
            or any(character not in "0123456789abcdef" for character in self.revision)
        ):
            raise ConfigError(
                "model.inactive_parameter_paths requires an immutable 40-character lowercase "
                "hex revision so an upstream layout change cannot make a frozen path live"
            )


def _finite_number(name: str, value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ConfigError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def _positive_term_weight(kind: str, weight: float) -> None:
    if _finite_number(f"loss term {kind!r} weight", weight) <= 0.0:
        raise ConfigError(f"loss term {kind!r} weight must be positive, got {weight!r}")


def _nonnegative_weights(name: str, weights: list[float] | None) -> None:
    if weights is None:
        return
    if not isinstance(weights, list) or not weights:
        raise ConfigError(f"{name} must be a non-empty list with at least one positive value")
    values = [_finite_number(f"{name}[{index}]", value) for index, value in enumerate(weights)]
    if any(weight < 0.0 for weight in values) or not any(values):
        raise ConfigError(f"{name} must be a non-empty list with at least one positive value")


def _positive_weights(name: str, weights: list[float] | None) -> None:
    if weights is None:
        return
    if not isinstance(weights, list) or not weights:
        raise ConfigError(f"{name} must be a non-empty list of positive values")
    values = [_finite_number(f"{name}[{index}]", value) for index, value in enumerate(weights)]
    if any(weight <= 0.0 for weight in values):
        raise ConfigError(f"{name} must contain only positive values")


@dataclass
class CrossEntropyTerm:
    kind: Literal["cross_entropy"]
    weight: float = 1.0
    label_smoothing: float = 0.0
    class_weights: list[float] | None = None

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        if (
            not 0.0
            <= _finite_number("loss cross_entropy label_smoothing", self.label_smoothing)
            < 1.0
        ):
            raise ConfigError(
                f"loss cross_entropy label_smoothing must be in [0, 1), got {self.label_smoothing}"
            )
        _nonnegative_weights("loss cross_entropy class_weights", self.class_weights)


@dataclass
class BinaryCrossEntropyTerm:
    kind: Literal["binary_cross_entropy"]
    weight: float = 1.0
    pos_weights: list[float] | None = None

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        _positive_weights("loss binary_cross_entropy pos_weights", self.pos_weights)


@dataclass
class DiceTerm:
    kind: Literal["dice"]
    weight: float = 1.0
    smooth: float = 1.0
    present_only: bool = True
    include_background: bool = True

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        if _finite_number("loss dice smooth", self.smooth) <= 0.0:
            raise ConfigError(f"loss dice smooth must be positive, got {self.smooth}")


@dataclass
class JaccardTerm:
    kind: Literal["jaccard"]
    weight: float = 1.0
    smooth: float = 1.0
    present_only: bool = True
    include_background: bool = True

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        if _finite_number("loss jaccard smooth", self.smooth) <= 0.0:
            raise ConfigError(f"loss jaccard smooth must be positive, got {self.smooth}")


@dataclass
class LovaszTerm:
    kind: Literal["lovasz"]
    weight: float = 1.0
    present_only: bool = True
    include_background: bool = True

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)


@dataclass
class FocalTerm:
    kind: Literal["focal"]
    weight: float = 1.0
    gamma: float = 2.0
    alpha: float | list[float] | None = None

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        if _finite_number("loss focal gamma", self.gamma) < 0.0:
            raise ConfigError(f"loss focal gamma must be non-negative, got {self.gamma}")
        if isinstance(self.alpha, list):
            _nonnegative_weights("loss focal alpha", self.alpha)
        elif self.alpha is not None:
            alpha = _finite_number("loss focal scalar alpha", self.alpha)
            if not 0.0 <= alpha <= 1.0:
                raise ConfigError(f"loss focal scalar alpha must be in [0, 1], got {self.alpha}")


@dataclass
class TverskyTerm:
    kind: Literal["tversky"]
    weight: float = 1.0
    alpha: float = 0.5
    beta: float = 0.5
    smooth: float = 1.0
    present_only: bool = True
    include_background: bool = True

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        alpha = _finite_number("loss tversky alpha", self.alpha)
        beta = _finite_number("loss tversky beta", self.beta)
        if alpha < 0.0 or beta < 0.0 or alpha + beta == 0.0:
            raise ConfigError("loss tversky alpha and beta must be non-negative and not both zero")
        if _finite_number("loss tversky smooth", self.smooth) <= 0.0:
            raise ConfigError(f"loss tversky smooth must be positive, got {self.smooth}")


@dataclass
class OHEMCrossEntropyTerm:
    kind: Literal["ohem_cross_entropy"]
    weight: float = 1.0
    fraction: float = 0.25
    min_kept: int = 1
    probability_threshold: float | None = None
    label_smoothing: float = 0.0
    class_weights: list[float] | None = None

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        if not 0.0 < _finite_number("loss OHEM fraction", self.fraction) <= 1.0:
            raise ConfigError(f"loss OHEM fraction must be in (0, 1], got {self.fraction}")
        if self.min_kept < 1:
            raise ConfigError(f"loss OHEM min_kept must be at least 1, got {self.min_kept}")
        if self.probability_threshold is not None:
            threshold = _finite_number(
                "loss OHEM probability_threshold", self.probability_threshold
            )
            if not 0.0 < threshold < 1.0:
                raise ConfigError(
                    "loss OHEM probability_threshold must be in (0, 1) when set, got "
                    f"{self.probability_threshold}"
                )
        if not 0.0 <= _finite_number("loss OHEM label_smoothing", self.label_smoothing) < 1.0:
            raise ConfigError(
                f"loss OHEM label_smoothing must be in [0, 1), got {self.label_smoothing}"
            )
        _nonnegative_weights("loss OHEM class_weights", self.class_weights)


@dataclass
class BoundaryTerm:
    kind: Literal["boundary"]
    weight: float = 1.0
    width: int = 1
    smooth: float = 1.0
    include_background: bool = True

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        if self.width < 1:
            raise ConfigError(f"loss boundary width must be at least 1, got {self.width}")
        if _finite_number("loss boundary smooth", self.smooth) <= 0.0:
            raise ConfigError(f"loss boundary smooth must be positive, got {self.smooth}")


@dataclass
class HausdorffTerm:
    kind: Literal["hausdorff"]
    weight: float = 1.0
    max_distance: int = 16
    power: float = 2.0
    include_background: bool = True

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        if self.max_distance < 1:
            raise ConfigError(
                f"loss hausdorff max_distance must be at least 1, got {self.max_distance}"
            )
        if _finite_number("loss hausdorff power", self.power) <= 0.0:
            raise ConfigError(f"loss hausdorff power must be positive, got {self.power}")


@dataclass
class KLDistillationTerm:
    kind: Literal["kl_distillation"]
    weight: float = 1.0
    temperature: float = 1.0
    detach_teacher: bool = True

    def __post_init__(self) -> None:
        _positive_term_weight(self.kind, self.weight)
        if _finite_number("loss kl_distillation temperature", self.temperature) <= 0.0:
            raise ConfigError(
                f"loss kl_distillation temperature must be positive, got {self.temperature}"
            )


LossTermSpec = (
    CrossEntropyTerm
    | BinaryCrossEntropyTerm
    | DiceTerm
    | JaccardTerm
    | LovaszTerm
    | FocalTerm
    | TverskyTerm
    | OHEMCrossEntropyTerm
    | BoundaryTerm
    | HausdorffTerm
    | KLDistillationTerm
)


@dataclass
class QueryLossSpec:
    """Native set-prediction objective for mask-classification models.

    Matching costs choose the bipartite assignment and loss weights scale the
    differentiable objective after matching.  Keeping those two roles explicit
    prevents a tuning change to the loss scale from silently changing which
    query is supervised.
    """

    kind: Literal["hungarian_query"] = "hungarian_query"
    classification_weight: float = 2.0
    mask_bce_weight: float = 5.0
    dice_weight: float = 5.0
    no_object_coefficient: float = 0.1
    match_class_cost: float = 2.0
    match_mask_bce_cost: float = 5.0
    match_dice_cost: float = 5.0
    matching_num_points: int | None = None
    auxiliary_layer_weight: float = 1.0
    dice_smooth: float = 1.0

    def __post_init__(self) -> None:
        if self.kind != "hungarian_query":
            raise ConfigError(f"loss.query.kind must be 'hungarian_query', got {self.kind!r}")
        classification_weight = _finite_number(
            "loss.query.classification_weight", self.classification_weight
        )
        mask_weights = {
            "mask_bce_weight": self.mask_bce_weight,
            "dice_weight": self.dice_weight,
        }
        resolved_mask_weights = {
            name: _finite_number(f"loss.query.{name}", value)
            for name, value in mask_weights.items()
        }
        if classification_weight <= 0.0:
            raise ConfigError("loss.query.classification_weight must be positive")
        if any(value < 0.0 for value in resolved_mask_weights.values()) or not any(
            resolved_mask_weights.values()
        ):
            raise ConfigError(
                "loss.query mask_bce/dice weights must be non-negative with at least one "
                "positive mask loss"
            )
        match_costs = {
            "match_class_cost": self.match_class_cost,
            "match_mask_bce_cost": self.match_mask_bce_cost,
            "match_dice_cost": self.match_dice_cost,
        }
        resolved_match_costs = {
            name: _finite_number(f"loss.query.{name}", value) for name, value in match_costs.items()
        }
        if any(value < 0.0 for value in resolved_match_costs.values()) or not any(
            resolved_match_costs.values()
        ):
            raise ConfigError(
                "loss.query matching costs must be non-negative with at least one positive value"
            )
        if _finite_number("loss.query.no_object_coefficient", self.no_object_coefficient) < 0.0:
            raise ConfigError("loss.query.no_object_coefficient must be non-negative")
        if _finite_number("loss.query.auxiliary_layer_weight", self.auxiliary_layer_weight) < 0.0:
            raise ConfigError("loss.query.auxiliary_layer_weight must be non-negative")
        if _finite_number("loss.query.dice_smooth", self.dice_smooth) <= 0.0:
            raise ConfigError("loss.query.dice_smooth must be positive")
        if self.matching_num_points is not None and (
            isinstance(self.matching_num_points, bool)
            or not isinstance(self.matching_num_points, int)
            or self.matching_num_points < 1
        ):
            raise ConfigError("loss.query.matching_num_points must be a positive integer or null")


@dataclass
class LossSpec:
    """A typed weighted objective list plus the pre-0.2 CE/aux compatibility surface."""

    task: LossTask = "multiclass"
    activation: LossActivation = "auto"
    terms: list[LossTermSpec] = field(default_factory=list)

    # Legacy fields remain readable so old experiments reproduce exactly. New
    # configs should use ``terms``; non-default legacy fields cannot be mixed
    # with it because doing so would make the effective objective ambiguous.
    aux: Literal["none", "lovasz", "dice"] = "none"
    aux_weight: float = 0.0
    ce_weight: float = 1.0
    label_smoothing: float = 0.0
    class_weights: list[float] | None = None
    query: QueryLossSpec | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.terms, list) or not all(
            isinstance(term, get_args(LossTermSpec)) for term in self.terms
        ):
            raise ConfigError("loss.terms must be a list of typed dense loss terms")
        if self.query is not None and not isinstance(self.query, QueryLossSpec):
            raise ConfigError("loss.query must be a QueryLossSpec or null")
        if self.aux not in get_args(_AUX_KINDS):
            raise ConfigError(f"loss.aux must be one of {get_args(_AUX_KINDS)}, got {self.aux!r}")
        aux_weight = _finite_number("loss.aux_weight", self.aux_weight)
        ce_weight = _finite_number("loss.ce_weight", self.ce_weight)
        if self.aux != "none" and aux_weight <= 0.0:
            raise ConfigError(
                f"loss.aux={self.aux!r} has no effect with aux_weight={self.aux_weight}; "
                f"set a positive weight or use aux: none"
            )
        if self.aux == "none" and self.aux_weight != 0.0:
            raise ConfigError("loss.aux_weight is set but loss.aux is 'none'")
        if ce_weight < 0.0:
            raise ConfigError(f"loss.ce_weight must be non-negative, got {self.ce_weight}")
        if not 0.0 <= _finite_number("loss.label_smoothing", self.label_smoothing) < 1.0:
            raise ConfigError(f"loss.label_smoothing must be in [0, 1), got {self.label_smoothing}")
        _nonnegative_weights("loss.class_weights", self.class_weights)

        expected_activation = "softmax" if self.task == "multiclass" else "sigmoid"
        if self.activation not in ("auto", expected_activation):
            raise ConfigError(
                f"loss task {self.task!r} requires {expected_activation} probabilities, "
                f"not activation={self.activation!r}"
            )

        legacy_changed = self._legacy_changed()
        if self.query is not None:
            if self.task != "multiclass":
                raise ConfigError("loss.query requires task: multiclass")
            if self.terms or legacy_changed:
                raise ConfigError(
                    "loss.query cannot be combined with dense loss.terms or non-default "
                    "legacy CE/aux fields"
                )
            return

        resolved = self.resolved_terms()
        kinds = [term.kind for term in resolved]
        if len(kinds) != len(set(kinds)):
            raise ConfigError(f"loss.terms contains duplicate kinds: {kinds}")

        categorical_only = {"cross_entropy", "ohem_cross_entropy"}
        sigmoid_only = {"binary_cross_entropy"}
        if self.task == "multiclass" and any(kind in sigmoid_only for kind in kinds):
            raise ConfigError("binary_cross_entropy requires task: binary or task: multilabel")
        if self.task != "multiclass" and any(kind in categorical_only for kind in kinds):
            raise ConfigError(
                f"{self.task} targets cannot use categorical cross-entropy; "
                "use binary_cross_entropy or another sigmoid-compatible term"
            )
        if self.task == "multiclass":
            for term in resolved:
                if term.kind == "focal" and isinstance(term.alpha, (int, float)):
                    raise ConfigError(
                        "multiclass focal alpha must be a per-class list; scalar alpha is "
                        "only meaningful for binary negative/positive targets"
                    )
        if self.task != "multiclass":
            for term in resolved:
                if getattr(term, "include_background", True) is False:
                    raise ConfigError(
                        "include_background is only meaningful for multiclass softmax targets"
                    )

    def _legacy_changed(self) -> bool:
        return (
            self.aux != "none"
            or self.aux_weight != 0.0
            or self.ce_weight != 1.0
            or self.label_smoothing != 0.0
            or self.class_weights is not None
        )

    def resolved_terms(self) -> list[LossTermSpec]:
        """Return the canonical term list, migrating the legacy CE/aux fields."""
        if self.query is not None:
            raise ConfigError(
                "loss.query is a set-prediction objective and has no dense loss terms"
            )
        if self.terms:
            if self._legacy_changed():
                raise ConfigError(
                    "loss.terms cannot be combined with non-default legacy "
                    "aux/aux_weight/ce_weight/label_smoothing/class_weights fields"
                )
            return list(self.terms)

        terms: list[LossTermSpec] = []
        if self.ce_weight > 0.0:
            terms.append(
                CrossEntropyTerm(
                    kind="cross_entropy",
                    weight=self.ce_weight,
                    label_smoothing=self.label_smoothing,
                    class_weights=self.class_weights,
                )
            )
        if self.aux == "lovasz":
            terms.append(LovaszTerm(kind="lovasz", weight=self.aux_weight))
        elif self.aux == "dice":
            terms.append(DiceTerm(kind="dice", weight=self.aux_weight))
        if not terms:
            raise ConfigError("loss has zero total weight; configure at least one positive term")
        return terms


@dataclass
class OptimConfig:
    backbone_lr: float = 6e-5
    head_lr_mult: float = 10.0
    weight_decay: float = 0.05
    llrd: float = 1.0  # 1.0 disables layer-wise decay; ViTs want 0.65-0.9
    warmup_iters: int = 1500
    warmup_ratio: float = 1e-6
    poly_power: float = 0.9
    min_lr_ratio: float = 0.0
    betas: tuple[float, float] = (0.9, 0.999)
    grad_clip: float | None = 1.0

    def __post_init__(self) -> None:
        if not 0.0 < self.llrd <= 1.0:
            raise ConfigError(f"llrd must be in (0, 1], got {self.llrd}")
        if self.backbone_lr <= 0:
            raise ConfigError(f"backbone_lr must be positive, got {self.backbone_lr}")


@dataclass
class TrainConfig:
    """Iteration-based, never epoch-based, so dataset size does not redefine a run."""

    iters: int = 40000
    batch_size: int = 2  # per device
    accum: int = 1
    num_workers: int = 8
    precision: str = "bf16-mixed"
    ema_decay: float | None = 0.9998
    val_every: int = 4000
    ckpt_every: int = 4000
    seed: int = 0
    devices: int | str = "auto"

    def __post_init__(self) -> None:
        if self.iters <= 0:
            raise ConfigError(f"iters must be positive, got {self.iters}")
        if self.batch_size <= 0 or self.accum <= 0:
            raise ConfigError(
                f"train.batch_size and train.accum must be positive, got "
                f"{self.batch_size}, {self.accum}"
            )
        if self.num_workers < 0:
            raise ConfigError(f"train.num_workers cannot be negative, got {self.num_workers}")
        if self.val_every <= 0 or self.ckpt_every <= 0:
            raise ConfigError(
                f"train.val_every and train.ckpt_every must be positive, got "
                f"{self.val_every}, {self.ckpt_every}"
            )
        if not isinstance(self.precision, str) or not self.precision.strip():
            raise ConfigError("train.precision must be a non-empty Lightning precision string")
        if self.ema_decay is not None and not 0.0 < self.ema_decay < 1.0:
            raise ConfigError(f"ema_decay must be in (0, 1), got {self.ema_decay}")


@dataclass
class EvalConfig:
    sliding_window: bool = True
    window: tuple[int, int] = (1024, 1024)
    stride: tuple[int, int] = (768, 768)
    batch_size: int = 1
    num_workers: int = 4
    tta_scales: list[float] = field(default_factory=list)  # empty = single-scale
    tta_flip: bool = False
    threshold: float = 0.5  # class-1 positive probability threshold for task=binary
    boundary_tolerance_frac: float = 0.0075  # 0.75% of image diagonal
    save_confusion: bool = True

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ConfigError(f"eval.batch_size must be positive, got {self.batch_size}")
        if self.num_workers < 0:
            raise ConfigError(f"eval.num_workers cannot be negative, got {self.num_workers}")
        if any(scale <= 0 for scale in self.tta_scales):
            raise ConfigError(f"eval.tta_scales must be positive, got {self.tta_scales}")
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, (int, float))
            or not math.isfinite(self.threshold)
            or not 0.0 < self.threshold < 1.0
        ):
            raise ConfigError(
                f"eval.threshold must be a finite probability in (0, 1), got {self.threshold!r}"
            )
        if self.boundary_tolerance_frac < 0:
            raise ConfigError(
                "eval.boundary_tolerance_frac cannot be negative, got "
                f"{self.boundary_tolerance_frac}"
            )
        if self.sliding_window:
            if len(self.window) != 2 or len(self.stride) != 2:
                raise ConfigError(
                    f"eval.window and eval.stride must each contain exactly 2 values, got "
                    f"window={self.window}, stride={self.stride}"
                )
            for s, w in zip(self.stride, self.window, strict=True):
                if not 0 < s <= w:
                    raise ConfigError(
                        f"stride {self.stride} must be positive and <= window {self.window}"
                    )


@dataclass
class StageConfig:
    """One stage of a curriculum."""

    name: str
    data: list[DataConfig]
    iters: int | None = None  # overrides TrainConfig.iters
    lr_scale: float = 1.0  # later stages typically 0.1
    init_from: str = "pretrained"  # "pretrained" | "<path/to.ckpt>" | "previous"
    reset_head: bool = False
    freeze: str | None = None  # e.g. "backbone", "backbone.stages.0"
    sample_weights: dict[str, float] | None = None  # for mixed stages

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigError("stage.name must be a non-empty string")
        if not self.data:
            raise ConfigError(f"stage {self.name!r} has no datasets")
        names = [d.name for d in self.data]
        if len(set(names)) != len(names):
            raise ConfigError(f"stage {self.name!r} lists a dataset twice: {names}")
        if self.sample_weights is not None and len(self.data) == 1:
            raise ConfigError(f"stage {self.name!r} sets sample_weights but has one dataset")
        if self.iters is not None and self.iters <= 0:
            raise ConfigError(f"stage {self.name!r} iters must be positive, got {self.iters}")
        if self.lr_scale <= 0:
            raise ConfigError(f"stage {self.name!r} lr_scale must be positive, got {self.lr_scale}")
        if not isinstance(self.init_from, str) or not self.init_from.strip():
            raise ConfigError(f"stage {self.name!r} init_from must be a non-empty string")
        if self.sample_weights is not None:
            expected = set(names)
            actual = set(self.sample_weights)
            if actual != expected:
                raise ConfigError(
                    f"stage {self.name!r} sample_weights keys must exactly match datasets; "
                    f"expected {sorted(expected)}, got {sorted(actual)}"
                )
            if any(
                isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0
                for weight in self.sample_weights.values()
            ):
                raise ConfigError(
                    f"stage {self.name!r} sample_weights must all be positive numbers, "
                    f"got {self.sample_weights}"
                )


# kw_only so `model` can stay required without dictating field order; every
# config arrives as a YAML mapping anyway.
@dataclass(kw_only=True)
class ExperimentConfig:
    """A full curriculum run."""

    name: str
    model: ModelConfig  # required: there is no sensible default architecture
    space: str  # required: every project chooses its own explicit label space
    taxonomy_root: str = "taxonomy"
    output_root: str = "runs"
    optim: OptimConfig = field(default_factory=OptimConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
    eval: EvalConfig = field(default_factory=EvalConfig)
    loss: LossSpec = field(default_factory=LossSpec)
    aug: AugConfigSpec = field(default_factory=AugConfigSpec)
    stages: list[StageConfig] = field(default_factory=list)

    def __post_init__(self) -> None:
        for field_name, value in (
            ("name", self.name),
            ("space", self.space),
            ("taxonomy_root", self.taxonomy_root),
            ("output_root", self.output_root),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"experiment {field_name} must be a non-empty string")
        if not self.stages:
            raise ConfigError(f"experiment {self.name!r} defines no stages")
        seen = set()
        for s in self.stages:
            if s.name in seen:
                raise ConfigError(f"duplicate stage name {s.name!r}")
            seen.add(s.name)
        if self.stages[0].init_from == "previous":
            raise ConfigError("the first stage cannot init_from 'previous'")


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def _coerce(value: Any, typ: Any, path: str) -> Any:
    """Recursively build dataclasses from plain dicts, rejecting unknown keys."""
    origin = get_origin(typ)

    if typ is Any:
        return value

    if origin is Literal:
        allowed = get_args(typ)
        if value not in allowed:
            raise ConfigError(f"{path}: expected one of {allowed}, got {value!r}")
        return value

    # Unwrap Optional/Union (e.g. `DataConfig | None`).  For a real multi-arm
    # union such as ``int | str``, accept the first arm that validates rather
    # than allowing an arbitrary YAML value through unchanged.
    if origin in (Union, UnionType):
        all_arms = get_args(typ)
        arms = [a for a in all_arms if a is not type(None)]
        if value is None and type(None) in all_arms:
            return None
        if len(arms) == 1:
            return _coerce(value, arms[0], path)
        # Dataclass unions used as tagged YAML variants (for example loss
        # terms) are selected by their Literal discriminator. This gives a
        # useful error at ``terms[i].kind`` and prevents the first structurally
        # compatible arm from accepting the wrong variant.
        if isinstance(value, dict) and "kind" in value:
            matches: list[Any] = []
            for arm in arms:
                if not is_dataclass(arm):
                    continue
                discriminator = _hints(cast(type, arm)).get("kind")
                if get_origin(discriminator) is Literal and value["kind"] in get_args(
                    discriminator
                ):
                    matches.append(arm)
            if len(matches) == 1:
                return _coerce(value, matches[0], path)
            if not matches and all(is_dataclass(arm) for arm in arms):
                allowed_kinds = sorted(
                    literal
                    for arm in arms
                    for literal in get_args(_hints(cast(type, arm)).get("kind"))
                )
                raise ConfigError(
                    f"{path}.kind: expected one of {tuple(allowed_kinds)}, got {value['kind']!r}"
                )
        for arm in arms:
            try:
                return _coerce(value, arm, path)
            except ConfigError:
                pass
        expected = " | ".join(getattr(arm, "__name__", str(arm)) for arm in all_arms)
        raise ConfigError(f"{path}: expected {expected}, got {type(value).__name__}")

    if is_dataclass(typ):
        return from_dict(cast(type, typ), value, path)

    if origin is list:
        (inner,) = get_args(typ) or (Any,)
        if not isinstance(value, list):
            raise ConfigError(f"{path}: expected a list, got {type(value).__name__}")
        return [_coerce(v, inner, f"{path}[{i}]") for i, v in enumerate(value)]

    if origin is tuple:
        args = get_args(typ)
        if not isinstance(value, (list, tuple)):
            raise ConfigError(f"{path}: expected a sequence, got {type(value).__name__}")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_coerce(v, args[0], f"{path}[{i}]") for i, v in enumerate(value))
        if args and len(args) != len(value):
            raise ConfigError(f"{path}: expected {len(args)} items, got {len(value)}")
        return tuple(
            _coerce(v, args[i] if args else Any, f"{path}[{i}]") for i, v in enumerate(value)
        )

    if origin is dict:
        if not isinstance(value, dict):
            raise ConfigError(f"{path}: expected a mapping, got {type(value).__name__}")
        key_typ, value_typ = get_args(typ) or (Any, Any)
        return {
            _coerce(k, key_typ, f"{path}.<key>"): _coerce(v, value_typ, f"{path}.{k}")
            for k, v in value.items()
        }

    # YAML already parses scalar types, so reject incompatible values rather
    # than applying surprising conversions (``bool`` is notably an ``int``
    # subclass in Python).  Integers are safe inputs for float-valued fields.
    if typ is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{path}: expected bool, got {type(value).__name__}")
        return value
    if typ is int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ConfigError(f"{path}: expected int, got {type(value).__name__}")
        return value
    if typ is float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ConfigError(f"{path}: expected float, got {type(value).__name__}")
        return float(value)
    if typ is str:
        if not isinstance(value, str):
            raise ConfigError(f"{path}: expected str, got {type(value).__name__}")
        return value

    return value


_HINTS: dict[type, dict[str, Any]] = {}


def _hints(cls: type) -> dict[str, Any]:
    """Resolved type hints. `from __future__ import annotations` makes
    ``dataclasses.Field.type`` a string, so it cannot be introspected directly."""
    if cls not in _HINTS:
        _HINTS[cls] = get_type_hints(cls)
    return _HINTS[cls]


def from_dict(cls: type[T], data: dict[str, Any], path: str = "") -> T:
    """Instantiate a dataclass from a dict, failing loudly on unknown keys."""
    if not isinstance(data, dict):
        raise ConfigError(f"{path or cls.__name__}: expected a mapping, got {type(data).__name__}")

    known = {f.name for f in fields(cast(Any, cls))}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(
            f"{path or cls.__name__}: unknown key(s) {unknown}. Valid keys: {sorted(known)}. "
            f"A typo here would be silently ignored, so it is fatal instead."
        )

    hints = _hints(cls)
    kwargs: dict[str, Any] = {}
    for name in known:
        if name not in data:
            continue
        kwargs[name] = _coerce(data[name], hints[name], f"{path}.{name}" if path else name)
    try:
        return cls(**kwargs)
    except TypeError as exc:  # missing required field -> a config error, not a crash
        raise ConfigError(f"{path or cls.__name__}: {exc}") from exc


def deep_merge(base: dict, override: dict) -> dict:
    """Recursive dict merge; lists are replaced wholesale, not concatenated."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_yaml(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"config not found: {p}")
    data = yaml.safe_load(p.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{p}: top level must be a mapping")
    return data


def load_experiment(paths: list[Path | str], overrides: dict | None = None) -> ExperimentConfig:
    """Merge YAML files left to right, apply overrides, then validate."""
    merged: dict[str, Any] = {}
    for p in paths:
        merged = deep_merge(merged, load_yaml(p))
    if overrides:
        merged = deep_merge(merged, overrides)
    return from_dict(ExperimentConfig, merged)


def to_dict(cfg: Any) -> Any:
    """Dataclass -> plain JSON-able dict."""
    if is_dataclass(cfg):
        return {f.name: to_dict(getattr(cfg, f.name)) for f in fields(cfg)}
    if isinstance(cfg, (list, tuple)):
        return [to_dict(v) for v in cfg]
    if isinstance(cfg, dict):
        return {k: to_dict(v) for k, v in cfg.items()}
    return cfg


def config_hash(cfg: Any) -> str:
    """Stable short hash of a config, recorded in results.json."""
    blob = json.dumps(to_dict(cfg), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def replace(cfg: T, **changes: Any) -> T:
    """dataclasses.replace, re-running validation."""
    return cast(T, dataclasses.replace(cast(Any, cfg), **changes))
