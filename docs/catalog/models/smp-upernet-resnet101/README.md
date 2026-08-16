# UPerNet with ResNet-101

Recipe: [`smp_upernet_resnet101.yaml`](../../../../configs/models/smp_upernet_resnet101.yaml)

## Purpose and architecture

This is the explicit, provenance-friendly form of the old `upernet_r101`
factory alias. A ResNet-101 encoder provides four feature levels; UPerNet adds
pyramid pooling, a feature pyramid, and a new dataset-specific segmentation
head. Only the encoder receives ImageNet weights.

## Pros and cons

| pros | cons |
|---|---|
| conventional multi-scale CNN baseline; dense-CE objective matches the trainer; explicit decoder/encoder/weight fields | ResNet-101 and UPerNet are relatively heavy; decoder and classifier start fresh; convolutional encoder is not supported by automatic attention LoRA |

Use this recipe when you want a transparent ResNet pyramid control or need to
migrate an older `arch: upernet_r101` experiment. Prefer the explicit form for
new results because the resolved config explains the model without knowing
alias-specific `checkpoint` behavior.

## Advanced settings

Full and frozen tuning are supported. Frozen mode keeps the encoder and its
normalization state fixed while training UPerNet. `llrd` must remain `1.0`
because Segmentary does not infer transformer-style block depth from ResNet.
`reset_head` changes only the final segmentation predictor, not the decoder.

Use RGB ImageNet normalization and dimensions divisible by 32. Measure the
intended crop and batch on the target GPU; tiny-smoke memory is not a training
capacity estimate.

## Pretrained source

SMP 0.5.0 resolves `encoder_name: resnet101` with
`encoder_weights: imagenet` through its reviewed encoder-weight catalog. A
failed load is fatal. Set `encoder_weights: scratch` only when scratch training is
intentional and should be recorded as such.

## Evidence and benchmarks

The legacy alias has a real CUDA regression that loads ImageNet ResNet-101 and
checks finite BF16, input-resolution output on a non-square input. The generic
SMP tests exercise UPerNet forward/backward behavior and the frozen
backbone/head contract. These prove compatibility, not accuracy or throughput.

No same-protocol Segmentary accuracy benchmark exists for this recipe. Run the
eight-image overfit check and a short real-data training smoke before a full
experiment. See the [SMP component guide](../../components/smp/README.md), the
[legacy alias page](../builtin-upernet-r101-alias/README.md), and the
[benchmark evidence rules](../../../benchmarks/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 78.57 | 86.12 | 88.99 | 87.40 | 99.76 | 96.10 | 92.74 | 84.42 |
| RailSem19 | 40,000 / 40,000 | 66.82 | 80.55 | 77.80 | 78.89 | 99.37 | 88.85 | 81.03 | 75.38 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 66.06 | 78.40 | 79.53 | 78.70 | 99.31 | 87.91 | 79.60 | 74.19 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 56,281,941 | 214.7 MiB | 860.4 MiB | 72.48 | 13.70 ms | 14.30 ms | 1.44 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 9h 21m 34s | 9.36 | 6.51 GiB | 6.398 |
| RailSem19 | 12h 55m 26s | 12.92 | 6.70 GiB | 5.532 |
| Cityscapes → RailSem19 | — | — | — | 5.526 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.03 |
| sidewalk | 84.26 |
| building | 92.63 |
| wall | 54.44 |
| fence | 60.69 |
| pole | 64.40 |
| traffic-light | 72.20 |
| traffic-sign | 81.22 |
| vegetation | 92.49 |
| terrain | 62.85 |
| sky | 94.96 |
| person | 82.45 |
| rider | 64.50 |
| car | 95.35 |
| truck | 81.57 |
| bus | 88.83 |
| train | 73.46 |
| motorcycle | 69.89 |
| bicycle | 78.67 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 59.77 | 56.69 |
| sidewalk | 61.56 | 58.43 |
| construction | 77.73 | 76.24 |
| fence | 56.09 | 53.61 |
| pole | 63.24 | 61.98 |
| traffic-light | 56.60 | 52.81 |
| traffic-sign | 46.99 | 48.21 |
| vegetation | 86.43 | 86.20 |
| terrain | 67.81 | 63.49 |
| sky | 95.77 | 94.59 |
| human | 64.25 | 64.98 |
| car | 80.05 | 79.55 |
| truck | 22.99 | 39.75 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 68.86 | 70.34 |
| rail-track | 88.51 | 87.39 |
| rail-raised | 72.12 | 69.75 |
| rail-embedded | 54.62 | 51.85 |
| tram-track | 71.70 | 66.44 |
| trackbed | 74.54 | 72.76 |

### Provenance

- Model recipe: `configs/models/smp_upernet_resnet101.yaml`
- Source revisions: `57f686737f3aa22db9a92e9880b1862227160dfd, db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: —; Cityscapes: —; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
