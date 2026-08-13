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
