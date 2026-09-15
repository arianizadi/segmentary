# Recorded training cost

Generated: 2026-09-15T16:57:01.231228+00:00. Source: `f9051656be4a9800d415b8e99ba782b23632a968`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-batch-seed0](models/dynunet-batch-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-per-sample-seed0](models/dynunet-per-sample-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-batch-seed1](models/dynunet-batch-seed1.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-per-sample-seed1](models/dynunet-per-sample-seed1.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
