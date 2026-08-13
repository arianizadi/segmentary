# Interpreting results and debugging metrics

The shortest useful answer is: Segmentary stores accuracy-like metrics as decimal
fractions from **0 to 1**. Multiply by 100 to write them as percentages.

```text
0.0000 =   0.00%
0.5000 =  50.00%
0.7500 =  75.00%
1.0000 = 100.00%
```

For example, a stored score of `0.75` renders as **75%**. It does not mean
`0.75%`. Generated result tables do the multiplication for you.

That conversion is easy. Deciding whether two numbers answer the same question
is the important part. This tutorial starts with the metric meanings, then shows
how to read a real `results.json`, recognize common failure patterns, and debug
from the cheapest checks to the most expensive ones.

## 1. Check the experiment identity before the score

Do not begin with `metrics.miou`. Begin with these fields:

| Field | Question it answers |
|---|---|
| `name`, `stage`, `seed` | Which experimental unit is this? |
| `finished_at` | Did the process finish, or is this a live/interrupted record? |
| `dataset_sizes` | Was the expected full split evaluated? |
| `config.space` | Which canonical classes and ignore rules were scored? |
| `config.evaluation.prediction` | For standalone eval, was prediction multiclass argmax or binary sigmoid, and at what threshold? |
| `config_hash` | Was the resolved configuration identical? |
| `git_sha`, `git_dirty` | Which source produced the result, and was it clean? |
| `notes` | Which checkpoint, EMA choice, and TTA choice did standalone evaluation use? |

From the repository root, inspect one record with `jq` if it is installed:

```bash
RESULT=runs/my_experiment_seed0/eval_my_dataset_val/results.json
jq '{
  name, stage, seed, finished_at, dataset_sizes,
  space: .config.space,
  config_hash, git_sha, git_dirty, notes,
  miou: .metrics.miou
}' "$RESULT"
```

`jq` is optional. Section 8 provides a Python standard-library reader that works
without adding a package. The later `jq` snippets are compact alternatives for
machines that already provide it.

If `finished_at` is `null`, the run did not reach its normal end. Its last
atomic record can still help diagnose the run, but it is not a completed result.
If `git_dirty` is `true`, inspect the source diff before trying to reproduce it.

## 2. Metric meanings and scales

For one class, the confusion counts are:

- **TP (true positive):** the class was present and predicted correctly;
- **FP (false positive):** the model predicted the class where it was not present;
- **FN (false negative):** the class was present but the model missed it.

Every IoU, accuracy, precision, recall, and F1 value below is in the inclusive
range **0 to 1**. In ordinary prose and generated tables, report `100 * value`
as a percentage.

| Metric in `results.json` | Definition | What it is good at | Main trap |
|---|---|---|---|
| `per_class_iou.<class>` | `TP / (TP + FP + FN)` | Measures overlap while penalizing both extra and missing pixels | Rare and thin classes can be volatile |
| `miou` | Arithmetic mean of scored per-class IoUs | Gives every scored class equal weight | Can hide which classes improved or failed |
| `per_class_acc.<class>` | `TP / (TP + FN)` | Per-class recall: how much of the true class was found | Does not penalize predicting too much of that class |
| `per_class_recall.<class>` | `TP / (TP + FN)` | Explicitly named alias of `per_class_acc` | Same recall-only limitation |
| `per_class_precision.<class>` | `TP / (TP + FP)` | Shows whether predictions of the class are trustworthy | Does not penalize missing the class |
| `per_class_dice.<class>` | `2 TP / (2 TP + FP + FN)` | Familiar overlap/F1 score, especially common in medical and binary segmentation | Like IoU, depends on the exact label space and split |
| `per_class_specificity.<class>` | `TN / (TN + FP)` in a one-vs-rest view | Finds classes that fire too often on everything else | Can look very high when the class is rare because negatives dominate |
| `macc` | Mean of scored per-class accuracies | Reveals missed classes better than pixel accuracy | High recall can coexist with many false positives |
| `mprecision`, `mdice`, `mspecificity` | Arithmetic means of the corresponding scored class metrics | Compact complementary views of false positives and overlap | Means still hide which class caused the change |
| `pixel_accuracy` | All correct pixels divided by all labelled pixels | Easy whole-image sanity check | Large road, sky, and background-like regions dominate it |
| `freqw_iou` | Per-class IoU weighted by ground-truth pixel frequency | Summarizes performance experienced by a random labelled pixel | Frequent classes dominate; rare rail classes barely move it |
| `boundary.macro_precision` | Matched predicted contour pixels divided by predicted contour pixels, averaged over scored classes | Detects extra or badly placed predicted boundaries | Depends on the configured matching tolerance |
| `boundary.macro_recall` | Matched ground-truth contour pixels divided by ground-truth contour pixels, averaged over scored classes | Detects missing boundaries | Depends on the configured matching tolerance |
| `boundary.macro_f1` | Harmonic mean of boundary precision and recall, averaged over scored classes | Balances missing and extra contours | A good region score can still have a poor contour score, and vice versa |

