# Model config catalog

Model files are one layer of an experiment. Compose one with the shared base and
your dataset/curriculum file:

```bash
segmentary-train configs/base.yaml configs/models/smp_unet_resnet34.yaml path/to/experiment.yaml
```

Changing this layer switches the model without forcing a dataset or taxonomy.
Start with a small overfit check before scheduling a full run.

Discover every installed recipe without loading weights, then admission-test an
exact choice without opening dataset roots:

```bash
segmentary-models list
segmentary-models probe \
  configs/base.yaml \
  configs/models/native_resnet18_fpn_fcn.yaml \
  path/to/experiment.yaml \
  --output reports/model-probe.json
```

The probe uses the experiment's real taxonomy/class count and production
loss/optimizer, checks two non-square shapes, audits every trainable gradient,
and requires the classifier/head to update. It uses synthetic inputs and labels,
so it proves compatibility—not accuracy, convergence, speed, or production
memory. Read the full [catalog/probe guide](https://github.com/arianizadi/segmentary/blob/main/docs/guides/model-catalog-and-probe.md).

## Segmentary-native component recipes

These YAMLs use Segmentary's own typed backbone → neck → head contracts and native
training/output interfaces. They do not import, execute, or copy another
segmentation framework. Each pretrained backbone is an exact timm 1.0.28 tag
that loaded its requested weights without fallback and passed two CPU feature
shapes, including odd dimensions. Decoders and classifiers start fresh.

| config | native composition | point-of-choice documentation |
|---|---|---|
| `native_convnext_tiny_channelmapper_dpt.yaml` | ConvNeXt-Tiny / ChannelMapper / DPT-style fusion | [progressive-fusion contract, tradeoffs, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) |
| `native_resnet18_fpn_fcn.yaml` | ResNet-18 / FPN / FCN | [purpose, tradeoffs, settings, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-resnet18-fpn-fcn/README.md) |
| `native_resnet18_fpn_segformer_aux.yaml` | ResNet-18 / FPN / SegFormer + FCN auxiliary | [auxiliary-loss tutorial and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-resnet18-fpn-segformer-aux/README.md) |
| `native_resnet50_psp.yaml` | ResNet-50 / identity / PSP | [context pooling, limits, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-resnet50-psp/README.md) |
| `native_resnet50_aspp.yaml` | ResNet-50 / identity / ASPP | [dilation choices, limits, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-resnet50-aspp/README.md) |
| `native_resnet50_deeplabv3plus.yaml` | ResNet-50 / identity / DeepLabV3+ | [low/high feature choices and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-resnet50-deeplabv3plus/README.md) |
| `native_resnet50_fpn_ocr.yaml` | ResNet-50 / FPN / supervised OCR | [object-context pipeline, coarse supervision, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-resnet50-fpn-ocr/README.md) |
| `native_resnet101_uper.yaml` | ResNet-101 / identity / UPer | [capacity tradeoffs and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-resnet101-uper/README.md) |
| `native_convnext_tiny_uper.yaml` | ConvNeXt-Tiny / identity / UPer | [feature-index compatibility and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-convnext-tiny-uper/README.md) |
| `native_efficientnet_b0_deeplabv3plus.yaml` | EfficientNet-B0 / identity / DeepLabV3+ | [compact-recipe tradeoffs and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) |
| `native_mobilenetv3_large_deeplabv3plus.yaml` | MobileNetV3-Large / identity / DeepLabV3+ | [deployment caveats and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) |
| `native_mobilenetv3_large_lraspp.yaml` | MobileNetV3-Large / identity / LR-ASPP | [lightweight decoder tradeoffs and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/native-mobilenetv3-large-lraspp/README.md) |

Read the separate guides for [native backbones](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/components/native-backbones/README.md),
[necks](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/components/native-necks/README.md),
[heads and auxiliary outputs](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/components/native-heads/README.md),
and shared [normalization/activation/dropout blocks](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/components/native-blocks/README.md).
The [smoke ledger](https://github.com/arianizadi/segmentary/blob/main/docs/benchmarks/native-component-smokes/README.md)
separates backbone admission, component training smokes, and evidence that is
still missing. No common-dataset native model-quality benchmark exists yet.

## Audited Hugging Face recipes

These use complete, revision-pinned semantic checkpoints. Segmentary audits every
loaded tensor and reproduces the checkpoint image processor, including BGR
channel order for MobileViT.

| config | backbone / head | point-of-choice documentation |
|---|---|---|
| `hf_auto_segformer_b0.yaml` | MiT-B0 / SegFormer MLP | [purpose, tradeoffs, preprocessing, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/hf-auto-segformer-b0/README.md) |
| `hf_auto_beit_base_ade.yaml` | BEiT-Base / pyramid decode head | [purpose, tradeoffs, auxiliary-head policy, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/hf-auto-beit-base-ade/README.md) |
| `hf_auto_mobilenetv2_deeplabv3.yaml` | MobileNetV2 / DeepLabV3 | [purpose, BatchNorm caveat, resources, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) |
| `hf_auto_mobilevit_xxs_deeplabv3.yaml` | MobileViT XXS / DeepLabV3 | [purpose, BGR preprocessing, upstream benchmark, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) |
| `hf_auto_mobilevitv2_deeplabv3.yaml` | MobileViTv2 1.0 / DeepLabV3 | [purpose, BGR preprocessing, resources, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) |
| `hf_auto_upernet_swin_tiny.yaml` | Swin-Tiny / UPerNet | [purpose, pyramid/auxiliary heads, resources, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/hf-auto-upernet-swin-tiny/README.md) |

Read the [generic `hf_auto` component contract](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/components/hf-auto/README.md)
before adding another Hub checkpoint. Hub download counts are not model-quality
benchmarks; a new recipe needs strict loading, exact processor parity, and a
real optimizer smoke before it belongs in this table.

## Hand-integrated built-ins

These paths have architecture-specific factory wiring. Eight have ready model
files; the blocked research arm and one legacy alias intentionally do not.

| config or `model.arch` | status | point-of-choice documentation |
|---|---|---|
| `segformer_b0.yaml` | supported encoder-pretrained baseline | [SegFormer-B0](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-segformer-b0/README.md) |
| `segformer_b2.yaml` | supported, trained Cityscapes evidence | [SegFormer-B2](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-segformer-b2/README.md) |
| `segformer_b5.yaml` | supported high-capacity encoder-pretrained arm | [SegFormer-B5](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-segformer-b5/README.md) |
| `upernet_convnext.yaml` | supported complete ADE20K checkpoint | [UPerNet/ConvNeXt](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-upernet-convnext/README.md) |
| `eomt_large.yaml` | query objective available; model YAML alone retains experimental dense loss | [EoMT-L](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-eomt-large/README.md) |
| `eomt_dinov3_large.yaml` | query objective available; model YAML alone retains experimental dense loss | [EoMT-DINOv3-L](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-eomt-dinov3-large/README.md) |
| `hrnet_w48_ocr.yaml` | supported with OCR-objective deviation | [HRNet-W48/OCR](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-hrnet-w48-ocr/README.md) |
| `deeplabv3plus_r101.yaml` | compatibility alias | [DeepLabV3+/R101](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-deeplabv3plus-r101-alias/README.md) |
| `mask2former_dinov3` | deliberately blocked | [architectural reason and required adapter](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-mask2former-dinov3/README.md) |
| `upernet_r101` | factory-only compatibility alias | [UPerNet/R101](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/builtin-upernet-r101-alias/README.md) |

Read the [built-in model component guide](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/components/builtin-models/README.md)
for shared preprocessing, checkpoint, tuning, and evidence rules. The
[strict local DINOv3 loader](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/local-dinov3-loader/README.md)
is an advanced backbone utility, not a complete `model.arch`.

## Composable SMP recipes

| config | decoder / encoder | point-of-choice documentation |
|---|---|---|
| `smp_unet_resnet34.yaml` | U-Net / ResNet-34 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-unet-resnet34/README.md) |
| `smp_unetplusplus_efficientnet_b0.yaml` | U-Net++ / EfficientNet-B0 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-unetplusplus-efficientnet-b0/README.md) |
| `smp_fpn_resnet50.yaml` | FPN / ResNet-50 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-fpn-resnet50/README.md) |
| `smp_pspnet_mobilenet_v2.yaml` | PSPNet / MobileNetV2 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-pspnet-mobilenet-v2/README.md) |
| `smp_deeplabv3_resnet50.yaml` | DeepLabV3 / ResNet-50 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-deeplabv3-resnet50/README.md) |
| `smp_deeplabv3plus_resnet101.yaml` | DeepLabV3+ / ResNet-101 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-deeplabv3plus-resnet101/README.md) |
| `smp_manet_efficientnet_b0.yaml` | MA-Net / EfficientNet-B0 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-manet-efficientnet-b0/README.md) |
| `smp_linknet_mobilenet_v2.yaml` | LinkNet / MobileNetV2 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-linknet-mobilenet-v2/README.md) |
| `smp_pan_resnext50.yaml` | PAN / ResNeXt-50 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-pan-resnext50/README.md) |
| `smp_upernet_mit_b0.yaml` | UPerNet / MiT-B0 | [purpose, tradeoffs, weights, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-upernet-mit-b0/README.md) |
| `smp_upernet_resnet101.yaml` | UPerNet / ResNet-101 | [purpose, tradeoffs, migration, and evidence](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/models/smp-upernet-resnet101/README.md) |

Read the [SMP component guide](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/components/smp/README.md) for
the shared decoder/encoder contract, tuning support, resource caveats, and
cross-catalog verification.

The older `deeplabv3plus_r101.yaml` remains a compatibility alias. New
experiments should use the explicit `smp_deeplabv3plus_resnet101.yaml` recipe so
the decoder, encoder, and pretrained-weight choice are separately recorded.

The hand-written factory paths are indexed in the
[models and tuning guide](https://github.com/arianizadi/segmentary/blob/main/docs/guides/models-and-tuning.md); their
point-of-choice pages are also collected under `docs/catalog/models/`.
