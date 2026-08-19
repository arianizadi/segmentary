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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 78.61 | 85.98 | 89.27 | 87.43 | 99.76 | 96.10 | 92.75 | 84.19 |
| RailSem19 | 40,000 / 40,000 | 68.41 | 80.94 | 79.76 | 80.29 | 99.39 | 89.31 | 81.68 | 76.38 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 66.11 | 79.96 | 77.73 | 78.73 | 99.31 | 87.97 | 79.70 | 73.47 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 39,638,869 | 151.2 MiB | 605.7 MiB | 77.91 | 12.83 ms | 12.89 ms | 0.67 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 14h 07m 22s | 14.12 | 6.02 GiB | 6.275 |
| RailSem19 | Rail40 standalone | 17h 40m 01s | 17.67 | 6.59 GiB | 5.625 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 8h 45m 07s | 8.75 | 6.60 GiB | 5.585 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 22h 52m 29s | 22.87 | 6.60 GiB | — |

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
| road | 60.39 | 56.10 |
| sidewalk | 62.76 | 59.19 |
| construction | 78.09 | 76.83 |
| fence | 56.41 | 53.85 |
| pole | 64.21 | 62.45 |
| traffic-light | 57.21 | 54.10 |
| traffic-sign | 48.73 | 47.54 |
| vegetation | 87.23 | 85.69 |
| terrain | 69.26 | 64.84 |
| sky | 95.70 | 94.83 |
| human | 64.60 | 65.10 |
| car | 81.44 | 77.34 |
| truck | 33.51 | 40.94 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 75.79 | 74.06 |
| rail-track | 89.78 | 87.70 |
| rail-raised | 71.75 | 67.11 |
| rail-embedded | 55.23 | 48.37 |
| tram-track | 72.93 | 67.70 |
| trackbed | 74.72 | 72.38 |

### Provenance

- Model recipe: `configs/models/smp_deeplabv3_resnet50.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
