# UPerNet with ResNet-101

Recipe: [`smp_upernet_resnet101.yaml`](../../../../configs/models/smp_upernet_resnet101.yaml)

## Purpose and architecture

This is the explicit, provenance-friendly form of the old `upernet_r101`
factory alias. A ResNet-101 encoder provides four feature levels; UPerNet adds
pyramid pooling, a feature pyramid, and a new dataset-specific segmentation
head. Only the encoder receives ImageNet weights.

## Pros and cons

| pros | cons |
|---|---|
| conventional multi-scale CNN baseline; dense-CE objective matches the trainer; explicit decoder/encoder/weight fields | ResNet-101 and UPerNet are relatively heavy; decoder and classifier start fresh; convolutional encoder is not supported by automatic attention LoRA |

Use this recipe when you want a transparent ResNet pyramid control or need to
migrate an older `arch: upernet_r101` experiment. Prefer the explicit form for
new results because the resolved config explains the model without knowing
alias-specific `checkpoint` behavior.

## Advanced settings

Full and frozen tuning are supported. Frozen mode keeps the encoder and its
normalization state fixed while training UPerNet. `llrd` must remain `1.0`
because Segmentary does not infer transformer-style block depth from ResNet.
`reset_head` changes only the final segmentation predictor, not the decoder.

Use RGB ImageNet normalization and dimensions divisible by 32. Measure the
intended crop and batch on the target GPU; tiny-smoke memory is not a training
capacity estimate.

## Pretrained source

SMP 0.5.0 resolves `encoder_name: resnet101` with
`encoder_weights: imagenet` through its reviewed encoder-weight catalog. A
failed load is fatal. Set `encoder_weights: scratch` only when scratch training is
intentional and should be recorded as such.

## Evidence and benchmarks

The legacy alias has a real CUDA regression that loads ImageNet ResNet-101 and
checks finite BF16, input-resolution output on a non-square input. The generic
SMP tests exercise UPerNet forward/backward behavior and the frozen
backbone/head contract. These prove compatibility, not accuracy or throughput.

No same-protocol Segmentary accuracy benchmark exists for this recipe. Run the
eight-image overfit check and a short real-data training smoke before a full
experiment. See the [SMP component guide](../../components/smp/README.md), the
[legacy alias page](../builtin-upernet-r101-alias/README.md), and the
[benchmark evidence rules](../../../benchmarks/README.md).
