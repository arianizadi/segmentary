# MobileViT XXS + DeepLabV3

Use [`hf_auto_mobilevit_xxs_deeplabv3.yaml`](../../../../configs/models/hf_auto_mobilevit_xxs_deeplabv3.yaml)
when you want a very small convolution/attention hybrid rather than a pure CNN.

## What it is

MobileViT mixes MobileNet-style local convolutions with transformer blocks for
global context, then applies a DeepLabV3 head. It has no positional embeddings.
The complete source checkpoint was trained for Pascal VOC segmentation.

| item | value |
|---|---|
| checkpoint | [`apple/deeplabv3-mobilevit-xx-small`](https://huggingface.co/apple/deeplabv3-mobilevit-xx-small) |
| pinned revision | `2bece0a6464b15913c1f2c82cb5ab11bc5b7b3ad` |
| source task | Pascal VOC, 21 classes, 512×512 fine-tuning |
| source preprocessing | **BGR**, `1/255` rescale, no subsequent normalization |
| Segmentary parameters with 19 classes | 1,854,339 |

## Why choose it

Pros:

- smallest parameter count in the current HF catalog;
- combines local image bias with global attention;
- useful mobile-oriented comparison against MobileNetV2;
- full, frozen, and compatible attention-LoRA tuning are available.

Cons:

- low capacity limits the likely ceiling on difficult domains;
- BatchNorm favors batch 2 or synchronized multi-GPU statistics;
- its processor expects BGR. An RGB-only pipeline silently changes its input
  distribution; Segmentary audits and reproduces the channel flip;
- mobile-oriented design still needs target-device latency measurement.

## Benchmarks and verified evidence

The upstream model card reports Pascal VOC quality and model-size evidence.
That number uses the upstream VOC protocol and must not be compared directly to
Cityscapes, RailSem19, or a different label space.

Segmentary's pinned checkpoint passed five FP32 AdamW steps on one L40S at batch 2
/ 128×128, using 0.080 GiB peak allocated CUDA memory. All losses and gradients
were finite. This smoke is not a Segmentary accuracy or latency benchmark.
The later BF16 strict audit also reproduced the BGR processor pixels, verified
every trainable tensor received a finite gradient, and updated the classifier.

## Advanced settings

- Do not override the recorded BGR processor contract unless the checkpoint
  itself changes.
- Use LoRA only after checking inferred target coverage and head gradients.
- Benchmark both this recipe and MobileNetV2 on the deployment device; parameter
  count alone cannot decide real latency.

See the [Hugging Face component contract](../../components/hf-auto/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 69.99 | 79.65 | 83.25 | 81.25 | 99.67 | 94.64 | 90.29 | 74.97 |
| RailSem19 | 40,000 / 40,000 | 60.72 | 75.08 | 73.43 | 74.13 | 99.21 | 86.49 | 77.34 | 67.78 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 58.02 | 72.31 | 72.83 | 72.20 | 99.10 | 84.59 | 74.64 | 64.76 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 1,854,853 | 7.1 MiB | 28.9 MiB | 34.78 | 28.67 ms | 29.04 ms | 3.30 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 18h 40m 27s | 18.67 | 15.78 GiB | 4.686 |
| RailSem19 | 22h 28m 15s | 22.47 | 15.78 GiB | 3.691 |
| Cityscapes → RailSem19 | 11h 14m 52s | 11.25 | 15.78 GiB | 3.677 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.39 |
| sidewalk | 79.55 |
| building | 90.11 |
| wall | 53.67 |
| fence | 50.79 |
| pole | 47.79 |
| traffic-light | 53.62 |
| traffic-sign | 67.46 |
| vegetation | 90.60 |
| terrain | 56.51 |
| sky | 92.87 |
| person | 74.72 |
| rider | 48.93 |
| car | 92.44 |
| truck | 71.23 |
| bus | 76.93 |
| train | 61.81 |
| motorcycle | 53.69 |
| bicycle | 69.64 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 53.43 | 49.65 |
| sidewalk | 51.97 | 48.78 |
| construction | 72.85 | 71.13 |
| fence | 47.49 | 44.03 |
| pole | 55.13 | 54.59 |
| traffic-light | 43.95 | 44.09 |
| traffic-sign | 33.20 | 33.95 |
| vegetation | 84.06 | 82.29 |
| terrain | 63.14 | 58.45 |
| sky | 94.41 | 93.85 |
| human | 58.27 | 59.49 |
| car | 70.69 | 72.30 |
| truck | 27.87 | 37.03 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 72.77 | 62.19 |
| rail-track | 85.22 | 78.98 |
| rail-raised | 63.21 | 56.40 |
| rail-embedded | 44.51 | 38.59 |
| tram-track | 61.12 | 50.77 |
| trackbed | 70.32 | 65.89 |

### Provenance

- Model recipe: `configs/models/hf_auto_mobilevit_xxs_deeplabv3.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
