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

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 81.03 | 87.64 | 90.64 | 89.04 | 99.78 | 96.46 | 93.38 | 87.36 |
| RailSem19 | 0 / 40,000 | — | — | — | — | — | — | — | — |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Pending one measurement from this model's RailSem19-only 21-class EMA checkpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| — | — | — | — | — | — | — |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 13h 28m 59s | 13.48 | 10.60 GiB | 5.379 |
| RailSem19 | — | — | — | — |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.28 |
| sidewalk | 86.21 |
| building | 93.25 |
| wall | 62.87 |
| fence | 65.17 |
| pole | 65.92 |
| traffic-light | 72.96 |
| traffic-sign | 81.48 |
| vegetation | 92.80 |
| terrain | 66.77 |
| sky | 94.97 |
| person | 83.59 |
| rider | 65.93 |
| car | 95.73 |
| truck | 87.71 |
| bus | 92.05 |
| train | 84.96 |
| motorcycle | 69.38 |
| bicycle | 79.50 |

### Provenance

- Model recipe: `configs/models/upernet_convnext.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0.
- EMA quality evaluation uses 1024x1024 sliding windows, stride 768, no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
