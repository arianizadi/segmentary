# Segmentary-native component smoke evidence

This ledger records compatibility evidence for the first native component
catalog. It is deliberately separate from model-quality benchmarks.

## Scratch feature probes

On 2026-08-12, the pinned HDRFS environment used Python 3.11, PyTorch
`2.11.0+cu128`, timm `1.0.28`, CPU execution, scratch initialization, and one
random `1x3x128x128` input. timm's public `features_only` path constructed and
returned the following NCHW feature tuples:

| backbone | default feature channels | reductions | observed output spatial sizes | extractor parameters |
|---|---|---|---|---:|
| `resnet18` | 64/64/128/256/512 | 2/4/8/16/32 | 64/32/16/8/4 square | 11,176,512 |
| `resnet50` | 64/256/512/1024/2048 | 2/4/8/16/32 | 64/32/16/8/4 square | 23,508,032 |
| `resnet101` | 64/256/512/1024/2048 | 2/4/8/16/32 | 64/32/16/8/4 square | 42,500,160 |
| `convnext_tiny` | 96/192/384/768 | 4/8/16/32 | 32/16/8/4 square | 27,818,592 |
| `efficientnet_b0` | 16/24/40/112/320 | 2/4/8/16/32 | 64/32/16/8/4 square | 3,595,388 |
| `mobilenetv3_large_100` | 16/24/40/112/960 | 2/4/8/16/32 | 64/32/16/8/4 square | 2,971,952 |

## Exact pretrained feature admission

A separate CPU admission loaded the requested pretrained weights without a
scratch fallback and checked both `64x96` and odd `65x97` inputs. The pinned
timm configuration supplied RGB/ImageNet normalization. The exact names were:

