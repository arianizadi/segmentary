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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 78.15 | 85.37 | 89.27 | 87.11 | 99.75 | 96.07 | 92.68 | 84.33 |
| RailSem19 | 40,000 / 40,000 | 67.17 | 79.95 | 78.72 | 79.14 | 99.37 | 89.08 | 81.34 | 75.69 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 66.06 | 78.40 | 79.53 | 78.70 | 99.31 | 87.91 | 79.60 | 74.19 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 56,281,941 | 214.7 MiB | 860.4 MiB | 71.01 | 13.70 ms | 17.42 ms | 1.44 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 9h 21m 34s | 9.36 | 6.51 GiB | 6.336 |
| RailSem19 | Rail40 standalone | 12h 55m 26s | 12.92 | 6.70 GiB | 5.483 |
| Cityscapes → RailSem19 | Rail20 adaptation; City40 warm-start provenance not retained | not retained | not retained | not retained | 5.526 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | not retained | not retained | not retained | — |

`not retained` means the exact whole-run wall time, GPU-hours, or peak training-VRAM record is unavailable. The validated quality result, final checkpoint, iteration count, and inference evidence are still complete; the model is not retrained only to recreate resource metadata.

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.95 |
| sidewalk | 83.96 |
| building | 92.63 |
| wall | 52.46 |
| fence | 60.25 |
| pole | 64.74 |
| traffic-light | 72.23 |
| traffic-sign | 81.12 |
| vegetation | 92.45 |
| terrain | 63.70 |
| sky | 95.08 |
| person | 82.43 |
| rider | 64.09 |
| car | 95.41 |
| truck | 80.99 |
| bus | 87.77 |
| train | 69.02 |
| motorcycle | 69.80 |
| bicycle | 78.80 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 59.21 | 56.69 |
| sidewalk | 62.09 | 58.43 |
| construction | 77.73 | 76.24 |
| fence | 55.94 | 53.61 |
| pole | 62.69 | 61.98 |
| traffic-light | 57.29 | 52.81 |
| traffic-sign | 48.07 | 48.21 |
| vegetation | 86.95 | 86.20 |
| terrain | 68.44 | 63.49 |
| sky | 95.83 | 94.59 |
| human | 63.78 | 64.98 |
| car | 80.94 | 79.55 |
| truck | 23.44 | 39.75 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 68.47 | 70.34 |
| rail-track | 89.52 | 87.39 |
| rail-raised | 72.67 | 69.75 |
| rail-embedded | 55.55 | 51.85 |
| tram-track | 72.41 | 66.44 |
| trackbed | 75.14 | 72.76 |

### Provenance

- Model recipe: `configs/models/smp_upernet_resnet101.yaml`
- Source revisions: `57f686737f3aa22db9a92e9880b1862227160dfd, a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: The transfer endpoint is complete, but its City40 source-checkpoint hash was not retained, so the warm-start link cannot be independently audited.

<!-- segmentary:generated-city-rail-benchmark:end -->