The boundary object also stores all three metrics per class. Its default
`tolerance_frac` is `0.0075`, meaning a contour can match within 0.75% of the
image diagonal. Changing that tolerance changes the metric, so compare boundary
results only under the same setting.

### A small IoU example

Suppose a class has 60 correct pixels, 20 extra predicted pixels, and 20 missed
pixels:

```text
IoU       = 60 / (60 + 20 + 20) = 0.60 = 60%
precision = 60 / (60 + 20)      = 0.75 = 75%
recall    = 60 / (60 + 20)      = 0.75 = 75%
dice/F1   = 120 / (120 + 20 + 20) = 0.75 = 75%
```

Current result records store these region metrics directly and retain the full
confusion matrix when `eval.save_confusion` is enabled. Older records may have
only IoU/accuracy/support; derive missing metrics from their confusion matrix or
rerun evaluation rather than filling them with zero.

### Loss is not an accuracy percentage

Training loss is different. Segmentary's cross-entropy and optional Dice or
Lovasz terms are objectives to minimize, not bounded accuracy scores. A loss can
be greater than 1, and `0.8` loss does **not** mean 80% accuracy. Compare loss
values only when the loss definition, weights, label space, data, and reduction
are the same. The final `results.json` stores evaluation metrics; step-by-step
training loss is in the training logs.

### Binary scores and thresholds

Native binary evaluation still builds a two-class confusion matrix using the
configured taxonomy names. Its mIoU is the mean of the scored IoUs for canonical
IDs 0 and 1, not another name for class-1 IoU. Read the positive class's
precision, recall, IoU, boundary F1, and support explicitly because an abundant
negative class can make pixel accuracy look reassuring.

The native head emits one raw class-1 positive logit. A single view applies
sigmoid and predicts canonical ID 1 at `eval.threshold` (default 0.5). TTA
averages aligned sigmoid probabilities before applying that threshold. Raising
the threshold shrinks the predicted class-1 area, often increasing precision
and reducing recall; lowering it often does the reverse. The exact metric change
depends on the data. Calibrate on validation data, freeze the threshold before
testing, and never group records with different thresholds as equivalent
protocols. See
the [semantic task contract](../catalog/components/tasks/README.md).

## 3. Practical interpretation bands

There is no universal mIoU grading scale. Dataset difficulty, class count,
label quality, image resolution, taxonomy, split, model size, pretraining, and
evaluation protocol all matter. A 40% IoU on a rare three-pixel-wide rail class
may be useful, while 90% on an easy two-class task may be weak.

The following bands are **debugging heuristics, not research standards**. Use
them only to decide what to inspect next. A valid same-protocol baseline is
always a better reference.

