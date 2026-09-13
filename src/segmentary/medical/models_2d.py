"""Offline, random-initialized 2D/2.5D segmentation architectures for CT.

These adapters reuse architectures, never published weights. ``profile=smoke``
explicitly selects reduced capacity for execution tests where available; it is
not a paper baseline. All spatial adaptation is padding/cropping, not CT scaling.
Query models retain their native Hungarian objective. Auxiliary and boundary
heads remain supervised; their declared CT objectives are not Cityscapes recipes.
"""

from __future__ import annotations

import copy
import math
from typing import Any, cast

import torch
import torch.nn.functional as F
from torch import Tensor, nn

MODEL_NAMES = (
    "unet_2d",
    "unet_plus_plus",
    "fpn",
    "deeplabv3_plus",
    "hrnet_ocr",
    "convnext_upernet",
    "segformer_b0",
    "segformer_b2",
    "swin_upernet",
    "dpt",
    "maskformer",
    "mask2former",
    "bisenetv2",
    "ddrnet",
    "pidnet",
    "lraspp",
)

_VARIANTS = {
    "unet_2d": ("U-Net", "ResNet-34 encoder / SMP U-Net decoder", "ResNet-18 encoder"),
    "unet_plus_plus": ("U-Net++", "ResNet-34 encoder / SMP nested decoder", "ResNet-18 encoder"),
    "fpn": ("FPN", "ResNet-34 encoder / SMP FPN decoder", "ResNet-18 encoder"),
    "deeplabv3_plus": ("DeepLabV3+", "ResNet-50 encoder / output stride 16", "ResNet-18 encoder"),
    "hrnet_ocr": ("HRNet + OCR", "HRNet-W32 / OCR width 512", "HRNet-W18 / OCR width 64"),
    "convnext_upernet": (
        "ConvNeXt + UPerNet",
        "ConvNeXt-Tiny / UPerNet width 512",
        "four stages [1,1,1,1], widths [16,32,64,128] / head 32",
    ),
    "segformer_b0": ("SegFormer", "MiT-B0 / MLP decoder 256", "same B0 capacity"),
    "segformer_b2": ("SegFormer", "MiT-B2 / MLP decoder 768", "same B2 capacity"),
    "swin_upernet": (
        "Swin + UPerNet",
        "Swin-Tiny / UPerNet width 512",
        "Swin embed 32, depths [1,1,1,1], heads [1,2,4,8], window 2 / head 32",
    ),
    "dpt": (
        "DPT",
        "ViT-Base, 12 layers, width 768 / DPT reassembly and fusion",
        "4 layers, width 96, 4 attention heads / fusion 32",
    ),
    "maskformer": (
        "MaskFormer",
        "Swin-Tiny / DETR 6-layer decoder, width 256, 100 queries",
        "small Swin / 2-layer decoder, width 64, 12 queries",
    ),
    "mask2former": (
        "Mask2Former",
        "Swin-Tiny / deformable pixel decoder and masked attention, 100 queries",
        "small Swin / 1 encoder and 2 decoder layers, width 64, 12 queries",
    ),
    "bisenetv2": (
        "BiSeNetV2",
        "CoinCheung implementation with four booster heads",
        "same capacity",
    ),
    "ddrnet": ("DDRNet", "DDRNet-23-slim / planes 32", "same block graph / planes 16"),
    "pidnet": ("PIDNet", "PIDNet-S / planes 32", "same PIDNet-S block graph / planes 16"),
    "lraspp": ("LR-ASPP", "MobileNetV3-Large / torchvision LR-ASPP", "same capacity"),
}

_SOURCES = {
    "bisenetv2": "https://github.com/CoinCheung/BiSeNet/blob/6b4b67a8e3eb0cc23b3d7a94843a7c3c11dedca8/lib/models/bisenetv2.py",
    "ddrnet": "https://github.com/ydhongHIT/DDRNet/blob/de0db317c5af4b0946231f475cf74ca4f51b8ac2/segmentation/DDRNet_23_slim.py",
    "pidnet": "https://github.com/XuJiacong/PIDNet/blob/4c158cf24ce432f0a8cb43364fae38d93cee0dc3/models/pidnet.py",
}


