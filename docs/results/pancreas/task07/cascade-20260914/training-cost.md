# Recorded training cost

Generated: 2026-09-15T01:44:03.651744+00:00. Source: `8fd7fe0dc773a9d60d333e4cdb663e3c255f9868`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | completed | current | 2277.769 (100/100 epochs) | 803.644 (100/100 epochs) | 46.743 (100/100 epochs) | 0.907 |
| [dynunet-roi20-seed0](models/dynunet-roi20-seed0.md) | failed | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | 0.009 |
| [dynunet-roi40-seed0](models/dynunet-roi40-seed0.md) | failed | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | 0.009 |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
