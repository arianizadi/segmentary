# MA-Net with EfficientNet-B0

Recipe: [`smp_manet_efficientnet_b0.yaml`](../../../../configs/models/smp_manet_efficientnet_b0.yaml)

## Purpose and architecture

Use this recipe to test whether decoder attention helps multi-scale segmentation
without using a large encoder. EfficientNet-B0 provides the hierarchy; MA-Net
adds position-wise and multi-scale attention before the fresh classifier.

## Pros and cons

| pros | cons |
|---|---|
| compact encoder; explicit attention across feature scales; useful architectural contrast | more decoder complexity than skip-only designs; attention benefit is dataset-dependent |

## Resource notes

With five classes the model has 9,092,937 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 48.6 MiB on an NVIDIA L40S. That tiny inference
probe does not predict real training memory or speed.

## Tuning support

Full and frozen EfficientNet tuning are supported. Segmentary does not advertise
LoRA for this SMP encoder/decoder layout. Head reset reinitializes only the
segmentation head.
SMP's EfficientNet class retains `_conv_head` and `_bn1` from image
classification, but its segmentation feature forward never calls them. The
recipe lists and freezes those exact modules; all other loss-reachable
parameters remain trainable in `full` mode.

## Pretrained source

The ImageNet encoder source is
[`smp-hub/efficientnet-b0.imagenet`](https://huggingface.co/smp-hub/efficientnet-b0.imagenet/tree/1bbe7ecc1d5ea1d2058de1a2db063b8701aff314)
at revision `1bbe7ecc1d5ea1d2058de1a2db063b8701aff314`, pinned by SMP
0.5.0. The MA-Net decoder starts from random weights. Use `scratch` explicitly for
scratch; pretraining failures are not hidden.

## Verified evidence and benchmarks

On 2026-08-12 the exact MA-Net/EfficientNet-B0 configuration loaded its requested
ImageNet encoder and completed four finite BF16/AdamW steps at batch 2 and
64×64. The head changed and peak allocated CUDA memory was 0.183 GiB. The
repeatable scratch/frozen contract is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No protocol-comparable accuracy benchmark has been generated for this recipe.
See the [SMP component guide](../../components/smp/README.md).
