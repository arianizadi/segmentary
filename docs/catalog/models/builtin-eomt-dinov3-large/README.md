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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 82.94 | 90.40 | 90.26 | 90.31 | 99.80 | 96.71 | 93.85 | 88.49 |
| RailSem19 | 40,000 / 40,000 | 71.45 | 82.65 | 82.90 | 82.69 | 99.41 | 89.98 | 82.47 | 78.09 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 69.84 | 81.29 | 82.28 | 81.56 | 99.36 | 89.12 | 81.20 | 76.61 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 314,917,910 | 1201.3 MiB | 4805.9 MiB | 41.23 | 24.12 ms | 24.77 ms | 3.13 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 14h 06m 17s | 14.10 | 17.02 GiB | 5.814 |
| RailSem19 | Rail40 standalone | 13h 41m 29s | 13.69 | 17.02 GiB | 4.248 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 7h 36m 59s | 7.62 | 16.54 GiB | 4.291 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 21h 43m 15s | 21.72 | 17.02 GiB | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.42 |
| sidewalk | 87.74 |
| building | 93.91 |
| wall | 69.00 |
| fence | 70.38 |
| pole | 66.21 |
| traffic-light | 73.36 |
| traffic-sign | 81.46 |
| vegetation | 92.83 |
| terrain | 69.90 |
| sky | 95.30 |
| person | 84.84 |
| rider | 71.16 |
| car | 95.88 |
| truck | 89.16 |
| bus | 93.45 |
| train | 88.34 |
| motorcycle | 74.01 |
| bicycle | 80.54 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 63.14 | 57.97 |
| sidewalk | 64.70 | 62.92 |
| construction | 79.32 | 78.41 |
| fence | 59.19 | 57.41 |
| pole | 65.09 | 64.68 |
| traffic-light | 59.04 | 58.33 |
| traffic-sign | 53.59 | 54.17 |
| vegetation | 87.54 | 86.84 |
| terrain | 69.19 | 67.22 |
| sky | 95.57 | 95.36 |
| human | 69.23 | 69.55 |
| car | 83.79 | 84.73 |
| truck | 48.96 | 53.76 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 86.38 | 84.69 |
| rail-track | 90.29 | 88.44 |
| rail-raised | 73.08 | 69.93 |
| rail-embedded | 58.14 | 49.83 |
| tram-track | 75.95 | 69.83 |
| trackbed | 75.31 | 72.99 |

### Provenance

- Model recipe: `configs/models/eomt_dinov3_large.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
