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
