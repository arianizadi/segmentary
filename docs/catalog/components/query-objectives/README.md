# Hungarian query and mask objective

This is Segmentary's native training objective for models that predict a fixed
set of class-labelled masks, such as EoMT and Mask2Former. It consumes the raw
query tensors; it does not train the dense map used by evaluation.

Use this page at the model/loss decision point. A dense model needs a
[dense objective](../losses/README.md). A query model can use this objective or,
for a deliberately controlled legacy ablation, the experimental dense-loss
path described below. Segmentary rejects a query objective attached to a dense
model and rejects any config that mixes `loss.query` with dense terms.

## Beginner explanation

A dense head makes one class prediction at every pixel. A mask-classification
head instead makes `Q` proposals. Each proposal contains:

- one class distribution with `C` semantic classes plus **no object**; and
- one binary mask logit map.

The ground-truth image does not say which proposal should learn which region.
Segmentary therefore turns the semantic label map into one binary mask for every
class present in that image, then uses exact Hungarian bipartite matching to
pair target masks with proposals. Matched proposals learn a class and a mask;
unmatched proposals learn no-object.

For a first query-model experiment, use the defaults:

```yaml
loss:
  task: multiclass
  activation: auto
  query:
    kind: hungarian_query
```

This is a complete objective. Do not add `terms`, Dice, CE, or the legacy
`aux` fields beside it. `activation: auto` remains a consistency field;
matching uses softmax class probabilities and sigmoid mask probabilities.

## Important composition rule

Configs merge from left to right. The shipped EoMT model YAMLs choose a model,
not an objective. With only `configs/base.yaml` they deliberately retain the
older dense-CE ablation. To use native query training, add a final objective
override that selects `loss.query`.

If an earlier curriculum selected a dense objective, reset those fields in the
final override or Segmentary will stop instead of guessing:

```yaml
loss:
  task: multiclass
  activation: auto
  terms: []
  aux: none
  aux_weight: 0.0
  ce_weight: 1.0
  label_smoothing: 0.0
  class_weights: null
  query:
    kind: hungarian_query
```

That explicit reset is useful evidence: it prevents an old Lovász or Dice
choice from being silently carried into a scientifically different objective.

## What each setting controls

```yaml
loss:
  task: multiclass
  query:
    kind: hungarian_query

    # Differentiable loss after the assignment is chosen.
    classification_weight: 2.0
    mask_bce_weight: 5.0
    dice_weight: 5.0
    no_object_coefficient: 0.1

    # Detached costs used only to choose the assignment.
    match_class_cost: 2.0
    match_mask_bce_cost: 5.0
    match_dice_cost: 5.0

    # null uses every valid pixel for matching. An integer deterministically
    # samples that many evenly spaced valid pixels per image.
    matching_num_points: null

    # Applies the complete objective to each returned intermediate decoder layer.
    auxiliary_layer_weight: 1.0
    dice_smooth: 1.0
```

| setting | raise it when | cost or risk |
|---|---|---|
| `classification_weight` | proposals choose the wrong semantic class | may improve labels without improving boundaries |
| `mask_bce_weight` | local mask pixels are poorly calibrated | large regions/pixel counts influence the term |
| `dice_weight` | overlap or small/thin regions matter | can be noisier for extremely small masks |
| `no_object_coefficient` | too many unmatched queries fire | too high can favor suppressing proposals; `0` disables unmatched-query classification |
| `match_class_cost` | assignment should trust class identity more | early wrong class logits can select a worse mask |
| `match_mask_bce_cost` | pixel agreement should drive assignment | full-mask matching costs more memory/time |
| `match_dice_cost` | overlap should drive assignment | smooth masks can tie early in training |
| `matching_num_points` | matching is a memory/latency bottleneck | sampled matching is an approximation and can miss tiny regions |
| `auxiliary_layer_weight` | earlier decoder layers need direct gradients | each returned layer repeats matching and loss work; `0` disables it |
| `dice_smooth` | tiny masks make the ratio unstable | larger values weaken the penalty on tiny masks |

Matching-cost weights and loss weights are separate on purpose. Changing a
matching cost can change **which** proposal is supervised. Changing a loss
weight changes the gradient after that assignment. Treat them as different
ablation families.

Classification weight, at least one mask-loss weight, and at least one matching
cost must be positive. This prevents a nominally trainable class or mask head
from receiving no differentiable signal. All numeric values must be finite.
Unknown keys, invalid point counts, binary or multilabel tasks, and ambiguous
dense/query combinations fail during config loading.

## Exact target and masking semantics

- Input targets are integer `(N,H,W)` semantic class IDs.
- One binary target mask is created for each present canonical class, in sorted
  class-ID order. Disconnected regions of one semantic class are one target;
  this is semantic set prediction, not instance segmentation.
- `255` is excluded from matching costs, BCE, and Dice. Changing predictions
  only under ignored pixels cannot change assignment or loss.
- The per-sample active-class mask removes unavailable classes from matching
  and class softmax. A target containing an inactive class is an error.
- An all-ignore image contributes neither no-object classification nor mask
  loss. An all-ignore batch returns graph-connected zero.
- Query class logits must be `(N,Q,C+1)` with no-object last. Mask logits must
  be `(N,Q,h,w)`. A sample with more present classes than queries is rejected.
- Matching and objective arithmetic run in float32 under fp16/bf16 autocast.
  SciPy's exact `linear_sum_assignment` receives a detached CPU float64 cost
  matrix; gradients flow only through the post-match class/BCE/Dice losses.
- Class/BCE/Dice components are macro-averaged across non-void samples (and
  matched masks within a sample), so a large image or a class occupying many
  pixels does not receive an automatic extra sample-level weight.

