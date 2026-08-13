# UPerNet with MiT-B0

Recipe: [`smp_upernet_mit_b0.yaml`](../../../../configs/models/smp_upernet_mit_b0.yaml)

## Purpose and architecture

This is the shipped hybrid transformer-style option. Hierarchical MiT-B0
features feed UPerNet's pyramid-pooling module and feature pyramid before the
new segmentation head. It provides a compact alternative to the separate,
heavier Hugging Face UPerNet/ConvNeXt arm.

## Pros and cons

| pros | cons |
|---|---|
| hierarchical multi-scale encoder; broad pyramid head; modest parameter count | head is heavier than simple decoders; this SMP recipe is not checkpoint-compatible with the Hugging Face UPerNet arm |

## Resource notes

At five classes the recipe has 10,733,413 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 63.4 MiB on an NVIDIA L40S. Real-resolution
training must be measured separately.

## Tuning support

Full and frozen MiT tuning are supported. LoRA is not advertised for the SMP
MiT module layout because it has not passed Segmentary's projection-name and
head-preservation checks. Head reset affects the final segmentation head only.

## Pretrained source

SMP 0.5.0 maps the configured ImageNet tag to
[`smp-hub/mit_b0.imagenet`](https://huggingface.co/smp-hub/mit_b0.imagenet/tree/9ce53d104d92d75aabb00aae70677aaab67e7c84)
at revision `9ce53d104d92d75aabb00aae70677aaab67e7c84`. UPerNet and its
classifier are fresh. Set `encoder_weights: scratch` deliberately for scratch; a
load failure never changes the run to scratch.

## Verified evidence and benchmarks

On 2026-08-12 the exact UPerNet/MiT-B0 pair loaded its requested ImageNet encoder
and completed four finite BF16/AdamW steps at batch 2 and 64×64. The head
changed and peak allocated CUDA memory was 0.224 GiB. The repeatable
scratch/frozen check is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No same-protocol accuracy result exists for this recipe. Do not compare its
smoke memory with a differently sized model as a throughput benchmark. See the
[SMP component guide](../../components/smp/README.md).
