# Recorded training cost

Generated: 2026-09-15T17:54:41.384912+00:00. Source: `f9051656be4a9800d415b8e99ba782b23632a968`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-batch-seed0](models/dynunet-batch-seed0.md) | completed | current | 2274.543 (100/100 epochs) | 793.977 (100/100 epochs) | 46.649 (100/100 epochs) | 0.905 |
| [dynunet-per-sample-seed0](models/dynunet-per-sample-seed0.md) | completed | current | 2283.316 (100/100 epochs) | 792.791 (100/100 epochs) | 45.459 (100/100 epochs) | 0.907 |
| [dynunet-batch-seed1](models/dynunet-batch-seed1.md) | completed | current | 2290.231 (100/100 epochs) | 803.099 (100/100 epochs) | 46.904 (100/100 epochs) | 0.913 |
| [dynunet-per-sample-seed1](models/dynunet-per-sample-seed1.md) | completed | current | 2278.528 (100/100 epochs) | 795.325 (100/100 epochs) | 46.202 (100/100 epochs) | 0.907 |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
