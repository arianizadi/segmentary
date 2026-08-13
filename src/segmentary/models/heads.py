"""Object-Contextual Representations head (OCR).

Yuan, Chen & Wang, "Object-Contextual Representations for Semantic Segmentation",
ECCV 2020 (arXiv:1909.11065).

Implemented directly from the paper's three-step formulation because the model
stack needs an inspectable OCR contract without importing another segmentation
framework. timm supplies classification backbones, not this dense head.

The three steps of the paper, in order:

1. A coarse auxiliary classifier predicts *soft object regions* -- one spatial
   map per class.
2. Each region pools the pixel features it covers into a single *object region
   representation*.
3. Every pixel attends over those K representations; the resulting *object
   contextual representation* is concatenated with the original pixel feature and
   classified.

The auxiliary logits are returned as well, not discarded: they are what makes
step 1 learn anything, and the paper's training recipe supervises them.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import Tensor, nn


def conv_bn_relu(in_ch: int, out_ch: int, kernel_size: int = 1) -> nn.Sequential:
    """Conv-BN-ReLU with 'same' padding; bias is redundant in front of BN."""
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, kernel_size, padding=kernel_size // 2, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
    )


class SpatialGather(nn.Module):
    """Pool pixel features into one representation per soft object region.

    Args:
        scale: logit temperature before the spatial softmax. The paper uses 1.
    """

    def __init__(self, scale: float = 1.0) -> None:
        super().__init__()
        self.scale = scale

    def forward(self, feats: Tensor, probs: Tensor) -> Tensor:
        """(N, C, H, W) features and (N, K, H, W) coarse logits -> (N, K, C)."""
        n, k = probs.shape[0], probs.shape[1]
        c = feats.shape[1]
        # Softmax over pixels, not over classes: each region is a distribution
        # over the image, so the pooled vector is a weighted mean of features.
        weights = (self.scale * probs.reshape(n, k, -1)).softmax(dim=2)
        flat = feats.reshape(n, c, -1).permute(0, 2, 1)
        return torch.bmm(weights, flat)


class ObjectAttention(nn.Module):
    """Pixel-region relation, then the object contextual representation.

    Args:
        in_channels: pixel feature channels.
        key_channels: attention embedding width, typically ``in_channels // 2``.
    """

    def __init__(self, in_channels: int, key_channels: int) -> None:
        super().__init__()
        self.key_channels = key_channels
        self.f_pixel = nn.Sequential(
            conv_bn_relu(in_channels, key_channels), conv_bn_relu(key_channels, key_channels)
        )
        self.f_object = nn.Sequential(
            conv_bn_relu(in_channels, key_channels), conv_bn_relu(key_channels, key_channels)
        )
        self.f_down = conv_bn_relu(in_channels, key_channels)
        self.f_up = conv_bn_relu(key_channels, in_channels)

    def forward(self, feats: Tensor, region_feats: Tensor) -> Tensor:
        """(N, C, H, W) pixels and (N, K, C) regions -> (N, C, H, W) context."""
        n, _, h, w = feats.shape
        # Regions carry no spatial extent; the 1x1 convs above are reused on a
        # (N, C, K, 1) view so pixel and region branches share their form.
        regions = region_feats.permute(0, 2, 1).unsqueeze(3)

        query = self.f_pixel(feats).reshape(n, self.key_channels, -1).permute(0, 2, 1)
        key = self.f_object(regions).reshape(n, self.key_channels, -1)
        value = self.f_down(regions).reshape(n, self.key_channels, -1).permute(0, 2, 1)

        sim = torch.bmm(query, key) * (self.key_channels**-0.5)
        sim = sim.softmax(dim=-1)

        context = torch.bmm(sim, value).permute(0, 2, 1).reshape(n, self.key_channels, h, w)
        return self.f_up(context)


class OCRHead(nn.Module):
    """Coarse classifier + object-contextual refinement.

    Args:
        in_channels: channels of the concatenated backbone feature map.
        num_classes: canonical class count.
        ocr_channels: width the pixel features are projected to (paper: 512).
        key_channels: attention width (paper: 256).
        dropout: dropout before the final 1x1 classifier.
    """

    def __init__(
        self,
        in_channels: int,
        num_classes: int,
        ocr_channels: int = 512,
        key_channels: int = 256,
        dropout: float = 0.05,
    ) -> None:
        super().__init__()
        self.num_classes = num_classes

        # Named "coarse", not "aux_head": PEFT's modules_to_save matches with
        # key.endswith(), so a submodule whose name ends in the parent's name
        # ("head" -> "head.aux_head") gets its own wrapper nested inside the
        # parent's and is left frozen under LoRA.
        self.coarse = nn.Sequential(
            conv_bn_relu(in_channels, ocr_channels, kernel_size=3),
            nn.Conv2d(ocr_channels, num_classes, 1),
        )
        self.bottleneck = conv_bn_relu(in_channels, ocr_channels, kernel_size=3)
        self.gather = SpatialGather()
        self.attention = ObjectAttention(ocr_channels, key_channels)
        self.fuse = nn.Sequential(
            conv_bn_relu(2 * ocr_channels, ocr_channels), nn.Dropout2d(dropout)
        )
        self.classifier = nn.Conv2d(ocr_channels, num_classes, 1)

    def forward(self, feats: Tensor) -> tuple[Tensor, Tensor]:
        """Return ``(logits, aux_logits)``, both (N, num_classes, H, W) at feature stride."""
        aux = self.coarse(feats)
        pixels = self.bottleneck(feats)
        regions = self.gather(pixels, aux)
        context = self.attention(pixels, regions)
        fused = self.fuse(torch.cat([context, pixels], dim=1))
        return self.classifier(fused), aux


def concat_multi_scale(feats: list[Tensor]) -> Tensor:
    """Upsample a multi-resolution pyramid to its finest level and concatenate.

    HRNet's whole point is that its four branches stay parallel rather than being
    merged, so the head has to do the merging itself.
    """
    if not feats:
        raise ValueError("concat_multi_scale needs at least one feature map")
    size = feats[0].shape[-2:]
    resized = [feats[0]] + [
        F.interpolate(f, size=size, mode="bilinear", align_corners=False) for f in feats[1:]
    ]
    return torch.cat(resized, dim=1)
