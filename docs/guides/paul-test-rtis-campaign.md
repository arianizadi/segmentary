# paul-test-rtis campaign preparation

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

## Proposed pilot settings

The manifest proposes 4,000 RTIS optimizer steps per arm, effective batch 16
(batch 2 × accumulation 8), validation/checkpoint cadence 500, and the existing
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

## Publisher status

At preparation time, HDRFS had no campaign/publisher process, no tmux server,
no user crontab, and no user systemd timers. The old campaign's recorded publisher
worktree `/data/izadia1/projects/segmentary-publisher-v4` no longer exists. The
bounded diagnostic sessions exited after their checks; no RTIS campaign or
publisher was launched. Historical campaign manifests remain intact.

The old runner/importer and their tests now target only the explicitly named
Cityscapes/RailSem19 report. RTIS reports and future run outputs occupy their
own directories. No results were committed or pushed automatically.
