# Curriculum catalog

A curriculum is an ordered list of training stages. Each stage chooses one or
more datasets, an optimizer-step budget, where weights come from, and optional
transfer controls. Model and runtime settings are composed separately.

## Beginner choice

Start with one dataset and one stage (`cs_only`, `rs_only`, or your own folder
dataset). A one-stage control proves the data/model path and gives staged or
joint transfer something fair to beat.

## How stages work

| switch | exact behavior |
|---|---|
| `init_from: pretrained` | construct the model from its configured upstream weights |
| `init_from: previous` | load the immediately preceding stage's evaluated EMA weights when present |
| `init_from: <checkpoint>` | exact weight warm start; optimizer/scheduler do not resume |
| `iters` | stage optimizer-step budget; overrides `train.iters` |
| `lr_scale` | positive multiplier on every stage LR |
| `head_group_lr_scale` | optional positive multiplier for model-declared decoder/head groups; omitted inherits `lr_scale` |
| `reset_head` | reset final classifier only after weight load |
| `freeze` | freeze every parameter whose qualified name contains the string; zero matches fail |
| `sample_weights` | positive relative dataset shares for a mixed stage; keys must exactly match every data name |

The first stage cannot use `previous`. One canonical label space applies to the
whole curriculum. A stage result lives in its own directory with periodic,
best, and true-final checkpoints plus `results.json`.
`head_group_lr_scale` is an optimizer ablation, not a classifier-only control:
the exact parameter set comes from each model's `head_patterns()` contract.

## Shipped choices

| curriculum | flow | status | question |
|---|---|---|---|
| [`cs_only`](cs_only/README.md) | Cityscapes | runnable with Cityscapes | urban-source control |
| [`rs_only`](rs_only/README.md) | RailSem19 | runnable with RailSem19 + split | rail-only control |
| [`cs_rs`](cs_rs/README.md) | Cityscapes -> RailSem19 | runnable with both | staged domain transfer |
| [`cs_rs_railbridge`](cs_rs_railbridge/README.md) | rail-bridged Cityscapes -> RailSem19 | runnable ablation | whether weak early rail labels help |
| [`joint_cs_rs`](joint_cs_rs/README.md) | Cityscapes + RailSem19 | runnable with both | pooled-data baseline |
| [`reference_cityscapes19`](reference_cityscapes19/README.md) | standard Cityscapes-19 | runnable with Cityscapes | implementation/literature sanity check |
| [`direct`](direct/README.md) | custom | blocked on custom data | no-transfer floor |
| [`rs_custom`](rs_custom/README.md) | RailSem19 -> custom | blocked on custom data | rail pretraining value |
| [`cs_rs_custom`](cs_rs_custom/README.md) | Cityscapes -> RailSem19 -> custom | blocked on custom data | complete staged-transfer recipe |
| [`joint`](joint/README.md) | Cityscapes + RailSem19 -> custom | blocked on custom data | pooling versus sequencing |

## Sequential versus mixed: pros and cons

Sequential stages isolate order and let later stages use lower LR/shorter
schedules, but can forget earlier domains. Mixed training sees both domains
together and makes sampling ratio explicit, but does not test order. In a mixed
stage each sample has its own active-class mask; in-training validation uses
only the first listed dataset. Always run the same explicit common-target
evaluation after every arm.

## Fair comparison rules

- Keep model, taxonomy, split files, total optimizer steps, effective batch,
  seed set, EMA/raw choice, checkpoint policy, and evaluator fixed.
- A train seed changes stochastic training but does not rewrite a configured
  split filename. The shipped curricula intentionally keep
  `railsem19_seed0.json` fixed across model seeds.
- `rail_union` scores are not Cityscapes-19 literature scores.
- The rail-bridge variant is nonstandard supervision and must remain a named
  ablation.
- Custom-data curricula are templates until the real dataset and group-safe
  split exist.

## Evidence and benchmark boundary

No prior quality table is bundled. Unit and integration tests prove stage
chaining, EMA handoff, reset/freeze, mixed sampling, and result-record behavior;
they do not rank curricula. See [benchmark evidence](../../benchmarks/README.md).

## Related documentation

- [Config-file index](../../../configs/curricula/README.md)
- [Configuration guide](../../guides/configuration.md)
- [Training runtime](../components/training-runtime/README.md)
- [Evaluation choices](../components/evaluation/README.md)