| IoU or mIoU | Diagnostic reading | What to do next |
|---:|---|---|
| Exactly `0.00` | No correct overlap for a scored class | Check whether the model never predicts it, predicts it in the wrong places, or the mapping is wrong |
| `0.00`–`0.20` | Very weak overlap | Inspect overlays, IDs, active masks, class support, and logits before tuning |
| `0.20`–`0.40` | Partial but poor overlap | Look at the dominant confusions and precision/recall balance |
| `0.40`–`0.60` | Meaningful partial segmentation | Improvements may now depend on data, class balance, boundaries, and model capacity |
| `0.60`–`0.80` | Often a useful or strong result on a challenging multiclass task | Compare per class and across seeds; do not rely on the aggregate alone |
| `0.80`–`0.95` | Often very strong | Verify the split and protocol, then compare with a matching baseline or published recipe |
| `0.95`–`1.00` | Near-perfect overlap | Expected for an eight-image memorization test; investigate leakage or an overly easy/partial eval if seen unexpectedly on validation |

Never turn these bands into labels such as “state of the art.” A research claim
requires the same dataset, split, class space, inference protocol, checkpoint
rule, and a suitable baseline.

## 4. `null`, zero, support, and ignored pixels

`null` and `0.0` do not mean the same thing.

- **`null`: not scored.** Internally this is NaN. An inactive class, or an active
  class absent from both ground truth and predictions, has no IoU denominator
  and is excluded from the mean.
- **`0.0`: scored and failed.** The class appeared in the ground truth or the
  prediction, but there was no correct intersection.
- **Positive value:** scored with at least some overlap.

There is one useful asymmetry: if a class has no ground-truth pixels but the
model predicts it, its IoU is zero because those predictions are false
positives. Its per-class accuracy is `null` because recall has no ground-truth
denominator.

`metrics.support.<class>` is the number of ground-truth pixels for the class
after ignore handling. Support is context, not a score:

- large support usually makes a metric more stable;
- small support means a few images or pixels can move the score sharply;
- support zero plus IoU zero means the model hallucinated that class;
- support zero plus IoU `null` means neither target nor prediction contained it.

Pixels with the canonical ignore value `255` are excluded before the confusion
matrix is built. They do not count as correct background and do not enter any of
these metrics.

Print every class with its support, IoU, and recall:

```bash
RESULT=runs/my_experiment_seed0/eval_my_dataset_val/results.json
jq -r '
  .metrics as $m
  | $m.per_class_iou
  | keys[]
  | [., $m.support[.], $m.per_class_iou[.], $m.per_class_acc[.]]
  | @tsv
' "$RESULT"
```

Print the lowest scored classes first while keeping `null` out of the ranking:

```bash
jq -r '
  .metrics as $m
  | $m.per_class_iou
  | to_entries
  | map(select(.value != null))
  | sort_by(.value)[]
  | [.key, (.value * 100), $m.support[.key]]
  | @tsv
' "$RESULT"
```

The three columns are class, IoU percentage, and ground-truth pixel support.

## 5. Aggregate traps

No single aggregate is enough for semantic segmentation.

### High pixel accuracy can hide failed rare classes

A model can label frequent background regions correctly while missing every
small or thin object. Those frequent regions keep `pixel_accuracy` and
`freqw_iou` high. mIoU is better because every scored class gets equal weight,
but even mIoU can hide whether the particular classes central to the experiment
improved.

Always read at least:

1. mIoU;
2. the task-critical class IoUs;
3. class support;
4. boundary F1, precision, and recall;
5. variation across seeds.

### Means can change when the scored class set changes

Segmentary excludes `null` classes from macro means. Therefore, two records can
average a different set of classes even if both say `miou`. Compare the same
canonical space, dataset mapping, split, and active-class policy. Do not compare
scores from different spaces as though they measure the same task. For example,
the bundled `rail_union` score is not a standard Cityscapes-19 score.

### Support-weighted and class-weighted metrics answer different questions

- `pixel_accuracy` and `freqw_iou` emphasize frequent pixels.
- `macc`, `miou`, and boundary macro metrics give each scored class equal weight.
- Per-class metrics answer whether the particular target class works.

