# Models and tuning modes

Every model obeys one contract: `(N, 3, H, W)` in, dense logits `(N, C, H, W)`
out. Swap the backend and your data, loss, metrics, and evaluator stay identical.

**In a hurry?** Use `segformer_b2` with `tuning: full`. It is the default for a
reason: verified, and a good speed/accuracy balance.

Two commands worth knowing before you pick anything:

```bash
segmentary-models list                          # what is installed
segmentary-models probe base.yaml model.yaml experiment.yaml   # will it actually run?
```

`probe` composes the exact model and pushes synthetic data through
normalization, two input shapes, the production loss, backward, and AdamW — so
you find out it works before you open a dataset. It proves compatibility, never
quality. Each recipe also has its own page in the
[model catalog](../../configs/models/README.md) covering architecture,
preprocessing, pros/cons, resource evidence, and benchmark scope.

## Choosing a model

| architecture | best use | strengths | limitations |
|---|---|---|---|
| `hf_auto` | standard Hub semantic-segmentation checkpoints | generic, audited path; model ID/revision is config | complete standard checkpoint required; remote code disabled; unfamiliar layouts fail closed |
| `segformer_b0` | smoke tests, overfit checks | tiny and quick | not a reported-quality arm |
| `segformer_b2` | default experiments | strong speed/accuracy balance; fully verified | less capacity than the largest transformer arms |
| `segformer_b5` | higher-capacity SegFormer study | familiar dense architecture; shipped recipe | heavier and not yet quality-benchmarked |
| `smp` | compose a conventional decoder and encoder | ten reviewed decoder families; explicit encoder and pretraining choice | each new decoder/encoder pair needs a smoke test; no arbitrary constructor options |
| `deeplabv3plus_r101` | sanity floor | established CNN baseline; export verified | typically lower ceiling than modern transformers |
| `hrnet_w48_ocr` | legacy comparison | maintains high-resolution features | large; OCR head is local; export not validated |
| `upernet_convnext` | modern convolutional alternative | hierarchical multi-scale feature pyramid | heavier than the default |
| `upernet_r101` | ResNet pyramid comparison | conventional and interpretable | older backbone |
| `eomt_large` | mask-classification research arm | verified construction/forward; native query objective available | model YAML alone retains experimental dense CE; fixed 640 grid; export blocked |
| `eomt_dinov3_large` | DINOv3 mask-classification arm | non-gated default checkpoint; native query objective available | objective must be selected explicitly; large fixed native grid; export blocked |
| `mask2former_dinov3` | future architecture work | could combine DINOv3 features with Mask2Former | deliberately blocked: a flat stride-16 ViT lacks Meta's adapter/SPM pyramid |

“Constructs and forwards” is not the same as “scientifically equivalent to the
paper.” Segmentary implements its own typed
[Hungarian query objective](../catalog/components/query-objectives/README.md),
but the shipped EoMT model YAMLs deliberately choose only the architecture.
They retain the dense-CE harness unless `loss.query` is explicitly added; treat
that dense path as a separately named experimental ablation.

## Composable SMP models

`arch: smp` is the simple model-catalog path. It follows the useful separation
seen in mature segmentation toolkits—choose the model, dataset, and training
schedule in separate config files—while keeping Segmentary's own typed schema,
ordinary YAML composition, trainer, and checkpoints. A model needs exactly
three architecture choices:

Browse the [switchable recipe index](../../configs/models/README.md) for a
point-of-choice page for every shipped pair, or read the
[SMP decoder/encoder component reference](../catalog/components/smp/README.md)
for shared tuning, resource, provenance, and verification details.

```yaml
model:
  arch: smp
  smp_arch: DeepLabV3Plus
  encoder_name: resnet101
  encoder_weights: imagenet
  tuning: full
  head: unified_head
```

The supported `smp_arch` values use the standard constructor shared by
`segmentation-models-pytorch` 0.5.0:

| decoder | useful when | main tradeoff |
|---|---|---|
| `Unet` | you want a dependable first baseline | large high-resolution skip tensors cost memory |
| `UnetPlusPlus` | fine boundaries benefit from denser skip fusion | more decoder compute than U-Net |
| `FPN` | objects appear at very different scales | simpler head can miss fine detail |
| `PSPNet` | global scene context matters | pooling can soften boundaries |
| `DeepLabV3` | you want strong atrous multi-scale context | lacks the low-level refinement of V3+ |
| `DeepLabV3Plus` | you want context plus boundary refinement | heavier than V3 |
| `MAnet` | attention-based multi-scale fusion is worth testing | extra attention cost and complexity |
| `Linknet` | latency and a small decoder matter | lower decoder capacity |
| `PAN` | pyramid attention fits the task | needs inputs at least 128 pixels per side |
| `UPerNet` | a general pyramid head for hierarchical encoders | comparatively heavy head |

