# Segmentary-native timm backbones

The native backbone adapter turns an image into a checked tuple of feature maps.
It uses timm's public `features_only` interface, but the composition, validation,
heads, checkpoints, and training loop belong to Segmentary. It does not import or
execute another segmentation framework.

## Beginner choice

Start with the admitted `resnet18.a1_in1k` tag, pretrained weights, and feature
indices `[1, 2, 3, 4]`. That is a small, familiar transfer-learning baseline
before spending time on a larger encoder. Use `weights: scratch` deliberately
for an offline smoke or a controlled no-pretraining experiment.

```yaml
backbone:
  kind: timm
  name: resnet18.a1_in1k
  weights: pretrained
  out_indices: [1, 2, 3, 4]
  in_channels: 3
```

## What every switch means

| setting | plain meaning | advanced notes |
|---|---|---|
| `kind: timm` | select the one implemented native backbone adapter | no arbitrary constructor arguments are forwarded |
| `name` | exact timm constructor name | availability is tied to pinned `timm==1.0.28`; probe a new name before adding a recipe |
| `weights: scratch` | random initialization, no download | requires enough training data/schedule; use for offline/ablation work |
| `weights: pretrained` | ask timm for its configured pretrained weights | shipped recipes use only exact names that passed admission; the resolved config records the exact tag and the result environment records the timm version |
| `out_indices` | which timm feature levels to return, in increasing order | downstream indices refer to this returned tuple, not timm's original level numbers |
| `in_channels` | input image channels | currently must be RGB `3`; configuration fails early for any other value because the public dataset pipeline decodes RGB images |

Segmentary checks that runtime tensors match timm's reported channel counts and
spatial reductions. A missing feature level, wrong layout, fixed-size failure,
or invalid model name stops construction or forward with context. Pretrained
construction also fails if timm does not expose complete mean/std metadata;
Segmentary will not silently guess a checkpoint's input distribution. Scratch
models use an explicit Segmentary ImageNet-style RGB default and identify that
source in the result record.

## CPU-probed families

The following scratch construction facts were observed with PyTorch
`2.11.0+cu128`, timm `1.0.28`, one `1x3x128x128` CPU tensor, and timm's default
feature list on 2026-08-12. Recipes select the last four useful levels.

| name | parameters in timm feature extractor | default channels | reductions | pros | cons |
|---|---:|---|---|---|---|
| `resnet18` | 11,176,512 | 64/64/128/256/512 | 2/4/8/16/32 | smallest conventional baseline here; simple to debug | least capacity of the ResNets; scratch training may underfit |
| `resnet50` | 23,508,032 | 64/256/512/1024/2048 | 2/4/8/16/32 | established higher-capacity CNN hierarchy | wider deep features raise decoder memory and compute |
| `resnet101` | 42,500,160 | 64/256/512/1024/2048 | 2/4/8/16/32 | deeper contextual backbone | slowest and largest ResNet here; not justified for first data checks |
| `convnext_tiny` | 27,818,592 | 96/192/384/768 | 4/8/16/32 | clean four-scale modern convolutional pyramid | index layout differs from the five-level families; larger than its name suggests |
| `efficientnet_b0` | 3,595,388 | 16/24/40/112/320 | 2/4/8/16/32 | compact feature extractor | narrow features may limit hard scenes; exact speed depends on hardware |
| `mobilenetv3_large_100` | 2,971,952 | 16/24/40/112/960 | 2/4/8/16/32 | lowest parameter count in this set | final feature is much wider than earlier levels; parameter count is not latency evidence |

These are construction facts, not latency, memory, or quality rankings. The raw
probe record is in the [native component smoke ledger](../../../benchmarks/native-component-smokes/README.md).

## Pros and cons of native composition

Pros:

- backbone, neck, head, and auxiliary heads are independently typed;
- feature metadata is checked before modules are connected;
- an explicit scratch switch supports offline and no-pretraining ablations;
- one new backbone can be evaluated with several heads without a new wrapper.

Cons:

- timm names are an upstream compatibility surface;
- scratch initialization usually needs more data and training than pretrained initialization;
- an arbitrary timm classifier is not automatically a useful dense backbone;
- only features with valid NCHW/NHWC metadata and spatial reductions are accepted.

## Advanced compatibility and evidence

FPN requires a strictly fine-to-coarse hierarchy. Identity passes feature
metadata unchanged. Head indices must exist after the selected neck. CNN
backbones should normally keep `optim.llrd: 1.0`; automatic LoRA is not promised.
Use `tuning: full` for the ordinary recipe. `tuning: frozen` is a cheap feature
diagnostic, not a likely final setting. The shipped convolutional tags have no
admitted automatic LoRA targets. Fresh necks and heads use `head_lr_mult: 10.0`
over the recipe's `1e-4` pretrained-backbone learning rate; treat both as
starting values and change them as a named optimization ablation.

The six untagged family names above passed a scratch CPU feature-extraction
probe. Exact tagged pretrained variants used by the recipes then loaded the
requested weights without fallback and passed both `64x96` and odd `65x97`
feature probes. Exact sources and normalization are in the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md). The
native component suite also covers real scratch ResNet-18 construction,
forward/backward, four optimizer steps, and CPU Gloo DDP. No common-dataset mIoU
benchmark exists for any native recipe yet.

See [native necks](../native-necks/README.md), [native heads](../native-heads/README.md),
and the [native model recipe index](../../../../configs/models/README.md).
