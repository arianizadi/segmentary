# PAN with ResNeXt-50

Recipe: [`smp_pan_resnext50.yaml`](../../../../configs/models/smp_pan_resnext50.yaml)

## Purpose and architecture

Use this recipe to test pyramid attention with a higher-capacity grouped-
convolution encoder. ResNeXt-50 produces hierarchical features; PAN applies
feature-pyramid attention and global-attention upsampling before the fresh head.

## Pros and cons

| pros | cons |
|---|---|
| compact attention decoder; capable encoder; explicit multi-scale context | verified SMP implementation fails below 128 pixels per side; more encoder cost than mobile recipes |

## Resource notes

With five classes the recipe has 23,732,844 parameters. Because 64×64 collapses
PAN's pooling pyramid, its diagnostic probe used 128×128 and allocated 106.8 MiB
for BF16 batch-1 inference on an NVIDIA L40S. Use crops at least 128 pixels per
side and normally divisible by 32. Full training memory is substantially higher.

## Tuning support

Full and frozen ResNeXt tuning are supported. Automatic LoRA is not supported
for this convolutional encoder. Head reset keeps the PAN decoder and replaces
only the final classifier.

## Pretrained source

The ImageNet source is
[`smp-hub/resnext50_32x4d.imagenet`](https://huggingface.co/smp-hub/resnext50_32x4d.imagenet/tree/329793c85d62fd340ae42ae39fb905a63df872e7)
at revision `329793c85d62fd340ae42ae39fb905a63df872e7`, pinned by SMP
0.5.0. PAN itself starts fresh. `encoder_weights: scratch` is the explicit scratch
choice; a failed requested load is fatal.

## Verified evidence and benchmarks

On 2026-08-12 the exact PAN/ResNeXt-50 pair loaded its requested ImageNet encoder
and completed four finite BF16/AdamW steps at batch 2 and 128×128. The head
changed and peak allocated CUDA memory was 0.466 GiB.
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py) keeps PAN's
larger minimum smoke shape explicit.

No protocol-comparable accuracy benchmark exists for this recipe. The minimum
shape finding is a compatibility result, not an accuracy result. See the
[SMP component guide](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 67.25 | 74.43 | 86.00 | 78.24 | 99.69 | 95.03 | 90.85 | 78.36 |
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class recorded raw/EMA endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | 7.034 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 97.63 |
| sidewalk | 82.51 |
| building | 90.98 |
| wall | 28.50 |
| fence | 52.26 |
| pole | 60.48 |
| traffic-light | 68.90 |
| traffic-sign | 77.00 |
| vegetation | 91.47 |
| terrain | 61.04 |
| sky | 94.06 |
| person | 79.42 |
| rider | 53.96 |
| car | 91.23 |
| truck | 28.31 |
| bus | 51.96 |
| train | 33.09 |
| motorcycle | 58.44 |
| bicycle | 76.55 |

### Provenance

- Model recipe: `configs/models/smp_pan_resnext50.yaml`
- Source revisions: `a50027d6a72a9146f6302bc1f407e6477a74e8c7`
- Retained seeds: Cityscapes: 0.
- Quality evaluation weights: Cityscapes: —.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final full-state checkpoint and standalone raw-weight validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
