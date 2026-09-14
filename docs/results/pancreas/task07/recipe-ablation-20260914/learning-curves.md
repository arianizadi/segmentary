# Training and native validation curves

**Recipe experiment:** the named arms use the same DynUNet architecture, loss, split, inference protocol and fixed 10,000-update budget. Run IDs identify separate scratch initializations under declared ingredient changes; they are not different architectures. Rankings stay within each seed and require all planned arms to finish. The class111/class115 pair changes class weights; both also change background-center semantics relative to the uniform-volume control. Historical results used a different source snapshot and are not included as same-source replicates.

Generated: 2026-09-14T17:28:27.928232+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

Each row is a completed training epoch. Blank validation cells mean validation was not scheduled. The step count, rather than wall-clock order, is the comparison axis. No values are interpolated.

## dynunet-control-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-mass50-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-class111-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-class115-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-rotation-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## dynunet-intensity-seed0

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
