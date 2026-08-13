# DeepLabV3 with ResNet-50

Recipe: [`smp_deeplabv3_resnet50.yaml`](../../../../configs/models/smp_deeplabv3_resnet50.yaml)

## Purpose and architecture

This is the atrous-context baseline without the V3+ low-level refinement path.
ResNet-50 encodes the image, and DeepLabV3 applies atrous spatial pyramid pooling
at several dilation rates before the new segmentation classifier.

## Pros and cons

| pros | cons |
|---|---|
| broad receptive field; established dense-prediction baseline; simpler than V3+ | lacks V3+'s low-level boundary refinement; dilated features still carry a substantial compute cost |

## Resource notes

With five classes this recipe has 39,634,757 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 173.8 MiB on an NVIDIA L40S. Full training
memory at practical crops is much higher.

## Tuning support

Full and frozen ResNet tuning are supported. Automatic LoRA is not supported for
the convolutional backbone. Head reset keeps the ASPP decoder and resets only
the final classifier.

## Pretrained source

The encoder comes from
[`smp-hub/resnet50.imagenet`](https://huggingface.co/smp-hub/resnet50.imagenet/tree/00cb74e366966d59cd9a35af57e618af9f88efe9)
revision `00cb74e366966d59cd9a35af57e618af9f88efe9`, pinned by SMP
0.5.0. ASPP and the classifier are new. `encoder_weights: scratch` means scratch;
weight-loading failure remains an error rather than changing the experiment.

## Verified evidence and benchmarks

On 2026-08-12 the exact DeepLabV3/ResNet-50 pair loaded its requested ImageNet
encoder and completed four finite BF16/AdamW optimizer steps at batch 2 and
64×64. The segmentation head changed and peak allocated CUDA memory was 0.751
GiB. The normal-suite scratch/frozen contract is in
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No comparable Segmentary accuracy benchmark is available for this exact recipe,
so none is listed. See the [SMP component guide](../../components/smp/README.md).
