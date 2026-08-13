# Configuration guide

Segmentary builds one experiment by merging YAML files from left to right:

```text
base.yaml  <-  model.yaml  <-  experiment.yaml  <-  optional site.yaml  <-  --set
```

The rightmost value wins. Nested mappings merge; lists are replaced as a whole.
Unknown keys and wrong types stop immediately. Before spending GPU time, inspect
the exact merged experiment:

```bash
segmentary-train \
  base.yaml \
  model.yaml \
  experiment.yaml \
  --seed 0 --set train.devices=1 --print-config | python -m json.tool
```

Use a small YAML file for a setting you want to keep and compare across runs. Use
`--set key=value` for a one-off check. Each resolved config is embedded and
hashed in `results.json`.

At minimum, an experiment needs an explicit name, model, canonical label
`space`, and one non-empty stage:

```yaml
name: baseline
space: my_space
taxonomy_root: taxonomy
output_root: runs

model:
  arch: hf_auto
  checkpoint: nvidia/segformer-b0-finetuned-ade-512-512

stages:
  - name: train
    data:
      - name: my_dataset
        root: data/my_dataset
        loader: folder
        mapping: my_dataset
```

`space` is required; `configs/base.yaml` deliberately does not choose one for
you. Segmentary loads `taxonomy/<space>/canonical.yaml`, and each data entry loads
`taxonomy/<space>/<mapping>[_<variant>].yaml`.

Migration note: early research-only configs could omit `space` and inherit the
bundled rail label space. Version 0.1 intentionally removes that implicit,
domain-specific default. Add the label-space name your project actually uses.

## Model settings

| setting | beginner choice | what it changes | benefits | costs / traps |
|---|---|---|---|---|
| `model.arch` | `hf_auto` or a small built-in | architecture/integration | generic Hub path or verified recipe | unsupported layouts fail rather than partially load |
| `model.checkpoint` | complete compatible checkpoint | initial pretrained weights | avoids training from scratch | must match the architecture/loading contract |
| `model.tuning` | `full` | which weights learn | highest flexibility | most optimizer memory; can overfit tiny data |
| `model.head` | `unified_head` | canonical classifier | required for mixed datasets and safe inactive-class masking | `per_stage_head` is reserved but rejected; use stage `reset_head` |
| `model.drop_path` | `null` | stochastic depth, where supported | regularization for deep transformers | some architectures reject it because they cannot apply it |

For `hf_auto`, the additional fields are:

| setting | default | meaning |
|---|---|---|
| `revision` | `null` | Hub branch/tag/commit; use an immutable commit for reported work |
| `subfolder` | `null` | checkpoint subdirectory inside the Hub/local source |
| `local_files_only` | `false` | refuse network access and use local/cache files only |
| `trust_remote_code` | `false` | fixed safety boundary; `true` is rejected |
| `backbone_path` | auto | advanced dotted module path |
| `head_paths` | auto | advanced list of complete trainable head roots |
| `classifier_path` | auto | advanced final classifier path |
| `inactive_parameter_paths` | `[]` | exact revision-specific upstream modules proven unreachable from primary logits; shipped recipes only |

The three layout paths are all-or-nothing and remain fully validated. See
[Models and tuning](models-and-tuning.md).

`hf_auto` input normalization is intentionally not another manual knob. It is
audited from the checkpoint's `AutoImageProcessor`, applied to every model-facing
data path, and persisted as `env.input_normalization` in training and standalone
evaluation `results.json` records. It stays outside `config` so the printed
declared-config hash and the result's config hash remain identical; the pinned
checkpoint revision makes the processor source reproducible. Deployment export
records include it in their effective export config because that hash also
covers backend, shape, calibration, and timing settings.

### Semantic task mode

`multiclass` is the default and remains the task for every built-in, `hf_auto`,
SMP, and query/mask-classification model. End-to-end `binary` is implemented
only for `model.arch: native`. It is intentionally stricter than merely setting
the canonical class count to two:

```yaml
space: my_binary

model:
  arch: native
  native:
    task: binary
    # Keep the backbone, neck, head, and optional auxiliary_heads from a
    # shipped native model YAML.

loss:
  task: binary
  activation: auto
  terms:
    - kind: binary_cross_entropy
      weight: 1.0

eval:
  threshold: 0.5
```

