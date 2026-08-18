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
| Cityscapes | 0 / 40,000 | — | — | — | — | — | — | — | — |
| RailSem19 | 40,000 / 40,000 | 61.43 | 73.45 | 76.91 | 74.07 | 99.27 | 87.09 | 78.40 | 72.16 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 24,439,269 | 93.2 MiB | 373.4 MiB | 143.68 | 6.87 ms | 7.37 ms | 0.67 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | — |
| RailSem19 | 10h 43m 02s | 10.72 | 4.35 GiB | 6.996 |
| Cityscapes → RailSem19 | — | — | — | — |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 54.40 | — |
| sidewalk | 58.08 | — |
| construction | 72.30 | — |
| fence | 53.15 | — |
| pole | 62.36 | — |
| traffic-light | 54.83 | — |
| traffic-sign | 45.68 | — |
| vegetation | 85.90 | — |
| terrain | 64.07 | — |
| sky | 95.29 | — |
| human | 63.85 | — |
| car | 74.89 | — |
| truck | 12.54 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 27.24 | — |
| rail-track | 88.37 | — |
| rail-raised | 69.91 | — |
| rail-embedded | 47.97 | — |
| tram-track | 63.96 | — |
| trackbed | 72.41 | — |

### Provenance

- Model recipe: `configs/models/smp_unet_resnet34.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0.
- Quality evaluation weights: RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