| exact timm name | selected indices | source recorded by timm 1.0.28 |
|---|---|---|
| `resnet18.a1_in1k` | 1/2/3/4 | [`timm/resnet18.a1_in1k`](https://huggingface.co/timm/resnet18.a1_in1k), A1/ImageNet-1k |
| `resnet50.a1_in1k` | 1/2/3/4 | [`timm/resnet50.a1_in1k`](https://huggingface.co/timm/resnet50.a1_in1k), A1/ImageNet-1k |
| `resnet101.a1_in1k` | 1/2/3/4 | [`timm/resnet101.a1_in1k`](https://huggingface.co/timm/resnet101.a1_in1k), A1/ImageNet-1k |
| `efficientnet_b0.ra_in1k` | 1/2/3/4 | [`timm/efficientnet_b0.ra_in1k`](https://huggingface.co/timm/efficientnet_b0.ra_in1k), RandAugment/ImageNet-1k |
| `mobilenetv3_large_100.ra_in1k` | 1/2/3/4 | [`timm/mobilenetv3_large_100.ra_in1k`](https://huggingface.co/timm/mobilenetv3_large_100.ra_in1k), RandAugment/ImageNet-1k |
| `convnext_tiny.fb_in22k_ft_in1k` | 0/1/2/3 | [`timm/convnext_tiny.fb_in22k_ft_in1k`](https://huggingface.co/timm/convnext_tiny.fb_in22k_ft_in1k), FB ImageNet-22k then ImageNet-1k |

For all six, timm reported Apache-2.0 model-card metadata, ImageNet RGB mean
`[0.485, 0.456, 0.406]`, and standard deviation `[0.229, 0.224, 0.225]`. The
repository recipes use these exact tagged names. The five-level families
select original indices `[1, 2, 3, 4]`; ConvNeXt selects `[0, 1, 2, 3]`. Each
therefore exposes a 4/8/16/32 pyramid. Weight provenance still belongs in the
resolved run record, and an upstream weight/license change needs re-admission.

The exact `url` values returned by `timm.get_pretrained_cfg(name)` were:

- ResNet-18: [`resnet18_a1_0-d63eafa0.pth`](https://github.com/huggingface/pytorch-image-models/releases/download/v0.1-rsb-weights/resnet18_a1_0-d63eafa0.pth)
- ResNet-50: [`resnet50_a1_0-14fe96d1.pth`](https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-rsb-weights/resnet50_a1_0-14fe96d1.pth)
- ResNet-101: [`resnet101_a1_0-cdcb52a9.pth`](https://github.com/huggingface/pytorch-image-models/releases/download/v0.1-rsb-weights/resnet101_a1_0-cdcb52a9.pth)
- EfficientNet-B0: [`efficientnet_b0_ra-3dd342df.pth`](https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-weights/efficientnet_b0_ra-3dd342df.pth)
- MobileNetV3-Large: [`mobilenetv3_large_100_ra-f55367f5.pth`](https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-weights/mobilenetv3_large_100_ra-f55367f5.pth)
- ConvNeXt-Tiny: [`convnext_tiny_22k_1k_224.pth`](https://dl.fbaipublicfiles.com/convnext/convnext_tiny_22k_1k_224.pth)

The embedded hexadecimal filenames identify the timm release artifacts where
provided; they are not a locally recomputed checksum. The admission proved that
the pinned library resolved and loaded the requested sources, not that an
upstream host is immutable forever.

## Native component contracts

The native component unit suite verifies:

- feature metadata and runtime shape rejection;
- identity, ChannelMapper, and FPN neck forward/backward behavior, including
  ChannelMapper extra levels and independence between mapped inputs;
- FCN, SegFormer, PSP, ASPP, DeepLabV3+, LR-ASPP, UPer, DPT, and OCR
  output/gradient contracts;
- DPT four-level progressive fusion, odd output sizes, every native
  normalization, all-input gradients, classifier-only reset, and fail-closed
  width/pyramid validation;
- a real scratch ConvNeXt-Tiny + ChannelMapper + DPT forward/backward pass;
- four CPU AdamW steps through a small ChannelMapper/DPT stack;
- OCR refined/coarse output shapes, region gathering, every normalization,
  attention scaling, fail-closed settings, and two-classifier reset;
- positive weighted coarse supervision through the production dense objective;
- a real scratch ResNet-50 + FPN + OCR forward/backward pass;
- four CPU AdamW steps through OCR and a Gloo DDP step with no unused tensors;
- LR-ASPP batch-one BatchNorm safety and two-classifier reset behavior;
- a real scratch ResNet-18 + FPN + SegFormer + FCN auxiliary stack;
- four CPU AdamW optimizer steps with finite loss and changed parameters;
- a two-process CPU Gloo DDP step without unused parameters;
- disjoint backbone/neck/main-head/auxiliary parameter ownership.

## Full native-recipe GPU acceptance

The retained [2026-08-12 machine record](native-catalog-gpu8-2026-08-12.json)
was generated from clean Segmentary commit `ebfbe49a4c33807f50af920c9b8dd128ed8a24a0`
in the pinned Python 3.11 / PyTorch `2.11.0+cu128` HDRFS environment. The test
dynamically discovered all ten shipped `arch: native` recipes, loaded their
requested pretrained timm weights without a scratch fallback, and ran them
sequentially on physical GPU 8 (the process saw only `cuda:0`). Each recipe
completed both `64x96` and odd `65x97` forwards plus four BF16 production
dense-objective/backward/AdamW steps at batch one. Every trainable parameter
tensor received a present finite gradient, and at least one tracked classifier
or head tensor changed. The whole sequential run took 274.6 seconds.

| recipe | parameters | peak reserved CUDA memory |
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

These memory numbers are per-recipe allocator high-water marks for this tiny
compatibility protocol, not production crop/batch requirements or a speed
ranking. The JSON retains exact configs, normalization, component feature
specs, optimizer groups, per-step losses, gradient checks, environment, and
provenance. It explicitly records `synthetic_data: true` and
`quality_benchmark: false`.

## ChannelMapper/DPT exact GPU8 acceptance

The separate retained
[ChannelMapper/DPT machine record](native-convnext-tiny-channelmapper-dpt-gpu8-2026-08-12.json)
was generated from clean commit `23eebad016e977bfad5793d52e0516f7b136b09b`.
It loaded the exact pretrained `convnext_tiny.fb_in22k_ft_in1k` weights and
constructed the 38,229,875-parameter native ConvNeXt-Tiny / ChannelMapper / DPT
recipe. With physical GPU 8 isolated as `CUDA_VISIBLE_DEVICES=8`, the process
saw one NVIDIA L40S as `cuda:0` and completed:

- full-resolution forwards at `64x96` and odd `65x97`;
- four BF16 production dense-objective/backward/AdamW steps at batch one;
- present finite gradients for all 243 trainable parameter tensors on every
  step; and
- updates to both tracked DPT classifier tensors.

The run took 24.9 seconds and reported a 732 MiB allocator high-water mark for
this tiny protocol. It used Python 3.11.15, PyTorch `2.11.0+cu128`, and timm
`1.0.28`; the JSON contains the complete component feature contracts,
optimizer groups, normalization, per-step values, environment, and clean git
provenance. It explicitly records synthetic data and `quality_benchmark:
false`, so the timing and memory value are evidence details, not a deployment
or performance ranking.

## Native binary exact GPU8 acceptance

The retained
[native-binary machine record](native-binary-gpu8-2026-08-12.json) was generated
from clean commit `f1f81eb5b6223a899b7bf26cc057cff800a99a14` after rebasing
onto the ChannelMapper/DPT integration. It loaded the exact pretrained
`resnet18.a1_in1k` backbone and composed an FPN, an FCN primary head, and a
positively weighted FCN auxiliary head under the native binary contract. The
canonical taxonomy still contained `0 background` and `1 foreground`; both
heads emitted exactly one raw foreground logit.

With physical GPU 8 isolated as `CUDA_VISIBLE_DEVICES=8`, the process saw one
NVIDIA L40S as `cuda:0` and completed full-resolution forwards at `64x96` and
odd `65x97`, followed by four BF16 production dense-objective/backward/AdamW
steps at batch two. All 90 trainable parameter tensors had present finite
gradients on every step, and both primary classifier tensors plus both
auxiliary classifier tensors changed. The 11,286,098-parameter model reported a
242 MiB allocator high-water mark for this tiny protocol.

The same rebased source tree separately passed the real generated-folder CPU
train/checkpoint/standalone-eval test and the one-step overfit CLI test. The JSON
probe itself uses synthetic tensors and labels, explicitly records
`quality_benchmark: false`, and therefore provides no mIoU, calibration,
convergence, speed, or production-memory evidence.

## ResNet-50/FPN/OCR exact GPU8 acceptance

The separate retained
[ResNet-50/FPN/OCR machine record](native-resnet50-fpn-ocr-gpu8-2026-08-12.json)
was generated from clean commit `ae6febdb78c334f4c3c9ee30d6edda888c0d4c92`.
It loaded the exact pretrained `resnet50.a1_in1k` weights and constructed the
32,644,710-parameter native ResNet-50 / FPN / OCR recipe. With physical GPU 8
isolated as `CUDA_VISIBLE_DEVICES=8`, the process saw one NVIDIA L40S as
`cuda:0` and completed:

- full-resolution forwards at `64x96` and odd `65x97`;
- four BF16 production dense-objective/backward/AdamW steps at batch one;
- named `aux/ocr_coarse/loss` and `aux/ocr_coarse/weighted_loss` components on
  every step;
- present finite gradients for all 201 trainable parameter tensors on every
  step; and
- updates to the weight and bias of both the coarse and refined classifiers.

The run took 59.1 seconds and reported a 715,128,832-byte allocator high-water
mark for this tiny protocol. The record retains the resolved pretrained source,
normalization, feature contracts, optimizer groups, step losses, environment,
and clean git provenance. It explicitly records `synthetic_data: true` and
`quality_benchmark: false`; the timing and memory values are evidence details,
not speed, capacity-planning, convergence, or quality measurements.

## Binary ResNet-50/FPN/OCR exact GPU8 acceptance

The direct retained
[binary-OCR machine record](native-binary-ocr-gpu8-2026-08-13.json) was generated
from exact clean integration commit
`5e799107e7572574b51897957051a950ab53e28f`. It loaded the exact pretrained
`resnet50.a1_in1k` weights and composed the 32,626,242-parameter ResNet-50 / FPN
/ OCR model with public one-logit refined and `ocr_coarse` outputs. The binary
taxonomy used arbitrary valid names (`background`, `tumor`) to verify that
canonical ID 1—not a hard-coded class name—defines the positive class.

With physical GPU 8 isolated as `CUDA_VISIBLE_DEVICES=8`, the process saw one
NVIDIA L40S as `cuda:0` and completed:

- full-resolution one-logit forwards at `64x96` and odd `65x97`;
- four BF16 production BCE/backward/AdamW steps at batch one;
- named primary BCE, `aux/ocr_coarse/loss`, and positively weighted
  `aux/ocr_coarse/weighted_loss` components on every step;
- present finite gradients for all 201 trainable parameter tensors on every
  step; and
- finite nonzero final gradients plus parameter updates for OCR's pixel-query
  weight, region-key weight, and weight/bias of both coarse and refined
  classifiers.

The run took 59.6 seconds and reported a 715,128,832-byte allocator high-water
mark for this tiny protocol. The record contains the centered internal
`[-z/2,+z/2]` negative/positive proxy convention, resolved typed config,
normalization, feature contracts, optimizer groups, per-step values,
environment, GPU isolation, and clean provenance. It explicitly records
synthetic data and `quality_benchmark: false`; it is direct compatibility and
gradient evidence only, not mIoU, calibration, convergence, speed, deployment,
or production-memory evidence.

## EoMT-Large native-query exact GPU8 acceptance

The retained
[EoMT-Large query machine record](eomt-large-query-gpu8-2026-08-13.json) was
generated by the public `segmentary-models probe` from exact clean source commit
`e69fb4eb569d79f837f8f1678d1a31b6a85fddf6`. It loaded
`tue-mps/coco_panoptic_eomt_large_640` revision
`dcd130bed9b1ebda7041fd660fddb16f905b9c3b` from the complete local cache with
network access disabled. The 19-class predictor was necessarily reinitialized
from the checkpoint's 133-class COCO predictor; the pretrained query, mask,
decoder, and backbone tensors loaded without a scratch fallback.

With physical GPU 8 isolated as `CUDA_VISIBLE_DEVICES=8`, the process saw one
NVIDIA L40S as `cuda:0` and completed two distinct non-square wrapper inputs
(`64x96` and odd `65x97`) plus two BF16 production
[Hungarian query-objective](../../catalog/components/query-objectives/README.md)
backward/AdamW steps. All 458 trainable parameter tensors had present finite
gradients on both steps, and all 19 tracked learned-query, upscale, mask-head,
and class-predictor tensors changed. GPU 8 was idle before the run and returned
to zero memory use with no compute process afterward.

This is synthetic compatibility evidence only. EoMT internally processed its
fixed `640x640` checkpoint grid, so the two shapes prove Segmentary's
resize-and-restore wrapper rather than native arbitrary-grid EoMT support. The
record explicitly sets `synthetic_data: true` and `quality_benchmark: false`;
it provides no mIoU, learning, convergence, speed, calibration, or
production-memory evidence.

## What this does not prove

- No real dataset was used.
- No mIoU, Dice, boundary score, convergence, or ranking was measured.
- Parameter count is not GPU memory, latency, throughput, or energy.
- Pretrained feature admission is not a full decoder optimizer smoke.
- The historical catalog JSON proves only the ten native recipes present at its
  commit. The later `native_convnext_tiny_channelmapper_dpt` recipe is covered
  by its separate acceptance above, and `native_resnet50_fpn_ocr` by the OCR
  acceptance, not retroactively by the old catalog run.
  The binary record covers one checked task composition, not every native
  backbone/head/loss/threshold combination. The binary-OCR record directly
  covers the one-logit OCR extension but not a real-data training outcome. None
  of these dense-native records extends to Hugging Face, SMP, query-model, or
  future recipes. The separate EoMT record covers one pretrained query-model
  composition only. None establishes useful learning.

Before publishing a native recipe result, record the taxonomy, dataset split,
crop, schedule, seed set, checkpoint/EMA/TTA choice, Segmentary commit, dependency
versions, and native-resolution evaluator settings. See
[interpreting results](../../tutorials/interpreting-results.md).
