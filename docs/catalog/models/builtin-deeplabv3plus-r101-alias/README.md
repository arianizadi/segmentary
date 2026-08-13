# DeepLabV3+/ResNet-101 compatibility alias

Use [`deeplabv3plus_r101.yaml`](../../../../configs/models/deeplabv3plus_r101.yaml)
to preserve older experiment commands. New configurations should prefer the
explicit [`smp_deeplabv3plus_resnet101.yaml`](../../../../configs/models/smp_deeplabv3plus_resnet101.yaml)
recipe, which records decoder, encoder, and encoder weights separately.

## What it is

`arch: deeplabv3plus_r101` constructs SMP's DeepLabV3+ with a ResNet-101 encoder
and ImageNet encoder weights. Atrous spatial pyramid pooling gathers context at
several dilation rates; the V3+ decoder fuses low-level features to recover
spatial detail. Decoder and final classifier start fresh.

The alias and the explicit SMP recipe reach the same constructor with their
default values. The alias exists for compatibility, not as a second model.

## The checkpoint field is unusual

For this alias only, `model.checkpoint` means the SMP **encoder name**. For
example, tests use `checkpoint: resnet18` to exercise the path cheaply. It does
not mean a `.ckpt` file and it does not resume training. Use stage `init_from`
for a Segmentary checkpoint.

Pros:

- established CNN baseline with broad context and boundary refinement;
- straightforward dense-CE training;
- fixed-shape ONNX export and ONNX Runtime parity are regression-tested;
- useful sanity floor for more experimental architectures.

Cons:

- older, large encoder;
- decoder has no task pretraining;
- compatibility field semantics are less clear than `arch: smp`;
- automatic LoRA is not available for the convolutional ResNet backbone.

## Tuning, resources, and evidence

Full and frozen tuning are supported. Head reset changes only the final
segmentation classifier. Use RGB ImageNet normalization and crop sizes divisible
by 32. Memory rises strongly with crop area; run a baby training test before a
full-resolution experiment.

The model suite exercises real forward/backward behavior through this alias,
and the export suite checks the real architecture against ONNX Runtime on a
real Cityscapes image. Separate deployment acceptance may use untrained weights;
that proves graph compatibility, not model accuracy. No same-protocol mIoU is
claimed for this recipe yet.

See the [explicit recipe page](../smp-deeplabv3plus-resnet101/README.md) and
[SMP component](../../components/smp/README.md).
