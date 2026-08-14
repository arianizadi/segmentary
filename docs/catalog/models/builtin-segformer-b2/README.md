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
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 65.71 | 79.16 | 78.16 | 78.43 | 99.29 | 87.97 | 79.51 | 73.56 |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class EMA checkpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 8h 10m 00s | 8.17 | 12.12 GiB | 6.331 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | 7h 09m 12s | 7.15 | 11.73 GiB | 5.042 |

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
| road | — | 56.11 |
| sidewalk | — | 58.40 |
| construction | — | 77.50 |
| fence | — | 53.43 |
| pole | — | 61.67 |
| traffic-light | — | 52.79 |
| traffic-sign | — | 48.60 |
| vegetation | — | 86.02 |
| terrain | — | 64.99 |
| sky | — | 95.43 |
| human | — | 65.52 |
| car | — | 79.81 |
| truck | — | 41.99 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | — | 79.10 |
| rail-track | — | 84.14 |
| rail-raised | — | 65.82 |
| rail-embedded | — | 48.76 |
| tram-track | — | 57.99 |
| trackbed | — | 70.51 |

### Provenance

- Model recipe: `configs/models/segformer_b2.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0; Cityscapes → RailSem19: 0.
- EMA quality evaluation uses 1024x1024 sliding windows, stride 768, no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
