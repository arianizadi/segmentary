"""ESPNet (v1) as a Segmentary built-in.

Mehta et al., "ESPNet: Efficient Spatial Pyramid of Dilated Convolutions for
Semantic Segmentation", ECCV 2018.  The layers are adapted from the authors'
reference implementation,
https://github.com/sacmehta/ESPNet/blob/afe71c38edaee3514ca44e0adcafdf36109bf437/train/Model.py
(MIT License, reproduced below), using the full ``ESPNet`` decoder with the
reference defaults p=2 and q=8 (``train/main.py``).

Local changes, all of which leave the computation unchanged for an input whose
sides are divisible by 8:

* Every decoder layer, including the encoder's stride-8 class projection
  (upstream ``ESPNet_Encoder.classifier``), lives in ``decoder``; the upstream
  ``self.modules`` list aliasing is replaced by ordinary attributes.
* The three stride-2 transposed convolutions can overshoot an odd feature size
  by one row/column; their output is cropped to the skip connection it is
  concatenated with, and the final logits to the input.
* The decoder width is ``max(num_classes, 5)``. Upstream it is exactly
  ``num_classes``; the floor exists only because an ESP module splits its
  width into five dilated branches and cannot be built narrower than five.
  The last transposed convolution always projects to ``num_classes``.
* The upstream recipe initialises the full network from an ESPNet-C encoder
  trained on Cityscapes; that checkpoint is not an ImageNet backbone and is
  not available from a pinned public weight registry, so Segmentary trains the
  whole network from scratch (PyTorch default initialisation, as upstream).

MIT License

Copyright (c) 2018 Sachin Mehta

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

import torch
from torch import Tensor, nn

from .preprocessing import record_preprocessing
from .wrappers import SegmentationModel

ESP_BRANCHES = 5


class CBR(nn.Module):
    """Convolution, BatchNorm and PReLU."""

    def __init__(self, n_in: int, n_out: int, k_size: int, stride: int = 1) -> None:
        super().__init__()
        padding = (k_size - 1) // 2
        self.conv = nn.Conv2d(n_in, n_out, k_size, stride=stride, padding=padding, bias=False)
        self.bn = nn.BatchNorm2d(n_out, eps=1e-03)
        self.act = nn.PReLU(n_out)

    def forward(self, x: Tensor) -> Tensor:
        return self.act(self.bn(self.conv(x)))


class BR(nn.Module):
    """BatchNorm and PReLU."""

    def __init__(self, n_out: int) -> None:
        super().__init__()
        self.bn = nn.BatchNorm2d(n_out, eps=1e-03)
        self.act = nn.PReLU(n_out)

    def forward(self, x: Tensor) -> Tensor:
        return self.act(self.bn(x))


class C(nn.Module):
    """Bias-free convolution."""

    def __init__(self, n_in: int, n_out: int, k_size: int, stride: int = 1) -> None:
        super().__init__()
        padding = (k_size - 1) // 2
        self.conv = nn.Conv2d(n_in, n_out, k_size, stride=stride, padding=padding, bias=False)

    def forward(self, x: Tensor) -> Tensor:
        return self.conv(x)


class CDilated(nn.Module):
    """Bias-free dilated 3x3 convolution."""

    def __init__(self, n_in: int, n_out: int, k_size: int, stride: int = 1, d: int = 1) -> None:
        super().__init__()
        padding = ((k_size - 1) // 2) * d
        self.conv = nn.Conv2d(
            n_in, n_out, k_size, stride=stride, padding=padding, bias=False, dilation=d
        )

    def forward(self, x: Tensor) -> Tensor:
        return self.conv(x)


def _branch_widths(n_out: int) -> tuple[int, int]:
    n = n_out // ESP_BRANCHES
    if n < 1:
        raise ValueError(f"an ESP module needs at least {ESP_BRANCHES} output channels")
    return n, n_out - (ESP_BRANCHES - 1) * n


def _hierarchical_merge(branches: tuple[Tensor, ...]) -> Tensor:
    # Hierarchical feature fusion: add the dilated outputs cumulatively before
    # concatenation to remove gridding artifacts.
    d1, d2, d4, d8, d16 = branches
    add1 = d2
    add2 = add1 + d4
    add3 = add2 + d8
    add4 = add3 + d16
    return torch.cat([d1, add1, add2, add3, add4], 1)


class DownSamplerB(nn.Module):
    """Strided ESP module (upstream ``DownSamplerB``)."""

    def __init__(self, n_in: int, n_out: int) -> None:
        super().__init__()
        n, n1 = _branch_widths(n_out)
        self.c1 = C(n_in, n, 3, 2)
        self.d1 = CDilated(n, n1, 3, 1, 1)
        self.d2 = CDilated(n, n, 3, 1, 2)
        self.d4 = CDilated(n, n, 3, 1, 4)
        self.d8 = CDilated(n, n, 3, 1, 8)
        self.d16 = CDilated(n, n, 3, 1, 16)
        self.bn = nn.BatchNorm2d(n_out, eps=1e-3)
        self.act = nn.PReLU(n_out)

    def forward(self, x: Tensor) -> Tensor:
        reduced = self.c1(x)
        combine = _hierarchical_merge(
            tuple(branch(reduced) for branch in (self.d1, self.d2, self.d4, self.d8, self.d16))
        )
        return self.act(self.bn(combine))


class DilatedParllelResidualBlockB(nn.Module):
    """The ESP module: reduce, split, transform, merge (upstream spelling kept)."""

    def __init__(self, n_in: int, n_out: int, add: bool = True) -> None:
        super().__init__()
        n, n1 = _branch_widths(n_out)
        self.c1 = C(n_in, n, 1, 1)
        self.d1 = CDilated(n, n1, 3, 1, 1)
        self.d2 = CDilated(n, n, 3, 1, 2)
        self.d4 = CDilated(n, n, 3, 1, 4)
        self.d8 = CDilated(n, n, 3, 1, 8)
        self.d16 = CDilated(n, n, 3, 1, 16)
        self.bn = BR(n_out)
        self.add = add

    def forward(self, x: Tensor) -> Tensor:
        reduced = self.c1(x)
        combine = _hierarchical_merge(
            tuple(branch(reduced) for branch in (self.d1, self.d2, self.d4, self.d8, self.d16))
        )
        if self.add:
            combine = x + combine
        return self.bn(combine)


class InputProjectionA(nn.Module):
    """Average-pool the RGB input down to a feature map's resolution."""

    def __init__(self, sampling_times: int) -> None:
        super().__init__()
        self.pool = nn.ModuleList(
            nn.AvgPool2d(3, stride=2, padding=1) for _ in range(sampling_times)
        )

    def forward(self, x: Tensor) -> Tensor:
        for pool in self.pool:
            x = pool(x)
        return x


