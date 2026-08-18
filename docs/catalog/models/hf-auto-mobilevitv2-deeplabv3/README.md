# MobileViTv2 1.0 + DeepLabV3

Use [`hf_auto_mobilevitv2_deeplabv3.yaml`](../../../../configs/models/hf_auto_mobilevitv2_deeplabv3.yaml)
to compare MobileViTv2's separable self-attention against the XXS MobileViT and
MobileNetV2 efficiency baselines.

## What it is

MobileViTv2 replaces MobileViT's multi-head attention with separable
self-attention while retaining the local-convolution/global-context hybrid. A
DeepLabV3 head produces dense Pascal VOC predictions.

| item | value |
|---|---|
| checkpoint | [`apple/mobilevitv2-1.0-voc-deeplabv3`](https://huggingface.co/apple/mobilevitv2-1.0-voc-deeplabv3) |
| pinned revision | `cd9b6a101aefbccb4c3cc1bce0324cfc1de8a4c9` |
| source task | Pascal VOC, 21 classes, 512×512 recipe |
| source preprocessing | **BGR**, `1/255` rescale, no subsequent normalization |
| Segmentary parameters with 19 classes | 13,317,628 |

## Why choose it

Pros:

- mobile-oriented global context with linear-style separable attention;
- useful architecture comparison to MobileViT XXS;
- complete semantic checkpoint;
- full and frozen tuning are supported; LoRA requires an explicit convolutional
  projection target list as described below.

Cons:

- much larger than the XXS recipe despite sharing the mobile family name;
- the source processor requires BGR and must not be replaced by RGB defaults;
- BatchNorm needs a sensible effective batch;
- no comparable Segmentary accuracy benchmark exists yet.

## Verified Segmentary evidence

The pinned checkpoint passed strict loading and five FP32 AdamW steps on one
L40S at batch 2 / 128×128. It used 0.300 GiB peak allocated CUDA memory; all
losses and gradients were finite. The upstream model card provides no semantic
mIoU number that we can verify and quote here.
The later BF16 strict audit also reproduced the BGR processor pixels, verified
every trainable tensor received a finite gradient, and updated the classifier.

## Advanced settings

- Keep BGR preprocessing enabled and recorded in result provenance.
- Compare full and frozen tuning before attributing gains to adaptation.
- Automatic LoRA inference deliberately fails because MobileViTv2 implements
  its attention projections as `Conv2d` leaves rather than the library's known
  `Linear` layouts. Advanced users may test the verified PEFT target names
  `qkv_proj.convolution` and `out_proj.convolution` explicitly:

  ```yaml
  model:
    tuning: lora
    lora_targets: [qkv_proj.convolution, out_proj.convolution]
  ```

  Treat this as a separate experiment and retain a gradient/optimizer smoke for
  the installed Transformers and PEFT versions.

See the [Hugging Face component contract](../../components/hf-auto/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 0 / 40,000 | — | — | — | — | — | — | — | — |
| RailSem19 | 40,000 / 40,000 | 64.34 | 77.85 | 76.95 | 77.28 | 99.27 | 87.55 | 78.82 | 72.09 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 13,318,654 | 50.8 MiB | 203.8 MiB | 84.66 | 11.79 ms | 11.91 ms | 0.39 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | — |
| RailSem19 | 12h 38m 53s | 12.65 | 4.96 GiB | 5.695 |
| Cityscapes → RailSem19 | — | — | — | — |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 56.72 | — |
| sidewalk | 57.68 | — |
| construction | 74.02 | — |
| fence | 49.72 | — |
| pole | 59.25 | — |
| traffic-light | 48.52 | — |
| traffic-sign | 42.69 | — |
| vegetation | 84.99 | — |
| terrain | 65.48 | — |
| sky | 94.53 | — |
| human | 62.22 | — |
| car | 75.62 | — |
| truck | 36.92 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 71.09 | — |
| rail-track | 87.10 | — |
| rail-raised | 66.09 | — |
| rail-embedded | 49.29 | — |
| tram-track | 68.27 | — |
| trackbed | 72.17 | — |

### Provenance

- Model recipe: `configs/models/hf_auto_mobilevitv2_deeplabv3.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0.
- Quality evaluation weights: RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
