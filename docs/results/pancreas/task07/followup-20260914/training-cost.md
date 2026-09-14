# Recorded training cost

Generated: 2026-09-14T22:30:14.972452+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | completed | current | 2263.662 (100/100 epochs) | 805.878 (100/100 epochs) | 44.337 (100/100 epochs) | 0.904 |
| [dynunet-long30k-seed0](models/dynunet-long30k-seed0.md) | running | current | 3960.911 (174/174 epochs) | 1297.707 (174/174 epochs) | 76.571 (174/174 epochs) | 0.000 |
| [dynunet-fine10k-seed0](models/dynunet-fine10k-seed0.md) | running | current | 4296.207 (83/83 epochs) | 976.011 (83/83 epochs) | 37.480 (83/83 epochs) | 0.000 |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
