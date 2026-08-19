# Native ResNet-18 + FPN + FCN

Recipe: [`native_resnet18_fpn_fcn.yaml`](../../../../configs/models/native_resnet18_fpn_fcn.yaml)

This is the smallest conventional multi-scale native recipe. The exact
`resnet18.a1_in1k` backbone emits
four selected feature levels, FPN makes them all 128 channels, and FCN resizes
and concatenates the pyramid before two ordinary convolutions and a classifier.

## When to use it

Use it for a first native-component run, a dataset plumbing check, or a readable
baseline before trying context-heavy heads.

Pros:

- relatively small and easy to reason about;
- explicit feature pyramid supports objects at several scales;
- every decoder component is Segmentary-owned and independently checked;
- exact admitted ImageNet-1k feature initialization.

Cons:

- pretrained initialization adds a download/license/provenance dependency;
- FCN has less explicit global context than PSP, ASPP, or UPer;
- FPN adds memory compared with an identity neck.

## Advanced settings and compatibility

Reduce `out_channels` and FCN `channels` together for a smaller smoke. Increase
them only after measuring memory. All selected FPN indices are post-neck indices.
Keep `llrd: 1.0` for this CNN. GroupNorm is safe for small batches; BatchNorm
needs representative batch statistics.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes, including odd dimensions. The native suite separately
passed scratch FPN/head shape, backward, optimizer, and DDP tests. The assembled
pretrained recipe has parser evidence, not an optimizer smoke. No common-data
mIoU benchmark exists for this exact recipe.

See [native backbones](../../components/native-backbones/README.md),
[necks](../../components/native-necks/README.md), and
[heads](../../components/native-heads/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 74.33 | 83.19 | 86.09 | 84.52 | 99.71 | 95.37 | 91.50 | 78.48 |
| RailSem19 | 40,000 / 40,000 | 62.77 | 75.91 | 76.39 | 75.55 | 99.27 | 87.52 | 78.86 | 70.85 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 59.26 | 72.51 | 74.44 | 72.52 | 99.16 | 85.73 | 76.23 | 67.73 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 12,631,253 | 48.2 MiB | 193.0 MiB | 226.85 | 4.38 ms | 4.60 ms | 0.64 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 2h 12m 01s | 2.20 | 2.43 GiB | 7.602 |
| RailSem19 | 9h 13m 56s | 9.23 | 3.08 GiB | 7.731 |
| Cityscapes → RailSem19 | 4h 36m 48s | 4.61 | 3.10 GiB | 7.720 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.55 |
| sidewalk | 81.29 |
| building | 91.32 |
| wall | 53.27 |
| fence | 55.73 |
| pole | 57.69 |
| traffic-light | 66.01 |
| traffic-sign | 75.35 |
| vegetation | 91.74 |
| terrain | 62.14 |
| sky | 93.86 |
| person | 79.24 |
| rider | 58.64 |
| car | 94.23 |
| truck | 73.82 |
| bus | 77.52 |
| train | 69.80 |
| motorcycle | 58.33 |
| bicycle | 74.69 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 55.53 | 50.86 |
| sidewalk | 55.16 | 51.46 |
| construction | 74.61 | 72.22 |
| fence | 49.11 | 46.02 |
| pole | 59.41 | 56.73 |
| traffic-light | 47.96 | 45.85 |
| traffic-sign | 42.52 | 39.65 |
| vegetation | 85.22 | 83.19 |
| terrain | 64.49 | 60.39 |
| sky | 95.15 | 94.66 |
| human | 57.82 | 58.22 |
| car | 71.66 | 71.24 |
| truck | 16.90 | 9.55 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 76.06 | 73.09 |
| rail-track | 86.01 | 80.63 |
| rail-raised | 68.72 | 65.63 |
| rail-embedded | 49.29 | 45.44 |
| tram-track | 65.35 | 53.72 |
| trackbed | 71.74 | 67.44 |

### Provenance

- Model recipe: `configs/models/native_resnet18_fpn_fcn.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