None is universally best. Use the one that matches the question and report the
others as safeguards against a misleading aggregate.

## 6. Training-stage, native, and common-target results

Segmentary can write several scientifically different records.

### Training-stage record

Training writes `runs/<experiment>_seed<seed>/<stage>/results.json`. Its `stage`
is a curriculum stage name such as `cityscapes` or `railsem19`, and its metrics
come from the most recent in-training validation. Validation uses EMA when EMA
is enabled. In a mixed stage, the validation dataset is the first dataset listed
for that stage, and its mapping alone defines which classes are scored.

This record is useful for monitoring the stage's native target. It should not be
silently treated as a common cross-curriculum endpoint.

### Native standalone evaluation

`python -m segmentary.eval` writes a record whose stage looks like
`eval:cityscapes:val` or `eval:railsem19:val`. A native evaluation scores a
checkpoint on the dataset naturally associated with that experiment or stage.
It is the cleanest way to reproduce the score for one explicit checkpoint.

### Common-target evaluation

A common evaluation scores **every** experiment on the same dataset and exact
split. This makes otherwise different curricula comparable on one target. A
source-only model's score is a zero-shot domain-transfer endpoint; models
trained on that target have an in-domain endpoint. The bundled rail experiments
are one concrete example of this general protocol.

“Common” is a protocol and directory convention, not a special JSON metric.
Confirm it from `stage`, `dataset_sizes`, `notes`, embedded config, and the
launch command. A folder name alone is not proof.

### Native and common scores may legitimately differ

The cause may be:

- a different dataset or split;
- different class support or active classes;
- domain shift;
- a different checkpoint (`best.ckpt` versus `last.ckpt`);
- EMA versus raw weights;
- TTA versus no TTA;
- a partial `--limit` smoke evaluation.

Resolve those differences before treating the gap as a model effect.

## 7. Best, last, EMA, raw, and TTA

These choices produce different models or inference protocols.

| Choice | Meaning | Advantage | Cost or risk |
|---|---|---|---|
| `best.ckpt` | Checkpoint saved at the highest observed validation mIoU | Good deployment candidate for that same validation target | Selection is biased toward that validation target and may use fewer steps |
| `last.ckpt` | Exact state at the configured final optimizer step | Fixed training budget; clean curriculum handoff | May score below an earlier validation peak |
| `--ema` | Load the checkpoint's exponential moving average shadow | Usually smoother and matches current in-training validation | Requires saved EMA state; it is a different weight set from raw |
| no `--ema` | Load raw optimizer weights | Supports raw-only legacy artifacts and raw-vs-EMA analysis | Does not match EMA-based in-training validation |
| `--tta` | Average multi-scale and flipped predictions | Can improve robustness and score | Multiplies inference work and changes the protocol |
| no `--tta` | One configured inference view | Fast, reproducible baseline | May be lower than a separately reported TTA result |

The training-stage `results.json` describes its most recent validation; it is
not automatically a re-evaluation of `best.ckpt`. For a table of exact
artifacts, evaluate each chosen checkpoint explicitly and keep one checkpoint
policy across the table.

For fixed-budget curriculum research, `last.ckpt --ema` with no TTA is a useful
default. For deployment selection on one fixed target, `best.ckpt --ema` may be
appropriate. The important rule is to state the choice and never mix policies
inside one comparison.

## 8. Read a result without `jq`

The following command uses only Python's standard library and matches the
actual Segmentary schema:

