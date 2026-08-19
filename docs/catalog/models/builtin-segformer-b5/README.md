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

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 82.30 | 88.92 | 91.00 | 89.89 | 99.80 | 96.73 | 93.85 | 88.17 |
| RailSem19 | 40,000 / 40,000 | 71.87 | 82.36 | 83.72 | 82.96 | 99.44 | 90.50 | 83.26 | 80.04 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 69.30 | 81.53 | 81.03 | 81.17 | 99.37 | 89.29 | 81.43 | 76.94 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 84,609,493 | 322.8 MiB | 1292.9 MiB | 26.74 | 37.00 ms | 39.55 ms | 2.57 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 17h 59m 42s | 17.99 | 16.31 GiB | 4.880 |
| RailSem19 | 19h 38m 19s | 19.64 | 16.94 GiB | 3.476 |
| Cityscapes → RailSem19 | 10h 48m 49s | 10.81 | 16.31 GiB | 3.408 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.55 |
| sidewalk | 87.94 |
| building | 93.64 |
| wall | 69.65 |
| fence | 66.18 |
| pole | 68.34 |
| traffic-light | 75.10 |
| traffic-sign | 81.68 |
| vegetation | 93.09 |
| terrain | 66.68 |
| sky | 95.48 |
| person | 84.72 |
| rider | 67.80 |
| car | 95.78 |
| truck | 88.18 |
| bus | 91.54 |
| train | 85.29 |
| motorcycle | 73.71 |
| bicycle | 80.26 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 64.57 | 60.80 |
| sidewalk | 65.05 | 62.86 |
| construction | 80.44 | 78.96 |
| fence | 59.59 | 57.34 |
| pole | 64.33 | 64.13 |
| traffic-light | 57.11 | 56.42 |
| traffic-sign | 53.25 | 51.55 |
| vegetation | 87.95 | 87.15 |
| terrain | 71.15 | 68.12 |
| sky | 95.96 | 95.35 |
| human | 67.63 | 67.71 |
| car | 82.80 | 82.57 |
| truck | 49.42 | 49.63 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 85.12 | 82.36 |
| rail-track | 91.22 | 87.93 |
| rail-raised | 74.74 | 69.73 |
| rail-embedded | 59.08 | 52.56 |
| tram-track | 79.11 | 68.01 |
| trackbed | 76.95 | 73.45 |

### Provenance

- Model recipe: `configs/models/segformer_b5.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270, b9eb3e1f390b70aad63e78b2e723bd79b5266471`
- Retained seeds: RailSem19: 0; Cityscapes: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: RailSem19: raw; Cityscapes: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
