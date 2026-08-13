# Mask2Former with plain DINOv3: blocked

`mask2former_dinov3` is listed in the factory so an attempted experiment fails
with a precise explanation. It is **not a runnable model choice**, has no model
YAML, and has no checkpoint or benchmark.

## Why it is blocked

Mask2Former's pixel decoder expects a hierarchical feature pyramid at roughly
stride 4, 8, 16, and 32. A plain DINOv3 ViT exposes flat stride-16 features.
Passing several same-resolution ViT layers as if they were a pyramid can make a
forward pass appear to work while violating the architecture Mask2Former needs.

The supported future design requires a real DINOv3 adapter with a spatial-prior
module that creates the missing pyramid. Until that adapter is implemented and
verified, calling this factory arm raises before training.

## Pros and cons

Potential advantages after a correct implementation:

- DINOv3 representation combined with a query-based mask decoder;
- multi-scale spatial prior could recover fine and coarse structure;
- native matching loss could model regions directly.

Current disadvantages:

- no valid backbone-to-decoder feature pyramid;
- the native query objective exists, but cannot make this invalid architecture
  runnable without the missing adapter;
- no end-to-end checkpoint-loading proof;
- no export path or benchmark;
- licensed DINOv3 weight handling would need explicit provenance and terms.

## What advanced contributors must add

Enabling the name requires more than removing the exception:

1. implement the adapter/spatial-prior pyramid and verify every feature stride;
2. prove pretrained DINOv3 tensors loaded exactly rather than randomly;
3. connect the existing native Hungarian query objective to the valid wrapper;
4. add output, gradient, tuning, checkpoint, and real baby-training tests;
5. document preprocessing, licensing, memory, and export status;
6. add a model YAML only after the above evidence exists.

If you need a runnable DINOv3 experiment now, read
[EoMT-DINOv3-Large](../builtin-eomt-dinov3-large/README.md), including its own
explicit objective choice. If you need a conventional pyramid model, use
[UPerNet/ConvNeXt](../builtin-upernet-convnext/README.md) or an SMP recipe.

The blocking regression is in
[`tests/test_models.py`](../../../../tests/test_models.py), and the guard itself
is in [`factory.py`](../../../../src/segmentary/models/factory.py).
