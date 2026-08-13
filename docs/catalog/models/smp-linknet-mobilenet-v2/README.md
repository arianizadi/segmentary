# LinkNet with MobileNetV2

Recipe: [`smp_linknet_mobilenet_v2.yaml`](../../../../configs/models/smp_linknet_mobilenet_v2.yaml)

## Purpose and architecture

This is the latency-conscious shipped recipe. MobileNetV2 supplies efficient
inverted-residual features; LinkNet uses residual encoder-to-decoder links and a
small newly initialized dense head.

## Pros and cons

| pros | cons |
|---|---|
| small parameter count; efficient encoder and decoder; good deployment-oriented baseline | lower decoder and encoder capacity can reduce accuracy on complex scenes |

## Resource notes

At five classes the recipe has 4,319,991 parameters. Its diagnostic BF16
batch-1 64×64 forward allocated 23.1 MiB on an NVIDIA L40S. End-to-end latency
and memory must still be measured at the intended resolution and export backend.

## Tuning support

Full and frozen MobileNetV2 tuning are supported. Automatic LoRA is not
supported. Head reset replaces only the final segmentation head.

## Pretrained source

SMP 0.5.0 pins `encoder_weights: imagenet` to
[`smp-hub/mobilenet_v2.imagenet`](https://huggingface.co/smp-hub/mobilenet_v2.imagenet/tree/e67aa804e17f7b404b629127eabbd224c4e0690b)
revision `e67aa804e17f7b404b629127eabbd224c4e0690b`. The LinkNet
decoder is new. Set `encoder_weights: scratch` for scratch; a failed download does
not alter the configured choice.

## Verified evidence and benchmarks

On 2026-08-12 the exact LinkNet/MobileNetV2 pair loaded its requested ImageNet
encoder and passed four finite BF16/AdamW steps at batch 2 and 64×64. Its head
updated and peak allocated CUDA memory was 0.081 GiB. Normal scratch/frozen test
coverage is
[`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py).

No common-protocol accuracy or deployment benchmark has been recorded for this
recipe, so none is claimed. See the
[SMP component guide](../../components/smp/README.md).
