# Getting started

This tutorial builds one complete semantic-segmentation project from paired
images and masks. It begins with safe, cheap checks and ends with an evaluated
checkpoint and a provenance-rich result record.

You need an installed Segmentary environment from [Installation](installation.md).
Training is practical on a GPU; project creation, config validation, and data
verification can run on CPU.

## 1. Create a portable project

Run this from a parent directory outside the cloned Segmentary source tree:

```bash
segmentary-init my-segmentation-project --name first_run
cd my-segmentation-project
git init
git add .
git commit -m "Initialize Segmentary project"
find . -maxdepth 3 -type f | sort
```

The starter contains:

```text
base.yaml                         optimization, augmentation, evaluation
model.yaml                        model/checkpoint/tuning choice
experiment.yaml                   label space, data, and stage order
taxonomy/example/canonical.yaml   output classes
taxonomy/example/my_dataset.yaml  native mask ID -> output class ID
```

Segmentary merges the three YAML files left to right. Keeping concerns in separate
layers makes it easy to compare models or curricula without copying an entire
config.

## 2. Arrange paired data

The starter expects:

```text
data/
  images/train/frame_001.jpg
  images/train/frame_002.jpg
  images/val/frame_101.jpg
  masks/train/frame_001.png
  masks/train/frame_002.png
  masks/val/frame_101.png
```

Rules:

- an image and mask share the same relative path and stem;
- the mask is a single-channel integer image (`L`, palette-index `P`, or integer
  PIL mode), not an RGB visualization;
- each pixel is a native class ID;
- `255` means ignore;
- image and mask dimensions match;
- train and validation contain different samples.

PNG/JPEG/TIFF/BMP/WebP images are recognized by default. Masks default to PNG.
Nested folders work. The [custom-data guide](../guides/custom-data.md) shows how
to change directories/extensions and how to prevent video-frame leakage.

## 3. Define what the model predicts

Edit `taxonomy/example/canonical.yaml`. Class IDs must be contiguous from zero:

```yaml
name: example
description: Classes predicted by this project.
ignore_index: 255
classes:
  - {id: 0, name: background, color: [0, 0, 0]}
  - {id: 1, name: object, color: [0, 160, 255]}
  - {id: 2, name: detail, color: [255, 180, 0]}
thin_classes: [2]
```

Then edit `taxonomy/example/my_dataset.yaml` so every native mask ID has an
intentional meaning:

```yaml
space: example
dataset: my_dataset
source: Annotation format name and version.
default: 255
map:
  0: 0
  1: 1
  2: 2
```

The left side is the ID stored in your mask. The right side is the canonical ID
from `canonical.yaml`. Unlisted values become ignore. If several native IDs map
to one class, add `allow_merge` with a written reason; otherwise validation
rejects the silent information collapse.

Why separate files? Two datasets may call the same concept by different IDs, or
one may have a coarser taxonomy. Both can still train one classifier when their
mappings resolve into one explicit canonical space.

## 4. Validate the merged config

```bash
segmentary-train base.yaml model.yaml experiment.yaml --print-config > resolved.json
python -m json.tool resolved.json >/dev/null
```

This step does not download weights, open the dataset, or reserve a GPU. It
checks required fields, types, unknown keys, stage order, schedules, and unsafe
setting combinations.

Commit the intended configuration and taxonomy before verification or training:

```bash
git add base.yaml model.yaml experiment.yaml taxonomy
git commit -m "Configure first segmentation baseline"
git status --short
```

The last command should print nothing. The starter ignores `data/`, `runs/`,
checkpoints, `debug/`, and `resolved.json`, so generated artifacts do not make
the recorded project provenance dirty.

Important values in the starter:

- top-level `space: example` is required;
- the data's logical `name` is `my_dataset`;
- `loader: folder` chooses the generic paired-folder implementation;
- `mapping: my_dataset` chooses the mapping filename stem;
- `model.arch: hf_auto` loads a complete standard Hugging Face segmentation
  checkpoint;
- the first stage uses `init_from: pretrained`.

An unknown key is fatal. Fix it; do not remove validation to make a typo run.

## 5. Verify real masks and inspect overlays

```bash
segmentary-verify \
  --dataset my_dataset \
  --loader folder \
  --mapping my_dataset \
  --root data \
  --space example \
  --taxonomy taxonomy \
  --split train \
  --crop 512 512 \
  --out debug/verify
```

The command checks native ID coverage, canonical IDs after augmentation, image
and mask pairing, ignore padding, and class frequencies. It writes colored
overlays.

Open the PNGs. Check:

- boundaries align with the image;
- colors mean the expected classes;
- horizontal flips and crops transform image/mask together;
- magenta ignore hatching appears only where intended;
- rare and thin objects are still present;
- no palette/RGB conversion changed integer IDs.

A passing script cannot see that “class 1” was semantically mislabeled. Visual
inspection is part of verification.

## 6. Prove the pipeline can memorize a few images

```bash
segmentary-overfit base.yaml model.yaml experiment.yaml \
  --images 8 \
  --iters 400 \
  --target 0.95 \
  --crop 512 512 \
  --device cuda:0
```

This intentionally removes ordinary augmentation and uses a high learning rate.
The goal is not generalization; it is to prove data, labels, model output, loss,
active masks, optimizer, and gradients connect end to end.

