# Built-in SegFormer-B5

[`segformer_b5.yaml`](../../../../configs/models/segformer_b5.yaml) selects the
largest SegFormer option in the hand-written factory.

```yaml
model:
  arch: segformer_b5
  checkpoint: nvidia/mit-b5
  tuning: full
  head: unified_head
```

## What it is

The path loads the ImageNet-pretrained `nvidia/mit-b5` hierarchical transformer
encoder and creates a new dataset-specific SegFormer decode head. Like B0 and
B2, it fuses four feature scales and returns input-resolution logits.

## When to use it

Pros:

- highest-capacity built-in SegFormer;
- direct architectural scale-up from the well-tested B0/B2 path;
- hierarchical features avoid the fixed single-scale map of a plain ViT;
- full, frozen, and attention-projection LoRA are available in principle.

Cons:

- largest memory and compute cost in the built-in SegFormer family;
- no shipped tuned recipe or Segmentary dataset benchmark;
- decoder is fresh, so the encoder's capacity does not remove the need for
  sufficient task data and training;
- construction compatibility is not a substitute for a B5-specific baby run.

## Safe first experiment

Compose the shipped model YAML with the same taxonomy, data split, optimizer
schedule, evaluation settings, and seeds used for B2. First run the overfit
check and a few-step training smoke at a small crop. Then measure intended-crop
peak memory before launching the full comparison.

Use RGB ImageNet normalization and dimensions divisible by 32. Reduce
per-device batch before changing the scientific protocol; accumulation can
restore the effective batch. A local immutable `nvidia/mit-b5` snapshot is the
way to pin the encoder exactly because this built-in path rejects the generic
Hub `revision` field.

## Verified evidence and benchmarks

B5 shares the tested SegFormer wrapper and factory logic with B0/B2, but no
same-protocol Segmentary accuracy result or retained B5 baby-training artifact is
claimed here. Treat it as an available advanced arm that still needs its own
resource and training acceptance on the target system.

See [SegFormer-B2](../builtin-segformer-b2/README.md) for the current comparable
reference and the [built-in model component](../../components/builtin-models/README.md)
for shared rules.
