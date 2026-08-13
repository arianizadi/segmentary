# Semantic task modes

The task mode decides what one output channel means, which activation converts
raw logits to probabilities, and how probabilities become canonical class IDs.
Segmentary currently has two complete dense semantic-segmentation paths:
multiclass for all supported model integrations, and binary for Segmentary-native
models.

## Beginner choice

Use `multiclass` unless the problem has exactly two mutually exclusive semantic
classes and one can be designated the positive class. A binary experiment can
use domain-specific names such as this:

```yaml
# taxonomy/tumor_binary/canonical.yaml
name: tumor_binary
description: Tumor versus non-tumor tissue.
ignore_index: 255
classes:
  - {id: 0, name: background, color: [30, 30, 30]}
  - {id: 1, name: tumor, color: [220, 60, 60]}
thin_classes: []
```

The IDs—not specific names—define the binary contract. Canonical ID 0 is the
negative class, and canonical ID 1 is always the positive class represented by
the sigmoid probability and `eval.threshold`. Names may be any unique taxonomy
labels (`background`/`tumor`, `dry`/`wet`, `non_rail`/`rail`, and so on).
Reversing the IDs changes the meaning of the probability and checkpoint. Every
dataset mapping must make both classes active:

```yaml
# taxonomy/tumor_binary/my_dataset.yaml
space: tumor_binary
dataset: my_dataset
source: Native masks already store 0=background and 1=tumor.
default: 255
map:
  0: 0
  1: 1
```

A minimal task override layered after a shipped native model recipe is:

```yaml
name: tumor_binary_baseline
space: tumor_binary

model:
  arch: native
  native:
    task: binary

loss:
  task: binary
  activation: auto
  terms:
    - kind: binary_cross_entropy
      weight: 1.0

eval:
  threshold: 0.5

stages:
  - name: train
    data:
      - name: my_dataset
        root: data/my_dataset
        loader: folder
        mapping: my_dataset
```

For example, merge that file after
`configs/models/native_resnet18_fpn_segformer_aux.yaml`. Both
`model.native.task` and `loss.task` must be `binary`; a mismatch stops before
training.

## Binary is not two-class multiclass

Both modes predict canonical IDs 0 and 1, but their tensor and probability
contracts differ:

| detail | binary | two-class multiclass |
|---|---|---|
| canonical taxonomy | exactly IDs 0 and 1; names are arbitrary; ID 1 is positive | any two canonical classes |
| raw model output | `(N,1,H,W)` | `(N,2,H,W)` |
| probability | `sigmoid(class_1_logit)` | two-channel softmax |
| prediction | canonical ID 1 when probability is at least `eval.threshold` | `argmax` over two channels |
| runnable model integration | `native` only | all supported multiclass integrations |
| main baseline loss | binary cross-entropy | cross-entropy |

For a raw class-1 logit `z`, binary inference computes
`p(class_1) = sigmoid(z)`. It emits canonical ID 1 when
`p(class_1) >= threshold` and ID 0 otherwise. Applying `argmax` to one channel
would always produce zero, so Segmentary rejects that interpretation.

The one-logit form uses a smaller classifier and gives an explicit operating
threshold. The two-logit form is the established path for arbitrary class
semantics and every non-native integration. They are different experiments:
checkpoints and output heads are not interchangeable even when both end in IDs
0 and 1.

## Dataset and active-class contract

Dataset masks remain integer `(N,H,W)` labels containing only canonical 0,
canonical 1, or ignore 255 after mapping. The taxonomy mapping first produces
the normal canonical active mask `(2,)` for one dataset or `(N,2)` for a batch.
Every row must be exactly `[true, true]`.

Only after that check does training collapse the canonical active mask to the
single output-channel shape `(1,)` or `(N,1)`. This is deliberately strict. A
one-logit model cannot distinguish “the positive class is unannotated” from
“this pixel is a supervised class-0 negative,” so allowing either canonical
class to be inactive would silently create incorrect supervision.

Consequences:

- every stage dataset and every member of a mixed stage must label both classes;
- mapping either complete semantic class to ignore makes the dataset
  incompatible with binary mode;
- 255 pixels may still be ignored locally inside an otherwise valid mask;
- non-0/1 canonical IDs, incomplete active masks, or one/two-channel model
  mismatches fail closed. Domain-specific class names are valid.

## Whole-image, sliding-window, and TTA inference

`eval.threshold` defaults to `0.5` and must be a finite probability strictly
between 0 and 1.

- **One view:** whole-image inference or overlapping sliding windows produce one
  raw class-1-logit map. Sliding windows average overlapping logits. Segmentary
  then applies sigmoid once and thresholds the probability.
- **Transformed views:** each scale/flip view first produces its aligned logit
  map, then applies sigmoid. Segmentary averages class-1 probabilities across
  views and thresholds the mean. It does not average transformed logits and it
  never uses one-channel argmax.

This distinction matters because logits from differently transformed inputs do
not have a shared calibration scale. TTA also changes the evaluation protocol
and cost, so keep TTA and no-TTA results separate.

## Metrics and interpreting a binary result

Prediction is converted back to canonical IDs before metric updates. Evaluation
therefore retains the normal two-class confusion matrix and reports separate
IoU, Dice/F1, precision, recall, specificity, boundary metrics, and support for
the two names in the configured taxonomy.

