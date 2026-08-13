# UPerNet/ResNet-101 compatibility alias

`upernet_r101` preserves the original short factory name. It has no shipped
model YAML. New configs should use the shipped
[`smp_upernet_resnet101.yaml`](../../../../configs/models/smp_upernet_resnet101.yaml)
recipe, which uses the typed `arch: smp` form:

```yaml
model:
  arch: smp
  smp_arch: UPerNet
  encoder_name: resnet101
  encoder_weights: imagenet
  tuning: full
  head: unified_head
```

## What it is

SMP's ResNet-101 encoder produces a multi-level feature hierarchy. UPerNet
combines pyramid pooling at the deepest level with a feature-pyramid decoder,
then produces full-resolution semantic logits. Only the encoder receives
ImageNet weights; decoder and classifier start fresh.

The alias's `checkpoint` field is an encoder-name override, not a training
checkpoint. Use a stage's `init_from` field to resume or transfer trained
Segmentary weights.

Pros:

- conventional and interpretable multi-scale CNN baseline;
- dense-CE objective matches the common Segmentary trainer;
- full and frozen tuning have a clear backbone/head split;
- useful control for UPerNet with newer encoders.

Cons:

- ResNet-101 and UPerNet are both relatively heavy;
- decoder begins from random initialization;
- alias syntax hides encoder and weight choices inside special-case behavior;
- convolutional encoder does not support automatic attention LoRA;
- no Segmentary accuracy or deployment benchmark is recorded.

## Verification and first run

The real GPU integration regression loads this alias and verifies finite BF16
input-resolution output on a non-square input. Alias-specific tests also prove
that the encoder-name override reaches the expected SMP constructor. These are
compatibility checks, not quality or latency measurements.

Use RGB ImageNet normalization, a crop divisible by 32, and a small real-data
baby run before scheduling full training. Prefer the explicit SMP form for all
new result tables so the resolved config explains itself without knowing alias
rules.

See the [SMP component](../../components/smp/README.md), the shipped
[UPerNet/ResNet-101 recipe](../smp-upernet-resnet101/README.md), and the
[built-in model component](../../components/builtin-models/README.md).
