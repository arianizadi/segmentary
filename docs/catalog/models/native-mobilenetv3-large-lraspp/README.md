# Native MobileNetV3-Large + LR-ASPP

Recipe: [`native_mobilenetv3_large_lraspp.yaml`](../../../../configs/models/native_mobilenetv3_large_lraspp.yaml)

This is Segmentary's smallest native mobile-oriented composition. The exact
`mobilenetv3_large_100.ra_in1k` feature pyramid feeds a lightweight head: one
fine feature is classified directly, while a projected deep feature is
modulated by an image-level sigmoid gate and added back at the fine scale.

Pros:

- substantially less decoder work than the DeepLabV3+ recipe;
- direct fine-feature prediction preserves a short boundary path;
- the global gate uses no BatchNorm, so batch-one training remains valid.

Cons:

- less multi-scale context than ASPP, UPer, or FPN compositions;
- low parameter count does not prove low latency on a specific device;
- only one low and one high feature participate in the prediction.

## Beginner use

Use it when memory or deployment cost matters enough to justify a deliberately
small decoder. Keep the shipped indices, 128 channels, GroupNorm, and ReLU for
the first overfit check. Compare it against MobileNetV3 + DeepLabV3+ under the
same data, crop, schedule, seed, EMA, and evaluator rather than comparing paper
numbers from different protocols.

## Advanced settings and compatibility

`low_index` must name a finer feature than `high_index`; the shipped returned
features have reductions 4/8/16/32. `channels` sizes only the deep projection.
`dropout`, every native activation, and every native normalization are typed.
The image-level gate always remains an unnormalized convolution followed by
sigmoid, preventing a pooled 1x1 BatchNorm failure. The two class projections
reset together at a taxonomy boundary.

## Evidence and benchmarks

The exact pretrained backbone tag loaded without fallback and passed two CPU
feature shapes. LR-ASPP has direct forward/backward, batch-one BatchNorm, and
classifier-reset contract tests. The assembled recipe has parser evidence; it
has no common-data mIoU, latency, memory, or multi-seed benchmark yet.

See [native heads](../../components/native-heads/README.md),
[native backbones](../../components/native-backbones/README.md), and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 69.45 | 81.16 | 81.03 | 80.95 | 99.66 | 94.58 | 90.24 | 75.37 |
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class recorded raw/EMA endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 1h 41m 02s | 1.68 | 1.80 GiB | 7.324 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.33 |
| sidewalk | 79.81 |
| building | 90.08 |
| wall | 52.09 |
| fence | 53.57 |
| pole | 47.45 |
| traffic-light | 56.71 |
| traffic-sign | 68.34 |
| vegetation | 90.71 |
| terrain | 58.11 |
| sky | 93.84 |
| person | 72.13 |
| rider | 51.23 |
| car | 92.14 |
| truck | 60.97 |
| bus | 68.48 |
| train | 61.06 |
| motorcycle | 56.22 |
| bicycle | 69.21 |

### Provenance

- Model recipe: `configs/models/native_mobilenetv3_large_lraspp.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0.
- Quality evaluation weights: Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
