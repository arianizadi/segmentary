# Native ResNet-50 + ASPP

Recipe: [`native_resnet50_aspp.yaml`](../../../../configs/models/native_resnet50_aspp.yaml)

ASPP applies parallel atrous convolutions and a global-context branch to the
deepest selected `resnet50.a1_in1k` feature. Choose it when the experiment is about
multi-scale receptive fields without a low-level skip connection.

Pros:

- several context scales in one head;
- simple single-feature input;
- useful control for the DeepLabV3+ recipe.

Cons:

- limited high-resolution detail path;
- dilation rates depend on feature stride and crop size;
- pretrained initialization adds download/license/provenance dependencies.

## Advanced settings and compatibility

The shipped `[6, 12, 18]` rates are a starting choice, not a universal optimum.
Change them only as a named ablation. GroupNorm avoids the batch-one problem in
the global pooled branch. Head `in_index: 3` refers to the returned four-level
tuple after `out_indices: [1, 2, 3, 4]`.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes; ASPP has isolated forward/backward contract tests. This
assembled YAML has parser evidence but no recorded optimizer smoke or
common-data mIoU benchmark.

See [native heads](../../components/native-heads/README.md) and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 71.87 | 81.17 | 84.58 | 82.61 | 99.67 | 94.60 | 90.20 | 78.96 |
| RailSem19 | 40,000 / 40,000 | 63.99 | 76.98 | 77.46 | 76.97 | 99.28 | 87.22 | 78.66 | 72.28 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 61.00 | 74.63 | 75.12 | 74.66 | 99.17 | 85.70 | 76.32 | 69.00 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 39,048,277 | 149.0 MiB | 596.6 MiB | 223.41 | 4.44 ms | 4.67 ms | 0.53 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 8h 00m 50s | 8.01 | 3.66 GiB | 7.171 |
| RailSem19 | 12h 23m 01s | 12.38 | 4.27 GiB | 7.351 |
| Cityscapes → RailSem19 | 6h 11m 24s | 6.19 | 4.25 GiB | 7.369 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.43 |
| sidewalk | 80.16 |
| building | 90.14 |
| wall | 50.40 |
| fence | 59.31 |
| pole | 39.76 |
| traffic-light | 58.11 |
| traffic-sign | 66.67 |
| vegetation | 89.83 |
| terrain | 61.20 |
| sky | 91.86 |
| person | 71.07 |
| rider | 54.78 |
| car | 92.94 |
| truck | 77.00 |
| bus | 83.57 |
| train | 71.71 |
| motorcycle | 59.61 |
| bicycle | 70.05 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 57.17 | 53.28 |
| sidewalk | 58.38 | 55.58 |
| construction | 75.92 | 73.81 |
| fence | 51.86 | 48.46 |
| pole | 54.34 | 52.29 |
| traffic-light | 46.86 | 46.66 |
| traffic-sign | 41.13 | 40.17 |
| vegetation | 84.58 | 83.31 |
| terrain | 64.44 | 61.05 |
| sky | 94.35 | 93.83 |
| human | 58.84 | 59.12 |
| car | 73.59 | 74.70 |
| truck | 40.29 | 40.23 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 79.36 | 73.95 |
| rail-track | 85.93 | 80.88 |
| rail-raised | 61.02 | 53.08 |
| rail-embedded | 45.57 | 38.81 |
| tram-track | 70.19 | 61.61 |
| trackbed | 71.90 | 68.25 |

### Provenance

- Model recipe: `configs/models/native_resnet50_aspp.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471, db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0; Cityscapes → RailSem19: 0; RailSem19: 0.
- Quality evaluation weights: Cityscapes: —; Cityscapes → RailSem19: raw; RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
