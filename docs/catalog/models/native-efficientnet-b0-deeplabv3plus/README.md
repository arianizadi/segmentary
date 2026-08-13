# Native EfficientNet-B0 + DeepLabV3+

Recipe: [`native_efficientnet_b0_deeplabv3plus.yaml`](../../../../configs/models/native_efficientnet_b0_deeplabv3plus.yaml)

This combines the exact `efficientnet_b0.ra_in1k` feature extractor with the context and
low-level skip paths of DeepLabV3+. It is the smaller parameter-count
alternative to the ResNet-50 pairing.

Pros:

- about 3.6 million feature-extractor parameters in the CPU probe;
- retains a low-level path for boundaries;
- useful compact architecture study.

Cons:

- parameter count does not prove wall-clock speed or low activation memory;
- narrow features may underfit difficult scenes;
- DeepLab settings remain crop/output-stride dependent.

## Advanced settings and compatibility

The recipe selects original feature entries `[1, 2, 3, 4]`, making head index
`0` stride 4 and index `3` stride 32. The decoder is reduced to 160/32 channels
to match the compact intent. Measure before increasing them.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes. DeepLabV3+ has isolated contract tests. The assembled
recipe has parser evidence but no optimizer, latency, memory, or common-data
mIoU benchmark.

See the [native head guide](../../components/native-heads/README.md) and
[smoke ledger](../../../benchmarks/native-component-smokes/README.md).