```bash
RESULT=runs/my_experiment_seed0/eval_my_dataset_val/results.json
python - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
record = json.loads(path.read_text())
metrics = record["metrics"]

def percent(value):
    return "n/a" if value is None else f"{100 * value:.2f}%"

print(f"file:        {path}")
print(f"experiment:  {record['name']}")
print(f"stage:       {record['stage']}")
print(f"seed:        {record['seed']}")
print(f"finished:    {record['finished_at']}")
print(f"dataset:     {record['dataset_sizes']}")
print(f"git:         {record['git_sha'][:12]} dirty={record['git_dirty']}")
print(f"notes:       {record['notes']}")
print(f"mIoU:        {percent(metrics['miou'])}")
print(f"mean Dice:   {percent(metrics.get('mdice'))}")
print(f"mean prec:   {percent(metrics.get('mprecision'))}")
print(f"mAcc:        {percent(metrics['macc'])}")
print(f"pixel acc:   {percent(metrics['pixel_accuracy'])}")
print(f"freqw IoU:   {percent(metrics['freqw_iou'])}")
print(f"boundary F1: {percent(metrics['boundary']['macro_f1'])}")

print("\nPer-class scores, lowest IoU first:")
items = sorted(
    metrics["per_class_iou"].items(),
    key=lambda item: (item[1] is None, item[1] if item[1] is not None else 0.0),
)
for name, iou in items:
    support = metrics["support"][name]
    recall = metrics["per_class_acc"][name]
    precision = metrics.get("per_class_precision", {}).get(name)
    dice = metrics.get("per_class_dice", {}).get(name)
    print(
        f"  {name:18s} IoU={percent(iou):>8s} "
        f"Dice={percent(dice):>8s} precision={percent(precision):>8s} "
        f"recall={percent(recall):>8s} support={support:,}"
    )
PY
```

For generated mean and sample-standard-deviation tables, use the checked table
builder instead of copying values:

```bash
segmentary-table \
  --runs runs/my_campaign \
  --out docs/results/my_campaign
```

It rejects malformed records, duplicate seeds, mismatched config hashes,
non-seed config differences, and mixed Git provenance instead of silently
building a misleading aggregate.

Discovery is limited to `**/results.json` below `--runs`. Store every full
evaluation intended for a table in its own descriptive directory with that
exact filename.

## 9. Symptom-to-cause guide

The patterns below are starting hypotheses. Confirm them with per-class values,
support, overlays, and the confusion matrix before changing the experiment.

| Pattern | Likely meaning | First checks |
|---|---|---|
| High pixel accuracy, much lower mIoU | Frequent classes work while rare classes fail | Sort per-class IoU; inspect support; check task-critical classes and active masks |
| mAcc much higher than mIoU | The model finds much of each true class but overpredicts classes, creating false positives | Derive per-class precision; inspect column-normalized confusion and predicted area |
| Both mAcc and mIoU low | Classes are mostly missed or confused | Inspect row-normalized confusion, labels, logits, and data overlays |
| Rare class is `0.0` | It was scored but had no correct overlap | Check support, predictions, class ID mapping, and whether it is confused with a related class |
| Rare class is `null` | It was inactive or absent from both target and prediction | Confirm the mapping and split; do not replace it with zero |
| Good region IoU, weak boundary F1 | Regions are broadly right but contours are displaced, thick, coarse, or fragmented | Compare per-class boundary precision/recall; inspect full-resolution overlays and resize alignment |
| Weak region IoU, good boundary F1 | Some contours align within tolerance, but interiors, extent, or class identity are wrong | Check predicted area, false positives, tolerance, and region confusion |
| Boundary precision low, recall high | Too many or overly thick/spurious predicted contours | Inspect predicted contour counts and false-positive regions |
| Boundary precision high, recall low | Conservative prediction misses many true contours | Inspect false negatives and small disconnected structures |
| Binary class-1 precision low, recall high | Threshold may be permissive, the model may be poorly calibrated, or class-0 supervision may be wrong | Check exact ID semantics, taxonomy/active masks, and overlays first; then evaluate a validation-only threshold sweep |
| Binary class-1 precision high, recall low | Threshold may be conservative or small/weak positives are missed | Check support, ignored pixels, and logits; then evaluate a validation-only threshold sweep |
| Tiny-train score rises, validation stays low | Overfitting, domain/split mismatch, or augmentation/regularization issue | Confirm leakage-safe split, compare train-like and validation overlays, then tune regularization |
| Training loss falls, mIoU stays flat | Confidence improves without changing argmax, frequent classes dominate loss, LR is ineffective for the head/backbone, or labels/logits are misaligned | Read per-class metrics, check predicted class histogram and gradients, run the eight-image overfit check |
| Loss is NaN or infinite | Numerical instability, corrupt inputs/weights, bad LR, or nonfinite model output | Find the first bad step; check image/logit/gradient finiteness and LR; do not debug only the final checkpoint |
| JSON metric is `null` | Usually an intentionally unscored class, not numerical failure | Check support and active mapping; distinguish it from a nonfinite training loss |
| Large spread across seeds | Result is optimization- or sample-sensitive, or the effect is smaller than noise | Verify identical configs/provenance; inspect paired seed deltas; run more seeds before claiming a small effect |
| EMA clearly better than raw | Raw updates are noisy; averaging stabilizes the endpoint | Confirm same checkpoint and protocol; use EMA consistently if it is the declared policy |
| EMA clearly worse than raw | EMA may lag rapid late learning, decay may be too slow, or comparison inputs differ | Confirm same artifact/TTA/split; inspect validation through time before changing decay |
| Common-target score is below native score | Domain shift or different class/split difficulty, not automatically a bug | Align checkpoint, EMA, TTA, space, split, and dataset sizes; then inspect domain-specific classes |
| Native and common scores disagree on the same target | Protocol or artifact mismatch is more likely than domain shift | Compare `notes`, `stage`, config hash, split file, limit, checkpoint, and EMA/TTA flags |

