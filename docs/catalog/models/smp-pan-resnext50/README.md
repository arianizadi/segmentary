# PAN with ResNeXt-50

Recipe: [`smp_pan_resnext50.yaml`](../../../../configs/models/smp_pan_resnext50.yaml)

## Purpose and architecture

Use this recipe to test pyramid attention with a higher-capacity grouped-
convolution encoder. ResNeXt-50 produces hierarchical features; PAN applies
feature-pyramid attention and global-attention upsampling before the fresh head.

## Pros and cons

| pros | cons |
|---|---|
| compact attention decoder; capable encoder; explicit multi-scale context | verified SMP implementation fails below 128 pixels per side; more encoder cost than mobile recipes |

## Resource notes

With five classes the recipe has 23,732,844 parameters. Because 64×64 collapses
PAN's pooling pyramid, its diagnostic probe used 128×128 and allocated 106.8 MiB
for BF16 batch-1 inference on an NVIDIA L40S. Use crops at least 128 pixels per
side and normally divisible by 32. Full training memory is substantially higher.

## Tuning support

Full and frozen ResNeXt tuning are supported. Automatic LoRA is not supported
for this convolutional encoder. Head reset keeps the PAN decoder and replaces
only the final classifier.

## Pretrained source

The ImageNet source is
[`smp-hub/resnext50_32x4d.imagenet`](https://huggingface.co/smp-hub/resnext50_32x4d.imagenet/tree/329793c85d62fd340ae42ae39fb905a63df872e7)
at revision `329793c85d62fd340ae42ae39fb905a63df872e7`, pinned by SMP
0.5.0. PAN itself starts fresh. `encoder_weights: scratch` is the explicit scratch
choice; a failed requested load is fatal.

## Verified evidence and benchmarks

On 2026-08-12 the exact PAN/ResNeXt-50 pair loaded its requested ImageNet encoder
and completed four finite BF16/AdamW steps at batch 2 and 128×128. The head
changed and peak allocated CUDA memory was 0.466 GiB.
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py) keeps PAN's
larger minimum smoke shape explicit.

No protocol-comparable accuracy benchmark exists for this recipe. The minimum
shape finding is a compatibility result, not an accuracy result. See the
[SMP component guide](../../components/smp/README.md).
