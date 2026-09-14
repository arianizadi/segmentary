"""Random-initialized volumetric architectures with a common native-logit contract.

MONAI is pinned to 1.6.0. Other architectures are pinned source under
``three_d_vendor``; no constructor downloads or imports weights. Options expose
architecture capacity, not pretrained checkpoints or hidden initialization modes.
"""

from __future__ import annotations

from copy import deepcopy
from importlib.metadata import version
from typing import Any

import torch
import torch.nn.functional as F
from torch import nn

MODEL_NAMES = (
    "unet_3d",
    "dynunet",
    "segresnet",
    "mednext_v1",
    "swin_unetr",
    "unetr",
    "medformer",
    "transunet_3d",
)

_SOURCES = {
    "mednext_v1": ("MIC-DKFZ/MedNeXt", "0b78ed869fbd1cc2fd38754d2f8519f1b72d43ba"),
    "medformer": (
        "yhygao/CBIM-Medical-Image-Segmentation",
        "7c26979a96eb9fe057320e1db38680bae33786b8",
    ),
    "transunet_3d": ("Beckschen/3D-TransUNet", "9f18182f5f7b26fc81e2f2d70fb5c40ee8a58908"),
}

_DEFAULTS: dict[str, dict[str, Any]] = {
    "unet_3d": {"channels": [32, 64, 128, 256, 512], "num_res_units": 0},
    "dynunet": {
        "filters": [32, 64, 128, 256, 320],
        "res_block": False,
        "deep_supervision": False,
    },
    "segresnet": {
        "init_filters": 32,
        "blocks_down": [1, 2, 2, 4],
        "blocks_up": [1, 1, 1],
        "num_groups": 8,
    },
    "mednext_v1": {"model_id": "S", "kernel_size": 3},
    "swin_unetr": {
        "feature_size": 24,
        "depths": [2, 2, 2, 2],
        "num_heads": [3, 6, 12, 24],
        "window_size": 7,
        "use_checkpoint": False,
    },
    "unetr": {"feature_size": 16, "hidden_size": 768, "mlp_dim": 3072, "num_heads": 12},
    "medformer": {
        "base_chan": 32,
        "map_size": [4, 4, 4],
        "chan_num": [64, 128, 256, 320, 256, 128, 64, 32],
        "conv_num": [2, 1, 0, 0, 0, 1, 2, 2],
        "trans_num": [0, 1, 4, 6, 4, 1, 0, 0],
        "num_heads": [1, 4, 8, 10, 8, 4, 1, 1],
        "fusion_depth": 2,
        "fusion_dim": 320,
        "fusion_heads": 10,
        "expansion": 4,
    },
    "transunet_3d": {
        "base_num_features": 32,
        "num_pool": 4,
        "max_num_features": 320,
        "vit_depth": 12,
        "vit_hidden_size": 768,
        "vit_mlp_dim": 3072,
        "vit_num_heads": 12,
        "vit_layer_scale": True,
    },
}

_SMOKE_OPTIONS: dict[str, dict[str, Any]] = {
    "unet_3d": {"channels": [4, 8, 16]},
    "dynunet": {"filters": [4, 8, 16]},
    "segresnet": {"init_filters": 8},
    "mednext_v1": {},
    "swin_unetr": {"feature_size": 12, "depths": [1, 1, 1, 1], "window_size": 4},
    "unetr": {"feature_size": 4, "hidden_size": 48, "mlp_dim": 96, "num_heads": 4},
    "medformer": {
        "base_chan": 8,
        "map_size": [2, 2, 2],
        "chan_num": [8, 16, 24, 32, 24, 16, 8, 8],
        "num_heads": [1, 2, 4, 4, 4, 2, 1, 1],
        "trans_num": [0, 1, 1, 1, 1, 1, 0, 0],
        "fusion_dim": 32,
        "fusion_heads": 4,
        "fusion_depth": 1,
        "expansion": 2,
    },
    "transunet_3d": {
        "base_num_features": 4,
        "num_pool": 3,
        "max_num_features": 32,
        "vit_depth": 2,
        "vit_hidden_size": 48,
        "vit_mlp_dim": 96,
        "vit_num_heads": 4,
    },
}


