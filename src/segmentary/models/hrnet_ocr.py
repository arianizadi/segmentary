"""HRNet-W48 + OCR: the legacy CNN baseline.

timm supplies the HRNet trunk (ImageNet weights, four parallel branches kept at
strides 4/8/16/32); ``heads.OCRHead`` supplies the segmentation head. The
classification head timm attaches -- ``incre_modules``, ``downsamp_modules``,
``final_layer``, ``classifier`` -- is removed at construction: keeping it would
add tens of millions of parameters that receive no gradient signal but still get
allocated optimiser state and written into every checkpoint.

Public inference returns only the refined logits. Training uses the richer
``SegmentationOutput`` contract so the coarse OCR logits receive their own
weighted auxiliary loss instead of learning only indirectly through region
pooling.
"""

from __future__ import annotations

import math
from typing import Any, cast

import timm
import torch.nn as nn
from torch import Tensor

from .heads import OCRHead, concat_multi_scale
from .outputs import AuxiliaryDenseOutput, SegmentationOutput
from .wrappers import SegmentationModel, reinit_, reinit_component_, resize_logits


class HRNetOCR(SegmentationModel):
    """timm HRNet trunk with an OCR head, output upsampled to input resolution.

    Args:
        num_classes: canonical class count.
        backbone_name: any timm HRNet variant, e.g. ``hrnet_w48``.
        pretrained: load ImageNet weights. False is only for tests.
        ocr_channels: OCR pixel-representation width.
        key_channels: OCR attention width.
    """

    def __init__(
        self,
        num_classes: int,
        backbone_name: str = "hrnet_w48",
        pretrained: bool = True,
        ocr_channels: int = 512,
        key_channels: int = 256,
        coarse_loss_weight: float = 0.4,
    ) -> None:
        super().__init__(num_classes)
        if not math.isfinite(coarse_loss_weight) or coarse_loss_weight <= 0.0:
            raise ValueError("coarse_loss_weight must be finite and positive")
        self.coarse_loss_weight = float(coarse_loss_weight)
        # No drop_path here on purpose: timm's HighResolutionNet has no
        # drop_path_rate argument, builds no DropPath modules, and absorbs the
        # keyword into **kwargs without complaint. Accepting it would report
        # stochastic depth in the config hash of a run that never used any.
        trunk = timm.create_model(backbone_name, pretrained=pretrained, num_classes=0)

        if not hasattr(trunk, "stage4_cfg"):
            raise ValueError(
                f"{backbone_name!r} is not a timm HRNet (no stage4_cfg); HRNetOCR reads its "
                f"branch widths from that config"
            )
        # Strip timm's classification path so forward_features returns the four
        # branch feature maps. nn.Module types attribute writes as
        # Tensor | Module, which cannot express "set this submodule to None".
        trunk_attrs = cast(Any, trunk)
        trunk_attrs.incre_modules = None
        trunk_attrs.downsamp_modules = None
        trunk_attrs.final_layer = nn.Identity()
        trunk_attrs.global_pool = nn.Identity()
        trunk_attrs.classifier = nn.Identity()
        self.trunk = trunk

        stage4_cfg = cast(dict[str, Any], trunk.stage4_cfg)
        in_channels = sum(stage4_cfg["num_channels"])
        self.head = OCRHead(
            in_channels, num_classes, ocr_channels=ocr_channels, key_channels=key_channels
        )

    def _predictions(self, pixel_values: Tensor) -> tuple[Tensor, Tensor]:
        # With incre_modules removed, forward_features returns the four branch
        # feature maps rather than a fused classification embedding.
        branches = cast(Any, self.trunk).forward_features(pixel_values)
        if not isinstance(branches, (list, tuple)):
            raise ValueError(
                "HRNet trunk returned a fused tensor; its classification head was not removed"
            )
        logits, coarse = self.head(concat_multi_scale(list(branches)))
        output_size = tuple(pixel_values.shape[-2:])
        logits = self._check_output(resize_logits(logits, output_size), pixel_values)
        coarse = self._check_output(resize_logits(coarse, output_size), pixel_values)
        return logits, coarse

    def forward(self, pixel_values: Tensor) -> Tensor:
        logits, _ = self._predictions(pixel_values)
        return logits

    def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
        logits, coarse = self._predictions(pixel_values)
        return SegmentationOutput(
            dense_logits=logits,
            auxiliary_dense=(AuxiliaryDenseOutput("ocr_coarse", coarse, self.coarse_loss_weight),),
        )

    def head_patterns(self) -> tuple[str, ...]:
        return ("head.",)

    def backbone_modules(self) -> list[nn.Module]:
        return [self.trunk]

    def reset_head(self) -> None:
        # Only the two 1x1 classifiers, not the OCR attention or bottleneck: those
        # are class-agnostic feature machinery and are worth carrying across stages.
        reinit_component_(self, "classifier")
        # coarse is Sequential(conv_bn_relu, Conv2d); only the 1x1 is the classifier.
        if reinit_(self.head.coarse[-1]) != 1:
            raise ValueError(
                "the OCR auxiliary head no longer ends in a single 1x1 classifier; reset_head "
                "would leave the coarse region logits pointing at the previous label space"
            )
