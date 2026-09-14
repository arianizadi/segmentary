# Shared training progress

`segmentary-progress` opens the same interactive table, filters, run details and
responsive curves for RTIS and medical campaigns. Backend adapters translate the
existing telemetry and preserve the meaning of each metric. The UI only observes
training: opening, closing or detaching it does not start or stop GPU workers.

```bash
segmentary-progress /path/to/campaign
# Equivalent, including from a source checkout:
PYTHONPATH=src python -m segmentary.progress /path/to/campaign
# A complete textual snapshot for logs or remote checks:
segmentary-progress /path/to/campaign --once --no-gpus
```

Detection supports the ordinary medical campaign directory, an arbitrary medical
state directory containing `campaign-binding.json`, and the existing RTIS layout.
`--backend medical` or `--backend rtis` chooses an adapter explicitly. Older lane
campaigns retain their existing compact monitor. The old
`python -m segmentary.rtis_progress ...` command remains compatible and now uses
the shared interactive component.

## Controls

| Key | Action |
| --- | --- |
| Up / Down | Select a model |
| Enter | Open its recorded curves and metrics |
| Esc | Return to the overview |
| A / T / C / Q / F | Show all / active / complete / queued / failed runs |
| Shift + Left / Right | Scroll wide tables horizontally |
| R | Refresh |
| Ctrl+B, then D | Detach from tmux while training continues |

All models remain available, including completed, queued and failed models. The
UI adapts to small terminals; rows and wide tables scroll. It refreshes RTIS
telemetry every three seconds and medical telemetry every ten seconds. Immutable
medical epoch JSON is cached by filesystem signature. A failed read leaves a
clearly marked stale snapshot until a subsequent successful read, including while
switching filters or viewing details.

## Medical scores

The columns include current optimizer progress or validation-case progress,
mass Dice, pancreas Dice, the score's basis, its validation step and scan coverage.
Only a completed validation of the entire frozen native-volume cohort supplies
in-training Dice. Partial evaluation never substitutes for complete coverage.

- **Native:** latest completed in-training full-volume validation. The campaign
  counts a reference-empty, prediction-empty mass case as Dice 1.
- **Final:** selected-checkpoint evaluation after training. This evaluator uses
  reference-positive patient means, excluding both-empty mass cases. Its scoring
  population differs from the in-training calculation.
- **Pending / —:** unavailable; this never means zero.

nnU-Net's patch-level pseudo-Dice appears in a separate summary and its detailed
metric table. Its pancreas class excludes mass, while the native pancreas score
uses the pancreas-plus-mass union. Patch pseudo-Dice never enters the full-volume
Dice columns or charts. Different training stages, objectives and budgets prevent
this progress display from being an architecture ranking.

Training ETA uses observed training elapsed time, including previous periodic
validation for Torch, or recent completed-epoch durations for nnU-Net. It excludes
later final prediction/evaluation and is unavailable for queued runs. Epoch
completion is read from nnU-Net's completed epoch timing record, not its next
epoch's start message.

## Automatic startup and the current HDRFS view

The campaign launchers start the shared tmux dashboard automatically after
initializing campaign state. `--no-dashboard` disables it. Missing UI dependencies
or tmux produce a diagnostic without blocking training. The shared helper reuses
owned sessions, avoids changing unrelated sessions, and never signals workers.

The current Task07 campaign's display is:

```bash
ssh HDRFS
tmux attach -t pancreas-fullstats-controller
```

Its `training` window shows this shared UI; its `gpu-monitor` window shows
`nvidia-smi`. The actual frozen training controller remains in
`pancreas-scratch-20260913`; the dashboard is a separate observer, not a second
training controller. It runs from the isolated UI snapshot at
`/data/izadia1/projects/segmentary-progress-ui-20260914`, using the existing
`rtis-viewer` environment. Training source, recipes, runtimes and checkpoints were
not changed to add this display.

Implementation:

- `src/segmentary/campaign_progress.py`: common interactive renderer and controls.
- `src/segmentary/rtis_progress.py`: RTIS telemetry and metric profile, plus the
  compatible historical command.
- `src/segmentary/medical_progress.py`: medical report/epoch telemetry and its
  metric profile; no torch/model/checkpoint loading.
- `src/segmentary/campaign_dashboard.py`: shared automatic tmux launcher.
- `src/segmentary/progress.py`: common command and adapter detection.

### Automatic cleanup after completion

Campaign launchers automatically start a lightweight cleanup watcher alongside
both RTIS and medical dashboards. Within 30 seconds after every planned job
successfully finishes (including prediction, evaluation, and RTIS collection),
it closes the generated training view and GPU-monitor panes. An empty tmux
session then disappears automatically. Logs, reports, and checkpoints stay on disk.

Failed, interrupted, queued, or unreadable campaign states keep their views.
The watcher targets individually registered panes and checks their original
commands; user-added panes/windows and unrelated sessions survive. Existing
untagged legacy panes are not automatically adopted. Manually opening
`segmentary-progress` does not enable cleanup, so you can review finished results.
Cleanup events are recorded in `service-logs/dashboard-cleanup.log`.
