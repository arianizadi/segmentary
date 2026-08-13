# `cs_rs`: staged Cityscapes to RailSem19

This is the main runnable staged-transfer arm. It asks whether learning an urban
source first improves the final rail-domain endpoint.

## Status and flow

Runnable with both datasets:

```text
Cityscapes: 40,000 steps, upstream pretrained weights
        -> exact prior EMA handoff
RailSem19: 20,000 steps, learning rates multiplied by 0.1
```

Both stages use `rail_union` and the curriculum's global CE + Lovász (`0.5`)
loss. The classifier is retained (`reset_head: false`). RailSem19 uses the fixed
`railsem19_seed0.json` split.

## Beginner choice

Run `cs_only` and `rs_only` with the same model and seeds first. Then run this
file unchanged except for site paths/devices. Evaluate every final checkpoint on
the same common RailSem19 endpoint.

## Exact switches

The [source YAML](../../../../configs/curricula/cs_rs.yaml) exposes stage
`iters`, RailSem `lr_scale`, `reset_head`, roots, and split file. Useful named
ablations are:

- `reset_head: true` to discard classifier transfer while keeping the backbone;
- another positive RailSem `lr_scale` to test adaptation/forgetting;
- the [`cs_rs_railbridge`](../cs_rs_railbridge/README.md) mapping variant.

Change one at a time. `init_from: previous` is an exact weight handoff, not a
resume of stage-one optimizer/scheduler state.

## Pros and cons

Pros: directly tests domain order; shorter/lower-LR target stage can preserve
source features; stage-specific result records show where behavior changes.

Cons: 60,000 total steps versus 40,000 one-stage controls unless compute is
explicitly normalized; later training can forget source behavior; more wall time
and checkpoints; a positive single-seed delta may be noise.

## Evidence and benchmark boundary

The chain, EMA handoff, exact load, and true-final checkpoints are tested. In the
completed [three-seed case study](../../../findings.md), this schedule reached
`66.44 ± 0.03%` common-target mIoU: `4.03 ± 0.20` points below `rs_only` and
`4.60 ± 0.21` below the equal-total-update joint path, paired by seed. This is a
real negative result for these settings. It mixes source initialization with
half as many target updates and a 0.1 target LR, so it does not show that staged
transfer is universally harmful.

## Related documentation

- [All curricula](../README.md)
- [`cs_only`](../cs_only/README.md)
- [`rs_only`](../rs_only/README.md)
- [Training runtime](../../components/training-runtime/README.md)
- [Evaluation choices](../../components/evaluation/README.md)
- [Audited case-study findings](../../../findings.md)
