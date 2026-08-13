"""The one place an ``arch`` string turns into a model. No registry, no decorators.

============================  ==================================================
arch                          default weights / notes
============================  ==================================================
segformer_b0                  nvidia/mit-b0, ImageNet encoder, fresh decode head
segformer_b2                  nvidia/mit-b2
segformer_b5                  nvidia/mit-b5
upernet_convnext              openmmlab/upernet-convnext-small (ADE20k)
eomt_large                    tue-mps/coco_panoptic_eomt_large_640; fixed 640 grid
eomt_dinov3_large             tue-mps/eomt-dinov3-coco-panoptic-large-640; 640 grid
mask2former_dinov3            BLOCKED: vanilla DINOv3 has no feature pyramid;
                              requires Meta's DINOv3 Adapter implementation
hrnet_w48_ocr                 timm hrnet_w48 (ImageNet) + models.heads.OCRHead
deeplabv3plus_r101            smp DeepLabV3Plus, resnet101/imagenet
upernet_r101                  smp UPerNet, resnet101/imagenet
smp                           reviewed smp decoder + explicit encoder/weights
hf_auto                       validated AutoModelForSemanticSegmentation checkpoint;
                              model id and safe module layout required
native                        Segmentary-native typed backbone -> neck -> dense-head
                              composition, with optional auxiliary dense heads
============================  ==================================================

``cfg.checkpoint`` overrides the default HuggingFace id, or -- for the two legacy
smp aliases, which have no HF id -- the smp encoder name.  The generic ``smp``
path instead records ``smp_arch``, ``encoder_name`` and ``encoder_weights`` as
separate typed fields.

Every path that requests pretrained weights either loads them or raises. The SMP
path can train from scratch only when ``encoder_weights: scratch`` is explicit;
there is no random-init fallback after a failed load. Such a fallback would make
an expired token look like a bad hyperparameter choice instead of a load error.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, TypeVar, cast

from torch import nn

from ..config import ModelConfig, SMPDecoder
from .hrnet_ocr import HRNetOCR
from .mask_classification import MaskClassWrapper
from .wrappers import HFDenseWrapper, SegmentationModel, SMPWrapper

SEGFORMER_ARCHS = {
    "segformer_b0": "nvidia/mit-b0",
    "segformer_b2": "nvidia/mit-b2",
    "segformer_b5": "nvidia/mit-b5",
}
SMP_ARCHS = ("deeplabv3plus_r101", "upernet_r101")
SMP_DECODERS: tuple[SMPDecoder, ...] = (
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
)
VALID_ARCHS = (
    *SEGFORMER_ARCHS,
    "upernet_convnext",
    "eomt_large",
    "eomt_dinov3_large",
    "mask2former_dinov3",
    "hrnet_w48_ocr",
    "hf_auto",
    "native",
    "smp",
    *SMP_ARCHS,
)

UPERNET_CONVNEXT_ID = "openmmlab/upernet-convnext-small"
EOMT_ID = "tue-mps/coco_panoptic_eomt_large_640"
EOMT_DINOV3_ID = "tue-mps/eomt-dinov3-coco-panoptic-large-640"
_EOMT_BACKBONE = ("embeddings", "layers", "layernorm")
_EOMT_HEAD = ("query", "upscale_block", "mask_head", "class_predictor")

_T = TypeVar("_T")


def _load(loader: type[_T], model_id: str, **kwargs: object) -> _T:
    """``from_pretrained`` with a gated-repo failure turned into instructions."""
    try:
        return cast(_T, cast(Any, loader).from_pretrained(model_id, **kwargs))
    except OSError as exc:
        raise ValueError(
            f"could not load {model_id!r}: {exc}\n"
            f"If this is a gated repository (every facebook/dinov3-* checkpoint is), "
            f"request access at https://huggingface.co/{model_id} and then run "
            f"`huggingface-cli login` with a token that has access. Training would "
            f"otherwise start from random weights, which is never what you meant."
        ) from exc


def _segformer(model_id: str, cfg: ModelConfig, num_classes: int) -> SegmentationModel:
    from transformers import SegformerForSemanticSegmentation

    extra = {} if cfg.drop_path is None else {"drop_path_rate": cfg.drop_path}
    model = _load(
        SegformerForSemanticSegmentation,
        model_id,
        num_labels=num_classes,
        ignore_mismatched_sizes=True,
        **extra,
    )
    # nvidia/mit-* ship an encoder only, so decode_head is fresh by construction.
    return HFDenseWrapper(
        model, num_classes, backbone_path="segformer", head_paths=("decode_head",)
    )


def _upernet_convnext(model_id: str, cfg: ModelConfig, num_classes: int) -> SegmentationModel:
    from transformers import UperNetForSemanticSegmentation

    if cfg.drop_path is not None:
        raise ValueError(
            "upernet_convnext does not accept drop_path through this factory; the rate lives "
            "on the nested backbone config and would be silently dropped"
        )
    # UperNet runs its FCN auxiliary head on every forward, but we return only the
    # decode head's logits, so those ~2.6M parameters would burn compute and then
    # receive no gradient -- which DDP reports as an unused-parameter crash, not as
    # a wasted branch. engine.losses has no slot for a second head, so drop it.
    model = _load(
        UperNetForSemanticSegmentation,
        model_id,
        num_labels=num_classes,
        ignore_mismatched_sizes=True,
        use_auxiliary_head=False,
    )
    return HFDenseWrapper(model, num_classes, backbone_path="backbone", head_paths=("decode_head",))


def _eomt_native_size(model: nn.Module) -> tuple[int, int]:
    """The single input resolution an EoMT checkpoint can run at.

    Read off the loaded checkpoint rather than assumed: ``predict()`` reshapes the
    patch tokens with ``self.grid_size``, frozen at export time, so a 512-export
    would otherwise die inside transformers on an unreadable view error.
    """
    patch = cast(Any, model.config).patch_size
    if not isinstance(patch, int):
        raise ValueError(
            f"EoMT checkpoint has a non-scalar patch_size {patch!r}; the native input size "
            f"cannot be derived and inference would fail on a token-grid reshape"
        )
    grid_h, grid_w = cast(Any, model.grid_size)
    return (grid_h * patch, grid_w * patch)


def _eomt(arch: str, model_id: str, cfg: ModelConfig, num_classes: int) -> SegmentationModel:
    from transformers import EomtDinov3ForUniversalSegmentation, EomtForUniversalSegmentation

    loader = (
        EomtForUniversalSegmentation if arch == "eomt_large" else EomtDinov3ForUniversalSegmentation
    )
    extra = {} if cfg.drop_path is None else {"drop_path_rate": cfg.drop_path}
    model = _load(loader, model_id, num_labels=num_classes, ignore_mismatched_sizes=True, **extra)
    backbone = _EOMT_BACKBONE + (("rope_embeddings",) if arch == "eomt_dinov3_large" else ())
    return MaskClassWrapper(
        model,
        num_classes,
        backbone_paths=backbone,
        head_paths=_EOMT_HEAD,
        native_size=_eomt_native_size(model),
    )


def assemble_mask2former(backbone: nn.Module, num_classes: int) -> SegmentationModel:
    """Wrap a pretrained backbone in a fresh Mask2Former.

    Split out from the gated download so the wiring can be exercised in tests with
    a small randomly initialised backbone.

    Args:
        backbone: any transformers backbone exposing ``.config`` and ``.channels``.
        num_classes: canonical class count.
    """
    from transformers import Mask2FormerConfig, Mask2FormerForUniversalSegmentation

    config = Mask2FormerConfig(backbone_config=cast(Any, backbone.config))
    config.num_labels = num_classes
    model = Mask2FormerForUniversalSegmentation(config)
    encoder = model.model.pixel_level_module.encoder
    if list(cast(Any, encoder).channels) != list(cast(Any, backbone).channels):
        raise ValueError(
            f"backbone channels {backbone.channels} do not match the pixel decoder's "
            f"expectation {encoder.channels}"
        )
    model.model.pixel_level_module.encoder = backbone
    return MaskClassWrapper(
        model,
        num_classes,
        backbone_paths=("model.pixel_level_module.encoder",),
        head_paths=("pixel_level_module.decoder", "transformer_module", "class_predictor"),
        native_size=None,
        request_auxiliary_logits=True,
    )


def _mask2former_dinov3() -> SegmentationModel:
    raise ValueError(
        "mask2former_dinov3 is blocked: Transformers Mask2Former supports a Swin-style "
        "hierarchical backbone with stride-4/8/16/32 feature maps, while a plain DINOv3 "
        "ViT produces four stride-16 maps. A same-shape forward pass is therefore not "
        "evidence that this is a valid DINOv3 segmentation arm. Meta's official DINOv3 "
        "Mask2Former baseline uses DINOv3_Adapter with a SpatialPriorModule to construct "
        "the required feature pyramid. Implement and verify that adapter before enabling "
        "this architecture arm."
    )


def _smp(arch: str, cfg: ModelConfig, num_classes: int) -> SegmentationModel:
    import segmentation_models_pytorch as smp
    from segmentation_models_pytorch.encoders import get_preprocessing_params

    if cfg.drop_path is not None:
        raise ValueError(f"{arch} has no stochastic depth; drop_path would be ignored")

    decoder: SMPDecoder
    if arch == "smp":
        # ModelConfig has already proved these values are present and allowlisted.
        assert cfg.smp_arch is not None and cfg.encoder_name is not None
        decoder = cfg.smp_arch
        encoder = cfg.encoder_name
        encoder_weights = None if cfg.encoder_weights == "scratch" else cfg.encoder_weights
    else:
        decoder = "DeepLabV3Plus" if arch == "deeplabv3plus_r101" else "UPerNet"
        encoder = cfg.checkpoint or "resnet101"
        encoder_weights = "imagenet"

    # Keep this exhaustive and local instead of creating a mutable model
    # registry or resolving a config string with getattr().
    match decoder:
        case "Unet":
            ctor = smp.Unet
        case "UnetPlusPlus":
            ctor = smp.UnetPlusPlus
        case "FPN":
            ctor = smp.FPN
        case "PSPNet":
            ctor = smp.PSPNet
        case "DeepLabV3":
            ctor = smp.DeepLabV3
        case "DeepLabV3Plus":
            ctor = smp.DeepLabV3Plus
        case "MAnet":
            ctor = smp.MAnet
        case "Linknet":
            ctor = smp.Linknet
        case "PAN":
            ctor = smp.PAN
        case "UPerNet":
            ctor = smp.UPerNet

    if encoder_weights is None:
        preprocessing = {
            "input_space": "RGB",
            "input_range": [0, 1],
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        }
        normalization_source = "imagenet_scratch_default"
    else:
        try:
            preprocessing = get_preprocessing_params(encoder, pretrained=encoder_weights)
        except Exception as exc:
            raise ValueError(
                f"could not resolve preprocessing for SMP encoder {encoder!r} with "
                f"weights {encoder_weights!r}: {exc}"
            ) from exc
        normalization_source = "smp_encoder_settings"

    input_range = preprocessing.get("input_range")
    if input_range not in ([0, 1], (0, 1)):
        raise ValueError(
            f"SMP encoder {encoder!r}/{encoder_weights!r} uses unsupported input_range="
            f"{input_range!r}; Segmentary currently requires uint8 images rescaled to [0, 1]"
        )
    input_space = preprocessing.get("input_space")
    if not isinstance(input_space, str) or input_space.upper() not in ("RGB", "BGR"):
        raise ValueError(
            f"SMP encoder {encoder!r}/{encoder_weights!r} uses unsupported input_space="
            f"{input_space!r}; expected RGB or BGR"
        )

    def triplet(name: str) -> tuple[float, float, float]:
        raw = preprocessing.get(name)
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 3:
            raise ValueError(
                f"SMP encoder {encoder!r}/{encoder_weights!r} has invalid {name}={raw!r}"
            )
        values = tuple(float(value) for value in cast(Any, raw))
        if any(not math.isfinite(value) for value in values) or (
            name == "std" and any(value <= 0.0 for value in values)
        ):
            raise ValueError(
                f"SMP encoder {encoder!r}/{encoder_weights!r} has invalid {name}={raw!r}"
            )
        return values  # type: ignore[return-value]

    # Do not catch a failed pretrained-weight download and retry with ``None``:
    # that would turn a requested pretrained run into an unreported scratch run.
    model = ctor(
        encoder_name=encoder,
        encoder_weights=encoder_weights,
        in_channels=3,
        classes=num_classes,
    )
    return SMPWrapper(
        model,
        num_classes,
        input_mean=triplet("mean"),
        input_std=triplet("std"),
        input_channel_order=input_space.lower(),
        input_normalization_source=normalization_source,
        inactive_parameter_paths=tuple(cfg.inactive_parameter_paths),
    )


def build_model(cfg: ModelConfig, num_classes: int) -> SegmentationModel:
    """Build the architecture named by ``cfg.arch`` with a ``num_classes`` head.

    Args:
        cfg: model config; ``checkpoint`` overrides the default weights.
        num_classes: canonical class count from the label space.
    """
    arch = cfg.arch
    if cfg.head != "unified_head":
        # Building a unified head anyway while train.py prints head=per_stage_head
        # would produce a whole ablation table for an experiment nobody ran.
        raise ValueError(
            f"model.head={cfg.head!r} is not implemented: every arch here has one classifier "
            f"over the canonical label space. Use unified_head, and re-initialise it between "
            f"curriculum stages with the stage's reset_head flag."
        )

    if arch in SEGFORMER_ARCHS:
        return _segformer(cfg.checkpoint or SEGFORMER_ARCHS[arch], cfg, num_classes)

    if arch == "upernet_convnext":
        return _upernet_convnext(cfg.checkpoint or UPERNET_CONVNEXT_ID, cfg, num_classes)

    if arch == "eomt_large":
        return _eomt(arch, cfg.checkpoint or EOMT_ID, cfg, num_classes)

    if arch == "eomt_dinov3_large":
        return _eomt(arch, cfg.checkpoint or EOMT_DINOV3_ID, cfg, num_classes)

    if arch == "hf_auto":
        # Kept in its own module so the generic, deliberately strict loading
        # audit does not complicate the stable hand-written architecture arms.
        from .hf_auto import build_hf_auto

        return build_hf_auto(cfg, num_classes)

    if arch == "native":
        # ModelConfig proves the nested specification exists and rejects every
        # unrelated top-level option. The component builders then exhaustively
        # dispatch each typed ``kind`` without forwarding arbitrary kwargs.
        from .components import build_native_model

        native = cfg.native
        if native is None:  # Defensive for direct/non-dataclass callers.
            raise ValueError("arch='native' requires model.native")
        return build_native_model(
            native.backbone,
            native.neck,
            native.head,
            cast(Any, native.auxiliary_heads),
            num_classes,
            task=native.task,
        )

    if arch == "mask2former_dinov3":
        return _mask2former_dinov3()

    if arch == "hrnet_w48_ocr":
        if cfg.checkpoint is not None:
            raise ValueError(
                "hrnet_w48_ocr takes its weights from timm, not from a checkpoint id; "
                "load a finetuned state_dict through the stage's init_from instead"
            )
        if cfg.drop_path is not None:
            raise ValueError(
                "hrnet_w48_ocr has no stochastic depth: timm's HighResolutionNet takes no "
                "drop_path_rate and silently swallows the keyword, so the run would record a "
                "regularisation setting it never applied"
            )
        return HRNetOCR(num_classes, backbone_name="hrnet_w48")

    if arch == "smp" or arch in SMP_ARCHS:
        return _smp(arch, cfg, num_classes)

    raise ValueError(f"unknown arch {arch!r}. Valid archs: {sorted(VALID_ARCHS)}")
