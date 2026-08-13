# Native ResNet-50 + DeepLabV3+

Recipe: [`native_resnet50_deeplabv3plus.yaml`](../../../../configs/models/native_resnet50_deeplabv3plus.yaml)

This head combines ASPP context from the coarsest selected feature with an
early high-resolution skip from `resnet50.a1_in1k`. It is the native catalog's balanced ResNet recipe
for both scene context and boundaries.

Pros:

- explicit low-level detail path;
- multi-rate context in the deep path;
- familiar architecture for controlled head comparisons.

Cons:

- more compute and knobs than plain ASPP;
- low/high feature selection must match the returned backbone tuple;
- pretrained initialization adds download/license/provenance dependencies.

## Advanced settings and compatibility

Here `low_index: 0` is stride 4 and `high_index: 3` is stride 32 because the
backbone returns original levels `[1, 2, 3, 4]`. Keep indices ordered. Tune
`low_channels`, main `channels`, and dilation rates one family at a time. Use
GroupNorm for small segmentation batches.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes; DeepLabV3+ has isolated forward/backward contract tests.
The assembled recipe has parser evidence but no recorded optimizer smoke. No
common Segmentary mIoU benchmark exists.

See [native heads](../../components/native-heads/README.md) and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).