If it cannot memorize a representative tiny set, do not launch a long run. Read
[Interpreting results and debugging](interpreting-results.md) and
[Troubleshooting](../guides/troubleshooting.md). If your eight images do not
contain every class, the maximum macro score can be unstable; choose a small set
that covers the classes you expect to learn.

## 7. Choose the first training budget

The generated `base.yaml` is a starter, not a universal recipe. Before training,
set:

- `aug.crop` and evaluation window/stride appropriate for image resolution;
- per-device `train.batch_size` that fits;
- `train.accum` for the intended effective batch;
- `train.iters`, `val_every`, and `ckpt_every` for dataset size and budget;
- `train.precision` supported by the hardware;
- `model.checkpoint` and optional immutable Hub `revision`.

Print the config again after changes. For a two-minute smoke, override the
resolved values without editing YAML:

```bash
segmentary-train base.yaml model.yaml experiment.yaml \
  --seed 0 --devices 1 \
  --set train.iters=2 \
  --set train.val_every=2 \
  --set train.ckpt_every=2 \
  --set train.num_workers=0 \
  --set aug.crop='[128,128]'
```

That proves the trainer/checkpoint path but is not a benchmark.

## 8. Run the real baseline

```bash
segmentary-train base.yaml model.yaml experiment.yaml --seed 0 --devices 1
```

Segmentary writes:

```text
runs/first_run_seed0/
  train_my_data/
    best.ckpt
    last.ckpt
    step-00000100.ckpt
    step-00000200.ckpt
    ...
    results.json
    lightning_logs/
      version_0/
        events.out.tfevents.*
```

`last.ckpt` is explicitly saved after the trainer reaches its final configured
step and includes optimizer/scheduler and EMA state. `best.ckpt` is selected by
observed validation mIoU. Do not assume they represent the same step or selection
policy.

Every `train.ckpt_every` optimizer steps, Segmentary also writes and retains a full
`step-XXXXXXXX.ckpt` recovery snapshot. These improve recovery choices but can
consume substantial storage; use a larger cadence for big models while keeping
`best.ckpt` and the explicit true-final `last.ckpt` semantics unchanged.

`results.json` includes the resolved config, config hash, Git SHA/dirty state,
seed, environment, dataset sizes, metrics, wall time, and peak VRAM. Preserve it
with the checkpoint.

## 9. Evaluate an exact artifact

Use the same config layers and state clearly whether you select EMA:

```bash
segmentary-eval base.yaml model.yaml experiment.yaml \
  --ckpt runs/first_run_seed0/train_my_data/last.ckpt \
  --seed 0 \
  --ema \
  --device cuda:0 \
  --out runs/first_run_seed0/eval_my_dataset_val/results.json
```

The evaluator uses the configured validation split, active classes, native
resolution, sliding window, boundary tolerance, and confusion-matrix policy. Use
`--limit 4` only as a load/forward smoke; its metric is not comparable with the
full validation split.

Read [Interpreting results](interpreting-results.md) before deciding whether a
number is good. Accuracy-like values use `0–1`; multiply by 100 for percent.
`null` is unscored/absent, while zero is a scored failure.

## 10. Move beyond the baseline

Change one thing at a time:

- a larger/smaller model or another complete `hf_auto` checkpoint;
- `tuning: frozen`, `lora`, or `full`;
- an auxiliary loss;
- an augmentation or optimizer setting;
- another seed;
- another dataset stage with `init_from: previous`;
- a mixed stage with explicit sampling weights;
- common evaluation of all candidates on the same target split.

For a serious comparison, run at least three seeds and use the checked table
builder rather than copying metrics by hand:

```bash
segmentary-table \
  --runs runs --out reports/first_run
```

The table builder discovers only `**/results.json` below `--runs`. Give every
explicit evaluation its own directory ending in `results.json`; other JSON
filenames are intentionally ignored. Once you have several unrelated campaigns,
give each one a separate `output_root` and point `--runs` at only the campaign
you intend to aggregate.

## Common first-run failures

**`taxonomy file not found`**

Run from the project directory or set `taxonomy_root` to the correct directory.
Both `space` and the dataset's `mapping` stem must exist there.

**No samples found**

Check `root`, `train_split`/`val_split`, folder names, extensions, recursive
layout, and one-to-one stems. Use advanced `loader_options` only for real layout
differences.

**Mask mode is RGB**

Use an integer-index mask, not a color rendering. Convert colors to IDs once and
audit the conversion.

**Pretrained load is rejected**

`hf_auto` requires a complete standard semantic-segmentation checkpoint. It
allows a label-count change only at the final classifier. An encoder-only model,
discarded auxiliary head, remote-code model, or partially matching checkpoint
must use a compatible built-in/custom integration rather than weakening the
load audit.

**CUDA out of memory**

Lower per-device `train.batch_size`, use accumulation to preserve effective
batch, reduce crop size if scientifically acceptable, choose a smaller model, or
use LoRA/frozen tuning. Record every change.

**mIoU looks high but small classes fail**

Inspect per-class IoU/support, confusion, and boundary precision/recall. Pixel
accuracy is dominated by frequent pixels.

Next: [Core concepts](core-concepts.md).
