# Command-line reference

An installed package exposes ten commands. From a source checkout, the module
forms (`python -m segmentary.train`, for example) are equivalent for train/eval/
export; compatibility wrappers for repository helpers remain under `scripts/`.

## Watch live training

```bash
segmentary-progress runs/my_campaign --timezone America/Los_Angeles
```

This opens a read-only Rich terminal dashboard over an existing queued
campaign. It combines every `lane_*_status.json` file with the TensorBoard
scalar stream and, when available, `nvidia-smi` and tmux health. The display
shows:

- completed, active, and queued jobs in each lane;
- the actual active stage and optimizer step, with a progress bar;
- training loss, learning rate, validation mIoU, boundary F1, and measured
  optimizer-step throughput;
- current-stage, lane, and campaign completion estimates; and
- per-GPU utilization, memory, and temperature.

The command never loads a checkpoint or model, reserves a GPU, changes a run
file, or sends a signal to training. Ctrl-C stops only the dashboard. Use
`--once` for a normal printable status snapshot, `--refresh SECONDS` to change
the live cadence, `--no-gpus` on a non-NVIDIA host, and `--tmux-prefix PREFIX`
when lane sessions do not use the default `segmentary-m5-a`/`-b` names.

Training scalars normally update at `log_every_n_steps`, whereas validation
metrics update only at `val_every`. The dashboard labels both steps so an older
validation value is never presented as if it came from the newest training
iteration. Its ETA is an estimate based on measured stage throughput and
completed jobs of the same curriculum, not a scheduler guarantee.

## List and probe models

```bash
segmentary-models list [--config-dir PATH] [--json] [--output PATH]
segmentary-models probe CONFIG [CONFIG ...] [options]
```

`list` type-checks and summarizes installed model YAMLs without building them.
`probe` composes a normal experiment, derives the class count from its taxonomy,
builds the exact first-stage model, validates preprocessing and two non-square
shapes, then runs the configured production dense or Hungarian query objective,
backward, gradient audit, and AdamW step on synthetic tensors. Query probes also
validate raw class/mask outputs while preserving the public dense evaluation
contract. It never opens dataset roots and its output is compatibility evidence,
not an accuracy or latency result.

Probe options include repeatable `--shape HxW` (at least two), `--batch-size`,
`--steps`, exact `--device`, `--precision {auto,fp32,bf16}`, `--seed`, repeatable
`--set KEY=VALUE`, `--json`, and `--output`. Dense/query or task mismatches,
fixed-size failures, invalid normalization, missing/non-finite gradients, or a
classifier/head that does not change return nonzero. See [Model catalog and
compatibility probe](../guides/model-catalog-and-probe.md) for the record fields,
failure guide, advanced examples, and opt-in all-native GPU acceptance.

## Initialize a project

```bash
segmentary-init DESTINATION [--name NAME]
```

Creates a complete starter in a new or empty directory: base/model/experiment
YAML, example taxonomy/mapping, README, and `.gitignore`. It refuses a non-empty
destination.

## Verify data

```bash
segmentary-verify --dataset NAME --root PATH --space SPACE [options]
```

| Option | Purpose |
|---|---|
| `--loader ID` | built-in loader (`folder`, `cityscapes`, etc.) or `package.module:Class` |
| `--mapping STEM` | taxonomy mapping stem; defaults to dataset name |
| `--loader-options JSON` | loader-specific JSON object |
| `--taxonomy PATH` | taxonomy root (default `taxonomy`) |
| `--split NAME`, `--split-file PATH` | selected split/manifest |
| `--variant NAME` | mapping variant |
| `--out PATH` | overlay output directory |
| `--n-overlays`, `--n-scan` | visual and native-ID scan counts |
| `--crop H W`, `--seed N` | deterministic augmentation preview |

Example:

```bash
segmentary-verify \
  --dataset my_dataset --loader folder --mapping my_dataset \
  --root data --space my_space --taxonomy taxonomy \
  --loader-options '{"recursive":true}'
```

## Tiny memorization check

```bash
segmentary-overfit CONFIG [CONFIG ...] [options]
```

| Option | Default | Purpose |
|---|---:|---|
| `--images N` | 8 | first N training images |
| `--iters N` | 400 | maximum optimization steps |
| `--target X` | 0.95 | pass threshold on the tiny training set |
| `--lr X` | `6e-4` | deliberately high diagnostic LR |
| `--crop H W` | 512 512 | fixed diagnostic crop |
| `--seed N` | 0 | diagnostic seed |
| `--device DEVICE` | `cuda:0` | compute device (falls back to CPU if CUDA unavailable) |

This diagnostic uses the selected model's configured tuning mode and the same
CE/auxiliary-loss composition as training. That makes it a check of the actual
pipeline, not a hidden full-fine-tuning substitute.

## Train

```bash
segmentary-train CONFIG [CONFIG ...] [options]
```

