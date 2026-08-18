# PSPNet with MobileNetV2

Recipe: [`smp_pspnet_mobilenet_v2.yaml`](../../../../configs/models/smp_pspnet_mobilenet_v2.yaml)

## Purpose and architecture

Use this as a small model with explicit global context. MobileNetV2 is the
efficient encoder; PSPNet pools its deepest features at several spatial scales
before a newly initialized segmentation classifier.

## Pros and cons

| pros | cons |
|---|---|
| smallest shipped SMP recipe; global pyramid context; useful for constrained experiments | limited encoder capacity; pooled context can soften precise boundaries |

## Resource notes

At five classes this recipe has 2,281,789 parameters. The diagnostic BF16
batch-1 64×64 GPU forward allocated 17.7 MiB on an NVIDIA L40S, the lowest
small-input allocation in this catalog. Do not extrapolate that number directly
to full-resolution training.

## Tuning support

Full and frozen MobileNetV2 tuning are supported. Automatic LoRA is not supported
for this convolutional encoder. Head reset retains the PSP decoder and replaces
the final segmentation classifier.
This PSPNet constructor requests a shallow MobileNet feature depth. SMP retains
later `encoder.features.7` through `.18` modules in the object but does not call
them; the recipe explicitly freezes those exact paths so strict DDP still
detects any other disconnected branch.

## Pretrained source

`encoder_weights: imagenet` maps to
[`smp-hub/mobilenet_v2.imagenet`](https://huggingface.co/smp-hub/mobilenet_v2.imagenet/tree/e67aa804e17f7b404b629127eabbd224c4e0690b)
at revision `e67aa804e17f7b404b629127eabbd224c4e0690b`. SMP 0.5.0 pins
that source; the PSP decoder is fresh. `scratch` is the deliberate scratch option,
and no fallback hides download failures.

## Verified evidence and benchmarks

On 2026-08-12 the exact PSPNet/MobileNetV2 recipe loaded its requested ImageNet
encoder and completed four finite BF16/AdamW steps at batch 2 and 64×64. The
head changed and peak allocated CUDA memory was 0.033 GiB. See
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py) for the
repeatable scratch/frozen backward check.

No same-protocol accuracy benchmark has been run for this recipe. Parameter and
smoke-memory figures are not an accuracy claim. See the
[SMP component guide](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 46.87 | 55.61 | 68.00 | 58.28 | 99.39 | 90.39 | 83.44 | 53.34 |
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
| Cityscapes | 4h 11m 01s | 4.18 | 2.67 GiB | 8.008 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 94.12 |
| sidewalk | 62.36 |
| building | 82.91 |
| wall | 21.64 |
| fence | 33.61 |
| pole | 33.31 |
| traffic-light | 36.26 |
| traffic-sign | 49.44 |
| vegetation | 87.36 |
| terrain | 48.65 |
| sky | 89.32 |
| person | 55.14 |
| rider | 9.61 |
| car | 81.71 |
| truck | 11.42 |
| bus | 28.51 |
| train | 8.20 |
| motorcycle | 3.14 |
| bicycle | 53.82 |

### Provenance

- Model recipe: `configs/models/smp_pspnet_mobilenet_v2.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0.
- Quality evaluation weights: Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
