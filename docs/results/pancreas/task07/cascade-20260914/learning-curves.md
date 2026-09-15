# Training and native validation curves

**Controlled recipe explorations:** fresh scratch runs, 10,000 updates each, using the same development partition. The frozen campaign lists exact changes in loss, normalization, spacing, architecture or predicted-organ cropping. Compare each candidate with its control using full-native per-patient metrics. These are one-seed validation experiments, not equal-compute architecture rankings or independent test results. Cascade misses outside the crop still count.

Generated: 2026-09-15T00:44:56.329460+00:00. Source: `8fd7fe0dc773a9d60d333e4cdb663e3c255f9868`.

Each row is a completed training epoch. Blank validation cells mean validation was not scheduled. The step count, rather than wall-clock order, is the comparison axis. No values are interpolated.

## dynunet-control10k-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-roi20-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-roi40-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
