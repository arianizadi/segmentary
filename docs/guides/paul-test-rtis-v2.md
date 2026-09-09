# RTIS v2: remove the disputed CVAT import

`paul-test-rtis_v2` excludes `no_anomalies_0251.png` through
`no_anomalies_0265.png`, including their masks, previews and annotations.
All 15 were training images. The split changes from 220/37/50 to **205/37/50**;
validation and test membership and pixels are unchanged. The original dataset
has an annotation warning in its README and remains available with its results.

The copy keeps all remaining image, mask and annotation bytes. Validation checks
all 292 retained samples against their preparation hashes, regenerates every
mask from native Supervisely polygons in saved order, and requires exact equality.
The native Supervisely project has the original 22 polygon classes and colors,
without imported `_1` classes or bitmaps. The established training mapping remains
21 channels, with void/uncovered pixels ignored as 255. Platform IDs are not
training-channel indices. This validates format and preservation, not a new
human adjudication of label semantics or overlap order.

Prepare a new destination, leaving the original data intact:

```bash
PYTHONPATH=.:src python scripts/prepare_rtis_v2.py \
  --source /path/to/paul-test-rtis --target /path/to/paul-test-rtis_v2
```

The HDRFS experiment uses the original frozen training revision
`066afb2626398b7be59d4d19f5a0e4644fd59adc`. Its 144 configs are copied from
`mud-fullstats-v1-20260906-r2`, selecting seed 0 and changing only the dataset root
and output root. This preserves all 36 models, four initialization paths, source
checkpoint hashes, effective batch size, 4,000-step cap, mud-IoU checkpoint
selection and early stopping. The source checkpoints and data hashes are checked
again during campaign initialization. Full evaluation/collection/profiling stays
required before a run counts as complete. Test inference is not performed.

The immutable `baseline-seed-0.json` snapshot supplies paired baseline metrics.
The comparison reports v2 minus v1 in percentage points, only for completed jobs.
One seed is an exploratory ablation and does not estimate optimization variance.
Removing questionable training data can help or hurt; no improvement is assumed.

The new report is separate from v1:
[RTIS v2](../results/paul-test-rtis/v2/README.md) and
[paired comparison](../results/paul-test-rtis/v2/comparison.md).
The [results index](../results/README.md) links both datasets.

Run the reporter from an up-to-date tools checkout, with an independent Git
checkout for publication:

```bash
python scripts/publish_rtis_results.py --campaign /path/to/v2-campaign \
  --checkout /path/to/publisher-checkout \
  --report-dir docs/results/paul-test-rtis/v2 --interval-seconds 1800
```

The reporter publishes at startup, then attempts a batch at most once every
30 minutes, including retries. Rapid training/status changes do not bypass the
interval. `--once` explicitly requests one immediate publication. A
`STOP_PUBLISHER` file stops the loop. Existing v1 reports are preserved.

## Live training controller

The full-statistics launcher starts the standard `rtis-fullstats-controller`
Tmux session. Its `training` window uses Textual and Rich to show recorded
optimizer iterations, progress, average optimizer steps/s, training ETA, loss,
and sample age. Select a row for elapsed time, images/s, GPU utilization and
memory, validation metrics, and a loss curve. The other window shows GPUs.

```bash
tmux attach -t rtis-fullstats-controller
```

Use arrow keys to select a run and `r` to refresh. Press `Ctrl+b`, release,
then press `d` to detach and leave the dashboard running. There is no `q` shortcut.
The screen polls every three seconds. Training currently emits telemetry every
50 optimizer steps; the sample-age column identifies how fresh each value is.
ETA is the trainer's estimate to its step limit, before final evaluation and
profiling; early stopping can shorten training. Rates are averages since the
training process started. Viewing or closing the display does not stop workers.

The reusable entry point is `python -m segmentary.rtis_progress CAMPAIGN_DIR`.
It reads campaign state and TensorBoard event files without loading models or
checkpoints. Install the project's dependencies before launching the controller.

Press **Enter** on a selected run to open its live detail view; **Escape** returns
to the overview. The detail view stays on that run as jobs advance. It includes
larger loss, validation mIoU, mud-pumping IoU, and optimizer-throughput charts,
with labeled optimizer-step axes and latest/minimum/maximum values. Dots are
recorded samples, joined for readability; curves are not smoothed. Scroll down
for loss components, learning rate, memory, validation scores, and per-class IoU,
each with its own recorded step and sample age. Missing metrics show as waiting.
Charts retain up to 256 recorded samples per scalar and stack on narrow terminals.
`Ctrl+b`, then `d` detaches from either view; neither `q` nor `Ctrl+q` quits it.
