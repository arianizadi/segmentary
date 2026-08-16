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

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 76.31 | 84.86 | 87.19 | 85.89 | 99.73 | 95.68 | 92.04 | 81.74 |
| RailSem19 | 40,000 / 40,000 | 66.41 | 78.89 | 79.20 | 78.85 | 99.33 | 88.31 | 80.16 | 74.40 |
| Cityscapes → RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |

### Transfer checkpoints

The cumulative count includes the reused 40,000-step Cityscapes source. The historical row is retained as a baseline and is not mixed with corrected runs.

| optimizer contract | Rail iterations | cumulative iterations | mIoU | boundary F1 |
|---|---:|---:|---:|---:|
| historical 0.1x backbone + 0.1x head groups | 20,000 | 60,000 | — | — |
| corrected 0.1x backbone + 1.0x head groups | 20,000 | 60,000 | — | — |
| corrected 0.1x backbone + 1.0x head groups | 40,000 | 80,000 | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 40,351,925 | 153.9 MiB | 616.5 MiB | 128.07 | 7.38 ms | 9.29 ms | 0.82 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | 6.788 |
| RailSem19 | 11h 13m 54s | 11.23 | 5.03 GiB | 6.632 |
| Cityscapes → RailSem19 | — | — | — | — |

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
| road | 57.65 | — |
| sidewalk | 58.82 | — |
| construction | 76.82 | — |
| fence | 52.58 | — |
| pole | 61.13 | — |
| traffic-light | 50.86 | — |
| traffic-sign | 45.31 | — |
| vegetation | 85.50 | — |
| terrain | 65.83 | — |
| sky | 95.11 | — |
| human | 61.97 | — |
| car | 76.27 | — |
| truck | 39.88 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 79.72 | — |
| rail-track | 88.78 | — |
| rail-raised | 70.41 | — |
| rail-embedded | 50.41 | — |
| tram-track | 71.04 | — |
| trackbed | 73.60 | — |

### Provenance

- Model recipe: `configs/models/native_resnet50_deeplabv3plus.yaml`
- Source revisions: `a50027d6a72a9146f6302bc1f407e6477a74e8c7, db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: RailSem19: 0; Cityscapes: 0.
- Quality evaluation weights: RailSem19: —; Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone raw-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
