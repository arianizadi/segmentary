# Evaluation choices

Evaluation converts model output into one fixed, auditable score protocol. A
number is comparable only when dataset, split, taxonomy, checkpoint/weight
policy, image handling, and TTA all match.

## Beginner choice

Use EMA weights, native-resolution sliding windows, one scale, no flip, and a
descriptive output directory:

```bash
segmentary-eval base.yaml model.yaml experiment.yaml \
  --ckpt runs/experiment_seed0/target/last.ckpt \
  --seed 0 --ema \
  --out runs/experiment_seed0/eval_target_val/results.json
```

## Config switches

```yaml
eval:
  sliding_window: true
  window: [1024, 1024]
  stride: [768, 768]
  batch_size: 1
  num_workers: 4
  tta_scales: []
  tta_flip: false
  threshold: 0.5
  boundary_tolerance_frac: 0.0075
  save_confusion: true
```

- `stride` must be positive and no larger than `window`; smaller stride means
  more overlap, smoother tile joins, and more compute.
- In-training validation uses `tta_scales`/`tta_flip`. An empty scale list means
  exactly one `1.0` view.
- Standalone evaluation keeps TTA off unless `--tta` is supplied; `--scales`
  selects its scales and flip is included when TTA is on.
- `threshold` is the native-binary class-1 positive probability cutoff and is unused
  by multiclass argmax. It must be strictly between 0 and 1.
- `boundary_tolerance_frac` is a fraction of image diagonal. The default 0.0075
  is roughly 17 pixels at 1024x2048 and 5 pixels at 512x512.
- `save_confusion: false` reduces result size but removes the strongest metric
  audit artifact.

## Runtime and dataset switches

`segmentary-eval` supports `--stage`, `--dataset`, `--root`, `--loader`,
`--mapping`, `--variant`, `--split-file`, `--split`, JSON `--loader-options`,
positive `--limit`, `--device`, `--num-workers`, `--ema`, and `--out`.
Dataset override fields require `--dataset`. A partial `--limit` result is a
smoke test, never a full benchmark.

## Metrics

- mIoU, mean Dice/F1, mean precision, mAcc/recall, mean specificity, pixel
  accuracy, and frequency-weighted IoU;
- per-class IoU, Dice/F1, precision, recall, specificity, and ground-truth
  support;
- macro/per-class boundary precision, recall, and F1;
- full confusion matrix when enabled.

Scores use `0.0` to `1.0`. Inactive or completely absent classes serialize as
`null`, not zero, and are excluded from the mean. A supported class predicted
incorrectly can legitimately score zero.

### Native binary semantics

A native binary head emits one raw class-1 positive logit. One-view whole/sliding
inference applies sigmoid and `eval.threshold` (default 0.5). Transformed-view
TTA applies sigmoid per aligned scale/flip view, averages class-1
probabilities, then thresholds. A one-channel argmax is never used.

Predictions become canonical IDs 0/1 before metrics, so the normal two-class
confusion matrix and per-class metrics remain intact. Binary mIoU is the mean of
the scored canonical ID 0 and ID 1 IoUs, not class-1 IoU alone. Raising
the threshold predicts fewer class-1 pixels and usually trades false
positives against false negatives; select it on validation data and treat every
different threshold as a different protocol. See
[Semantic task modes](../tasks/README.md) for the full compatibility and data
contract.

## Pros and cons

- Sliding windows preserve native pixels and limit memory, but overlap repeats
  work. Whole-image inference is faster only when the complete frame fits and is
  the intended protocol.
- TTA may improve accuracy, but multiplies inference and becomes a separate
  protocol variant.
- EMA usually smooths a training trajectory, but `--ema` requires a checkpoint
  that saved the shadow state. Raw and EMA rows must not be mixed.
- `best.ckpt` is selected on validation; `last.ckpt` is the true fixed-step
  endpoint. Use one policy across a comparison.

## Mixed-stage limit

In-training validation uses only the first dataset listed in a mixed stage and
only that mapping's active classes. Run explicit standalone common-target
evaluation for every checkpoint before comparing sequential and joint curricula.

## Evidence and benchmark boundary

The fixed reference run recorded **0.805073 Cityscapes-19 mIoU** on all 500
validation images during its final in-memory EMA validation at step 40k; that is
a whole model/schedule acceptance result, not a claim that one evaluation switch
is superior. Exact
tracked context and the raw-artifact limitation are in the
[benchmark evidence page](../../../benchmarks/README.md). Numeric tests
independently verify confusion, ignore/active semantics, sliding grids, TTA,
boundary aggregation, and JSON serialization.

## Related documentation

- [Semantic task modes](../tasks/README.md)
- [Interpreting results](../../../tutorials/interpreting-results.md)
- [Evaluation and results guide](../../../guides/evaluation-and-results.md)
- [Export](../export/README.md)
- [Taxonomy catalog](../../../../taxonomy/README.md)
