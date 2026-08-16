# Built-in EoMT-DINOv3-Large

Use [`eomt_dinov3_large.yaml`](../../../../configs/models/eomt_dinov3_large.yaml)
for the advanced EoMT arm with a DINOv3 large backbone.

## What it is

The default `tue-mps/eomt-dinov3-coco-panoptic-large-640` repository is a
complete EoMT-DINOv3 checkpoint. Its DINOv3 transformer supplies image features;
query, mask, and class modules produce a set of region predictions. Segmentary
contracts those queries into an input-resolution dense semantic score map.

The checkpoint has a fixed 640×640 native grid. Segmentary resizes each sliding
window to that grid and resizes the prediction back. Use square windows to avoid
aspect-ratio distortion.

## When it helps—and when it does not

Pros:

- combines a large DINOv3 representation with an already trained mask head;
- default repository is loadable without passing a separate local Meta `.pth`;
- suitable as a clearly named advanced research ablation.

Cons:

- the model YAML alone retains Segmentary's experimental dense-CE objective;
  native query training requires an explicit `loss.query` override;
- large memory and compute demand; the shipped file starts at batch 1 with
  accumulation 2;
- fixed grid and square-window restriction;
- ONNX/TensorRT export is unsupported;
- DINOv3-derived weight licensing must be reviewed before redistribution.

The shipped optimizer lowers backbone LR to `1e-5`, uses layer-wise decay
`0.75`, and keeps a 10x head multiplier. These are starting settings, not a
benchmark guarantee. Full and frozen tuning are supported. Treat LoRA as
unverified until the exact installed model's targets and gradients pass a
retained baby run.

`checkpoint` overrides the complete EoMT repository; it is not the path to one
of Meta's raw pretraining `.pth` files. Raw licensed files use the separate
[local DINOv3 loader](../local-dinov3-loader/README.md), which supplies only a
backbone and cannot replace a complete EoMT repository here.

## Verified evidence and benchmarks

The real CUDA integration test loaded the non-gated default checkpoint and
produced finite BF16 input-resolution output. That proves construction and
forward compatibility only. Segmentary's
[Hungarian query objective](../../components/query-objectives/README.md) can
train the raw final query tensors, while the unchanged model YAML plus base
config still selects dense CE. No comparable Segmentary dataset mIoU is recorded;
the two objective choices must be named separately. The current EoMT output
does not expose intermediate decoder predictions for auxiliary loss.

See the [built-in model component](../../components/builtin-models/README.md)
and [model tuning guide](../../../guides/models-and-tuning.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 82.96 | 90.44 | 90.24 | 90.32 | 99.80 | 96.71 | 93.86 | 88.46 |
| RailSem19 | 40,000 / 40,000 | 71.42 | 82.65 | 82.87 | 82.67 | 99.41 | 89.96 | 82.44 | 78.12 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 314,917,910 | 1201.3 MiB | 4805.9 MiB | 41.23 | 24.12 ms | 24.77 ms | 3.13 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 14h 06m 17s | 14.10 | 17.02 GiB | 5.799 |
| RailSem19 | 13h 41m 29s | 13.69 | 17.02 GiB | 4.267 |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.41 |
| sidewalk | 87.72 |
| building | 93.92 |
| wall | 69.14 |
| fence | 70.41 |
| pole | 66.33 |
| traffic-light | 73.34 |
| traffic-sign | 81.52 |
| vegetation | 92.84 |
| terrain | 70.14 |
| sky | 95.30 |
| person | 84.88 |
| rider | 71.10 |
| car | 95.89 |
| truck | 89.19 |
| bus | 93.47 |
| train | 88.25 |
| motorcycle | 73.88 |
| bicycle | 80.53 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 63.05 | — |
| sidewalk | 64.52 | — |
| construction | 79.31 | — |
| fence | 59.18 | — |
| pole | 65.14 | — |
| traffic-light | 58.81 | — |
| traffic-sign | 53.69 | — |
| vegetation | 87.50 | — |
| terrain | 69.11 | — |
| sky | 95.55 | — |
| human | 69.17 | — |
| car | 84.03 | — |
| truck | 49.20 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 86.37 | — |
| rail-track | 90.30 | — |
| rail-raised | 72.94 | — |
| rail-embedded | 57.71 | — |
| tram-track | 76.19 | — |
| trackbed | 75.28 | — |

### Provenance

- Model recipe: `configs/models/eomt_dinov3_large.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0; RailSem19: 0.
- Quality evaluation weights: Cityscapes: —; RailSem19: —.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
