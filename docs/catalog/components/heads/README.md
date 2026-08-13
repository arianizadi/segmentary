# Segmentation heads and output strategy

The head converts backbone features into raw dense logits at input image
resolution. Multiclass heads return `(N,C,H,W)`, where `C` is the canonical
taxonomy size. A Segmentary-native binary head is the explicit exception: its
taxonomy still has two canonical classes, but it returns exactly one raw
class-1 positive logit `(N,1,H,W)` for sigmoid/threshold prediction.

## Beginner choice

Use `model.head: unified_head`. It is the only implemented strategy and is what
makes staged and mixed-dataset training safe: one classifier keeps the same
class meaning throughout the experiment, while each sample masks classes its
source dataset cannot label.

```yaml
model:
  head: unified_head
```

## Exact switches

`model.head` accepts two typed values, but only one is runnable:

| value | status | meaning |
|---|---|---|
| `unified_head` | implemented | one classifier over the canonical space; inactive logits are removed from each sample's loss |
| `per_stage_head` | unavailable | reserved config value; model construction raises rather than pretending separate heads exist |

At a stage boundary, the separate switch is:

```yaml
stages:
  - name: target
    init_from: previous
    reset_head: true
```

`reset_head: true` reinitializes the final classifier with the repository's
small-normal/zero-bias convention after loading the prior stage. It does not
change the label space and does not create one head per dataset.

For binary mode, `unified_head` still describes one stable canonical task, not
one head per dataset. Every mapping must activate both canonical IDs 0 and 1;
their names may be domain-specific. Partial active-class masking is unsafe with
one sigmoid logit and is rejected. See [Semantic task modes](../tasks/README.md).

## Head families

Segmentary-native composition exposes nine separately typed dense heads—FCN,
SegFormer, PSP, ASPP, DeepLabV3+, LR-ASPP, UPer, DPT, and OCR—plus named weighted auxiliary heads.
Their exact switches and per-head tradeoffs are in the
[native head guide](../native-heads/README.md).

All native main and auxiliary head families use one output channel when both
`model.native.task` and `loss.task` are `binary`. All other model integrations
remain multiclass; Segmentary does not silently discard one channel from a
two-class pretrained head.

- **Dense decode heads** (SegFormer, DeepLab, U-Net, FPN, PSPNet, UPerNet and
  related SMP decoders) naturally fit Segmentary's dense cross-entropy contract.
- **OCR** pools class-conditioned context. Its public inference tensor is the
  refined logits, while its rich training output also carries the named,
  positive-weight `ocr_coarse` logits required to supervise region gathering.
  See the [native head guide](../native-heads/README.md) for the multiclass and
  one-logit binary contracts.
- **EoMT/Mask2Former-style mask classification** predicts query classes and
  masks. Segmentary preserves the raw tensors for its native
  [Hungarian query objective](../query-objectives/README.md), then contracts them
  into a dense map for evaluation. Existing EoMT model YAMLs choose only the
  model and therefore keep the experimental dense-CE path unless `loss.query`
  is explicitly selected. Do not mix or silently compare the two objectives.
- **Hugging Face UPerNet/BEiT auxiliary heads** are disabled because Segmentary has
  one dense loss output. For `hf_auto`, only an exact audited
  `auxiliary_head.*` checkpoint prefix may be discarded; unrelated load gaps are
  fatal.

## Pros and cons of a unified head

Pros:

- class IDs keep one meaning across every stage;
- mixed batches can mask supervision independently per sample;
- classifier knowledge can transfer to a later dataset;
- result and checkpoint shapes remain stable.

Cons:

- the canonical space must be designed before training;
- a coarse dataset cannot supervise distinctions it does not label;
- large union spaces may include many inactive classes for one source;
- changing to another taxonomy is a separate experiment, not a stage option.

## Advanced cautions

`reset_head` is an ablation, not a default. It discards learned class priors and
only resets the final classifier; class-agnostic decoder/context layers remain.
If a checkpoint was built for a different canonical class count, exact loading
fails. Do not use reset as a workaround for a mismatched experiment.

For binary checkpoints, output shape is also part of compatibility: a one-logit
binary classifier and a two-logit multiclass classifier are not interchangeable
even though both can ultimately produce canonical IDs 0 and 1. Binary
query/mask heads and binary ONNX export are not implemented.

## Evidence and benchmark boundary

Tests verify classifier-only reset, output shape, model partitioning, and
per-sample inactive-class gradients. There is no protocol-comparable benchmark
isolating `reset_head` or an alternate head strategy. The mask-classification
and OCR objective deviations above must accompany any result from those arms.

## Related documentation

- [Semantic task modes](../tasks/README.md)
- [Backbones](../backbones/README.md)
- [Losses](../losses/README.md)
- [Query/mask objective](../query-objectives/README.md)
- [Taxonomy catalog](../../../../taxonomy/README.md)
- [Models and tuning guide](../../../guides/models-and-tuning.md)
