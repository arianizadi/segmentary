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
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class EMA checkpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 9h 12m 18s | 9.21 | 5.86 GiB | 6.607 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

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

### Provenance

- Model recipe: `configs/models/native_convnext_tiny_uper.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0.
- EMA quality evaluation uses 1024x1024 sliding windows, stride 768, no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
