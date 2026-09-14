# Medical model training campaigns

The campaign runner queues explicit scratch experiments across available GPUs.
Each GPU trains one model at a time; after training it predicts the complete
validation partition and runs the native-volume evaluator. The runner then starts
the next queued model. No Slurm or root privileges are required.

First read the [model guide](medical-models.md) for scratch-only initialization,
physical preprocessing, objectives, supported architectures and model recipes.
Use a frozen source checkout and an audited dataset manifest with one immutable
group-safe split. Keep the 139 unannotated Task07 scans outside scored cohorts.
Task07 mass masks do not establish malignancy or pancreatic cancer diagnosis.

## Files and launch

The runner's JSON specification records `schema_version: 1`, `campaign_id`,
`source_root`, `source_commit`, `python`, `manifest`, `splits`, the explicit `gpus`
list, and `runs`. Each run needs a unique `id` and an absolute `config` recipe
path. Add `model`, `backend` and `comparison_group` for readable reporting.
Optional `evaluation` settings include `bootstrap_samples`, `seed` and
`surface_tolerance_mm`. Set a shared `comparison_group` only for experiments
intended for the same budget and endpoint. Keep the official nnU-Net training
schedule in a separate group from a fixed-step Torch screen.

```bash
python scripts/run_medical_campaign.py \
  --spec /data/project/campaign.json \
  --state-dir /data/project/campaign-state \
  --prepare-only

python scripts/run_medical_campaign.py \
  --spec /data/project/campaign.json \
  --state-dir /data/project/campaign-state
```

Run the second command in your persistent terminal session or process supervisor.
The state directory freezes the specification and resolved recipes. Each run's
state records its assigned GPU, active stage, stage log, timestamps, completion
artifacts and failures. Reusing the state directory resumes verified completed
stages; `--retry-failed` explicitly requests another attempt at failed work.
Do not change recipes or source inside an active campaign. A changed scientific
recipe needs a new run identity and workspace.

## Live dashboard

The medical runner and both RTIS campaign launchers automatically open the same
Textual dashboard in a detached tmux session. The shared UI provides a model
table, a focused model view, learning curves, GPU telemetry, and visible failures;
each data adapter supplies the metrics appropriate to its task. Medical views
show pancreas and mass Dice with their measurement scope instead of substituting
RTIS IoU values. This shares monitoring infrastructure without changing either
dataset's training recipe or evaluation protocol.

The launcher prints the exact `tmux attach -t ...` command. Default session names
include the state directory name and a hash of its full path, so two directories
with the same name do not collide. The session contains `training` and
`gpu-monitor` windows. Startup failures and nonzero dashboard exit status are
appended to `<state-dir>/service-logs/dashboard.log`; interactive output and
runtime traceback details stay in the tmux `training` pane. Re-running the launcher reuses its own
live dashboard and can revive its dead dashboard pane without signaling workers.
An unrelated or old untagged session is preserved under its existing name.

Use `--no-dashboard` on the campaign launcher to disable automatic startup.
Missing tmux or UI dependencies produce a diagnostic while training continues.
The dashboard needs Segmentary's ordinary `textual` and `tensorboard` dependencies
in the launcher interpreter; model backend interpreters remain isolated.

For a foreground dashboard, run:

```bash
python -m segmentary.progress /data/project/campaign-state
```

The same entrypoint accepts an RTIS campaign root and the older lane campaign
layout. For medical runs it accepts the actual `--state-dir` even when the spec
file lives elsewhere, using the embedded frozen specification in
`campaign-binding.json`. Launching a dashboard does not start training. Already
running campaigns retain their pinned source and continue unchanged; their
dashboard can be launched separately from a newer monitoring checkout.

## Generate the comparison pages

```bash
python scripts/report_medical_campaign.py \
  --campaign /data/project/campaign.json \
  --state-dir /data/project/campaign-state \
  --out docs/results/pancreas/task07/scratch-screen-20260913
```

The reporter reads JSON, never CT images, and does not publish scan identifiers,
server paths, checkpoint files or raw dataset manifests. It writes:

```text
scratch-screen-20260913/
  README.md             reading order, split counts and limitations
  comparison.md         every model, status, metric and ranking gate
  learning-curves.md    each recorded epoch and native validation point
  optimization.md       runtime changes, profiling scope and available measurements
  models/<run>.md       recipe, objective, memory, timing and final evaluation
  results.csv           spreadsheet-friendly aggregate rows
  status.json           aggregate evidence and compatibility decisions
```

Generate again to update the snapshot. Publication is a separate, authorized Git
operation; the reporting command does not commit or push. Keep periodic result
updates separate from model-source edits so an immutable training checkout stays
bound to its original source. Raw training artifacts remain on the server.

An optional `campaign-state/optimization.json` adds measured profile rows. Its
metadata records `measurement_scope`, `gpu_name`, `warmup_steps` and
`measured_steps`; `rows` contain model, status, precision, batch size, patch size,
training-step seconds and peak allocated/reserved bytes. Only publish values
actually measured with that stated scope.

## Decide what the results mean

The comparison shows live models in queue order, with the optimizer step of each
native validation measurement. It does not award a winner while other members
of the planned comparison group remain unfinished. Missing metrics stay blank;
failed work stays visible. An invalid result record blocks ranking.

A completed screening rank requires every planned group member to complete its
declared budget, have scratch-origin evidence, and cover the same native
validation cases and reference checksums under the same evaluation protocol,
source, split, seed, batch size and checkpoint selection. The ranking uses the
standalone evaluator's mean patient mass Dice, with both-empty references
excluded. In-training selection instead uses mean per-case mass Dice with
both-empty scored as one; those values are labeled separately.

Even a complete seed-0 screen cannot identify a clinical winner. Review anatomy
and mass failures, run additional seeds, tune with a predeclared budget, audit
patient/source overlap, and reserve the held-out test until the final choice is
frozen. Native 3D context differs from adjacent-slice 2.5D context, and query or
auxiliary objectives differ from dense Dice/CE. The comparison measures complete
configured pipelines, not the causal effect of architecture alone. Equal update
counts do not guarantee equal compute or equal tuning effort.
