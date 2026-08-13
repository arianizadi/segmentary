# Built-in UPerNet with ConvNeXt-Small

[`upernet_convnext.yaml`](../../../../configs/models/upernet_convnext.yaml)
selects a modern convolutional alternative to SegFormer:

```yaml
model:
  arch: upernet_convnext
  checkpoint: openmmlab/upernet-convnext-small
  tuning: full
  head: unified_head
```

## What it is

ConvNeXt-Small produces a four-level hierarchical feature pyramid. UPerNet adds
pyramid pooling for broad context and a feature-pyramid decoder for multi-scale
fusion. The default is a complete ADE20K semantic-segmentation checkpoint; when
the destination class count differs, Transformers replaces the class-dependent
prediction layer.

Segmentary disables the upstream FCN auxiliary head. The current trainer owns one
dense loss and would otherwise compute a branch that receives no loss gradient,
causing wasted work and distributed unused-parameter failures.

## When to use it

Pros:

- strong convolutional control against transformer encoders;
- complete task-trained decoder, not only an ImageNet backbone;
- explicit multi-scale pyramid is useful when object sizes vary;
- ordinary dense logits work with Segmentary's loss and evaluator.

Cons:

- heavier decoder than SegFormer;
- the source classifier is replaced for a new taxonomy;
- the auxiliary-head training signal from the source recipe is not reproduced;
- ConvNeXt has no attention projections for Segmentary's automatic LoRA path.

## Advanced settings

Full and frozen tuning are supported. Frozen mode keeps ConvNeXt fixed while
training the UPerNet decoder and classifier. Top-level `drop_path` is rejected:
the value belongs inside the nested backbone config, and silently accepting it
would make the resolved experiment record false.

Use RGB ImageNet normalization, start with dimensions divisible by 32, and
measure memory at the intended crop. Override `checkpoint` only with a
structurally compatible UPerNet/ConvNeXt checkpoint or local snapshot.

## Verified evidence and benchmarks

The real integration regression constructs the default checkpoint on CUDA and
checks a finite `(1, 21, 96, 128)` BF16 output from a `(1, 3, 96, 128)` input.
That proves the current pinned environment can load and forward the arm. It is
not a speed, memory, or accuracy benchmark. No comparable Segmentary dataset mIoU
is claimed yet.

See the [built-in model component](../../components/builtin-models/README.md)
and [model comparison guide](../../../guides/models-and-tuning.md).
