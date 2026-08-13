# U-Net with ResNet-34

Recipe: [`smp_unet_resnet34.yaml`](../../../../configs/models/smp_unet_resnet34.yaml)

## Purpose and architecture

This is the safest general-purpose SMP starting point. A ResNet-34 encoder
produces a five-level feature hierarchy; U-Net upsamples it while fusing
same-scale encoder features through direct skip connections. The decoder and
taxonomy-sized segmentation head start from random weights.

## Pros and cons

| pros | cons |
|---|---|
| familiar architecture; reliable small-data baseline; skip paths preserve detail | high-resolution skip activations increase training memory; global context is limited compared with pyramid-context heads |

## Resource notes

With five output classes this recipe has 24,436,949 parameters. The diagnostic
BF16 batch-1 64×64 forward allocated 110.9 MiB on an NVIDIA L40S. Those are
smoke-test figures, not a production memory estimate; full-resolution training
also stores activations, gradients, and optimizer state.

## Tuning support

Full and frozen-encoder tuning are supported. Segmentary does not advertise LoRA
for the convolutional ResNet encoder. A head reset changes the final
segmentation head, not the whole U-Net decoder.

## Pretrained source

`encoder_weights: imagenet` resolves through SMP 0.5.0 to
[`smp-hub/resnet34.imagenet`](https://huggingface.co/smp-hub/resnet34.imagenet/tree/7a57b34f723329ff020b3f8bc41771163c519d0c)
at revision `7a57b34f723329ff020b3f8bc41771163c519d0c`. Write
`encoder_weights: scratch` for an intentional scratch encoder. A failed load is
fatal; there is no scratch fallback.

## Verified evidence and benchmarks

On 2026-08-12 the exact U-Net/ResNet-34 combination loaded its requested ImageNet
encoder and completed four finite BF16/AdamW steps at batch 2 and 64×64. The
head changed and peak allocated CUDA memory was 0.476 GiB. The repeatable
scratch/frozen contract lives in
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No protocol-comparable accuracy benchmark has been recorded for this recipe, so
none is reported. Tiny synthetic losses and memory probes are not model-quality
benchmarks. See the [SMP component guide](../../components/smp/README.md) for the
shared evidence protocol.
