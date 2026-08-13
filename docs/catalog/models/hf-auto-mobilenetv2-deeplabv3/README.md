# MobileNetV2 + DeepLabV3

Use [`hf_auto_mobilenetv2_deeplabv3.yaml`](../../../../configs/models/hf_auto_mobilenetv2_deeplabv3.yaml)
for the smallest conventional CNN baseline in the audited Hugging Face catalog.

## What it is

MobileNetV2 uses inverted residual blocks and depthwise convolutions to reduce
compute. Its semantic head uses atrous spatial pyramid pooling to collect
context at several dilation rates. The complete source checkpoint was trained
for 21-class Pascal VOC segmentation.

| item | value |
|---|---|
| checkpoint | [`google/deeplabv3_mobilenet_v2_1.0_513`](https://huggingface.co/google/deeplabv3_mobilenet_v2_1.0_513) |
| pinned revision | `5282e0eaf10de7cc7f35ee5e40f47981b801bf63` |
| source task | Pascal VOC, 21 classes, 513×513 recipe |
| source preprocessing | RGB, mean/std `(0.5, 0.5, 0.5)`, `1/255` rescale |
| Segmentary parameters with 19 classes | 2,525,203 |

## Why choose it

Pros:

- very small model and quick iteration;
- good diagnostic for whether a complex model is necessary;
- conventional CNN operations are generally deployment-friendly;
- full and frozen tuning are supported.

Cons:

- lower capacity than desktop backbones;
- the pooled BatchNorm branch needs at least two values while training: use
  batch 2 or synchronized multi-GPU BatchNorm;
- ordinary convolution layers are not the attention projections expected by
  Segmentary's LoRA path;
- small parameter count does not automatically imply best device latency.

## Verified Segmentary evidence

The pinned real checkpoint passed strict loading and five FP32 AdamW steps on an
L40S at batch 2 / 128×128. It used 0.188 GiB peak allocated CUDA memory; all
losses and gradients were finite. This is not a latency or accuracy benchmark,
and no comparable Segmentary mIoU has been measured for this recipe.
The later BF16 strict audit froze only the declared terminal projection,
verified every remaining trainable gradient, and updated the classifier.

## Advanced settings

- Keep per-device batch at least 2 unless SyncBatchNorm supplies the missing
  statistics across ranks.
- Try frozen tuning first on very small datasets, then compare full tuning.
- Benchmark exported ONNX/TensorRT on the actual target device before making a
  speed claim.
- The source backbone's terminal `mobilenet_v2.conv_1x1` projection is bypassed
  by this DeepLab feature tap. It is explicitly frozen as loss-unreachable;
  every other parameter remains trainable in `full` mode.

See the [Hugging Face component contract](../../components/hf-auto/README.md).
