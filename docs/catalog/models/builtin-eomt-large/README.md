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

Values are validated mean percentages, shown as one clean number. Detailed machine records retain every contributing seed. `—` means evidence is unavailable, not zero.

| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cityscapes | 40,000 / 40,000 | 82.74 | 90.29 | 90.11 | 90.18 | 99.79 | 96.62 | 93.69 | 88.48 |
| RailSem19 | 40,000 / 40,000 | 72.13 | 82.80 | 83.89 | 83.20 | 99.42 | 90.18 | 82.76 | 78.92 |
| Cityscapes → RailSem19 | 0 / 20,000 | — | — | — | — | — | — | — | — |

### Standardized model-only inference

Measured once from this model's RailSem19-only 21-class ema endpoint on an NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal conversion to dense logits, including query collapse where applicable, and excludes I/O, preprocessing, sliding windows, argmax, and metrics.

| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |
|---:|---:|---:|---:|---:|---:|---:|
| 316,580,886 | 1207.7 MiB | 4831.3 MiB | 45.91 | 21.76 ms | 21.86 ms | 3.12 GiB |

### Training and full-pipeline evaluation cost

Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM is the maximum per-device allocator-reserved high-water mark. Full-pipeline throughput includes the loader, sliding-window inference, and metrics.

| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |
|---|---:|---:|---:|---:|
| Cityscapes | 13h 26m 42s | 13.45 | 16.86 GiB | 6.199 |
| RailSem19 | 14h 39m 19s | 14.66 | 16.40 GiB | 4.534 |
| Cityscapes → RailSem19 | — | — | — | — |

### Cityscapes class IoU

| class | IoU |
|---|---:|
| road | 98.39 |
| sidewalk | 87.38 |
| building | 93.70 |
| wall | 67.90 |
| fence | 71.59 |
| pole | 65.31 |
| traffic-light | 72.80 |
| traffic-sign | 80.71 |
| vegetation | 92.62 |
| terrain | 69.94 |
| sky | 95.22 |
| person | 84.43 |
| rider | 71.31 |
| car | 95.62 |
| truck | 90.38 |
| bus | 92.86 |
| train | 87.58 |
| motorcycle | 74.29 |
| bicycle | 80.00 |

### RailSem19 class IoU

| class | RailSem19 | Cityscapes → RailSem19 |
|---|---:|---:|
| road | 63.91 | — |
| sidewalk | 64.70 | — |
| construction | 79.95 | — |
| fence | 59.47 | — |
| pole | 64.32 | — |
| traffic-light | 59.54 | — |
| traffic-sign | 54.46 | — |
| vegetation | 87.56 | — |
| terrain | 69.38 | — |
| sky | 95.83 | — |
| human | 70.07 | — |
| car | 83.59 | — |
| truck | 52.43 | — |
| motorcycle | — | — |
| bicycle | — | — |
| on-rails | 85.97 | — |
| rail-track | 91.07 | — |
| rail-raised | 73.93 | — |
| rail-embedded | 59.98 | — |
| tram-track | 78.77 | — |
| trackbed | 75.64 | — |

### Provenance

- Model recipe: `configs/models/eomt_large.yaml`
- Source revisions: `db1e951f289fc6c09294e9a019945695ad2d94d2`
- Retained seeds: Cityscapes: 0; RailSem19: 0.
- Quality evaluation weights: Cityscapes: —; RailSem19: —.
- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.
- Metric derivation: Derived from each retained confusion matrix when absent; all other metrics come directly from validated result records.

<!-- segmentary:generated-city-rail-benchmark:end -->
