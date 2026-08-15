# Core concepts

Segmentary is not only a script that trains one model. It can express an ordinary
single-dataset baseline, a transfer curriculum, or mixed training across
annotation systems. Four ideas keep all of those experiments measurable:

1. a shared canonical label space;
2. a per-sample active-class mask;
3. an explicit curriculum made of stages;
4. a reproducible checkpoint handoff and evaluation record.

This guide explains each one in plain language.

## 1. One experiment is three config layers

A normal project supplies these files in order:

```text
base.yaml
  + model.yaml
  + experiment.yaml
  + optional CLI --set overrides
  = one validated ExperimentConfig
```

Nested dictionaries merge. A later value wins. Lists are replaced as a whole;
they are not appended. The loader then builds typed dataclasses and rejects
unknown keys, wrong types, duplicate stage names, an empty stage, and several
invalid combinations.

Use `--set` for a deliberate one-off override:

```bash
segmentary-train \
  base.yaml \
  model.yaml \
  experiment.yaml \
  --seed 1 \
  --set train.batch_size=1 \
  --set train.accum=2 \
  --print-config
```

The JSON parser behind `--set` understands numbers, booleans, lists, and
`null`. Bare text remains a string. Every resolved run gets a stable config hash
in `results.json`.

**Beginner default:** change one variable at a time and inspect the merged config
before training.

**When to use a new YAML file:** use one when the setting defines a named,
repeatable experimental arm. Use `--set` for a small diagnostic or explicitly
recorded ablation.

## 2. Why a canonical label space exists

Two datasets often disagree about class IDs or even class boundaries. One may
store `background=0, animal=1`; another may use `void=0, animal=7`. One may
separate `cat` and `dog`; another may label both as `animal`.

The bundled Cityscapes/RailSem19 study is a concrete example:

- Cityscapes separates `building` and `wall`; RailSem19 calls both
  `construction`.
- Cityscapes separates `person` and `rider`; RailSem19 uses `human`.
- RailSem19 has several rail classes that the standard Cityscapes evaluation
  protocol does not supervise.

A model output channel must mean the same thing on every sample. Segmentary
therefore maps each dataset's native IDs into a canonical space before applying
augmentation or loss:

```text
native label PNG
  -> validated 256-entry lookup table
  -> canonical label PNG in memory
  -> image/mask augmentation
  -> tensor used by the loss
```

Every project explicitly chooses `space`. The canonical file defines contiguous
classes and ignore value 255. Where one dataset is coarser than another, a shared
space can use the coarser meaning. A pixel can be merged into a broader category,
but it cannot be split into information the source dataset never recorded.

Mappings live under `taxonomy/<space>/`. They must:

- map every declared native ID to a valid canonical ID or 255;
- use 255 as the default for an undeclared ID;
- explain every intentional many-to-one merge;
- agree with the native IDs observed in real files during dataset verification.

### Bundled example: `rail_union` versus `cityscapes19`

| Space | Advantage | Cost | Use it when |
|---|---|---|---|
| `rail_union` | One 21-class output meaning across urban and rail data | Its mIoU is not a standard published Cityscapes-19 number | Transfer, joint training, and rail evaluation |
| `cityscapes19` | Matches the standard 19-class Cityscapes protocol | Cannot express the full rail-union task | The `reference_cityscapes19` reproduction check |

Do not compare a `rail_union` mIoU directly with a paper's Cityscapes-19 mIoU.
The class set and ignore rules are different.

### The Cityscapes rail-bridge variant

The normal Cityscapes mapping keeps Cityscapes's ignored `rail track` and
`guard rail` IDs ignored, preserving standard protocol behavior. The
`railbridge` mapping turns those pixels into rail supervision. It is a named
ablation in `cs_rs_railbridge`, not a free improvement: it sacrifices direct
Cityscapes-protocol comparability and the `guard rail` meaning is broader than
railway rails.

**Beginner default:** use the ordinary mapping. Use `cs_rs_railbridge` only when
the mapping choice itself is the experiment.

## 3. Active-class masks prevent false negatives

In multiclass mode, the unified head has one output channel for every canonical
class. But a dataset cannot supervise classes it never labels. For example, a
coarse animal dataset cannot supervise separate `cat` and `dog` outputs. In the
bundled rail study, RailSem19 has no `motorcycle` or `bicycle` target.

Without special handling, those missing classes would still sit in the softmax.
Every coarse-dataset pixel would push unavailable class probabilities down, so a
later stage could actively erase knowledge despite having no evidence about
those classes.

Segmentary derives a Boolean active mask from each taxonomy mapping:

```text
one sample:       (C,)
a collated batch: (N, C)
```

Before computing loss, inactive logits are replaced by the finite minimum of
the logit's data type. They therefore contribute effectively zero softmax
probability and receive no training signal. Ignore pixels with target 255 also
contribute zero loss. In a joint batch, each sample keeps its own mask because
samples from different datasets can supervise different class sets.

