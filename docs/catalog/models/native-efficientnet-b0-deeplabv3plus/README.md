# Native EfficientNet-B0 + DeepLabV3+

Recipe: [`native_efficientnet_b0_deeplabv3plus.yaml`](../../../../configs/models/native_efficientnet_b0_deeplabv3plus.yaml)

This combines the exact `efficientnet_b0.ra_in1k` feature extractor with the context and
low-level skip paths of DeepLabV3+. It is the smaller parameter-count
alternative to the ResNet-50 pairing.

Pros:

- about 3.6 million feature-extractor parameters in the CPU probe;
- retains a low-level path for boundaries;
- useful compact architecture study.

Cons:

- parameter count does not prove wall-clock speed or low activation memory;
- narrow features may underfit difficult scenes;
- DeepLab settings remain crop/output-stride dependent.

## Advanced settings and compatibility

The recipe selects original feature entries `[1, 2, 3, 4]`, making head index
`0` stride 4 and index `3` stride 32. The decoder is reduced to 160/32 channels
to match the compact intent. Measure before increasing them.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes. DeepLabV3+ has isolated contract tests. The assembled
recipe has parser evidence but no optimizer, latency, memory, or common-data
mIoU benchmark.

See the [native head guide](../../components/native-heads/README.md) and
[smoke ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 74.38 | 84.52 | 84.91 | 84.57 | 99.73 | 95.59 | 91.90 | 79.54 |
| RailSem19 | 40,000 / 40,000 | 63.95 | 77.45 | 76.67 | 76.71 | 99.29 | 87.62 | 79.19 | 72.26 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 62.30 | 76.71 | 75.34 | 75.79 | 99.20 | 86.24 | 77.06 | 69.68 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 5,721,681 | 21.8 MiB | 88.1 MiB | 143.40 | 6.47 ms | 9.83 ms | 0.43 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 5h 57m 46s | 5.96 | 3.65 GiB | 6.706 |
| RailSem19 | 10h 09m 38s | 10.16 | 4.04 GiB | 7.005 |
| Cityscapes → RailSem19 | 5h 05m 37s | 5.09 | 4.06 GiB | 7.020 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.78 |
| sidewalk | 82.94 |
| building | 91.92 |
| wall | 60.47 |
| fence | 58.66 |
| pole | 57.85 |
| traffic-light | 64.88 |
| traffic-sign | 74.14 |
| vegetation | 92.03 |
| terrain | 61.91 |
| sky | 94.42 |
| person | 78.64 |
| rider | 56.87 |
| car | 93.97 |
| truck | 73.78 |
| bus | 76.76 |
| train | 67.63 |
| motorcycle | 54.93 |
| bicycle | 73.66 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 56.59 | 51.66 |
| sidewalk | 57.32 | 54.99 |
| construction | 75.13 | 72.87 |
| fence | 51.97 | 49.40 |
| pole | 58.72 | 57.46 |
| traffic-light | 49.06 | 46.94 |
| traffic-sign | 41.52 | 41.59 |
| vegetation | 85.05 | 82.95 |
| terrain | 64.52 | 61.95 |
| sky | 94.94 | 94.36 |
| human | 59.82 | 58.56 |
| car | 71.13 | 75.57 |
| truck | 25.23 | 41.80 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 74.79 | 64.53 |
| rail-track | 88.13 | 85.46 |
| rail-raised | 69.00 | 65.64 |
| rail-embedded | 49.42 | 46.00 |
| tram-track | 70.38 | 62.03 |
| trackbed | 72.28 | 69.94 |

### Provenance

- Model recipe: `configs/models/native_efficientnet_b0_deeplabv3plus.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
