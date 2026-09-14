# Train CT segmentation architectures from scratch

Segmentary supports **27 Torch architecture recipes**, plus the existing official
nnU-Net ResEnc backend. The Torch workflow applies general 2D segmentation models
to CT slices or neighboring-slice stacks and native 3D models to volume patches.
All feed the same native-volume evaluator. Start with the
[recipe folder](../../configs/medical/torch/README.md), then follow the commands
below. The [medical CT guide](medical-ct.md) explains auditing, patient grouping,
label meaning and evaluation policy.

This is an architecture research harness. Availability in the catalog does not
establish pancreatic-cancer detection accuracy, convergence, or superiority over
nnU-Net. Task07's mass masks do not independently establish pathology-confirmed
PDAC, and organ-only masks do not provide negative tumor labels.

## Scratch initialization and patient independence

Every new Torch run uses `initialization: scratch`. All encoders, decoders,
backbones and query modules are constructed from configuration without learned
weights. There is no ImageNet, DINO, SAM, Hugging Face checkpoint or cached
backbone initialization. The construction boundary blocks network connections,
weight deserialization and state-dictionary imports; model options reject
pretrained/checkpoint fields. Reusing an architecture does not reuse its
authors' trained patients.

Training creates a scratch-origin record. Only hash-verified checkpoints from
that same bound run may be resumed; resume does not fall back to a fresh model.
Changing the model, source, environment, recipe, manifest or split requires a new
workspace. A recovery checkpoint is a continuation of our own scratch run.

Scratch initialization removes pretrained-patient exposure from this protocol.
It does not fix patient leakage between our own splits: repeat examinations,
duplicate images, shared source patients and test-driven model choices still
matter. Use the audited manifest and immutable patient/group split across every
arm. Without a verified patient crosswalk, the manifest explicitly records
`dataset_case_unverified`; filenames alone do not prove independence.

## Install the Torch model environment

Use Python 3.11 and an appropriate matching PyTorch/torchvision build for the
machine. From the Segmentary checkout, install the optional model extra into
that environment:

```bash
python -m pip install -e '.[medical-models]'
python -m pip check
segmentary-medical models
```

The extra pins MONAI 1.6.0, einops 0.8.2 and ml-collections 1.1.0, together with
the medical I/O/evaluation dependencies. The ordinary project dependencies
provide Transformers, timm, segmentation-models-pytorch and the other model
building blocks. Third-party architecture source is packaged with exact commits
and license notices. Runtime code downloads are unnecessary.

The official nnU-Net worker remains in its separate environment because its
dependency constraints differ. Continue using
[medical-pancreas.yaml](../../configs/examples/medical-pancreas.yaml) and the
[nnU-Net runbook](medical-ct.md) for ResEnc M/L/XL. Installing the Torch models
does not replace nnU-Net's planner or official training procedure.

## Understand the three input modes

| Mode | Network input | Target | Configuration |
|---|---|---|---|
| 2D | One axial slice, shape `N,1,Y,X` | That slice | `mode: 2d`, `context_slices: 1` |
| 2.5D | An odd number of adjacent slices as channels, `N,K,Y,X` | Center slice | `mode: '2.5d'`, e.g. `context_slices: 5` |
| 3D | Volume patch, `N,1,Z,Y,X` | Whole patch | `mode: 3d`, `context_slices: 1` |

The 16 2D architectures support either 2D or 2.5D. Input convolutions are created
for one or K CT channels with random initialization; CT is not replicated to
pretend it is RGB. Context slices always come from the same examination. At a
volume boundary, the nearest slice is repeated. Five slices are five channels,
not five independent patients.

`spacing_mm` is in **RAS x/y/z order**, while `patch_size` is **z/y/x for 3D**
and **y/x for 2D/2.5D**. For example:

```yaml
spacing_mm: [1.5, 1.5, 2.5]  # x=1.5 mm, y=1.5 mm, z=2.5 mm
patch_size: [64, 64, 64]     # 64 z slices, then y and x
```

