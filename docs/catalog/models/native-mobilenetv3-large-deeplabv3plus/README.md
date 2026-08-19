# Native MobileNetV3-Large + DeepLabV3+

Recipe: [`native_mobilenetv3_large_deeplabv3plus.yaml`](../../../../configs/models/native_mobilenetv3_large_deeplabv3plus.yaml)

This is the lowest-backbone-parameter native recipe in the initial set. The
exact `mobilenetv3_large_100.ra_in1k` pyramid feeds a reduced-width DeepLabV3+
head.

Pros:

- about 3.0 million feature-extractor parameters in the CPU probe;
- explicit low-level boundary skip despite the compact backbone;
- reasonable candidate for later deployment profiling.

Cons:

- low parameter count does not establish latency on a target device;
- the selected deepest feature is 960 channels, so decoder projections still matter;
- pretrained initialization adds download/license/provenance dependencies.

## Advanced settings and compatibility

Original feature entries `[1, 2, 3, 4]` become returned head indices `0..3` at
strides 4/8/16/32. The 160-channel main and 32-channel low-level projections are
deliberately smaller than the ResNet recipes. Profile the actual target device
before calling this an edge model.

## Evidence and benchmarks

The exact tagged feature extractor loaded requested weights without fallback and
passed two CPU feature shapes. DeepLabV3+ has isolated contract tests. The
assembled recipe has parser evidence only and no latency, memory, optimizer, or
common-data mIoU benchmark.

See [native backbones](../../components/native-backbones/README.md) and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 72.91 | 82.26 | 85.08 | 83.52 | 99.71 | 95.32 | 91.46 | 78.26 |
| RailSem19 | 40,000 / 40,000 | 64.19 | 77.55 | 76.96 | 76.88 | 99.30 | 87.99 | 79.59 | 71.93 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 62.39 | 76.25 | 75.44 | 75.64 | 99.22 | 86.72 | 77.68 | 69.71 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 8,067,845 | 30.8 MiB | 123.7 MiB | 168.14 | 5.93 ms | 6.45 ms | 0.44 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 5h 03m 01s | 5.05 | 2.80 GiB | 6.798 |
| RailSem19 | 9h 37m 04s | 9.62 | 3.23 GiB | 7.657 |
| Cityscapes → RailSem19 | 4h 48m 27s | 4.81 | 3.23 GiB | 7.263 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.71 |
| sidewalk | 81.82 |
| building | 91.46 |
| wall | 53.91 |
| fence | 55.64 |
| pole | 56.47 |
| traffic-light | 62.87 |
| traffic-sign | 72.89 |
| vegetation | 91.71 |
| terrain | 60.24 |
| sky | 94.32 |
| person | 77.07 |
| rider | 55.77 |
| car | 93.74 |
| truck | 66.97 |
| bus | 76.42 |
| train | 66.11 |
| motorcycle | 58.63 |
| bicycle | 71.57 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 56.10 | 53.93 |
| sidewalk | 57.10 | 54.94 |
| construction | 75.64 | 74.22 |
| fence | 50.37 | 48.26 |
| pole | 59.78 | 57.51 |
| traffic-light | 48.12 | 47.55 |
| traffic-sign | 39.70 | 38.83 |
| vegetation | 85.30 | 83.54 |
| terrain | 65.45 | 62.23 |
| sky | 95.25 | 94.57 |
| human | 58.41 | 58.46 |
| car | 71.82 | 73.69 |
| truck | 28.04 | 32.56 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 78.96 | 74.45 |
| rail-track | 88.27 | 85.22 |
| rail-raised | 69.33 | 65.79 |
| rail-embedded | 49.00 | 45.68 |
| tram-track | 70.11 | 63.57 |
| trackbed | 72.92 | 70.43 |

### Provenance

- Model recipe: `configs/models/native_mobilenetv3_large_deeplabv3plus.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
