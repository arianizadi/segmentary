"""Scratch-only U-Mamba and SegMamba with their actual selective SSM mixers.

This typed 3D adaptation preserves the upstream topology, including U-Mamba
channel tokens and SegMamba's GSC and three sequence directions. See
``mamba_vendor/NOTICE.md`` for pinned sources, licenses and declared adaptations.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from .mamba_scan import Mamba

MODEL_NAMES = ("umamba_bot", "umamba_enc", "segmamba")
_UPSTREAMS = {
    "umamba": ("https://github.com/bowang-lab/U-Mamba", "28459e33ca03769800dd35e23c6e62491d1925b5"),
    "segmamba": ("https://github.com/ge-xing/SegMamba", "cff35970e0c542ad940b5701267f1ac888298b06"),
}


def model_metadata(name: str) -> dict[str, Any]:
    if name not in MODEL_NAMES:
        raise ValueError(f"Unknown Mamba model: {name}")
    source, commit = _UPSTREAMS["segmamba" if name == "segmamba" else "umamba"]
    shared_defaults = {
        "d_state": 16,
        "d_conv": 4,
        "expand": 2,
        "scan_backend": "torch",
        "scan_chunk_size": 256,
        "checkpoint_mamba": False,
    }
    defaults = (
        {
            "features": [48, 96, 192, 384],
            "depths": [2, 2, 2, 2],
            "hidden_size": 768,
            "num_slices": [64, 32, 16, 8],
        }
        if name == "segmamba"
        else {
            "features": [32, 64, 128, 256, 320],
            "blocks": [2, 2, 2, 2, 2],
            "decoder_blocks": [2, 2, 2, 2],
        }
    )
    smoke = (
        {"features": [4, 8, 16, 32], "depths": [1, 1, 1, 1], "hidden_size": 48}
        if name == "segmamba"
        else {"features": [4, 8, 16], "blocks": [1, 1, 1], "decoder_blocks": [1, 1]}
    )
    return {
        "name": name,
        "dimensions": 3,
        "spatial_dims": 3,
        "initialization": "scratch",
        "pretrained": False,
        "family": "state_space",
        "upstream": source,
        "upstream_commit": commit,
        "license": "Apache-2.0",
        "default_scan_backend": "torch",
        "scan_backend_notes": "Exact chunked selective recurrence; slower than fused CUDA. Native scan is explicit and requires mamba-ssm.",
        "checkpoint_mamba_notes": "Optional non-reentrant activation recomputation of the pure SSM mixer; no change to weights, widths, spatial normalization or effective batch. Trades additional compute for lower training memory.",
        "objective": "dense_ce_dice",
        "deep_supervision": False,
        "default_options": {**defaults, **shared_defaults},
        "allowed_options": sorted([*defaults, *shared_defaults]),
        "smoke_options": {**smoke, "d_state": 2, "expand": 1, "scan_chunk_size": 64},
        "smoke_patch_size": [32, 32, 32] if name == "segmamba" else [8, 8, 8],
        "third_party_notice": "segmentary/medical/mamba_vendor/NOTICE.md",
        "adaptations": "Fixed declared patch plan; end padding then crop; no pretrained weights. SegMamba feature-width head bug fixed; U-Mamba uses explicit isotropic stage widths/strides.",
    }


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _integer_list(name: str, value: Any, *, length: int | None = None) -> list[int]:
    if not isinstance(value, (tuple, list)) or not value:
        raise ValueError(f"{name} must be a nonempty integer list")
    result = [_positive_int(name, item) for item in value]
    if length is not None and len(result) != length:
        raise ValueError(f"{name} must contain {length} entries")
    return result


class _Residual(nn.Module):
    """U-Mamba BasicResBlock / same-channel BasicBlockD equivalent."""

    def __init__(
        self, in_channels: int, out_channels: int, stride: int = 1, *, projection: bool = True
    ) -> None:
        super().__init__()
        self.conv1 = nn.Conv3d(in_channels, out_channels, 3, stride=stride, padding=1)
        self.norm1 = nn.InstanceNorm3d(out_channels, eps=1e-5, affine=True)
        self.conv2 = nn.Conv3d(out_channels, out_channels, 3, padding=1)
        self.norm2 = nn.InstanceNorm3d(out_channels, eps=1e-5, affine=True)
        self.act = nn.LeakyReLU(inplace=True)
        self.proj: nn.Module = (
            nn.Conv3d(in_channels, out_channels, 1, stride=stride) if projection else nn.Identity()
        )

    def forward(self, x: Tensor) -> Tensor:
        y = self.act(self.norm1(self.conv1(x)))
        return self.act(self.norm2(self.conv2(y)) + self.proj(x))


def _residual_stage(
    in_channels: int, out_channels: int, blocks: int, stride: int = 1
) -> nn.Sequential:
    return nn.Sequential(
        _Residual(in_channels, out_channels, stride),
        *[_Residual(out_channels, out_channels, projection=False) for _ in range(blocks - 1)],
    )


class _VolumeMamba(nn.Module):
    def __init__(
        self, dim: int, *, channel_token: bool = False, residual: bool = False, **options: Any
    ) -> None:
        super().__init__()
        self.dim = dim
        self.channel_token = channel_token
        self.residual = residual
        self.norm = nn.LayerNorm(dim)
        self.mamba = Mamba(dim, **options)

    def forward(self, x: Tensor) -> Tensor:
        original = x
        # Upstream U-Mamba disables autocast for the full mixer. This also avoids
        # unstable half-precision recurrence parameters in SegMamba.
        with torch.autocast(device_type=x.device.type, enabled=False):
            if x.dtype in (torch.float16, torch.bfloat16):
                x = x.float()
            tokens = x.flatten(2)
            if not self.channel_token:
                tokens = tokens.transpose(1, 2)
            if tokens.shape[-1] != self.dim:
                raise ValueError(
                    "U-Mamba channel-token dimensions are bound to the configured patch"
                )
            tokens = self.mamba(self.norm(tokens))
            if not self.channel_token:
                tokens = tokens.transpose(1, 2)
            out = tokens.reshape_as(x)
            if self.residual:
                out = out + original.float() if original.dtype != torch.float64 else out + original
            return out


class UMamba(nn.Module):
    """Residual U-Net with bottleneck-only or every-encoder-stage Mamba v1."""

    def __init__(
        self,
        in_channels: int,
        num_classes: int,
        patch_size: tuple[int, int, int],
        features: list[int],
        blocks: list[int],
        decoder_blocks: list[int],
        *,
        encoder_mamba: bool,
        mixer_options: dict[str, Any],
    ) -> None:
        super().__init__()
        count = len(features)
        # Exact stage-depth reductions performed by upstream UMambaBot/Enc.
        blocks = list(blocks)
        decoder_blocks = list(decoder_blocks)
        for i in range(math.ceil(count / 2), count):
            blocks[i] = 1
        for i in range(math.ceil((count - 1) / 2 + 0.5), count - 1):
            decoder_blocks[i] = 1
        self.effective_blocks = blocks
        self.effective_decoder_blocks = decoder_blocks
        self.stem = _residual_stage(in_channels, features[0], blocks[0])
        self.stages = nn.ModuleList()
        self.mixers = nn.ModuleList()
        current_channels = features[0]
        for i, channels in enumerate(features):
            self.stages.append(
                _residual_stage(current_channels, channels, blocks[i], 1 if i == 0 else 2)
            )
            spatial_tokens = math.prod(size // (2**i) for size in patch_size)
            channel_tokens = encoder_mamba and spatial_tokens <= channels
            if encoder_mamba or i == count - 1:
                self.mixers.append(
                    _VolumeMamba(
                        spatial_tokens if channel_tokens else channels,
                        channel_token=channel_tokens,
                        **mixer_options,
                    )
                )
            else:
                self.mixers.append(nn.Identity())
            current_channels = channels
        self.upsample = nn.ModuleList()
        self.decoder = nn.ModuleList()
        for i in range(count - 1):
            skip_channels = features[-i - 2]
            self.upsample.append(nn.Conv3d(features[-i - 1], skip_channels, 1))
            self.decoder.append(
                _residual_stage(2 * skip_channels, skip_channels, decoder_blocks[i])
            )
        self.out = nn.Conv3d(features[0], num_classes, 1)
        # Upstream InitWeights_He(1e-2) initializes all convolutional weights only.
        for module in self.modules():
            if isinstance(module, nn.Conv3d):
                nn.init.kaiming_normal_(module.weight, a=1e-2)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(self, x: Tensor) -> Tensor:
        x = self.stem(x)
        skips = []
        for stage, mixer in zip(self.stages, self.mixers, strict=True):
            x = mixer(stage(x))
            skips.append(x)
        for i, (upsample, decoder) in enumerate(zip(self.upsample, self.decoder, strict=True)):
            skip = skips[-i - 2]
            x = upsample(F.interpolate(x, scale_factor=2, mode="nearest"))
            x = decoder(torch.cat((x, skip), dim=1))
        return self.out(x)


class _GSC(nn.Module):
    """SegMamba gated spatial convolution block (upstream GSC topology)."""

    def __init__(self, channels: int) -> None:
        super().__init__()

        def unit(kernel: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv3d(channels, channels, kernel, padding=kernel // 2),
                nn.InstanceNorm3d(channels),
                nn.ReLU(),
            )

        self.long = nn.Sequential(unit(3), unit(3))
        self.short = unit(1)
        self.fuse = unit(1)

    def forward(self, x: Tensor) -> Tensor:
        return x + self.fuse(self.long(x) + self.short(x))


class SegMamba(nn.Module):
    """Official four-stage GSC + tri-direction Mamba + UNETR decoder design."""

    def __init__(
        self,
        in_channels: int,
        num_classes: int,
        features: list[int],
        depths: list[int],
        hidden_size: int,
        num_slices: list[int],
        *,
        mixer_options: dict[str, Any],
    ) -> None:
        super().__init__()
        try:
            from monai.networks.blocks.dynunet_block import UnetOutBlock
            from monai.networks.blocks.unetr_block import UnetrBasicBlock, UnetrUpBlock
        except ImportError as exc:
            raise RuntimeError("SegMamba requires the medical-models MONAI dependency") from exc
        self.downsample = nn.ModuleList(
            [nn.Conv3d(in_channels, features[0], 7, stride=2, padding=3)]
        )
        for i in range(3):
            self.downsample.append(
                nn.Sequential(
                    nn.InstanceNorm3d(features[i]),
                    nn.Conv3d(features[i], features[i + 1], 2, stride=2),
                )
            )
        self.gsc = nn.ModuleList([_GSC(channels) for channels in features])
        self.stages = nn.ModuleList(
            [
                nn.Sequential(
                    *[
                        _VolumeMamba(
                            channels,
                            residual=True,
                            three_direction=True,
                            nslices=num_slices[i],
                            **mixer_options,
                        )
                        for _ in range(depths[i])
                    ]
                )
                for i, channels in enumerate(features)
            ]
        )
        self.norms = nn.ModuleList([nn.InstanceNorm3d(channels) for channels in features])
        self.mlps = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Conv3d(channels, 2 * channels, 1),
                    nn.GELU(),
                    nn.Conv3d(2 * channels, channels, 1),
                )
                for channels in features
            ]
        )

        def basic(in_c: int, out_c: int) -> nn.Module:
            return UnetrBasicBlock(
                spatial_dims=3,
                in_channels=in_c,
                out_channels=out_c,
                kernel_size=3,
                stride=1,
                norm_name="instance",
                res_block=True,
            )

        self.encoders = nn.ModuleList(
            [basic(in_channels, features[0])]
            + [basic(features[i], features[i + 1]) for i in range(3)]
        )
        self.hidden = basic(features[-1], hidden_size)
        decoder_channels = [hidden_size, *features[::-1]]
        self.decoders = nn.ModuleList(
            [
                UnetrUpBlock(
                    spatial_dims=3,
                    in_channels=decoder_channels[i],
                    out_channels=decoder_channels[i + 1],
                    kernel_size=3,
                    upsample_kernel_size=2,
                    norm_name="instance",
                    res_block=True,
                )
                for i in range(4)
            ]
        )
        self.final = basic(features[0], features[0])
        self.out = UnetOutBlock(spatial_dims=3, in_channels=features[0], out_channels=num_classes)

    def forward(self, x: Tensor) -> Tensor:
        input_tensor = x
        outputs = []
        for down, gsc, stage, norm, mlp in zip(
            self.downsample, self.gsc, self.stages, self.norms, self.mlps, strict=True
        ):
            x = stage(gsc(down(x)))
            outputs.append(mlp(norm(x)))
        skips = [self.encoders[0](input_tensor)]
        for i in range(3):
            skips.append(self.encoders[i + 1](outputs[i]))
        x = self.hidden(outputs[-1])
        for decoder, skip in zip(self.decoders, reversed(skips), strict=True):
            x = decoder(x, skip)
        return self.out(self.final(x))


class _PatchContract(nn.Module):
    def __init__(
        self,
        network: nn.Module,
        name: str,
        in_channels: int,
        patch_size: tuple[int, int, int],
        resolved_options: dict[str, Any],
    ) -> None:
        super().__init__()
        self.network = network
        self.in_channels = in_channels
        self.patch_size = patch_size
        self.model_name = name
        self.initialization = "scratch"
        self.resolved_model_options = resolved_options

    def forward(self, x: Tensor) -> Tensor:
        if x.ndim != 5 or x.shape[1] != self.in_channels:
            raise ValueError("Medical Mamba input must be N,C,D,H,W with the configured channels")
        shape = tuple(int(size) for size in x.shape[2:])
        if any(
            size > limit or size < 1 for size, limit in zip(shape, self.patch_size, strict=True)
        ):
            raise ValueError(
                f"Input exceeds configured Mamba patch {self.patch_size}; use sliding-window inference"
            )
        padding = [
            value
            for size, target in reversed(list(zip(shape, self.patch_size, strict=True)))
            for value in (0, target - size)
        ]
        output = self.network(F.pad(x, padding))
        return output[..., : shape[0], : shape[1], : shape[2]]


def build_model(
    name: str,
    *,
    in_channels: int = 1,
    num_classes: int = 3,
    patch_size: Sequence[int] = (64, 64, 64),
    model_options: Mapping[str, Any] | None = None,
) -> nn.Module:
    """Construct fresh random weights; unknown and pretrained options are rejected.

    U-Mamba options: features (default 32/64/128/256/320), blocks and
    decoder_blocks. SegMamba: features (48/96/192/384), depths (2/2/2/2),
    hidden_size (768), num_slices (64/32/16/8). Shared options: d_state,
    d_conv, expand, scan_backend ('torch' or explicit 'native'), scan_chunk_size,
    checkpoint_mamba (False; optionally recompute pure mixer activations).
    Small configurable widths/depths are ablations, not paper-sized replicas.
    """
    model_metadata(name)
    _positive_int("in_channels", in_channels)
    _positive_int("num_classes", num_classes)
    patch = _integer_list("patch_size", list(patch_size), length=3)
    options = dict(model_options or {})
    common = {"d_state", "d_conv", "expand", "scan_backend", "scan_chunk_size", "checkpoint_mamba"}
    allowed = common | (
        {"features", "depths", "hidden_size", "num_slices"}
        if name == "segmamba"
        else {"features", "blocks", "decoder_blocks"}
    )
    unknown = set(options) - allowed
    if unknown:
        raise ValueError(f"Unknown or forbidden scratch-only model options: {sorted(unknown)}")
    mixer = {
        key: _positive_int(key, options.get(key, default))
        for key, default in {"d_state": 16, "d_conv": 4, "expand": 2}.items()
    }
    mixer["chunk_size"] = _positive_int("scan_chunk_size", options.get("scan_chunk_size", 256))
    mixer_options: dict[str, Any] = {**mixer, "scan_backend": options.get("scan_backend", "torch")}
    if type(options.get("checkpoint_mamba", False)) is not bool:
        raise ValueError("checkpoint_mamba must be boolean")
    mixer_options["checkpoint_mamba"] = options.get("checkpoint_mamba", False)
    if mixer_options["scan_backend"] not in {"torch", "native"}:
        raise ValueError("scan_backend must be torch or native")
    if name == "segmamba":
        features = _integer_list("features", options.get("features", [48, 96, 192, 384]), length=4)
        depths = _integer_list("depths", options.get("depths", [2, 2, 2, 2]), length=4)
        slices = _integer_list("num_slices", options.get("num_slices", [64, 32, 16, 8]), length=4)
        padded_values = [max(32, math.ceil(size / 16) * 16) for size in patch]
        padded = (padded_values[0], padded_values[1], padded_values[2])
        for stage, count in enumerate(slices):
            if math.prod(size // (2 ** (stage + 1)) for size in padded) % count:
                raise ValueError(
                    "SegMamba stage token count must be divisible by num_slices; adjust patch_size or num_slices explicitly"
                )
        hidden = _positive_int("hidden_size", options.get("hidden_size", 768))
        network: nn.Module = SegMamba(
            in_channels, num_classes, features, depths, hidden, slices, mixer_options=mixer_options
        )
        resolved = {
            "features": features,
            "depths": depths,
            "hidden_size": hidden,
            "num_slices": slices,
        }
    else:
        features = _integer_list("features", options.get("features", [32, 64, 128, 256, 320]))
        if len(features) < 2:
            raise ValueError("U-Mamba needs at least two resolution stages")
        blocks = _integer_list(
            "blocks", options.get("blocks", [2] * len(features)), length=len(features)
        )
        decoder = _integer_list(
            "decoder_blocks",
            options.get("decoder_blocks", [2] * (len(features) - 1)),
            length=len(features) - 1,
        )
        factor = 2 ** (len(features) - 1)
        padded_values = [max(2 * factor, math.ceil(size / factor) * factor) for size in patch]
        padded = (padded_values[0], padded_values[1], padded_values[2])
        umamba = UMamba(
            in_channels,
            num_classes,
            padded,
            features,
            blocks,
            decoder,
            encoder_mamba=name == "umamba_enc",
            mixer_options=mixer_options,
        )
        network = umamba
        resolved = {
            "features": features,
            "blocks": umamba.effective_blocks,
            "decoder_blocks": umamba.effective_decoder_blocks,
        }
    resolved.update(mixer_options)
    resolved["padded_patch_size"] = list(padded)
    return _PatchContract(network, name, in_channels, padded, resolved)
