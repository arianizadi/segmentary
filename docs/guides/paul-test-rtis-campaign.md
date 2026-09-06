# paul-test-rtis campaign

Start with the [dataset guide](../datasets/paul-test-rtis/README.md) and
[diagnostic results](../results/paul-test-rtis/README.md).

The existing `run_benchmark_campaign.py` is specifically the Cityscapes-only,
RailSem19-only, and Cityscapes → RailSem19 study. Its fixed protocol checks,
dataset roots, and generated model README sections are not a generic RTIS
runner. Its results now live in `docs/results/cityscapes-railsem19/`.

RTIS has its own design manifest, `configs/campaigns/paul-test-rtis.yaml`, and
preparation command, `scripts/plan_rtis_campaign.py`. The command writes configs
and an auditable plan; it has no worker launcher, publisher, or Git push path.

## The four RTIS arms

| ID | Initialization | New training |
| --- | --- | --- |
| `rtis_only` | Architecture's pretrained backbone, fresh RTIS head | RTIS train |
| `cityscapes_to_rtis` | Existing Cityscapes endpoint | RTIS train |
| `railsem19_to_rtis` | Existing RailSem19-only endpoint | RTIS train |
| `cityscapes_to_railsem19_to_rtis` | Existing Cityscapes → RailSem19 endpoint | RTIS train |

Reuse the existing source checkpoints rather than rerunning the original study.
Each transferred model resets its classifier: both RailUnion and RTIS have 21
channels, but their channel meanings differ. Equal tensor shape does not make
the heads compatible. The existing strict non-classifier warm-start loader is
used; it follows Segmentary's raw/EMA-safe initialization policy. The inference
diagnostics use raw weights and record that separately.

The initial preparation covers 36 distinct model recipes × 4 arms × seed 0 =
144 jobs. The compatibility alias is not another physical model. All 108 source
endpoint files were found on HDRFS. The planner checks paths and validates each
serialized config. It does not claim that every architecture has passed an RTIS
runtime check: only FPN-ResNet50 and SegFormer-B2 have been checked so far.

## Pilot settings

The manifest uses 4,000 RTIS optimizer steps per arm, effective batch 16
(batch 2 × accumulation 8), validation every 250 steps and periodic checkpoints every 500, and the existing
model-specific crop/objective settings. These are a reviewable starting budget,
not the original Cityscapes/RailSem19 study's 40k/20k protocol. Source pretraining
compute must be reported separately from new RTIS compute. Transfer arms use
0.1× backbone LR and 1× head-group LR; the pretrained-backbone baseline uses
its model recipe's full rates.

Before a full comparison: confirm original recording groups, review the small
validation set's missing classes, freeze the split and source revision, verify
every source checkpoint hash, and run architecture admission checks. Inspect
native class/anomaly results, not the coarse cross-dataset diagnostic score.
Evaluate test only after model/protocol selection. More seeds would be needed
to quantify variation beyond a single descriptive run.

## Prepared files on HDRFS

```text
/data/izadia1/datasets/paul-test-rtis/
/data/izadia1/projects/segmentary-runs/paul-test-rtis/
  diagnostics/       # inference, tiny overfit logs, source checkpoint inventory
  campaign-plan/
    plan.json       # 144 planned jobs, split/config hashes, no publisher
    configs/        # one resolved configuration per job
```

Regenerate into a new directory from the HDRFS checkout:

```bash
python scripts/plan_rtis_campaign.py \
  --checkpoints /data/izadia1/projects/segmentary-runs/paul-test-rtis/diagnostics/all-source-checkpoints.json \
  --dataset-root /data/izadia1/datasets/paul-test-rtis \
  --out /path/to/new/rtis-plan
```

## Historical preparation status

At preparation time, HDRFS had no campaign/publisher process, no tmux server,
no user crontab, and no user systemd timers. The old campaign's recorded publisher
worktree `/data/izadia1/projects/segmentary-publisher-v4` no longer exists. The
bounded diagnostic sessions exited after their checks; no RTIS campaign or
publisher was launched. Historical campaign manifests remain intact.

The old runner/importer and their tests now target only the explicitly named
Cityscapes/RailSem19 report. RTIS reports and future run outputs occupy their
own directories. No results were committed or pushed automatically.

## Running the authorized pilot

