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

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 74.38 | 84.52 | 84.91 | 84.57 | 99.73 | 95.59 | 91.90 | 79.54 |
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class recorded raw/EMA endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 5h 57m 46s | 5.96 | 3.65 GiB | 6.706 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

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

### Provenance

- Model recipe: `configs/models/native_efficientnet_b0_deeplabv3plus.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0.
- Quality evaluation weights: Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