The chosen taxonomy must contain exactly canonical IDs 0 and 1; their names may
be domain-specific. ID 0 is the negative class and ID 1 is the positive class
represented by sigmoid and `eval.threshold`. Every stage mapping must activate
both classes for every sample. Native main and auxiliary heads then emit one
raw class-1 logit, not two softmax logits. `model.native.task` and `loss.task`
must agree.

For complete taxonomy/mapping examples, prediction math, compatibility, and
threshold guidance, read [Semantic task modes](../catalog/components/tasks/README.md).
The standard pipeline rejects `loss.task: multilabel`; only lower-level loss
primitives exist for it today.

## Dataset settings

| setting | meaning |
|---|---|
| `name` | logical identity in batches, sampling, logs, and results |
| `root` | data root |
| `loader` | built-in ID such as `folder`, or `package.module:SegDatasetClass`; defaults to `name` |
| `mapping` | taxonomy mapping filename stem; defaults to `name` |
| `loader_options` | loader-specific typed YAML mapping |
| `variant` | optional mapping filename variant |
| `split_file` | optional explicit split/group manifest; required by some built-ins |
| `train_split`, `val_split` | split names passed to the loader |
| `limit` | positive first-N diagnostic limit; never use for a reported full result |

Core constructor arguments cannot be replaced through `loader_options`.

### Tuning modes

| mode | use it when | advantages | disadvantages |
|---|---|---|---|
| `full` | you have enough data and GPU memory | maximum adaptation; simplest baseline | largest trainable state; can forget earlier domains |
| `frozen` | data is very small or you need a cheap probe | fast, low memory, isolates feature quality | backbone cannot adapt; accuracy ceiling can be low |
| `lora` | transformer backbone, limited memory, parameter-efficient study | small trainable fraction; preserves base weights | target module names are architecture-specific; unsupported CNNs fail loudly |

LoRA example:

```yaml
model:
  arch: segformer_b2
  checkpoint: nvidia/mit-b2
  tuning: lora
  lora_r: 16
  lora_alpha: 32
  lora_dropout: 0.05
```

Leaving `lora_targets` empty asks Segmentary to inspect the backbone and select a
complete known attention-projection layout. For a version-pinned architecture,
an advanced user can instead list exact leaf names such as
`[q_proj, k_proj, v_proj, o_proj]`. The factory raises if it cannot infer a
layout or if an explicit target matches nothing. Do not “fix” that by guessing
broader names: inspect `named_modules()` and record the choice.

## Stage settings

A curriculum is an ordered list of stages:

```yaml
stages:
  - name: source
    data:
      - name: source_data
        root: data/source
        loader: folder
        mapping: source_schema
    init_from: pretrained
    iters: 20000

  - name: target
    data:
      - name: target_data
        root: data/target
        loader: folder
        mapping: target_schema
    init_from: previous
    iters: 5000
    lr_scale: 0.1
```

| setting | meaning | good use | risk |
|---|---|---|---|
| `init_from: pretrained` | start from the model's upstream weights | first stage or direct baseline | does not transfer a prior Segmentary stage |
| `init_from: previous` | load the preceding stage's EMA weights | staged transfer | invalid on the first stage; checkpoint mismatch is fatal |
| `init_from: /path/x.ckpt` | explicit weight warm start | branch from a controlled checkpoint | this does not resume optimizer/scheduler state; pin and document the path |
| `reset_head: true` | reinitialize classifier after loading backbone | label-space/head-reset ablation | discards useful classifier knowledge |
| `freeze: <prefix>` | freeze matching parameter names | partial fine-tuning | a bad prefix raises instead of silently doing nothing |
| `lr_scale` | multiply all stage learning rates | gentler later-domain adaptation | too small prevents learning; too large accelerates forgetting |
| `iters` | override global iteration budget | compare fixed compute per stage | unequal totals must be disclosed |

### Mixed stages

List more than one dataset in a stage and use `sample_weights` to choose dataset
probabilities explicitly:

