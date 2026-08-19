# FPN with ResNet-50

Recipe: [`smp_fpn_resnet50.yaml`](../../../../configs/models/smp_fpn_resnet50.yaml)

## Purpose and architecture

This recipe is a conventional multi-scale baseline. ResNet-50 produces a
hierarchy of features; the Feature Pyramid Network combines them through a
top-down pyramid and produces dense logits with a fresh segmentation head.

## Pros and cons

| pros | cons |
|---|---|
| simple multi-scale design; useful when object sizes vary; easy baseline to interpret | the lightweight fusion head may lose fine boundaries; larger encoder than mobile recipes |

## Resource notes

At five classes the model has 26,116,549 parameters. The diagnostic BF16
batch-1 64×64 forward allocated 111.4 MiB on an NVIDIA L40S. This excludes
training gradients and optimizer state and should only size a first smoke run.

## Tuning support

Full and frozen ResNet tuning are supported. Automatic LoRA is not supported for
this convolutional encoder. Resetting the head reinitializes the final
classifier but retains the FPN decoder.

## Pretrained source

The configured ImageNet encoder is
[`smp-hub/resnet50.imagenet`](https://huggingface.co/smp-hub/resnet50.imagenet/tree/00cb74e366966d59cd9a35af57e618af9f88efe9)
at revision `00cb74e366966d59cd9a35af57e618af9f88efe9`, as pinned by SMP
0.5.0. FPN and the classifier start fresh. Use `encoder_weights: scratch` only when
scratch training is intended; a failed pretrained request is never downgraded.

## Verified evidence and benchmarks

On 2026-08-12 the exact FPN/ResNet-50 pair loaded its requested ImageNet encoder
and passed four BF16/AdamW steps at batch 2 and 64×64. Losses were finite, the
head changed, and peak allocated CUDA memory was 0.498 GiB.
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py) keeps the
scratch/frozen contract in the normal test suite.

No accuracy number from a common Segmentary protocol exists for this recipe, so no
benchmark is shown. See the [SMP component guide](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 77.08 | 84.11 | 89.05 | 86.29 | 99.74 | 95.87 | 92.34 | 83.73 |
| RailSem19 | 40,000 / 40,000 | 67.70 | 79.81 | 80.05 | 79.81 | 99.36 | 89.07 | 81.17 | 76.12 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 65.34 | 77.34 | 79.44 | 78.09 | 99.29 | 87.81 | 79.25 | 73.32 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 26,118,613 | 99.6 MiB | 399.3 MiB | 156.92 | 6.26 ms | 6.95 ms | 0.73 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 6h 07m 27s | 6.12 | 4.21 GiB | 7.254 |
| RailSem19 | Rail40 standalone | 10h 23m 49s | 10.40 | 4.35 GiB | 6.854 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 5h 13m 08s | 5.22 | 4.35 GiB | 6.816 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 11h 20m 35s | 11.34 | 4.35 GiB | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.06 |
| sidewalk | 84.61 |
| building | 91.91 |
| wall | 50.32 |
| fence | 53.82 |
| pole | 62.14 |
| traffic-light | 69.99 |
| traffic-sign | 79.51 |
| vegetation | 92.14 |
| terrain | 62.96 |
| sky | 94.68 |
| person | 81.04 |
| rider | 58.93 |
| car | 95.07 |
| truck | 78.39 |
| bus | 87.77 |
| train | 79.03 |
| motorcycle | 66.39 |
| bicycle | 77.68 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 59.47 | 58.36 |
| sidewalk | 61.19 | 58.91 |
| construction | 77.14 | 75.89 |
| fence | 54.65 | 52.11 |
| pole | 61.05 | 60.02 |
| traffic-light | 54.61 | 51.86 |
| traffic-sign | 47.97 | 46.49 |
| vegetation | 87.06 | 85.65 |
| terrain | 67.99 | 63.73 |
| sky | 95.83 | 95.10 |
| human | 63.99 | 63.81 |
| car | 79.27 | 79.01 |
| truck | 37.03 | 38.37 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 79.56 | 76.50 |
| rail-track | 89.08 | 85.75 |
| rail-raised | 71.00 | 66.98 |
| rail-embedded | 54.01 | 47.35 |
| tram-track | 71.26 | 64.47 |
| trackbed | 74.13 | 71.05 |

### Provenance

- Model recipe: `configs/models/smp_fpn_resnet50.yaml`
- Source revisions: `a50027d6a72a9146f6302bc1f407e6477a74e8c7, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone raw-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
