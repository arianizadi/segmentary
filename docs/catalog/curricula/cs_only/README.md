# `cs_only`: Cityscapes control

This one-stage control asks what the configured model learns from Cityscapes
without any rail-domain training.

## Status and beginner use

Runnable when the official Cityscapes train/val tree exists at the configured
root. Use it as the source-only baseline before interpreting transfer.

```text
Cityscapes (rail_union) --pretrained--> final Cityscapes checkpoint
```

The stage inherits `train.iters` (40,000 in `configs/base.yaml`), uses
`init_from: pretrained`, and inherits base CE-only loss unless another later
config deliberately overrides it.

## Exact switches

Edit or override the [source YAML](../../../../configs/curricula/cs_only.yaml):

- change the Cityscapes `root` for the site;
- set stage `iters` for an explicit compute ablation;
- select a different model YAML independently;
- keep `space: rail_union` for transfer-table compatibility.

Do not use this result as a published Cityscapes-19 number. The union taxonomy
coarsens some urban classes and has inactive rail classes. Use
[`reference_cityscapes19`](../reference_cityscapes19/README.md) for standard
Cityscapes comparison.

## Pros and cons

Pros: simplest source-domain control; reveals zero-shot rail generalization when
evaluated later on the common RailSem19 split; cheaper than staged/joint arms.

Cons: receives no direct rail supervision; its native training validation is
Cityscapes rather than the final target; `rail_union` mIoU is not a literature
benchmark.

## Evidence and benchmark boundary

The completed [three-seed case study](../../../findings.md) evaluated every
true-final EMA checkpoint on the same RailSem19 target. This zero-shot control
scored `30.24 ± 0.50%` mIoU, far below each RailSem-supervised arm. That measures
the domain gap for this fixed protocol; it is not a general Cityscapes transfer
ceiling.

## Related documentation

- [All curricula](../README.md)
- [Cityscapes dataset](../../datasets/cityscapes/README.md)
- [`rail_union` taxonomy](../../../../taxonomy/rail_union/README.md)
- [`cs_rs` staged transfer](../cs_rs/README.md)
- [Audited case-study findings](../../../findings.md)
