# MA-Net with EfficientNet-B0

Recipe: [`smp_manet_efficientnet_b0.yaml`](../../../../configs/models/smp_manet_efficientnet_b0.yaml)

## Purpose and architecture

Use this recipe to test whether decoder attention helps multi-scale segmentation
without using a large encoder. EfficientNet-B0 provides the hierarchy; MA-Net
adds position-wise and multi-scale attention before the fresh classifier.

## Pros and cons

| pros | cons |
|---|---|
| compact encoder; explicit attention across feature scales; useful architectural contrast | more decoder complexity than skip-only designs; attention benefit is dataset-dependent |

## Resource notes

With five classes the model has 9,092,937 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 48.6 MiB on an NVIDIA L40S. That tiny inference
probe does not predict real training memory or speed.

## Tuning support

Full and frozen EfficientNet tuning are supported. Segmentary does not advertise
LoRA for this SMP encoder/decoder layout. Head reset reinitializes only the
segmentation head.
SMP's EfficientNet class retains `_conv_head` and `_bn1` from image
classification, but its segmentation feature forward never calls them. The
recipe lists and freezes those exact modules; all other loss-reachable
parameters remain trainable in `full` mode.

## Pretrained source

The ImageNet encoder source is
[`smp-hub/efficientnet-b0.imagenet`](https://huggingface.co/smp-hub/efficientnet-b0.imagenet/tree/1bbe7ecc1d5ea1d2058de1a2db063b8701aff314)
at revision `1bbe7ecc1d5ea1d2058de1a2db063b8701aff314`, pinned by SMP
0.5.0. The MA-Net decoder starts from random weights. Use `scratch` explicitly for
scratch; pretraining failures are not hidden.

## Verified evidence and benchmarks

On 2026-08-12 the exact MA-Net/EfficientNet-B0 configuration loaded its requested
ImageNet encoder and completed four finite BF16/AdamW steps at batch 2 and
64×64. The head changed and peak allocated CUDA memory was 0.183 GiB. The
repeatable scratch/frozen contract is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No protocol-comparable accuracy benchmark has been generated for this recipe.
See the [SMP component guide](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 71.98 | 80.17 | 86.04 | 82.72 | 99.72 | 95.43 | 91.61 | 75.18 |
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
| Cityscapes | 7h 43m 24s | 7.72 | 4.73 GiB | 6.083 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.79 |
| sidewalk | 82.44 |
| building | 91.76 |
| wall | 50.78 |
| fence | 56.29 |
| pole | 60.19 |
| traffic-light | 67.18 |
| traffic-sign | 76.16 |
| vegetation | 91.77 |
| terrain | 59.69 |
| sky | 93.81 |
| person | 79.11 |
| rider | 56.34 |
| car | 93.55 |
| truck | 57.52 |
| bus | 70.70 |
| train | 63.39 |
| motorcycle | 46.21 |
| bicycle | 72.96 |

### Provenance

- Model recipe: `configs/models/smp_manet_efficientnet_b0.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0.
- Quality evaluation weights: Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
