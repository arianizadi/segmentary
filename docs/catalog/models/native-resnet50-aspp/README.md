# Native ResNet-50 + ASPP

Recipe: [`native_resnet50_aspp.yaml`](../../../../configs/models/native_resnet50_aspp.yaml)

ASPP applies parallel atrous convolutions and a global-context branch to the
deepest selected `resnet50.a1_in1k` feature. Choose it when the experiment is about
multi-scale receptive fields without a low-level skip connection.

Pros:

- several context scales in one head;
- simple single-feature input;
- useful control for the DeepLabV3+ recipe.

Cons:

- limited high-resolution detail path;
- dilation rates depend on feature stride and crop size;
- pretrained initialization adds download/license/provenance dependencies.

## Advanced settings and compatibility

The shipped `[6, 12, 18]` rates are a starting choice, not a universal optimum.
Change them only as a named ablation. GroupNorm avoids the batch-one problem in
the global pooled branch. Head `in_index: 3` refers to the returned four-level
tuple after `out_indices: [1, 2, 3, 4]`.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes; ASPP has isolated forward/backward contract tests. This
assembled YAML has parser evidence but no recorded optimizer smoke or
common-data mIoU benchmark.

See [native heads](../../components/native-heads/README.md) and the
[evidence ledger](../../../benchmarks/native-component-smokes/README.md).
