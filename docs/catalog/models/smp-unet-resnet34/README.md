# U-Net with ResNet-34

Recipe: [`smp_unet_resnet34.yaml`](../../../../configs/models/smp_unet_resnet34.yaml)

## Purpose and architecture

This is the safest general-purpose SMP starting point. A ResNet-34 encoder
produces a five-level feature hierarchy; U-Net upsamples it while fusing
same-scale encoder features through direct skip connections. The decoder and
taxonomy-sized segmentation head start from random weights.

## Pros and cons

| pros | cons |
|---|---|
| familiar architecture; reliable small-data baseline; skip paths preserve detail | high-resolution skip activations increase training memory; global context is limited compared with pyramid-context heads |

## Resource notes

With five output classes this recipe has 24,436,949 parameters. The diagnostic
BF16 batch-1 64×64 forward allocated 110.9 MiB on an NVIDIA L40S. Those are
smoke-test figures, not a production memory estimate; full-resolution training
also stores activations, gradients, and optimizer state.

## Tuning support

Full and frozen-encoder tuning are supported. Segmentary does not advertise LoRA
for the convolutional ResNet encoder. A head reset changes the final
segmentation head, not the whole U-Net decoder.

## Pretrained source

`encoder_weights: imagenet` resolves through SMP 0.5.0 to
[`smp-hub/resnet34.imagenet`](https://huggingface.co/smp-hub/resnet34.imagenet/tree/7a57b34f723329ff020b3f8bc41771163c519d0c)
at revision `7a57b34f723329ff020b3f8bc41771163c519d0c`. Write
`encoder_weights: scratch` for an intentional scratch encoder. A failed load is
fatal; there is no scratch fallback.

## Verified evidence and benchmarks

On 2026-08-12 the exact U-Net/ResNet-34 combination loaded its requested ImageNet
encoder and completed four finite BF16/AdamW steps at batch 2 and 64×64. The
head changed and peak allocated CUDA memory was 0.476 GiB. The repeatable
scratch/frozen contract lives in
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No protocol-comparable accuracy benchmark has been recorded for this recipe, so
none is reported. Tiny synthetic losses and memory probes are not model-quality
benchmarks. See the [SMP component guide](../../components/smp/README.md) for the
shared evidence protocol.

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 73.88 | 81.55 | 87.30 | 83.99 | 99.74 | 95.80 | 92.22 | 80.26 |
| RailSem19 | 40,000 / 40,000 | 61.43 | 73.45 | 76.91 | 74.07 | 99.27 | 87.09 | 78.40 | 72.16 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 59.78 | 70.63 | 78.23 | 73.09 | 99.20 | 85.75 | 76.49 | 69.71 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 24,439,269 | 93.2 MiB | 373.4 MiB | 143.68 | 6.87 ms | 7.37 ms | 0.67 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 6h 17m 00s | 6.28 | 3.65 GiB | 7.503 |
| RailSem19 | 10h 43m 02s | 10.72 | 4.35 GiB | 6.996 |
| Cityscapes → RailSem19 | 5h 21m 19s | 5.36 | 4.36 GiB | 6.829 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.05 |
| sidewalk | 84.43 |
| building | 92.00 |
| wall | 42.52 |
| fence | 56.36 |
| pole | 65.38 |
| traffic-light | 70.23 |
| traffic-sign | 79.13 |
| vegetation | 92.31 |
| terrain | 62.77 |
| sky | 94.43 |
| person | 81.43 |
| rider | 61.30 |
| car | 94.47 |
| truck | 60.38 |
| bus | 77.78 |
| train | 52.62 |
| motorcycle | 61.06 |
| bicycle | 77.06 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 54.40 | 47.70 |
| sidewalk | 58.08 | 49.51 |
| construction | 72.30 | 70.85 |
| fence | 53.15 | 49.74 |
| pole | 62.36 | 60.60 |
| traffic-light | 54.83 | 51.60 |
| traffic-sign | 45.68 | 46.78 |
| vegetation | 85.90 | 84.57 |
| terrain | 64.07 | 60.72 |
| sky | 95.29 | 94.76 |
| human | 63.85 | 63.79 |
| car | 74.89 | 75.81 |
| truck | 12.54 | 13.82 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 27.24 | 44.94 |
| rail-track | 88.37 | 85.18 |
| rail-raised | 69.91 | 65.88 |
| rail-embedded | 47.97 | 42.89 |
| tram-track | 63.96 | 58.22 |
| trackbed | 72.41 | 68.52 |

### Provenance

- Model recipe: `configs/models/smp_unet_resnet34.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
