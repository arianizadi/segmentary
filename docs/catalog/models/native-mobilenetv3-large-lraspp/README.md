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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 69.45 | 81.16 | 81.03 | 80.95 | 99.66 | 94.58 | 90.24 | 75.37 |
| RailSem19 | 40,000 / 40,000 | 57.64 | 69.13 | 75.78 | 71.41 | 99.31 | 82.53 | 74.87 | 65.21 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 56.76 | 71.76 | 71.75 | 71.15 | 99.07 | 83.80 | 73.77 | 64.38 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 3,221,330 | 12.3 MiB | 49.7 MiB | 234.22 | 4.17 ms | 4.79 ms | 0.30 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | not retained | not retained | not retained | 7.324 |
| RailSem19 | Rail40 standalone | not retained | not retained | not retained | 8.128 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 4h 12m 17s | 4.20 | 2.65 GiB | 8.271 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | not retained | not retained | not retained | — |

`not retained` means the exact whole-run wall time, GPU-hours, or peak training-VRAM record is unavailable. The validated quality result, final checkpoint, iteration count, and inference evidence are still complete; the model is not retrained only to recreate resource metadata.

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

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 52.84 | 49.78 |
| sidewalk | 53.04 | 49.77 |
| construction | 69.91 | 68.36 |
| fence | 42.86 | 44.59 |
| pole | 53.62 | 51.59 |
| traffic-light | 44.58 | 42.56 |
| traffic-sign | 35.86 | 36.23 |
| vegetation | 80.57 | 82.04 |
| terrain | 61.08 | 58.37 |
| sky | 92.51 | 93.49 |
| human | 52.01 | 56.76 |
| car | 53.56 | 70.50 |
| truck | 14.84 | 30.01 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 72.00 | 55.70 |
| rail-track | 84.03 | 77.89 |
| rail-raised | 57.66 | 54.61 |
| rail-embedded | 41.78 | 38.94 |
| tram-track | 64.80 | 52.44 |
| trackbed | 67.68 | 64.81 |

### Provenance

- Model recipe: `configs/models/native_mobilenetv3_large_lraspp.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: The exact total training wall time, GPU-hours, and whole-run peak VRAM were not retained across interruption recovery; the machine record preserves the final post-resume segment separately but does not present it as the total.

<!-- segmentary:generated-city-rail-benchmark:end -->
