# Recorded training cost

Generated: 2026-09-14T17:58:31.426550+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control-seed0](models/dynunet-control-seed0.md) | running | current | 1268.064 (56/56 epochs) | 453.844 (56/56 epochs) | 26.639 (56/56 epochs) | 0.000 |
| [dynunet-mass50-seed0](models/dynunet-mass50-seed0.md) | running | current | 1271.195 (56/56 epochs) | 447.709 (56/56 epochs) | 26.192 (56/56 epochs) | 0.000 |
| [dynunet-class111-seed0](models/dynunet-class111-seed0.md) | running | current | 1274.728 (56/56 epochs) | 450.820 (56/56 epochs) | 26.498 (56/56 epochs) | 0.000 |
| [dynunet-class115-seed0](models/dynunet-class115-seed0.md) | running | current | 1273.433 (56/56 epochs) | 448.782 (56/56 epochs) | 26.263 (56/56 epochs) | 0.000 |
| [dynunet-rotation-seed0](models/dynunet-rotation-seed0.md) | running | current | 1284.249 (56/56 epochs) | 444.498 (56/56 epochs) | 26.455 (56/56 epochs) | 0.000 |
| [dynunet-intensity-seed0](models/dynunet-intensity-seed0.md) | running | current | 1259.070 (55/55 epochs) | 460.050 (55/55 epochs) | 25.973 (55/55 epochs) | 0.000 |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
