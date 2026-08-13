# Evaluation, results, and fair comparisons

The main rule is simple: a number is comparable only when the checkpoint,
dataset split, label space, image protocol, EMA/TTA choice, and code provenance
are all explicit.

If you are new to the metric scale or diagnosing a surprising pattern, read
[Interpreting results and debugging metrics](../tutorials/interpreting-results.md)
first. It explains percentage conversion, `null` versus zero, practical
heuristics, and confusion-matrix debugging.

## Evaluate a run

```bash
segmentary-eval \
  base.yaml model.yaml experiment.yaml \
  --ckpt runs/my_experiment_seed0/target/last.ckpt \
  --seed 0 --ema \
  --out runs/my_experiment_seed0/eval_target_val/results.json
```

- `--ema` loads the persisted shadow weights and fails if they do not exist.
- Without `--ema`, raw training weights are evaluated.
- `--stage NAME` chooses which configured stage supplies dataset settings.
- `--limit N` is useful for a smoke test, never a substitute for full validation.
- The default is native-resolution sliding-window evaluation with no TTA.

### Native binary prediction

A binary run must use exactly canonical IDs 0 and 1, but their taxonomy names
may be domain-specific. ID 1 is the positive class, and the native head returns
one raw class-1 logit. The default `eval.threshold: 0.5` means:

```text
class_1_probability = sigmoid(class_1_logit)
prediction = 1 if class_1_probability >= threshold else 0
```

Sliding-window evaluation first averages overlapping logits for that view, then
applies sigmoid. Scale/flip TTA applies sigmoid to every aligned view and
averages probabilities before thresholding. Segmentary never applies `argmax` to
the one-channel tensor. See the [task contract](../catalog/components/tasks/README.md)
before constructing a binary taxonomy or changing the threshold.

## Cross-dataset evaluation

Use a common target to compare curricula whose native validation datasets differ:

```bash
segmentary-eval \
  base.yaml model.yaml experiment.yaml \
  --ckpt runs/my_experiment_seed0/source/last.ckpt \
  --seed 0 --ema \
  --dataset common_target \
  --root data/common_target \
  --loader folder \
  --mapping common_schema \
  --split val \
  --out runs/my_experiment_seed0/common_target/results.json
```

This is a zero-shot score when the model never trained on `common_target`. For
curricula that did train on it, the identical override produces a fair in-domain
endpoint on the same images. Keep each training seed in `--seed`; it becomes part
of the embedded config hash.

## TTA

```bash
segmentary-eval \
  base.yaml model.yaml experiment.yaml \
  --ckpt runs/my_experiment_seed0/target/last.ckpt \
  --seed 0 \
  --ema \
  --tta \
  --scales 0.75 1.0 1.25 1.5 \
  --out runs/my_experiment_seed0/eval_target_val_tta/results.json
```

TTA can improve accuracy by averaging multiple views, but multiplies inference
cost and changes the protocol. Label it as a separate result; never replace the
baseline file or mix TTA and no-TTA seeds in one aggregate.

For binary TTA specifically, the averaged values are class-1 probabilities,
not raw logits. This preserves the meaning of `eval.threshold` across whole,
sliding-window, and transformed-view inference.

## What `results.json` contains

Every record includes:

- experiment/stage identity and seed;
- the full resolved config plus stable config hash;
- git SHA and dirty flag;
- environment versions and dataset sizes;
- start/end time, wall-clock duration, and peak VRAM;
- mIoU, mAcc, pixel and frequency-weighted accuracy;
- per-class IoU/accuracy/support;
- boundary F1 details and, by default, the confusion matrix.

Standalone evaluation also records prediction semantics under
`config.evaluation.prediction`: the task, activation (`sigmoid` for binary), and
the numeric binary threshold. A multiclass record stores a null threshold.

Inactive classes, and active classes absent from both ground truth and
predictions, are JSON `null` (internally NaN), not zero. An active class that is
absent from ground truth but predicted anyway has IoU zero. Zero therefore means
the class was evaluable and failed; null means the protocol had nothing to score.

## Generate tables

```bash
segmentary-table \
  --runs runs/my_campaign \
  --out docs/results/my_campaign
```

Use an exact stage filter when the campaign also contains native training-stage
records but the comparison must use one shared endpoint:

```bash
segmentary-table \
  --runs runs/my_campaign \
  --out docs/results/my_campaign_common \
  --stage eval:my_dataset:val
```

`--stage` and `--experiment` are repeatable. They are presentation filters, not
validation bypasses: all discovered records are validated before filtering.

The table builder discovers only files named `results.json` (the
`**/results.json` pattern) below `--runs`. Store each explicit checkpoint,
dataset, split, EMA/raw, and TTA/no-TTA evaluation in its own descriptive
directory. A file such as `eval.json` is valid evaluator output but is not table
input.

The script displays the mean for mIoU, mean class accuracy, pixel accuracy,
boundary F1, and requested per-class IoUs when more than one seed exists.
Machine records retain every per-seed value. It fails closed on malformed records, duplicate seeds,
mismatched config hashes, config differences beyond seed, mixed git provenance,
dirty multi-seed groups, or a class missing for only some seeds.

Generate tables from one campaign root. Scanning all historical runs can mix old
protocols and intentionally dirty calibration artifacts.

## Read the metrics

- **mIoU:** equal weight per scored class. Good headline, but the mean can hide
  task-critical failures.
- **Per-class IoU:** primary evidence for the classes your application values.
- **Boundary F1:** measures contour placement within a tolerance; especially
  useful for thin or small structures.
- **mAcc:** average class recall; reveals whether a model ignores rare classes.
- **Pixel accuracy:** dominated by frequent regions; never use it alone.
- **Support:** number of ground-truth pixels; essential context for volatile rare
  classes.

For binary evaluation, the confusion matrix still has two canonical classes.
Canonical IDs 0 and 1 each receive their own IoU using the configured taxonomy
names, and mIoU is their equal-weight mean when both are scorable—not class-1
IoU by another name.
All reported score scales remain 0 to 1. If a class is absent from both target
and prediction it is `null` and excluded under the shared absent-class rule.
When class 0 dominates pixel count, read class-1 IoU, recall,
precision, boundary F1, and support beside pixel accuracy and mIoU.

### Threshold comparisons

Raising the binary threshold can only shrink the predicted class-1 set. It
often trades fewer false positives for more false negatives; the best IoU or
application operating point is not knowable from the default alone. Select a
threshold on a validation/calibration split while holding checkpoint, EMA/raw,
TTA, image protocol, and code fixed. Then freeze the rule before the test split.
Different thresholds are different evaluation protocols and must not be pooled
in one seed aggregate.

## Best versus final checkpoints

- `best.ckpt` is selected by the stage's validation metric and is useful for a
  deployment model on that same validation target.
- `last.ckpt` is the true fixed-step endpoint and is safer for cross-curriculum
  research when best checkpoints were selected on different datasets.

Do not mix the two policies inside one table. The current curriculum explicitly
writes `last.ckpt` after fit and tests its optimizer step and EMA counter.

## Fair-comparison checklist

Before interpreting a delta, confirm:

1. same target dataset and exact split;
2. same canonical label space and active-class policy;
3. same native/sliding-window settings and boundary tolerance;
4. all EMA or all raw; all TTA or all no-TTA;
5. same final/best checkpoint rule;
6. same seed set and clean code SHA;
7. training budgets and effective batches are disclosed;
8. the displayed mean is generated from the retained per-seed records;
9. paired per-seed directions agree before making a strong claim;
10. task-critical per-class and boundary results support the overall mIoU story.