## 10. Cheapest-first debugging flow

Stop as soon as a step explains the result. Changing five settings at once makes
the next result harder to interpret.

### Step 1: preserve the evidence

Do not overwrite the record or reuse its run directory. Save the exact command
and log, then inspect Git state:

```bash
git status --short
git rev-parse HEAD
```

### Step 2: inspect record identity and completion

Run the identity `jq` command from section 1. Confirm `finished_at`, expected
dataset size, seed, space, Git SHA, dirty flag, and notes. A surprising
`dataset_sizes` value often exposes `--limit`, a wrong split, or an incomplete
dataset immediately.

### Step 3: prove the comparison is like-for-like

For every record in the comparison, check:

1. exact dataset root and split file;
2. canonical label space and mapping variant;
3. sliding-window size and stride;
4. boundary tolerance;
5. best versus last checkpoint policy;
6. EMA versus raw weights;
7. TTA setting and scales;
8. seed set, config hash, Git SHA, and training budget.

If any item differs, label it as a separate protocol instead of explaining the
delta as a model improvement.

### Step 4: inspect per-class support and confusions

Use the lowest-class commands above. Decide whether the aggregate problem is one
class, all rare classes, or the whole model. Compare semantically related
confusions before tuning global settings.

### Step 5: inspect real images and mappings

Run the dataset verifier and open several generated overlays:

```bash
segmentary-verify \
  --dataset my_dataset \
  --loader folder \
  --mapping my_dataset \
  --root data \
  --space my_space \
  --taxonomy taxonomy
```

Look for wrong colors, shifted masks, interpolated label IDs, padding counted as
a class, flipped image/mask disagreement, and adjacent frames split across train
and validation. A clean loss curve cannot prove labels are semantically correct.

### Step 6: run the eight-image memorization check

Use a free GPU:

```bash
segmentary-overfit base.yaml model.yaml experiment.yaml \
  --images 8 --target 0.95 --device cuda:0
```

The intended check must reach its configured tiny-set threshold on the same
eight images. Failure points
to model/loss/mapping/optimizer wiring, not generalization. Passing does not
prove that the validation split or research protocol is correct.

### Step 7: run a small standalone evaluation

Use `--limit` only to prove that a checkpoint loads and the evaluator finishes.
Do not compare its metric with a full validation result because class support
and image composition changed.

