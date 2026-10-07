"""BiSeNet V1 (ResNet-18 context path) and BiSeNet V2 as Segmentary built-ins.

BiSeNet V1
    Yu et al., "BiSeNet: Bilateral Segmentation Network for Real-time Semantic
    Segmentation", ECCV 2018.  The module structure, layer widths, attention
    placement and initialization below are adapted from CoinCheung/BiSeNet,
    https://github.com/CoinCheung/BiSeNet/blob/6b4b67a8e3eb0cc23b3d7a94843a7c3c11dedca8/lib/models/bisenetv1.py
    (MIT License, reproduced below).  Local changes: the hand-written ResNet-18
    and its torchvision checkpoint download are replaced by timm's
    ``resnet18.tv_in1k`` (the same torchvision ImageNet weights) through
    Segmentary's fail-closed ``TimmBackbone``; fixed-factor ``nn.Upsample``
    calls are replaced by size-targeted interpolation so odd input sizes work;
    the classifiers emit stride-8 logits that the wrapper resizes with the
    repository-wide bilinear convention; optimizer helpers, ``aux_mode`` and the
    argmax export path are removed because the auxiliary heads are selected by
    ``nn.Module.training`` and Segmentary's public forward always returns logits.

BiSeNet V2
    Yu et al., "BiSeNet V2: Bilateral Network with Guided Aggregation for
    Real-time Semantic Segmentation", IJCV 2021.  The architecture is the copy
    already vendored for the medical pipeline in
    ``segmentary.medical.two_d_bisenet`` (CoinCheung/BiSeNet @6b4b67a, MIT).
    It is imported, not duplicated, and that file is deliberately left
    byte-identical: the medical runner hashes every ``medical/*.py`` file into
    its experiment code identity, so moving or editing it would invalidate the
    binding of existing medical runs.  This wrapper calls the upstream
    submodules directly so the four booster heads run only in training mode.

MIT License

Copyright (c) 2018 CoinCheung

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import math
from typing import cast

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from .backbones import TimmBackbone
from .outputs import AuxiliaryDenseOutput, SegmentationOutput
from .preprocessing import record_preprocessing
from .wrappers import SegmentationModel, reinit_, resize_logits

BISENETV1_BACKBONE = "resnet18.tv_in1k"


def _positive_weight(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _kaiming_a1_(module: nn.Module) -> None:
    # CoinCheung's init_weight: kaiming_normal_(a=1) on every convolution of the
    # freshly initialized BiSeNet modules, zero bias. BatchNorm keeps 1/0.
    for layer in module.modules():
        if isinstance(layer, nn.Conv2d):
            nn.init.kaiming_normal_(layer.weight, a=1)
            if layer.bias is not None:
                nn.init.zeros_(layer.bias)


class ConvBNReLU(nn.Module):
    def __init__(
        self, in_chan: int, out_chan: int, ks: int = 3, stride: int = 1, padding: int = 1
    ) -> None:
        super().__init__()
        self.conv = nn.Conv2d(
            in_chan, out_chan, kernel_size=ks, stride=stride, padding=padding, bias=False
        )
        self.bn = nn.BatchNorm2d(out_chan)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: Tensor) -> Tensor:
        return self.relu(self.bn(self.conv(x)))


class BiSeNetOutput(nn.Module):
    """3x3 ConvBNReLU followed by the 1x1 ``classifier`` (upstream ``conv_out``)."""

    def __init__(self, in_chan: int, mid_chan: int, n_classes: int) -> None:
        super().__init__()
        self.conv = ConvBNReLU(in_chan, mid_chan, ks=3, stride=1, padding=1)
        self.classifier = nn.Conv2d(mid_chan, n_classes, kernel_size=1, bias=True)

    def forward(self, x: Tensor) -> Tensor:
        return self.classifier(self.conv(x))


class AttentionRefinementModule(nn.Module):
    def __init__(self, in_chan: int, out_chan: int) -> None:
        super().__init__()
        self.conv = ConvBNReLU(in_chan, out_chan, ks=3, stride=1, padding=1)
        self.conv_atten = nn.Conv2d(out_chan, out_chan, kernel_size=1, bias=False)
        self.bn_atten = nn.BatchNorm2d(out_chan)

    def forward(self, x: Tensor) -> Tensor:
        feat = self.conv(x)
        atten = torch.mean(feat, dim=(2, 3), keepdim=True)
        atten = self.bn_atten(self.conv_atten(atten)).sigmoid()
        return torch.mul(feat, atten)


class ContextPath(nn.Module):
    """Upstream ``ContextPath`` minus its ResNet-18, which is ``BiSeNetV1.backbone``."""

    def __init__(self, channels16: int = 256, channels32: int = 512) -> None:
        super().__init__()
        self.arm16 = AttentionRefinementModule(channels16, 128)
        self.arm32 = AttentionRefinementModule(channels32, 128)
        self.conv_head32 = ConvBNReLU(128, 128, ks=3, stride=1, padding=1)
        self.conv_head16 = ConvBNReLU(128, 128, ks=3, stride=1, padding=1)
        self.conv_avg = ConvBNReLU(channels32, 128, ks=1, stride=1, padding=0)

    def forward(
        self, feat16: Tensor, feat32: Tensor, size8: tuple[int, int]
    ) -> tuple[Tensor, Tensor]:
        avg = self.conv_avg(torch.mean(feat32, dim=(2, 3), keepdim=True))
        feat32_sum = self.arm32(feat32) + avg
        # Upstream uses nn.Upsample(scale_factor=2) (nearest); targeting the
        # skip's real size is identical for even sizes and also handles odd ones.
        feat32_up = F.interpolate(feat32_sum, size=feat16.shape[-2:], mode="nearest")
        feat32_up = self.conv_head32(feat32_up)
        feat16_sum = self.arm16(feat16) + feat32_up
        feat16_up = F.interpolate(feat16_sum, size=size8, mode="nearest")
        feat16_up = self.conv_head16(feat16_up)
        return feat16_up, feat32_up


class SpatialPath(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv1 = ConvBNReLU(3, 64, ks=7, stride=2, padding=3)
        self.conv2 = ConvBNReLU(64, 64, ks=3, stride=2, padding=1)
        self.conv3 = ConvBNReLU(64, 64, ks=3, stride=2, padding=1)
        self.conv_out = ConvBNReLU(64, 128, ks=1, stride=1, padding=0)

    def forward(self, x: Tensor) -> Tensor:
        return self.conv_out(self.conv3(self.conv2(self.conv1(x))))


class FeatureFusionModule(nn.Module):
    def __init__(self, in_chan: int, out_chan: int) -> None:
        super().__init__()
        self.convblk = ConvBNReLU(in_chan, out_chan, ks=1, stride=1, padding=0)
        self.conv = nn.Conv2d(out_chan, out_chan, kernel_size=1, stride=1, padding=0, bias=False)
        self.bn = nn.BatchNorm2d(out_chan)

    def forward(self, fsp: Tensor, fcp: Tensor) -> Tensor:
        feat = self.convblk(torch.cat([fsp, fcp], dim=1))
        atten = torch.mean(feat, dim=(2, 3), keepdim=True)
        atten = self.bn(self.conv(atten)).sigmoid()
        return torch.mul(feat, atten) + feat


class BiSeNetV1(SegmentationModel):
    """BiSeNet V1 with an ImageNet ResNet-18 context path and two auxiliary heads.

    Public ``forward`` returns only the fused-path logits. In training mode
    ``forward_output`` additionally returns the two context-path auxiliary
    predictions (upstream ``conv_out16``/``conv_out32``), each weighted by
    ``aux_loss_weight`` (the paper's alpha = 1). In eval mode the auxiliary
    heads are not run.

    Args:
        num_classes: canonical class count.
        backbone_name: exact timm tag of the ResNet-18 context path.
        pretrained: load ImageNet weights. False is only for offline tests.
        aux_loss_weight: weight of each context-path auxiliary loss.
    """

    AUXILIARY_NAMES = ("context_path_s8", "context_path_s16")

    def __init__(
        self,
        num_classes: int,
        *,
        backbone_name: str = BISENETV1_BACKBONE,
        pretrained: bool = True,
        aux_loss_weight: float = 1.0,
    ) -> None:
        super().__init__(num_classes)
        self.aux_loss_weight = _positive_weight(aux_loss_weight, name="aux_loss_weight")
        # out_indices 3/4 are ResNet layer3/4, the stride-16/32 maps the upstream
        # context path refines. Upstream also returns layer2 but never uses it:
        # the stride-8 detail comes from the spatial path.
        self.backbone = TimmBackbone(backbone_name, pretrained=pretrained, out_indices=(3, 4))
        specs = self.backbone.output_specs
        if tuple(spec.reduction for spec in specs) != (16, 32):
            raise ValueError(
                f"BiSeNetV1 needs stride-16/32 context features; {backbone_name!r} reports "
                f"{tuple(spec.reduction for spec in specs)}"
            )
        self.spatial_path = SpatialPath()
        self.context_path = ContextPath(specs[0].channels, specs[1].channels)
        self.ffm = FeatureFusionModule(256, 256)
        self.decode_head = BiSeNetOutput(256, 256, num_classes)
        self.aux_heads = nn.ModuleDict(
            {
                "context_path_s8": BiSeNetOutput(128, 64, num_classes),
                "context_path_s16": BiSeNetOutput(128, 64, num_classes),
            }
        )
        for module in (
            self.spatial_path,
            self.context_path,
            self.ffm,
            self.decode_head,
            self.aux_heads,
        ):
            _kaiming_a1_(module)
        record_preprocessing(
            self,
            where=f"BiSeNetV1 backbone {backbone_name!r}",
            pretrained_cfg=self.backbone.pretrained_cfg if pretrained else None,
        )

    def _run(self, pixel_values: Tensor, *, auxiliary: bool) -> SegmentationOutput:
        feat16, feat32 = self.backbone.forward_features(pixel_values)
        feat_sp = self.spatial_path(pixel_values)
        size8 = (int(feat_sp.shape[-2]), int(feat_sp.shape[-1]))
        feat_cp8, feat_cp16 = self.context_path(feat16, feat32, size8)
        logits = self.decode_head(self.ffm(feat_sp, feat_cp8))
        size = tuple(pixel_values.shape[-2:])
        logits = self._check_output(resize_logits(logits, size), pixel_values)
        if not auxiliary:
            return SegmentationOutput(dense_logits=logits)
        extra = tuple(
            AuxiliaryDenseOutput(
                name,
                self._check_output(
                    resize_logits(self.aux_heads[name](feature), size), pixel_values
                ),
                self.aux_loss_weight,
            )
            for name, feature in zip(self.AUXILIARY_NAMES, (feat_cp8, feat_cp16), strict=True)
        )
        return SegmentationOutput(dense_logits=logits, auxiliary_dense=extra)

    def forward(self, pixel_values: Tensor) -> Tensor:
        output = self._run(pixel_values, auxiliary=False)
        assert output.dense_logits is not None
        return output.dense_logits

    def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
        return self._run(pixel_values, auxiliary=self.training)

    def head_patterns(self) -> tuple[str, ...]:
        # Everything except the ImageNet ResNet-18 is freshly initialized.
        return ("spatial_path.", "context_path.", "ffm.", "decode_head.", "aux_heads.")

    def backbone_modules(self) -> list[nn.Module]:
        return [self.backbone]

    def reset_head(self) -> None:
        heads = [self.decode_head, *(cast(BiSeNetOutput, h) for h in self.aux_heads.values())]
        if sum(reinit_(head.classifier) for head in heads) != len(heads):
            raise ValueError("BiSeNetV1 classifiers are no longer single 1x1 convolutions")


class BiSeNetV2Segmenter(SegmentationModel):
    """BiSeNet V2 (trained from scratch, as in the paper) with four booster heads.

    The upstream graph needs height and width divisible by 32 (fixed-factor
    upsampling inside the aggregation layer). The input is zero-padded on the
    bottom/right to the next multiple of 32 -- zero is the normalized mean
    colour -- and the logits are cropped back, the same policy the medical
    adapter uses. A 1024x1024 input is never padded.

    Args:
        num_classes: canonical class count.
        aux_loss_weight: weight of each booster loss (paper and upstream: 1.0).
    """

    BOOSTERS = (
        ("booster_s4", "aux2"),
        ("booster_s8", "aux3"),
        ("booster_s16", "aux4"),
        ("booster_s32", "aux5_4"),
    )
    _DIVISOR = 32

    def __init__(self, num_classes: int, *, aux_loss_weight: float = 1.0) -> None:
        super().__init__(num_classes)
        from ..medical.two_d_bisenet import BiSeNetV2

        self.aux_loss_weight = _positive_weight(aux_loss_weight, name="aux_loss_weight")
        self.model = BiSeNetV2(num_classes, aux_mode="train")
        record_preprocessing(self, where="BiSeNetV2", pretrained_cfg=None)

    def _classifiers(self) -> list[nn.Module]:
        heads = [self.model.head, *(getattr(self.model, attr) for _, attr in self.BOOSTERS)]
        classifiers = [head.conv_out[1] for head in heads]
        for classifier in classifiers:
            if not isinstance(classifier, nn.Conv2d) or classifier.out_channels != self.num_classes:
                raise ValueError("BiSeNetV2 SegmentHead no longer ends in its class projection")
        return classifiers

    def _run(self, pixel_values: Tensor, *, auxiliary: bool) -> SegmentationOutput:
        height, width = int(pixel_values.shape[-2]), int(pixel_values.shape[-1])
        pad_h = -height % self._DIVISOR
        pad_w = -width % self._DIVISOR
        padded = F.pad(pixel_values, (0, pad_w, 0, pad_h)) if pad_h or pad_w else pixel_values
        padded_size = tuple(padded.shape[-2:])

        def crop(raw: Tensor) -> Tensor:
            full = resize_logits(raw, padded_size)[..., :height, :width]
            return self._check_output(full, pixel_values)

        model = self.model
        feat_d = model.detail(padded)
        feat2, feat3, feat4, feat5_4, feat_s = model.segment(padded)
        logits = crop(model.head(model.bga(feat_d, feat_s)))
        if not auxiliary:
            return SegmentationOutput(dense_logits=logits)
        extra = tuple(
            AuxiliaryDenseOutput(name, crop(getattr(model, attr)(feature)), self.aux_loss_weight)
            for (name, attr), feature in zip(
                self.BOOSTERS, (feat2, feat3, feat4, feat5_4), strict=True
            )
        )
        return SegmentationOutput(dense_logits=logits, auxiliary_dense=extra)

    def forward(self, pixel_values: Tensor) -> Tensor:
        output = self._run(pixel_values, auxiliary=False)
        assert output.dense_logits is not None
        return output.dense_logits

    def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
        return self._run(pixel_values, auxiliary=self.training)

    def head_patterns(self) -> tuple[str, ...]:
        # Detail and semantic branches are the "backbone"; the aggregation
        # layer and every segment head form the decoder. The shipped recipe
        # uses head_lr_mult=1.0 because the whole network trains from scratch.
        return ("model.bga.", "model.head.", *(f"model.{attr}." for _, attr in self.BOOSTERS))

    def backbone_modules(self) -> list[nn.Module]:
        return [self.model.detail, self.model.segment]

    def reset_head(self) -> None:
        classifiers = self._classifiers()
        if sum(reinit_(classifier) for classifier in classifiers) != len(classifiers):
            raise ValueError("BiSeNetV2 reset_head did not re-initialise every classifier")
