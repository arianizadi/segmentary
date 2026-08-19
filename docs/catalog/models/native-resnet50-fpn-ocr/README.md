# Native ResNet-50 + FPN + supervised OCR

Recipe:
[`native_resnet50_fpn_ocr.yaml`](../../../../configs/models/native_resnet50_fpn_ocr.yaml)

Here, OCR means **object-contextual representations**, not reading text. The
model predicts a rough semantic map, uses that map to form one image-specific
feature vector per class, and lets every pixel attend to those class regions
before making the refined prediction.

The rough map is not disposable scaffolding. It defines the object regions, so
the recipe exposes it as named full-resolution `ocr_coarse` logits with positive
loss weight 0.4. Training optimizes both the refined output and that coarse
region generator; evaluation and the public tensor `forward` use only the
refined output.

## Beginner use

Compose this model after the base config and before your experiment:

```bash
segmentary-train \
  configs/base.yaml \
  configs/models/native_resnet50_fpn_ocr.yaml \
  path/to/experiment.yaml \
  --seed 0 --print-config
```

Run `segmentary-models probe` and a tiny real-data overfit check before a long
job. Only the exact ResNet-50 backbone is pretrained. FPN, object-context
layers, and both classifiers start randomly initialized.

The shipped recipe is **multiclass**. For a binary task, layer the usual
`model.native.task: binary`, `loss.task: binary`, an exact two-class taxonomy,
and BCE settings on top. Both the refined and `ocr_coarse` outputs stay at one
raw class-1 positive logit.

<details>
<summary>How binary OCR handles object-context gathering</summary>

Inside object-context gathering *only*, a logit difference `z` maps to centered
two-class logits `[-z/2, +z/2]`. Under the per-pixel class-axis softmax that
gives `[1-sigmoid(z), sigmoid(z)]`, and cross-entropy on the pair equals BCE
on `z`.

OCR's later spatial softmax pools the two channels separately, so the resulting
proxies can differ. Centering is a symmetric, zero-mean **gauge choice** — one
logit cannot reconstruct two independently learned spatial score maps.

This is an explicit Segmentary extension, not a two-logit OCR equivalence,
configuration, or benchmark from the paper.

</details>

The retained GPU record below is multiclass. Binary OCR has separate CPU
contract and gradient evidence only.

## Pros:

- the object-region generator is explicitly supervised, as required by the
  OCR paper;
- object context distinguishes semantic classes rather than only pooling fixed
  spatial scales;
- pixel-to-region attention grows with pixels times classes, avoiding dense
  pixel-to-pixel attention;
- FPN gives the head high-resolution detail and deep context through a regular
  four-level feature contract;
- the exact pretrained backbone source and both train-time outputs are recorded
  by the standard model probe.

## Cons:

- a 512-channel fusion path plus FPN is heavier than FCN or LR-ASPP;
- poor coarse predictions can produce poor region representations early in
  training;
- two supervised predictions consume more training memory than a one-output
  head;
- the decoder has no task-trained checkpoint; only the backbone is pretrained;
- this ResNet-50/FPN composition differs from the paper's dilated ResNet-101 and
  HRNet-W48 architectures, so their mIoU values are not expected results here.

## What each part does

| part | shipped setting | simple meaning |
|---|---|---|
| backbone | `resnet50.a1_in1k`, pretrained | exact timm A1 ImageNet-1k feature extractor |
| feature indices | `[1, 2, 3, 4]` | use admitted 1/4, 1/8, 1/16, and 1/32 stages |
| FPN | four 256-channel outputs | merge deep context downward and standardize feature widths |
| OCR `channels` | 512 | width of pixel, region, and fused output representations |
| `key_channels` | 256 | width used to compare pixels with class regions |
| `attention_scale` | 1 | compute relations at the full 1/4 fusion grid |
| dropout | 0.05 | regularize the refined classifier input |
| coarse loss | 0.4 | supervise class-region formation with 40% of the configured dense objective |
| primary loss | 1.0 | train the refined full-resolution logits normally |

The loss listed here is not a hidden second implementation. Segmentary returns
both tensors through `SegmentationOutput`, applies the experiment's configured
dense loss to each, and records `aux/ocr_coarse/*` components. Thus class
weights, ignore pixels, active-class masks, and any selected compatible dense
terms use the same engine contract for both outputs.

## Advanced settings and compatibility

Lowering `channels` reduces the cost of the concatenated FPN projection,
context feature, and fusion block. Lowering `key_channels` specifically reduces
the pixel-region query/key/value work. These change model capacity and need a
new experiment identity; neither is a lossless runtime switch.

`attention_scale: 2` or larger max-pools the pixel-query grid only during
attention and upsamples the resulting context before fusion. This can reduce
relation memory at large crops, but small objects and boundaries may lose
detail. Values must be positive and cannot exceed the finest selected runtime
feature size. Keep 1 until actual memory pressure is measured.

`coarse_loss_weight` must be finite and greater than zero. The default 0.4 is
the semantic-segmentation weight reported in the primary paper. Larger values
emphasize region formation but can pull optimization toward the rough map;
smaller positive values weaken its direct supervision. Zero is rejected because
the paper's ablation shows that supervised object-region formation is crucial.

Selected `in_indices` must be unique, increasing, and form a strictly
fine-to-coarse pyramid. FPN is not mathematically required, but it makes the
four inputs regular and already shares context across scales. Identity can be
used as a separate experiment if the much wider raw concatenation fits memory.
GroupNorm is the safe starting point for small segmentation batches. All native
normalization and activation choices construct, but changing them is an
architecture ablation.

