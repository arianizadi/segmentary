# FPN with ResNet-50

Recipe: [`smp_fpn_resnet50.yaml`](../../../../configs/models/smp_fpn_resnet50.yaml)

## Purpose and architecture

This recipe is a conventional multi-scale baseline. ResNet-50 produces a
hierarchy of features; the Feature Pyramid Network combines them through a
top-down pyramid and produces dense logits with a fresh segmentation head.

## Pros and cons

| pros | cons |
|---|---|
| simple multi-scale design; useful when object sizes vary; easy baseline to interpret | the lightweight fusion head may lose fine boundaries; larger encoder than mobile recipes |

## Resource notes

At five classes the model has 26,116,549 parameters. The diagnostic BF16
batch-1 64×64 forward allocated 111.4 MiB on an NVIDIA L40S. This excludes
training gradients and optimizer state and should only size a first smoke run.

## Tuning support

Full and frozen ResNet tuning are supported. Automatic LoRA is not supported for
this convolutional encoder. Resetting the head reinitializes the final
classifier but retains the FPN decoder.

## Pretrained source

The configured ImageNet encoder is
[`smp-hub/resnet50.imagenet`](https://huggingface.co/smp-hub/resnet50.imagenet/tree/00cb74e366966d59cd9a35af57e618af9f88efe9)
at revision `00cb74e366966d59cd9a35af57e618af9f88efe9`, as pinned by SMP
0.5.0. FPN and the classifier start fresh. Use `encoder_weights: scratch` only when
scratch training is intended; a failed pretrained request is never downgraded.

## Verified evidence and benchmarks

On 2026-08-12 the exact FPN/ResNet-50 pair loaded its requested ImageNet encoder
and passed four BF16/AdamW steps at batch 2 and 64×64. Losses were finite, the
head changed, and peak allocated CUDA memory was 0.498 GiB.
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py) keeps the
scratch/frozen contract in the normal test suite.

No accuracy number from a common Segmentary protocol exists for this recipe, so no
benchmark is shown. See the [SMP component guide](../../components/smp/README.md).
