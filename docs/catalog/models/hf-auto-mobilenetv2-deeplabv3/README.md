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
| PyTorch BatchNorm momentum | `0.003` |

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
losses and gradients were finite. The later BF16 strict audit froze only the
declared terminal projection, verified every remaining trainable gradient, and
updated the classifier. Comparable campaign measurements appear below.

The upstream checkpoint constructs 55 PyTorch BatchNorm modules with
`momentum=0.997`, apparently carrying TensorFlow's running-stat decay into
PyTorch's opposite convention. That makes evaluation statistics follow almost
only the last micro-batch. This recipe explicitly uses `0.003`, the equivalent
PyTorch batch contribution, so running statistics accumulate during training.
Historical weights trained before this recipe correction were evaluated only
after a training-only running-stat recalibration that changed zero learned
parameters. It used 2,968 of 2,975 Cityscapes training images and all 6,800
RailSem19 training images; machine records retain the correction provenance.

## Advanced settings

- Keep per-device batch at least 2 unless SyncBatchNorm supplies the missing
  statistics across ranks.
- Do not remove `batch_norm_momentum: 0.003`; it corrects the pinned upstream
  checkpoint's TensorFlow-versus-PyTorch momentum convention mismatch.
- Try frozen tuning first on very small datasets, then compare full tuning.
- Benchmark exported ONNX/TensorRT on the actual target device before making a
  speed claim.
- The source backbone's terminal `mobilenet_v2.conv_1x1` projection is bypassed
  by this DeepLab feature tap. It is explicitly frozen as loss-unreachable;
  every other parameter remains trainable in `full` mode.

See the [Hugging Face component contract](../../components/hf-auto/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 67.74 | 75.15 | 85.40 | 79.26 | 99.67 | 94.73 | 90.34 | 73.48 |
| RailSem19 | 40,000 / 40,000 | 57.93 | 70.66 | 73.63 | 71.20 | 99.17 | 85.77 | 76.36 | 65.87 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 53.29 | 66.16 | 72.60 | 67.24 | 98.99 | 82.64 | 72.05 | 61.24 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class raw endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 2,525,717 | 9.6 MiB | 36.0 MiB | 166.66 | 5.96 ms | 6.59 ms | 0.45 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 9h 38m 35s | 9.64 | 5.24 GiB | 7.287 |
| RailSem19 | Rail40 standalone | not retained | not retained | not retained | 7.069 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 6h 36m 03s | 6.60 | 5.55 GiB | 7.159 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 16h 14m 38s | 16.24 | 5.55 GiB | — |

`not retained` means the exact whole-run wall time, GPU-hours, or peak training-VRAM record is unavailable. The validated quality result, final checkpoint, iteration count, and inference evidence are still complete; the model is not retrained only to recreate resource metadata.

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.36 |
| sidewalk | 80.08 |
| building | 90.16 |
| wall | 36.99 |
| fence | 41.13 |
| pole | 55.61 |
| traffic-light | 62.37 |
| traffic-sign | 72.80 |
| vegetation | 91.06 |
| terrain | 55.61 |
| sky | 93.42 |
| person | 76.46 |
| rider | 50.39 |
| car | 92.83 |
| truck | 59.14 |
| bus | 62.93 |
| train | 50.82 |
| motorcycle | 45.04 |
| bicycle | 72.87 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 50.53 | 46.09 |
| sidewalk | 46.37 | 42.39 |
| construction | 71.30 | 66.28 |
| fence | 44.05 | 41.52 |
| pole | 55.59 | 52.95 |
| traffic-light | 42.19 | 40.28 |
| traffic-sign | 41.35 | 38.80 |
| vegetation | 83.88 | 81.15 |
| terrain | 61.26 | 53.20 |
| sky | 94.33 | 93.38 |
| human | 57.07 | 57.21 |
| car | 65.75 | 65.84 |
| truck | 5.81 | 2.08 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 61.32 | 52.03 |
| rail-track | 85.11 | 76.55 |
| rail-raised | 65.10 | 58.33 |
| rail-embedded | 40.53 | 37.97 |
| tram-track | 59.69 | 44.77 |
| trackbed | 69.54 | 61.67 |

### Provenance

- Model recipe: `configs/models/hf_auto_mobilenetv2_deeplabv3.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Before evaluation, 55 BatchNorm running-statistics buffers were recalibrated on the protocol's training split to correct an imported momentum-convention error; no learned parameter or validation image was used. The reported raw mIoU changed from 11.86 to 53.29.
- Caveat: Before evaluation, 55 BatchNorm running-statistics buffers were recalibrated on the protocol's training split to correct an imported momentum-convention error; no learned parameter or validation image was used. The reported raw mIoU changed from 14.36 to 57.93.
- Caveat: Before evaluation, 55 BatchNorm running-statistics buffers were recalibrated on the protocol's training split to correct an imported momentum-convention error; no learned parameter or validation image was used. The reported raw mIoU changed from 31.46 to 67.74.
- Caveat: The exact total training wall time, GPU-hours, and whole-run peak VRAM were not retained across interruption recovery; the machine record preserves the final post-resume segment separately but does not present it as the total.
- Caveat: Transfer warm-started from the pre-recalibration Cityscapes checkpoint; only BatchNorm buffers differ from the published Cityscapes endpoint. Training-mode BatchNorm uses batch statistics, so those initial buffers did not affect gradient calculations; the transfer endpoint received its own disclosed recalibration before evaluation.

<!-- segmentary:generated-city-rail-benchmark:end -->
