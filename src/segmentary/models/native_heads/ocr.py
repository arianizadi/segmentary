"""Object-contextual refinement with an explicitly supervised coarse map.

This is an original Segmentary implementation of the OCR formulation from Yuan,
Chen, and Wang (ECCV 2020).  Coarse class logits define soft object regions;
the head gathers one representation per class, relates every pixel to those
regions, fuses the resulting context with the pixel feature, and predicts a
refined segmentation.  The coarse logits remain a named positive-weight
training output rather than an unoptimized internal side effect.
"""

from __future__ import annotations

import math

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from ..features import FeatureMaps, FeatureSpec, require_increasing_reductions
from ..layers import ActivationKind, ConvNormAct, NormKind
from ..outputs import AuxiliaryDenseOutput, SegmentationOutput
from ..wrappers import reinit_
from .base import DenseHead, resize
from .blocks import checked_dropout


class ObjectContextBlock(nn.Module):
    """Relate spatial pixels to class-region representations and return context."""

    def __init__(
        self,
        channels: int,
        key_channels: int,
        *,
        attention_scale: int,
        norm: NormKind,
        activation: ActivationKind,
    ) -> None:
        super().__init__()
        if isinstance(channels, bool) or not isinstance(channels, int) or channels < 1:
            raise ValueError("OCR channels must be a positive integer")
        if isinstance(key_channels, bool) or not isinstance(key_channels, int) or key_channels < 1:
            raise ValueError("OCR key_channels must be a positive integer")
        if (
            isinstance(attention_scale, bool)
            or not isinstance(attention_scale, int)
            or attention_scale < 1
        ):
            raise ValueError("OCR attention_scale must be a positive integer")
        self.channels = channels
        self.key_channels = key_channels
        self.attention_scale = attention_scale
        self.pixel_query = ConvNormAct(channels, key_channels, 1, norm=norm, activation=activation)
        self.region_key = ConvNormAct(channels, key_channels, 1, norm=norm, activation=activation)
        self.region_value = ConvNormAct(channels, key_channels, 1, norm=norm, activation=activation)
        self.context_projection = ConvNormAct(
            key_channels, channels, 1, norm=norm, activation=activation
        )

    def forward(self, pixels: Tensor, regions: Tensor) -> Tensor:
        if pixels.ndim != 4 or int(pixels.shape[1]) != self.channels:
            raise ValueError(f"OCR pixels must be N,{self.channels},H,W, got {tuple(pixels.shape)}")
        if (
            regions.ndim != 4
            or int(regions.shape[0]) != int(pixels.shape[0])
            or int(regions.shape[1]) != self.channels
            or int(regions.shape[2]) < 2
            or int(regions.shape[3]) != 1
        ):
            raise ValueError(
                f"OCR regions must be N,{self.channels},K,1 with K>=2 and matching batch, got "
                f"{tuple(regions.shape)}"
            )
        original_size = (int(pixels.shape[2]), int(pixels.shape[3]))
        if self.attention_scale > min(original_size):
            raise ValueError(
                f"OCR attention_scale={self.attention_scale} exceeds pixel feature size "
                f"{original_size}"
            )
        relation_pixels = (
            F.max_pool2d(
                pixels,
                kernel_size=self.attention_scale,
                stride=self.attention_scale,
            )
            if self.attention_scale > 1
            else pixels
        )
        batch_size, _, height, width = relation_pixels.shape
        queries = self.pixel_query(relation_pixels).flatten(2).transpose(1, 2)
        keys = self.region_key(regions).flatten(2)
        values = self.region_value(regions).flatten(2).transpose(1, 2)
        relations = torch.bmm(queries, keys) * (self.key_channels**-0.5)
        relations = relations.softmax(dim=-1)
        context = torch.bmm(relations, values).transpose(1, 2).contiguous()
        context = context.reshape(batch_size, self.key_channels, height, width)
        context = self.context_projection(context)
        return resize(context, original_size)


