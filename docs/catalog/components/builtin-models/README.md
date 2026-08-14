# Built-in model factory

The built-in factory is Segmentary's short list of hand-integrated model paths.
Choose one with `model.arch`. Every successful choice accepts an RGB tensor
`(batch, 3, height, width)` and returns one input-resolution tensor
`(batch, classes, height, width)`, so datasets, losses, and evaluation do not
need model-specific code.

These paths differ from the generic [Hugging Face adapter](../hf-auto/README.md)
and [SMP component](../smp/README.md): each built-in has explicit Python wiring
for its exact upstream module layout and behavior.

## Choices

| `model.arch` | page | status | pretrained source |
|---|---|---|---|
| `segformer_b0` | [SegFormer-B0](../../models/builtin-segformer-b0/README.md) | supported | MiT-B0 encoder |
| `segformer_b2` | [SegFormer-B2](../../models/builtin-segformer-b2/README.md) | supported and benchmarked | MiT-B2 encoder |
| `segformer_b5` | [SegFormer-B5](../../models/builtin-segformer-b5/README.md) | supported; shipped YAML | MiT-B5 encoder |
| `upernet_convnext` | [UPerNet/ConvNeXt](../../models/builtin-upernet-convnext/README.md) | supported | complete ADE20K checkpoint |
| `eomt_large` | [EoMT-L](../../models/builtin-eomt-large/README.md) | native query objective available; dense default remains experimental | complete COCO panoptic checkpoint |
| `eomt_dinov3_large` | [EoMT-DINOv3-L](../../models/builtin-eomt-dinov3-large/README.md) | native query objective available; dense default remains experimental | complete COCO panoptic checkpoint |
| `mask2former_dinov3` | [Mask2Former/DINOv3](../../models/builtin-mask2former-dinov3/README.md) | deliberately blocked | none |
| `hrnet_w48_ocr` | [HRNet-W48/OCR](../../models/builtin-hrnet-w48-ocr/README.md) | supported with supervised coarse OCR logits | ImageNet HRNet backbone |
| `deeplabv3plus_r101` | [DeepLabV3+/R101 alias](../../models/builtin-deeplabv3plus-r101-alias/README.md) | compatibility alias | ImageNet ResNet-101 encoder |
| `upernet_r101` | [UPerNet/R101 alias](../../models/builtin-upernet-r101-alias/README.md) | compatibility alias | ImageNet ResNet-101 encoder |

The [local DINOv3 loader](../../models/local-dinov3-loader/README.md) is also a
switchable building block, but it is not a complete segmentation architecture.

## Beginner choice and tradeoffs

Start with `segformer_b0` when you want the smallest hand-integrated baseline,
or `segformer_b2` when you want the built-in with retained Segmentary training
evidence. Move to a larger or experimental path only after the complete input,
label-space, and evaluation pipeline passes with that baseline.

The main advantage of a built-in is precision: Segmentary knows the exact
backbone, head, checkpoint, and reset behavior instead of guessing an upstream
layout. The tradeoff is less free composition than [`smp`](../smp/README.md)
and a smaller checkpoint catalog than [`hf_auto`](../hf-auto/README.md).
Architecture-specific choices—such as EoMT trained through the default dense
path—also require reading the selected model page before interpreting results.
EoMT native query training is
an explicit [loss choice](../query-objectives/README.md), not a model-side switch.

## What is shared

### Preprocessing

These hand-written paths use RGB in `[0, 1]`, followed by ImageNet mean
`(0.485, 0.456, 0.406)` and standard deviation
`(0.229, 0.224, 0.225)`. Segmentary records the effective normalization in every
`results.json`. The separate `hf_auto` path can reproduce a checkpoint's own
audited image processor instead.

Masks are never normalized. Resize and augmentation use nearest-neighbor for
masks, and padded mask pixels receive the label space's ignore ID.

### Pretrained weights

If a built-in requests pretrained weights and loading fails, training stops.
There is no silent retry from random initialization. For SegFormer, the default
`nvidia/mit-*` repositories are encoder-only: the decode head is intentionally
new. UPerNet/ConvNeXt and the EoMT paths load complete task checkpoints and
replace only the class-dependent output for the requested taxonomy.

Most built-ins accept `model.checkpoint` as an override, but its meaning is
architecture-specific. On the two SMP compatibility aliases it is an **encoder
name**, not a training checkpoint file. The generic `revision` field is rejected
outside `hf_auto`; use an immutable local snapshot when a built-in must pin an
upstream revision. Read the selected page before changing it. Use a stage's
`init_from` to resume a Segmentary training checkpoint.

### Tuning

- `full` trains backbone and head.
- `frozen` freezes the declared backbone, including running-stat normalization,
  while training the decoder/classifier.
- `lora` is appropriate only when the actual backbone exposes a verified
  attention-projection layout. Pure ConvNeXt and ResNet backbones do not.
- A stage-level `reset_head: true` resets the final class predictor, not the
  class-agnostic feature extractor or complete decoder.

Settings that an architecture cannot honor fail. For example, HRNet rejects
`drop_path`, and UPerNet/ConvNeXt rejects the top-level setting because accepting
it would record a value that never reached the nested backbone.

## How to read the evidence

The pages distinguish four very different evidence levels:

1. **Contract test:** shape, finite output, parameter partition, or gradient
   behavior was checked.
2. **Training smoke:** a few optimizer steps completed. This finds wiring bugs,
   not model quality.
3. **Deployment check:** export or backend parity was checked. An untrained
   export says nothing about mIoU.
4. **Dataset benchmark:** a complete result record exists under a stated data,
   training, and evaluation protocol.

Only SegFormer-B2 currently has a built-in, same-library dataset result suitable
for this catalog. Do not compare an upstream paper number, a synthetic smoke,
and a Segmentary result as if they were the same benchmark. For a new comparison,
hold taxonomy, splits, steps, crop, augmentation, checkpoint policy, EMA, TTA,
and seeds fixed; then report at least three seeds.

See the [models and tuning guide](../../../guides/models-and-tuning.md) for the
experiment workflow and [interpreting results](../../../tutorials/interpreting-results.md)
for metric scales and warning signs.
