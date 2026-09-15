# Recorded training cost

Generated: 2026-09-15T00:38:50.653104+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | running | current | 1244.924 (55/55 epochs) | 455.912 (55/55 epochs) | 25.591 (55/55 epochs) | 0.000 |
| [dynunet-deep10k-seed0](models/dynunet-deep10k-seed0.md) | running | current | 1244.289 (54/54 epochs) | 466.942 (54/54 epochs) | 25.094 (54/54 epochs) | 0.000 |
| [dynunet-focal05-seed0](models/dynunet-focal05-seed0.md) | running | current | 1258.071 (55/55 epochs) | 454.686 (55/55 epochs) | 25.591 (55/55 epochs) | 0.000 |
| [dynunet-focal10-seed0](models/dynunet-focal10-seed0.md) | running | current | 1255.046 (55/55 epochs) | 449.633 (55/55 epochs) | 25.480 (55/55 epochs) | 0.000 |
| [dynunet-window-seed0](models/dynunet-window-seed0.md) | running | current | 1252.848 (55/55 epochs) | 456.765 (55/55 epochs) | 25.999 (55/55 epochs) | 0.000 |
| [dynunet-minmax-seed0](models/dynunet-minmax-seed0.md) | running | current | 1235.287 (54/54 epochs) | 454.697 (54/54 epochs) | 25.192 (54/54 epochs) | 0.000 |
| [dynunet-isotropic-seed0](models/dynunet-isotropic-seed0.md) | running | current | 1303.996 (34/34 epochs) | 395.413 (34/34 epochs) | 16.318 (34/34 epochs) | 0.000 |
| [swin_unetr-swin24-seed0](models/swin_unetr-swin24-seed0.md) | running | current | 1403.956 (23/23 epochs) | 301.673 (23/23 epochs) | 10.954 (23/23 epochs) | 0.000 |
| [swin_unetr-swin48-seed0](models/swin_unetr-swin48-seed0.md) | queued | current | — (0/0 epochs) | — (0/0 epochs) | — (0/0 epochs) | — |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
