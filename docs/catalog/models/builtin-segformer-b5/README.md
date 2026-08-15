# Built-in SegFormer-B5

[`segformer_b5.yaml`](../../../../configs/models/segformer_b5.yaml) selects the
largest SegFormer option in the hand-written factory.

```yaml
model:
  arch: segformer_b5
  checkpoint: nvidia/mit-b5
  tuning: full
  head: unified_head
```

## What it is

The path loads the ImageNet-pretrained `nvidia/mit-b5` hierarchical transformer
encoder and creates a new dataset-specific SegFormer decode head. Like B0 and
B2, it fuses four feature scales and returns input-resolution logits.

## When to use it

Pros:

- highest-capacity built-in SegFormer;
- direct architectural scale-up from the well-tested B0/B2 path;
- hierarchical features avoid the fixed single-scale map of a plain ViT;
- full, frozen, and attention-projection LoRA are available in principle.

Cons:

- largest memory and compute cost in the built-in SegFormer family;
- no shipped tuned recipe or Segmentary dataset benchmark;
- decoder is fresh, so the encoder's capacity does not remove the need for
  sufficient task data and training;
- construction compatibility is not a substitute for a B5-specific baby run.

## Safe first experiment

Compose the shipped model YAML with the same taxonomy, data split, optimizer
schedule, evaluation settings, and seeds used for B2. First run the overfit
check and a few-step training smoke at a small crop. Then measure intended-crop
peak memory before launching the full comparison.

Use RGB ImageNet normalization and dimensions divisible by 32. Reduce
per-device batch before changing the scientific protocol; accumulation can
restore the effective batch. A local immutable `nvidia/mit-b5` snapshot is the
way to pin the encoder exactly because this built-in path rejects the generic
Hub `revision` field.

## Verified evidence and benchmarks

B5 shares the tested SegFormer wrapper and factory logic with B0/B2, but no
same-protocol Segmentary accuracy result or retained B5 baby-training artifact is
claimed here. Treat it as an available advanced arm that still needs its own
resource and training acceptance on the target system.

See [SegFormer-B2](../builtin-segformer-b2/README.md) for the current comparable
reference and the [built-in model component](../../components/builtin-models/README.md)
for shared rules.

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 82.40 | 89.06 | 90.98 | 89.96 | 99.80 | 96.73 | 93.87 | 88.23 |
| RailSem19 | 40,000 / 40,000 | 71.95 | 82.46 | 83.76 | 83.02 | 99.44 | 90.51 | 83.29 | 80.07 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class EMA checkpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 84,609,493 | 322.8 MiB | 1292.9 MiB | 25.13 | 39.28 ms | 43.62 ms | 2.57 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 17h 59m 42s | 17.99 | 16.31 GiB | 4.783 |
| RailSem19 | 19h 38m 19s | 19.64 | 16.94 GiB | 3.478 |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.54 |
| sidewalk | 87.92 |
| building | 93.65 |
| wall | 69.71 |
| fence | 66.49 |
| pole | 68.21 |
| traffic-light | 75.11 |
| traffic-sign | 81.69 |
| vegetation | 93.12 |
| terrain | 67.10 |
| sky | 95.46 |
| person | 84.70 |
| rider | 67.94 |
| car | 95.84 |
| truck | 89.15 |
| bus | 91.54 |
| train | 85.56 |
| motorcycle | 73.64 |
| bicycle | 80.25 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 64.76 | — |
| sidewalk | 65.14 | — |
| construction | 80.50 | — |
| fence | 59.74 | — |
| pole | 64.44 | — |
| traffic-light | 57.19 | — |
| traffic-sign | 53.31 | — |
| vegetation | 87.93 | — |
| terrain | 71.23 | — |
| sky | 95.96 | — |
| human | 67.69 | — |
| car | 82.90 | — |
| truck | 49.83 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 85.17 | — |
| rail-track | 91.26 | — |
| rail-raised | 74.74 | — |
| rail-embedded | 59.11 | — |
| tram-track | 79.08 | — |
| trackbed | 76.99 | — |

### Provenance

- Model recipe: `configs/models/segformer_b5.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: RailSem19: 0; Cityscapes: 0.
- EMA quality evaluation uses 1024x1024 sliding windows, stride 768, no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
