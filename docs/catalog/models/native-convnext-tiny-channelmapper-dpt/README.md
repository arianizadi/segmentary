# Native ConvNeXt-Tiny + ChannelMapper + DPT-style fusion

Recipe:
[`native_convnext_tiny_channelmapper_dpt.yaml`](../../../../configs/models/native_convnext_tiny_channelmapper_dpt.yaml)

This recipe pairs an exact pretrained ConvNeXt-Tiny feature extractor with two
Segmentary-native components. ChannelMapper independently turns the
96/192/384/768 backbone stages into four 256-channel maps. The DPT-style head
then progressively refines and combines those maps from 1/32 scale to 1/4
scale, refines a half-resolution representation, and upsamples raw multiclass
logits to the input size.

It is a useful architectural comparison with
[`native_convnext_tiny_uper.yaml`](../native-convnext-tiny-uper/README.md): the
backbone and pretrained initialization match, while the neck/head aggregation
strategy changes.

## Beginner use

Compose the model file after the base and before your experiment:

```bash
segmentary-train \
  configs/base.yaml \
  configs/models/native_convnext_tiny_channelmapper_dpt.yaml \
  path/to/experiment.yaml \
  --seed 0 --print-config
```

Run the model probe and a tiny overfit check before a long training job. The
decoder and classifier are randomly initialized even though the backbone is
pretrained.

## Pros:

- exact `convnext_tiny.fb_in22k_ft_in1k` pretrained feature source;
- four natural 4/8/16/32 spatial stages;
- projection and fusion are separate typed components that can be inspected or
  ablated independently;
- every feature level has a direct residual route into the prediction;
- GroupNorm is suitable for the small per-device batches common in segmentation.

## Cons:

- two residual 3x3 convolutions in each refinement unit make the head
  substantially heavier than a simple FCN or SegFormer-style fusion head;
- 256-channel half-resolution refinement can be memory-intensive at large
  crops;
- ConvNeXt pretraining adds download, license, and provenance dependencies;
- no task-trained DPT weights are loaded: only the ConvNeXt backbone is
  pretrained;
- this CNN-pyramid composition is DPT-inspired, not checkpoint-compatible with
  the paper's ViT DPT models.

## Advanced settings and compatibility

| part | setting | contract |
|---|---|---|
| backbone | `convnext_tiny.fb_in22k_ft_in1k` | exact timm tag; pretrained on ImageNet-22k then fine-tuned on ImageNet-1k |
| backbone indices | `[0, 1, 2, 3]` | ConvNeXt exposes exactly the four admitted 4/8/16/32 stages |
| ChannelMapper | 256 channels, kernel 1, four outputs | maps widths independently and preserves reductions; no top-down fusion |
| DPT head | four indices, 256 channels | requires exactly four strictly coarser equal-width maps |
| normalization | GroupNorm | avoids per-device batch-statistic dependence |
| task | multiclass | raw `(N,C,H,W)` logits and the standard dense objective |
| tuning | full | all backbone, neck, and head tensors train |
| LLRD | `1.0` | disabled; no ConvNeXt-specific depth mapping is claimed |

ChannelMapper `out_channels` and DPT `channels` must be changed together. Lower
both to reduce decoder compute and memory; that is a new architecture variant,
not a runtime optimization. `kernel_size: 3` adds local mixing to each mapped
level. Increasing `num_outputs` has no effect unless the DPT indices are changed,
and DPT deliberately accepts exactly four selected levels.

An FPN can also provide four equal-width inputs, but it fuses the hierarchy
before the DPT head and is therefore a separate double-fusion experiment.
Identity is incompatible with this ConvNeXt selection because its four native
channel widths differ. `reset_head: true` resets only the DPT classifier; the
ChannelMapper and class-agnostic fusion units are retained.

The generic ONNX/TensorRT exporter does not admit this native architecture.
Do not infer deployment support from a PyTorch training smoke.

## DPT relationship and primary references

The original DPT work reassembles tokens from multiple transformer stages and
progressively combines image-like representations with a convolutional decoder.
This recipe begins with ConvNeXt's already-spatial hierarchy, so ChannelMapper
replaces token reassembly only as a channel-normalization boundary. The head
retains the primary paper's coarse-to-fine residual fusion, half-resolution
semantic representation, dropout, raw class logits, and bilinear final
upsampling ideas. It is not an exact reproduction and uses no copied/imported
MMSegmentation code.

Primary sources:

- Ranftl, Bochkovskiy, and Koltun,
  [*Vision Transformers for Dense Prediction* (ICCV
  2021)](https://openaccess.thecvf.com/content/ICCV2021/html/Ranftl_Vision_Transformers_for_Dense_Prediction_ICCV_2021_paper.html).
- The authors' archived, MIT-licensed
  [official DPT repository](https://github.com/isl-org/DPT).

## Evidence and benchmark boundary

The exact ConvNeXt tag already has retained CPU pretrained-feature admission at
two shapes, including an odd input. New CPU tests cover ChannelMapper metadata,
extra levels, independence, invalid values, and backward behavior; DPT
full-resolution shapes, all selected-feature gradients, supported
normalizations, classifier reset, invalid contracts, a real scratch
ConvNeXt-Tiny forward/backward, and four optimizer steps on a small native
stack. The catalog parser validates this exact YAML.

The retained
[GPU8 machine record](../../../benchmarks/native-component-smokes/native-convnext-tiny-channelmapper-dpt-gpu8-2026-08-12.json)
comes from clean commit `23eebad016e977bfad5793d52e0516f7b136b09b`.
The exact pretrained recipe completed both `64x96` and odd `65x97` forwards and
four BF16 production-objective AdamW steps at batch one. Every one of 243
trainable parameter tensors had a present finite gradient on every step, and
both tracked classifier tensors changed.

These are compatibility and training-smoke checks on synthetic inputs. They do
not measure convergence, memory at production crops, latency, mIoU, or whether
this recipe beats UPer. No common-protocol Segmentary model-quality benchmark
exists for this composition yet.

See [native necks](../../components/native-necks/README.md),
[native heads](../../components/native-heads/README.md), and the
[native smoke ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 0 / 40,000 | — | — | — | — | — | — | — | — |
| RailSem19 | 40,000 / 40,000 | 70.70 | 80.84 | 83.58 | 82.01 | 99.43 | 90.25 | 82.91 | 79.22 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class EMA checkpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 38,230,389 | 145.8 MiB | 583.7 MiB | 28.85 | 34.65 ms | 34.74 ms | 1.95 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | — |
| RailSem19 | 22h 57m 26s | 22.96 | 11.42 GiB | 3.334 |
| Cityscapes → RailSem19 | — | — | — | — |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 63.33 | — |
| sidewalk | 63.63 | — |
| construction | 79.95 | — |
| fence | 58.59 | — |
| pole | 63.52 | — |
| traffic-light | 57.23 | — |
| traffic-sign | 53.16 | — |
| vegetation | 87.87 | — |
| terrain | 70.37 | — |
| sky | 96.04 | — |
| human | 67.29 | — |
| car | 81.38 | — |
| truck | 38.45 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 81.57 | — |
| rail-track | 91.13 | — |
| rail-raised | 75.31 | — |
| rail-embedded | 59.56 | — |
| tram-track | 78.20 | — |
| trackbed | 76.70 | — |

### Provenance

- Model recipe: `configs/models/native_convnext_tiny_channelmapper_dpt.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: RailSem19: 0.
- EMA quality evaluation uses 1024x1024 sliding windows, stride 768, no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