All score values range from 0 to 1. Binary mIoU is the equal-weight mean of the
scored class-0 and class-1 IoUs; it is not class-1 IoU alone. If class 0
dominates pixel count, pixel accuracy can look reassuring, so always read the
positive class's IoU/recall and support beside mIoU. Under the shared metric
contract, an active class absent from both target and prediction is `null` and
excluded from a mean rather than changed to zero.

Standalone `results.json` records the task, `sigmoid` activation, and threshold
under `config.evaluation.prediction`. The full resolved config and config hash
also preserve the model/loss task choices. Do not combine different thresholds
inside one comparison as though only training changed.

## Advanced threshold selection

The default `0.5` is the neutral starting point, not a claim that it is optimal.
Increasing the threshold can only reduce the set of predicted class-1 pixels;
it often reduces false positives while increasing false negatives.
Lowering it does the reverse. The effect on IoU, precision, recall, and boundary
F1 is dataset-dependent.

Choose a threshold on a validation/calibration split, record the selection rule,
then evaluate it once on an untouched test split. Do not select a threshold on
the test set. For an honest sweep:

1. keep the checkpoint, split, image protocol, EMA/raw policy, and TTA fixed;
2. examine class-1 precision/recall, IoU, boundary F1, and application costs;
3. record every tried threshold or the deterministic search procedure;
4. store each selected-threshold evaluation as a separately named result;
5. use the same threshold-selection procedure for every compared model.

`pos_weights` in binary cross-entropy changes training pressure; the evaluation
threshold changes the operating point after training. They are related through
calibration but are not substitutes for one another.

## Pros and cons

Binary advantages:

- one output logit and a direct class-1 positive probability;
- explicit precision/recall operating-point control;
- every native dense and auxiliary head follows the same one-channel contract;
- whole, sliding-window, and TTA prediction share one checked conversion path.

Binary disadvantages:

- it cannot represent more than two mutually exclusive classes;
- it fixes canonical ID 1 as positive and requires complete supervision of both
  classes;
- thresholds add a protocol choice that must be calibrated and reported;
- pretrained multiclass task heads are not shape-compatible;
- the end-to-end path is currently limited to native models.

## Compatibility matrix

| component or path | binary status | boundary |
|---|---|---|
| native dense heads and named auxiliary heads | supported | exactly one raw class-1 positive logit each |
| native OCR primary head | supported | one-logit refined/coarse outputs; internal centered negative/positive proxy convention, not a learned two-logit equivalent |
| native whole/sliding inference | supported | sigmoid once after the view's logits are assembled |
| native scale/flip TTA | supported | average aligned sigmoid probabilities |
| Lightning training/validation and standalone evaluation | supported | exact taxonomy and active-mask checks apply |
| dense BCE and compatible sigmoid terms | supported | start with BCE; see the loss page for each term |
| `hf_auto`, SMP, and hand-integrated built-ins | unsupported | their wrappers remain multiclass |
| query/mask-classification objective | unsupported | query class semantics require `task: multiclass` |
| standard multilabel train/eval pipeline | unsupported | objective primitives exist, but data/inference/evaluation do not |
| binary ONNX/TensorRT export | unsupported | no accepted one-channel export/parity contract yet |

Unsupported combinations raise instead of silently converting channels or
semantics. Do not use a custom wrapper to bypass these checks and then describe
the result as the standard binary pipeline.

## Evidence and benchmark boundary

Correctness tests cover task/config mismatches, exact taxonomy semantics,
canonical-to-one-channel active-mask conversion, ignored-pixel invariance,
one-logit gradients, output-shape rejection, threshold edges, sliding windows,
probability-space TTA, Lightning validation, checkpoint loading, and a real
on-disk synthetic folder train/evaluate smoke. Native-head tests exercise the
one-channel output contract across the head families. OCR additionally checks
that its internal centered two-region logits have positive-minus-negative
equal to the public logit, are label-swap symmetric, match BCE under class-axis
cross-entropy, and remain finite at extreme values. Its refined/coarse outputs
stay one-channel; weighted BCE and all-ignore objectives reach every parameter,
both classifiers update, and query/key context gradients are nonzero. This is
CPU contract evidence for Segmentary's symmetric gauge choice, not evidence that
one logit reconstructs an independently learned two-logit OCR classifier. A
separate retained
[GPU8 compatibility record](../../../benchmarks/native-component-smokes/native-binary-gpu8-2026-08-12.json)
captures the exact clean commit, typed composition, two checked shapes, four
BF16 optimizer steps, loss components, gradient audit, classifier updates,
environment, and GPU isolation. A direct
[binary-OCR GPU8 record](../../../benchmarks/native-component-smokes/native-binary-ocr-gpu8-2026-08-13.json)
additionally covers the centered two-region extension, weighted coarse BCE,
and updates to query/key plus both classifiers.

Those checks establish wiring and numerical semantics only. The synthetic data
is not a model-quality benchmark, and no common-protocol Segmentary study currently
shows that binary mode, a particular head, a threshold, or a loss improves a real
dataset. Report quality only from a separately documented dataset, split,
schedule, checkpoint, seed set, and evaluation protocol.

## Related documentation

- [Configuration guide](../../../guides/configuration.md)
- [Evaluation and results](../../../guides/evaluation-and-results.md)
- [Dense losses](../losses/README.md)
- [Heads and output strategy](../heads/README.md)
- [Native heads](../native-heads/README.md)
- [Taxonomy and mappings](../../../../taxonomy/README.md)
- [Interpreting results](../../../tutorials/interpreting-results.md)
