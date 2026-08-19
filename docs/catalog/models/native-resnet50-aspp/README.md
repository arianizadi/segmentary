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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 71.93 | 81.23 | 84.61 | 82.65 | 99.67 | 94.61 | 90.21 | 79.02 |
| RailSem19 | 40,000 / 40,000 | 63.99 | 76.98 | 77.46 | 76.97 | 99.28 | 87.22 | 78.66 | 72.28 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 61.00 | 74.63 | 75.12 | 74.66 | 99.17 | 85.70 | 76.32 | 69.00 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 39,048,277 | 149.0 MiB | 596.6 MiB | 223.41 | 4.44 ms | 4.67 ms | 0.53 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 8h 00m 50s | 8.01 | 3.66 GiB | 7.603 |
| RailSem19 | Rail40 standalone | 12h 23m 01s | 12.38 | 4.27 GiB | 7.351 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 6h 11m 24s | 6.19 | 4.25 GiB | 7.369 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 14h 12m 14s | 14.20 | 4.25 GiB | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.44 |
| sidewalk | 80.29 |
| building | 90.12 |
| wall | 50.32 |
| fence | 58.72 |
| pole | 39.78 |
| traffic-light | 58.30 |
| traffic-sign | 66.61 |
| vegetation | 89.85 |
| terrain | 61.03 |
| sky | 91.84 |
| person | 71.21 |
| rider | 54.62 |
| car | 92.93 |
| truck | 77.40 |
| bus | 83.41 |
| train | 72.35 |
| motorcycle | 60.23 |
| bicycle | 70.25 |

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
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
