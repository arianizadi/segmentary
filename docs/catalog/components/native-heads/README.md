# Segmentary-native dense heads

Every native head takes a checked feature tuple and returns **raw dense logits at
the input image size**. No head hides its own activation, loss, or
preprocessing — the trainer applies the objective you configured.

- **Multiclass:** one channel per canonical class.
- **Binary:** exactly one raw class-1 positive logit, even though the taxonomy
  holds IDs 0 and 1.
- **OCR** is the one exception: it also declares a named, positive-weight coarse
  output, because that supervision is part of how it learns object regions.

**New here?** Start with `fcn` — it is the smallest head and the easiest to
inspect when something looks wrong.

## Choose a head

| `kind` | simple explanation | good first use | pros | cons |
|---|---|---|---|---|
| `fcn` | resize selected maps, concatenate them, then use ordinary convolutions | smallest transparent baseline; auxiliary supervision | easy to inspect; flexible number of feature inputs | limited explicit global context |
| `segformer` | project every selected scale to one width and fuse them | efficient all-scale fusion after identity or FPN | simple multi-scale decoder; no attention decoder | fusion width can become memory-heavy at large crops |
| `psp` | pool the deepest feature at several grid sizes | scenes where broad image context may disambiguate classes | explicit global-to-local context | one deep feature carries limited boundary detail; pooled branch normalization needs care |
| `aspp` | process one deep feature with several dilation rates plus global context | compare receptive fields without a low-level skip | parallel context scales; conceptually clean | dilation rates depend on output stride/crop; weak fine-detail path |
| `deeplabv3plus` | ASPP context plus one early high-resolution skip | boundaries and small structures | combines context and low-level detail | more knobs and compute than ASPP; wrong feature indices hurt silently unless audited |
| `lraspp` | add a direct fine prediction to image-gated deep context | mobile or memory-conscious baselines | very small decoder; batch-one-safe global gate | less context capacity than ASPP/UPer; only two feature levels |
| `uper` | pyramid pooling on the deepest map plus top-down multi-scale fusion | a strong general multi-scale architecture study | rich context and fine-to-coarse fusion | heaviest native head here; more memory and components |
| `dpt` | refine four equal-width maps and progressively add coarse context into finer skips | study DPT-style convolutional fusion after ChannelMapper | every selected scale has a direct residual path; ends with a refined half-scale representation | requires exactly four mapped levels; repeated full-width 3x3 blocks use memory/compute |
| `ocr` | predict coarse class regions, pool one representation per class, and use pixel-to-region attention to refine every pixel | explicitly study object-class context rather than only spatial-scale context | attention grows with pixels times classes instead of pixels squared; coarse region generator is directly supervised | two classifiers and a wide fusion path add compute; bad coarse regions can mislead refinement |

These are architectural expectations, not measured rankings.

## Exact switches

All heads support `channels`, `dropout`, `norm`, and `activation`. Feature
selectors are typed:

- FCN, SegFormer, UPer, OCR, and DPT use increasing `in_indices` (DPT requires
  exactly four).
- PSP and ASPP use one `in_index`.
- DeepLabV3+ and LR-ASPP use `low_index < high_index`.

PSP/UPer also expose unique positive `pool_bins`. ASPP/DeepLabV3+ expose unique
positive `dilation_rates`. FCN exposes `num_convs`, odd `kernel_size`, and
positive `dilation`. Invalid values fail while parsing or constructing the
model.

## Beginner settings

- FCN: `channels: 128`, two 3x3 convolutions.
- SegFormer: four feature levels and `channels: 128` for a first smoke.
- PSP/ASPP/DeepLabV3+/UPer: keep the shipped 256-channel context defaults until
  memory and overfit behavior are understood.
- LR-ASPP: start with the shipped 128-channel deep projection; its low branch
  classifies the selected fine feature directly.
- DPT: start with ChannelMapper and DPT `channels: 256`, indices
  `[0, 1, 2, 3]`, GroupNorm, ReLU, and dropout 0.1. Reduce both channel settings
  together when memory is the constraint.
- OCR: start with FPN, `channels: 512`, `key_channels: 256`,
  `attention_scale: 1`, dropout 0.05, and `coarse_loss_weight: 0.4`. The latter
  is the paper's semantic-segmentation weighting, not an arbitrary extra head.
- Keep `dropout: 0.1`, `norm: group`, and `activation: relu` initially.

## Binary output

Every native family in the table, including named auxiliary heads, supports the
one-logit binary output contract. Set both switches together:

```yaml
model:
  arch: native
  native:
    task: binary

loss:
  task: binary
  activation: auto
  terms:
    - {kind: binary_cross_entropy, weight: 1.0}
```

