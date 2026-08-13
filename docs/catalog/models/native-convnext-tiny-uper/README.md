# Native ConvNeXt-Tiny + UPer

Recipe: [`native_convnext_tiny_uper.yaml`](../../../../configs/models/native_convnext_tiny_uper.yaml)

This is a modern convolutional alternative to the ResNet/UPer recipe. The exact
`convnext_tiny.fb_in22k_ft_in1k` backbone emits four feature scales, and UPer
fuses all four with pyramid pooling at the deepest level.

Pros:

- clean four-stage hierarchy;
- useful architectural contrast with ResNet;
- global and multi-scale context in the head.

Cons:

- “Tiny” still has about 27.8 million feature-extractor parameters;
- UPer adds substantial decoder work;
- 22k-to-1k initialization adds download/license/provenance dependencies.

## Advanced settings and compatibility

ConvNeXt exposes only four default feature entries, so its valid selection is
`[0, 1, 2, 3]`, unlike the five-entry ResNet/EfficientNet/MobileNet families.
Reducing UPer channels is the first memory lever. Keep CNN `llrd: 1.0`.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and returned
the 4/8/16/32 hierarchy at two CPU input shapes. UPer has isolated
forward/backward tests. The assembled YAML has parser evidence but no optimizer
smoke or common Segmentary mIoU benchmark.

See [native backbones](../../components/native-backbones/README.md) and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).