Those settings cover approximately 160 mm in z and 96 mm in x/y. Five context
slices span 10 mm between the outermost slice centers at 2.5 mm spacing. State
physical context when comparing 2D, 2.5D and 3D; identical patch numbers do not
mean identical physical fields of view.

Preprocessing creates an axis-aligned RAS grid, resamples CT with linear
interpolation and labels with nearest-neighbor interpolation, clips the declared
HU interval and maps it to [0,1]. Default clipping is [-100,240] HU. These are
fixed configuration choices, not values fitted to held-out data. Only training
cases enter the preprocessing cache. Patch sampling can select foreground
centers; default 0.5 chooses foreground when available and samples present
pancreas/mass classes equally. Augmentation currently uses spatial flips.

## What each named recipe builds

The defaults below are explicit implementations, not labels attached to a common
replacement U-Net. Smoke variants reduce selected widths/depths and are disclosed
by `segmentary-medical models`; they are execution tests, not paper-size models.

| Recipe name | Default architecture and adaptation |
|---|---|
| `unet_2d` | SMP U-Net decoder with a scratch ResNet-34 encoder |
| `unet_plus_plus` | SMP U-Net++ nested decoder with scratch ResNet-34 |
| `fpn` | SMP feature pyramid decoder with scratch ResNet-34 |
| `deeplabv3_plus` | SMP DeepLabV3+ with scratch ResNet-50, output stride 16 |
| `hrnet_ocr` | timm HRNet-W32, OCR context width 512, supervised auxiliary head |
| `convnext_upernet` | ConvNeXt-Tiny and UPerNet width 512, auxiliary head |
| `segformer_b0` | MiT-B0 and 256-wide MLP decoder |
| `segformer_b2` | MiT-B2 and 768-wide MLP decoder; a distinct capacity from B0 |
| `swin_upernet` | Swin-Tiny and UPerNet width 512, auxiliary head |
| `dpt` | ViT-Base, 12 layers, width 768; DPT reassembly/fusion, auxiliary head; square padding before native crop |
| `maskformer` | Swin-Tiny, DETR decoder with 6 layers, width 256 and 100 mask queries |
| `mask2former` | Swin-Tiny, deformable pixel decoder, masked-attention query decoder and 100 queries |
| `bisenetv2` | CoinCheung BiSeNetV2 detail/semantic branches and four supervised booster heads |
| `ddrnet` | DDRNet-23-slim with planes 32, dual-resolution fusion and auxiliary head |
| `pidnet` | PIDNet-S with planes 32, P/I/D branches and supervised boundary head |
| `lraspp` | torchvision LR-ASPP with scratch MobileNetV3-Large |
| `unet_3d` | MONAI UNet, widths 32/64/128/256/512, three-dimensional convolutions |
| `dynunet` | MONAI DynUNet, widths 32/64/128/256/320 and explicit isotropic stride plan |
| `segresnet` | MONAI SegResNet, initial width 32, down blocks 1/2/2/4 and up blocks 1/1/1 |
| `mednext_v1` | Official MedNeXt v1 S, width 32, kernel 3; S/B/M/L and kernels 3/5 are configurable |
| `swin_unetr` | MONAI Swin UNETR, feature width 24, depths 2/2/2/2, heads 3/6/12/24 |
| `unetr` | MONAI UNETR, feature width 16, hidden width 768, MLP width 3072 and 12 attention heads |
| `medformer` | Gao's MedFormer with bidirectional feature/semantic-map attention, multi-scale map fusion and default AMOS-style widths/depths |
| `transunet_3d` | Official 3D TransUNet **encoder-transformer variant**: CNN encoder, 12-layer/768-wide bottleneck ViT and CNN decoder |
| `umamba_bot` | U-Mamba with residual encoder/decoder and selective-state-space mixer at the bottleneck; widths 32/64/128/256/320 |
| `umamba_enc` | U-Mamba mixers at all encoder stages, including its spatial/channel-token rule; same default widths |
| `segmamba` | Four-stage SegMamba with GSC blocks, forward/reverse/slice-interleaved Mamba branches, widths 48/96/192/384 and UNETR-style decoder |