```bash
segmentary-eval base.yaml model.yaml experiment.yaml \
  --ckpt runs/my_experiment_seed0/train_my_data/last.ckpt \
  --seed 0 \
  --ema \
  --limit 4 \
  --out debug/eval_limit4.json \
  --device cuda:0
```

The deliberately different `debug/eval_limit4.json` filename keeps this partial
smoke record outside `segmentary-table` discovery. Do not rename a limited result
to `results.json` under a campaign root.

### Step 8: isolate one hypothesis

Only now test one named change: raw versus EMA, a different checkpoint, one
mapping variant, one LR change, or one loss change. Keep the same evaluation
target and write to a new result file.

### Step 9: rerun the full evaluation, then multiple seeds

Once the cause is fixed or the hypothesis is clear, evaluate the full split.
For research comparisons, run the planned seed set and generate the table from
all records. Do not use a favorable single seed to settle a small delta.

## 11. Advanced confusion-matrix analysis

When `config.eval.save_confusion` is true, `metrics.confusion` is a square matrix
whose **rows are ground-truth classes** and **columns are predicted classes**.
Do not obtain class order from JSON dictionary order: result keys are sorted
when written, while matrix order comes from the canonical taxonomy.

Run this from the repository root with the project environment:

```bash
export PYTHONPATH=src
RESULT=runs/my_experiment_seed0/eval_my_dataset_val/results.json
python - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

import numpy as np

from segmentary.taxonomy import load_space

path = Path(sys.argv[1])
record = json.loads(path.read_text())
metrics = record["metrics"]
if "confusion" not in metrics:
    raise SystemExit("this record has no confusion matrix; enable eval.save_confusion")

space = load_space(record["config"]["taxonomy_root"], record["config"]["space"])
names = list(space.names)
cm = np.asarray(metrics["confusion"], dtype=np.int64)
if cm.shape != (len(names), len(names)):
    raise SystemExit(f"confusion shape {cm.shape} does not match {len(names)} classes")

tp = np.diag(cm).astype(np.float64)
gt = cm.sum(axis=1).astype(np.float64)
pred = cm.sum(axis=0).astype(np.float64)
precision = np.divide(tp, pred, out=np.full_like(tp, np.nan), where=pred > 0)

# Use Segmentary's reported values for IoU/recall so inactive classes remain
# unscored. A raw confusion-derived IoU would incorrectly turn an inactive
# class predicted by the model into a displayed 0 instead of the recorded null.
iou = np.asarray(
    [
        np.nan if metrics["per_class_iou"][name] is None else metrics["per_class_iou"][name]
        for name in names
    ],
    dtype=np.float64,
)
recall = np.asarray(
    [
        np.nan if metrics["per_class_acc"][name] is None else metrics["per_class_acc"][name]
        for name in names
    ],
    dtype=np.float64,
)
scored = np.isfinite(iou)
precision = np.where(scored, precision, np.nan)

print("Per-class region diagnostics:")
order = sorted(
    range(len(names)),
    key=lambda index: (not scored[index], iou[index] if scored[index] else 0.0),
)
for index in order:
    name = names[index]
    scores = (
        f"IoU={iou[index]:7.2%} precision={precision[index]:7.2%} "
        f"recall={recall[index]:7.2%}"
        if scored[index]
        else "unscored (inactive or absent from target and prediction)"
    )
    print(
        f"{name:18s} support={int(gt[index]):12,d} "
        f"predicted={int(pred[index]):12,d} "
        f"{scores}"
    )

off_diagonal = cm.copy()
np.fill_diagonal(off_diagonal, 0)
print("\nLargest ground-truth -> predicted confusions:")
for flat_index in np.argsort(off_diagonal, axis=None)[::-1][:20]:
    row, column = np.unravel_index(flat_index, off_diagonal.shape)
    count = int(off_diagonal[row, column])
    if count == 0:
        break
    share = count / gt[row] if gt[row] else float("nan")
    print(
        f"{names[row]:18s} -> {names[column]:18s} "
        f"{count:12,d} pixels ({share:7.2%} of true {names[row]})"
    )
PY
```