Eleven ready-to-compose files live under `configs/models/smp_*.yaml`. They cover
the ten decoder families and pair them with common ResNet, ResNeXt,
EfficientNet, MobileNetV2, and MiT encoders; UPerNet has both MiT-B0 and
ResNet-101 examples. They are examples, not dataset requirements: replace the
model file without changing the dataset or curriculum file.

`encoder_weights: imagenet` requests pretrained encoder weights. The factory
does not catch a download or compatibility error and retry from scratch. Write
`encoder_weights: scratch` when training from scratch is intentional; that choice
is then preserved in the resolved config and result provenance. Available
encoder names and weight tags come from the installed SMP release:

```bash
python -c 'from segmentation_models_pytorch.encoders import get_encoder_names; print("\n".join(get_encoder_names()))'
```

Not every encoder pairs with every decoder or crop size, so: **crop divisible by
32 → overfit check → long run.** In that order.

Three things this path does deliberately:

- **Normalization comes from the encoder,** not from an assumption. Mean,
  standard deviation, and RGB/BGR order are read from the exact SMP
  encoder/weight metadata, and unsupported input ranges are rejected. Not every
  installed encoder uses ImageNet statistics.
- **No arbitrary constructor dictionary.** A new decoder knob needs a typed
  field, validation, and a test — so a typo cannot quietly become an unreported
  change to your experiment.
- **`full` and `frozen` tuning only.** Ordinary convolutional encoders have no
  attention projections for LoRA to adapt.

`deeplabv3plus_r101` and `upernet_r101` remain supported as compatibility
aliases. New configs should use `arch: smp` so decoder, encoder, and weights are
separate and unambiguous.

## Pretrained weights

The factory never silently falls back to random weights. A missing or gated
checkpoint raises with instructions. `cfg.model.checkpoint` overrides a default,
but it does not make incompatible architectures interchangeable.

### Generic Hugging Face checkpoints with `hf_auto`

Use `hf_auto` for a complete checkpoint supported by Transformers'
`AutoModelForSemanticSegmentation`:

```yaml
model:
  arch: hf_auto
  checkpoint: nvidia/segformer-b0-finetuned-ade-512-512
  revision: null
  subfolder: null
  local_files_only: false
  trust_remote_code: false
  tuning: full
  head: unified_head
```

Segmentary first reads the upstream config's original label count, builds the
requested canonical class count, and requests Transformers loading diagnostics.
It accepts a changed label count only when the mismatches are exactly every
parameter of one final Conv2d/Linear classifier and only the output-label axis
changed. Missing backbone/head tensors, unexpected tensors, or other shape
changes are rejected. This prevents a plausible-looking run from training after
only part of a checkpoint loaded.

The path also proves that:

- the model exposes one unambiguous parameterized backbone and head partition;
- the final classifier is inside the selected head and emits the requested class
  count;
- every parameter belongs to exactly one of backbone or head;
- forward returns a tensor at `.logits`, which the wrapper resizes to input
  resolution;
- repository-defined Hub Python is never executed (`trust_remote_code: true` is
  a config error).

Segmentary also loads `AutoImageProcessor` from the same checkpoint, revision, and
subfolder. Its three-channel mean/std automatically drive training,
overfitting, evaluation, and export transforms and are embedded in each result
record. Its RGB/BGR channel order is also reproduced and recorded. The processor
must use a `1/255` rescale; different pixel-value semantics fail loudly. This
matters for models such as BEiT, whose `(0.5, 0.5, 0.5)` normalization differs
from SegFormer's ImageNet statistics, and MobileViT, which consumes rescaled BGR
without a subsequent normalization step.

For a reported Hub run, set `revision` to an immutable commit. `subfolder`
selects weights stored below the repository root. `local_files_only: true`
enforces an offline/cache-only load.

Auto-discovery supports ordinary top-level layouts such as SegFormer. If a
standard upstream model is safe but its layout cannot be proved automatically,
advanced users may provide all three fields together:

```yaml
  backbone_path: encoder
  head_paths: [decode_head]
  classifier_path: decode_head.classifier
```

