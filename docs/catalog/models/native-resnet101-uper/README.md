# Native ResNet-101 + UPer

Recipe: [`native_resnet101_uper.yaml`](../../../../configs/models/native_resnet101_uper.yaml)

UPer adds pyramid pooling to the deepest feature and then fuses the whole
fine-to-coarse hierarchy. Paired with `resnet101.a1_in1k`, this is the high-capacity
native CNN recipe in the initial catalog.

Pros:

- combines global scene context with all four selected scales;
- deeper backbone offers more representational capacity;
- direct identity neck keeps the model graph understandable.

Cons:

- largest backbone parameter count in this native set;
- highest expected training memory/compute among these recipes;
- capacity is wasteful until data and overfit checks are healthy.

## Advanced settings and compatibility

Begin at 256 decoder channels and GroupNorm. Reducing channels is the first
memory lever. Keep `llrd: 1.0`: this is a CNN and no layerwise schedule is
claimed. The four head indices refer to the four selected ResNet outputs.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes. UPer has isolated forward/backward tests. The assembled
YAML has parser evidence only; there is no recorded optimizer smoke, memory
measurement, latency result, or common-data mIoU benchmark.

See [native backbones](../../components/native-backbones/README.md),
[native heads](../../components/native-heads/README.md), and the
[smoke ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 78.46 | 86.42 | 88.49 | 87.35 | 99.75 | 95.99 | 92.58 | 84.70 |
| RailSem19 | 40,000 / 40,000 | 68.44 | 80.47 | 80.56 | 80.40 | 99.37 | 89.08 | 81.27 | 76.77 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 66.89 | 79.44 | 79.31 | 79.30 | 99.31 | 88.24 | 79.93 | 75.24 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 61,323,093 | 233.9 MiB | 937.2 MiB | 65.20 | 15.19 ms | 16.65 ms | 1.36 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 7h 54m 19s | 7.91 | 6.61 GiB | 6.192 |
| RailSem19 | 13h 39m 24s | 13.66 | 6.86 GiB | 5.364 |
| Cityscapes → RailSem19 | 6h 50m 30s | 6.84 | 6.88 GiB | 5.285 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.89 |
| sidewalk | 83.22 |
| building | 92.76 |
| wall | 58.37 |
| fence | 60.55 |
| pole | 61.89 |
| traffic-light | 72.23 |
| traffic-sign | 79.36 |
| vegetation | 92.31 |
| terrain | 63.19 |
| sky | 94.56 |
| person | 82.78 |
| rider | 64.61 |
| car | 95.32 |
| truck | 74.27 |
| bus | 87.92 |
| train | 84.01 |
| motorcycle | 67.35 |
| bicycle | 78.21 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 58.58 | 56.14 |
| sidewalk | 60.82 | 58.91 |
| construction | 78.21 | 77.61 |
| fence | 54.66 | 53.25 |
| pole | 61.90 | 61.82 |
| traffic-light | 55.67 | 53.18 |
| traffic-sign | 48.12 | 49.58 |
| vegetation | 86.75 | 85.23 |
| terrain | 67.73 | 64.58 |
| sky | 95.38 | 95.51 |
| human | 65.45 | 65.98 |
| car | 79.48 | 79.71 |
| truck | 41.54 | 41.25 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 81.86 | 79.34 |
| rail-track | 89.61 | 87.04 |
| rail-raised | 72.84 | 70.65 |
| rail-embedded | 54.70 | 52.47 |
| tram-track | 72.58 | 66.21 |
| trackbed | 74.43 | 72.44 |

### Provenance

- Model recipe: `configs/models/native_resnet101_uper.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471, db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: —; RailSem19: —; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
