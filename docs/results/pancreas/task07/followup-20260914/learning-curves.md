# Training and native validation curves

**Budget and resolution experiments:** all arms are scratch DynUNet runs with the same held-out validation split. The long arm changes both update budget and polynomial-decay horizon; the finer arm changes voxel spacing and patch dimensions to preserve physical context, with more voxels per update. These are planned recipe contrasts, not equal-compute architecture rankings.

Generated: 2026-09-14T21:00:04.574801+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

Each row is a completed training epoch. Blank validation cells mean validation was not scheduled. The step count, rather than wall-clock order, is the comparison axis. No values are interpolated.

## dynunet-control10k-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-long30k-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-fine10k-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
