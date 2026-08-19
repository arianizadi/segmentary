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

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 31.46 | 39.92 | 78.84 | 43.99 | 98.21 | 67.58 | 63.85 | 38.88 |
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 11.86 | 18.01 | 61.63 | 19.44 | 96.07 | 29.80 | 18.46 | 13.57 |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class recorded raw/EMA endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 9h 38m 35s | 9.64 | 5.24 GiB | 7.262 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | 6h 36m 03s | 6.60 | 5.55 GiB | 7.073 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 86.09 |
| sidewalk | 49.41 |
| building | 58.39 |
| wall | 2.57 |
| fence | 9.81 |
| pole | 16.69 |
| traffic-light | 25.62 |
| traffic-sign | 36.73 |
| vegetation | 49.83 |
| terrain | 22.97 |
| sky | 30.88 |
| person | 27.92 |
| rider | 12.94 |
| car | 72.21 |
| truck | 30.72 |
| bus | 18.90 |
| train | 8.53 |
| motorcycle | 10.59 |
| bicycle | 26.86 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | — | 22.43 |
| sidewalk | — | 5.38 |
| construction | — | 16.75 |
| fence | — | 7.42 |
| pole | — | 4.88 |
| traffic-light | — | 1.59 |
| traffic-sign | — | 2.00 |
| vegetation | — | 21.91 |
| terrain | — | 3.50 |
| sky | — | 19.27 |
| human | — | 0.74 |
| car | — | 23.33 |
| truck | — | 0.00 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | — | 28.97 |
| rail-track | — | 38.55 |
| rail-raised | — | 3.64 |
| rail-embedded | — | 0.13 |
| tram-track | — | 2.80 |
| trackbed | — | 22.04 |

### Provenance

- Model recipe: `configs/models/hf_auto_mobilenetv2_deeplabv3.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
