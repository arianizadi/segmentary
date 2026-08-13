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
