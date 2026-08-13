# SegFormer-B2

Config: [`configs/models/segformer_b2.yaml`](../../../../configs/models/segformer_b2.yaml)

## What it is

This built-in recipe pairs the MiT-B2 encoder with Segmentary's unified dense
segmentation head. It supports full, frozen-backbone, and configured LoRA tuning,
EMA checkpoints, native-resolution validation, sliding-window evaluation, and
the standard curriculum runner.

## Pros

- It is a balanced general-purpose transformer baseline.
- The unified head works with the repository's canonical taxonomy and active-class
  masking contracts.
- The recipe is small enough to iterate on while remaining more capable than the
  B0 variant.

## Cons

- It is slower and larger than SegFormer-B0.
- It is not designed for instance or panoptic segmentation.
- Model quality still depends on the dataset, taxonomy, schedule, augmentation,
  seed, and evaluation protocol; the recipe itself is not a quality claim.

## Tuning and resource advice

Start with full tuning and keep effective batch size, crop size, optimizer-step
budget, seed, checkpoint policy, and evaluation settings fixed across comparisons.
If memory is tight, lower the per-device batch and raise accumulation rather than
silently changing effective batch size. Frozen and LoRA tuning answer different
questions and should remain explicitly labeled.

## Evidence boundary

The recipe has implementation and compatibility coverage, but this clean public
starting point does not include a prior model-quality benchmark. New results
should be added only after a complete, reproducible run.

## Related documentation

- [Built-in model components](../../components/builtin-models/README.md)
- [Models and tuning](../../../guides/models-and-tuning.md)
- [Evaluation and results](../../../guides/evaluation-and-results.md)
- [Interpreting results](../../../tutorials/interpreting-results.md)
