# Recorded training cost

Generated: 2026-09-15T02:41:56.708661+00:00. Source: `993e6413341dbc5c39ec46cdf5f846e246215b4f`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | running | current | 1229.165 (54/54 epochs) | 464.586 (54/54 epochs) | 25.413 (54/54 epochs) | 0.000 |
| [dynunet-roi20-seed0](models/dynunet-roi20-seed0.md) | running | current | 1530.243 (67/67 epochs) | 193.264 (67/67 epochs) | 31.517 (67/67 epochs) | 0.000 |
| [dynunet-roi40-seed0](models/dynunet-roi40-seed0.md) | running | current | 1505.185 (66/66 epochs) | 210.318 (66/66 epochs) | 31.099 (66/66 epochs) | 0.000 |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
