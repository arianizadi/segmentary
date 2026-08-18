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

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 75.47 | 83.65 | 87.45 | 85.30 | 99.74 | 95.76 | 92.18 | 81.15 |
| RailSem19 | 40,000 / 40,000 | 66.56 | 80.18 | 77.80 | 78.87 | 99.36 | 89.02 | 81.08 | 74.19 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 65.11 | 77.32 | 78.88 | 77.91 | 99.28 | 87.84 | 79.23 | 72.64 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 10,737,525 | 41.0 MiB | 164.2 MiB | 54.28 | 18.39 ms | 18.66 ms | 1.09 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | 6.043 |
| RailSem19 | 14h 35m 12s | 14.59 | 6.69 GiB | 4.839 |
| Cityscapes → RailSem19 | 7h 13m 36s | 7.23 | 6.70 GiB | 4.846 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.94 |
| sidewalk | 83.72 |
| building | 92.03 |
| wall | 60.36 |
| fence | 58.06 |
| pole | 59.65 |
| traffic-light | 69.44 |
| traffic-sign | 77.78 |
| vegetation | 92.03 |
| terrain | 61.61 |
| sky | 94.34 |
| person | 80.09 |
| rider | 58.43 |
| car | 94.58 |
| truck | 76.74 |
| bus | 80.26 |
| train | 56.29 |
| motorcycle | 63.96 |
| bicycle | 76.59 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 58.60 | 54.77 |
| sidewalk | 59.40 | 57.03 |
| construction | 77.76 | 75.38 |
| fence | 54.79 | 52.25 |
| pole | 60.57 | 60.27 |
| traffic-light | 49.13 | 51.58 |
| traffic-sign | 44.92 | 46.16 |
| vegetation | 86.81 | 85.33 |
| terrain | 68.46 | 64.80 |
| sky | 95.57 | 95.24 |
| human | 61.62 | 62.85 |
| car | 76.70 | 78.75 |
| truck | 34.67 | 39.24 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 77.97 | 76.37 |
| rail-track | 88.84 | 86.21 |
| rail-raised | 72.08 | 68.96 |
| rail-embedded | 52.93 | 48.87 |
| tram-track | 69.21 | 60.94 |
| trackbed | 74.69 | 72.08 |

### Provenance

- Model recipe: `configs/models/smp_upernet_mit_b0.yaml`
- Source revisions: `a50027d6a72a9146f6302bc1f407e6477a74e8c7, b9eb3e1f390b70aad63e78b2e723bd79b5266471, db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: ema; Cityscapes: ema; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone ema-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
