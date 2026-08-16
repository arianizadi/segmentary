# Built-in HRNet-W48 with OCR

Use [`hrnet_w48_ocr.yaml`](../../../../configs/models/hrnet_w48_ocr.yaml) for a
legacy high-resolution CNN comparison with an Object-Contextual Representations
head.

## What it is

The backbone is timm's ImageNet-pretrained HRNet-W48. Unlike an ordinary encoder
that repeatedly downsamples one stream, HRNet keeps four resolution branches in
parallel. Segmentary removes timm's classification-only modules, upsamples the four
branches to the finest feature resolution, concatenates them, and feeds them to
the local OCR head.

OCR first predicts soft class regions, pools an object representation for each
region, lets every pixel attend to those representations, and classifies the
refined features.

## OCR supervision

Training applies an explicit `0.4`-weighted auxiliary loss to the full-resolution
coarse OCR logits. Public inference still returns only the refined logits, so the
extra prediction is used for deep supervision without changing deployment or
evaluation output.

Pros:

- preserves high-resolution features for thin structures and boundaries;
- useful convolutional legacy comparison against transformer models;
- local OCR implementation is readable and covered without adding another
  segmentation framework as a runtime dependency.

Cons:

- large W48 backbone and high-resolution activations;
- the auxiliary OCR objective increases training memory and computation;
- export has not been validated;
- no same-protocol Segmentary dataset-quality benchmark is recorded.

## Settings and checkpoints

Full and frozen tuning are supported. Automatic LoRA target discovery is not a
default for HRNet; an explicit convolution target is an advanced experiment and
needs its own gradient proof. `drop_path` is rejected because timm HRNet does
not implement the option even though it can silently accept an unused keyword.

The factory rejects `model.checkpoint` for this arm because timm owns the
ImageNet weight selection. To load a Segmentary-trained model, use the curriculum
stage's `init_from` field. `reset_head` resets the final classifier and the
coarse class predictor while keeping class-agnostic OCR attention.

Use RGB ImageNet normalization and crop sizes divisible by 32. Begin with a
smaller crop/batch smoke, then measure intended-crop memory.

## Verified evidence

Unit and gradient regressions exercise the local OCR arithmetic, multi-scale
concatenation, reset behavior, and a smaller HRNet variant through the same code
path. This is implementation evidence, not W48 accuracy evidence. No benchmark
number is claimed until a complete result record exists.

See the [built-in model component](../../components/builtin-models/README.md)
and [`hrnet_ocr.py`](../../../../src/segmentary/models/hrnet_ocr.py).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 80.75 | 87.16 | 90.83 | 88.84 | 99.78 | 96.44 | 93.34 | 86.86 |
| RailSem19 | 40,000 / 40,000 | 68.62 | 80.86 | 80.14 | 80.21 | 99.39 | 89.42 | 81.86 | 78.23 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 73,168,490 | 279.1 MiB | 1119.2 MiB | 29.24 | 33.89 ms | 36.02 ms | 1.26 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | 4.784 |
| RailSem19 | 27h 48m 14s | 27.80 | 17.35 GiB | 3.529 |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.35 |
| sidewalk | 86.11 |
| building | 93.20 |
| wall | 58.42 |
| fence | 63.46 |
| pole | 67.06 |
| traffic-light | 73.92 |
| traffic-sign | 82.60 |
| vegetation | 92.80 |
| terrain | 64.58 |
| sky | 95.10 |
| person | 84.17 |
| rider | 68.22 |
| car | 95.58 |
| truck | 80.65 |
| bus | 92.04 |
| train | 87.16 |
| motorcycle | 70.82 |
| bicycle | 79.98 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 61.80 | — |
| sidewalk | 62.78 | — |
| construction | 78.87 | — |
| fence | 58.53 | — |
| pole | 63.99 | — |
| traffic-light | 56.43 | — |
| traffic-sign | 52.48 | — |
| vegetation | 86.94 | — |
| terrain | 69.81 | — |
| sky | 94.81 | — |
| human | 65.61 | — |
| car | 82.60 | — |
| truck | 23.22 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 72.47 | — |
| rail-track | 90.97 | — |
| rail-raised | 74.89 | — |
| rail-embedded | 56.90 | — |
| tram-track | 75.04 | — |
| trackbed | 75.69 | — |

### Provenance

- Model recipe: `configs/models/hrnet_w48_ocr.yaml`
- Source revisions: `a50027d6a72a9146f6302bc1f407e6477a74e8c7, db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: RailSem19: 0; Cityscapes: 0.
- Quality evaluation weights: RailSem19: —; Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone raw-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
