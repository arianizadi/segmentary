# Built-in EoMT-DINOv3-Large

Use [`eomt_dinov3_large.yaml`](../../../../configs/models/eomt_dinov3_large.yaml)
for the advanced EoMT arm with a DINOv3 large backbone.

## What it is

The default `tue-mps/eomt-dinov3-coco-panoptic-large-640` repository is a
complete EoMT-DINOv3 checkpoint. Its DINOv3 transformer supplies image features;
query, mask, and class modules produce a set of region predictions. Segmentary
contracts those queries into an input-resolution dense semantic score map.

The checkpoint has a fixed 640×640 native grid. Segmentary resizes each sliding
window to that grid and resizes the prediction back. Use square windows to avoid
aspect-ratio distortion.

## When it helps—and when it does not

Pros:

- combines a large DINOv3 representation with an already trained mask head;
- default repository is loadable without passing a separate local Meta `.pth`;
- suitable as a clearly named advanced research ablation.

Cons:

- the model YAML alone retains Segmentary's experimental dense-CE objective;
  native query training requires an explicit `loss.query` override;
- large memory and compute demand; the shipped file starts at batch 1 with
  accumulation 2;
- fixed grid and square-window restriction;
- ONNX/TensorRT export is unsupported;
- DINOv3-derived weight licensing must be reviewed before redistribution.

The shipped optimizer lowers backbone LR to `1e-5`, uses layer-wise decay
`0.75`, and keeps a 10x head multiplier. These are starting settings, not a
benchmark guarantee. Full and frozen tuning are supported. Treat LoRA as
unverified until the exact installed model's targets and gradients pass a
retained baby run.

`checkpoint` overrides the complete EoMT repository; it is not the path to one
of Meta's raw pretraining `.pth` files. Raw licensed files use the separate
[local DINOv3 loader](../local-dinov3-loader/README.md), which supplies only a
backbone and cannot replace a complete EoMT repository here.

## Verified evidence and benchmarks

The real CUDA integration test loaded the non-gated default checkpoint and
produced finite BF16 input-resolution output. That proves construction and
forward compatibility only. Segmentary's
[Hungarian query objective](../../components/query-objectives/README.md) can
train the raw final query tensors, while the unchanged model YAML plus base
config still selects dense CE. No comparable Segmentary dataset mIoU is recorded;
the two objective choices must be named separately. The current EoMT output
does not expose intermediate decoder predictions for auxiliary loss.

See the [built-in model component](../../components/builtin-models/README.md)
and [model tuning guide](../../../guides/models-and-tuning.md).
