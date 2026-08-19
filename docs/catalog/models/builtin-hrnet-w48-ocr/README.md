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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 80.75 | 87.16 | 90.83 | 88.84 | 99.78 | 96.44 | 93.34 | 86.86 |
| RailSem19 | 40,000 / 40,000 | 68.52 | 80.45 | 80.50 | 80.08 | 99.39 | 89.53 | 81.94 | 78.20 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 66.03 | 78.92 | 78.57 | 78.31 | 99.33 | 88.43 | 80.28 | 75.04 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 73,168,490 | 279.1 MiB | 1119.2 MiB | 30.75 | 32.11 ms | 34.73 ms | 1.26 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 19h 14m 44s | 19.25 | 17.35 GiB | 4.784 |
| RailSem19 | Rail40 standalone | 27h 48m 14s | 27.80 | 17.35 GiB | 3.676 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 13h 54m 23s | 13.91 | 17.35 GiB | 3.628 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 33h 09m 07s | 33.15 | 17.35 GiB | — |

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
| road | 61.35 | 60.05 |
| sidewalk | 63.30 | 61.01 |
| construction | 79.01 | 77.04 |
| fence | 58.47 | 56.61 |
| pole | 64.45 | 64.18 |
| traffic-light | 55.77 | 55.27 |
| traffic-sign | 52.62 | 48.25 |
| vegetation | 87.04 | 86.53 |
| terrain | 69.63 | 66.66 |
| sky | 95.21 | 94.28 |
| human | 66.29 | 65.77 |
| car | 83.02 | 81.94 |
| truck | 21.74 | 23.01 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 70.86 | 63.02 |
| rail-track | 90.92 | 88.38 |
| rail-raised | 74.95 | 70.03 |
| rail-embedded | 56.94 | 50.10 |
| tram-track | 74.68 | 68.84 |
| trackbed | 75.53 | 73.51 |

### Provenance

- Model recipe: `configs/models/hrnet_w48_ocr.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, a50027d6a72a9146f6302bc1f407e6477a74e8c7, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone raw-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
