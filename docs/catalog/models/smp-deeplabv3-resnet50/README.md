# DeepLabV3 with ResNet-50

Recipe: [`smp_deeplabv3_resnet50.yaml`](../../../../configs/models/smp_deeplabv3_resnet50.yaml)

## Purpose and architecture

This is the atrous-context baseline without the V3+ low-level refinement path.
ResNet-50 encodes the image, and DeepLabV3 applies atrous spatial pyramid pooling
at several dilation rates before the new segmentation classifier.

## Pros and cons

| pros | cons |
|---|---|
| broad receptive field; established dense-prediction baseline; simpler than V3+ | lacks V3+'s low-level boundary refinement; dilated features still carry a substantial compute cost |

## Resource notes

With five classes this recipe has 39,634,757 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 173.8 MiB on an NVIDIA L40S. Full training
memory at practical crops is much higher.

## Tuning support

Full and frozen ResNet tuning are supported. Automatic LoRA is not supported for
the convolutional backbone. Head reset keeps the ASPP decoder and resets only
the final classifier.

## Pretrained source

The encoder comes from
[`smp-hub/resnet50.imagenet`](https://huggingface.co/smp-hub/resnet50.imagenet/tree/00cb74e366966d59cd9a35af57e618af9f88efe9)
revision `00cb74e366966d59cd9a35af57e618af9f88efe9`, pinned by SMP
0.5.0. ASPP and the classifier are new. `encoder_weights: scratch` means scratch;
weight-loading failure remains an error rather than changing the experiment.

## Verified evidence and benchmarks

On 2026-08-12 the exact DeepLabV3/ResNet-50 pair loaded its requested ImageNet
encoder and completed four finite BF16/AdamW optimizer steps at batch 2 and
64×64. The segmentation head changed and peak allocated CUDA memory was 0.751
GiB. The normal-suite scratch/frozen contract is in
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No comparable Segmentary accuracy benchmark is available for this exact recipe,
so none is listed. See the [SMP component guide](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 78.61 | 85.98 | 89.27 | 87.43 | 99.76 | 96.10 | 92.75 | 84.19 |
| RailSem19 | 40,000 / 40,000 | 68.18 | 81.67 | 78.88 | 80.17 | 99.38 | 89.18 | 81.52 | 76.03 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 66.11 | 79.96 | 77.73 | 78.73 | 99.31 | 87.97 | 79.70 | 73.47 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 39,638,869 | 151.2 MiB | 605.7 MiB | 77.91 | 12.83 ms | 12.89 ms | 0.67 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 14h 07m 22s | 14.12 | 6.02 GiB | 6.275 |
| RailSem19 | 17h 40m 01s | 17.67 | 6.59 GiB | 5.576 |
| Cityscapes → RailSem19 | 8h 45m 07s | 8.75 | 6.60 GiB | 5.585 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.21 |
| sidewalk | 85.37 |
| building | 92.47 |
| wall | 53.79 |
| fence | 59.81 |
| pole | 63.40 |
| traffic-light | 71.03 |
| traffic-sign | 79.49 |
| vegetation | 92.30 |
| terrain | 64.40 |
| sky | 94.80 |
| person | 82.41 |
| rider | 66.96 |
| car | 95.21 |
| truck | 78.60 |
| bus | 87.53 |
| train | 82.18 |
| motorcycle | 67.73 |
| bicycle | 77.98 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 60.02 | 56.10 |
| sidewalk | 62.38 | 59.19 |
| construction | 77.82 | 76.83 |
| fence | 56.53 | 53.85 |
| pole | 63.40 | 62.45 |
| traffic-light | 56.53 | 54.10 |
| traffic-sign | 47.74 | 47.54 |
| vegetation | 87.13 | 85.69 |
| terrain | 69.03 | 64.84 |
| sky | 95.53 | 94.83 |
| human | 63.48 | 65.10 |
| car | 80.36 | 77.34 |
| truck | 35.95 | 40.94 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 75.92 | 74.06 |
| rail-track | 89.73 | 87.70 |
| rail-raised | 71.80 | 67.11 |
| rail-embedded | 54.86 | 48.37 |
| tram-track | 72.52 | 67.70 |
| trackbed | 74.75 | 72.38 |

### Provenance

- Model recipe: `configs/models/smp_deeplabv3_resnet50.yaml`
- Source revisions: `b9eb3e1f390b70aad63e78b2e723bd79b5266471, db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: —; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
