# Built-in SegFormer-B0

Use [`segformer_b0.yaml`](../../../../configs/models/segformer_b0.yaml) for the
smallest hand-integrated SegFormer. It is the quickest built-in transformer for
an overfit check, data-pipeline check, or short experiment.

## What it is

`segformer_b0` loads the `nvidia/mit-b0` hierarchical transformer **encoder**.
Its four feature scales feed a newly initialized SegFormer all-MLP decode head.
Segmentary resizes the head's stride-4 logits back to input resolution before loss
or evaluation.

This is not the same choice as
[`hf_auto` SegFormer-B0](../hf-auto-segformer-b0/README.md). The latter starts
from a complete ADE20K semantic-segmentation checkpoint; this built-in starts
from an ImageNet-pretrained encoder and a fresh dataset-specific head.

## When to use it

Pros:

- small enough for fast setup checks and cheap tuning-mode experiments;
- multi-scale transformer features fit dense prediction naturally;
- full, frozen, and LoRA paths have regression coverage;
- its output contract and non-square input behavior are tested.

Cons:

- lower capacity than B2 or B5;
- the decoder has no task-specific pretraining;
- a successful B0 run does not predict the memory or throughput of a large arm;
- no comparable Segmentary dataset-quality result is recorded for this recipe.

## Practical settings

The shipped file uses full tuning. Frozen tuning is a useful low-cost diagnostic:
if only the head cannot learn a tiny training set, inspect labels and mappings
before scheduling a larger model. LoRA is useful for a parameter-efficiency
study, but it adds rank, alpha, dropout, and target-layout choices; prove that
adapter and head gradients are nonzero before a long run.

Use RGB ImageNet normalization and a crop divisible by 32. The default
`checkpoint` may be replaced by another compatible MiT-B0 encoder repository or
local snapshot. The hand-written path rejects the generic `revision` field, so
use a local immutable snapshot if the exact upstream weight revision matters.

`reset_head: true` resets only the final classifier. It keeps the MiT encoder and
the class-agnostic portions of the decode head.

## Verified evidence and benchmarks

The model contract suite loads the real B0 encoder, checks finite
input-resolution output, a non-square input, head reset, full/frozen tuning,
LoRA injection, and real backward gradients. B0 is also the model used by the
tiny end-to-end curriculum regression.

Those are compatibility checks, not accuracy benchmarks. No same-protocol
Segmentary mIoU is claimed for this recipe yet.

See the [built-in model component](../../components/builtin-models/README.md)
and [model comparison guide](../../../guides/models-and-tuning.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 74.55 | 82.61 | 87.15 | 84.65 | 99.73 | 95.63 | 91.93 | 80.35 |
| RailSem19 | 40,000 / 40,000 | 65.26 | 78.44 | 77.53 | 77.91 | 99.32 | 88.39 | 80.13 | 72.64 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 60.17 | 73.81 | 74.71 | 73.76 | 99.18 | 86.00 | 76.56 | 67.85 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 3,719,541 | 14.2 MiB | 57.1 MiB | 136.18 | 7.29 ms | 7.67 ms | 0.89 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 5h 35m 44s | 5.60 | 3.05 GiB | 8.574 |
| RailSem19 | Rail40 standalone | 9h 51m 21s | 9.86 | 3.24 GiB | 7.551 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 4h 55m 50s | 4.93 | 3.24 GiB | 7.478 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 10h 31m 34s | 10.53 | 3.24 GiB | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.93 |
| sidewalk | 83.35 |
| building | 91.70 |
| wall | 54.98 |
| fence | 55.93 |
| pole | 59.07 |
| traffic-light | 67.23 |
| traffic-sign | 75.48 |
| vegetation | 92.00 |
| terrain | 63.75 |
| sky | 94.47 |
| person | 78.93 |
| rider | 53.61 |
| car | 94.05 |
| truck | 67.98 |
| bus | 81.59 |
| train | 65.60 |
| motorcycle | 63.10 |
| bicycle | 75.65 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 57.58 | 50.02 |
| sidewalk | 57.48 | 52.38 |
| construction | 76.03 | 73.33 |
| fence | 52.12 | 49.00 |
| pole | 59.59 | 56.96 |
| traffic-light | 48.02 | 46.24 |
| traffic-sign | 41.59 | 41.06 |
| vegetation | 86.21 | 84.07 |
| terrain | 67.29 | 61.55 |
| sky | 95.27 | 94.72 |
| human | 59.01 | 59.16 |
| car | 74.70 | 72.78 |
| truck | 37.94 | 25.05 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 78.82 | 75.00 |
| rail-track | 87.91 | 79.29 |
| rail-raised | 69.32 | 63.19 |
| rail-embedded | 49.97 | 43.79 |
| tram-track | 67.61 | 48.59 |
| trackbed | 73.55 | 66.98 |

### Provenance

- Model recipe: `configs/models/segformer_b0.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone ema-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
