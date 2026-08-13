# Native MobileNetV3-Large + DeepLabV3+

Recipe: [`native_mobilenetv3_large_deeplabv3plus.yaml`](../../../../configs/models/native_mobilenetv3_large_deeplabv3plus.yaml)

This is the lowest-backbone-parameter native recipe in the initial set. The
exact `mobilenetv3_large_100.ra_in1k` pyramid feeds a reduced-width DeepLabV3+
head.

Pros:

- about 3.0 million feature-extractor parameters in the CPU probe;
- explicit low-level boundary skip despite the compact backbone;
- reasonable candidate for later deployment profiling.

Cons:

- low parameter count does not establish latency on a target device;
- the selected deepest feature is 960 channels, so decoder projections still matter;
- pretrained initialization adds download/license/provenance dependencies.

## Advanced settings and compatibility

Original feature entries `[1, 2, 3, 4]` become returned head indices `0..3` at
strides 4/8/16/32. The 160-channel main and 32-channel low-level projections are
deliberately smaller than the ResNet recipes. Profile the actual target device
before calling this an edge model.

## Evidence and benchmarks

The exact tagged feature extractor loaded requested weights without fallback and
passed two CPU feature shapes. DeepLabV3+ has isolated contract tests. The
assembled recipe has parser evidence only and no latency, memory, optimizer, or
common-data mIoU benchmark.

See [native backbones](../../components/native-backbones/README.md) and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).
