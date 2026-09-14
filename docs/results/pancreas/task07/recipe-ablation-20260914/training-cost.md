# Recorded training cost

Generated: 2026-09-14T18:33:30.436031+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control-seed0](models/dynunet-control-seed0.md) | completed | current | 2264.235 (100/100 epochs) | 808.747 (100/100 epochs) | 47.339 (100/100 epochs) | 0.907 |
| [dynunet-mass50-seed0](models/dynunet-mass50-seed0.md) | completed | current | 2269.777 (100/100 epochs) | 802.281 (100/100 epochs) | 46.895 (100/100 epochs) | 0.904 |
| [dynunet-class111-seed0](models/dynunet-class111-seed0.md) | completed | current | 2276.846 (100/100 epochs) | 809.061 (100/100 epochs) | 47.121 (100/100 epochs) | 0.909 |
| [dynunet-class115-seed0](models/dynunet-class115-seed0.md) | completed | current | 2273.970 (100/100 epochs) | 806.646 (100/100 epochs) | 46.794 (100/100 epochs) | 0.908 |
| [dynunet-rotation-seed0](models/dynunet-rotation-seed0.md) | completed | current | 2290.066 (100/100 epochs) | 803.460 (100/100 epochs) | 47.235 (100/100 epochs) | 0.912 |
| [dynunet-intensity-seed0](models/dynunet-intensity-seed0.md) | completed | current | 2289.566 (100/100 epochs) | 813.592 (100/100 epochs) | 47.041 (100/100 epochs) | 0.914 |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
