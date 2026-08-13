# Native component smoke evidence

Compatibility evidence for the native component catalog — **not** model quality.
Every record here uses synthetic tensors and sets `quality_benchmark: false`.

> **What none of this proves:** no real dataset was used, and no mIoU, Dice,
> boundary score, convergence, speed, or ranking was measured. Parameter count is
> not memory, latency, or energy. Memory figures are allocator high-water marks
> for a tiny protocol, not production capacity planning.

## The acceptance protocol

Every GPU record below follows the same recipe, so the differences are only in
the model. Each one:

1. loads the exact pretrained weights, with no scratch fallback;
2. runs a forward pass at `64x96` **and** at odd `65x97`, to catch code that
   assumes even or square inputs;
3. runs four BF16 production objective / backward / AdamW steps;
4. requires a present, finite gradient on every trainable parameter tensor; and
5. requires at least one tracked classifier or head tensor to actually change.

Physical GPU 8 was isolated with `CUDA_VISIBLE_DEVICES=8`, so each process saw a
single NVIDIA L40S as `cuda:0`. All ran Python 3.11 and PyTorch `2.11.0+cu128`
with timm `1.0.28`. Each JSON retains the resolved config, normalization,
feature contracts, optimizer groups, per-step losses, environment, and clean git
provenance.

## GPU acceptance records

| Record | Model | Params | Peak reserved | Runtime |
|---|---|---:|---:|---:|
| [Full native catalog](native-catalog-gpu8-2026-08-12.json) | all 10 shipped `arch: native` recipes | see table below | ≤1,168 MiB | 274.6 s |
| [ChannelMapper/DPT](native-convnext-tiny-channelmapper-dpt-gpu8-2026-08-12.json) | ConvNeXt-Tiny / ChannelMapper / DPT | 38,229,875 | 732 MiB | 24.9 s |
| [Native binary](native-binary-gpu8-2026-08-12.json) | ResNet-18 / FPN / FCN + aux | 11,286,098 | 242 MiB | — |
| [ResNet-50/FPN/OCR](native-resnet50-fpn-ocr-gpu8-2026-08-12.json) | ResNet-50 / FPN / OCR | 32,644,710 | 682 MiB | 59.1 s |
| [Binary OCR](native-binary-ocr-gpu8-2026-08-13.json) | ResNet-50 / FPN / OCR, one logit | 32,626,242 | 682 MiB | 59.6 s |
| [EoMT-Large query](eomt-large-query-gpu8-2026-08-13.json) | EoMT-Large, Hungarian objective | — | — | — |

Per-recipe figures from the full catalog run:

| recipe | parameters | peak reserved |
|---|---:|---:|
| `native_convnext_tiny_uper` | 36,849,011 | 684 MiB |
| `native_efficientnet_b0_deeplabv3plus` | 5,721,359 | 160 MiB |
| `native_mobilenetv3_large_deeplabv3plus` | 8,067,523 | 190 MiB |
| `native_mobilenetv3_large_lraspp` | 3,221,022 | 104 MiB |
| `native_resnet101_uper` | 61,322,579 | 1,168 MiB |
| `native_resnet18_fpn_fcn` | 12,630,995 | 274 MiB |
| `native_resnet18_fpn_segformer_aux` | 12,100,134 | 274 MiB |
| `native_resnet50_aspp` | 39,047,763 | 732 MiB |
| `native_resnet50_deeplabv3plus` | 40,351,411 | 754 MiB |
| `native_resnet50_psp` | 37,149,011 | 704 MiB |

### Record-specific notes

- **Full catalog** (commit `ebfbe49`) discovered the ten recipes dynamically
  rather than from a hard-coded list.
- **Native binary** (commit `f1f81eb`) used a `0 background` / `1 foreground`
  taxonomy; both the primary and the positively weighted auxiliary head emitted
  exactly one raw foreground logit. The same tree also passed the real
  generated-folder CPU train/checkpoint/eval test and the overfit CLI test.
- **Binary OCR** (commit `5e79910`) deliberately used arbitrary class names
  (`background`, `tumor`) to prove that canonical **ID 1**, not a class name,
  defines the positive class. It records the centered `[-z/2,+z/2]` proxy
  convention.
- **OCR records** additionally require named `aux/ocr_coarse/loss` and
  `aux/ocr_coarse/weighted_loss` components on every step, and updates to both
  the coarse and refined classifiers.
- **EoMT-Large** (commit `e69fb4e`) loaded
  `tue-mps/coco_panoptic_eomt_large_640` at revision `dcd130b` from a complete
  local cache with network access disabled, and trained through the
  [Hungarian query objective](../../catalog/components/query-objectives/README.md).
  Its 19-class predictor was necessarily reinitialized from the checkpoint's
  133-class COCO predictor. EoMT processes its fixed `640x640` grid internally,
  so the two input shapes exercise Segmentary's resize-and-restore wrapper
  rather than native arbitrary-grid support.

## Backbone feature probes

On 2026-08-12, on CPU with scratch initialization and one random `1x3x128x128`
input, timm's public `features_only` path returned these NCHW feature tuples:

