# Training and native validation curves

**Controlled recipe explorations:** fresh scratch runs, 10,000 updates each, using the same development partition. The frozen campaign lists exact changes in loss, normalization, spacing, architecture or predicted-organ cropping. Compare each candidate with its control using full-native per-patient metrics. These are one-seed validation experiments, not equal-compute architecture rankings or independent test results. Cascade misses outside the crop still count.

Generated: 2026-09-14T23:58:36.669554+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Each row is a completed training epoch. Blank validation cells mean validation was not scheduled. The step count, rather than wall-clock order, is the comparison axis. No values are interpolated.

## dynunet-control10k-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-deep10k-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-focal05-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-focal10-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-window-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-minmax-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-isotropic-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## swin_unetr-swin24-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## swin_unetr-swin48-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