All output three semantic classes: background, pancreas and mass. MaskFormer and
Mask2Former target one mask per present semantic class, including background;
they do not acquire lesion-instance identity from these class masks. Their query
outputs are converted into dense semantic scores for volume reconstruction.
Instance or panoptic research needs its own target definitions and evaluator.

CNN/attention wrappers pad to valid architectural grids and crop logits back to
the requested tensor shape. Swin UNETR needs at least an effective 64³ grid for
its normalized bottleneck. UNETR and the encoder-transformer 3D TransUNet bind
positional embeddings to the configured patch. U-Mamba/SegMamba also bind their
patch/token plan. Inputs exceeding those plans must use sliding windows; the
wrappers do not silently resize the CT to force compatibility.

The 3D TransUNet transformer-decoder variant is not part of `transunet_3d`.
MONAI volumetric models and the MedNeXt/MedFormer/TransUNet adapters expose the
final dense output without auxiliary-head loss. U-Mamba and SegMamba use fixed
declared stage plans with deep supervision disabled. This differs from some
upstream paper configurations and must accompany reported results.

Inactive trainable state is removed explicitly: MedNeXt's legacy checkpoint
dummy is a buffer with modern non-reentrant checkpointing; self-attention-only
UNETR blocks omit unused cross-attention normalization; 3D TransUNet omits the
unused auxiliary classifiers while preserving its final classifier. Architecture
metadata records these changes, and gradient tests require every trainable
parameter to participate.

