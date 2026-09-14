# Recorded training cost

Generated: 2026-09-14T23:58:36.669554+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-deep10k-seed0](models/dynunet-deep10k-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-focal05-seed0](models/dynunet-focal05-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-focal10-seed0](models/dynunet-focal10-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-window-seed0](models/dynunet-window-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-minmax-seed0](models/dynunet-minmax-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [dynunet-isotropic-seed0](models/dynunet-isotropic-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [swin_unetr-swin24-seed0](models/swin_unetr-swin24-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |
| [swin_unetr-swin48-seed0](models/swin_unetr-swin48-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
