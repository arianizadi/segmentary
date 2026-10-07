"""DenseASPP with an ImageNet DenseNet-121 or DenseNet-161 backbone.

Yang et al., "DenseASPP for Semantic Segmentation in Street Scenes", CVPR 2018.

This is a clean Segmentary implementation written from the paper. The authors'
repository (DeepMotionAIResearch/DenseASPP) publishes no license, so none of
its code is copied; it was consulted only for facts the paper leaves open
(per-backbone ASPP widths, the stride-1 fifth transition, the classifier
dropout). Differences from that repository are deliberate and recorded:

* The ImageNet DenseNet comes from timm's pinned torchvision weights
  (``densenet121.tv_in1k`` / ``densenet161.tv_in1k``). Output stride 8 is made
  exactly as in the paper: the average pooling of transitions 2 and 3 is
  removed and the 3x3 convolutions of dense blocks 3 and 4 are dilated by 2 and
  4. Pretrained weights do not depend on stride or dilation.
* As upstream, the pretrained final norm is replaced by a fresh stride-1
  transition (BN-ReLU-1x1 conv halving the channels) and a fresh BatchNorm.
  The ReLU after that BatchNorm is explicit here; upstream obtains the same
  tensor because the first ASPP layer applies ``ReLU(inplace=True)`` to the
  shared feature map before it is concatenated.
* BatchNorm momentum uses the PyTorch default. The upstream ASPP sets
  ``momentum=0.0003``, a TensorFlow-decay value that in PyTorch semantics
  almost freezes the running statistics.
* Logits are produced at stride 8 and resized with the repository-wide
  bilinear ``align_corners=False`` convention, which also handles odd sizes.

The paper trains DenseASPP with a single cross-entropy loss, so there are no
auxiliary heads; ``forward_output`` is the inherited single-tensor contract.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, cast

import timm
import torch
from torch import Tensor, nn

from .preprocessing import record_preprocessing
from .wrappers import SegmentationModel, reinit_, resize_logits

# timm tag -> (d_feature0, d_feature1): the ASPP bottleneck and growth widths
# the authors use with each backbone.
DENSEASPP_VARIANTS: dict[str, tuple[int, int]] = {
    "densenet121.tv_in1k": (128, 64),
    "densenet161.tv_in1k": (512, 128),
}
ASPP_DILATIONS = (3, 6, 12, 18, 24)


class DenseASPPBlock(nn.Module):
    """One densely connected atrous layer: [BN]-ReLU-1x1-BN-ReLU-3x3(d)-Dropout2d."""

    def __init__(
        self,
        in_channels: int,
        bottleneck: int,
        out_channels: int,
        dilation: int,
        dropout: float,
        *,
        pre_norm: bool,
    ) -> None:
        super().__init__()
        self.pre_norm: nn.Module = nn.BatchNorm2d(in_channels) if pre_norm else nn.Identity()
        self.reduce = nn.Conv2d(in_channels, bottleneck, kernel_size=1)
        self.norm = nn.BatchNorm2d(bottleneck)
        self.conv = nn.Conv2d(
            bottleneck, out_channels, kernel_size=3, padding=dilation, dilation=dilation
        )
        self.dropout = nn.Dropout2d(dropout)

    def forward(self, x: Tensor) -> Tensor:
        x = torch.relu(self.pre_norm(x))
        x = self.reduce(x)
        x = self.conv(torch.relu(self.norm(x)))
        return cast(Tensor, self.dropout(x))


def _dilate_dense_block(block: nn.Module, dilation: int) -> None:
    layers = 0
    for layer in block.children():
        conv = getattr(layer, "conv2", None)
        if not isinstance(conv, nn.Conv2d) or conv.kernel_size != (3, 3) or conv.stride != (1, 1):
            raise ValueError("timm DenseNet layer no longer exposes a stride-1 3x3 conv2")
        conv.dilation = (dilation, dilation)
        conv.padding = (dilation, dilation)
        layers += 1
    if layers == 0:
        raise ValueError("timm DenseNet block has no dense layers to dilate")


def _remove_pooling(transition: nn.Module) -> None:
    if not isinstance(getattr(transition, "pool", None), nn.AvgPool2d):
        raise ValueError("timm DenseNet transition no longer ends in a 2x2 average pool")
    cast(Any, transition).pool = nn.Identity()


class DenseASPP(SegmentationModel):
    """DenseNet at output stride 8 followed by five densely connected atrous layers.

    Args:
        num_classes: canonical class count.
        backbone_name: an exact timm tag listed in ``DENSEASPP_VARIANTS``.
        pretrained: load ImageNet weights. False is only for offline tests.
        dropout: dropout after every ASPP layer and before the classifier (0.1).
    """

    def __init__(
        self,
        num_classes: int,
        *,
        backbone_name: str = "densenet121.tv_in1k",
        pretrained: bool = True,
        dropout: float = 0.1,
    ) -> None:
        super().__init__(num_classes)
        if backbone_name not in DENSEASPP_VARIANTS:
            raise ValueError(
                f"DenseASPP backbone {backbone_name!r} is not one of the audited variants "
                f"{sorted(DENSEASPP_VARIANTS)}"
            )
        if not 0.0 <= dropout < 1.0:
            raise ValueError("DenseASPP dropout must be in [0, 1)")
        d_feature0, d_feature1 = DENSEASPP_VARIANTS[backbone_name]
        try:
            trunk = timm.create_model(backbone_name, pretrained=pretrained, num_classes=0)
        except Exception as exc:
            source = "pretrained weights" if pretrained else "scratch initialization"
            raise ValueError(
                f"could not construct timm DenseNet {backbone_name!r} with {source}: {exc}"
            ) from exc
        features = getattr(trunk, "features", None)
        if not isinstance(features, nn.Module):
            raise ValueError(f"timm model {backbone_name!r} exposes no DenseNet features")
        names = [name for name, _ in features.named_children()]
        expected = [
            "conv0",
            "norm0",
            "pool0",
            "denseblock1",
            "transition1",
            "denseblock2",
            "transition2",
            "denseblock3",
            "transition3",
            "denseblock4",
            "norm5",
        ]
        if names != expected:
            raise ValueError(f"unexpected timm DenseNet feature layout {names}")
        _remove_pooling(features.get_submodule("transition2"))
        _remove_pooling(features.get_submodule("transition3"))
        _dilate_dense_block(features.get_submodule("denseblock3"), 2)
        _dilate_dense_block(features.get_submodule("denseblock4"), 4)
        # The pretrained classification norm5 is not used (see module docstring).
        self.backbone = nn.Sequential(
            OrderedDict(
                (name, module) for name, module in features.named_children() if name != "norm5"
            )
        )
        channels = int(cast(Any, trunk).num_features)
        reduced = channels // 2
        self.neck = nn.Sequential(
            OrderedDict(
                [
                    ("transition_norm", nn.BatchNorm2d(channels)),
                    ("transition_act", nn.ReLU()),
                    ("transition_conv", nn.Conv2d(channels, reduced, kernel_size=1, bias=False)),
                    ("norm", nn.BatchNorm2d(reduced)),
                    ("act", nn.ReLU()),
                ]
            )
        )
        self.aspp = nn.ModuleList(
            DenseASPPBlock(
                reduced + index * d_feature1,
                d_feature0,
                d_feature1,
                dilation,
                dropout,
                pre_norm=index > 0,
            )
            for index, dilation in enumerate(ASPP_DILATIONS)
        )
        self.dropout = nn.Dropout2d(dropout)
        self.classifier = nn.Conv2d(
            reduced + len(ASPP_DILATIONS) * d_feature1, num_classes, kernel_size=1
        )
        for module in (self.neck, self.aspp, self.classifier):
            for layer in module.modules():
                if isinstance(layer, nn.Conv2d):
                    nn.init.kaiming_uniform_(layer.weight)
                    if layer.bias is not None:
                        nn.init.zeros_(layer.bias)
        self.backbone_name = backbone_name
        record_preprocessing(
            self,
            where=f"DenseASPP backbone {backbone_name!r}",
            pretrained_cfg=dict(cast(Any, trunk).pretrained_cfg) if pretrained else None,
        )

    def forward(self, pixel_values: Tensor) -> Tensor:
        feature = self.neck(self.backbone(pixel_values))
        for block in self.aspp:
            # New atrous features go first, as in the reference implementation.
            feature = torch.cat((block(feature), feature), dim=1)
        logits = self.classifier(self.dropout(feature))
        logits = resize_logits(logits, tuple(pixel_values.shape[-2:]))
        return self._check_output(logits, pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return ("neck.", "aspp.", "classifier.")

    def backbone_modules(self) -> list[nn.Module]:
        return [self.backbone]

    def reset_head(self) -> None:
        if reinit_(self.classifier) != 1:
            raise ValueError("DenseASPP classifier is no longer a single 1x1 convolution")
