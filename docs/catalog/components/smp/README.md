# SMP decoder and encoder component

This component is the typed, composable CNN path in Segmentary. It combines one
reviewed `segmentation-models-pytorch` (SMP) decoder with one encoder exposed by
the pinned SMP release. It is useful when you want modular model composition
without importing another framework's registry or allowing arbitrary
constructor arguments.

## Configuration contract

```yaml
model:
  arch: smp
  smp_arch: DeepLabV3Plus
  encoder_name: resnet101
  encoder_weights: imagenet
  tuning: full
  head: unified_head
```

- `smp_arch` is limited to `Unet`, `UnetPlusPlus`, `FPN`, `PSPNet`,
  `DeepLabV3`, `DeepLabV3Plus`, `MAnet`, `Linknet`, `PAN`, and `UPerNet`.
- `encoder_name` is an encoder recognized by SMP 0.5.0. Decoder/encoder
  compatibility is checked by actual construction; there is no fallback.
- Segmentary reads the chosen encoder/weight pair's SMP preprocessing metadata,
  validates `[0, 1]` input range plus RGB/BGR order, and records its mean, standard
  deviation, channel order, and source. Unsupported pixel contracts fail before
  model construction.
- `encoder_weights: imagenet` requests the named pretrained weights.
  `encoder_weights: scratch` is the explicit from-scratch choice. The field is
  required so an omitted value cannot be mistaken for a deliberate scratch run.
- Only the shared constructor surface is exposed: encoder, encoder weights,
  three input channels, and the taxonomy-derived class count. A new
  decoder-specific option must become a typed, tested field before it can affect
  a run.
- A curated recipe may declare exact `inactive_parameter_paths` below
  `encoder.` when the pinned SMP implementation retains modules its feature
  forward never calls. Those paths are frozen before optimizer/DDP construction.
  Decoder/head paths are rejected, and new dynamic combinations receive no
  blanket exception: a disconnected trainable branch fails strict DDP until it
  is inspected and documented.

The wrapper treats `.encoder` as the backbone and both `.decoder` and
`.segmentation_head` as the head. Every model must return finite
`(N, C, H, W)` logits at the input resolution.

## Decoder choices

| decoder | purpose | advantages | costs or constraints |
|---|---|---|---|
| U-Net | general first baseline | direct skip connections; easy to understand | high-resolution skip tensors consume memory |
| U-Net++ | boundary-sensitive baseline | denser nested skip fusion | more decoder work than U-Net |
| FPN | multi-scale objects | simple feature pyramid | may lose fine boundary detail |
| PSPNet | global scene context | pyramid pooling gives broad context | pooled features can soften boundaries |
| DeepLabV3 | atrous-context baseline | strong receptive field without a large decoder | no V3+ low-level refinement |
| DeepLabV3+ | context plus refinement | established, broadly useful baseline | heavier than V3 |
| MA-Net | attention-based fusion | explicit multi-scale attention | more decoder complexity |
| LinkNet | efficiency | small residual decoder | less decoder capacity |
| PAN | pyramid attention | compact attention pyramid | at least 128 pixels per side in the verified implementation |
| UPerNet | general pyramid head | pyramid pooling plus FPN | comparatively heavy head |

Encoder choice controls most parameter count and feature capacity. ResNet is the
conservative baseline; MobileNetV2 and EfficientNet-B0 reduce resource use;
ResNeXt adds capacity; MiT is a hierarchical transformer-style encoder. List
the encoders available in the installed version with:

```bash
python -c 'from segmentation_models_pytorch.encoders import get_encoder_names; print("\n".join(get_encoder_names()))'
```

## Pretraining and reproducibility

SMP 0.5.0 resolves each `imagenet` tag to a pinned Hugging Face Hub revision.
Every shipped recipe page records that repository and full revision. The
decoder and final segmentation head are newly initialized; only the encoder is
pretrained. A failed pretrained load is fatal and is never retried with random
weights.

For a reported experiment, retain the resolved Segmentary config, package lock,
checkpoint, and result record together. The package version is part of the
meaning of an SMP weight tag.

