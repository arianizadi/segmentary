"""Scratch architectures implementing the nnU-Net 2.8.1 network contract.

The trainer and predictor import this class through the architecture dotted path
in a frozen plans file. All preprocessing, augmentation, losses and optimization
remain in nnU-Net. This bridge changes the network topology only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
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
