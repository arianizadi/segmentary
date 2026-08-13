# `reference_cityscapes19`: implementation check

This one-stage curriculum trains in the standard Cityscapes 19-class protocol.
Its purpose is to test the complete implementation against a recognizable
reference scale before interpreting custom transfer experiments.

## Status and beginner use

Runnable with Cityscapes:

```text
Cityscapes (standard cityscapes19) --pretrained--> 40k fixed endpoint
```

Pair it with `configs/models/segformer_b2.yaml` and do not silently change the
augmentation or evaluation protocol when reproducing the recorded acceptance.

## Why this is separate

Published Cityscapes semantic-segmentation results use exactly 19 train IDs and
official ignore rules. A `rail_union` model has different class meanings and
cannot be compared with that literature number even on the same pixels.

The [source YAML](../../../../configs/curricula/reference_cityscapes19.yaml)
sets `space: cityscapes19`, one Cityscapes stage, and `init_from: pretrained`.
The base config supplies 40,000 steps, CE loss, native sliding-window evaluation,
EMA, and checkpoint cadence.

## Pros and cons

Pros: recognized protocol; catches normalization, output-resize, SyncBN,
optimizer, and evaluator errors; gives new architecture work a sanity gate.

Cons: urban-only and not a rail-domain target; one model/reference does not
validate every architecture; reproducing a headline can consume substantial
compute; changing model or schedule removes direct comparability.

## Verified evidence

Config and runtime tests cover the schedule, checkpoint, EMA, and evaluation
contracts. No prior model-quality result is bundled.

## Related documentation

- [`cityscapes19` taxonomy](../../../../taxonomy/cityscapes19/README.md)
- [Cityscapes dataset](../../datasets/cityscapes/README.md)
- [Evaluation choices](../../components/evaluation/README.md)
- [All curricula](../README.md)