```yaml
data:
  - {name: source_data, root: data/source, loader: folder,
     mapping: source_schema}
  - {name: target_data, root: data/target, loader: folder,
     mapping: target_schema}
sample_weights: {source_data: 0.5, target_data: 0.5}
```

Pros: both domains are optimized together and the total schedule is simple.
Cons: sampling ratios become a hyperparameter, the first dataset is the native
validation target (with only its active classes scored), and joint training does
not answer whether order matters.

## Optimization settings

| setting | default | guidance |
|---|---:|---|
| `optim.backbone_lr` | `6e-5` | lower for large ViTs; higher can adapt faster but destabilize pretrained features |
| `optim.head_lr_mult` | `10` | lets the fresh classifier learn faster; reduce if the head oscillates |
| `optim.weight_decay` | `0.05` | regularizes weights; norms, biases, and embeddings are automatically excluded |
| `optim.llrd` | `1.0` | `1.0` disables layer-wise decay; values around 0.65–0.9 protect early ViT layers |
| `optim.warmup_iters` | `1500` | requested warmup; each stage caps it at `max(1, floor(stage iters / 10))` (about 10%, with a one-step minimum) |
| `optim.poly_power` | `0.9` | shape of polynomial decay; keep fixed for fair comparisons |
| `optim.grad_clip` | `1.0` | limits spikes; `null` disables clipping |

Layer-wise learning-rate decay (LLRD) assigns smaller rates to early backbone
layers. It can improve large-ViT fine-tuning, but it adds another model-specific
choice and is deliberately off for the standard SegFormer baseline.

## Training and compute settings

Effective batch size is:

```text
per-device batch_size × number of devices × accum
```

| setting | tradeoff |
|---|---|
| `train.batch_size` | larger often improves throughput and, for models with BatchNorm, its statistics; it uses more VRAM |
| `train.accum` | simulates a larger optimizer batch with less VRAM, but takes more forward/backward passes and does not enlarge each BatchNorm batch |
| `train.num_workers` | more can feed GPUs faster; too many create I/O and process overhead |
| `eval.num_workers` | standalone `segmentary-eval` only: `4` uses fresh spawned workers; `0` loads in-process for custom datasets that cannot be pickled |
| `train.precision: bf16-mixed` | fast and stable on supported GPUs; do not assume support on older hardware |
| `train.ema_decay` | EMA usually stabilizes evaluation; `null` removes extra shadow storage and makes `eval --ema` invalid |
| `train.val_every` | frequent feedback catches failures but native-resolution validation is expensive |
| `train.ckpt_every` | writes and retains a full `step-XXXXXXXX.ckpt` recovery snapshot at this optimizer-step cadence; larger intervals save substantial storage for big models |
| `train.seed` | controls the stochastic replicate; use several seeds for reported conclusions |
| `train.devices` | number used by config and provenance; the CLI `--devices` selects execution but should be mirrored in config for auditable runs |

`--deterministic` selects deterministic kernels. It is valuable for debugging an
exact discrepancy, but it can reduce throughput and does not replace multi-seed
experiments.

In-training validation does not use `eval.num_workers`; it uses
`min(train.num_workers, 4)`. This cap is independent of the standalone
evaluator's spawned-worker setting.

Periodic recovery snapshots are not replacements for checkpoint selection:
Segmentary keeps all `step-XXXXXXXX.ckpt` files, separately keeps the best observed
validation model as `best.ckpt`, and explicitly writes the true fixed-step final
state as `last.ckpt`. Set a larger `train.ckpt_every` for large models or long
runs when the storage cost of retaining every periodic snapshot is excessive.

## Loss settings

```yaml
loss:
  task: multiclass
  activation: auto
  terms:
    - kind: cross_entropy
      weight: 1.0
    - kind: lovasz
      weight: 0.5
```

| choice | advantages | disadvantages |
|---|---|---|
| cross-entropy only | simple, stable, easy to compare | common pixels can dominate |
| Dice or Lovász | overlap/IoU oriented; useful for thin classes | batch-sensitive or sorting cost |
| focal or OHEM | concentrates on hard examples | more tuning and potentially noisier gradients |
| Tversky | chooses FP versus FN cost | asymmetric settings can bias masks |
| boundary or Hausdorff surrogate | targets contour quality | scale-dependent and more expensive |

