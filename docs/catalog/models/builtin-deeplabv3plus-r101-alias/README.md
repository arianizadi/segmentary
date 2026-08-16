# DeepLabV3+/ResNet-101 compatibility alias

Use [`deeplabv3plus_r101.yaml`](../../../../configs/models/deeplabv3plus_r101.yaml)
to preserve older experiment commands. New configurations should prefer the
explicit [`smp_deeplabv3plus_resnet101.yaml`](../../../../configs/models/smp_deeplabv3plus_resnet101.yaml)
recipe, which records decoder, encoder, and encoder weights separately.

## What it is

`arch: deeplabv3plus_r101` constructs SMP's DeepLabV3+ with a ResNet-101 encoder
and ImageNet encoder weights. Atrous spatial pyramid pooling gathers context at
several dilation rates; the V3+ decoder fuses low-level features to recover
spatial detail. Decoder and final classifier start fresh.

The alias and the explicit SMP recipe reach the same constructor with their
default values. The alias exists for compatibility, not as a second model.

## The checkpoint field is unusual

For this alias only, `model.checkpoint` means the SMP **encoder name**. For
example, tests use `checkpoint: resnet18` to exercise the path cheaply. It does
not mean a `.ckpt` file and it does not resume training. Use stage `init_from`
for a Segmentary checkpoint.

Pros:

- established CNN baseline with broad context and boundary refinement;
- straightforward dense-CE training;
- fixed-shape ONNX export and ONNX Runtime parity are regression-tested;
- useful sanity floor for more experimental architectures.

Cons:

- older, large encoder;
- decoder has no task pretraining;
- compatibility field semantics are less clear than `arch: smp`;
- automatic LoRA is not available for the convolutional ResNet backbone.

## Tuning, resources, and evidence

Full and frozen tuning are supported. Head reset changes only the final
segmentation classifier. Use RGB ImageNet normalization and crop sizes divisible
by 32. Memory rises strongly with crop area; run a baby training test before a
full-resolution experiment.

The model suite exercises real forward/backward behavior through this alias,
and the export suite checks the real architecture against ONNX Runtime on a
real Cityscapes image. Separate deployment acceptance may use untrained weights;
that proves graph compatibility, not model accuracy. No same-protocol mIoU is
claimed for this recipe yet.

See the [explicit recipe page](../smp-deeplabv3plus-resnet101/README.md) and
[SMP component](../../components/smp/README.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 78.99 | 86.69 | 88.94 | 87.68 | 99.77 | 96.20 | 92.94 | 84.84 |
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

Pending one measurement from this model's RailSem19-only 21-class EMA checkpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | — | — | — | 6.643 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.33 |
| sidewalk | 86.18 |
| building | 92.65 |
| wall | 54.35 |
| fence | 61.73 |
| pole | 64.28 |
| traffic-light | 71.31 |
| traffic-sign | 79.68 |
| vegetation | 92.31 |
| terrain | 64.91 |
| sky | 95.00 |
| person | 82.46 |
| rider | 64.83 |
| car | 95.38 |
| truck | 79.35 |
| bus | 88.48 |
| train | 82.45 |
| motorcycle | 69.01 |
| bicycle | 78.12 |

### Provenance

- Model recipe: `configs/models/deeplabv3plus_r101.yaml`
- Source revisions: `a50027d6a72a9146f6302bc1f407e6477a74e8c7`
- Retained seeds: Cityscapes: 0.
- EMA quality evaluation uses 1024x1024 sliding windows, stride 768, no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.
- Caveat: Completed on compatible clean source a50027d6a72a after the legacy lane was stopped before this cell produced a reusable result; exact final EMA checkpoint and standalone validation evidence are retained.

<!-- segmentary:generated-city-rail-benchmark:end -->
