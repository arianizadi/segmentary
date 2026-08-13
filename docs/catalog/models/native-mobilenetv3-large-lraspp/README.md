# Native MobileNetV3-Large + LR-ASPP

Recipe: [`native_mobilenetv3_large_lraspp.yaml`](../../../../configs/models/native_mobilenetv3_large_lraspp.yaml)

This is Segmentary's smallest native mobile-oriented composition. The exact
`mobilenetv3_large_100.ra_in1k` feature pyramid feeds a lightweight head: one
fine feature is classified directly, while a projected deep feature is
modulated by an image-level sigmoid gate and added back at the fine scale.

Pros:

- substantially less decoder work than the DeepLabV3+ recipe;
- direct fine-feature prediction preserves a short boundary path;
- the global gate uses no BatchNorm, so batch-one training remains valid.

Cons:

- less multi-scale context than ASPP, UPer, or FPN compositions;
- low parameter count does not prove low latency on a specific device;
- only one low and one high feature participate in the prediction.

## Beginner use

Use it when memory or deployment cost matters enough to justify a deliberately
small decoder. Keep the shipped indices, 128 channels, GroupNorm, and ReLU for
the first overfit check. Compare it against MobileNetV3 + DeepLabV3+ under the
same data, crop, schedule, seed, EMA, and evaluator rather than comparing paper
numbers from different protocols.

## Advanced settings and compatibility

`low_index` must name a finer feature than `high_index`; the shipped returned
features have reductions 4/8/16/32. `channels` sizes only the deep projection.
`dropout`, every native activation, and every native normalization are typed.
The image-level gate always remains an unnormalized convolution followed by
sigmoid, preventing a pooled 1x1 BatchNorm failure. The two class projections
reset together at a taxonomy boundary.

## Evidence and benchmarks

The exact pretrained backbone tag loaded without fallback and passed two CPU
feature shapes. LR-ASPP has direct forward/backward, batch-one BatchNorm, and
classifier-reset contract tests. The assembled recipe has parser evidence; it
has no common-data mIoU, latency, memory, or multi-seed benchmark yet.

See [native heads](../../components/native-heads/README.md),
[native backbones](../../components/native-backbones/README.md), and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).
