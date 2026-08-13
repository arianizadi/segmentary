"""HRNet-W48 + OCR: the legacy CNN baseline.

timm supplies the HRNet trunk (ImageNet weights, four parallel branches kept at
strides 4/8/16/32); ``heads.OCRHead`` supplies the segmentation head. The
classification head timm attaches -- ``incre_modules``, ``downsamp_modules``,
``final_layer``, ``classifier`` -- is removed at construction: keeping it would
add tens of millions of parameters that receive no gradient signal but still get
allocated optimiser state and written into every checkpoint.

Deviation from the paper, stated plainly: OCR is normally trained with deep
supervision on the coarse auxiliary logits. ``SegmentationModel.forward``
returns exactly one tensor, and ``engine.losses`` has no slot for a second
head, so the auxiliary classifier here is trained only through the gradient that
reaches it via the region-pooling softmax. That is weaker supervision than the
paper's, and this baseline should be read accordingly.
"""

from __future__ import annotations

from typing import Any, cast

import timm
import torch.nn as nn
from torch import Tensor

from .heads import OCRHead, concat_multi_scale
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
    ) -> None:
        super().__init__(num_classes)
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

    def forward(self, pixel_values: Tensor) -> Tensor:
        # With incre_modules removed, forward_features returns the four branch
        # feature maps rather than a fused classification embedding.
        branches = cast(Any, self.trunk).forward_features(pixel_values)
        if not isinstance(branches, (list, tuple)):
            raise ValueError(
                "HRNet trunk returned a fused tensor; its classification head was not removed"
            )
        logits, _aux = self.head(concat_multi_scale(list(branches)))
        logits = resize_logits(logits, tuple(pixel_values.shape[-2:]))
        return self._check_output(logits, pixel_values)

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
