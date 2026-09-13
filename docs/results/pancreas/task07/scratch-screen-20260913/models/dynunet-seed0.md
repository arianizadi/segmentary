# dynunet

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-13T23:53:06.453616+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **9**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.252247+00:00 / — |
| Last worker update | 2026-09-13T23:18:14.572575+00:00 |
| Completed / budget steps | 4800 / 10000 |
| Live step / phase | 4801 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5775 |
| Peak allocated / reserved GiB | 7.61 / 10.50 |

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
  "model": "dynunet",
  "model_options": {
    "filters": [
      32,
      64,
      128,
      256,
      320
    ],
    "res_block": false
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
| 1 | 100 | 1.3888 | 0.0002972986 | 0.1619 | 0.0000 |
| 2 | 200 | 1.1421 | 0.0002945946 | — | — |
| 3 | 300 | 1.0401 | 0.0002918877 | — | — |
| 4 | 400 | 0.9500 | 0.0002891781 | — | — |
| 5 | 500 | 0.8793 | 0.0002864656 | — | — |
| 6 | 600 | 0.8235 | 0.0002837503 | — | — |
| 7 | 700 | 0.7786 | 0.0002810321 | — | — |
| 8 | 800 | 0.7446 | 0.000278311 | — | — |
| 9 | 900 | 0.7122 | 0.0002755869 | — | — |
| 10 | 1000 | 0.6705 | 0.0002728598 | 0.4947 | 0.1309 |
| 11 | 1100 | 0.6138 | 0.0002701297 | — | — |
| 12 | 1200 | 0.5978 | 0.0002673965 | — | — |
| 13 | 1300 | 0.5527 | 0.0002646602 | — | — |
| 14 | 1400 | 0.5859 | 0.0002619207 | — | — |
| 15 | 1500 | 0.5580 | 0.0002591781 | — | — |
| 16 | 1600 | 0.5509 | 0.0002564322 | — | — |
| 17 | 1700 | 0.5291 | 0.0002536831 | — | — |
| 18 | 1800 | 0.4998 | 0.0002509307 | — | — |
| 19 | 1900 | 0.5273 | 0.0002481749 | — | — |
| 20 | 2000 | 0.4784 | 0.0002454156 | 0.4892 | 0.2021 |
| 21 | 2100 | 0.4801 | 0.000242653 | — | — |
| 22 | 2200 | 0.4730 | 0.0002398868 | — | — |
| 23 | 2300 | 0.4599 | 0.0002371171 | — | — |
| 24 | 2400 | 0.4605 | 0.0002343438 | — | — |
| 25 | 2500 | 0.4166 | 0.0002315669 | — | — |
| 26 | 2600 | 0.4590 | 0.0002287862 | — | — |
| 27 | 2700 | 0.4172 | 0.0002260018 | — | — |
| 28 | 2800 | 0.4110 | 0.0002232135 | — | — |
| 29 | 2900 | 0.4156 | 0.0002204214 | — | — |
| 30 | 3000 | 0.4146 | 0.0002176254 | 0.6293 | 0.2467 |
| 31 | 3100 | 0.4110 | 0.0002148253 | — | — |
| 32 | 3200 | 0.3941 | 0.0002120212 | — | — |
| 33 | 3300 | 0.4014 | 0.000209213 | — | — |
| 34 | 3400 | 0.4030 | 0.0002064005 | — | — |
| 35 | 3500 | 0.3894 | 0.0002035838 | — | — |
| 36 | 3600 | 0.3906 | 0.0002007628 | — | — |
| 37 | 3700 | 0.3709 | 0.0001979373 | — | — |
| 38 | 3800 | 0.3851 | 0.0001951074 | — | — |
| 39 | 3900 | 0.3790 | 0.0001922729 | — | — |
| 40 | 4000 | 0.3599 | 0.0001894338 | 0.6125 | 0.2187 |
| 41 | 4100 | 0.4113 | 0.0001865899 | — | — |
| 42 | 4200 | 0.3704 | 0.0001837412 | — | — |
| 43 | 4300 | 0.3874 | 0.0001808875 | — | — |
| 44 | 4400 | 0.3461 | 0.0001780289 | — | — |
| 45 | 4500 | 0.3472 | 0.0001751651 | — | — |
| 46 | 4600 | 0.3321 | 0.0001722962 | — | — |
| 47 | 4700 | 0.3355 | 0.0001694219 | — | — |
| 48 | 4800 | 0.3425 | 0.0001665422 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
