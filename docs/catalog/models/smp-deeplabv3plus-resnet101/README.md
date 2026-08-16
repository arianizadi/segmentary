# DeepLabV3+ with ResNet-101

Recipe: [`smp_deeplabv3plus_resnet101.yaml`](../../../../configs/models/smp_deeplabv3plus_resnet101.yaml)

## Purpose and architecture

This is the high-capacity conventional baseline. ResNet-101 supplies the feature
hierarchy; DeepLabV3+ combines atrous spatial pyramid context with a low-level
refinement path to recover boundaries. The decoder and classifier start fresh.

## Pros and cons

| pros | cons |
|---|---|
| established architecture; combines broad context and local refinement; useful sanity reference | largest shipped SMP recipe by parameter count; slower and more memory-intensive than mobile or ResNet-50 choices |

## Resource notes

At five classes the recipe has 45,670,741 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 187.6 MiB on an NVIDIA L40S. Production training
adds large activation, gradient, optimizer, and crop-size costs.

## Tuning support

Full and frozen ResNet tuning are supported. Automatic LoRA is not supported for
this convolutional encoder. Head reset changes only the final segmentation
classifier, retaining the V3+ decoder.

## Pretrained source

SMP 0.5.0 maps the ImageNet tag to
[`smp-hub/resnet101.imagenet`](https://huggingface.co/smp-hub/resnet101.imagenet/tree/cd7c15e8c51da86ae6a084515fdb962d0c94e7d1)
at revision `cd7c15e8c51da86ae6a084515fdb962d0c94e7d1`. Only the encoder
is pretrained. Set `encoder_weights: scratch` deliberately for scratch; load
failures never cause an automatic scratch retry.

## Verified evidence and benchmarks

On 2026-08-12 the exact DeepLabV3+/ResNet-101 pair loaded its requested ImageNet
encoder and ran four finite BF16/AdamW steps at batch 2 and 64×64. Its head
updated and peak allocated CUDA memory was 0.866 GiB. The repeatable
scratch/frozen regression is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

The older `deeplabv3plus_r101` alias has [untrained deployment compatibility
evidence](../../../benchmarks/deeplabv3plus-r101-untrained-export/README.md), but it
must not be treated as an accuracy benchmark for a new dataset or protocol. No
same-protocol accuracy result exists for this recipe yet. See the
[SMP component guide](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 79.18 | 86.57 | 89.35 | 87.82 | 99.77 | 96.23 | 92.98 | 84.82 |
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |

### Transfer checkpoints

The cumulative count includes the reused 40,000-step Cityscapes source. The historical row is retained as a baseline and is not mixed with corrected runs.

| optimizer contract | Rail iterations | cumulative iterations | mIoU | boundary F1 |
|---|---:|---:|---:|---:|
| historical 0.1x backbone + 0.1x head groups | 20,000 | 60,000 | — | — |
| corrected 0.1x backbone + 1.0x head groups | 20,000 | 60,000 | — | — |
| corrected 0.1x backbone + 1.0x head groups | 40,000 | 80,000 | — | — |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class recorded raw/EMA endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | 6.853 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.35 |
| sidewalk | 86.20 |
| building | 92.65 |
| wall | 55.39 |
| fence | 61.54 |
| pole | 65.08 |
| traffic-light | 71.87 |
| traffic-sign | 79.32 |
| vegetation | 92.33 |
| terrain | 64.76 |
| sky | 95.07 |
| person | 82.55 |
| rider | 65.95 |
| car | 95.36 |
| truck | 79.91 |
| bus | 88.66 |
| train | 82.09 |
| motorcycle | 69.03 |
| bicycle | 78.39 |

### Provenance

- Model recipe: `configs/models/smp_deeplabv3plus_resnet101.yaml`
- Source revisions: `a50027d6a72a9146f6302bc1f407e6477a74e8c7`
- Retained seeds: Cityscapes: 0.
- Quality evaluation weights: Cityscapes: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone raw-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
