# `cs_rs_custom`: full staged transfer

This is the complete three-domain transfer recipe: urban source, public rail source,
then custom rail target.

## Status and flow

**Blocked until real custom data and a valid group-safe split exist.**

```text
Cityscapes: 40,000 steps from upstream pretrained weights
        -> exact prior EMA
RailSem19: 20,000 steps at 0.1 learning-rate scale
        -> exact prior EMA
custom: 10,000 steps at 0.1 learning-rate scale
```

The [source YAML](../../../../configs/curricula/cs_rs_custom.yaml) uses one
`rail_union` head across all stages and CE + Lovász at weight 0.5.

## Beginner path

Do not start here. First establish `direct`, `rs_custom`, `cs_only`, `rs_only`,
and the runnable `cs_rs` chain. Verify custom masks/splits and overfit eight real
custom images. The full chain is interpretable only when its controls work.

## Advanced switches

Stage budgets, later-stage `lr_scale`, classifier reset, partial freeze, and
tuning mode are available, but each adds an experimental axis. Preserve the
same custom split and fixed final/common evaluation. A three-stage run totals
70k optimizer steps; disclose or normalize that compute when comparing shorter
controls.

## Pros and cons

Pros: tests gradual broad-to-specific adaptation; one canonical head can carry
class knowledge through all domains; per-stage records expose where gains or
forgetting appear.

Cons: longest sequential path; most opportunities for forgetting and protocol
drift; unequal compute versus controls; custom stage currently unavailable.

## Evidence and benchmark boundary

No real custom endpoint or complete benchmark exists. Runnable earlier stages
do not make the blocked final stage complete. Any future claim needs matched
multi-seed `direct`, `rs_custom`, and joint baselines.

## Related documentation

- [`cs_rs` runnable prefix](../cs_rs/README.md)
- [`rs_custom`](../rs_custom/README.md)
- [`joint`](../joint/README.md)
- [Training runtime](../../components/training-runtime/README.md)
- [All curricula](../README.md)
