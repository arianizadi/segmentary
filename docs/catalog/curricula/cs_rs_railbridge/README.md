# `cs_rs_railbridge`: early rail-label ablation

This curriculum is identical in structure to `cs_rs`, except the Cityscapes
stage uses `variant: railbridge`. Native Cityscapes IDs for rail track and guard
rail become `rail_union` rail-track and rail-raised supervision.

## Status and flow

Runnable with Cityscapes and RailSem19:

```text
Cityscapes rail-bridge: 40,000 steps
        -> prior EMA
RailSem19: 20,000 steps at 0.1 learning-rate scale
```

## What it asks

Does a small, imperfect rail-related signal during the urban stage help the
later railway stage? It is a named taxonomy ablation, not a corrected default.

## Beginner choice

Run the ordinary `cs_rs` curriculum with the same model and seeds first. Add
this arm only after the default taxonomy and common RailSem19 endpoint are
verified, and keep `variant: railbridge` visible in the resolved config.

## Pros and cons

Pros: isolates whether any early rail supervision helps; changes only the
mapping relative to the main staged arm; supplies direct stage-one gradients for
two otherwise inactive rail classes.

Cons: both native labels are ignored by the official Cityscapes evaluation
protocol, so the stage is not literature-comparable. Cityscapes guard rail also
includes ordinary road barriers and is a lossy proxy for RailSem19
`rail-raised`. The available rail-track pixels are rare, so a null or negative
effect is plausible.

## Exact switches and safeguards

The [source YAML](../../../../configs/curricula/cs_rs_railbridge.yaml) sets
`variant: railbridge` only on the Cityscapes data entry. The matching file is
`taxonomy/rail_union/cityscapes_railbridge.yaml`. Never silently replace the
default `cityscapes.yaml`; keep the variant name in config and results.

All other comparison settings—model, seed set, step counts, split, EMA/final
policy, and common endpoint—must match `cs_rs`.

## Evidence and benchmark boundary

Taxonomy tests prove the variant activates 18 of 21 classes and declares all
merges. No completed same-protocol multi-seed accuracy result is committed. The
mapping file documents sampled class-rarity evidence, but that is not an outcome
benchmark.

## Related documentation

- [`cs_rs` baseline](../cs_rs/README.md)
- [`rail_union` mapping details](../../../../taxonomy/rail_union/README.md)
- [Cityscapes dataset](../../datasets/cityscapes/README.md)
- [All curricula](../README.md)