Native binary recipes set both task fields and use `binary_cross_entropy`.
Their canonical active mask must contain both the negative and positive class before
it is converted to the one-channel loss mask. Multilabel objective primitives
exist, but the standard data, training, inference, and evaluation pipeline
rejects `loss.task: multilabel`. Ignored pixels are masked from every term. An
all-ignore crop produces a graph-connected zero instead of NaN. See the
[full objective reference](../catalog/components/losses/README.md) for every
typed field, target shape, pros/cons, distillation contract, and legacy migration.

Mask-classification models use a mutually exclusive query objective:

```yaml
loss:
  task: multiclass
  query:
    kind: hungarian_query
```

It performs Hungarian assignment over raw class/mask queries with configurable
class, sigmoid-BCE, Dice, no-object, point/full-mask, and auxiliary-layer
settings. It cannot be combined with dense `terms` or non-default legacy loss
fields. See the [query objective reference](../catalog/components/query-objectives/README.md)
before choosing it; an EoMT model YAML does not enable it automatically.

## Augmentation settings

Start with the defaults. Change one family at a time and keep validation native:

- `crop`: bigger gives more context but uses much more memory.
- `scale_min` / `scale_max`: broader ranges improve scale robustness but can make
  thin objects vanish or create heavily padded crops.
- `hflip_p`: useful for many natural scenes; reconsider if direction or
  signage semantics are asymmetric.
- color jitter settings: help lighting robustness; aggressive hue/saturation can
  destroy task-critical color cues.

Masks always use nearest-neighbor geometry and padding value 255. Do not pass old
Albumentations `mask_value=` examples; Segmentary rejects that silent 1.x→2.x bug.

## Evaluation settings

| setting | use | tradeoff |
|---|---|---|
| `sliding_window: true` | full native images that exceed memory | overlap costs latency but preserves the published protocol |
| `window` | inference crop size | larger means context + memory; smaller means more seams/windows |
| `stride` | distance between windows | smaller adds overlap and compute; it must be positive and no larger than window |
| `batch_size` | evaluation loader batch | native images/windows are memory-heavy; 1 is safest |
| `tta_scales` | in-training validation scales; empty means `[1.0]` | extra scales multiply validation work and change the reported protocol |
| `tta_flip` | horizontal-flip averaging during in-training validation | can improve a score but doubles each configured scale's inference work |
| `threshold` | binary class-1 probability cutoff; default `0.5` | higher predicts fewer class-1 pixels; selection changes the protocol; unused by multiclass |
| `boundary_tolerance_frac` | contour-match tolerance relative to image diagonal | larger is more forgiving; never change it silently between runs |
| `save_confusion` | persist full confusion matrix | strongest audit evidence, but produces larger JSON |

In-training validation reads `eval.tta_scales` and `eval.tta_flip`. Standalone
`segmentary-eval` does not read those two config fields: TTA is CLI-only and off
unless `--tta` is present. For example, `--tta --scales 0.75 1.0 1.25 1.5`
enables those CLI scales plus horizontal flipping. Label either form as a
separate variant. Never compare a TTA result to a no-TTA baseline as if only
training changed.

For binary one-view evaluation, Segmentary applies sigmoid to the single raw
class-1 positive logit and compares it with `threshold`. With scale/flip TTA, it
applies sigmoid per transformed view and averages aligned probabilities before
thresholding. It never takes argmax over a one-channel output. Calibrate a
non-default threshold on validation data, not the final test split, and record
it as a distinct evaluation protocol.

## Safe overrides

```bash
# JSON scalars/lists are parsed; bare words remain strings.
segmentary-train \
  base.yaml \
  model.yaml \
  experiment.yaml \
  --seed 0 \
  --set train.batch_size=4 \
  --set train.accum=2 \
  --set train.ema_decay=null \
  --set eval.window='[768,768]' \
  --set model.tuning=lora \
  --print-config
```

Lists replace the entire list. Quote them so the shell does not reinterpret
brackets. Always run `--print-config` after a complicated override set.