def model_metadata(name: str) -> dict[str, Any]:
    """Return versioned architecture provenance without importing optional packages."""
    if name not in MODEL_NAMES:
        raise ValueError(f"Unknown volumetric model {name!r}; choose from {MODEL_NAMES}")
    repo, revision = _SOURCES.get(name, ("Project-MONAI/MONAI", "1.6.0"))
    return {
        "name": name,
        "dimensions": 3,
        "spatial_dims": 3,
        "initialization": "random",
        "pretrained": False,
        "source": f"https://github.com/{repo}",
        "revision": revision,
        "license": "Apache-2.0",
        "variant": "encoder_transformer" if name == "transunet_3d" else name,
        "default_options": deepcopy(_DEFAULTS[name]),
        "default_patch_size": [64, 64, 64],
        "smoke_options": deepcopy(_SMOKE_OPTIONS[name]),
        "smoke_patch_size": [64, 64, 64] if name == "swin_unetr" else [32, 32, 32],
        "smoke_note": "Reduced widths/depths where specified; all named architectural mechanisms retained. Not a benchmark configuration.",
        "fixed_patch_size": name in {"unetr", "transunet_3d"},
        "objective": "dense_ce_dice_no_auxiliary_heads",
        "unused_modules_removed": {
            "mednext_v1": "Legacy checkpoint dummy is a nontrainable buffer; checkpointing uses non-reentrant execution",
            "unetr": "Unused cross-attention normalization is Identity in self-attention-only ViT blocks",
            "transunet_3d": "Unused auxiliary dense classifiers are Identity; final classifier is preserved",
        }.get(name, "none"),
        "paper_training_reproduction": False,
    }


def _positive(value: Any, key: str, *, zero: bool = False) -> int:
    if type(value) is not int or value < (0 if zero else 1):
        raise ValueError(f"{key} must be {'nonnegative' if zero else 'positive'} integer")
    return value


