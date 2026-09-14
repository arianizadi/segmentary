# Recorded training cost

Generated: 2026-09-14T23:00:17.977338+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | completed | current | 2263.662 (100/100 epochs) | 805.878 (100/100 epochs) | 44.337 (100/100 epochs) | 0.904 |
| [dynunet-long30k-seed0](models/dynunet-long30k-seed0.md) | running | current | 5304.002 (233/233 epochs) | 1718.566 (233/233 epochs) | 102.446 (233/233 epochs) | 0.000 |
| [dynunet-fine10k-seed0](models/dynunet-fine10k-seed0.md) | completed | current | 5176.962 (100/100 epochs) | 1194.147 (100/100 epochs) | 45.285 (100/100 epochs) | 1.826 |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