The head output is raw `(N,1,H,W)` logits. Sigmoid and `eval.threshold` belong
to inference, not the head. A two-channel native head configured as multiclass
is a different model/checkpoint and is not automatically converted. Binary
mode also requires the exact two-class taxonomy and full per-sample activity
described in [Semantic task modes](../tasks/README.md).

Binary OCR keeps both its refined and supervised coarse public outputs at one
raw class-1 positive logit. Internally, object-context gathering expands each coarse
logit difference `z` into the centered equivalent two-class logits
`[-z/2, +z/2]`. A per-pixel softmax across those internal class channels gives
`[1-sigmoid(z), sigmoid(z)]`, and cross-entropy on that pair equals binary
cross-entropy on `z`. OCR then spatially pools the two channels separately, so
their negative and positive proxies can differ instead of attention being
forced over one region. The centered, zero-mean pair is a deterministic
symmetric gauge: the one public logit does not uniquely determine two
independently learned spatial score maps. This is a Segmentary-specific binary
modeling choice, not equivalence to a learned two-logit OCR classifier. The
primary OCR paper and retained exact ResNet-50/FPN/OCR GPU record are multiclass
evidence.

## Advanced usage and compatibility

An auxiliary head is a normal dense head used only during training:

```yaml
auxiliary_heads:
  - name: aux_s16
    loss_weight: 0.4
    head:
      kind: fcn
      in_indices: [2]
      channels: 64
      num_convs: 1
```

Names must be unique and weights finite and positive. Auxiliary logits are not
returned by the deployment-friendly tensor `forward`; the richer training
output carries them. The configured loss is evaluated for the main output and
each auxiliary output, then weighted. Auxiliary supervision can improve
gradient flow, but also increases memory and may overemphasize coarse labels.
At a stage boundary, `reset_head: true` resets the main and auxiliary
classifiers while retaining backbone, neck, and class-agnostic decoder layers.
It is an ablation, not a fix for a mismatched taxonomy.

OCR is primary-only: it cannot be placed inside `auxiliary_heads`, because that
path exposes one tensor and would discard OCR's own required coarse
supervision. As a primary head, its rich `SegmentationOutput` contains refined
logits plus `ocr_coarse` logits. The ordinary dense objective is evaluated on
both with the configured positive weight. Ordinary external auxiliary heads may
still accompany OCR if their names are unique. `reset_head: true` resets both
OCR classifiers and no class-agnostic projection, relation, or fusion layer.

Pool bins and dilation rates should be treated as resolution-dependent
hyperparameters. A crop that leaves fewer pixels than a pooling grid or an
extreme dilation is a poor test even if it constructs. GroupNorm remains the
safer shipped default for small batches. When `norm: batch` is selected,
Segmentary deliberately omits normalization only on a branch pooled to `1×1`;
otherwise a valid per-device batch of one has no variance estimate and crashes.
The remaining branches still use the requested BatchNorm.

### DPT-style fusion contract

The native DPT head consumes exactly four spatial feature maps whose reductions
are strictly increasing and whose widths all equal `head.channels`. It refines
the coarsest map, aligns it to the next finer skip, adds a separately refined
skip, and repeats until all four maps have contributed. A final residual unit
builds a half-input-scale representation; a task block and classifier emit raw
logits that are bilinearly resized to the input size.

The original DPT architecture first reassembles transformer tokens at several
resolutions. Segmentary's native recipe starts from an already-spatial ConvNeXt
pyramid and uses ChannelMapper as the width-normalization boundary. It therefore
implements the progressive convolutional fusion idea, not an exact DPT model or
checkpoint-compatible reproduction. There is no imported or executed
MMSegmentation code.

ChannelMapper is recommended because it makes projection and fusion separately
auditable. An equal-width FPN also constructs, but its own top-down merge occurs
before DPT and changes the architecture. Identity works only if all four chosen
backbone widths already equal `head.channels`.

### OCR object-context contract

OCR runs in six steps:

1. **Fuse** — resize the selected pyramid maps to the finest resolution,
   concatenate, and project into `channels`.
2. **Classify coarsely** — a linear classifier emits one raw map per output
   channel. Multiclass uses these directly; binary keeps its one-logit contract
   and applies the centered two-region conversion *only* inside the context
   path, where negating `z` swaps the two internal channels exactly.
3. **Normalize** — spatial softmax normalizes each region map across all pixels,
   independently.
4. **Pool** — those weights collapse the pixel features into one image-specific
   representation per region.
5. **Attend** — scaled dot-product between pixel queries and region keys mixes
   the region values back into every pixel.
6. **Refine** — a 1x1 block fuses that context with the original pixel feature,
   and the final classifier emits refined logits.

Two consequences worth knowing. The spatial softmax in step 3 is why the
centered pair is an explicit *gauge choice*, not a reconstruction of some
unobserved two-logit classifier. And fewer than two context regions is rejected
outright, so a later change cannot silently reintroduce singleton-attention
degeneracy.

