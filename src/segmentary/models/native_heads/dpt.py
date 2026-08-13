"""DPT-inspired progressive multi-scale fusion for native feature pyramids.

This is an original Segmentary implementation of the architectural principles in
Ranftl, Bochkovskiy, and Koltun (ICCV 2021): refine multiple image-like feature
maps, progressively combine coarse context with finer skips, build a half-scale
representation, and bilinearly upsample semantic logits.  It is not a copy of
the authors' implementation and does not implement their transformer-token
reassembly stage; a native neck supplies already-spatial feature maps.
"""

from __future__ import annotations

from torch import Tensor, nn

from ..features import FeatureMaps, FeatureSpec, require_increasing_reductions
from ..layers import ActivationKind, ConvNormAct, NormKind, build_activation, build_norm
from ..wrappers import reinit_
from .base import DenseHead, resize
from .blocks import checked_dropout


class ResidualConvUnit(nn.Module):
    """Two pre-activated 3x3 convolutions with an identity residual path."""

    def __init__(
        self,
        channels: int,
        *,
        norm: NormKind,
        activation: ActivationKind,
    ) -> None:
        super().__init__()
        if isinstance(channels, bool) or not isinstance(channels, int) or channels < 1:
            raise ValueError("DPT residual channels must be a positive integer")
        bias = norm == "none"
        self.channels = channels
        self.activation1 = build_activation(activation)
        self.conv1 = nn.Conv2d(channels, channels, 3, padding=1, bias=bias)
        self.norm1 = build_norm(norm, channels)
        self.activation2 = build_activation(activation)
        self.conv2 = nn.Conv2d(channels, channels, 3, padding=1, bias=bias)
        self.norm2 = build_norm(norm, channels)

    def forward(self, feature: Tensor) -> Tensor:
        if feature.ndim != 4 or int(feature.shape[1]) != self.channels:
            raise ValueError(
                f"DPT residual unit expected N,{self.channels},H,W, got {tuple(feature.shape)}"
            )
        refined = self.norm1(self.conv1(self.activation1(feature)))
        refined = self.norm2(self.conv2(self.activation2(refined)))
        return feature + refined


class DPTHead(DenseHead):
    """Fuse exactly four equal-width spatial features from coarse to fine."""

    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        *,
        in_indices: tuple[int, ...],
        channels: int,
        dropout: float = 0.1,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        if not isinstance(in_indices, tuple) or len(in_indices) != 4:
            raise ValueError("DPT head requires exactly four feature levels")
        super().__init__(input_specs, num_classes, in_indices, minimum_inputs=4)
        require_increasing_reductions(self.selected_specs, where="DPT head")
        if isinstance(channels, bool) or not isinstance(channels, int) or channels < 1:
            raise ValueError("DPT channels must be a positive integer")
        mismatched = [
            (spec.name, spec.channels) for spec in self.selected_specs if spec.channels != channels
        ]
        if mismatched:
            raise ValueError(
                f"DPT head requires four features already mapped to channels={channels}; "
                f"mismatched levels={mismatched}. Add a ChannelMapper neck or align its "
                "out_channels with model.native.head.channels."
            )

        self.channels = channels
        self.deep_refine = ResidualConvUnit(channels, norm=norm, activation=activation)
        self.skip_refines = nn.ModuleList(
            ResidualConvUnit(channels, norm=norm, activation=activation)
            for _ in self.selected_specs[:-1]
        )
        self.fusion_refines = nn.ModuleList(
            ResidualConvUnit(channels, norm=norm, activation=activation)
            for _ in self.selected_specs[:-1]
        )
        self.half_scale_refine = ResidualConvUnit(channels, norm=norm, activation=activation)
        self.output_block = ConvNormAct(
            channels,
            channels,
            3,
            norm=norm,
            activation=activation,
        )
        self.dropout = nn.Dropout2d(checked_dropout(dropout))
        self.classifier = nn.Conv2d(channels, num_classes, 1)

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        selected = self.selected_features(features)
        current = self.deep_refine(selected[-1])

        # Coarse-to-fine refinement. Runtime feature sizes, rather than assumed
        # exact powers of two, keep odd input dimensions aligned to their skips.
        for fusion_index, level_index in enumerate(range(len(selected) - 2, -1, -1)):
            lateral = self.skip_refines[level_index](selected[level_index])
            current = resize(current, tuple(lateral.shape[-2:]))
            current = self.fusion_refines[fusion_index](current + lateral)

        # The DPT semantic decoder forms a half-resolution representation before
        # its task head; the final checked resize returns full-resolution logits.
        half_size = (
            max(1, (int(output_size[0]) + 1) // 2),
            max(1, (int(output_size[1]) + 1) // 2),
        )
        current = self.half_scale_refine(resize(current, half_size))
        logits = self.classifier(self.dropout(self.output_block(current)))
        return self.checked_logits(logits, output_size)

    def reset_classifier(self) -> None:
        if reinit_(self.classifier) != 1:
            raise RuntimeError("DPT classifier reset changed no layer")