| backbone | feature channels | reductions | output sizes | extractor params |
|---|---|---|---|---:|
| `resnet18` | 64/64/128/256/512 | 2/4/8/16/32 | 64/32/16/8/4 square | 11,176,512 |
| `resnet50` | 64/256/512/1024/2048 | 2/4/8/16/32 | 64/32/16/8/4 square | 23,508,032 |
| `resnet101` | 64/256/512/1024/2048 | 2/4/8/16/32 | 64/32/16/8/4 square | 42,500,160 |
| `convnext_tiny` | 96/192/384/768 | 4/8/16/32 | 32/16/8/4 square | 27,818,592 |
| `efficientnet_b0` | 16/24/40/112/320 | 2/4/8/16/32 | 64/32/16/8/4 square | 3,595,388 |
| `mobilenetv3_large_100` | 16/24/40/112/960 | 2/4/8/16/32 | 64/32/16/8/4 square | 2,971,952 |

## Pretrained weight admission

A separate CPU pass loaded the exact tagged weights (no scratch fallback) at
both `64x96` and odd `65x97`. All six reported Apache-2.0 model-card metadata
and ImageNet RGB normalization (mean `[0.485, 0.456, 0.406]`, std
`[0.229, 0.224, 0.225]`).

| exact timm name | indices | source |
|---|---|---|
| `resnet18.a1_in1k` | 1/2/3/4 | [`timm/resnet18.a1_in1k`](https://huggingface.co/timm/resnet18.a1_in1k), A1/ImageNet-1k |
| `resnet50.a1_in1k` | 1/2/3/4 | [`timm/resnet50.a1_in1k`](https://huggingface.co/timm/resnet50.a1_in1k), A1/ImageNet-1k |
| `resnet101.a1_in1k` | 1/2/3/4 | [`timm/resnet101.a1_in1k`](https://huggingface.co/timm/resnet101.a1_in1k), A1/ImageNet-1k |
| `efficientnet_b0.ra_in1k` | 1/2/3/4 | [`timm/efficientnet_b0.ra_in1k`](https://huggingface.co/timm/efficientnet_b0.ra_in1k), RandAugment/ImageNet-1k |
| `mobilenetv3_large_100.ra_in1k` | 1/2/3/4 | [`timm/mobilenetv3_large_100.ra_in1k`](https://huggingface.co/timm/mobilenetv3_large_100.ra_in1k), RandAugment/ImageNet-1k |
| `convnext_tiny.fb_in22k_ft_in1k` | 0/1/2/3 | [`timm/convnext_tiny.fb_in22k_ft_in1k`](https://huggingface.co/timm/convnext_tiny.fb_in22k_ft_in1k), FB IN-22k → IN-1k |

The five-level families select original indices `[1, 2, 3, 4]` and ConvNeXt
selects `[0, 1, 2, 3]`, so each exposes a 4/8/16/32 pyramid. The exact `url`
values `timm.get_pretrained_cfg(name)` returned:

- ResNet-18 — [`resnet18_a1_0-d63eafa0.pth`](https://github.com/huggingface/pytorch-image-models/releases/download/v0.1-rsb-weights/resnet18_a1_0-d63eafa0.pth)
- ResNet-50 — [`resnet50_a1_0-14fe96d1.pth`](https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-rsb-weights/resnet50_a1_0-14fe96d1.pth)
- ResNet-101 — [`resnet101_a1_0-cdcb52a9.pth`](https://github.com/huggingface/pytorch-image-models/releases/download/v0.1-rsb-weights/resnet101_a1_0-cdcb52a9.pth)
- EfficientNet-B0 — [`efficientnet_b0_ra-3dd342df.pth`](https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-weights/efficientnet_b0_ra-3dd342df.pth)
- MobileNetV3-Large — [`mobilenetv3_large_100_ra-f55367f5.pth`](https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-weights/mobilenetv3_large_100_ra-f55367f5.pth)
- ConvNeXt-Tiny — [`convnext_tiny_22k_1k_224.pth`](https://dl.fbaipublicfiles.com/convnext/convnext_tiny_22k_1k_224.pth)

Those hexadecimal filenames identify timm release artifacts; they are not a
locally recomputed checksum. This admission proves the pinned library resolved
and loaded the requested sources — not that an upstream host is immutable.
Weight provenance still belongs in the run record, and an upstream weight or
license change needs re-admission.

## Unit-level contracts

The native component suite verifies feature metadata and runtime shape
rejection; identity/ChannelMapper/FPN neck behaviour including extra levels and
input independence; output and gradient contracts for FCN, SegFormer, PSP, ASPP,
DeepLabV3+, LR-ASPP, UPer, DPT and OCR; DPT four-level fusion with odd sizes and
fail-closed width validation; OCR region gathering, attention scaling and
two-classifier reset; disjoint backbone/neck/head/auxiliary parameter ownership;
and real scratch forward/backward passes with four CPU AdamW steps plus a Gloo
DDP step with no unused parameters.

## Coverage limits

The historical catalog JSON covers only the ten recipes present at its commit.
`native_convnext_tiny_channelmapper_dpt` and `native_resnet50_fpn_ocr` are
covered by their own records, not retroactively. The binary records cover one
task composition each, not every backbone/head/loss/threshold combination. None
of the dense-native records extends to Hugging Face, SMP, or query models; the
EoMT record covers one query-model composition only.

Before publishing a native recipe result, record the taxonomy, dataset split,
crop, schedule, seed set, checkpoint/EMA/TTA choice, Segmentary commit,
dependency versions, and evaluator settings. See
[interpreting results](../../tutorials/interpreting-results.md).
