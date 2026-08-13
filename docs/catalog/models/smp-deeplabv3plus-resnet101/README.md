# DeepLabV3+ with ResNet-101

Recipe: [`smp_deeplabv3plus_resnet101.yaml`](../../../../configs/models/smp_deeplabv3plus_resnet101.yaml)

## Purpose and architecture

This is the high-capacity conventional baseline. ResNet-101 supplies the feature
hierarchy; DeepLabV3+ combines atrous spatial pyramid context with a low-level
refinement path to recover boundaries. The decoder and classifier start fresh.

## Pros and cons

| pros | cons |
|---|---|
| established architecture; combines broad context and local refinement; useful sanity reference | largest shipped SMP recipe by parameter count; slower and more memory-intensive than mobile or ResNet-50 choices |

## Resource notes

At five classes the recipe has 45,670,741 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 187.6 MiB on an NVIDIA L40S. Production training
adds large activation, gradient, optimizer, and crop-size costs.

## Tuning support

Full and frozen ResNet tuning are supported. Automatic LoRA is not supported for
this convolutional encoder. Head reset changes only the final segmentation
classifier, retaining the V3+ decoder.

## Pretrained source

SMP 0.5.0 maps the ImageNet tag to
[`smp-hub/resnet101.imagenet`](https://huggingface.co/smp-hub/resnet101.imagenet/tree/cd7c15e8c51da86ae6a084515fdb962d0c94e7d1)
at revision `cd7c15e8c51da86ae6a084515fdb962d0c94e7d1`. Only the encoder
is pretrained. Set `encoder_weights: scratch` deliberately for scratch; load
failures never cause an automatic scratch retry.

## Verified evidence and benchmarks

On 2026-08-12 the exact DeepLabV3+/ResNet-101 pair loaded its requested ImageNet
encoder and ran four finite BF16/AdamW steps at batch 2 and 64×64. Its head
updated and peak allocated CUDA memory was 0.866 GiB. The repeatable
scratch/frozen regression is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

The older `deeplabv3plus_r101` alias has [untrained deployment compatibility
evidence](../../../benchmarks/deeplabv3plus-r101-untrained-export/README.md), but it
must not be treated as an accuracy benchmark for a new dataset or protocol. No
same-protocol accuracy result exists for this recipe yet. See the
[SMP component guide](../../components/smp/README.md).