## Tuning support

- **Full:** supported and used by every shipped recipe.
- **Frozen:** supported; the encoder and its running-stat normalization stay
  frozen while the decoder and segmentation head train.
- **LoRA:** not advertised for these recipes. The common convolutional encoders
  have no compatible attention projections, and SMP module naming is not part
  of Segmentary's current LoRA allowlist. Unsupported layouts fail instead of
  silently training only the head.
- **Head reset:** reinitializes the final `.segmentation_head`; it does not reset
  the whole decoder.

## Verified smoke evidence

On 2026-08-12, all ten decoder implementations and all eleven shipped recipes
passed two independent checks with PyTorch 2.11.0+cu128 and SMP 0.5.0:

1. [`tests/test_smp_catalog.py`](../../../../tests/test_smp_catalog.py) constructed
   every decoder with a scratch ResNet-18, verified the backbone/head split and
   frozen-tuning contract, produced input-resolution finite logits, and ran a
   real backward pass.
2. GPU acceptance on one NVIDIA L40S loaded every shipped pair's requested
   ImageNet encoder and ran four BF16/AdamW optimizer steps per recipe. All 44
   steps had finite losses, every loss-reachable trainable parameter had a
   finite gradient, every segmentation head changed, and peak allocated
   CUDA memory ranged from 0.033 to 0.866 GiB at batch 2 with tiny crops.

The exact pairs also passed a separate scratch-weight BF16 forward that isolates
decoder/encoder shape compatibility. The table below retains the original ten
per-recipe resource probes; the eleventh UPerNet/ResNet-101 recipe is covered by
the later common-shape strict audit in `smp.json`. These measurements are
diagnostic resource notes, not training-memory estimates:

| recipe | parameters at 5 classes | smoke input | peak allocated CUDA memory | result |
|---|---:|---:|---:|---|
| DeepLabV3 / ResNet-50 | 39,634,757 | 1×3×64×64 | 173.8 MiB | passed |
| DeepLabV3+ / ResNet-101 | 45,670,741 | 1×3×64×64 | 187.6 MiB | passed |
| FPN / ResNet-50 | 26,116,549 | 1×3×64×64 | 111.4 MiB | passed |
| LinkNet / MobileNetV2 | 4,319,991 | 1×3×64×64 | 23.1 MiB | passed |
| MA-Net / EfficientNet-B0 | 9,092,937 | 1×3×64×64 | 48.6 MiB | passed |
| PAN / ResNeXt-50 | 23,732,844 | 1×3×128×128 | 106.8 MiB | passed |
| PSPNet / MobileNetV2 | 2,281,789 | 1×3×64×64 | 17.7 MiB | passed |
| U-Net / ResNet-34 | 24,436,949 | 1×3×64×64 | 110.9 MiB | passed |
| U-Net++ / EfficientNet-B0 | 6,570,161 | 1×3×64×64 | 38.7 MiB | passed |
| UPerNet / MiT-B0 | 10,733,413 | 1×3×64×64 | 63.4 MiB | passed |

Parameter counts change slightly with the dataset class count. Real training
memory grows with crop size, batch size, activation precision, optimizer state,
and whether the encoder is frozen. Measure the intended configuration before a
long run.

No accuracy benchmark is claimed here. A construction check, tiny synthetic
optimizer run, or parameter count cannot rank models. Compare accuracy only
from result records produced with the same taxonomy, dataset split, transforms,
checkpoint policy, evaluation protocol, and seed set.
The compact pretrained-optimizer acceptance record is
[`smp.json`](../../../benchmarks/model-catalog-smokes/smp.json).

The eleven catalog recipes use RGB plus standard ImageNet mean/std. That is
not assumed for arbitrary SMP encoders: for example, an encoder with `0.5/0.5`
statistics receives those audited values through the same data pipeline.

See the [SMP recipe index](../../../../configs/models/README.md) for switchable
model files and the [models and tuning guide](../../../guides/models-and-tuning.md)
for experiment-level advice.
