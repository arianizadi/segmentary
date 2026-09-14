# segresnet

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T01:23:13.975052+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **5**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T00:32:52.654389+00:00 / — |
| Last worker update | 2026-09-14T00:33:32.964963+00:00 |
| Completed / budget steps | 4900 / 10000 |
| Live step / phase | — / validation |
| Parameters | 18796035 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.8246 |
| Peak allocated / reserved GiB | 17.07 / 19.56 |

Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.

```json
{
  "augment": true,
  "backend": "torch",
  "batch_size": 8,
  "context_slices": 1,
  "deterministic": false,
  "epochs": 100,
  "foreground_probability": 0.5,
  "gradient_clip": 12.0,
  "hu_window": [
    -100.0,
    240.0
  ],
  "inference_batch_size": 8,
  "learning_rate": 0.0003,
  "mode": "3d",
  "model": "segresnet",
  "model_options": {
    "blocks_down": [
      1,
      2,
      2,
      4
    ],
    "blocks_up": [
      1,
      1,
      1
    ],
    "init_filters": 32,
    "num_groups": 8
  },
  "overlap": 0.5,
  "patch_size": [
    96,
    96,
    96
  ],
  "precision": "bf16",
  "prefetch_batches": true,
  "progress_interval": 10,
  "purpose": "baseline",
  "seed": 0,
  "spacing_mm": [
    1.5,
    1.5,
    2.5
  ],
  "steps_per_epoch": 100,
  "validation_interval": 10,
  "weight_decay": 1e-05,
  "workers": 4
}
```

## Native validation

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice |
| --- | --- | --- | --- | --- | --- |
| 1 | 100 | 1.2533 | 0.0002972986 | 0.0000 | 0.0000 |
| 2 | 200 | 1.1178 | 0.0002945946 | — | — |
| 3 | 300 | 1.0721 | 0.0002918877 | — | — |
| 4 | 400 | 1.0308 | 0.0002891781 | — | — |
| 5 | 500 | 0.9986 | 0.0002864656 | — | — |
| 6 | 600 | 0.9757 | 0.0002837503 | — | — |
| 7 | 700 | 0.9603 | 0.0002810321 | — | — |
| 8 | 800 | 0.9314 | 0.000278311 | — | — |
| 9 | 900 | 0.8880 | 0.0002755869 | — | — |
| 10 | 1000 | 0.8673 | 0.0002728598 | 0.2317 | 0.0000 |
| 11 | 1100 | 0.8451 | 0.0002701297 | — | — |
| 12 | 1200 | 0.8349 | 0.0002673965 | — | — |
| 13 | 1300 | 0.8146 | 0.0002646602 | — | — |
| 14 | 1400 | 0.7806 | 0.0002619207 | — | — |
| 15 | 1500 | 0.7583 | 0.0002591781 | — | — |
| 16 | 1600 | 0.7531 | 0.0002564322 | — | — |
| 17 | 1700 | 0.6913 | 0.0002536831 | — | — |
| 18 | 1800 | 0.6746 | 0.0002509307 | — | — |
| 19 | 1900 | 0.7109 | 0.0002481749 | — | — |
| 20 | 2000 | 0.6289 | 0.0002454156 | 0.2981 | 0.1170 |
| 21 | 2100 | 0.6223 | 0.000242653 | — | — |
| 22 | 2200 | 0.6204 | 0.0002398868 | — | — |
| 23 | 2300 | 0.6376 | 0.0002371171 | — | — |
| 24 | 2400 | 0.6126 | 0.0002343438 | — | — |
| 25 | 2500 | 0.5548 | 0.0002315669 | — | — |
| 26 | 2600 | 0.5753 | 0.0002287862 | — | — |
| 27 | 2700 | 0.5481 | 0.0002260018 | — | — |
| 28 | 2800 | 0.5493 | 0.0002232135 | — | — |
| 29 | 2900 | 0.5466 | 0.0002204214 | — | — |
| 30 | 3000 | 0.5209 | 0.0002176254 | 0.5690 | 0.2054 |
| 31 | 3100 | 0.5483 | 0.0002148253 | — | — |
| 32 | 3200 | 0.5426 | 0.0002120212 | — | — |
| 33 | 3300 | 0.5247 | 0.000209213 | — | — |
| 34 | 3400 | 0.4962 | 0.0002064005 | — | — |
| 35 | 3500 | 0.5201 | 0.0002035838 | — | — |
| 36 | 3600 | 0.5007 | 0.0002007628 | — | — |
| 37 | 3700 | 0.4707 | 0.0001979373 | — | — |
| 38 | 3800 | 0.4742 | 0.0001951074 | — | — |
| 39 | 3900 | 0.4726 | 0.0001922729 | — | — |
| 40 | 4000 | 0.4478 | 0.0001894338 | 0.5764 | 0.2318 |
| 41 | 4100 | 0.4999 | 0.0001865899 | — | — |
| 42 | 4200 | 0.4669 | 0.0001837412 | — | — |
| 43 | 4300 | 0.4640 | 0.0001808875 | — | — |
| 44 | 4400 | 0.4272 | 0.0001780289 | — | — |
| 45 | 4500 | 0.4349 | 0.0001751651 | — | — |
| 46 | 4600 | 0.4364 | 0.0001722962 | — | — |
| 47 | 4700 | 0.4240 | 0.0001694219 | — | — |
| 48 | 4800 | 0.4285 | 0.0001665422 | — | — |
| 49 | 4900 | 0.4265 | 0.0001636569 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
