# Recorded training cost

Generated: 2026-09-14T21:30:08.948358+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | running | current | 1267.136 (56/56 epochs) | 445.438 (56/56 epochs) | 24.698 (56/56 epochs) | 0.000 |
| [dynunet-long30k-seed0](models/dynunet-long30k-seed0.md) | running | current | 1251.275 (55/55 epochs) | 445.235 (55/55 epochs) | 24.516 (55/55 epochs) | 0.000 |
| [dynunet-fine10k-seed0](models/dynunet-fine10k-seed0.md) | running | current | 1344.889 (26/26 epochs) | 339.053 (26/26 epochs) | 11.604 (26/26 epochs) | 0.000 |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
