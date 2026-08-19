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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 80.48 | 87.56 | 90.06 | 88.72 | 99.78 | 96.44 | 93.36 | 86.75 |
| RailSem19 | 40,000 / 40,000 | 70.42 | 81.65 | 82.30 | 81.92 | 99.41 | 90.05 | 82.59 | 78.49 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 67.37 | 80.08 | 79.58 | 79.73 | 99.33 | 88.55 | 80.34 | 75.16 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 27,362,773 | 104.4 MiB | 418.1 MiB | 53.26 | 18.63 ms | 19.41 ms | 2.25 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 8h 10m 00s | 8.17 | 12.12 GiB | 6.416 |
| RailSem19 | Rail40 standalone | 14h 17m 34s | 14.29 | 11.73 GiB | 5.039 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 7h 06m 54s | 7.12 | 11.73 GiB | 4.963 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 15h 16m 54s | 15.28 | 12.12 GiB | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.40 |
| sidewalk | 86.61 |
| building | 93.18 |
| wall | 66.33 |
| fence | 62.17 |
| pole | 65.14 |
| traffic-light | 73.65 |
| traffic-sign | 80.48 |
| vegetation | 92.77 |
| terrain | 65.18 |
| sky | 95.13 |
| person | 83.49 |
| rider | 65.82 |
| car | 95.44 |
| truck | 85.41 |
| bus | 89.34 |
| train | 79.74 |
| motorcycle | 71.72 |
| bicycle | 79.10 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 62.30 | 57.14 |
| sidewalk | 63.30 | 60.28 |
| construction | 79.73 | 78.21 |
| fence | 57.88 | 54.60 |
| pole | 63.74 | 62.20 |
| traffic-light | 56.62 | 55.33 |
| traffic-sign | 50.93 | 51.02 |
| vegetation | 87.71 | 86.58 |
| terrain | 70.33 | 66.20 |
| sky | 95.99 | 95.51 |
| human | 66.23 | 66.57 |
| car | 81.42 | 80.72 |
| truck | 47.53 | 44.88 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 83.24 | 80.22 |
| rail-track | 90.24 | 85.74 |
| rail-raised | 73.46 | 68.45 |
| rail-embedded | 56.74 | 51.67 |
| tram-track | 74.65 | 62.97 |
| trackbed | 75.87 | 71.71 |

### Provenance

- Model recipe: `configs/models/segformer_b2.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