OCR may be the primary head only, because placing it in `auxiliary_heads` would
drop its own coarse output. Ordinary external auxiliary heads can still be
added with unique names. `reset_head: true` resets exactly the coarse and
refined classifiers, retaining FPN and class-agnostic context transformations.
The current generic ONNX/TensorRT exporter does not admit native models, so a
PyTorch smoke is not deployment evidence.

## Primary-source relationship and upstream benchmarks

The design follows Yuan, Chen, and Wang, [*Object-Contextual Representations for
Semantic Segmentation* (ECCV
2020)](https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123510171.pdf),
and the authors' [official HRNet/OCR implementation at the reviewed
revision](https://github.com/HRNet/HRNet-Semantic-Segmentation/tree/0bbb2880446ddff2d78f8dd7e8c4c610151d5a51). Segmentary
implements the paper's three central stages: supervised soft class regions,
spatially weighted class-region representations, and pixel-to-region attention
followed by feature fusion.

The paper's controlled ablations are useful architecture evidence and motivate
the positive coarse weight; they are **not** benchmarks for this ResNet-50/FPN
recipe. No MMSegmentation code, imports, or configs are used.

## Segmentary evidence and no-quality claim

CPU contract tests cover refined and coarse full-resolution logits on odd
inputs, spatial-softmax region gathering, every native normalization,
attention scaling, invalid settings, and exact two-classifier reset. The
production dense objective test verifies the numerical `primary + 0.4 × coarse`
total and nonzero gradients for both classifiers. Additional tests cover a real
scratch ResNet-50/FPN forward-backward, four optimizer steps with changes in all
components and both classifiers, and Gloo DDP without unused parameters. The
catalog parser checks this exact pretrained YAML.

The exact multiclass recipe also passed a retained physical-GPU8 smoke from
clean commit `ae6febdb78c334f4c3c9ee30d6edda888c0d4c92`: both configured
shapes forwarded, four BF16 production-objective steps completed, every
trainable tensor received a present finite gradient, every step recorded the
named coarse loss and its weighted value, and the weight and bias of both
classifiers changed. See the
[multiclass machine record](../../../benchmarks/native-component-smokes/native-resnet50-fpn-ocr-gpu8-2026-08-12.json).

The one-logit binary extension separately passed the same two shapes and four
BF16 production-BCE steps from exact clean integration commit
`5e799107e7572574b51897957051a950ab53e28f`. All 201 trainable tensors had
present finite gradients each step; OCR pixel-query and region-key weights plus
both classifier weights and biases received finite nonzero final gradients and
changed. See the
[binary-OCR machine record](../../../benchmarks/native-component-smokes/native-binary-ocr-gpu8-2026-08-13.json).

These are construction and training-compatibility checks on synthetic inputs.
They do not measure convergence, mIoU, boundary quality, calibration,
throughput, latency, or production-crop memory. No common-protocol Segmentary
quality benchmark exists for this recipe yet.

See [native heads](../../components/native-heads/README.md),
[native necks](../../components/native-necks/README.md), and the
[native smoke ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 78.67 | 86.35 | 88.80 | 87.47 | 99.74 | 95.89 | 92.37 | 84.24 |
| RailSem19 | 40,000 / 40,000 | 67.68 | 80.19 | 79.77 | 79.86 | 99.34 | 88.89 | 80.81 | 75.59 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 66.31 | 79.12 | 79.09 | 78.96 | 99.29 | 88.00 | 79.43 | 74.03 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 32,646,762 | 124.5 MiB | 499.0 MiB | 48.24 | 20.57 ms | 21.29 ms | 1.46 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 12h 42m 58s | 12.72 | 7.09 GiB | 5.492 |
| RailSem19 | Rail40 standalone | 22h 44m 13s | 22.74 | 8.60 GiB | 4.467 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 11h 22m 57s | 11.38 | 8.59 GiB | 4.469 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 24h 05m 56s | 24.10 | 8.59 GiB | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.66 |
| sidewalk | 82.89 |
| building | 92.25 |
| wall | 56.01 |
| fence | 60.43 |
| pole | 62.09 |
| traffic-light | 72.02 |
| traffic-sign | 79.99 |
| vegetation | 92.38 |
| terrain | 65.32 |
| sky | 93.95 |
| person | 82.20 |
| rider | 63.54 |
| car | 95.29 |
| truck | 82.13 |
| bus | 89.83 |
| train | 82.37 |
| motorcycle | 66.72 |
| bicycle | 77.57 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 56.84 | 56.90 |
| sidewalk | 61.16 | 59.89 |
| construction | 77.97 | 75.91 |
| fence | 55.44 | 52.95 |
| pole | 61.81 | 60.54 |
| traffic-light | 53.25 | 52.01 |
| traffic-sign | 49.57 | 47.90 |
| vegetation | 86.35 | 85.60 |
| terrain | 66.60 | 65.19 |
| sky | 95.47 | 95.11 |
| human | 64.60 | 63.51 |
| car | 77.69 | 78.55 |
| truck | 40.21 | 46.89 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 80.25 | 78.41 |
| rail-track | 88.66 | 85.15 |
| rail-raised | 72.24 | 69.88 |
| rail-embedded | 54.00 | 52.19 |
| tram-track | 70.22 | 62.21 |
| trackbed | 73.52 | 71.02 |

### Provenance

- Model recipe: `configs/models/native_resnet50_fpn_ocr.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
