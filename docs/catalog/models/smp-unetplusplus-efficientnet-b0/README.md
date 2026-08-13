# U-Net++ with EfficientNet-B0

Recipe: [`smp_unetplusplus_efficientnet_b0.yaml`](../../../../configs/models/smp_unetplusplus_efficientnet_b0.yaml)

## Purpose and architecture

Use this when boundary refinement is important but the encoder should remain
compact. EfficientNet-B0 supplies multi-resolution features; U-Net++ uses nested,
dense skip pathways to reduce the semantic gap between encoder and decoder
features. The decoder and final classifier are newly initialized.

## Pros and cons

| pros | cons |
|---|---|
| compact encoder; dense skip fusion can help fine structures | more decoder connections and compute than U-Net; nested skips increase implementation complexity |

## Resource notes

With five classes this recipe has 6,570,161 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 38.7 MiB on an NVIDIA L40S. Real crop sizes,
batches, backward activations, and optimizer state will be much larger.

## Tuning support

Full and frozen-encoder tuning are supported. LoRA is not a verified tuning mode
for this SMP EfficientNet implementation. Head reset affects only the final
segmentation head.
SMP's EfficientNet class retains `_conv_head` and `_bn1` from image
classification, but its segmentation feature forward never calls them. The
recipe lists and freezes those exact modules; all other loss-reachable
parameters remain trainable in `full` mode.

## Pretrained source

`encoder_weights: imagenet` selects
[`smp-hub/efficientnet-b0.imagenet`](https://huggingface.co/smp-hub/efficientnet-b0.imagenet/tree/1bbe7ecc1d5ea1d2058de1a2db063b8701aff314)
at SMP-pinned revision `1bbe7ecc1d5ea1d2058de1a2db063b8701aff314`.
The U-Net++ decoder is not pretrained. Set the weight field to `scratch` explicitly
for scratch; load failures do not trigger a fallback.

## Verified evidence and benchmarks

On 2026-08-12 the exact U-Net++/EfficientNet-B0 combination loaded its requested
ImageNet encoder and completed four finite BF16/AdamW steps at batch 2 and
64×64. The head changed and peak allocated CUDA memory was 0.135 GiB. The
permanent scratch/frozen contract test is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

There is no protocol-comparable accuracy result for this recipe yet. The smoke
numbers must not be compared as accuracy or throughput benchmarks. See the
[SMP component guide](../../components/smp/README.md).