`key_channels` controls relation width; lowering it reduces attention work.
`attention_scale > 1` max-pools only the pixel-query grid during relation
calculation, then restores the context to the fusion size. It can reduce memory
but loses fine relation detail and must not exceed that feature size.
`coarse_loss_weight` must remain finite and positive: setting it to zero would
violate the paper's supervised object-region premise and is rejected. Its
default 0.4 matches the primary paper, while any change defines an optimization
ablation. More selected high-resolution features increase the concatenation and
fusion cost. FPN is compatible and supplies a regular equal-width pyramid;
Identity is also valid when the selected raw widths fit memory. This head is
semantic segmentation, not optical character recognition and not an
instance-segmentation head.

## Evidence and benchmarks

CPU unit tests exercise FCN, SegFormer, PSP, ASPP, DeepLabV3+, LR-ASPP, UPer,
and DPT with heterogeneous feature sizes and backward gradients, including the
one-channel binary classifier shape. DPT has separate tests for odd-size
full-resolution output, contribution and gradients from all four levels, every
native normalization, classifier-only reset, invalid pyramid contracts, and
ChannelMapper/DPT integration. The end-to-end multiclass native smoke covers
SegFormer plus an FCN auxiliary head; the binary pipeline has a separate real
on-disk synthetic folder train/evaluate smoke. The exact pretrained
ConvNeXt-Tiny / ChannelMapper / DPT recipe also passed a retained four-step GPU8
BF16 production-objective smoke at two shapes. The other recipe combinations
have parser and backbone-feature evidence; a full optimizer smoke for every
head/backbone/task combination is still pending.

OCR has CPU coverage for odd full-resolution refined/coarse outputs, the
spatial-softmax region gather, every native normalization, attention scaling,
invalid contracts, exact two-classifier reset, explicit production-objective
weighting, all-parameter gradients, real scratch ResNet-50/FPN integration,
four optimizer steps, and Gloo DDP with no unused parameters. The exact
pretrained multiclass ResNet-50/FPN/OCR recipe also passed a retained four-step
GPU8 BF16 production-objective smoke with named coarse-loss components, all
gradients, and updates to both classifiers. Separate CPU integration tests
cover binary OCR's probability-equivalent two-region conversion, one-logit
refined/coarse shapes, the centered-pair algebra and BCE/CE identity, finite
extreme logits, weighted BCE and all-ignore objectives, updates to both
classifiers, and nonzero gradients through the query and key context paths.
The exact pretrained binary ResNet-50/FPN/OCR composition also has a retained
four-step GPU8 BF16 production-BCE record with one-logit shape checks, named
positive coarse loss, all-parameter gradient audits, and updates to query, key,
coarse-classifier, and refined-classifier tensors.

No native head has a common Segmentary model-quality benchmark yet. Do not infer
an mIoU ranking from parameter counts, upstream papers, or these synthetic
smokes. See the [evidence ledger](../../../benchmarks/native-component-smokes/README.md).

## Primary OCR references and upstream benchmarks

Segmentary follows Yuan, Chen, and Wang, [*Object-Contextual Representations for
Semantic Segmentation* (ECCV
2020)](https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123510171.pdf),
and the authors' [official HRNet/OCR implementation at the reviewed
revision](https://github.com/HRNet/HRNet-Semantic-Segmentation/tree/0bbb2880446ddff2d78f8dd7e8c4c610151d5a51). The paper
defines supervised coarse object regions, spatially weighted class-region
representations, pixel-region relations, augmented pixel features, and losses
on both coarse and final predictions. Its controlled ablations support the need
for a positive coarse loss but are not performance claims for Segmentary. The
paper's results and training protocol do not transfer to the shipped
ResNet-50/FPN recipe.

The native module is written against Segmentary's own feature/output contracts.
It does not copy or execute MMSegmentation code or configs.

## Primary DPT references

The design is based only on the architecture described by Ranftl, Bochkovskiy,
and Koltun in [*Vision Transformers for Dense Prediction*
(ICCV 2021)](https://openaccess.thecvf.com/content/ICCV2021/html/Ranftl_Vision_Transformers_for_Dense_Prediction_ICCV_2021_paper.html),
especially progressive RefineNet-style fusion, half-resolution semantic
features, dropout, and final bilinear logit upsampling. The authors' archived
[official DPT repository](https://github.com/isl-org/DPT) is the primary
implementation reference and is MIT-licensed. Segmentary's modules were written
against its own typed feature/head contracts and do not copy that code.

## Related documentation

- [Semantic task modes](../tasks/README.md)
- [Heads and output strategy](../heads/README.md)
- [Dense losses](../losses/README.md)
