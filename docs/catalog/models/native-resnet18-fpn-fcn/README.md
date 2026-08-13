# Native ResNet-18 + FPN + FCN

Recipe: [`native_resnet18_fpn_fcn.yaml`](../../../../configs/models/native_resnet18_fpn_fcn.yaml)

This is the smallest conventional multi-scale native recipe. The exact
`resnet18.a1_in1k` backbone emits
four selected feature levels, FPN makes them all 128 channels, and FCN resizes
and concatenates the pyramid before two ordinary convolutions and a classifier.

## When to use it

Use it for a first native-component run, a dataset plumbing check, or a readable
baseline before trying context-heavy heads.

Pros:

- relatively small and easy to reason about;
- explicit feature pyramid supports objects at several scales;
- every decoder component is Segmentary-owned and independently checked;
- exact admitted ImageNet-1k feature initialization.

Cons:

- pretrained initialization adds a download/license/provenance dependency;
- FCN has less explicit global context than PSP, ASPP, or UPer;
- FPN adds memory compared with an identity neck.

## Advanced settings and compatibility

Reduce `out_channels` and FCN `channels` together for a smaller smoke. Increase
them only after measuring memory. All selected FPN indices are post-neck indices.
Keep `llrd: 1.0` for this CNN. GroupNorm is safe for small batches; BatchNorm
needs representative batch statistics.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes, including odd dimensions. The native suite separately
passed scratch FPN/head shape, backward, optimizer, and DDP tests. The assembled
pretrained recipe has parser evidence, not an optimizer smoke. No common-data
mIoU benchmark exists for this exact recipe.

See [native backbones](../../components/native-backbones/README.md),
[necks](../../components/native-necks/README.md), and
[heads](../../components/native-heads/README.md).
