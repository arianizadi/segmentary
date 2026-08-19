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

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 59.82 | 67.91 | 80.91 | 71.98 | 99.61 | 93.59 | 88.55 | 66.27 |
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class recorded raw/EMA endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 5h 27m 32s | 5.46 | 3.43 GiB | 7.177 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

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

### Provenance

- Model recipe: `configs/models/smp_linknet_mobilenet_v2.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0.
- Quality evaluation weights: Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