class OCRHead(DenseHead):
    """Fuse a feature pyramid and refine pixels with supervised object context."""

    _COARSE_NAME = "ocr_coarse"

    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...],
        num_classes: int,
        *,
        in_indices: tuple[int, ...],
        channels: int,
        key_channels: int,
        attention_scale: int = 1,
        dropout: float = 0.05,
        coarse_loss_weight: float = 0.4,
        norm: NormKind = "group",
        activation: ActivationKind = "relu",
    ) -> None:
        super().__init__(input_specs, num_classes, in_indices)
        require_increasing_reductions(self.selected_specs, where="OCR head")
        if isinstance(channels, bool) or not isinstance(channels, int) or channels < 1:
            raise ValueError("OCR channels must be a positive integer")
        if (
            not isinstance(coarse_loss_weight, (int, float))
            or isinstance(coarse_loss_weight, bool)
            or not math.isfinite(coarse_loss_weight)
            or coarse_loss_weight <= 0.0
        ):
            raise ValueError("OCR coarse_loss_weight must be finite and positive")
        self.channels = channels
        self.coarse_loss_weight = float(coarse_loss_weight)
        input_channels = sum(spec.channels for spec in self.selected_specs)
        self.feature_projection = ConvNormAct(
            input_channels, channels, 3, norm=norm, activation=activation
        )
        self.coarse_classifier = nn.Conv2d(channels, num_classes, 1)
        self.object_context = ObjectContextBlock(
            channels,
            key_channels,
            attention_scale=attention_scale,
            norm=norm,
            activation=activation,
        )
        self.context_fusion = ConvNormAct(
            2 * channels, channels, 1, norm=norm, activation=activation
        )
        self.dropout = nn.Dropout2d(checked_dropout(dropout))
        self.classifier = nn.Conv2d(channels, num_classes, 1)

    @property
    def auxiliary_output_names(self) -> tuple[str, ...]:
        return (self._COARSE_NAME,)

    @staticmethod
    def object_region_logits(coarse_logits: Tensor) -> Tensor:
        """Return class-region logits without changing public output channels.

        Multiclass OCR uses its coarse logits unchanged, preserving the original
        execution bit for bit. A one-logit binary model represents the two-class
        logit difference ``z``. The centered equivalent logits ``[-z/2, z/2]``
        preserve ``softmax(...)[positive] == sigmoid(z)`` while providing two
        separately pooled negative/positive regions for object-context attention.
        """

        if coarse_logits.ndim != 4 or coarse_logits.shape[1] < 1:
            raise ValueError(
                "OCR coarse logits must be NCHW with at least one output channel, got "
                f"{tuple(coarse_logits.shape)}"
            )
        if coarse_logits.shape[1] != 1:
            return coarse_logits
        half_difference = 0.5 * coarse_logits
        return torch.cat((-half_difference, half_difference), dim=1)

    @staticmethod
    def gather_object_regions(features: Tensor, coarse_logits: Tensor) -> Tensor:
        """Spatial-softmax pool pixels into one representation per class."""

        if features.ndim != 4 or coarse_logits.ndim != 4:
            raise ValueError("OCR gather expects NCHW features and coarse logits")
        if (
            features.shape[0] != coarse_logits.shape[0]
            or features.shape[-2:] != coarse_logits.shape[-2:]
        ):
            raise ValueError(
                f"OCR gather feature/logit shapes disagree: {tuple(features.shape)} vs "
                f"{tuple(coarse_logits.shape)}"
            )
        weights = coarse_logits.flatten(2).softmax(dim=-1)
        regions = torch.bmm(features.flatten(2), weights.transpose(1, 2))
        return regions.unsqueeze(-1).contiguous()

    def _predictions(
        self, features: FeatureMaps, output_size: tuple[int, int]
    ) -> tuple[Tensor, Tensor]:
        selected = self.selected_features(features)
        fusion_size = tuple(selected[0].shape[-2:])
        fused = self.feature_projection(
            torch.cat([resize(feature, fusion_size) for feature in selected], dim=1)
        )
        coarse_native = self.coarse_classifier(fused)
        regions = self.gather_object_regions(
            fused,
            self.object_region_logits(coarse_native),
        )
        context = self.object_context(fused, regions)
        refined = self.context_fusion(torch.cat((fused, context), dim=1))
        primary_native = self.classifier(self.dropout(refined))
        return (
            self.checked_logits(primary_native, output_size),
            self.checked_logits(coarse_native, output_size),
        )

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        primary, _ = self._predictions(features, output_size)
        return primary

    def forward_output(
        self, features: FeatureMaps, output_size: tuple[int, int]
    ) -> SegmentationOutput:
        primary, coarse = self._predictions(features, output_size)
        return SegmentationOutput(
            dense_logits=primary,
            auxiliary_dense=(
                AuxiliaryDenseOutput(
                    self._COARSE_NAME,
                    coarse,
                    self.coarse_loss_weight,
                ),
            ),
        )

    def reset_classifier(self) -> None:
        hits = reinit_(self.coarse_classifier) + reinit_(self.classifier)
        if hits != 2:
            raise RuntimeError(f"OCR classifier reset changed {hits} layers, expected 2")
