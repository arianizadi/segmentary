# medformer

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T00:53:11.494509+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **7**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.246489+00:00 / — |
| Last worker update | 2026-09-13T23:18:15.484897+00:00 |
| Completed / budget steps | 5300 / 10000 |
| Live step / phase | 5350 / train |
| Parameters | 39591555 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 1.5786 |
| Peak allocated / reserved GiB | 29.95 / 33.89 |

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
  "model": "medformer",
  "model_options": {
    "base_chan": 32,
    "chan_num": [
      64,
      128,
      256,
      320,
      256,
      128,
      64,
      32
    ],
    "conv_num": [
      2,
      1,
      0,
      0,
      0,
      1,
      2,
      2
    ],
    "expansion": 4,
    "fusion_depth": 2,
    "fusion_dim": 320,
    "fusion_heads": 10,
    "map_size": [
      4,
      4,
      4
    ],
    "num_heads": [
      1,
      4,
      8,
      10,
      8,
      4,
      1,
      1
    ],
    "trans_num": [
      0,
      1,
      4,
      6,
      4,
      1,
      0,
      0
    ]
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
| 1 | 100 | 0.9491 | 0.0002972986 | 0.1097 | 0.0000 |
| 2 | 200 | 0.8706 | 0.0002945946 | — | — |
| 3 | 300 | 0.8252 | 0.0002918877 | — | — |
| 4 | 400 | 0.7550 | 0.0002891781 | — | — |
| 5 | 500 | 0.7413 | 0.0002864656 | — | — |
| 6 | 600 | 0.6942 | 0.0002837503 | — | — |
| 7 | 700 | 0.6726 | 0.0002810321 | — | — |
| 8 | 800 | 0.6263 | 0.000278311 | — | — |
| 9 | 900 | 0.6528 | 0.0002755869 | — | — |
| 10 | 1000 | 0.6217 | 0.0002728598 | 0.4124 | 0.1281 |
| 11 | 1100 | 0.5712 | 0.0002701297 | — | — |
| 12 | 1200 | 0.5908 | 0.0002673965 | — | — |
| 13 | 1300 | 0.5980 | 0.0002646602 | — | — |
| 14 | 1400 | 0.5973 | 0.0002619207 | — | — |
| 15 | 1500 | 0.5662 | 0.0002591781 | — | — |
| 16 | 1600 | 0.6063 | 0.0002564322 | — | — |
| 17 | 1700 | 0.5533 | 0.0002536831 | — | — |
| 18 | 1800 | 0.5237 | 0.0002509307 | — | — |
| 19 | 1900 | 0.5777 | 0.0002481749 | — | — |
| 20 | 2000 | 0.5218 | 0.0002454156 | 0.4443 | 0.2141 |
| 21 | 2100 | 0.4884 | 0.000242653 | — | — |
| 22 | 2200 | 0.5076 | 0.0002398868 | — | — |
| 23 | 2300 | 0.4943 | 0.0002371171 | — | — |
| 24 | 2400 | 0.4880 | 0.0002343438 | — | — |
| 25 | 2500 | 0.4477 | 0.0002315669 | — | — |
| 26 | 2600 | 0.5004 | 0.0002287862 | — | — |
| 27 | 2700 | 0.4618 | 0.0002260018 | — | — |
| 28 | 2800 | 0.4634 | 0.0002232135 | — | — |
| 29 | 2900 | 0.4703 | 0.0002204214 | — | — |
| 30 | 3000 | 0.4621 | 0.0002176254 | 0.5771 | 0.2261 |
| 31 | 3100 | 0.4751 | 0.0002148253 | — | — |
| 32 | 3200 | 0.4419 | 0.0002120212 | — | — |
| 33 | 3300 | 0.4552 | 0.000209213 | — | — |
| 34 | 3400 | 0.4559 | 0.0002064005 | — | — |
| 35 | 3500 | 0.4403 | 0.0002035838 | — | — |
| 36 | 3600 | 0.4232 | 0.0002007628 | — | — |
| 37 | 3700 | 0.4144 | 0.0001979373 | — | — |
| 38 | 3800 | 0.4086 | 0.0001951074 | — | — |
| 39 | 3900 | 0.4038 | 0.0001922729 | — | — |
| 40 | 4000 | 0.3858 | 0.0001894338 | 0.6181 | 0.2196 |
| 41 | 4100 | 0.4510 | 0.0001865899 | — | — |
| 42 | 4200 | 0.4076 | 0.0001837412 | — | — |
| 43 | 4300 | 0.4150 | 0.0001808875 | — | — |
| 44 | 4400 | 0.3927 | 0.0001780289 | — | — |
| 45 | 4500 | 0.3861 | 0.0001751651 | — | — |
| 46 | 4600 | 0.3879 | 0.0001722962 | — | — |
| 47 | 4700 | 0.3724 | 0.0001694219 | — | — |
| 48 | 4800 | 0.3937 | 0.0001665422 | — | — |
| 49 | 4900 | 0.3612 | 0.0001636569 | — | — |
| 50 | 5000 | 0.3647 | 0.000160766 | 0.6647 | 0.2702 |
| 51 | 5100 | 0.3977 | 0.0001578693 | — | — |
| 52 | 5200 | 0.3884 | 0.0001549667 | — | — |
| 53 | 5300 | 0.3751 | 0.000152058 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
