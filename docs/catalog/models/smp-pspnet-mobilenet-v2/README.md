# PSPNet with MobileNetV2

Recipe: [`smp_pspnet_mobilenet_v2.yaml`](../../../../configs/models/smp_pspnet_mobilenet_v2.yaml)

## Purpose and architecture

Use this as a small model with explicit global context. MobileNetV2 is the
efficient encoder; PSPNet pools its deepest features at several spatial scales
before a newly initialized segmentation classifier.

## Pros and cons

| pros | cons |
|---|---|
| smallest shipped SMP recipe; global pyramid context; useful for constrained experiments | limited encoder capacity; pooled context can soften precise boundaries |

## Resource notes

At five classes this recipe has 2,281,789 parameters. The diagnostic BF16
batch-1 64×64 GPU forward allocated 17.7 MiB on an NVIDIA L40S, the lowest
small-input allocation in this catalog. Do not extrapolate that number directly
to full-resolution training.

## Tuning support

Full and frozen MobileNetV2 tuning are supported. Automatic LoRA is not supported
for this convolutional encoder. Head reset retains the PSP decoder and replaces
the final segmentation classifier.
This PSPNet constructor requests a shallow MobileNet feature depth. SMP retains
later `encoder.features.7` through `.18` modules in the object but does not call
them; the recipe explicitly freezes those exact paths so strict DDP still
detects any other disconnected branch.

## Pretrained source

`encoder_weights: imagenet` maps to
[`smp-hub/mobilenet_v2.imagenet`](https://huggingface.co/smp-hub/mobilenet_v2.imagenet/tree/e67aa804e17f7b404b629127eabbd224c4e0690b)
at revision `e67aa804e17f7b404b629127eabbd224c4e0690b`. SMP 0.5.0 pins
that source; the PSP decoder is fresh. `scratch` is the deliberate scratch option,
and no fallback hides download failures.

## Verified evidence and benchmarks

On 2026-08-12 the exact PSPNet/MobileNetV2 recipe loaded its requested ImageNet
encoder and completed four finite BF16/AdamW steps at batch 2 and 64×64. The
head changed and peak allocated CUDA memory was 0.033 GiB. See
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py) for the
repeatable scratch/frozen backward check.

No same-protocol accuracy benchmark has been run for this recipe. Parameter and
smoke-memory figures are not an accuracy claim. See the
[SMP component guide](../../components/smp/README.md).
