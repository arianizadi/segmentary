# LinkNet with MobileNetV2

Recipe: [`smp_linknet_mobilenet_v2.yaml`](../../../../configs/models/smp_linknet_mobilenet_v2.yaml)

## Purpose and architecture

This is the latency-conscious shipped recipe. MobileNetV2 supplies efficient
inverted-residual features; LinkNet uses residual encoder-to-decoder links and a
small newly initialized dense head.

## Pros and cons

| pros | cons |
|---|---|
| small parameter count; efficient encoder and decoder; good deployment-oriented baseline | lower decoder and encoder capacity can reduce accuracy on complex scenes |

## Resource notes

At five classes the recipe has 4,319,991 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 23.1 MiB on an NVIDIA L40S. End-to-end latency
and memory must still be measured at the intended resolution and export backend.

## Tuning support

Full and frozen MobileNetV2 tuning are supported. Automatic LoRA is not
supported. Head reset replaces only the final segmentation head.

## Pretrained source

SMP 0.5.0 pins `encoder_weights: imagenet` to
[`smp-hub/mobilenet_v2.imagenet`](https://huggingface.co/smp-hub/mobilenet_v2.imagenet/tree/e67aa804e17f7b404b629127eabbd224c4e0690b)
revision `e67aa804e17f7b404b629127eabbd224c4e0690b`. The LinkNet
decoder is new. Set `encoder_weights: scratch` for scratch; a failed download does
not alter the configured choice.

## Verified evidence and benchmarks

On 2026-08-12 the exact LinkNet/MobileNetV2 pair loaded its requested ImageNet
encoder and passed four finite BF16/AdamW steps at batch 2 and 64×64. Its head
updated and peak allocated CUDA memory was 0.081 GiB. Normal scratch/frozen test
coverage is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No common-protocol accuracy or deployment benchmark has been recorded for this
recipe, so none is claimed. See the
[SMP component guide](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 59.82 | 67.91 | 80.91 | 71.98 | 99.61 | 93.59 | 88.55 | 66.27 |
| RailSem19 | 40,000 / 40,000 | 52.86 | 63.72 | 71.43 | 66.07 | 99.04 | 83.63 | 73.28 | 60.01 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 48.54 | 59.93 | 67.56 | 62.54 | 98.85 | 80.74 | 69.34 | 54.75 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 4,320,519 | 16.5 MiB | 66.6 MiB | 178.77 | 5.53 ms | 6.10 ms | 0.32 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 5h 27m 32s | 5.46 | 3.43 GiB | 7.177 |
| RailSem19 | 9h 59m 29s | 9.99 | 3.82 GiB | 7.407 |
| Cityscapes → RailSem19 | 4h 59m 39s | 4.99 | 3.80 GiB | 7.322 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 96.93 |
| sidewalk | 75.93 |
| building | 88.49 |
| wall | 22.48 |
| fence | 36.59 |
| pole | 44.53 |
| traffic-light | 52.70 |
| traffic-sign | 68.83 |
| vegetation | 90.38 |
| terrain | 38.59 |
| sky | 92.71 |
| person | 69.87 |
| rider | 35.35 |
| car | 90.54 |
| truck | 40.70 |
| bus | 54.48 |
| train | 24.72 |
| motorcycle | 42.01 |
| bicycle | 70.75 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 45.15 | 37.27 |
| sidewalk | 43.45 | 36.49 |
| construction | 64.74 | 59.75 |
| fence | 39.08 | 34.05 |
| pole | 51.41 | 51.24 |
| traffic-light | 45.46 | 43.50 |
| traffic-sign | 40.83 | 38.00 |
| vegetation | 82.67 | 79.07 |
| terrain | 56.28 | 47.03 |
| sky | 93.96 | 93.45 |
| human | 53.51 | 52.42 |
| car | 63.44 | 54.91 |
| truck | 0.00 | 0.00 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 14.82 | 29.12 |
| rail-track | 85.32 | 78.75 |
| rail-raised | 64.07 | 59.12 |
| rail-embedded | 38.43 | 26.78 |
| tram-track | 54.18 | 39.51 |
| trackbed | 67.61 | 61.83 |

### Provenance

- Model recipe: `configs/models/smp_linknet_mobilenet_v2.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