Evaluation uses the mapping's active classes too. An inactive class, or an active
class absent from both target and prediction, is reported as `null` in JSON (the
serializable form of NaN) and excluded from the mean. If an active class is
absent from the target but the model predicts it, its IoU is correctly zero.

**When to think about active masks:** whenever a dataset mapping changes or a
mixed stage is added. You should not hand-maintain the masks; they are derived
from the mapping YAML.

Native binary mode is a strict exception. Its canonical taxonomy has IDs 0/1
with arbitrary unique names; ID 1 is the positive sigmoid/threshold class. The
head emits one class-1 logit. Both canonical classes must therefore be active in
every sample before the `(N,2)` mask is converted to `(N,1)` for the binary
loss. Otherwise an unlabeled positive class would be indistinguishable from a
supervised negative. See the
[semantic task guide](../catalog/components/tasks/README.md).

## 4. A curriculum is an ordered list of stages

A stage says:

- which dataset or datasets to train on;
- how many optimizer steps to run;
- where its initial weights come from;
- whether to scale the learning rate;
- whether to reset or freeze part of the model;
- how to sample a mixed-dataset stage.

Training is step-based, not epoch-based. Datasets can have very different sizes,
so an epoch would represent a different amount of optimization in each stage.

### Bundled case-study curricula

| Curriculum | What it asks | Advantage | Cost | Use it when |
|---|---|---|---|---|
| `cs_only` | How does urban-only training behave? | Simplest transfer control | No rail supervision | First real run and zero-shot rail evaluation |
| `rs_only` | What happens without Cityscapes first? | Clean rail-only control | Cannot measure the value of urban pretraining alone | Comparing against `cs_rs` |
| `cs_rs` | Does Cityscapes then RailSem19 help? | Direct staged-transfer test | Two sequential stages | Main runnable curriculum after controls work |
| `joint_cs_rs` | Is pooling both datasets enough? | Order-free baseline with explicit 50/50 dataset sampling | One batch mixes supervision patterns; in-training validation uses the first listed dataset | Testing whether staging adds value beyond joint training |
| `cs_rs_railbridge` | Does early weak rail supervision help? | Isolates a taxonomy decision | Breaks standard Cityscapes mapping comparability | A dedicated mapping ablation |
| `reference_cityscapes19` | Does the implementation reproduce a standard task? | Literature-parity sanity check | Not a rail-transfer result | Validating the implementation before a sweep |

These names belong to the bundled research example. Your project can use any
stage and dataset names. A one-stage experiment is a normal curriculum; a later
stage uses `init_from: previous`; and a mixed stage lists several datasets with
explicit `sample_weights`.

### Sequential versus joint training

Sequential `cs_rs` trains all Cityscapes steps, writes a final checkpoint, then
starts RailSem19 from that state. It measures the effect of order and transfer.

Joint `joint_cs_rs` uses one mixed loader. The configured sample weights give
Cityscapes and RailSem19 equal draw probability even though their dataset sizes
differ. It measures whether the same data works just as well without a staged
handoff.

Neither is automatically better. They answer different experimental questions,
which is why both belong in the comparison.

For a mixed stage, the training loop validates on the first dataset listed in
the stage and scores only that dataset's active classes. Use
`segmentary-eval --dataset ...` after training to score every checkpoint on the
same cross-dataset split.

## 5. Stage initialization and head behavior

`init_from` has three meanings:

| Value | Meaning | Use it when |
|---|---|---|
| `pretrained` | Build the architecture from its configured pretrained source | First stage of a normal curriculum |
| `previous` | Load the preceding stage's final checkpoint | Continuing a staged curriculum |
| A checkpoint path | Load that exact file | A deliberately pinned restart or branch experiment |

The first stage cannot use `previous`, and a missing checkpoint is fatal.
Checkpoint loading is strict about missing and unexpected model parameters.

### Unified head

Keep `model.head: unified_head`. It is one classifier over the canonical label
space and works because active masks remove unsupervised classes from each
sample's loss.

The typed config reserves the literal `per_stage_head`, but the model factory
rejects it. Segmentary does not pretend to implement separate per-dataset heads.

### Optional classifier reset

Set `reset_head: true` on a stage to reinitialize the existing unified
classifier after loading the inherited model. The backbone still carries over.

| Choice | Advantage | Cost | Use it when |
|---|---|---|---|
| `reset_head: false` | Preserves learned canonical classifiers across stages | Can carry a classifier biased toward the earlier domain | Default staged transfer |
| `reset_head: true` | Tests transfer through features without classifier carryover | Throws away all learned classifier weights, including shared classes | A named head-reset ablation |

Resetting the head is an experimental variable, not a repair for a mismatched
label space. All stages in one experiment must still share the same canonical
output meaning.

