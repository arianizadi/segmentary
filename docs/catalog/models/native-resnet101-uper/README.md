# Native ResNet-101 + UPer

Recipe: [`native_resnet101_uper.yaml`](../../../../configs/models/native_resnet101_uper.yaml)

UPer adds pyramid pooling to the deepest feature and then fuses the whole
fine-to-coarse hierarchy. Paired with `resnet101.a1_in1k`, this is the high-capacity
native CNN recipe in the initial catalog.

Pros:

- combines global scene context with all four selected scales;
- deeper backbone offers more representational capacity;
- direct identity neck keeps the model graph understandable.

Cons:

- largest backbone parameter count in this native set;
- highest expected training memory/compute among these recipes;
- capacity is wasteful until data and overfit checks are healthy.

## Advanced settings and compatibility

Begin at 256 decoder channels and GroupNorm. Reducing channels is the first
memory lever. Keep `llrd: 1.0`: this is a CNN and no layerwise schedule is
claimed. The four head indices refer to the four selected ResNet outputs.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes. UPer has isolated forward/backward tests. The assembled
YAML has parser evidence only; there is no recorded optimizer smoke, memory
measurement, latency result, or common-data mIoU benchmark.

See [native backbones](../../components/native-backbones/README.md),
[native heads](../../components/native-heads/README.md), and the
[smoke ledger](../../../benchmarks/native-component-smokes/README.md).
