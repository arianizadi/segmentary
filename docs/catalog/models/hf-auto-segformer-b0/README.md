# SegFormer-B0 (Hugging Face complete checkpoint)

Use [`hf_auto_segformer_b0.yaml`](../../../../configs/models/hf_auto_segformer_b0.yaml)
when you want a small transformer baseline whose encoder and ADE20K-trained
decode head both come from one complete checkpoint.

## What it is

SegFormer combines a four-stage hierarchical MiT-B0 transformer encoder with a
small all-MLP decode head. The hierarchy supplies multiple feature resolutions;
the decoder projects and fuses them, then Segmentary resizes logits to the input
resolution. This is a useful middle ground between a plain CNN and a large
transformer.

| item | value |
|---|---|
| checkpoint | [`nvidia/segformer-b0-finetuned-ade-512-512`](https://huggingface.co/nvidia/segformer-b0-finetuned-ade-512-512) |
| pinned revision | `489d5cd81a0b59fab9b7ea758d3548ebe99677da` |
| source task | ADE20K, 150 classes, 512×512 fine-tuning |
| source preprocessing | RGB, ImageNet mean/std, `1/255` rescale |
| Segmentary parameters with 19 classes | 3,719,027 |

## Why choose it

Pros:

- small enough for setup checks and rapid ablations;
- hierarchical features work naturally for dense prediction;
- complete task-finetuned checkpoint, not only an encoder;
- supports full, frozen, and transformer LoRA tuning.

Cons:

- lower capacity than B2/B5, BEiT, or Swin/UPerNet;
- replacing the 150-class classifier means the final layer starts fresh;
- its small size makes it a poor proxy for the memory or speed of larger arms.

## Verified Segmentary evidence

On 2026-08-12, the pinned real checkpoint passed strict loading, processor
reproduction, input-resolution forward, backward, and five AdamW steps on one
L40S. The synthetic proof used batch 2, 128×128 RGB inputs, 19 random labels,
FP32, and reported 0.108 GiB peak allocated CUDA memory. All five losses and
trainable gradients were finite.
The later BF16 strict audit also reproduced processor pixels, verified every
trainable tensor received a finite gradient, and updated the classifier.

This is a compatibility smoke, not an accuracy or throughput benchmark. No
Segmentary dataset mIoU is reported for this exact recipe yet. The upstream model
card also does not give a number directly usable under Segmentary's protocol.

## Advanced settings

- Start with `tuning: full` for a new domain.
- Use `tuning: frozen` as a cheap feature-quality diagnostic.
- Use LoRA only after checking the inferred attention targets in the resolved
  config and gradient report.
- Keep the pinned revision for reproducible runs; change it only as a named
  experiment.
- Use a crop divisible by 32. Production memory grows strongly with crop area.

See the [Hugging Face component contract](../../components/hf-auto/README.md)
and [models and tuning guide](../../../guides/models-and-tuning.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 74.47 | 83.02 | 86.54 | 84.60 | 99.73 | 95.67 | 92.04 | 80.13 |
| RailSem19 | 40,000 / 40,000 | 65.86 | 78.88 | 78.09 | 78.43 | 99.33 | 88.68 | 80.52 | 73.05 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 3,719,541 | 14.2 MiB | 57.1 MiB | 123.43 | 7.57 ms | 10.28 ms | 0.89 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 5h 39m 20s | 5.66 | 3.05 GiB | 8.121 |
| RailSem19 | 9h 48m 13s | 9.80 | 3.24 GiB | 7.567 |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.97 |
| sidewalk | 83.58 |
| building | 91.93 |
| wall | 60.39 |
| fence | 54.72 |
| pole | 59.12 |
| traffic-light | 65.99 |
| traffic-sign | 75.34 |
| vegetation | 92.11 |
| terrain | 61.17 |
| sky | 94.66 |
| person | 78.78 |
| rider | 53.76 |
| car | 94.29 |
| truck | 66.82 |
| bus | 78.21 |
| train | 70.49 |
| motorcycle | 60.59 |
| bicycle | 74.91 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 57.91 | — |
| sidewalk | 58.94 | — |
| construction | 77.00 | — |
| fence | 52.92 | — |
| pole | 60.41 | — |
| traffic-light | 47.86 | — |
| traffic-sign | 43.17 | — |
| vegetation | 86.56 | — |
| terrain | 67.88 | — |
| sky | 95.51 | — |
| human | 60.49 | — |
| car | 74.75 | — |
| truck | 40.59 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 77.78 | — |
| rail-track | 87.99 | — |
| rail-raised | 69.33 | — |
| rail-embedded | 50.65 | — |
| tram-track | 68.07 | — |
| trackbed | 73.54 | — |

### Provenance

- Model recipe: `configs/models/hf_auto_segformer_b0.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0; Cityscapes: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
