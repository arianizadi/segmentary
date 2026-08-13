# `rs_only`: RailSem19 control

This one-stage control asks what the model learns from railway-domain data
without an earlier urban stage.

## Status and beginner use

Runnable when RailSem19 exists and the committed split file is available.

```text
RailSem19 (rail_union) --pretrained--> final RailSem19 checkpoint
```

The stage inherits 40,000 optimizer steps from the base config, starts from the
model's upstream pretrained weights, and globally selects Lovász auxiliary loss
at weight 0.5 in addition to CE.

## Exact switches

The [source YAML](../../../../configs/curricula/rs_only.yaml) pins
`splits/railsem19_seed0.json`. Keep that split fixed across training seeds. A
different split filename defines a different protocol and needs separate result
grouping.

Advanced comparisons can change model, tuning mode, step budget, or loss in
separate config layers. Keep the common 850-image endpoint, taxonomy, and
evaluation policy fixed when comparing with `cs_only`, `cs_rs`, or
`joint_cs_rs`.

## Pros and cons

Pros: direct domain labels; clean no-urban-pretraining control; cheapest way to
test the rail pipeline and thin-class metrics.

Cons: skips potentially useful generic urban context; RailSem19 cannot supervise
motorcycle/bicycle in `rail_union`; one seed is not a conclusion.

## Evidence and benchmark boundary

No model-quality result is bundled for this curriculum. Compare it only at a
fixed common RailSem19 endpoint with the same update budget, seed policy,
checkpoint rule, and evaluator.

## Related documentation

- [All curricula](../README.md)
- [RailSem19 dataset](../../datasets/railsem19/README.md)
- [Loss choices](../../components/losses/README.md)
- [`cs_rs` staged transfer](../cs_rs/README.md)
