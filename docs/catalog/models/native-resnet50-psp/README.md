# Native ResNet-50 + PSP

Recipe: [`native_resnet50_psp.yaml`](../../../../configs/models/native_resnet50_psp.yaml)

This recipe takes the deepest selected `resnet50.a1_in1k` feature and pools it over
several grid sizes before fusion. It is a focused way to test whether broad
scene context helps a dense task.

Pros:

- explicit local-to-global context in a compact conceptual design;
- fewer multi-level fusion paths than UPer;
- exact admitted ImageNet-1k feature initialization.

Cons:

- predicts from one deep level, so fine boundaries rely on upsampling;
- pooling bins and crop size interact;
- ResNet-50 is materially larger than the ResNet-18 baseline.

## Advanced settings and compatibility

Start with bins `[1, 2, 3, 6]`, 256 channels, GroupNorm, and crops comfortably
larger than the deepest feature grid. Use `norm: batch` only with enough values
per channel; the 1x1 pooled branch makes batch-size-one training unsafe.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes. PSP has isolated forward/backward contract tests. The
assembled recipe has parser evidence, not a recorded optimizer smoke. No common
Segmentary quality benchmark exists for it.

See the [native head guide](../../components/native-heads/README.md) and
[smoke ledger](../../../benchmarks/native-component-smokes/README.md).