def model_metadata(name: str) -> dict[str, Any]:
    """Return architecture, objective, spatial and initialization provenance."""
    if name not in MODEL_NAMES:
        raise ValueError(f"unknown 2D model {name!r}; choose one of {MODEL_NAMES}")
    family, standard, smoke = _VARIANTS[name]
    loss: dict[str, Any] = {"name": "common_dice_ce", "custom_training_loss": False}
    if name in ("convnext_upernet", "swin_upernet", "dpt", "hrnet_ocr", "ddrnet"):
        loss = {
            "name": "main_ce_plus_auxiliary_ce",
            "main_weight": 1.0,
            "auxiliary_weight": 0.4,
            "custom_training_loss": True,
        }
    if name == "bisenetv2":
        loss = {
            "name": "main_ce_plus_four_booster_ce",
            "main_weight": 1.0,
            "auxiliary_weights": [1.0] * 4,
            "custom_training_loss": True,
        }
    if name == "pidnet":
        loss = {
            "name": "ct_ce_aux_ce_boundary_bce",
            "main_weight": 1.0,
            "auxiliary_weight": 0.4,
            "boundary_weight": 1.0,
            "boundary_target": "both sides of four-neighbor semantic transitions",
            "boundary_bce": "class-balanced when both labels present; unweighted otherwise",
            "paper_recipe": False,
            "custom_training_loss": True,
        }
    if name in ("maskformer", "mask2former"):
        loss = {
            "name": "native_hungarian_query_loss",
            "custom_training_loss": True,
            "mask_weight": 20.0 if name == "maskformer" else 5.0,
            "dice_weight": 1.0 if name == "maskformer" else 5.0,
            "class_weight": 1.0 if name == "maskformer" else 2.0,
            "no_object_weight": 0.1,
            "auxiliary_decoder_supervision": True,
            "target_unit": "one mask per present semantic class, including background",
        }
    source = _SOURCES.get(name)
    if source is None:
        if name in ("unet_2d", "unet_plus_plus", "fpn", "deeplabv3_plus"):
            source = "segmentation-models-pytorch==0.5.0"
        elif name == "hrnet_ocr":
            source = "timm==1.0.28 HRNet + Segmentary OCR"
        elif name == "lraspp":
            source = "torchvision==0.26.0"
        else:
            source = "transformers==5.15.0, locally constructed config"
    return copy.deepcopy(
        {
            "name": name,
            "family": family,
            "dimensions": 2,
            "spatial_dims": 2,
            "initialization": "scratch",
            "dead_modules": "Unused classification final norms removed; DPT first fusion unused skip unit removed",
            "pretrained": False,
            "source": source,
            "standard_variant": standard,
            "smoke_variant": smoke,
            "options": {"profile": {"default": "standard", "choices": ["standard", "smoke"]}},
            "default_patch_size": [128, 128],
            "smoke_options": {"profile": "smoke"},
            "smoke_patch_size": [64, 64],
            "smoke_batch_size": 2,
            "min_patch_size": [64, 64],
            "patch_divisibility": [32, 32],
            "square_padding": name == "dpt",
            "inference_padding": "right/bottom zero padding then crop to input shape",
            "training_batch_minimum": 2 if name not in ("maskformer", "mask2former") else 1,
            "training_loss": loss,
        }
    )


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _replace_input_conv(container: nn.Module, key: str, channels: int) -> None:
    old: Any = getattr(container, key)
    if not isinstance(old, nn.Conv2d) or old.groups != 1:
        raise TypeError("expected ordinary input Conv2d")
    new = nn.Conv2d(
        channels,
        old.out_channels,
        (old.kernel_size[0], old.kernel_size[1]),
        (old.stride[0], old.stride[1]),
        old.padding if isinstance(old.padding, str) else (old.padding[0], old.padding[1]),
        (old.dilation[0], old.dilation[1]),
        bias=old.bias is not None,
    )
    nn.init.kaiming_normal_(new.weight, mode="fan_out", nonlinearity="relu")
    if new.bias is not None:
        nn.init.zeros_(new.bias)
    setattr(container, key, new)