Launched on HDRFS on 2026-09-06 UTC. Follow the [live report](../results/paul-test-rtis/live/README.md).
The active campaign directory is `/data/izadia1/projects/segmentary-runs/paul-test-rtis/pilot-20260906/`.

`scripts/run_rtis_campaign.py` now provides the RTIS runtime. Use a clean,
fixed-revision training worktree and a **different** clean publisher worktree
tracking GitHub `main`. The historical Cityscapes/RailSem19 runner is not started.
The runtime verifies all 108 source checkpoint hashes, all 307 image/mask hashes,
the split, and resolved configurations before initializing the queue. Two data
loader workers per run limit contention across the ten GPUs.

```bash
# First generate a new plan with the preparation command above.
python scripts/run_rtis_campaign.py init --campaign /path/to/new/rtis-plan
python scripts/run_rtis_campaign.py launch --campaign /path/to/new/rtis-plan \
  --checkout /path/to/separate/publisher --gpus 0,1,2,3,4,5,6,7,8,9
```

The launcher starts independent tmux workers and a publisher. Each GPU claims
one job at a time. The queue covers 36 recipes and all four arms, with a maximum of 4,000
optimizer steps per job. Validation runs every 250 steps. After three validation
checks without at least 0.002 mIoU improvement (0.2 percentage points), training
stops and the best validation checkpoint is evaluated. The final step and
stopping reason are reported; early stopping is a successful outcome. Incompatible or failed runs are reported as failed;
settings are not silently changed to obtain a score. Existing model weights
must be cached: workers use offline Hugging Face loading.

Each successful job validates its best checkpoint on all 37 validation images
with the model's configured inference geometry, no TTA, and the repository's
raw/EMA-safe weight policy. The final checkpoint's training-time validation
record is also retained. Test is held out. Original recording groups remain
provisional, and validation lacks three classes, so this is a descriptive pilot.

The publisher checks every 30 seconds and commits changed results to
[`docs/results/paul-test-rtis/live/`](../results/paul-test-rtis/live/README.md).
Only its README and status JSON are staged. It follows upstream changes without
editing the training checkout or historical reports; conflicts stop publishing
and are logged for review. Report-only pushes skip the expensive code CI suite;
code changes continue to run all checks.

After training and best-checkpoint evaluation succeed, checkpoint hashes and
results are written durably. Only then are that run's `step-*.ckpt` snapshots
removed, with byte counts, hashes and deletion outcomes under `cleanup/`.
Best and final full-state checkpoints remain. Failed/interrupted runs retain
all recovery snapshots. Historical source checkpoints are never cleaned by this
runner. During training, at most eight periodic snapshots accumulate per job.

`state/` has job outcomes, `logs/` has model output, `service-logs/` has worker
and publisher output, `services.json` lists tmux sessions, and
`publisher-status.json` records the last successful GitHub commit. Add `STOP`
to the campaign directory to drain workers after current jobs; add
`STOP_PUBLISHER` to stop publishing. These files are not created by default.
An interrupted worker can be restarted with `worker --campaign ... --gpu N`;
job/GPU locks prevent duplicate work and full optimizer/scheduler/EMA state is
resumed from the newest readable recovery snapshot. Failed jobs require review
before their state is explicitly requeued.


## Overfitting controls

The 4,000-step budget is a ceiling, not a requirement to keep fitting a small
training set. Validation-based early stopping uses the same rule for every
model and initialization path. Reports include the actual step count, best
checkpoint step, stopping reason, training-loss curve and validation-mIoU curve.
The best checkpoint is retained even when later training degrades validation.
Existing random crops, scale changes, flips, color augmentation and weight decay
remain enabled according to each model recipe.

Early stopping reduces wasted training and selection of overfit final weights;
it cannot prove generalization. The 37 validation images represent only three
provisional scene groups. Repeated comparison of 144 runs can itself overfit
model selection to validation. Keep the 50 test images sealed until selecting a
small number of finalists, and confirm original recording identities before
claiming independent-video performance. Validation also lacks three classes,
so its overall score cannot establish performance on those classes.

The guard was added after launch at the user's request. Running jobs are paused
at their first saved validation checkpoint and resumed with full training state.
The campaign amendment records old/new code and configuration hashes and resume
steps; initial training is not discarded or presented as a fresh run.

Guarded runs save best checkpoints and periodic recovery snapshots during training, and write the final `last.ckpt` once at termination. This avoids writing a duplicate multi-gigabyte last checkpoint at every validation improvement.
