# Built-in EoMT-Large

[`eomt_large.yaml`](../../../../configs/models/eomt_large.yaml) selects an
experimental mask-classification arm. Use it only when the objective mismatch
described below is intentional, or explicitly add the native query objective.

```yaml
model:
  arch: eomt_large
  checkpoint: tue-mps/coco_panoptic_eomt_large_640
  tuning: full
  head: unified_head
```

## What it is

EoMT predicts a fixed set of query masks and, for each query, a class
distribution plus a no-object class. Segmentary converts those queries into a
dense semantic score map so the common evaluator can consume it. The default
complete checkpoint was trained for COCO panoptic segmentation and has a fixed
640×640 token grid.

The wrapper resizes each input window to the checkpoint's native grid, runs the
model, combines class probabilities with sigmoid mask scores, and maps the
result back to the original window. Keep evaluation windows square; otherwise
the internal resize distorts aspect ratio.

## Choose the objective explicitly

Native EoMT training uses Hungarian matching over predicted `(class, mask)`
pairs. Segmentary now has its own typed
[Hungarian query objective](../../components/query-objectives/README.md), which
consumes EoMT's raw final query tensors. The model YAML intentionally does not
select it: when composed only with `configs/base.yaml`, training still applies
pixel-wise dense cross-entropy after collapsing queries. That older path is a
different objective and remains an explicitly labeled ablation.

Add a final `loss.query` override to choose native query training. The current
Hugging Face EoMT output exposes only final query tensors, so this architecture
does not receive intermediate decoder-layer losses even when the generic query
objective's auxiliary weight is enabled.

Pros:

- gives access to query-based semantic prediction in the common evaluator;
- complete non-gated default checkpoint;
- query masks can model whole objects and regions rather than only local pixels.

Cons:

- objective must be selected and reported explicitly;
- fixed 640×640 native grid and square-window recommendation;
- large model and query head;
- ONNX/TensorRT export is explicitly unsupported;
- no Segmentary dataset-quality benchmark.

## Tuning and verification

Full and frozen tuning use the normal backbone/head partition. LoRA should be
treated as unverified until an actual target/gradient smoke is retained for this
model version. `reset_head` resets the class predictor; it does not reset query
or mask feature machinery.

The real CUDA regression loads the default checkpoint and checks finite BF16,
input-resolution output. Unit tests cover query-to-dense math, raw-query
preservation, native Hungarian loss dispatch, and fixed-grid resizing. These
are compatibility proofs only.

No comparable Segmentary accuracy result yet establishes how query training ranks
against a dense model. Keep native-query and dense-collapse runs as separate,
clearly named objective ablations.

See the [built-in model component](../../components/builtin-models/README.md)
and [evaluation guide](../../../guides/evaluation-and-results.md).

<!-- segmentary:generated-city-rail-benchmark:start -->
## Cityscapes and RailSem19 benchmark results

Values are validated percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.
All quality values use raw checkpoint weights under the uniform paper policy.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 82.72 | 90.20 | 90.17 | 90.17 | 99.79 | 96.61 | 93.68 | 88.56 |
| RailSem19 | 40,000 / 40,000 | 72.14 | 82.69 | 83.99 | 83.21 | 99.42 | 90.17 | 82.75 | 78.85 |
| Cityscapes → RailSem19 | 20,000 / 20,000 | 69.96 | 81.30 | 82.29 | 81.65 | 99.36 | 89.16 | 81.25 | 76.48 |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 316,580,886 | 1207.7 MiB | 4831.3 MiB | 45.91 | 21.76 ms | 21.86 ms | 3.12 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 13h 26m 42s | 13.45 | 16.86 GiB | 6.209 |
| RailSem19 | 14h 39m 19s | 14.66 | 16.40 GiB | 4.595 |
| Cityscapes → RailSem19 | 7h 19m 43s | 7.33 | 16.39 GiB | 4.603 |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.38 |
| sidewalk | 87.33 |
| building | 93.69 |
| wall | 67.98 |
| fence | 71.36 |
| pole | 65.24 |
| traffic-light | 72.87 |
| traffic-sign | 80.69 |
| vegetation | 92.60 |
| terrain | 69.54 |
| sky | 95.22 |
| person | 84.40 |
| rider | 71.30 |
| car | 95.61 |
| truck | 90.33 |
| bus | 93.00 |
| train | 87.55 |
| motorcycle | 74.63 |
| bicycle | 79.91 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 63.91 | 58.32 |
| sidewalk | 64.71 | 62.72 |
| construction | 79.89 | 78.61 |
| fence | 59.35 | 57.10 |
| pole | 64.29 | 64.39 |
| traffic-light | 59.57 | 58.06 |
| traffic-sign | 54.39 | 54.09 |
| vegetation | 87.50 | 86.72 |
| terrain | 69.34 | 66.92 |
| sky | 95.84 | 95.49 |
| human | 70.14 | 69.42 |
| car | 83.77 | 84.25 |
| truck | 52.43 | 50.60 |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 85.99 | 85.70 |
| rail-track | 91.10 | 88.22 |
| rail-raised | 73.99 | 71.18 |
| rail-embedded | 60.00 | 54.62 |
| tram-track | 78.78 | 69.71 |
| trackbed | 75.68 | 73.10 |

### Provenance

- Model recipe: `configs/models/eomt_large.yaml`
- Source revisions: `a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270`
- Retained seeds: Cityscapes: 0; RailSem19: 0; Cityscapes → RailSem19: 0.
- Quality evaluation weights: Cityscapes: raw; RailSem19: raw; Cityscapes → RailSem19: raw.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