def _fixed_shape(
    patch_size: tuple[int, int, int], multiple: int, minimum: int
) -> tuple[int, int, int]:
    sizes = [max(minimum, (x + multiple - 1) // multiple * multiple) for x in patch_size]
    return sizes[0], sizes[1], sizes[2]


def _options(name: str, supplied: dict[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(_DEFAULTS[name])
    if supplied is not None:
        if not isinstance(supplied, dict):
            raise ValueError("model_options must be a mapping")
        if any(not isinstance(key, str) for key in supplied):
            raise ValueError("model_options keys must be strings")
        unknown = set(supplied) - set(result)
        if unknown:
            raise ValueError(f"Unsupported {name} model_options: {sorted(unknown)}")
        result.update(deepcopy(supplied))
    for key, value in result.items():
        if key in {"use_checkpoint", "res_block", "vit_layer_scale", "deep_supervision"}:
            if type(value) is not bool:
                raise ValueError(f"{key} must be boolean")
        elif key == "model_id":
            if not isinstance(value, str) or value not in {"S", "B", "M", "L"}:
                raise ValueError("MedNeXt model_id must be S, B, M, or L")
        elif isinstance(_DEFAULTS[name][key], list):
            if not isinstance(value, (list, tuple)) or not value:
                raise ValueError(f"{key} must be a nonempty integer sequence")
            for element in value:
                _positive(element, key, zero=key in {"conv_num", "trans_num"})
        else:
            _positive(value, key, zero=key == "num_res_units")
    return result


class VolumeLogits(nn.Module):
    """Pad to the architecture grid and crop raw logits back without resampling."""

    def __init__(
        self,
        network: nn.Module,
        *,
        name: str,
        in_channels: int,
        num_classes: int,
        multiple: int,
        minimum: int,
        fixed_size: tuple[int, int, int] | None = None,
        options: dict[str, Any],
    ) -> None:
        super().__init__()
        self.network = network
        self.in_channels = in_channels
        self.num_classes = num_classes
        self.multiple = multiple
        self.minimum = minimum
        self.fixed_size = fixed_size
        self.architecture_metadata = model_metadata(name)
        self.architecture_metadata["resolved_options"] = deepcopy(options)
        self.architecture_metadata["fixed_size"] = fixed_size

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        if image.ndim != 5 or image.shape[1] != self.in_channels:
            raise ValueError(f"Expected N,{self.in_channels},D,H,W input")
        shape = tuple(image.shape[2:])
        if min(shape) < 1:
            raise ValueError("Input spatial dimensions must be nonempty")
        target = self.fixed_size or tuple(
            max(self.minimum, (size + self.multiple - 1) // self.multiple * self.multiple)
            for size in shape
        )
        if any(size > limit for size, limit in zip(shape, target, strict=True)):
            raise ValueError(f"Input {shape} exceeds model's configured patch_size {target}")
        padding = [
            p
            for size, limit in reversed(list(zip(shape, target, strict=True)))
            for p in (0, limit - size)
        ]
        logits = self.network(F.pad(image, padding))
        if not isinstance(logits, torch.Tensor) or logits.ndim != 5:
            raise RuntimeError("Volumetric architecture did not return N,C,D,H,W raw logits")
        if logits.shape[1] != self.num_classes or tuple(logits.shape[2:]) != target:
            raise RuntimeError("Volumetric architecture output violates its native-logit geometry")
        return logits[:, :, : shape[0], : shape[1], : shape[2]]


def build_model(
    name: str,
    *,
    in_channels: int = 1,
    num_classes: int = 3,
    patch_size: tuple[int, int, int] = (64, 64, 64),
    model_options: dict[str, Any] | None = None,
) -> nn.Module:
    """Construct actual 3D architectures entirely from random initialization.

    General CNNs accept arbitrary volume sizes through right padding/cropping.
    UNETR and 3D TransUNet bind positional embeddings to ``patch_size``; smaller
    inputs are padded and larger ones rejected so inference must use patches.
    """
    model_metadata(name)
    _positive(in_channels, "in_channels")
    _positive(num_classes, "num_classes")
    if not isinstance(patch_size, (tuple, list)) or len(patch_size) != 3:
        raise ValueError("patch_size must contain three positive integers")
    for size in patch_size:
        _positive(size, "patch_size")
    opt = _options(name, model_options)
    fixed: tuple[int, int, int] | None = None
    network: nn.Module

    if name in {"unet_3d", "dynunet", "segresnet", "swin_unetr", "unetr"}:
        if version("monai") != "1.6.0":
            raise RuntimeError("Medical scratch models require the tested monai==1.6.0")
        from monai.networks.nets import UNETR, DynUNet, SegResNet, SwinUNETR, UNet

    if name == "unet_3d":
        if len(opt["channels"]) < 3:
            raise ValueError("unet_3d channels must have at least three levels")
        multiple = 2 ** (len(opt["channels"]) - 1)
        minimum = multiple * 2
        network = UNet(
            3,
            in_channels,
            num_classes,
            opt["channels"],
            [2] * (len(opt["channels"]) - 1),
            num_res_units=opt["num_res_units"],
        )
    elif name == "dynunet":
        levels = len(opt["filters"])
        if levels < 3:
            raise ValueError("DynUNet filters must have at least three levels")
        multiple, minimum = 2 ** (levels - 1), 2**levels
        network = DynUNet(
            3,
            in_channels,
            num_classes,
            [3] * levels,
            [1] + [2] * (levels - 1),
            [2] * (levels - 1),
            filters=opt["filters"],
            res_block=opt["res_block"],
            deep_supervision=False,
        )
    elif name == "segresnet":
        if len(opt["blocks_up"]) != len(opt["blocks_down"]) - 1:
            raise ValueError("SegResNet requires one fewer up than down stages")
        if opt["init_filters"] % opt["num_groups"]:
            raise ValueError("SegResNet init_filters must divide evenly by num_groups")
        multiple = 2 ** (len(opt["blocks_down"]) - 1)
        minimum = multiple * 2
        network = SegResNet(
            spatial_dims=3,
            in_channels=in_channels,
            out_channels=num_classes,
            init_filters=opt["init_filters"],
            blocks_down=tuple(opt["blocks_down"]),
            blocks_up=tuple(opt["blocks_up"]),
            norm=("GROUP", {"num_groups": opt["num_groups"]}),
        )
    elif name == "mednext_v1":
        from .three_d_vendor.mednext.create_mednext_v1 import create_mednext_v1

        if opt["kernel_size"] not in {3, 5}:
            raise ValueError("MedNeXt v1 kernel_size must be 3 or 5")
        multiple, minimum = 16, 32
        network = create_mednext_v1(
            in_channels, num_classes, opt["model_id"], opt["kernel_size"], deep_supervision=False
        )
    elif name == "swin_unetr":
        if len(opt["depths"]) != 4 or len(opt["num_heads"]) != 4:
            raise ValueError("Swin UNETR requires four depths and head counts")
        if opt["feature_size"] % 12 or any(
            opt["feature_size"] * 2**i % heads for i, heads in enumerate(opt["num_heads"])
        ):
            raise ValueError("Swin UNETR feature_size must divide by 12 and stage head counts")
        multiple, minimum = 32, 64
        network = SwinUNETR(in_channels, num_classes, spatial_dims=3, **opt)
    elif name == "unetr":
        if opt["hidden_size"] % opt["num_heads"]:
            raise ValueError("UNETR hidden_size must divide evenly by num_heads")
        multiple, minimum = 16, 32
        fixed = _fixed_shape(patch_size, multiple, minimum)
        network = UNETR(in_channels, num_classes, fixed, spatial_dims=3, **opt)
        for block in network.vit.blocks:
            if block.with_cross_attention:
                raise RuntimeError("UNETR unexpectedly enabled cross-attention")
            # MONAI retains these affine parameters for checkpoint compatibility;
            # our scratch self-attention model never executes that branch.
            block._modules["norm_cross_attn"] = nn.Identity()
    elif name == "medformer":
        from .three_d_vendor.medformer.medformer import MedFormer

        for key in ("chan_num", "conv_num", "trans_num", "num_heads"):
            if len(opt[key]) != 8:
                raise ValueError(f"MedFormer {key} must have eight entries")
        if len(opt["map_size"]) != 3:
            raise ValueError("MedFormer map_size must have three entries")
        if opt["map_size"] == [1, 1, 1] or opt["map_size"] == (1, 1, 1):
            raise ValueError("MedFormer semantic map must have more than one spatial element")
        if (
            any(c % h for c, h in zip(opt["chan_num"], opt["num_heads"], strict=True))
            or opt["fusion_dim"] % opt["fusion_heads"]
        ):
            raise ValueError("MedFormer channel/fusion dimensions must divide by attention heads")
        if (
            opt["chan_num"][0] != opt["chan_num"][6]
            or opt["chan_num"][1] != opt["chan_num"][5]
            or opt["chan_num"][2] != opt["chan_num"][4]
            or opt["base_chan"] != opt["chan_num"][7]
        ):
            raise ValueError("MedFormer encoder and decoder shortcut widths must match")
        if not all(opt["trans_num"][i] > 0 for i in (1, 2, 3, 4, 5)):
            raise ValueError("MedFormer must retain all five bidirectional-attention stages")
        multiple, minimum = 16, 32
        network = MedFormer(
            in_channels,
            num_classes,
            kernel_size=[[3, 3, 3]] * 5,
            scale=[[2, 2, 2]] * 4,
            act="relu",
            aux_loss=False,
            **opt,
        )
    else:
        from .three_d_vendor.transunet.transunet3d_model import Generic_TransUNet_max_ppbp

        if opt["num_pool"] < 2:
            raise ValueError("3D TransUNet requires at least two encoder pooling stages")
        if opt["vit_hidden_size"] % opt["vit_num_heads"]:
            raise ValueError("3D TransUNet vit_hidden_size must divide by vit_num_heads")
        multiple = 2 ** opt["num_pool"]
        minimum = multiple * 2
        fixed = _fixed_shape(patch_size, multiple, minimum)
        network = Generic_TransUNet_max_ppbp(
            input_channels=in_channels,
            num_classes=num_classes,
            conv_op=nn.Conv3d,
            norm_op=nn.InstanceNorm3d,
            norm_op_kwargs={"eps": 1e-5, "affine": True},
            dropout_op=nn.Dropout3d,
            dropout_op_kwargs={"p": 0.0},
            deep_supervision=True,
            final_nonlin=nn.Identity(),
            convolutional_pooling=True,
            convolutional_upsampling=True,
            patch_size=list(fixed),
            is_vit_pretrain=False,
            is_max=False,
            is_max_bottleneck_transformer=True,
            **opt,
        )
        # Upstream constructs dense classifiers only with do_ds=True. Keep those
        # classifiers, select the final raw-logit output, and omit auxiliary loss.
        network._deep_supervision = False
        for index in range(len(network.seg_outputs) - 1):
            network.seg_outputs[index] = nn.Identity()

    primary = VolumeLogits(
        network,
        name=name,
        in_channels=in_channels,
        num_classes=num_classes,
        multiple=multiple,
        minimum=minimum,
        fixed_size=fixed,
        options=opt,
    )
    if name == "dynunet" and opt["deep_supervision"]:
        from .torch_deep_supervision import DeepSupervisedDynUNet

        return DeepSupervisedDynUNet(primary, opt["filters"], num_classes)
    return primary