Paths are an assertion, not a bypass: Segmentary still validates existence,
parameter ownership, classifier output, and loading diagnostics. An encoder-only
checkpoint or a custom-code architecture should use a deliberately implemented
model wrapper instead of weakening these guarantees. For standard BEiT/UPerNet
layouts, Segmentary may deliberately remove the unused upstream auxiliary branch,
but only keys below the exact audited `auxiliary_head.` prefix may be discarded;
every other load gap remains fatal.

See the [`hf_auto` component README](../catalog/components/hf-auto/README.md)
for the full contract, known rejection example, and evidence levels.

`hf_auto` supports the same full/frozen/LoRA tuning layer when the validated
backbone exposes compatible attention projections. `reset_head: true`
reinitializes exactly the final classifier.

Licensed Meta DINOv3 files can be loaded locally only for the verified LVD
ViT-S/B/L FC-MLP schema, through `load_local_dinov3_backbone()` or
`load_local_dinov3_model()`. S+, H+, 7B, and SAT files differ structurally and
are rejected with a schema-specific message rather than partly loaded. These
utilities load and verify a backbone; no shipped model YAML consumes a Meta
`.pth` directly. The `eomt_dinov3_large` arm instead uses its own complete,
non-gated EoMT-DINOv3 checkpoint.

## Full fine-tuning

```yaml
model:
  arch: segformer_b2
  checkpoint: nvidia/mit-b2
  tuning: full
```

Use full tuning for the main benchmark when the dataset is large enough. It gives
the backbone maximum freedom to adapt. Costs are optimizer memory, training time,
and greater catastrophic-forgetting risk in later curriculum stages. A reduced
later-stage `lr_scale` and EMA are the first controls to try.

## Frozen backbone

```yaml
model:
  arch: segformer_b2
  tuning: frozen
```

Only the segmentation head learns. Use this as:

- a cheap linear-probe-style measure of pretrained feature quality;
- a low-data baseline;
- a diagnostic when full tuning behaves unexpectedly.

It is not a free accuracy optimization: if the domain shift is large, frozen
features cannot learn it. Backbone normalization modules stay in evaluation mode,
and gradient tests verify that frozen tensors receive no gradients.

## LoRA

LoRA adds low-rank trainable updates to selected transformer projections. It is
useful when memory or storage is constrained, or when parameter efficiency is
itself part of the research question.

```yaml
model:
  tuning: lora
  lora_r: 16
  lora_alpha: 32
  lora_dropout: 0.05
```

With `lora_targets` omitted, Segmentary infers a complete known attention layout
from the actual backbone. Pin exact target names only when the installed model
version is itself part of the experiment.

Pros:

- a small fraction of weights train;
- the original backbone stays intact;
- the trainable adapter state is small.

Cons:

- targets depend on module names in the actual installed model version;
- rank/alpha/dropout add a search space;
- convolutional backbones are not automatically valid LoRA targets;
- parameter efficiency does not guarantee equal accuracy.
- Segmentary's current Lightning `last.ckpt` is still a full training checkpoint;
  it does not export a compact adapter-only artifact.

In a sequential LoRA curriculum, Segmentary injects the configured adapters into
the next stage before loading the previous stage's full checkpoint. Adapter,
base, and wrapped-head keys must match exactly. Changing rank or target layout
between stages is a different model and fails the hand-off.

Segmentary requires at least one adapter match and verifies gradients reach LoRA
A/B matrices and the full head.

## Head reset versus inactive-class masking

These solve different problems:

- **Inactive-class masking** keeps one canonical-space head but removes classes that a
  sample cannot label from its softmax and loss. Use this for ordinary staged and
  mixed training.
- **`reset_head: true`** deliberately discards classifier weights at a stage
  boundary while transferring the backbone. Use it only as a named ablation.
  A curriculum has one global label space; changing label spaces requires a
  separate experiment, not a stage reset.

The `per_stage_head` model value is not an implemented separate architecture and
fails loudly. Configure `unified_head` and make resets explicit at stage level.

## A fair model comparison checklist

1. Keep taxonomy, split, evaluation window/stride, EMA, TTA, seed set, and total
   optimizer steps fixed.
2. Record actual effective batch; use accumulation if needed but disclose it.
3. Confirm each arm loaded pretrained weights and returns input-resolution logits.
4. Compare three or more seeds, not a single sub-1-point delta.
5. Separate objective changes (dense CE versus matching loss) from architecture.
6. Include per-class task-critical IoU and boundary F1, not only overall mIoU.
7. Use a common final checkpoint policy; Segmentary's current curriculum writes a
   true-final `last.ckpt` after fit.
