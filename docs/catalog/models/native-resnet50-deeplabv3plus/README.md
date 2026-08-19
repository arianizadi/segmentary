# Native ResNet-50 + DeepLabV3+

Recipe: [`native_resnet50_deeplabv3plus.yaml`](../../../../configs/models/native_resnet50_deeplabv3plus.yaml)

This head combines ASPP context from the coarsest selected feature with an
early high-resolution skip from `resnet50.a1_in1k`. It is the native catalog's balanced ResNet recipe
for both scene context and boundaries.

Pros:

- explicit low-level detail path;
- multi-rate context in the deep path;
- familiar architecture for controlled head comparisons.

Cons:

- more compute and knobs than plain ASPP;
- low/high feature selection must match the returned backbone tuple;
- pretrained initialization adds download/license/provenance dependencies.

## Advanced settings and compatibility

Here `low_index: 0` is stride 4 and `high_index: 3` is stride 32 because the
backbone returns original levels `[1, 2, 3, 4]`. Keep indices ordered. Tune
`low_channels`, main `channels`, and dilation rates one family at a time. Use
GroupNorm for small segmentation batches.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes; DeepLabV3+ has isolated forward/backward contract tests.
The assembled recipe has parser evidence but no recorded optimizer smoke. No
common Segmentary mIoU benchmark exists.

See [native heads](../../components/native-heads/README.md) and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 76.31 | 84.86 | 87.19 | 85.89 | 99.73 | 95.68 | 92.04 | 81.74 |
| RailSem19 | 40,000 / 40,000 | 66.38 | 78.71 | 79.28 | 78.83 | 99.33 | 88.26 | 80.11 | 74.30 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 64.68 | 77.95 | 77.58 | 77.63 | 99.26 | 87.33 | 78.59 | 72.02 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 40,351,925 | 153.9 MiB | 616.5 MiB | 136.37 | 7.30 ms | 7.61 ms | 0.78 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 6h 41m 47s | 6.70 | 4.53 GiB | 6.788 |
| RailSem19 | 11h 13m 54s | 11.23 | 5.03 GiB | 6.709 |
| Cityscapes → RailSem19 | 5h 38m 08s | 5.64 | 5.02 GiB | 6.566 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.78 |
| sidewalk | 82.69 |
| building | 92.01 |
| wall | 54.46 |
| fence | 59.76 |
| pole | 59.42 |
| traffic-light | 67.65 |
| traffic-sign | 77.20 |
| vegetation | 91.90 |
| terrain | 62.09 |
| sky | 94.53 |
| person | 80.28 |
| rider | 61.66 |
| car | 94.53 |
| truck | 77.94 |
| bus | 86.20 |
| train | 71.33 |
| motorcycle | 63.49 |
| bicycle | 74.97 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 57.66 | 55.81 |
| sidewalk | 58.99 | 57.01 |
| construction | 76.70 | 75.65 |
| fence | 52.21 | 50.52 |
| pole | 61.13 | 59.78 |
| traffic-light | 50.90 | 49.48 |
| traffic-sign | 45.51 | 44.14 |
| vegetation | 85.44 | 84.17 |
| terrain | 65.88 | 62.53 |
| sky | 95.18 | 95.03 |
| human | 61.75 | 62.15 |
| car | 76.63 | 75.67 |
| truck | 39.93 | 42.44 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 79.46 | 76.66 |
| rail-track | 88.77 | 85.64 |
| rail-raised | 70.40 | 67.55 |
| rail-embedded | 50.30 | 48.26 |
| tram-track | 71.11 | 65.43 |
| trackbed | 73.32 | 70.99 |

### Provenance

- Model recipe: `configs/models/native_resnet50_deeplabv3plus.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, a50027d6a72a9146f6302bc1f407e6477a74e8c7, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone raw-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
