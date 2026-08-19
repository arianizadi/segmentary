# Native ResNet-50 + PSP

Recipe: [`native_resnet50_psp.yaml`](../../../../configs/models/native_resnet50_psp.yaml)

This recipe takes the deepest selected `resnet50.a1_in1k` feature and pools it over
several grid sizes before fusion. It is a focused way to test whether broad
scene context helps a dense task.

Pros:

- explicit local-to-global context in a compact conceptual design;
- fewer multi-level fusion paths than UPer;
- exact admitted ImageNet-1k feature initialization.

Cons:

- predicts from one deep level, so fine boundaries rely on upsampling;
- pooling bins and crop size interact;
- ResNet-50 is materially larger than the ResNet-18 baseline.

## Advanced settings and compatibility

Start with bins `[1, 2, 3, 6]`, 256 channels, GroupNorm, and crops comfortably
larger than the deepest feature grid. Use `norm: batch` only with enough values
per channel; the 1x1 pooled branch makes batch-size-one training unsafe.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes. PSP has isolated forward/backward contract tests. The
assembled recipe has parser evidence, not a recorded optimizer smoke. No common
Segmentary quality benchmark exists for it.

See the [native head guide](../../components/native-heads/README.md) and
[smoke ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 72.45 | 80.91 | 85.78 | 83.02 | 99.66 | 94.60 | 90.16 | 79.96 |
| RailSem19 | 40,000 / 40,000 | 64.56 | 77.31 | 78.24 | 77.44 | 99.32 | 87.38 | 79.21 | 73.33 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 61.83 | 75.61 | 75.46 | 75.37 | 99.22 | 86.12 | 77.11 | 70.57 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 37,149,525 | 141.7 MiB | 567.6 MiB | 212.00 | 4.64 ms | 5.08 ms | 0.52 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 8h 24m 16s | 8.40 | 3.60 GiB | 7.313 |
| RailSem19 | 12h 20m 09s | 12.34 | 4.20 GiB | 7.161 |
| Cityscapes → RailSem19 | 6h 15m 52s | 6.26 | 4.21 GiB | 7.141 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.32 |
| sidewalk | 79.34 |
| building | 90.07 |
| wall | 56.29 |
| fence | 58.19 |
| pole | 38.48 |
| traffic-light | 58.05 |
| traffic-sign | 68.42 |
| vegetation | 89.89 |
| terrain | 60.36 |
| sky | 91.46 |
| person | 72.66 |
| rider | 55.00 |
| car | 93.10 |
| truck | 71.99 |
| bus | 86.61 |
| train | 77.44 |
| motorcycle | 61.12 |
| bicycle | 70.80 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 58.52 | 53.94 |
| sidewalk | 58.97 | 55.53 |
| construction | 76.04 | 74.62 |
| fence | 52.31 | 49.76 |
| pole | 55.16 | 52.87 |
| traffic-light | 49.26 | 48.58 |
| traffic-sign | 41.75 | 41.63 |
| vegetation | 85.60 | 84.41 |
| terrain | 66.35 | 63.18 |
| sky | 94.66 | 94.13 |
| human | 59.02 | 59.88 |
| car | 75.30 | 75.39 |
| truck | 40.21 | 41.74 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 78.35 | 72.40 |
| rail-track | 85.63 | 81.52 |
| rail-raised | 61.01 | 54.88 |
| rail-embedded | 46.78 | 40.26 |
| tram-track | 69.74 | 61.18 |
| trackbed | 72.00 | 68.84 |

### Provenance

- Model recipe: `configs/models/native_resnet50_psp.yaml`
- Source revisions: `a50027d6a72a9146f6302bc1f407e6477a74e8c7, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone raw-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