How to read it:

- **row normalization** asks, “Where did the true class go?” and exposes false
  negatives or class confusion;
- **column normalization** asks, “What made up this predicted class?” and
  exposes false positives;
- an unscored class can still have predicted pixels in the raw confusion matrix;
  keep its reported IoU `null`, then inspect those predictions as confusions
  rather than silently changing the metric's active-class policy;
- `predicted / support` much greater than 1 suggests overprediction;
- `predicted / support` much less than 1 suggests conservative underprediction;
- one dominant off-diagonal pair suggests a taxonomy or visual-confusion issue;
- diffuse errors across many columns suggest a broader representation, data, or
  optimization problem.

Counts matter. A million-pixel confusion can dominate deployment behavior even
if its class-normalized fraction is modest, while a 100-pixel class can swing
wildly between seeds.

## 12. Boundary details for thin structures

For each class, inspect:

- `boundary.per_class_f1`;
- `boundary.per_class_precision`;
- `boundary.per_class_recall`;
- `boundary.gt_contour_pixels`;
- `boundary.pred_contour_pixels`.

Print them with:

```bash
RESULT=runs/my_experiment_seed0/eval_my_dataset_val/results.json
jq -r '
  .metrics.boundary as $b
  | $b.per_class_f1
  | keys[]
  | [
      .,
      $b.per_class_f1[.],
      $b.per_class_precision[.],
      $b.per_class_recall[.],
      $b.gt_contour_pixels[.],
      $b.pred_contour_pixels[.]
    ]
  | @tsv
' "$RESULT"
```

A class present only in predicted or true contours is scored zero. A class with
no contour in either is `null` and excluded from the macro boundary mean. Read
contour counts alongside F1: a score based on very few contour pixels is less
stable than one supported across the full split.

Boundary F1 does not replace IoU. Report both because a rail can occupy roughly
the right region while being too thick, or have an approximately aligned edge
while its interior and class identity remain wrong.

## 13. Seeds and paired comparisons

With more than one seed, Segmentary's table generator shows one mean. Machine
records retain the individual per-seed values so you can inspect consistency
without adding spread notation to the public table.

For two curricula run with the same seeds, also inspect paired differences:

```text
delta(seed 0) = mIoU(B, seed 0) - mIoU(A, seed 0)
delta(seed 1) = mIoU(B, seed 1) - mIoU(A, seed 1)
delta(seed 2) = mIoU(B, seed 2) - mIoU(A, seed 2)
```

An average gain is more convincing when the paired direction agrees across
seeds and the per-class/boundary evidence tells the same story. If one seed
drives the entire gain, report that instability and gather more evidence rather
than hiding it in the mean.

Seeds are optimizer/data-order replicates on the same committed split. They are
not cross-validation folds unless the split itself changes by a documented
cross-validation design.

## 14. A result is ready to report when

- the record is finished and points to the intended full dataset size;
- the source SHA, dirty state, config, seed, and environment are recorded;
- dataset, split, class space, checkpoint, EMA, TTA, and inference settings are
  identical across the comparison;
- mIoU is accompanied by relevant per-class IoU, support, and boundary metrics;
- multiple seeds are summarized from `results.json`, not copied by hand;
- training budgets and any unequal stage lengths are disclosed;
- zero is not confused with `null`;
- a partial `--limit` evaluation is labelled as a smoke test, not a benchmark;
- the visual overlays and confusion patterns agree with the numeric story;
- claims are phrased relative to a same-protocol baseline, not the heuristic
  bands in this tutorial.

Next, read [Evaluation, results, and fair comparisons](../guides/evaluation-and-results.md)
for the exact evaluation commands and [Troubleshooting and reproducibility](../guides/troubleshooting.md)
for operational failures outside metric interpretation.
