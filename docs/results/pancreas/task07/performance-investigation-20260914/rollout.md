# Optimized pipeline deployment

Deployment began **2026-09-14 04:49:04 UTC** (September 13 evening Pacific).
All 27 Torch models had finished their original 10,000-update training budgets,
native validation prediction and evaluation. The continuation repeats prediction
and evaluation using those selected checkpoints; it does not add training steps.
nnU-Net remains on its original source and 250,000-update schedule on GPU 0.

## Code, checks and preserved state

The deployed source is `86363b101aa3685782defdf524face6af43edb2d`, a clean,
immutable HDRFS checkout. Its [GitHub Actions checks passed](https://github.com/arianizadi/segmentary/actions/runs/34806697397).
Implementation and evidence are described in [reviewed-fixes.md](reviewed-fixes.md).
The original source remains `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

All 27 continuation imports completed successfully before launch. They retain
model, optimizer, scheduler, scaler, RNG, epoch, step and checkpoint-selection
state, with exact original checkpoint bytes and explicit source lineage.
The same manifest, split, runtime, recipes and GPU assignments are bound to the
new workspaces. Normal preprocessing runs under the new source identity before
prediction. The train stage verifies the completed state and skips updates.

The new pipeline records per-case preparation, model pipeline, reconstruction and
export times, total prediction wall time, cache activity, continuous mass scores,
voxel counts and CUDA allocator peaks. These cannot be retroactively recovered
from an old run that did not record them. Simultaneous component times overlap;
their sum is not elapsed wall time.

## Where to look

- [Original all-model comparison](../scratch-screen-20260913/README.md): 27 completed Torch models and the continuing nnU-Net run.
- [Continuation comparison](../performance-continuation-20260914/README.md): the same 27 Torch checkpoints undergoing optimized prediction and evaluation, with parent training retained explicitly.
- [Training cost](../scratch-screen-20260913/training-cost.md): epoch phases, invocation cost and available resource records.
- [Inference benchmarks](../scratch-screen-20260913/inference.md): all 27 completed Torch models, each with 10 warmups and 50 retained CUDA-event samples. These are batch-one declared-input benchmarks, separate from CT throughput.
- [Detection metrics](../scratch-screen-20260913/clinical-metrics.md): all 27 complete 42-case native-mask diagnostics with a fixed localization protocol.
- [Checkpoint retention](checkpoint-retention.md): no unreferenced medical intermediate generations existed at the audit. Best and latest remain useful, and final shares the latest file.

The original publisher first released the expanded report in commit `ce8e92ff`;
all 335 relative links passed and the output contained no raw case identifiers or
private server paths. Published model records and CSV files preserve numerical
evidence. The new campaign has a separate report identity; it is a continuation
of the same seed and checkpoints, not another independent experiment.

## HDRFS operation

Campaign: `task07-performance-continuation-20260914`, under
`/data/izadia1/projects/segmentary-runs/pancreas/`.
The normal scheduler runs the original assignments on GPUs 1–9, with the recorded
`pancreas-campaign-20260913` Python environment. No Slurm, sudo, new weights or
training-recipe changes are involved.

```bash
tmux attach -t state-controller-4937f287ad
```

The view launches automatically with the normal campaign runner and displays
prediction progress. The computation launcher is `pancreas-performance-20260914`.
Runner logs/status are in the campaign's `service-logs`; dashboard/cleanup logs
are in `state/service-logs`. Owned, unchanged dashboard panes close after all
prediction and evaluation stages complete. Failed/interrupted runs retain their
view for diagnosis; user-added or repurposed panes are preserved.

## What remains a measurement question

The two-training-CT U-Net check had identical native labels and a 2.75× warm-path
speedup in its limited timing scope. It is not an all-model speed claim. A
separate CPU-only comparison checks the old and new selected checkpoint state,
prediction hashes, decoded native masks, geometry, Dice and scoped prediction
time for each completed continuation. Aggregate results require full coverage;
incomplete, failed or differing outputs must remain visible.

P-Sen here is a dataset-case/group proxy and T-Sen uses connected-component lesion
proxies. All 42 validation scans have annotated masses, so specificity and ROC
AUC remain unavailable. Continuous scores do not create the missing negative
reference class. These diagnostics are not an official PanTS leaderboard
reproduction or a claim of clinical cancer detection.
