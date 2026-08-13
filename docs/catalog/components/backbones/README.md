# Backbone choices

A backbone turns an image into features. The decoder/head turns those features
into one class prediction per pixel. In Segmentary, you normally choose both with
one reviewed model YAML rather than wiring Python modules by hand.

## Beginner choice

Start with `configs/models/hf_auto_segformer_b0.yaml` for a light complete Hub
checkpoint, or `configs/models/smp_unet_resnet34.yaml` for a conventional
encoder-decoder baseline. Move to a larger backbone only after the data verifier
and eight-image overfit check pass.

## Exact switches

For Segmentary-native composition, use a reviewed exact timm tag:

```yaml
model:
  arch: native
  native:
    backbone:
      kind: timm
      name: resnet18.a1_in1k
      weights: pretrained
      out_indices: [1, 2, 3, 4]
```

See the [native backbone guide](../native-backbones/README.md) for feature-index,
scratch/pretrained, provenance, and admission details.

```yaml
model:
  arch: hf_auto
  checkpoint: nvidia/segformer-b0-finetuned-ade-512-512
  revision: 489d5cd81a0b59fab9b7ea758d3548ebe99677da
```

For the composable SMP path:

```yaml
model:
  arch: smp
  smp_arch: Unet
  encoder_name: resnet34
  encoder_weights: imagenet  # `scratch` means intentionally from scratch
```

`checkpoint` selects or overrides weights for built-in/Hugging Face arms.
`revision`, `subfolder`, and `local_files_only` apply only to `hf_auto`.
`encoder_name` and `encoder_weights` apply only to `smp`; using them on another
architecture is a config error. A failed pretrained load never retries with
random weights.

## Families, pros, and cons

| family | strengths | costs and limits |
|---|---|---|
| MobileNet/MobileViT | small, useful for a first run or edge-oriented study | lower capacity; BatchNorm variants usually need at least two values per pooled training branch |
| ResNet/ResNeXt | familiar CNN baseline, broad SMP decoder support | no attention projections for automatic LoRA; `llrd` must remain `1.0` |
| EfficientNet | compact CNN scaling and useful SMP pairing | compatibility and memory depend on the exact decoder |
| MiT/SegFormer | efficient hierarchical transformer, strong dense baseline | larger variants cost more memory; built-in encoder-only arms start with a fresh classifier |
| Swin + UPerNet | explicit multi-scale feature hierarchy | heavier decoder and more moving parts |
| ConvNeXt + UPerNet | modern convolutional multi-scale baseline | heavier than mobile/SegFormer-B0 choices; automatic LoRA is not available |
| BEiT + decode/FPN heads | strong transformer features and LLRD support | substantially heavier; source auxiliary head is deliberately omitted by the one-head trainer |
| HRNet-W48 | preserves high-resolution branches | large CNN; local OCR integration has an objective caveat described in the [head guide](../heads/README.md) |
| EoMT/DINOv3 | advanced mask-classification research arm | fixed native grid; native query objective is explicit, while model YAMLs alone retain experimental dense training |

## Advanced settings

- `model.drop_path` is supported only by explicit arms that can prove it reaches
  the upstream configuration. SMP, HRNet, `hf_auto`, and the built-in UPerNet
  ConvNeXt arm reject it where it would be ignored.
- `optim.llrd < 1.0` protects early transformer layers with smaller learning
  rates. It fails on a backbone whose block depth cannot be discovered; use
  `1.0` for ordinary CNNs.
- `model.backbone_path`, `head_paths`, and `classifier_path` are an all-or-nothing
  advanced assertion for a standard `hf_auto` layout. They do not bypass
  parameter-partition or checkpoint-load checks.
- Licensed local Meta DINOv3 `.pth` conversion currently verifies only LVD
  ViT-S/B/L FC-MLP schemas. It is a backbone utility, not a shipped trainable
  model YAML. S+, H+, 7B, and SAT layouts are deliberately rejected.

## Evidence and benchmark boundary

The shipped model pages report construction, forward/backward, parameter, and
memory evidence when it exists. Those checks prove compatibility, not accuracy.
No same-protocol backbone-only benchmark exists: a meaningful mIoU comparison
also fixes the head, label space, split, seed set, schedule, EMA policy, and
evaluation protocol. See the [benchmark evidence page](../../../benchmarks/README.md).

## Related documentation

- [Model config catalog](../../../../configs/models/README.md)
- [Heads](../heads/README.md)
- [Tuning modes](../tuning/README.md)
- [Models and tuning guide](../../../guides/models-and-tuning.md)
