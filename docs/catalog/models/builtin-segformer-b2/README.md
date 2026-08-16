# SegFormer-B2

Config: [`configs/models/segformer_b2.yaml`](../../../../configs/models/segformer_b2.yaml)

## What it is

This built-in recipe pairs the MiT-B2 encoder with Segmentary's unified dense
segmentation head. It supports full, frozen-backbone, and configured LoRA tuning,
EMA checkpoints, native-resolution validation, sliding-window evaluation, and
the standard curriculum runner.

## Pros

- It is a balanced general-purpose transformer baseline.
- The unified head works with the repository's canonical taxonomy and active-class
  masking contracts.
- The recipe is small enough to iterate on while remaining more capable than the
  B0 variant.

## Cons

- It is slower and larger than SegFormer-B0.
- It is not designed for instance or panoptic segmentation.
- Model quality still depends on the dataset, taxonomy, schedule, augmentation,
  seed, and evaluation protocol; the recipe itself is not a quality claim.

## Tuning and resource advice

Start with full tuning and keep effective batch size, crop size, optimizer-step
budget, seed, checkpoint policy, and evaluation settings fixed across comparisons.
If memory is tight, lower the per-device batch and raise accumulation rather than
silently changing effective batch size. Frozen and LoRA tuning answer different
questions and should remain explicitly labeled.

## Evidence boundary

The recipe has implementation and compatibility coverage, but this clean public
starting point does not include a prior model-quality benchmark. New results
should be added only after a complete, reproducible run.

## Related documentation

- [Built-in model components](../../components/builtin-models/README.md)
- [Models and tuning](../../../guides/models-and-tuning.md)
- [Evaluation and results](../../../guides/evaluation-and-results.md)
- [Interpreting results](../../../tutorials/interpreting-results.md)

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 80.65 | 87.77 | 90.05 | 88.83 | 99.78 | 96.46 | 93.40 | 86.77 |
| RailSem19 | 40,000 / 40,000 | 70.39 | 81.73 | 82.20 | 81.90 | 99.41 | 90.06 | 82.61 | 78.41 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 27,362,773 | 104.4 MiB | 418.1 MiB | 53.26 | 18.63 ms | 19.41 ms | 2.25 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 8h 10m 00s | 8.17 | 12.12 GiB | 6.331 |
| RailSem19 | 14h 17m 34s | 14.29 | 11.73 GiB | 5.037 |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.42 |
| sidewalk | 86.65 |
| building | 93.22 |
| wall | 65.83 |
| fence | 62.47 |
| pole | 65.42 |
| traffic-light | 73.77 |
| traffic-sign | 80.58 |
| vegetation | 92.84 |
| terrain | 65.69 |
| sky | 95.14 |
| person | 83.55 |
| rider | 66.01 |
| car | 95.47 |
| truck | 85.63 |
| bus | 89.68 |
| train | 81.07 |
| motorcycle | 71.74 |
| bicycle | 79.15 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 62.31 | — |
| sidewalk | 62.97 | — |
| construction | 79.76 | — |
| fence | 58.21 | — |
| pole | 63.84 | — |
| traffic-light | 56.91 | — |
| traffic-sign | 51.03 | — |
| vegetation | 87.76 | — |
| terrain | 70.36 | — |
| sky | 96.00 | — |
| human | 66.07 | — |
| car | 81.16 | — |
| truck | 46.89 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 83.29 | — |
| rail-track | 90.26 | — |
| rail-raised | 73.44 | — |
| rail-embedded | 56.68 | — |
| tram-track | 74.63 | — |
| trackbed | 75.83 | — |

### Provenance

- Model recipe: `configs/models/segformer_b2.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0; RailSem19: 0.
- Quality evaluation weights: Cityscapes: —; RailSem19: —.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
