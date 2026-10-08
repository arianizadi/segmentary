"""Scratch architectures implementing the nnU-Net 2.8.1 network contract.

The trainer and predictor import these classes through the architecture dotted
path in a frozen plans file. All preprocessing, augmentation, losses and
optimization remain in nnU-Net. This bridge changes the network topology only.

``HRCResEncUNet`` (host-referenced calibration) and ``StarCResEncUNet``
(star-convex lesion completion) subclass nnU-Net's ``ResidualEncoderUNet``.
They are defined on first attribute access, so this module still imports in
environments without dynamic-network-architectures.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from copy import deepcopy
from importlib.metadata import version
from typing import Any

import torch
from torch import nn


class _SupervisionState(nn.Module):
    """The official trainer toggles ``network.decoder.deep_supervision``."""

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.deep_supervision = enabled


def _positive_sequence(values: Sequence[int], name: str, length: int) -> list[int]:
    if not isinstance(values, (tuple, list)) or len(values) != length:
        raise ValueError(f"{name} must contain {length} integers")
    if any(type(value) is not int or value < 1 for value in values):
        raise ValueError(f"{name} must contain positive integers")
    return list(values)


class PlannedDynUNet(nn.Module):
    """MONAI DynUNet with plan-derived grids and native decoder supervision.

    Unlike MONAI's ordinary forward method, supervision returns a list of raw
    logits at their native decoder resolutions, in finest-to-coarsest order.
    The flag is independent of ``training`` because nnU-Net's validation loss
    also uses deep supervision. Inference construction creates the same heads
    and state-dict keys, but returns only the full-resolution logits.

    DynUNet supplies its own two-convolution basic blocks, not ResEnc block
    counts. Its feature convolutions are bias-free, so plans must explicitly
    declare ``conv_bias=False`` instead of silently ignoring that setting.
    Auxiliary heads are constructed randomly even for inference-only loading;
    no constructor loads weights or provides a pretrained mode.
    """

    def __init__(
        self,
        input_channels: int,
        num_classes: int,
        n_stages: int,
        features_per_stage: Sequence[int],
        kernel_sizes: Sequence[Sequence[int]],
        strides: Sequence[Sequence[int]],
        conv_op: type[nn.Module] = nn.Conv3d,
        conv_bias: bool = False,
        norm_op: type[nn.Module] = nn.InstanceNorm3d,
        norm_op_kwargs: dict[str, Any] | None = None,
        dropout_op: type[nn.Module] | None = None,
        dropout_op_kwargs: dict[str, Any] | None = None,
        nonlin: type[nn.Module] = nn.LeakyReLU,
        nonlin_kwargs: dict[str, Any] | None = None,
        deep_supervision: bool = True,
    ) -> None:
        super().__init__()
        if version("monai") != "1.6.0":
            raise RuntimeError("PlannedDynUNet requires the verified monai==1.6.0")
        if any(type(value) is not int or value < 1 for value in (input_channels, num_classes)):
            raise ValueError("input_channels and num_classes must be positive integers")
        if type(n_stages) is not int or n_stages < 3:
            raise ValueError("PlannedDynUNet requires at least three stages")
        if type(deep_supervision) is not bool:
            raise ValueError("deep_supervision must be boolean")
        if (
            conv_op is not nn.Conv3d
            or norm_op is not nn.InstanceNorm3d
            or nonlin is not nn.LeakyReLU
        ):
            raise ValueError("PlannedDynUNet requires Conv3d, InstanceNorm3d and LeakyReLU")
        if conv_bias is not False:
            raise ValueError("DynUNet feature convolutions require explicit conv_bias=False")
        if dropout_op is not None or dropout_op_kwargs not in (None, {}):
            raise ValueError("PlannedDynUNet supports the no-dropout reference recipe only")
        features = _positive_sequence(features_per_stage, "features_per_stage", n_stages)
        if not isinstance(kernel_sizes, (tuple, list)) or len(kernel_sizes) != n_stages:
            raise ValueError("kernel_sizes must contain one 3D kernel per stage")
        if not isinstance(strides, (tuple, list)) or len(strides) != n_stages:
            raise ValueError("strides must contain one 3D stride per stage")
        kernels = [_positive_sequence(value, "kernel", 3) for value in kernel_sizes]
        grid = [_positive_sequence(value, "stride", 3) for value in strides]
        if any(size % 2 == 0 for kernel in kernels for size in kernel):
            raise ValueError("Only odd convolution kernels preserve the planned decoder alignment")
        if grid[0] != [1, 1, 1] or any(step not in {1, 2} for stride in grid for step in stride):
            raise ValueError("The first stride must be identity; later strides must be 1 or 2")
        norm = {"eps": 1e-5, "affine": True, **deepcopy(norm_op_kwargs or {})}
        activation = {"inplace": True, "negative_slope": 0.01, **deepcopy(nonlin_kwargs or {})}
        if set(norm) - {"eps", "affine", "momentum", "track_running_stats"}:
            raise ValueError("Unsupported InstanceNorm3d options")
        if set(activation) - {"inplace", "negative_slope"}:
            raise ValueError("Unsupported LeakyReLU options")

        from monai.networks.nets import DynUNet

        self.network = DynUNet(
            spatial_dims=3,
            in_channels=input_channels,
            out_channels=num_classes,
            kernel_size=kernels,
            strides=grid,
            upsample_kernel_size=grid[1:],
            filters=features,
            norm_name=("INSTANCE", norm),
            act_name=("leakyrelu", activation),
            deep_supervision=True,
            deep_supr_num=n_stages - 2,
            res_block=False,
            trans_bias=False,
        )
        self.decoder = _SupervisionState(deep_supervision)
        self.input_channels = input_channels
        self.num_classes = num_classes
        cumulative = [1, 1, 1]
        self.output_divisors: list[tuple[int, int, int]] = []
        for stride in grid:
            cumulative = [value * step for value, step in zip(cumulative, stride, strict=True)]
            self.output_divisors.append((cumulative[0], cumulative[1], cumulative[2]))
        self.input_divisors = self.output_divisors[-1]
        self.output_divisors = self.output_divisors[:-1]
        self.architecture_metadata = {
            "name": "planned_dynunet",
            "source": "https://github.com/Project-MONAI/MONAI",
            "revision": "1.6.0",
            "initialization": "scratch",
            "pretrained": False,
            "feature_convolution_bias": False,
            "blocks": "MONAI basic blocks, two convolutions per encoder and decoder stage",
            "features_per_stage": features,
            "kernel_sizes": kernels,
            "strides": grid,
            "supervision": "native decoder logits, finest first; flag independent of train/eval",
            "inference": "full-resolution logits; native auxiliary heads remain in the state dict",
        }

    def forward(self, image: torch.Tensor) -> torch.Tensor | list[torch.Tensor]:
        if image.ndim != 5 or image.shape[1] != self.input_channels:
            raise ValueError(f"Expected N,{self.input_channels},D,H,W input")
        shape = tuple(image.shape[2:])
        if any(
            size < divisor or size % divisor
            for size, divisor in zip(shape, self.input_divisors, strict=True)
        ):
            raise ValueError("Input must align exactly to the planned grid; no implicit padding")
        if (
            math.prod(
                size // divisor for size, divisor in zip(shape, self.input_divisors, strict=True)
            )
            < 2
        ):
            raise ValueError("The bottleneck must contain at least two spatial elements")
        primary = self.network.output_block(self.network.skip_layers(image))
        outputs = [primary, *self.network.heads]
        if len(outputs) != len(self.output_divisors):
            raise RuntimeError("DynUNet native supervision output count changed")
        for output, divisors in zip(outputs, self.output_divisors, strict=True):
            expected = tuple(size // divisor for size, divisor in zip(shape, divisors, strict=True))
            if output.shape != (image.shape[0], self.num_classes, *expected):
                raise RuntimeError("DynUNet native supervision output grid changed")
        return outputs if self.decoder.deep_supervision else primary


HRC_DEFAULT_LEVELS = (2, 1, 0)
HRC_DEFAULT_STATS_LEVEL = 2


def _hrc_level_list(levels: Sequence[int], stats_level: int, n_stages: int) -> list[int]:
    """Validate block levels against a fixed statistics level (box sizes are in its cells)."""
    if (
        not isinstance(levels, (tuple, list))
        or not levels
        or any(type(level) is not int for level in levels)
        or len(set(levels)) != len(levels)
    ):
        raise ValueError("hrc_levels must be a nonempty list of distinct integers")
    if type(stats_level) is not int or stats_level < 0 or stats_level + 1 > n_stages - 2:
        raise ValueError(
            "hrc_stats_level must be a decoder level whose next-coarser level has a decoder head"
        )
    ordered = sorted(levels, reverse=True)
    if ordered[-1] < 0 or ordered[0] > stats_level:
        raise ValueError("HRC levels must be decoder levels at or below hrc_stats_level")
    return ordered


def _define_hrc_resenc_unet() -> type:
    """Build ``HRCResEncUNet`` on first use; dynamic-network-architectures is optional here."""
    from dynamic_network_architectures.architectures.unet import ResidualEncoderUNet

    from .host_reference import (
        OUTPUT_MODES,
        REFERENCE_MODES,
        ROBUST_LOSSES,
        HostReference,
        HostReferenceBlock,
        compute_host_reference,
        host_lesion_probabilities,
    )

    class HRCResEncUNet(ResidualEncoderUNet):
        """ResEnc U-Net with host-referenced calibration blocks in the decoder.

        Module names match ``ResidualEncoderUNet``; the new modules live under
        ``hrc.<level>``, so a ResEnc state dict loads with only ``hrc.*`` keys
        missing. Levels index encoder skips (0 = full resolution). Each block
        runs after its decoder stage and before that stage's segmentation head.
        The statistics grid G is the fixed ``hrc_stats_level`` (default 2), so
        box sizes always count G cells whichever blocks are enabled. A block at
        G reads the next-coarser head; finer blocks read the head at G (after
        its HRC block when one exists). Those two heads always run, also
        without deep supervision, so
        deep-supervision outputs, their order and the inference output are the
        ResEnc contract. With zero FiLM weights the logits equal ResEnc's.
        """

        def __init__(
            self,
            input_channels: int,
            n_stages: int,
            features_per_stage: Any,
            conv_op: type[nn.Module],
            kernel_sizes: Any,
            strides: Any,
            n_blocks_per_stage: Any,
            num_classes: int,
            n_conv_per_stage_decoder: Any,
            conv_bias: bool = False,
            norm_op: type[nn.Module] | None = None,
            norm_op_kwargs: dict | None = None,
            dropout_op: type[nn.Module] | None = None,
            dropout_op_kwargs: dict | None = None,
            nonlin: type[nn.Module] | None = None,
            nonlin_kwargs: dict | None = None,
            deep_supervision: bool = False,
            *,
            hrc_sigma0: float | None = None,
            hrc_levels: Sequence[int] = HRC_DEFAULT_LEVELS,
            hrc_stats_level: int = HRC_DEFAULT_STATS_LEVEL,
            hrc_reference_mode: str = "robust",
            hrc_output_mode: str = "softmax",
            hrc_host_channels: Sequence[int] = (1,),
            hrc_lesion_channels: Sequence[int] = (2,),
            hrc_image_channel: int = 0,
            hrc_feature_channels: int = 16,
            hrc_hidden_channels: int = 32,
            hrc_outer_box: Sequence[int] = (9, 17, 17),
            hrc_inner_box: Sequence[int] = (3, 7, 7),
            hrc_smoothing_box: Sequence[int] = (1, 5, 5),
            hrc_stats_smoothing_box: Sequence[int] = (1, 3, 3),
            hrc_shrinkage_cells: float = 50.0,
            hrc_gland_prior_cells: float = 10.0,
            hrc_gland_prior_sd: float | None = None,
            hrc_robust_loss: str = "huber",
            hrc_robust_k: float = 1.5,
            hrc_irls_iterations: int = 3,
            **resenc_kwargs: Any,
        ) -> None:
            super().__init__(
                input_channels,
                n_stages,
                features_per_stage,
                conv_op,
                kernel_sizes,
                strides,
                n_blocks_per_stage,
                num_classes,
                n_conv_per_stage_decoder,
                conv_bias,
                norm_op,
                norm_op_kwargs,
                dropout_op,
                dropout_op_kwargs,
                nonlin,
                nonlin_kwargs,
                deep_supervision,
                **resenc_kwargs,
            )
            if conv_op is not nn.Conv3d:
                raise ValueError("HRCResEncUNet is volumetric; conv_op must be Conv3d")
            if hrc_sigma0 is None:
                raise ValueError("hrc_sigma0 must come from the plan's foreground intensity std")
            if hrc_reference_mode not in REFERENCE_MODES:
                raise ValueError(f"hrc_reference_mode must be one of {REFERENCE_MODES}")
            if hrc_output_mode not in OUTPUT_MODES:
                raise ValueError(f"hrc_output_mode must be one of {OUTPUT_MODES}")
            if hrc_robust_loss not in ROBUST_LOSSES:
                raise ValueError(f"hrc_robust_loss must be one of {ROBUST_LOSSES}")
            channels = list(hrc_host_channels) + list(hrc_lesion_channels)
            if (
                not hrc_host_channels
                or not hrc_lesion_channels
                or any(type(c) is not int or not 0 <= c < num_classes for c in channels)
                or len(set(channels)) != len(channels)
            ):
                raise ValueError("Host and lesion channels must be distinct output channels")
            if type(hrc_image_channel) is not int or not 0 <= hrc_image_channel < input_channels:
                raise ValueError("hrc_image_channel must index an input channel")
            if type(hrc_irls_iterations) is not int or hrc_irls_iterations < 0:
                raise ValueError("hrc_irls_iterations must be a non-negative integer")
            for name, value in (
                ("hrc_shrinkage_cells", hrc_shrinkage_cells),
                ("hrc_gland_prior_cells", hrc_gland_prior_cells),
                ("hrc_robust_k", hrc_robust_k),
            ):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    raise ValueError(f"{name} must be a non-negative number")
            if hrc_gland_prior_sd is None:
                # 3 sigma0, i.e. 15 HU at the planned sigma0 of 5 HU: parenchymal scale.
                hrc_gland_prior_sd = 3.0 * float(hrc_sigma0)
            if (
                isinstance(hrc_gland_prior_sd, bool)
                or not isinstance(hrc_gland_prior_sd, (int, float))
                or not hrc_gland_prior_sd > 0
            ):
                raise ValueError("hrc_gland_prior_sd must be a positive normalised intensity")
            levels = _hrc_level_list(hrc_levels, hrc_stats_level, n_stages)
            cumulative = [1, 1, 1]
            self.hrc_grid_strides: list[tuple[int, int, int]] = []
            for stride in self.encoder.strides:
                if len(stride) != 3:
                    raise ValueError("HRCResEncUNet requires 3D strides")
                cumulative = [a * int(b) for a, b in zip(cumulative, stride, strict=True)]
                self.hrc_grid_strides.append((cumulative[0], cumulative[1], cumulative[2]))
            self.hrc_levels = levels
            self.hrc_stats_level = hrc_stats_level
            self.hrc_reference_mode = hrc_reference_mode
            self.hrc_output_mode = hrc_output_mode
            self.hrc_host_channels = list(hrc_host_channels)
            self.hrc_lesion_channels = list(hrc_lesion_channels)
            self.hrc_image_channel = hrc_image_channel
            self.hrc_sigma0 = float(hrc_sigma0)
            self.hrc_outer_box = list(hrc_outer_box)
            self.hrc_inner_box = list(hrc_inner_box)
            self.hrc_shrinkage_cells = float(hrc_shrinkage_cells)
            self.hrc_gland_prior_cells = float(hrc_gland_prior_cells)
            self.hrc_gland_prior_var = float(hrc_gland_prior_sd) ** 2
            self.hrc_robust_loss = hrc_robust_loss
            self.hrc_robust_k = float(hrc_robust_k)
            self.hrc_irls_iterations = hrc_irls_iterations
            # Built without drawing from the global RNG: with one seed, nnU-Net's
            # initialize() pass then gives the ResEnc modules exactly the weights a
            # plain ResEnc L gets, so paired arms differ only by the HRC modules.
            with torch.random.fork_rng(devices=[]):
                hrc_blocks = {
                    str(level): HostReferenceBlock(
                        self.encoder.output_channels[level],
                        reference_mode=hrc_reference_mode,
                        feature_channels=hrc_feature_channels,
                        hidden_channels=hrc_hidden_channels,
                        sigma0=hrc_sigma0,
                        smoothing_box=hrc_stats_smoothing_box
                        if level == self.hrc_stats_level
                        else hrc_smoothing_box,
                        outer_box=hrc_outer_box,
                        inner_box=hrc_inner_box,
                        shrinkage=hrc_shrinkage_cells,
                    )
                    for level in levels
                }
            self.hrc = nn.ModuleDict(hrc_blocks)
            # Inference-only hooks for the reference-swap and zeroing tests.
            self.reference_override: Callable[[str, HostReference], HostReference] | None = None
            self.capture_reference = False
            self.captured_references: dict[str, HostReference] = {}
            self.architecture_metadata = {
                "name": "hrc_resenc_unet",
                "base": "dynamic_network_architectures ResidualEncoderUNet",
                "initialization": "scratch",
                "pretrained": False,
                "hrc_levels": levels,
                "statistics_level": self.hrc_stats_level,
                "reference_mode": hrc_reference_mode,
                "output_mode": hrc_output_mode,
                "host_channels": self.hrc_host_channels,
                "lesion_channels": self.hrc_lesion_channels,
                "sigma0_normalized": self.hrc_sigma0,
                "gland_prior": {
                    "cells": self.hrc_gland_prior_cells,
                    "sd_normalized": float(hrc_gland_prior_sd),
                },
                "deviation_channels": 8 + hrc_feature_channels,
                "film": "zero-initialised 1x1 convolution; identity at initialisation",
                "supervision": "ResEnc deep-supervision list, finest first; coarse HRC heads always run",
            }

        @staticmethod
        def initialize(module: nn.Module) -> None:
            ResidualEncoderUNet.initialize(module)
            # nn.Module.apply visits children first, so this undoes He init of FiLM.
            if isinstance(module, HostReferenceBlock):
                module.reset_film()

        def _stats_stride(self, level: int) -> tuple[int, int, int]:
            fine, coarse = self.hrc_grid_strides[level], self.hrc_grid_strides[self.hrc_stats_level]
            return (coarse[0] // fine[0], coarse[1] // fine[1], coarse[2] // fine[2])

        def _image(self, image: torch.Tensor, level: int) -> torch.Tensor:
            channel = image[:, self.hrc_image_channel : self.hrc_image_channel + 1]
            stride = self.hrc_grid_strides[level]
            if stride == (1, 1, 1):
                return channel
            return nn.functional.avg_pool3d(channel.float(), kernel_size=stride, stride=stride)

        def _reference(self, name: str, logits: torch.Tensor, image: torch.Tensor) -> HostReference:
            host, lesion = host_lesion_probabilities(
                logits,
                output_mode=self.hrc_output_mode,
                host_channels=self.hrc_host_channels,
                lesion_channels=self.hrc_lesion_channels,
            )
            shape = tuple(image.shape[2:])
            if tuple(host.shape[2:]) != shape:
                pair = nn.functional.interpolate(
                    torch.cat([host, lesion], 1), size=shape, mode="trilinear", align_corners=False
                )
                host, lesion = pair[:, :1], pair[:, 1:]
            reference = compute_host_reference(
                image,
                host,
                lesion,
                mode=self.hrc_reference_mode,
                sigma0=self.hrc_sigma0,
                outer=self.hrc_outer_box,
                inner=self.hrc_inner_box,
                shrinkage=self.hrc_shrinkage_cells,
                gland_prior_cells=self.hrc_gland_prior_cells,
                gland_prior_var=self.hrc_gland_prior_var,
                robust_loss=self.hrc_robust_loss,
                robust_k=self.hrc_robust_k,
                iterations=self.hrc_irls_iterations,
            )
            if self.reference_override is not None or self.capture_reference:
                if self.training:
                    raise RuntimeError("Reference override and capture are inference-only")
                if self.capture_reference:
                    self.captured_references[name] = reference.detached()
                if self.reference_override is not None:
                    reference = self.reference_override(name, reference)
            return reference

        def forward(self, x: torch.Tensor) -> torch.Tensor | list[torch.Tensor]:
            skips = self.encoder(x)
            decoder = self.decoder
            stats = self.hrc_stats_level
            stats_image = self._image(x, stats)
            references: dict[str, HostReference] = {}
            heads: dict[int, torch.Tensor] = {}
            outputs = []
            lres_input = skips[-1]
            last = len(decoder.stages) - 1
            for s in range(len(decoder.stages)):
                level = last - s
                features = decoder.transpconvs[s](lres_input)
                features = torch.cat((features, skips[-(s + 2)]), 1)
                features = decoder.stages[s](features)
                if str(level) in self.hrc:
                    name = "coarse" if level == stats else "refined"
                    if name not in references:
                        source = heads[stats + 1] if level == stats else heads[stats]
                        references[name] = self._reference(name, source, stats_image)
                    features = self.hrc[str(level)](
                        features,
                        stats_image if level == stats else self._image(x, level),
                        references[name],
                        self._stats_stride(level),
                    )
                if decoder.deep_supervision or s == last or level in (stats, stats + 1):
                    logits = decoder.seg_layers[s](features)
                    heads[level] = logits
                    if decoder.deep_supervision or s == last:
                        outputs.append(logits)
                lres_input = features
            outputs = outputs[::-1]
            return outputs if decoder.deep_supervision else outputs[0]

    HRCResEncUNet.__module__ = __name__
    HRCResEncUNet.__qualname__ = "HRCResEncUNet"
    return HRCResEncUNet


def _define_starc_resenc_unet() -> type:
    """Build ``StarCResEncUNet`` on first use; dynamic-network-architectures is optional here."""
    from dynamic_network_architectures.architectures.unet import ResidualEncoderUNet

    from .star_completion import (
        STARC_NETWORK_DEFAULTS,
        StarCompletion,
        StarInstances,
        validate_starc_options,
    )

    class StarCResEncUNet(ResidualEncoderUNet):
        """ResEnc U-Net with a star-convex lesion completion decoder (STAR-C).

        Module names match ``ResidualEncoderUNet``; the new modules live under
        ``starc.*``, so a ResEnc state dict loads with only ``starc.*`` keys
        missing. The centre and ray heads read decoder level ``starc_level``;
        the gate reads the full-resolution decoder features. Only the
        full-resolution logits are fused, so the deep-supervision list, its
        order and the inference output keep the ResEnc contract. The fusion
        weights start at zero, so at initialisation the logits equal ResEnc's.

        ``star_aux`` holds the last forward's heatmap logits, ray map and the
        rendered instances. ``set_star_instances`` replaces the proposals of the
        next forward only (teacher forcing in training, case-level instances in
        the two-pass predictor).
        """

        def __init__(
            self,
            input_channels: int,
            n_stages: int,
            features_per_stage: Any,
            conv_op: type[nn.Module],
            kernel_sizes: Any,
            strides: Any,
            n_blocks_per_stage: Any,
            num_classes: int,
            n_conv_per_stage_decoder: Any,
            conv_bias: bool = False,
            norm_op: type[nn.Module] | None = None,
            norm_op_kwargs: dict | None = None,
            dropout_op: type[nn.Module] | None = None,
            dropout_op_kwargs: dict | None = None,
            nonlin: type[nn.Module] | None = None,
            nonlin_kwargs: dict | None = None,
            deep_supervision: bool = False,
            *,
            starc_spacing: Sequence[float] | None = None,
            **kwargs: Any,
        ) -> None:
            options = {
                key[len("starc_") :]: kwargs.pop(key)
                for key in list(kwargs)
                if key.startswith("starc_")
            }
            unknown = set(options) - set(STARC_NETWORK_DEFAULTS)
            if unknown:
                raise ValueError(f"Unknown STAR-C network options: {sorted(unknown)}")
            super().__init__(
                input_channels,
                n_stages,
                features_per_stage,
                conv_op,
                kernel_sizes,
                strides,
                n_blocks_per_stage,
                num_classes,
                n_conv_per_stage_decoder,
                conv_bias,
                norm_op,
                norm_op_kwargs,
                dropout_op,
                dropout_op_kwargs,
                nonlin,
                nonlin_kwargs,
                deep_supervision,
                **kwargs,
            )
            if conv_op is not nn.Conv3d:
                raise ValueError("StarCResEncUNet is volumetric; conv_op must be Conv3d")
            if (
                not isinstance(starc_spacing, (list, tuple))
                or len(starc_spacing) != 3
                or not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
                    for v in starc_spacing
                )
            ):
                raise ValueError("starc_spacing must be the plan's three positive spacings (mm)")
            resolved = validate_starc_options(options)
            level = resolved["level"]
            if not 0 <= level <= n_stages - 2:
                raise ValueError("starc_level must be a decoder level")
            cumulative = [1, 1, 1]
            for stride in self.encoder.strides[: level + 1]:
                if len(stride) != 3:
                    raise ValueError("StarCResEncUNet requires 3D strides")
                cumulative = [a * int(b) for a, b in zip(cumulative, stride, strict=True)]
            self.starc_level = level
            self.starc_stride = tuple(cumulative)
            self.starc_spacing = [float(v) for v in starc_spacing]
            self.starc_options = {key: resolved[key] for key in STARC_NETWORK_DEFAULTS}
            # Built without drawing from the global RNG, as for HRC: with one seed,
            # nnU-Net's initialize() pass gives the ResEnc modules exactly the
            # weights a plain ResEnc L gets, so paired arms differ only by starc.*.
            with torch.random.fork_rng(devices=[]):
                starc = StarCompletion(
                    self.encoder.output_channels[level],
                    self.encoder.output_channels[0],
                    num_classes,
                    spacing=self.starc_spacing,
                    stride=self.starc_stride,
                    rays=resolved["rays"],
                    fusion_channels=resolved["fusion_channels"],
                    fusion=resolved["fusion"],
                    max_instances=resolved["max_instances"],
                    centre_threshold=resolved["centre_threshold"],
                    box_margin_mm=resolved["box_margin_mm"],
                    min_ray_mm=resolved["min_ray_mm"],
                    max_ray_mm=resolved["max_ray_mm"],
                    tau_init_mm=resolved["tau_init_mm"],
                    tau_min_mm=resolved["tau_min_mm"],
                    tau_max_mm=resolved["tau_max_mm"],
                    gate_bias=resolved["gate_bias"],
                    prior_scale=resolved["prior_scale"],
                    centre_hidden=resolved["centre_hidden"],
                    ray_hidden=resolved["ray_hidden"],
                    gate_hidden=resolved["gate_hidden"],
                    ray_init_mm=resolved["ray_init_mm"],
                    centre_prior=resolved["centre_prior"],
                    lut_shape=resolved["lut_shape"],
                    norm_op=norm_op or nn.InstanceNorm3d,
                    norm_kwargs=norm_op_kwargs,
                    nonlin=nonlin or nn.LeakyReLU,
                    nonlin_kwargs=nonlin_kwargs,
                )
            self.starc = starc
            self._star_instances: StarInstances | None = None
            self.star_aux: dict[str, Any] | None = None
            self.architecture_metadata = {
                "name": "starc_resenc_unet",
                "base": "dynamic_network_architectures ResidualEncoderUNet",
                "initialization": "scratch",
                "pretrained": False,
                "level": level,
                "level_stride": list(self.starc_stride),
                "spacing_mm": self.starc_spacing,
                "options": self.starc_options,
                "fusion": "zero-initialised per-channel weights times a sigmoid gate; "
                "identity at initialisation",
                "supervision": "ResEnc deep-supervision list, finest first; only the "
                "full-resolution output is fused",
            }

        @staticmethod
        def initialize(module: nn.Module) -> None:
            ResidualEncoderUNet.initialize(module)
            # nn.Module.apply visits children first, so this undoes He init of the heads.
            if isinstance(module, StarCompletion):
                module.reset_star_parameters()

        def set_star_instances(self, instances: StarInstances | None) -> None:
            self._star_instances = instances

        def forward(self, x: torch.Tensor) -> torch.Tensor | list[torch.Tensor]:
            skips = self.encoder(x)
            decoder = self.decoder
            outputs = []
            level_features = None
            lres_input = skips[-1]
            last = len(decoder.stages) - 1
            for s in range(len(decoder.stages)):
                features = decoder.transpconvs[s](lres_input)
                features = torch.cat((features, skips[-(s + 2)]), 1)
                features = decoder.stages[s](features)
                if last - s == self.starc_level:
                    level_features = features
                if decoder.deep_supervision or s == last:
                    outputs.append(decoder.seg_layers[s](features))
                lres_input = features
            assert level_features is not None
            instances, self._star_instances = self._star_instances, None
            fused, self.star_aux = self.starc(level_features, lres_input, outputs[-1], instances)
            outputs[-1] = fused
            outputs = outputs[::-1]
            return outputs if decoder.deep_supervision else outputs[0]

    StarCResEncUNet.__module__ = __name__
    StarCResEncUNet.__qualname__ = "StarCResEncUNet"
    return StarCResEncUNet


_LAZY_CLASSES: dict[str, Callable[[], type]] = {
    "HRCResEncUNet": _define_hrc_resenc_unet,
    "StarCResEncUNet": _define_starc_resenc_unet,
}


def __getattr__(name: str) -> Any:
    # nnU-Net resolves the plan's dotted class path with pydoc.locate, which uses
    # getattr; define the subclasses lazily so this module imports without nnU-Net.
    if name in _LAZY_CLASSES:
        cls = _LAZY_CLASSES[name]()
        globals()[name] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