class ESPNetEncoder(nn.Module):
    """ESPNet-C without its class projection; returns the three decoder taps.

    Returns:
        ``(output0_cat, output1_cat, output2_cat)`` with 19, 131 and 256
        channels at strides 2, 4 and 8.
    """

    def __init__(self, p: int = 2, q: int = 8) -> None:
        super().__init__()
        self.level1 = CBR(3, 16, 3, 2)
        self.sample1 = InputProjectionA(1)
        self.sample2 = InputProjectionA(2)
        self.b1 = BR(16 + 3)
        self.level2_0 = DownSamplerB(16 + 3, 64)
        self.level2 = nn.ModuleList(DilatedParllelResidualBlockB(64, 64) for _ in range(p))
        self.b2 = BR(128 + 3)
        self.level3_0 = DownSamplerB(128 + 3, 128)
        self.level3 = nn.ModuleList(DilatedParllelResidualBlockB(128, 128) for _ in range(q))
        self.b3 = BR(256)

    def forward(self, x: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        output0 = self.level1(x)
        inp1 = self.sample1(x)
        inp2 = self.sample2(x)
        output0_cat = self.b1(torch.cat([output0, inp1], 1))
        output1_0 = self.level2_0(output0_cat)
        output1 = output1_0
        for layer in self.level2:
            output1 = layer(output1)
        output1_cat = self.b2(torch.cat([output1, output1_0, inp2], 1))
        output2_0 = self.level3_0(output1_cat)
        output2 = output2_0
        for layer in self.level3:
            output2 = layer(output2)
        output2_cat = self.b3(torch.cat([output2_0, output2], 1))
        return output0_cat, output1_cat, output2_cat


def _crop_to(x: Tensor, reference: Tensor) -> Tensor:
    return x[..., : reference.shape[-2], : reference.shape[-1]]


class ESPNetDecoder(nn.Module):
    """The full ESPNet decoder. Every layer here operates in class space."""

    def __init__(self, num_classes: int) -> None:
        super().__init__()
        width = max(num_classes, ESP_BRANCHES)
        self.width = width
        self.classifier_l3 = C(256, width, 1, 1)  # upstream ESPNet_Encoder.classifier
        self.level3_C = C(128 + 3, width, 1, 1)
        self.br = nn.BatchNorm2d(width, eps=1e-03)
        self.conv = CBR(19 + width, width, 3, 1)
        self.up_l3 = nn.ConvTranspose2d(width, width, 2, stride=2, padding=0, bias=False)
        self.combine_l2_l3 = nn.Sequential(
            BR(2 * width), DilatedParllelResidualBlockB(2 * width, width, add=False)
        )
        self.up_l2 = nn.Sequential(
            nn.ConvTranspose2d(width, width, 2, stride=2, padding=0, bias=False), BR(width)
        )
        self.classifier = nn.ConvTranspose2d(width, num_classes, 2, stride=2, padding=0, bias=False)

    def forward(self, output0_cat: Tensor, output1_cat: Tensor, output2_cat: Tensor) -> Tensor:
        output1_c = self.level3_C(output1_cat)
        output2_c = _crop_to(self.up_l3(self.br(self.classifier_l3(output2_cat))), output1_c)
        comb_l2_l3 = self.up_l2(self.combine_l2_l3(torch.cat([output1_c, output2_c], 1)))
        concat_features = self.conv(torch.cat([_crop_to(comb_l2_l3, output0_cat), output0_cat], 1))
        return self.classifier(concat_features)


class ESPNet(SegmentationModel):
    """ESPNet with the full decoder (paper Fig. 4d), trained from scratch.

    There are no auxiliary heads: the paper trains ESPNet with one
    cross-entropy loss, so ``forward_output`` is the inherited single-tensor
    contract in both modes.

    Args:
        num_classes: canonical class count.
        p: ESP modules at stride 4 (reference default 2).
        q: ESP modules at stride 8 (reference default 8).
    """

    def __init__(self, num_classes: int, *, p: int = 2, q: int = 8) -> None:
        super().__init__(num_classes)
        if isinstance(p, bool) or isinstance(q, bool) or p < 1 or q < 1:
            raise ValueError("ESPNet depth multipliers p and q must be positive integers")
        self.encoder = ESPNetEncoder(p=p, q=q)
        self.decoder = ESPNetDecoder(num_classes)
        record_preprocessing(self, where="ESPNet", pretrained_cfg=None)

    def forward(self, pixel_values: Tensor) -> Tensor:
        logits = self.decoder(*self.encoder(pixel_values))
        return self._check_output(_crop_to(logits, pixel_values), pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return ("decoder.",)

    def backbone_modules(self) -> list[nn.Module]:
        return [self.encoder]

    def reset_head(self) -> None:
        # The whole decoder is class-shaped (its width is the class count), so
        # a stage hand-off to a different label space must rebuild all of it;
        # only the encoder carries over. PyTorch default init, as upstream.
        hits = 0
        for module in self.decoder.modules():
            reset = getattr(module, "reset_parameters", None)
            if module is not self.decoder and callable(reset):
                reset()
                hits += isinstance(module, (nn.Conv2d, nn.ConvTranspose2d))
        if hits == 0:
            raise ValueError("ESPNet reset_head re-initialised no decoder convolution")

    def reset_head_state_keys(self) -> tuple[str, ...]:
        # BatchNorm/PReLU state is class-count shaped but resets to the same
        # values a fresh model already holds; declare it so curriculum
        # hand-off keeps the target shapes instead of reporting a mismatch.
        # ``num_batches_tracked`` is a shape-free counter that BatchNorm's
        # loader back-fills silently, so it is carried over, not declared.
        return tuple(
            f"decoder.{name}"
            for name in self.decoder.state_dict()
            if not name.endswith("num_batches_tracked")
        )
