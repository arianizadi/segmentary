# U-Net++ with EfficientNet-B0

Recipe: [`smp_unetplusplus_efficientnet_b0.yaml`](../../../../configs/models/smp_unetplusplus_efficientnet_b0.yaml)

## Purpose and architecture

Use this when boundary refinement is important but the encoder should remain
compact. EfficientNet-B0 supplies multi-resolution features; U-Net++ uses nested,
dense skip pathways to reduce the semantic gap between encoder and decoder
features. The decoder and final classifier are newly initialized.

## Pros and cons

| pros | cons |
|---|---|
| compact encoder; dense skip fusion can help fine structures | more decoder connections and compute than U-Net; nested skips increase implementation complexity |

## Resource notes

With five classes this recipe has 6,570,161 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 38.7 MiB on an NVIDIA L40S. Real crop sizes,
batches, backward activations, and optimizer state will be much larger.

## Tuning support

Full and frozen-encoder tuning are supported. LoRA is not a verified tuning mode
for this SMP EfficientNet implementation. Head reset affects only the final
segmentation head.
SMP's EfficientNet class retains `_conv_head` and `_bn1` from image
classification, but its segmentation feature forward never calls them. The
recipe lists and freezes those exact modules; all other loss-reachable
parameters remain trainable in `full` mode.

## Pretrained source

`encoder_weights: imagenet` selects
[`smp-hub/efficientnet-b0.imagenet`](https://huggingface.co/smp-hub/efficientnet-b0.imagenet/tree/1bbe7ecc1d5ea1d2058de1a2db063b8701aff314)
at SMP-pinned revision `1bbe7ecc1d5ea1d2058de1a2db063b8701aff314`.
The U-Net++ decoder is not pretrained. Set the weight field to `scratch` explicitly
for scratch; load failures do not trigger a fallback.

## Verified evidence and benchmarks

On 2026-08-12 the exact U-Net++/EfficientNet-B0 combination loaded its requested
ImageNet encoder and completed four finite BF16/AdamW steps at batch 2 and
64×64. The head changed and peak allocated CUDA memory was 0.135 GiB. The
permanent scratch/frozen contract test is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

There is no protocol-comparable accuracy result for this recipe yet. The smoke
numbers must not be compared as accuracy or throughput benchmarks. See the
[SMP component guide](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 72.79 | 80.44 | 87.10 | 83.30 | 99.73 | 95.69 | 92.06 | 77.63 |
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 58.95 | 70.84 | 75.76 | 72.26 | 99.15 | 85.67 | 76.03 | 67.17 |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class recorded raw/EMA endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 9h 42m 08s | 9.70 | 5.65 GiB | 5.718 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | 6h 39m 56s | 6.67 | 6.19 GiB | 5.380 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.04 |
| sidewalk | 84.34 |
| building | 92.01 |
| wall | 58.65 |
| fence | 56.86 |
| pole | 60.87 |
| traffic-light | 67.94 |
| traffic-sign | 78.02 |
| vegetation | 91.87 |
| terrain | 61.43 |
| sky | 94.65 |
| person | 80.42 |
| rider | 58.89 |
| car | 93.91 |
| truck | 60.62 |
| bus | 70.85 |
| train | 48.62 |
| motorcycle | 50.75 |
| bicycle | 74.34 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | — | 49.93 |
| sidewalk | — | 53.12 |
| construction | — | 70.59 |
| fence | — | 48.11 |
| pole | — | 57.85 |
| traffic-light | — | 47.83 |
| traffic-sign | — | 42.40 |
| vegetation | — | 83.90 |
| terrain | — | 59.42 |
| sky | — | 94.62 |
| human | — | 60.90 |
| car | — | 73.83 |
| truck | — | 8.49 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | — | 50.94 |
| rail-track | — | 84.03 |
| rail-raised | — | 65.73 |
| rail-embedded | — | 43.75 |
| tram-track | — | 57.82 |
| trackbed | — | 66.88 |

### Provenance

- Model recipe: `configs/models/smp_unetplusplus_efficientnet_b0.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
