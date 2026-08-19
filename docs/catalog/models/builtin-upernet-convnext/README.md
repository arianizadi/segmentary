# Built-in UPerNet with ConvNeXt-Small

[`upernet_convnext.yaml`](../../../../configs/models/upernet_convnext.yaml)
selects a modern convolutional alternative to SegFormer:

```yaml
model:
  arch: upernet_convnext
  checkpoint: openmmlab/upernet-convnext-small
  tuning: full
  head: unified_head
```

## What it is

ConvNeXt-Small produces a four-level hierarchical feature pyramid. UPerNet adds
pyramid pooling for broad context and a feature-pyramid decoder for multi-scale
fusion. The default is a complete ADE20K semantic-segmentation checkpoint; when
the destination class count differs, Transformers replaces the class-dependent
prediction layer.

Segmentary disables the upstream FCN auxiliary head. The current trainer owns one
dense loss and would otherwise compute a branch that receives no loss gradient,
causing wasted work and distributed unused-parameter failures.

## When to use it

Pros:

- strong convolutional control against transformer encoders;
- complete task-trained decoder, not only an ImageNet backbone;
- explicit multi-scale pyramid is useful when object sizes vary;
- ordinary dense logits work with Segmentary's loss and evaluator.

Cons:

- heavier decoder than SegFormer;
- the source classifier is replaced for a new taxonomy;
- the auxiliary-head training signal from the source recipe is not reproduced;
- ConvNeXt has no attention projections for Segmentary's automatic LoRA path.

## Advanced settings

Full and frozen tuning are supported. Frozen mode keeps ConvNeXt fixed while
training the UPerNet decoder and classifier. Top-level `drop_path` is rejected:
the value belongs inside the nested backbone config, and silently accepting it
would make the resolved experiment record false.

Use RGB ImageNet normalization, start with dimensions divisible by 32, and
measure memory at the intended crop. Override `checkpoint` only with a
structurally compatible UPerNet/ConvNeXt checkpoint or local snapshot.

## Verified evidence and benchmarks

The real integration regression constructs the default checkpoint on CUDA and
checks a finite `(1, 21, 96, 128)` BF16 output from a `(1, 3, 96, 128)` input.
That proves the current pinned environment can load and forward the arm. It is
not a speed, memory, or accuracy benchmark. No comparable Segmentary dataset mIoU
is claimed yet.

See the [built-in model component](../../components/builtin-models/README.md)
and [model comparison guide](../../../guides/models-and-tuning.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
Each quality cell is one retained seed (seed 0). It has no error bar and should not be used to claim that a sub-one-point difference is statistically meaningful.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 80.88 | 87.55 | 90.55 | 88.95 | 99.78 | 96.44 | 93.34 | 87.14 |
| RailSem19 | 40,000 / 40,000 | 70.66 | 80.80 | 83.60 | 82.10 | 99.42 | 90.16 | 82.73 | 79.31 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 69.32 | 81.31 | 81.11 | 81.18 | 99.38 | 89.48 | 81.71 | 77.12 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 80,887,221 | 308.6 MiB | 1235.0 MiB | 43.06 | 23.19 ms | 23.35 ms | 2.48 GiB |

### Training and full-pipeline evaluation cost

Standalone rows report their own training cost. The transfer adaptation row reports only Rail20 because it reuses City40; the cumulative row adds the retained City40 and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---|---:|---:|---:|---:|
| Cityscapes | City40 standalone | 13h 28m 59s | 13.48 | 10.60 GiB | 5.390 |
| RailSem19 | Rail40 standalone | 16h 57m 54s | 16.96 | 10.60 GiB | 4.294 |
| Cityscapes → RailSem19 | Rail20 adaptation only; excludes reused City40 | 9h 28m 19s | 9.47 | 9.93 GiB | 4.210 |
| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | 22h 57m 18s | 22.96 | 10.60 GiB | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.29 |
| sidewalk | 86.29 |
| building | 93.18 |
| wall | 62.97 |
| fence | 65.15 |
| pole | 65.36 |
| traffic-light | 72.65 |
| traffic-sign | 81.29 |
| vegetation | 92.75 |
| terrain | 66.69 |
| sky | 95.03 |
| person | 83.41 |
| rider | 65.74 |
| car | 95.63 |
| truck | 87.24 |
| bus | 91.98 |
| train | 84.14 |
| motorcycle | 69.65 |
| bicycle | 79.37 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 62.46 | 59.58 |
| sidewalk | 63.84 | 61.42 |
| construction | 80.06 | 78.78 |
| fence | 58.44 | 57.24 |
| pole | 63.06 | 63.48 |
| traffic-light | 54.71 | 56.35 |
| traffic-sign | 53.51 | 52.46 |
| vegetation | 87.82 | 87.61 |
| terrain | 70.85 | 69.94 |
| sky | 95.86 | 95.38 |
| human | 67.14 | 67.08 |
| car | 82.88 | 82.84 |
| truck | 48.13 | 47.12 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 81.67 | 78.50 |
| rail-track | 90.73 | 88.70 |
| rail-raised | 74.01 | 71.81 |
| rail-embedded | 56.43 | 55.18 |
| tram-track | 74.77 | 69.26 |
| trackbed | 76.09 | 74.34 |

### Provenance

- Model recipe: `configs/models/upernet_convnext.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
