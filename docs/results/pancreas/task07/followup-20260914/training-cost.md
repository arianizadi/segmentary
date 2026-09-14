# Recorded training cost

Generated: 2026-09-14T21:00:04.574801+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | running | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-long30k-seed0](models/dynunet-long30k-seed0.md) | running | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-fine10k-seed0](models/dynunet-fine10k-seed0.md) | running | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
