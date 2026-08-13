# `rs_custom`: RailSem19 to custom

This two-stage curriculum asks how much a public railway dataset helps a custom
rail target without a preceding urban Cityscapes stage.

## Status and flow

**Blocked until real custom data and a group-safe split exist.** RailSem19 is
runnable, but the complete curriculum is not.

```text
RailSem19: 40,000 steps from upstream pretrained weights
        -> exact prior EMA
custom: 10,000 steps at 0.1 learning-rate scale
```

The [source YAML](../../../../configs/curricula/rs_custom.yaml) uses
`rail_union`, the fixed RailSem19 seed-0 split, and CE + Lovász at weight 0.5.

## Beginner choice

First establish `rs_only` and the real custom `direct` baseline. Only then run
this chain with the same model, custom split, seed set, and final EMA endpoint.

## What it controls

Compare this against `direct` to measure public rail pretraining value. Compare
it against `cs_rs_custom` to isolate whether the additional urban source stage
earns its compute.

## Advanced switches

Useful named ablations include custom-stage `lr_scale`, `reset_head`, step
budget, and tuning mode. Keep the custom split, model initialization, common
target evaluator, and total-budget accounting explicit. `init_from: previous`
loads weights, not RailSem optimizer state.

## Pros and cons

Pros: target-adjacent public source; shorter than the three-stage curriculum;
cleanly removes Cityscapes from the comparison.

Cons: blocked; potential RailSem-to-custom domain mismatch remains; 50k total
steps exceeds the direct arm's 10k unless compute-normalized comparisons are
also run; stage transfer can still forget.

## Evidence and benchmark boundary

No real custom endpoint exists, so no transfer benefit can be measured. The
configuration and stage chain are tested, but all quality claims remain blocked.

## Related documentation

- [`direct`](../direct/README.md)
- [`cs_rs_custom`](../cs_rs_custom/README.md)
- [RailSem19 dataset](../../datasets/railsem19/README.md)
- [Custom loader](../../datasets/custom-legacy/README.md)
- [All curricula](../README.md)
