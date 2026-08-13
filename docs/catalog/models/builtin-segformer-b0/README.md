# Built-in SegFormer-B0

Use [`segformer_b0.yaml`](../../../../configs/models/segformer_b0.yaml) for the
smallest hand-integrated SegFormer. It is the quickest built-in transformer for
an overfit check, data-pipeline check, or short experiment.

## What it is

`segformer_b0` loads the `nvidia/mit-b0` hierarchical transformer **encoder**.
Its four feature scales feed a newly initialized SegFormer all-MLP decode head.
Segmentary resizes the head's stride-4 logits back to input resolution before loss
or evaluation.

This is not the same choice as
[`hf_auto` SegFormer-B0](../hf-auto-segformer-b0/README.md). The latter starts
from a complete ADE20K semantic-segmentation checkpoint; this built-in starts
from an ImageNet-pretrained encoder and a fresh dataset-specific head.

## When to use it

Pros:

- small enough for fast setup checks and cheap tuning-mode experiments;
- multi-scale transformer features fit dense prediction naturally;
- full, frozen, and LoRA paths have regression coverage;
- its output contract and non-square input behavior are tested.

Cons:

- lower capacity than B2 or B5;
- the decoder has no task-specific pretraining;
- a successful B0 run does not predict the memory or throughput of a large arm;
- no comparable Segmentary dataset-quality result is recorded for this recipe.

## Practical settings

The shipped file uses full tuning. Frozen tuning is a useful low-cost diagnostic:
if only the head cannot learn a tiny training set, inspect labels and mappings
before scheduling a larger model. LoRA is useful for a parameter-efficiency
study, but it adds rank, alpha, dropout, and target-layout choices; prove that
adapter and head gradients are nonzero before a long run.

Use RGB ImageNet normalization and a crop divisible by 32. The default
`checkpoint` may be replaced by another compatible MiT-B0 encoder repository or
local snapshot. The hand-written path rejects the generic `revision` field, so
use a local immutable snapshot if the exact upstream weight revision matters.

`reset_head: true` resets only the final classifier. It keeps the MiT encoder and
the class-agnostic portions of the decode head.

## Verified evidence and benchmarks

The model contract suite loads the real B0 encoder, checks finite
input-resolution output, a non-square input, head reset, full/frozen tuning,
LoRA injection, and real backward gradients. B0 is also the model used by the
tiny end-to-end curriculum regression.

Those are compatibility checks, not accuracy benchmarks. No same-protocol
Segmentary mIoU is claimed for this recipe yet.

See the [built-in model component](../../components/builtin-models/README.md)
and [model comparison guide](../../../guides/models-and-tuning.md).