class _Adapter(nn.Module):
    def __init__(self, model: nn.Module, channels: int, classes: int, *, square: bool = False):
        super().__init__()
        self.model = model
        self.in_channels = channels
        self.num_classes = classes
        self.square = square

    def _input(self, images: Tensor) -> tuple[Tensor, tuple[int, int]]:
        if images.ndim != 4 or images.shape[1] != self.in_channels:
            raise ValueError(f"expected N,{self.in_channels},H,W input")
        if images.shape[0] < 1 or min(images.shape[-2:]) < 1 or not images.is_floating_point():
            raise ValueError("input must be a nonempty floating-point batch")
        height, width = int(images.shape[-2]), int(images.shape[-1])
        target_h, target_w = (max(64, math.ceil(v / 32) * 32) for v in (height, width))
        if self.square:
            target_h = target_w = max(target_h, target_w)
        return F.pad(images, (0, target_w - width, 0, target_h - height)), (height, width)

    def _logits(self, raw: Tensor, padded: Tensor, original: tuple[int, int]) -> Tensor:
        if raw.ndim != 4 or raw.shape[1] != self.num_classes:
            raise ValueError("architecture returned invalid semantic logits")
        raw = F.interpolate(raw, size=padded.shape[-2:], mode="bilinear", align_corners=False)
        return raw[..., : original[0], : original[1]]

    def _targets(self, targets: Tensor, images: Tensor, padded: Tensor) -> Tensor:
        if targets.dtype != torch.long or targets.shape != images.shape[:1] + images.shape[2:]:
            raise ValueError("targets must be int64 N,H,W matching input")
        if bool(((targets < 0) | (targets >= self.num_classes)).any()):
            raise ValueError("targets must be fully annotated canonical semantic class IDs")
        return F.pad(
            targets,
            (0, padded.shape[-1] - targets.shape[-1], 0, padded.shape[-2] - targets.shape[-2]),
            value=255,
        )

    def forward(self, images: Tensor) -> Tensor:
        padded, original = self._input(images)
        out = self.model(padded)
        raw = (
            out
            if isinstance(out, Tensor)
            else out["out"]
            if isinstance(out, dict) and "out" in out
            else out.logits
        )
        return self._logits(raw, padded, original)


class _HFAuxAdapter(_Adapter):
    def training_loss(self, images: Tensor, targets: Tensor) -> Tensor:
        padded, _ = self._input(images)
        labels = self._targets(targets, images, padded)
        return self.model(pixel_values=padded, labels=labels).loss


class _QueryAdapter(_Adapter):
    def forward(self, images: Tensor) -> Tensor:
        padded, original = self._input(images)
        out = self.model(pixel_values=padded, output_hidden_states=True)
        classes = out.class_queries_logits.softmax(-1)[..., :-1]
        masks = F.interpolate(
            out.masks_queries_logits, size=padded.shape[-2:], mode="bilinear", align_corners=False
        ).sigmoid()
        score = torch.einsum("bqc,bqhw->bchw", classes, masks)
        # Scores are nonnegative sums, not logits. Their log produces the same
        # semantic argmax and allows normalized probabilities downstream.
        logits = score.clamp_min(torch.finfo(score.dtype).tiny).log()
        return logits[..., : original[0], : original[1]]

    def training_loss(self, images: Tensor, targets: Tensor) -> Tensor:
        padded, _ = self._input(images)
        self._targets(targets, images, padded)
        if padded.shape != images.shape:
            raise ValueError(
                "query training needs H,W >=64 and divisible by 32; padded pixels lack annotations"
            )
        classes = [item.unique(sorted=True) for item in targets]
        masks = [
            (target.unsqueeze(0) == labels[:, None, None]).float()
            for target, labels in zip(targets, classes, strict=True)
        ]
        # Native loss performs Hungarian matching and supervises all decoder
        # layers. No image processor, checkpoint, or remote configuration needed.
        return self.model(
            pixel_values=images, mask_labels=masks, class_labels=classes, output_hidden_states=True
        ).loss