| Option | Purpose |
|---|---|
| positional configs | merge YAML files left to right |
| `--seed N` | override `train.seed` |
| `--devices auto\|N\|0,1,...` | Lightning execution devices |
| `--name NAME` | override experiment name/output identity |
| `--set KEY=VALUE` | repeatable dotted override; JSON scalars/lists parsed |
| `--deterministic` | deterministic kernels, usually lower throughput |
| `--print-config` | validate and print one JSON document without opening model/data |

Mirror an execution-only `--devices` choice into `train.devices` when you want
that choice represented in the embedded resolved config.

## Evaluate

```bash
segmentary-eval CONFIG [CONFIG ...] --ckpt PATH [options]
```

| Option | Purpose |
|---|---|
| `--ckpt PATH` | required Lightning/raw checkpoint |
| `--seed N`, `--set KEY=VALUE` | override the record config before hashing |
| `--stage NAME` | choose configured stage data (default last) |
| `--dataset NAME --root PATH` | score an override dataset |
| `--loader ID` | loader ID or `package.module:Class` for override data |
| `--mapping STEM` | taxonomy mapping stem for override data |
| `--loader-options JSON` | override-loader options as a JSON object |
| `--split-file PATH` | optional explicit split/group manifest |
| `--split NAME`, `--variant NAME` | split/mapping variant |
| `--ema` | load saved EMA shadow instead of raw weights |
| `--tta --scales ...` | opt-in multi-scale plus flip variant |
| `--num-workers N` | override `eval.num_workers`; use `0` for an in-process custom loader |
| `--out PATH` | explicit result JSON path |
| `--device cuda:0\|cpu` | evaluation device |
| `--limit N` | positive first-N smoke limit; not a full benchmark |

`--dataset` requires `--root`. Loader/mapping/manifest override options also
require `--dataset`; otherwise use `--stage` and the configured data entry.

Generic override example:

```bash
segmentary-eval base.yaml model.yaml experiment.yaml \
  --ckpt runs/baseline_seed0/train/last.ckpt --ema \
  --dataset common_target --root data/common \
  --loader folder --mapping common_schema \
  --loader-options '{"image_dir":"rgb/{split}","mask_dir":"labels/{split}"}' \
  --split val --seed 0 --out runs/common_target_seed0/results.json
```

## Export

```bash
segmentary-export CONFIG [CONFIG ...] --ckpt PATH [options]
```

The current export command is intentionally narrower than training/evaluation:
it supports the validated static-shape dense deployment arms and its dataset
benchmark path is the bundled Cityscapes acceptance profile. Read
[Export and deployment](../guides/export-and-deployment.md) for supported
architectures/backends, calibration, parity, and limitations. Do not assume an
arbitrary `hf_auto` model is export-verified merely because it trains.

Important advanced flags are `--shape H W`, `--ema`, `--backends`,
`--calibration-samples`, `--eval-samples`, `--warmup`, `--iterations`,
`--workspace-gib`, `--opset`, and `--onnx-rtol/--onnx-atol`. If the task head is
not trained, pass `--untrained-test-only`; every generated record will then say
that absolute mIoU is not model-quality evidence. `--int8-exclude-node NAME` is
a repeatable, last-resort mixed-precision control for a specifically diagnosed
TensorRT tactic failure. Record every excluded node and inspect the reported
engine precision counts.

## Create a group-safe split

Installed command (with a source-checkout compatibility wrapper):

```bash
segmentary-make-split \
  --images IMAGE_DIR --masks MASK_DIR --out-root NEW_DATASET_DIR \
  --groups GROUPS_JSON
```

Or derive a group from each stem with `--group-regex`. Options include `--seed`,
`--val-frac`, `--test-frac`, and `--materialize
{symlink,hardlink,copy}`. Existing output roots are refused.

## Generate checked result tables

Installed command (with a source-checkout compatibility wrapper):

```bash
segmentary-table --runs DIR --out DIR \
  [--stage EXACT_STAGE] [--experiment NAME] [--classes CLASS ...]
```

Writes `results.csv` and `results.md`, aggregating mIoU, mean class accuracy,
pixel accuracy, boundary F1, and any requested per-class IoUs as percentages.
It exits on malformed records, duplicate seeds, incompatible configs/provenance,
or partial optional metric groups rather than silently creating a misleading
table. Discovery is deliberately limited to `**/results.json` below `--runs`;
put each intended evaluation record in its own directory with that exact
filename.

Repeat `--stage` or `--experiment` to include several exact values. Filtering
happens only after every discovered record passes schema, hash, metric, and
provenance validation, so a malformed run cannot disappear from a plausible
filtered report. For a campaign that evaluates every arm on one common
endpoint:

```bash
segmentary-table \
  --runs runs/my_campaign \
  --out reports/my_campaign_common \
  --stage eval:my_dataset:val
```
