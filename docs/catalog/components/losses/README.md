# Objective and activation library

Segmentary combines its own typed loss terms as a weighted list. This is inspired
by the breadth that mature segmentation toolkits make useful, but the schema,
validation, masking rules, implementations, and tests here are Segmentary-native.
There is no MMSegmentation dependency or copied registry code.

This page covers **dense** objectives. Models that emit class-labelled query
masks use the separate [Hungarian query objective](../query-objectives/README.md).
The two families cannot be mixed in one `loss` config. Task-level output,
taxonomy, active-mask, inference, and compatibility rules live in
[Semantic task modes](../tasks/README.md).

## Start simple

```yaml
loss:
  task: multiclass
  activation: auto
  terms:
    - kind: cross_entropy
      weight: 1.0
```

This consumes raw `(N,C,H,W)` logits and integer `(N,H,W)` class labels. `auto`
means softmax for `multiclass` and sigmoid for `binary` or `multilabel`. Do not
put a softmax/sigmoid inside the model: fused logit losses are more stable.

Add one term because a measured failure calls for it, not because a longer
objective looks advanced:

```yaml
loss:
  task: multiclass
  activation: softmax
  terms:
    - kind: cross_entropy
      weight: 1.0
      label_smoothing: 0.0
      class_weights: null
    - kind: dice
      weight: 0.5
      smooth: 1.0
      present_only: true
      include_background: true
```

Unknown keys, unknown term kinds, zero/negative term weights, duplicate kinds,
wrong activation/task combinations, and class-weight length mismatches fail
before training.

## Terms, use cases, and costs

| `kind` | useful when | advantages | costs and cautions |
|---|---|---|---|
| `cross_entropy` | normal mutually-exclusive classes | stable baseline; class weights and label smoothing | common pixels can dominate |
| `binary_cross_entropy` | one-channel binary or independent multilabel classes | fused logits; per-channel positive weights | invalid for multiclass softmax |
| `dice` | overlap and imbalanced/thin objects matter | directly rewards overlap | batch-sensitive for tiny classes |
| `jaccard` | a smooth intersection-over-union objective is desired | directly optimizes soft IoU and is easy to interpret | harsher than Dice on partial overlap; smoothing and batch composition matter |
| `lovasz` | mean IoU is the selection metric | convex IoU surrogate (Berman et al.) | per-class sorting costs time |
| `focal` | easy pixels overwhelm hard ones | downweights confident easy examples | `gamma`/`alpha` need tuning; multiclass alpha is a per-class list |
| `tversky` | false positives and false negatives have different costs | explicit FP/FN tradeoff | asymmetric settings can create biased masks |
| `ohem_cross_entropy` | most pixels are already easy | CE on a deterministic hard subset | noisy with too small `min_kept`; slower selection |
| `boundary` | contours are visibly soft or misplaced | differentiable boundary Dice | depends on pixel-scale `width`; pair with a region term |
| `hausdorff` | rare but large contour misses are costly | differentiable distance-transform surrogate | most expensive term; distance is truncated and grid-based |
| `kl_distillation` | a teacher should constrain a student | temperature-scaled soft targets | training caller must supply aligned teacher logits |

Example OHEM plus a boundary term:

```yaml
loss:
  terms:
    - kind: ohem_cross_entropy
      weight: 1.0
      fraction: 0.25
      min_kept: 4096
      probability_threshold: 0.7
    - kind: boundary
      weight: 0.2
      width: 2
```

`probability_threshold` keeps pixels whose correct-class confidence is below the
threshold when enough qualify; otherwise `fraction` and `min_kept` select the
highest-loss pixels. `min_kept` is per batch, after ignored pixels are removed.

Jaccard uses `intersection / union`; Dice uses twice the intersection divided by
the summed prediction and target mass. Both expose `smooth`, `present_only`, and
`include_background`, but their numeric scales differ—do not swap one into a
run without recording it as a different objective.

For Tversky, `alpha` multiplies false positives and `beta` multiplies false
negatives. Raise `beta` when missing an object is worse; raise `alpha` when
false alarms are worse. `include_background: false` is available for
multiclass overlap/boundary/distance terms. `present_only: true` prevents an
empty class in the current batch from changing Dice, Lovász, or Tversky.

