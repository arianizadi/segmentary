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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 74.40 | 83.32 | 85.97 | 84.52 | 99.71 | 95.33 | 91.46 | 79.57 |
| RailSem19 | 40,000 / 40,000 | 64.34 | 77.85 | 76.95 | 77.28 | 99.27 | 87.55 | 78.82 | 72.09 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 60.83 | 74.86 | 74.74 | 74.61 | 99.15 | 85.39 | 75.82 | 68.38 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 13,318,654 | 50.8 MiB | 203.8 MiB | 84.66 | 11.79 ms | 11.91 ms | 0.39 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | not retained | not retained | not retained | 6.105 |
| RailSem19 | Rail40 standalone | 12h 38m 53s | 12.65 | 4.96 GiB | 5.695 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 6h 20m 27s | 6.34 | 4.96 GiB | 5.647 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | not retained | not retained | not retained | — |

`not retained` means the exact original training-duration record is no longer available. The validated quality result, final checkpoint, iteration count, and inference evidence are still complete; the model is not retrained only to recreate timing metadata.

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.76 |
| sidewalk | 82.28 |
| building | 91.19 |
| wall | 55.04 |
| fence | 55.99 |
| pole | 53.77 |
| traffic-light | 62.83 |
| traffic-sign | 73.18 |
| vegetation | 91.33 |
| terrain | 60.84 |
| sky | 93.63 |
| person | 78.38 |
| rider | 57.03 |
| car | 94.03 |
| truck | 79.77 |
| bus | 82.82 |
| train | 66.63 |
| motorcycle | 62.62 |
| bicycle | 74.49 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 56.72 | 53.25 |
| sidewalk | 57.68 | 54.80 |
| construction | 74.02 | 70.68 |
| fence | 49.72 | 46.44 |
| pole | 59.25 | 56.47 |
| traffic-light | 48.52 | 48.11 |
| traffic-sign | 42.69 | 40.37 |
| vegetation | 84.99 | 82.62 |
| terrain | 65.48 | 59.85 |
| sky | 94.53 | 93.50 |
| human | 62.22 | 60.59 |
| car | 75.62 | 74.67 |
| truck | 36.92 | 35.96 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 71.09 | 61.14 |
| rail-track | 87.10 | 83.00 |
| rail-raised | 66.09 | 60.29 |
| rail-embedded | 49.29 | 44.21 |
| tram-track | 68.27 | 61.21 |
| trackbed | 72.17 | 68.66 |

### Provenance

- Model recipe: `configs/models/hf_auto_mobilevitv2_deeplabv3.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: The exact total training wall time, GPU-hours, and whole-run peak VRAM were not retained across interruption recovery; the machine record preserves the final post-resume segment separately but does not present it as the total.

<!-- segmentary:generated-city-rail-benchmark:end -->
