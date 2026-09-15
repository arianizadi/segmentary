# Recorded training cost

Generated: 2026-09-15T04:44:00.800219+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | completed | current | 2263.016 (100/100 epochs) | 812.416 (100/100 epochs) | 47.341 (100/100 epochs) | 0.907 |
| [dynunet-deep10k-seed0](models/dynunet-deep10k-seed0.md) | completed | current | 2303.384 (100/100 epochs) | 829.258 (100/100 epochs) | 46.848 (100/100 epochs) | 0.920 |
| [dynunet-focal05-seed0](models/dynunet-focal05-seed0.md) | completed | current | 2286.400 (100/100 epochs) | 810.077 (100/100 epochs) | 46.660 (100/100 epochs) | 0.911 |
| [dynunet-focal10-seed0](models/dynunet-focal10-seed0.md) | completed | current | 2282.607 (100/100 epochs) | 814.844 (100/100 epochs) | 47.155 (100/100 epochs) | 0.912 |
| [dynunet-window-seed0](models/dynunet-window-seed0.md) | completed | current | 2277.908 (100/100 epochs) | 823.821 (100/100 epochs) | 47.173 (100/100 epochs) | 0.914 |
| [dynunet-minmax-seed0](models/dynunet-minmax-seed0.md) | completed | current | 2287.721 (100/100 epochs) | 814.350 (100/100 epochs) | 47.313 (100/100 epochs) | 0.914 |
| [dynunet-isotropic-seed0](models/dynunet-isotropic-seed0.md) | completed | current | 3834.609 (100/100 epochs) | 1045.757 (100/100 epochs) | 47.191 (100/100 epochs) | 1.409 |
| [swin_unetr-swin24-seed0](models/swin_unetr-swin24-seed0.md) | completed | current | 6100.750 (100/100 epochs) | 1074.097 (100/100 epochs) | 47.055 (100/100 epochs) | 2.045 |
| [swin_unetr-swin48-seed0](models/swin_unetr-swin48-seed0.md) | completed | current | 10658.141 (100/100 epochs) | 1270.221 (100/100 epochs) | 165.795 (100/100 epochs) | 3.400 |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
