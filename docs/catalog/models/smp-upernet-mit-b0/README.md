# UPerNet with MiT-B0

Recipe: [`smp_upernet_mit_b0.yaml`](../../../../configs/models/smp_upernet_mit_b0.yaml)

## Purpose and architecture

This is the shipped hybrid transformer-style option. Hierarchical MiT-B0
features feed UPerNet's pyramid-pooling module and feature pyramid before the
new segmentation head. It provides a compact alternative to the separate,
heavier Hugging Face UPerNet/ConvNeXt arm.

## Pros and cons

| pros | cons |
|---|---|
| hierarchical multi-scale encoder; broad pyramid head; modest parameter count | head is heavier than simple decoders; this SMP recipe is not checkpoint-compatible with the Hugging Face UPerNet arm |

## Resource notes

At five classes the recipe has 10,733,413 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 63.4 MiB on an NVIDIA L40S. Real-resolution
training must be measured separately.

## Tuning support

Full and frozen MiT tuning are supported. LoRA is not advertised for the SMP
MiT module layout because it has not passed Segmentary's projection-name and
head-preservation checks. Head reset affects the final segmentation head only.

## Pretrained source

SMP 0.5.0 maps the configured ImageNet tag to
[`smp-hub/mit_b0.imagenet`](https://huggingface.co/smp-hub/mit_b0.imagenet/tree/9ce53d104d92d75aabb00aae70677aaab67e7c84)
at revision `9ce53d104d92d75aabb00aae70677aaab67e7c84`. UPerNet and its
classifier are fresh. Set `encoder_weights: scratch` deliberately for scratch; a
load failure never changes the run to scratch.

## Verified evidence and benchmarks

On 2026-08-12 the exact UPerNet/MiT-B0 pair loaded its requested ImageNet encoder
and completed four finite BF16/AdamW steps at batch 2 and 64×64. The head
changed and peak allocated CUDA memory was 0.224 GiB. The repeatable
scratch/frozen check is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No same-protocol accuracy result exists for this recipe. Do not compare its
smoke memory with a differently sized model as a throughput benchmark. See the
[SMP component guide](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 75.74 | 83.53 | 87.96 | 85.49 | 99.74 | 95.79 | 92.22 | 81.30 |
| RailSem19 | 40,000 / 40,000 | 66.85 | 79.70 | 78.62 | 79.10 | 99.36 | 89.07 | 81.12 | 74.69 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 65.11 | 77.32 | 78.88 | 77.91 | 99.28 | 87.84 | 79.23 | 72.64 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 10,737,525 | 41.0 MiB | 164.2 MiB | 54.28 | 18.39 ms | 18.66 ms | 1.09 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 10h 21m 56s | 10.37 | 6.67 GiB | 6.122 |
| RailSem19 | Rail40 standalone | 14h 35m 12s | 14.59 | 6.69 GiB | 4.895 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 7h 13m 36s | 7.23 | 6.70 GiB | 4.846 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 17h 35m 32s | 17.59 | 6.70 GiB | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.91 |
| sidewalk | 83.53 |
| building | 92.10 |
| wall | 61.38 |
| fence | 57.83 |
| pole | 59.92 |
| traffic-light | 70.03 |
| traffic-sign | 78.29 |
| vegetation | 92.10 |
| terrain | 61.50 |
| sky | 94.43 |
| person | 80.29 |
| rider | 58.26 |
| car | 94.70 |
| truck | 77.88 |
| bus | 80.71 |
| train | 57.46 |
| motorcycle | 63.98 |
| bicycle | 76.82 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 58.73 | 54.77 |
| sidewalk | 59.66 | 57.03 |
| construction | 77.86 | 75.38 |
| fence | 54.45 | 52.25 |
| pole | 60.32 | 60.27 |
| traffic-light | 50.09 | 51.58 |
| traffic-sign | 45.83 | 46.16 |
| vegetation | 86.87 | 85.33 |
| terrain | 68.60 | 64.80 |
| sky | 95.54 | 95.24 |
| human | 62.79 | 62.85 |
| car | 77.23 | 78.75 |
| truck | 34.99 | 39.24 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 78.08 | 76.37 |
| rail-track | 88.91 | 86.21 |
| rail-raised | 72.14 | 68.96 |
| rail-embedded | 53.46 | 48.87 |
| tram-track | 69.98 | 60.94 |
| trackbed | 74.63 | 72.08 |

### Provenance

- Model recipe: `configs/models/smp_upernet_mit_b0.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone ema-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
