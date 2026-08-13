# Segmentary-native necks

A neck sits between the backbone and the prediction head. It may preserve the
feature tuple or reshape it into a more convenient pyramid. Necks never choose
the dataset, classes, loss, or final classifier.

## Available choices

| `kind` | what it does | when to use it | pros | cons |
|---|---|---|---|---|
| `identity` | validates and passes all selected backbone features unchanged | the head already understands their channel widths and scales | no extra parameters; clearest baseline | does not standardize channels or create scales |
| `channel_mapper` | independently projects every level to one channel width; optional extra levels are learned stride-2 projections | the head owns fusion but requires equal-width inputs, especially the native DPT head | clean separation of projection from fusion; preserves each original resolution | adds parameters/normalization; does not exchange information between levels |
| `fpn` | projects each level to one width, merges coarse context top-down, then smooths every level | a head benefits from equal-width multi-scale features | reusable pyramid; combines semantic and spatial levels | extra memory/compute; requires strictly increasing reductions |

## Beginner settings

Use identity with PSP, ASPP, DeepLabV3+, or UPer recipes. Use this small FPN
when you specifically want to compare a separate feature-pyramid stage:

```yaml
neck:
  kind: fpn
  out_channels: 128
  num_outputs: 4
  norm: group
  activation: relu
```

Use ChannelMapper when the downstream head, rather than the neck, should own
cross-scale fusion:

```yaml
neck:
  kind: channel_mapper
  out_channels: 256
  kernel_size: 1
  num_outputs: 4
  norm: group
  activation: relu
```

For four ConvNeXt levels with widths 96/192/384/768, this returns the same
4/8/16/32 spatial hierarchy with width 256 at every level. There is no hidden
top-down addition: output level 0 depends only on input level 0, and so on.

## Advanced settings and compatibility

- `out_channels` controls every FPN output width. Smaller saves memory; larger
  may preserve more information. The same control applies to ChannelMapper. It
  is a hyperparameter, not a quality promise.
- `num_outputs` may equal or exceed the input count; neither neck can silently
  discard inputs. FPN pools extra levels. ChannelMapper creates each extra level
  with a learned stride-2 3x3 block from the preceding mapped output.
- ChannelMapper `kernel_size` is a positive odd integer. `1` performs the
  simplest channel projection. `3` adds local spatial mixing and compute but
  still does not mix pyramid levels.
- `norm` is `group`, `batch`, `instance`, `layer`, or `none`. Group
  normalization is the shipped default because segmentation often uses tiny
  per-device batches. Batch normalization can be useful with genuinely large
  batches but is sensitive to batch statistics. The
  [block guide](../native-blocks/README.md) explains the less common choices.
- `activation` is `relu`, `relu6`, `leaky_relu`, `gelu`, `silu`, `elu`, `mish`,
  or `hardswish`. ReLU is the conservative default; changing it is an
  architecture ablation, not a harmless runtime switch.
- Head feature indices are evaluated after the neck. With four FPN outputs,
  valid indices are `0` through `3`; the same is true for a four-output
  ChannelMapper.
- The DPT head requires exactly four progressively coarser, equal-width inputs.
  Set ChannelMapper `out_channels` equal to DPT `channels`. FPN can also satisfy
  the shape contract, but it adds top-down fusion before DPT and therefore tests
  a different architecture.

## Evidence and benchmarks

Contract tests cover metadata, unequal input sizes, extra levels, backward,
invalid settings, and ChannelMapper's lack of cross-level coupling. A real
ResNet-18/FPN/SegFormer stack passed four CPU optimizer steps and a Gloo DDP
check. ConvNeXt-Tiny/ChannelMapper/DPT has a separate CPU forward/backward test
and four-step toy-stack optimizer test. Its exact pretrained recipe also passed
a retained four-step GPU8 BF16 production-objective smoke at two shapes. These
establish wiring and optimizer compatibility, not accuracy.

No same-protocol quality benchmark isolates identity, ChannelMapper, or FPN, so
none is ranked by mIoU.

See [native backbones](../native-backbones/README.md),
[native heads](../native-heads/README.md), and
[native blocks](../native-blocks/README.md).