Focal's scalar `alpha` is the binary positive/negative balance: positives
receive `alpha`, negatives receive `1-alpha`. Multiclass focal therefore rejects
a scalar and accepts only a class-aligned list such as `alpha: [1.0, 0.5, 2.0]`.
This avoids silently multiplying every multiclass pixel by one irrelevant
constant. Multilabel focal accepts either the binary scalar convention or a
per-channel list.

## Target contracts

- `multiclass`: at least two logits per pixel; integer `(N,H,W)` target; softmax.
- `binary`: exactly one logit per pixel; `(N,H,W)` values `0`, `1`, or `255`;
  sigmoid. End-to-end use currently requires a native model and exactly
  canonical IDs 0 and 1. Names are arbitrary; ID 1 is the positive class.
- `multilabel`: one independent logit per label; `(N,C,H,W)` values `0`, `1`,
  or `255`; sigmoid at the objective level. Ignore is per element, so one label
  can be unknown while another is supervised at the same pixel. This is a
  lower-level loss contract only; the standard data/train/eval pipeline rejects
  multilabel experiments.
- `kl_distillation`: teacher logits must exactly match student `(N,C,H,W)`,
  channel order, and resolution. The teacher is detached by default. Segmentary
  deliberately does not guess a class mapping or resize teacher outputs.

`activation` is an explicit consistency check, not an extra output layer.
`auto` is recommended. `softmax` is accepted only for multiclass;
`sigmoid` only for binary/multilabel.

## Semantics shared by every term

- `255` contributes exactly zero value and gradient.
- A per-sample `(N,C)` active mask removes classes the source dataset cannot
  label. Inactive softmax classes leave the denominator; inactive sigmoid
  channels leave the element reduction.
- Binary datasets are the deliberate exception to partial activity: their
  canonical `(N,2)` mask must activate both negative ID 0 and positive ID 1 on
  every sample before training converts it to the one-channel output mask.
  Without that rule, an unlabeled positive class would be trained as a negative.
- A target that names an inactive class is rejected rather than trained wrongly.
- An all-ignore crop returns graph-connected zero, including KL-only recipes.
- fp16/bf16 logits are promoted to float32 for objective math; float64 is kept
  for numerical tests.
- A weighted total is `sum(term.weight * raw_term_value)`. Logs expose the raw
  named term and the weighted `total` so coefficients remain auditable.

## Legacy config migration

Existing runs remain reproducible:

```yaml
loss: {aux: lovasz, aux_weight: 0.5, ce_weight: 1.0}
```

is converted to `cross_entropy@1.0 + lovasz@0.5`. Do not combine a non-default
legacy field with `terms`; Segmentary rejects that ambiguity. New configs should
always use `terms`.

## Honest limits

- Hausdorff is a truncated city-block distance-transform surrogate, not an exact
  non-differentiable Hausdorff maximum. Tune `max_distance` to the object scale.
- Boundary loss extracts soft morphological contours, not signed-distance maps.
- KL is implemented in the objective, but the standard training CLI does not yet
  instantiate/run a teacher. A custom training step must pass `teacher_logits`.
- Multilabel terms are implemented at the objective level, but the standard
  dataset, training, inference, and evaluation pipeline has no multilabel
  contract and rejects the task. Do not describe a direct loss-unit call as
  end-to-end multilabel support.
- Hungarian matching for semantic query/mask classification and auxiliary
  decoder-layer supervision are implemented as a deliberately separate
  [query objective](../query-objectives/README.md), not approximated by these
  dense terms. Topology and instance-segmentation objectives remain separate,
  unimplemented feature families.
- There is no same-protocol model-quality ranking of these choices yet. Unit and
  gradient tests establish behavior, not which loss wins on a dataset.

## References

The formulations follow the original focal-loss (Lin et al., 2017),
Lovász-Softmax (Berman et al., 2018), Tversky-loss (Salehi et al., 2017), and
Hausdorff-loss (Karimi and Salcudean, 2019) papers, plus PyTorch's fused CE, BCE,
and KL primitives. See each paper before changing defaults; their task and
reduction assumptions differ.

## Related documentation

- [Semantic task modes](../tasks/README.md)
- [Taxonomy and active classes](../../../../taxonomy/README.md)
- [Heads](../heads/README.md)
- [Hungarian query objective](../query-objectives/README.md)
- [Configuration guide](../../../guides/configuration.md)
- [Interpreting results](../../../tutorials/interpreting-results.md)
