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
| Cityscapes | 0 / 40,000 | — | — | — | — | — | — | — | — |
| RailSem19 | 40,000 / 40,000 | 68.18 | 81.67 | 78.88 | 80.17 | 99.38 | 89.18 | 81.52 | 76.03 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 39,638,869 | 151.2 MiB | 605.7 MiB | 77.60 | 12.88 ms | 12.93 ms | 0.84 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | — |
| RailSem19 | 17h 40m 01s | 17.67 | 6.59 GiB | 5.576 |
| Cityscapes → RailSem19 | — | — | — | — |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 60.02 | — |
| sidewalk | 62.38 | — |
| construction | 77.82 | — |
| fence | 56.53 | — |
| pole | 63.40 | — |
| traffic-light | 56.53 | — |
| traffic-sign | 47.74 | — |
| vegetation | 87.13 | — |
| terrain | 69.03 | — |
| sky | 95.53 | — |
| human | 63.48 | — |
| car | 80.36 | — |
| truck | 35.95 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 75.92 | — |
| rail-track | 89.73 | — |
| rail-raised | 71.80 | — |
| rail-embedded | 54.86 | — |
| tram-track | 72.52 | — |
| trackbed | 74.75 | — |

### Provenance

- Model recipe: `configs/models/smp_deeplabv3_resnet50.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: RailSem19: 0.
- Quality evaluation weights: RailSem19: —.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