For a separately named optimizer ablation, model-declared decoder/head groups
can use a different stage scale:

```yaml
reset_head: true
lr_scale: 0.1
head_group_lr_scale: 1.0
```

This is not classifier-only. The override applies to every path returned by the
model's `head_patterns()` contract, which commonly includes reused decoder
parameters as well as the reset classifier. Keep it out of an unchanged
published protocol unless that optimizer ablation is explicitly versioned.
The unreferenced
[`city_checkpoint_rs_head_group_lr_v1.yaml`](../../configs/campaigns/experiments/city_checkpoint_rs_head_group_lr_v1.yaml)
file is a concrete versioned example; the public campaign manifest does not use it.

## 6. Exact checkpoint handoff and EMA

At the end of every stage, Segmentary explicitly saves:

```text
runs/<experiment>_seed<seed>/<stage>/last.ckpt
```

`last.ckpt` is the state at the configured final optimizer step. It is always the
automatic handoff path for the next stage. This differs from `best.ckpt`, which
is selected by validation mIoU and may come from an earlier step.

The base config enables an exponential moving average (EMA) of model weights.
In-training validation uses EMA, and current checkpoints save the EMA shadow
alongside raw model and optimizer state. When a later stage says
`init_from: previous`, the handoff loader prefers the saved EMA weights, then
optionally resets the head. Legacy checkpoints without EMA fall back to their
raw state.

This yields two useful but different checkpoint choices:

- use `last.ckpt` for a fixed-step curriculum handoff;
- evaluate `best.ckpt --ema` for the validation-selected EMA model.

Do not silently substitute one for the other. Record the choice in the eval
command and result file.

## 7. Model tuning modes

Every model config has one of three backbone tuning modes:

| Mode | Advantage | Cost | Use it when |
|---|---|---|---|
| `full` | Maximum adaptation capacity; simplest interpretation | Highest memory and trainable-parameter count | Beginner default and main baselines |
| `frozen` | Cheapest; trains the head while keeping backbone parameters and normalization state fixed | Usually less domain adaptation | A label-efficiency or feature-quality control |
| `lora` | Adapts attention projections with fewer trainable parameters | Only applies to compatible attention backbones and adds target/rank choices | A parameter-efficient tuning arm for supported attention backbones |

Segmentary scopes LoRA to backbone attention projections, keeps the classifier
trainable, and raises if no modules match. Pure convolutional backbones such as
ResNet and ConvNeXt do not have the required attention projections for this
LoRA path.

**Beginner default:** use `full`. A tuning mode changes the research arm, not
just runtime performance.

## 8. What makes evaluation comparable

Segmentary training validation and standalone evaluation share the same core
protocol:

- validation images stay at native resolution;
- sliding windows default to `1024 x 1024` with `768 x 768` stride;
- mIoU, mean accuracy, pixel accuracy, per-class IoU, boundary metrics, and a
  confusion matrix are recorded;
- absent classes are excluded rather than scored as zero;
- TTA is off unless explicitly requested.

To compare two checkpoints, hold all of these constant:

1. canonical label space and taxonomy variant;
2. dataset root, split, and any split/group manifest;
3. sliding-window settings;
4. raw versus EMA weights;
5. TTA setting;
6. seed accounting and checkpoint-selection rule.

A higher number under a different class space or split is not evidence that the
model is better.

## 9. Reading the output record

Each completed training stage and standalone evaluation writes a strict JSON
object. Important fields are:

| Field | Why it matters |
|---|---|
| `name`, `stage`, `seed` | Identifies the experimental unit |
| `config`, `config_hash` | Shows exactly what settings were resolved |
| `git_sha`, `git_dirty` | Ties the result to source state |
| `dataset_sizes` | Catches accidental limits or wrong splits |
| `metrics` | Holds aggregate, per-class, boundary, and confusion data |
| `wall_clock_s`, `peak_vram_bytes` | Records resource cost |
| `env` | Captures the software and hardware context |
| `notes` | Records checkpoint and variant details for eval |

Non-finite values are serialized as JSON `null`, and writes are atomic so a
reader does not see a half-written file. Generate tables from these records with
`segmentary-table`; do not copy metrics by hand.

## 10. A practical decision sequence

For a new dataset or model arm, use this order:

1. Print and read the merged config.
2. Verify each real dataset and inspect overlays.
3. Run the eight-image memorization check with a small model.
4. Train one dataset and one stage as the baseline.
5. Evaluate an explicitly selected raw/EMA and best/final checkpoint.
6. Add another stage or mixed dataset only after each one-stage control works.
7. Add heavier models, tuning modes, taxonomy variants, and multiple seeds only
   after the controls are trustworthy.

This sequence keeps failures interpretable. Each step proves one additional
piece instead of changing the data, model, and curriculum at the same time.