## Full-mask versus point matching

`matching_num_points: null` compares every non-ignored target pixel. It is the
easiest mode to reason about and is recommended for initial debugging.

An integer selects an evenly spaced deterministic subset of valid flattened
pixels. Unlike random point sampling, rerunning the same inputs produces the
same cost matrix and assignment. It reduces the `Q × targets × pixels` work,
but a small point budget can miss a narrow rail, cable, pole, or boundary. The
post-match BCE and Dice losses still use every valid pixel; only assignment is
sampled.

## Auxiliary decoder layers

If a wrapper returns intermediate `QueryPrediction` values, Segmentary performs a
fresh Hungarian assignment and complete class/BCE/Dice objective for each
layer. Reusing the final layer's assignment would assume proposal identities
are stable across decoder depth, which is not guaranteed.

Mask2Former is asked to return its supported intermediate decoder outputs.
The current Hugging Face EoMT output exposes only the final query tensors, so
`auxiliary_layer_weight` has no effect on EoMT unless that upstream output
contract later provides auxiliary layers. It is not a promise that every query
architecture has deep supervision.

## Compatibility

| model/output | query objective | dense objective | evaluation/export behavior |
|---|---|---|---|
| EoMT wrappers | supported for final raw queries | supported only as a named experimental ablation | public `forward` still returns the same dense semantic tensor |
| Mask2Former with a valid hierarchical backbone | objective and auxiliary layers supported | experimental ablation | dense public inference remains unchanged; export remains unsupported |
| plain dense heads (SegFormer, U-Net, FCN, PSP, ASPP, UPerNet, DeepLab) | rejected | supported | unchanged |
| plain DINOv3 wired directly to Mask2Former | still blocked | still blocked | query loss does not create the missing feature pyramid/adapter |

Selecting a correct objective does not repair an invalid architecture. The
`mask2former_dinov3` recipe remains blocked until it has a tested DINOv3 spatial
prior/feature-pyramid adapter.

## Pros and cons

Pros:

- trains query models in their native class-and-mask representation;
- exact deterministic assignment with auditable cost terms;
- preserves ignore pixels and mixed-dataset active classes exactly;
- supervises unmatched queries explicitly through the no-object class;
- supports intermediate decoder-layer supervision when the model exposes it;
- keeps evaluation compatible with Segmentary's dense metrics and inference.

Cons:

- substantially more moving parts and tuning choices than dense CE;
- Hungarian matching transfers cost matrices to CPU once per image and layer;
- full-mask cost grows with queries, present classes, and image pixels;
- one mask per semantic class cannot represent separate instances;
- query IDs are permutation-invariant, which makes proposal-level debugging
  less intuitive than inspecting dense channels;
- no same-protocol Segmentary accuracy benchmark yet proves it beats dense CE.

## Reading logs and debugging

Training logs expose `classification`, `mask_bce`, `dice`, and `total`.
Intermediate layers appear under `aux/<layer>/...`. These losses are not
bounded accuracy scores: a total above `1` is normal because it is a weighted
sum. Compare runs only when every weight, point mode, label space, and reduction
is identical.

Useful failure clues:

| symptom | likely cause | first check |
|---|---|---|
| config rejects dense/query mixture | an earlier merged YAML selected `terms` or legacy `aux` | inspect the fully merged config and use the explicit reset snippet |
| “dense model cannot use” | model returns dense logits, not raw queries | select a dense objective or implement a reviewed query wrapper |
| class-column error | head has the wrong taxonomy size or no-object position | require exactly `C+1`, no-object last |
| more targets than queries | too few queries for classes present in one image | raise model query count; do not drop target classes |
| class loss falls, masks do not | mask weights too low, bad resize, or ignored/active semantics | inspect matched masks and valid pixels before tuning |
| unstable assignments | matching costs disagree or point budget misses small classes | use full-mask matching, then change one matching cost at a time |
| too many predictions | no-object supervision is weak | inspect unmatched-query probabilities before raising its coefficient |
| query model looks good in training but mIoU is poor | collapse/evaluation protocol or taxonomy mismatch | inspect dense overlays and per-class confusion, not only set losses |

## Evidence and scientific limits

Focused CPU tests cover known assignments in full/point modes, empty/all-ignore
targets, ignore perturbation invariance, per-sample inactive classes, gradients
to both class and mask logits, auxiliary layers with independent matching,
float32 objective math under autocast, malformed shapes/configs, Lightning
dispatch, wrapper preservation of raw outputs, and legacy dense-loss behavior.

The retained
[EoMT-Large GPU8 machine record](../../../benchmarks/native-component-smokes/eomt-large-query-gpu8-2026-08-13.json)
adds exact pretrained compatibility evidence for two BF16 production-objective
optimizer steps. It records complete gradient coverage and updates to every
tracked query/head tensor, while explicitly limiting the result to synthetic
wrapper compatibility rather than model quality or native arbitrary-grid
support. See the [smoke ledger](../../../benchmarks/native-component-smokes/README.md)
for the checkpoint, isolation, and class-predictor-reset details.

That is implementation evidence, not a model-quality benchmark. No comparable
multi-seed Segmentary dataset result has yet isolated native query training from
the older dense-collapse ablation. Existing EoMT model YAMLs still select only
the model; unless `loss.query` is explicitly added, their training remains the
experimental dense objective and must be labeled that way.

## Related documentation

- [Dense objectives and activations](../losses/README.md)
- [Heads and output representations](../heads/README.md)
- [EoMT-Large](../../models/builtin-eomt-large/README.md)
- [EoMT-DINOv3-Large](../../models/builtin-eomt-dinov3-large/README.md)
- [Interpreting results](../../../tutorials/interpreting-results.md)
