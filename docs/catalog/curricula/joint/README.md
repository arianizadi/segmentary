# `joint`: mixed public pretraining to custom

This curriculum pools Cityscapes and RailSem19 in one public-data stage, then
fine-tunes the custom target. It is the principal baseline against the full
sequential `cs_rs_custom` curriculum.

## Status and flow

**Blocked until real custom data and a group-safe split exist.** The mixed public
stage can be built, but the requested two-stage experiment cannot complete.

```text
{Cityscapes 50%, RailSem19 50%}: 60,000 steps
        -> exact prior EMA
custom: 10,000 steps at 0.1 learning-rate scale
```

The [source YAML](../../../../configs/curricula/joint.yaml) explicitly requires
`model.head: unified_head`, uses `rail_union`, and applies CE + Lovász at 0.5.

## Beginner choice

Do not schedule the full file until the custom dataset passes verification and
the runnable `joint_cs_rs` public-only form works. Then compare true-final EMA
weights with `cs_rs_custom` on one fixed custom split.

## Exact mixed-stage behavior

`sample_weights: {cityscapes: 0.5, railsem19: 0.5}` selects relative dataset
shares with replacement regardless of member sizes. Per-sample active masks
protect unsupported classes. The public stage's in-training validation uses the
first dataset—Cityscapes—not a combined or RailSem endpoint.

## Pros and cons

Pros: both public domains shape features throughout pretraining; same 70k total
steps as the full staged curriculum; direct test of pooling versus ordering.

Cons: ratio is a hyperparameter; public-stage `best.ckpt` is selected on
Cityscapes because it is first; does not identify which domain order matters;
blocked on the custom endpoint.

## Advanced switches

Sampling ratio, public-stage budget, custom `lr_scale`, reset, and tuning are all
possible ablations. Changing data order changes validation semantics and must be
treated as a protocol change. Compare true-final EMA checkpoints on the same
custom validation split to avoid Cityscapes-selection bias.

## Evidence and benchmark boundary

Mixed sampling and active-mask behavior are tested. No real custom result exists,
so this baseline cannot yet support a joint-versus-staged conclusion.

## Related documentation

- [`joint_cs_rs` runnable public-only form](../joint_cs_rs/README.md)
- [`cs_rs_custom` sequential comparison](../cs_rs_custom/README.md)
- [Mixed dataset guide](../../datasets/README.md)
- [Evaluation choices](../../components/evaluation/README.md)
- [All curricula](../README.md)
