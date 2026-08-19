# Native ConvNeXt-Tiny + UPer

Recipe: [`native_convnext_tiny_uper.yaml`](../../../../configs/models/native_convnext_tiny_uper.yaml)

This is a modern convolutional alternative to the ResNet/UPer recipe. The exact
`convnext_tiny.fb_in22k_ft_in1k` backbone emits four feature scales, and UPer
fuses all four with pyramid pooling at the deepest level.

Pros:

- clean four-stage hierarchy;
- useful architectural contrast with ResNet;
- global and multi-scale context in the head.

Cons:

- “Tiny” still has about 27.8 million feature-extractor parameters;
- UPer adds substantial decoder work;
- 22k-to-1k initialization adds download/license/provenance dependencies.

## Advanced settings and compatibility

ConvNeXt exposes only four default feature entries, so its valid selection is
`[0, 1, 2, 3]`, unlike the five-entry ResNet/EfficientNet/MobileNet families.
Reducing UPer channels is the first memory lever. Keep CNN `llrd: 1.0`.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and returned
the 4/8/16/32 hierarchy at two CPU input shapes. UPer has isolated
forward/backward tests. The assembled YAML has parser evidence but no optimizer
smoke or common Segmentary mIoU benchmark.

See [native backbones](../../components/native-backbones/README.md) and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 81.48 | 87.86 | 91.05 | 89.34 | 99.79 | 96.55 | 93.53 | 87.21 |
| RailSem19 | 40,000 / 40,000 | 70.38 | 80.66 | 83.07 | 81.73 | 99.43 | 90.23 | 82.91 | 79.27 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 70.22 | 81.53 | 82.36 | 81.81 | 99.41 | 89.92 | 82.38 | 78.35 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 36,849,525 | 140.6 MiB | 562.6 MiB | 75.58 | 13.18 ms | 13.33 ms | 1.24 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 9h 12m 18s | 9.21 | 5.86 GiB | 6.607 |
| RailSem19 | 12h 49m 26s | 12.82 | 6.23 GiB | 5.674 |
| Cityscapes → RailSem19 | not retained | not retained | not retained | 5.828 |

`not retained` means the exact original training-duration record is no longer available. The validated quality result, final checkpoint, iteration count, and inference evidence are still complete; the model is not retrained only to recreate timing metadata.

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.38 |
| sidewalk | 86.51 |
| building | 93.32 |
| wall | 62.34 |
| fence | 66.12 |
| pole | 67.53 |
| traffic-light | 74.51 |
| traffic-sign | 82.41 |
| vegetation | 92.95 |
| terrain | 65.46 |
| sky | 95.40 |
| person | 84.69 |
| rider | 68.17 |
| car | 95.67 |
| truck | 86.21 |
| bus | 92.20 |
| train | 85.77 |
| motorcycle | 70.23 |
| bicycle | 80.26 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 64.19 | 63.54 |
| sidewalk | 64.25 | 63.71 |
| construction | 80.07 | 79.58 |
| fence | 58.37 | 58.83 |
| pole | 62.76 | 63.19 |
| traffic-light | 56.02 | 56.67 |
| traffic-sign | 54.13 | 51.31 |
| vegetation | 87.98 | 87.88 |
| terrain | 70.81 | 70.15 |
| sky | 95.93 | 95.62 |
| human | 67.77 | 68.16 |
| car | 81.38 | 82.42 |
| truck | 35.34 | 48.70 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 80.09 | 83.03 |
| rail-track | 90.96 | 88.88 |
| rail-raised | 74.87 | 72.34 |
| rail-embedded | 58.18 | 54.11 |
| tram-track | 77.52 | 70.58 |
| trackbed | 76.61 | 75.47 |

### Provenance

- Model recipe: `configs/models/native_convnext_tiny_uper.yaml`
- Source revisions: `57f686737f3aa22db9a92e9880b1862227160dfd, b9eb3e1f390b70aad63e78b2e723bd79b5266471, db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: —; RailSem19: ema; Cityscapes → RailSem19: ema.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
