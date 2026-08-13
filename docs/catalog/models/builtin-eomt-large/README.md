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