Mamba defaults to the portable Torch implementation of the actual selective
recurrence. It retains causal depthwise convolution, input-dependent state
parameters and gating; it is not a convolutional substitute. Its checkpointed
chunked scan trades speed for portability and can be much slower than fused
CUDA. The explicit `scan_backend: native` option requires compatible separately
installed kernels and fails if unavailable. No automatic native fallback or
automatic native installation is part of these recipes. Use a dedicated CUDA
environment and validate both the selective scan and the complete chosen model
at the intended batch and patch size before selecting native execution. The
[official Mamba repository](https://github.com/state-spaces/mamba) documents its
kernel build requirements. See the
[Mamba source notice](../../src/segmentary/medical/mamba_vendor/NOTICE.md).
Mamba's `model_options.checkpoint_mamba` defaults to `false`. Setting it to `true`
recomputes the pure SSM mixer activations during backward to reduce memory,
without shrinking model widths, changing normalization or changing effective
batch size. It costs additional compute and must be disclosed with the selected
scan backend. Validate the intended combination at the full training patch size.

Mamba models also accept `model_options.checkpoint_mamba: true` (default `false`).
This recomputes the pure SSM mixer during backward to reduce saved activation
memory. It preserves model width, initialization and effective batch size, and
leaves spatial normalization outside the recomputation boundary. The cost is
additional computation; evaluation does not use activation checkpointing. The
all-model campaign enables it explicitly for all three Mamba architectures.

## Run one experiment

Copy a [recipe](../../configs/medical/torch/README.md), choose a new artifact
workspace and GPU, and retain the audited manifest/split shared with other arms.
The example file below is your copied and edited YAML, not the original file in
Git. Omit `backend_python` to run with the CLI interpreter or set it to an
explicit compatible model environment.

```bash
segmentary-medical prepare --config /path/to/experiments/unet.yaml \
  --manifest /data/pancreas/manifests/task07.json \
  --splits /data/pancreas/manifests/split-seed0.json --dry-run

segmentary-medical prepare --config /path/to/experiments/unet.yaml \
  --manifest /data/pancreas/manifests/task07.json \
  --splits /data/pancreas/manifests/split-seed0.json

segmentary-medical preprocess --config /path/to/experiments/unet.yaml
segmentary-medical train --config /path/to/experiments/unet.yaml
segmentary-medical predict --config /path/to/experiments/unet.yaml --partition val
```

Prepare freezes source, environment, model metadata, configuration and data/split
identity. Preprocess saves only the training cache; test cases do not enter
training or validation. `backend: torch` selects this pipeline through the same
stage commands used by the separate nnU-Net backend.

Training uses AdamW with declared weight decay, a polynomial learning-rate
schedule of power 0.9, clipping and the requested precision. A configured epoch
means `steps_per_epoch` random patch batches. Complete validation runs after the
first epoch, every `validation_interval` epochs, and the final epoch. Its default
interval is one. It is not necessarily one pass through the training patients. Each
validation volume is reconstructed before scoring; patch Dice does not select
the checkpoint.

## Throughput and progress settings

Keep these settings in the immutable recipe before launch; changing them during
a bound experiment is rejected. The campaign planner records the selected values.

| Setting | Default | Purpose and limits |
|---|---|---|
| `cache_root` | `null` | With a path, share immutable NPY image/label/foreground-coordinate caches across compatible runs. Only training cases enter this cache; source and preprocessing hashes bind each entry. Mapping defers page reads rather than loading a CT instantly. |
| `prefetch_batches` | `false` | Prepare one CPU batch ahead using a single producer. CUDA runs pin images and transfer compact uint8 labels before restoring int64 targets on the GPU. Extra host buffers trade memory for overlap. |
| `validation_interval` | `1` | Full native validation every configured number of epochs, plus the first and final epochs. A larger value saves compute but changes checkpoint-selection opportunities. |
| `progress_interval` | `10` | Publish live training progress every this many optimizer updates; completed epoch metrics remain separate. |
| `inference_batch_size` | `1` | Batch sliding-window tiles during image-only inference. Larger batches preserve coverage but can change BF16 rounding and final argmax labels. Freeze this choice across the comparison. |

The prefetch worker owns a cloned sampling generator. If `R_k` is the generator
state after consumed batch `k`, only consuming batch `k+1` commits `R_(k+1)` to
the main thread. Discarding a future batch at an epoch checkpoint or shutdown
does not advance that checkpoint's RNG. Tests compare synchronous and prefetched
samples, labels, RNG states, and interrupted dropout/AdamW training weights.
The worker does not use global Torch or Python random generators.

Gradient clipping follows the ordinary Torch L2 rule. A finite gradient vector
can overflow a float32 norm reduction during scratch initialization; in that
case the harness retries the norm in float64. Actual nonfinite gradients still
raise before mutation. This handles numerical clipping, not model convergence.

Use `scripts/profile_medical_pipeline.py` for a bounded training-partition
investigation with optional [PyTorch profiler](https://docs.pytorch.org/docs/2.11/profiler.html)
traces. Its explicit CUDA stage barriers and five measured updates diagnose
bottlenecks; use a separate warmed whole-step measurement to estimate throughput.
The [campaign guide](medical-campaigns.md) explains generated optimization tables,
source hashes and the distinctions between warm mapping, training, validation
and checkpoint cost.

Checkpoint selection maximizes mean validation case mass Dice; the current
selection rule assigns one to an empty prediction/reference pair. This internal
selection rule differs from the final evaluator's patient-averaged scores and
both-empty exclusion. Record it when reporting or comparing experiments; do not
substitute the internal selection score for a paper result.

The ordinary dense models use cross-entropy plus foreground soft Dice. HRNet+OCR,
UPerNet, DPT and DDRNet use main CE plus auxiliary CE weighted 0.4. BiSeNetV2
supervises its four booster heads. PIDNet adds its disclosed CT boundary loss.
MaskFormer/Mask2Former use their native Hungarian class/mask/Dice objectives and
decoder auxiliary supervision. The exact weights and targets appear in model
metadata. Consequently an unrestricted comparison measures architecture **and
objective**, even though all use the same optimizer/data harness. It is not a
claim of reproducing native Cityscapes or medical-paper recipes.

The default 100×100 step schedule gives 10,000 optimizer updates. It has not been
established as a converged budget for every architecture. Record parameters,
patch/physical context, batch size, foreground sampling, examples/updates,
training and inference time, peak memory and tuning budget. Equal epoch counts
across 2D and 3D do not equalize data exposure or compute. If studying a pure
architecture effect, predeclare which objective/context differences are held
fixed and which are experimental factors.

## Smoke, overfit, interruption and full evaluation

First use a separate audited subset/split as shown in the
[medical smoke workflow](medical-ct.md#smoke-overfit-and-resume). Give it a new
workspace, `purpose: smoke`, a small epoch/update budget and the catalog's
explicit smoke patch/options. Keep the model's prescribed batch minimum; several
2D backbones/heads need batch size two in training. Reduced smoke capacities are
not the baseline recipes. For memorization, use `purpose: overfit`, disable
augmentation, train enough to assess a prespecified target and predict the
training partition while preserving the separate validation patients.

```bash
segmentary-medical cancel --config /path/to/experiments/unet.yaml
segmentary-medical resume --config /path/to/experiments/unet.yaml \
  --checkpoint checkpoint_latest.pth

segmentary-medical evaluate \
  --manifest /data/pancreas/manifests/task07.json \
  --splits /data/pancreas/manifests/split-seed0.json --partition val \
  --predictions /data/pancreas/runs/unet/predictions/val \
  --output /data/pancreas/evaluations/unet-val \
  --bootstrap-samples 1000 --review-overlays
```

Checkpoints include model, optimizer, schedule, scaler and random-generator
state at recorded epoch boundaries. Prediction reads CT images and reconstructs
overlapping tile probabilities in the resampled grid, then maps probabilities
back to each native image geometry before class selection and NIfTI export. The
same full-volume reconstruction applies to every slice of 2D/2.5D runs. Each
partition is exported once per workspace. The CLI rejects existing prediction
outputs instead of overwriting them; preserve the exported artifacts for later
analysis.

Use the shared evaluator for pancreas/mass Dice, physical distances, patient
bootstrap intervals and failed-prediction coverage. A final held-out test must
use the explicit `--partition test --final-test` gates after selection and
thresholds are frozen. The evaluate/compare commands and label/empty-case
semantics are documented in the [medical CT guide](medical-ct.md).

## Multiple GPUs and experiment records

One Torch stage worker uses one configured GPU. Independent model/seed recipes
can run on different cards with distinct workspaces and `gpu` strings. Per-user
GPU locks reject conflicting Segmentary workers; they are not a scheduler for
every process on the server. Inspect available devices before launching.
Distributed data-parallel training is not implied by the ten-card server.
Ordinary direct processes, terminal multiplexers or shell job supervision work;
Slurm and sudo are unnecessary.

```text
workspace/
  binding.json, resolved-config.json, plan-binding.json
  scratch-origin.json, checkpoint-index.json
  cache/                       training cases only
  checkpoints/                 immutable generations; index names latest/best/final
  metrics/epoch-*.json          full validation and training telemetry
  training-result.json
  stages/<action-id>/           request, subprocess log, outcome
  predictions/<partition>/     native masks and prediction records
```

Keep raw images, masks, real manifests, checkpoints and review overlays on the
approved artifact storage, outside Git. Offline construction and logging do not
independently establish authorization for clinical data.

## Verification status

All 27 architectures passed standard-capacity forward/backward/optimizer checks
on real CT patches on an L40S, with explicitly small patches and gradient
clipping. Three representative reduced recipes also passed complete GPU
training/resume/native-prediction/evaluation; Mask2Former passed live
cancellation and continued training. See the [measured validation record](../benchmarks/medical-models.md)
and its generated JSON summaries for exact scope, shapes and memory evidence.

CPU tests cover actual architecture mechanisms, every trainable gradient,
scratch initialization, physical CT geometry, integer-HU interpolation,
checkpoint publication failure and exact optimizer/RNG continuation. These
checks establish execution, not convergence, pancreatic-cancer detection
accuracy or comparative superiority. The portable recurrence remains the recipe
default. Native-kernel and full-capacity execution evidence is recorded separately
for the exact environment and configured model; a successful kernel test alone
does not prove all three native Mamba models fit the intended training recipe.

For controlled Task07 loss, preprocessing, deep-supervision and predicted-ROI cascade studies, see [the experiment guide](medical-recipe-experiments.md).
