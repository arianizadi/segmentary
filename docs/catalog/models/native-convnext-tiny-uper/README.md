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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 81.35 | 87.68 | 91.07 | 89.25 | 99.78 | 96.51 | 93.46 | 87.01 |
| RailSem19 | 40,000 / 40,000 | 70.10 | 80.32 | 82.89 | 81.49 | 99.43 | 90.15 | 82.82 | 79.14 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 69.61 | 80.70 | 82.12 | 81.34 | 99.39 | 89.63 | 81.98 | 77.81 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 36,849,525 | 140.6 MiB | 562.6 MiB | 75.58 | 13.18 ms | 13.33 ms | 1.24 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 9h 12m 18s | 9.21 | 5.86 GiB | 6.741 |
| RailSem19 | 12h 49m 26s | 12.82 | 6.23 GiB | 5.750 |
| Cityscapes → RailSem19 | not retained | not retained | not retained | 5.770 |

`not retained` means the exact original training-duration record is no longer available. The validated quality result, final checkpoint, iteration count, and inference evidence are still complete; the model is not retrained only to recreate timing metadata.

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.33 |
| sidewalk | 86.16 |
| building | 93.27 |
| wall | 62.57 |
| fence | 65.86 |
| pole | 67.27 |
| traffic-light | 74.35 |
| traffic-sign | 82.18 |
| vegetation | 92.89 |
| terrain | 65.01 |
| sky | 95.38 |
| person | 84.57 |
| rider | 67.98 |
| car | 95.64 |
| truck | 86.65 |
| bus | 92.25 |
| train | 85.33 |
| motorcycle | 69.70 |
| bicycle | 80.20 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 64.01 | 62.69 |
| sidewalk | 64.25 | 63.05 |
| construction | 79.86 | 78.91 |
| fence | 57.96 | 57.49 |
| pole | 62.71 | 63.10 |
| traffic-light | 55.66 | 56.89 |
| traffic-sign | 53.89 | 51.80 |
| vegetation | 87.94 | 87.42 |
| terrain | 70.65 | 69.36 |
| sky | 95.94 | 95.69 |
| human | 67.84 | 68.19 |
| car | 81.10 | 81.73 |
| truck | 33.19 | 45.08 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 79.45 | 81.99 |
| rail-track | 90.92 | 89.10 |
| rail-raised | 74.77 | 72.74 |
| rail-embedded | 58.05 | 53.60 |
| tram-track | 77.28 | 68.91 |
| trackbed | 76.50 | 74.80 |

### Provenance

- Model recipe: `configs/models/native_convnext_tiny_uper.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
