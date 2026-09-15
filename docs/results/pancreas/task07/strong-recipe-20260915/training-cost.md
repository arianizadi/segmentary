# Recorded training cost

Generated: 2026-09-15T18:04:55.064097+00:00. Source: `63a108f8b7a65a98b11ccae0e8883c54955b2099`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [nnunet_resenc_l](models/nnunet_resenc_l-seed0.md) | running | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [nnunet_planned_plainconv](models/nnunet_planned_plainconv-seed0.md) | running | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [nnunet_planned_dynunet](models/nnunet_planned_dynunet-seed0.md) | running | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