class _AuxAdapter(_Adapter):
    def __init__(self, *args: Any, kind: str, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.kind = kind

    def forward(self, images: Tensor) -> Tensor:
        padded, original = self._input(images)
        outputs = self.model(padded)
        primary = outputs[1] if self.kind == "pidnet" else outputs[0]
        return self._logits(primary, padded, original)

    def training_loss(self, images: Tensor, targets: Tensor) -> Tensor:
        padded, original = self._input(images)
        self._targets(targets, images, padded)
        outputs = self.model(padded)
        primary_index = 1 if self.kind == "pidnet" else 0
        loss = F.cross_entropy(self._logits(outputs[primary_index], padded, original), targets)
        if self.kind == "pidnet":
            loss = loss + 0.4 * F.cross_entropy(self._logits(outputs[0], padded, original), targets)
            boundary = semantic_boundaries(targets).float()
            boundary_logits = F.interpolate(
                outputs[2], size=padded.shape[-2:], mode="bilinear", align_corners=False
            )
            boundary_logits = boundary_logits[:, 0, : original[0], : original[1]]
            positives = boundary.sum()
            negatives = boundary.numel() - positives
            # No zero loss for empty-boundary patches: both degenerate cases
            # receive ordinary BCE so the boundary classifier remains supervised.
            if positives > 0 and negatives > 0:
                weight = torch.where(boundary.bool(), negatives, positives) / boundary.numel()
                boundary_loss = F.binary_cross_entropy_with_logits(
                    boundary_logits, boundary, weight=weight
                )
            else:
                boundary_loss = F.binary_cross_entropy_with_logits(boundary_logits, boundary)
            return loss + boundary_loss
        auxiliary_weight = 1.0 if self.kind == "bisenetv2" else 0.4
        return loss + sum(
            auxiliary_weight * F.cross_entropy(self._logits(aux, padded, original), targets)
            for aux in outputs[1:]
        )


def semantic_boundaries(targets: Tensor) -> Tensor:
    """Both pixels adjacent to a four-neighbor class transition; no outer border."""
    result = torch.zeros_like(targets, dtype=torch.bool)
    horizontal = targets[..., 1:] != targets[..., :-1]
    vertical = targets[..., 1:, :] != targets[..., :-1, :]
    result[..., 1:] |= horizontal
    result[..., :-1] |= horizontal
    result[..., 1:, :] |= vertical
    result[..., :-1, :] |= vertical
    return result


class _HRNet(nn.Module):
    def __init__(self, channels: int, classes: int, smoke: bool):
        super().__init__()
        import timm

        from segmentary.models.heads import OCRHead

        self.trunk = timm.create_model(
            "hrnet_w18" if smoke else "hrnet_w32",
            pretrained=False,
            in_chans=channels,
            num_classes=0,
        )
        for key in ("incre_modules", "downsamp_modules"):
            setattr(self.trunk, key, None)
        for key in ("final_layer", "global_pool", "classifier"):
            setattr(self.trunk, key, nn.Identity())
        widths = sum(cast(Any, self.trunk).stage4_cfg["num_channels"])
        self.head = OCRHead(
            widths, classes, ocr_channels=64 if smoke else 512, key_channels=32 if smoke else 256
        )

    def forward(self, images: Tensor) -> tuple[Tensor, Tensor]:
        from segmentary.models.heads import concat_multi_scale

        features = cast(Any, self.trunk).forward_features(images)
        return self.head(concat_multi_scale(features))


def _swin(channels: int, smoke: bool) -> Any:
    from transformers import SwinConfig

    config = SwinConfig(
        num_channels=channels,
        embed_dim=32 if smoke else 96,
        depths=[1, 1, 1, 1] if smoke else [2, 2, 6, 2],
        num_heads=[1, 2, 4, 8] if smoke else [3, 6, 12, 24],
        window_size=2 if smoke else 7,
    )
    config.out_features = ["stage1", "stage2", "stage3", "stage4"]
    return config


def _hf(name: str, channels: int, classes: int, patch: tuple[int, int], smoke: bool) -> nn.Module:
    from transformers import (
        ConvNextConfig,
        DetrConfig,
        DPTConfig,
        DPTForSemanticSegmentation,
        Mask2FormerConfig,
        Mask2FormerForUniversalSegmentation,
        MaskFormerConfig,
        MaskFormerForInstanceSegmentation,
        SegformerConfig,
        SegformerForSemanticSegmentation,
        UperNetConfig,
        UperNetForSemanticSegmentation,
    )

    config: Any
    if name.startswith("segformer"):
        b2 = name == "segformer_b2"
        config = SegformerConfig(
            num_channels=channels,
            hidden_sizes=[64, 128, 320, 512] if b2 else [32, 64, 160, 256],
            depths=[3, 4, 6, 3] if b2 else [2, 2, 2, 2],
            decoder_hidden_size=768 if b2 else 256,
        )
        config.num_labels = classes
        return _Adapter(SegformerForSemanticSegmentation(config), channels, classes)
    if name in ("convnext_upernet", "swin_upernet"):
        backbone = _swin(channels, smoke)
        if name == "convnext_upernet":
            backbone = ConvNextConfig(
                num_channels=channels,
                depths=[1, 1, 1, 1] if smoke else [3, 3, 9, 3],
                hidden_sizes=[16, 32, 64, 128] if smoke else [96, 192, 384, 768],
            )
            backbone.out_features = ["stage1", "stage2", "stage3", "stage4"]
        config = UperNetConfig(
            backbone_config=backbone,
            hidden_size=32 if smoke else 512,
            auxiliary_channels=32 if smoke else 256,
        )
        config.num_labels = classes
        return _HFAuxAdapter(UperNetForSemanticSegmentation(config), channels, classes)
    if name == "dpt":
        config = DPTConfig(
            num_channels=channels,
            image_size=max(patch),
            hidden_size=96 if smoke else 768,
            num_hidden_layers=4 if smoke else 12,
            num_attention_heads=4 if smoke else 12,
            intermediate_size=384 if smoke else 3072,
            backbone_out_indices=[0, 1, 2, 3] if smoke else [2, 5, 8, 11],
            neck_hidden_sizes=[16, 32, 64, 96] if smoke else [96, 192, 384, 768],
            fusion_hidden_size=32 if smoke else 256,
        )
        config.num_labels = classes
        return _HFAuxAdapter(DPTForSemanticSegmentation(config), channels, classes, square=True)
    if name == "maskformer":
        decoder = DetrConfig(
            d_model=64 if smoke else 256,
            encoder_layers=1 if smoke else 6,
            decoder_layers=2 if smoke else 6,
            encoder_attention_heads=4 if smoke else 8,
            decoder_attention_heads=4 if smoke else 8,
            encoder_ffn_dim=128 if smoke else 2048,
            decoder_ffn_dim=128 if smoke else 2048,
            num_queries=12 if smoke else 100,
        )
        config = MaskFormerConfig(
            backbone_config=_swin(channels, smoke),
            decoder_config=decoder,
            fpn_feature_size=64 if smoke else 256,
            mask_feature_size=64 if smoke else 256,
            use_auxiliary_loss=True,
            output_auxiliary_logits=True,
        )
        config.num_labels = classes
        return _QueryAdapter(MaskFormerForInstanceSegmentation(config), channels, classes)
    config = Mask2FormerConfig(
        backbone_config=_swin(channels, smoke),
        feature_size=64 if smoke else 256,
        mask_feature_size=64 if smoke else 256,
        hidden_dim=64 if smoke else 256,
        encoder_feedforward_dim=128 if smoke else 1024,
        encoder_layers=1 if smoke else 6,
        decoder_layers=2 if smoke else 10,
        num_attention_heads=4 if smoke else 8,
        dim_feedforward=128 if smoke else 2048,
        num_queries=12 if smoke else 100,
        train_num_points=256 if smoke else 12544,
        use_auxiliary_loss=True,
        output_auxiliary_logits=True,
    )
    config.num_labels = classes
    return _QueryAdapter(Mask2FormerForUniversalSegmentation(config), channels, classes)


def build_model(
    name: str,
    *,
    in_channels: int = 1,
    num_classes: int = 3,
    patch_size: tuple[int, int] = (128, 128),
    model_options: dict[str, Any] | None = None,
) -> nn.Module:
    """Construct a named architecture using random initialization exclusively."""
    metadata = model_metadata(name)
    in_channels = _positive_int(in_channels, "in_channels")
    num_classes = _positive_int(num_classes, "num_classes")
    if num_classes < 2:
        raise ValueError("medical semantic segmentation requires at least two classes")
    if not isinstance(patch_size, (tuple, list)) or len(patch_size) != 2:
        raise ValueError("patch_size must contain two dimensions")
    patch = tuple(_positive_int(v, "patch_size") for v in patch_size)
    if not isinstance(model_options, (dict, type(None))):
        raise TypeError("model_options must be a mapping")
    options = dict(model_options or {})
    if set(options) - {"profile"}:
        raise ValueError(
            f"unknown model options: {sorted(set(options) - {'profile'})}; weights are forbidden"
        )
    profile = options.get("profile", "standard")
    if profile not in ("standard", "smoke"):
        raise ValueError("profile must be standard or smoke")
    smoke = profile == "smoke"
    model: nn.Module
    if name in ("unet_2d", "unet_plus_plus", "fpn", "deeplabv3_plus"):
        import segmentation_models_pytorch as smp

        constructor = {
            "unet_2d": smp.Unet,
            "unet_plus_plus": smp.UnetPlusPlus,
            "fpn": smp.FPN,
            "deeplabv3_plus": smp.DeepLabV3Plus,
        }[name]
        encoder = "resnet18" if smoke else "resnet50" if name == "deeplabv3_plus" else "resnet34"
        inner = constructor(
            encoder_name=encoder,
            encoder_weights=None,
            in_channels=in_channels,
            classes=num_classes,
            activation=None,
        )
        model = _Adapter(inner, in_channels, num_classes)
    elif name == "hrnet_ocr":
        model = _AuxAdapter(
            _HRNet(in_channels, num_classes, smoke), in_channels, num_classes, kind=name
        )
    elif name == "bisenetv2":
        from .two_d_bisenet import BiSeNetV2

        inner = BiSeNetV2(num_classes, aux_mode="train")
        _replace_input_conv(inner.detail.S1[0], "conv", in_channels)
        _replace_input_conv(inner.segment.S1S2.conv, "conv", in_channels)
        model = _AuxAdapter(inner, in_channels, num_classes, kind=name)
    elif name == "ddrnet":
        from .two_d_ddrnet import BasicBlock, DualResNet

        inner = DualResNet(
            BasicBlock,
            [2, 2, 2, 2],
            num_classes=num_classes,
            planes=16 if smoke else 32,
            spp_planes=32 if smoke else 128,
            head_planes=32 if smoke else 64,
            augment=True,
        )
        _replace_input_conv(inner.conv1, "0", in_channels)
        model = _AuxAdapter(inner, in_channels, num_classes, kind=name)
    elif name == "pidnet":
        from .two_d_pidnet import PIDNet

        inner = PIDNet(
            m=2,
            n=3,
            num_classes=num_classes,
            planes=16 if smoke else 32,
            ppm_planes=32 if smoke else 96,
            head_planes=32 if smoke else 128,
            augment=True,
        )
        _replace_input_conv(inner.conv1, "0", in_channels)
        model = _AuxAdapter(inner, in_channels, num_classes, kind=name)
    elif name == "lraspp":
        from torchvision.models.segmentation import lraspp_mobilenet_v3_large

        inner = lraspp_mobilenet_v3_large(
            weights=None, weights_backbone=None, num_classes=num_classes
        )
        _replace_input_conv(inner.backbone["0"], "0", in_channels)
        model = _Adapter(inner, in_channels, num_classes)
    else:
        model = _hf(name, in_channels, num_classes, (patch[0], patch[1]), smoke)
    # HF backbones expose classification-only final norms even though semantic
    # decoders consume their intermediate feature maps. DPT's first fusion block
    # has no skip input, so its first residual unit is likewise never executed.
    # Remove only these statically identified dead modules, preserving every
    # feature used by the segmentation forward and every auxiliary classifier.
    dead_paths = {
        "swin_upernet": ["model.backbone.swin.layernorm"],
        "maskformer": ["model.model.pixel_level_module.encoder.model.layernorm"],
        "mask2former": ["model.model.pixel_level_module.encoder.swin.layernorm"],
        "dpt": ["model.dpt.layernorm", "model.neck.fusion_stage.layers.0.residual_layer1"],
    }
    for path in dead_paths.get(name, []):
        parent_path, key = path.rsplit(".", 1)
        parent = model.get_submodule(parent_path)
        setattr(parent, key, nn.Identity())
    metadata["removed_dead_modules"] = dead_paths.get(name, [])
    metadata["profile"] = profile
    metadata["resolved_variant"] = metadata[f"{profile}_variant"]
    cast(Any, model).medical_model_metadata = metadata
    return model
