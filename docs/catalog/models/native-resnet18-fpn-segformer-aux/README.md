# Native ResNet-18 + FPN + SegFormer + FCN auxiliary head

Recipe: [`native_resnet18_fpn_segformer_aux.yaml`](../../../../configs/models/native_resnet18_fpn_segformer_aux.yaml)

This is the composition tutorial in executable YAML. The exact
`resnet18.a1_in1k` backbone and FPN produce a uniform feature pyramid; a
SegFormer-style MLP head predicts the main logits;
an FCN head on the stride-16 FPN level adds a training-only loss weighted `0.4`.

Pros:

- demonstrates independently switchable native components in one small stack;
- auxiliary supervision supplies a shorter gradient path;
- main deployment `forward` stays a single dense tensor.

Cons:

- auxiliary logits and loss add training memory/compute;
- the `0.4` weight is an engineering starting point, not an optimum;
- coarse auxiliary supervision may work against fine boundaries.

## Advanced settings and compatibility

The auxiliary name must stay unique. Its feature index is evaluated after FPN;
index `2` is the third returned pyramid level. Set `loss_weight` lower to reduce
its influence or remove the entire list for a controlled ablation. The same
configured objective suite applies to main and auxiliary logits. Export and
ordinary inference use only the main logits.

## Evidence and benchmarks

The exact tagged backbone loaded requested weights without fallback and passed
two CPU feature shapes. The corresponding scratch
ResNet-18/FPN/SegFormer/FCN-aux stack passed four CPU optimizer steps with finite
loss, changed parameters, and a CPU Gloo DDP no-unused-parameter check. The
pretrained YAML has parser evidence but not an assembled optimizer smoke. No
common Segmentary mIoU benchmark exists.

See [native heads](../../components/native-heads/README.md),
[native necks](../../components/native-necks/README.md), and the
[smoke ledger](../../../benchmarks/native-component-smokes/README.md).
