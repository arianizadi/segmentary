# dynunet-control10k-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T21:30:08.948358+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

Status: **running**. Stage: **train**. GPU: **1**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T21:00:04.517156+00:00 / — |
| Last worker update | 2026-09-14T21:00:45.258404+00:00 |
| Completed / budget steps | 5600 / 10000 |
| Live step / phase | 5601 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4863 |
| Peak allocated / reserved GiB | 7.61 / 10.50 |

Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.

```json
{
  "augment": true,
  "backend": "torch",
  "batch_size": 8,
  "center_probabilities": null,
  "class_center_weights": null,
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
  "intensity_scale_probability": 0.0,
  "intensity_scale_range": [
    0.9,
    1.1
  ],
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
  "rotation_degrees": [
    -15.0,
    15.0
  ],
  "rotation_padding_value": 0.0,
  "rotation_probability": 0.0,
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

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | 1.3888 | 0.0002972986 | 0.1619 | 0.0000 | 22.9944 | 88.5053 | 0.4143 |
| 2 | 200 | 1.1421 | 0.0002945946 | — | — | 22.5056 | 0.0000 | 0.4096 |
| 3 | 300 | 1.0401 | 0.0002918877 | — | — | 22.5584 | 0.0000 | 0.4342 |
| 4 | 400 | 0.9500 | 0.0002891781 | — | — | 22.6227 | 0.0000 | 0.4479 |
| 5 | 500 | 0.8793 | 0.0002864656 | — | — | 22.6131 | 0.0000 | 0.4529 |
| 6 | 600 | 0.8235 | 0.0002837503 | — | — | 22.6314 | 0.0000 | 0.4264 |
| 7 | 700 | 0.7786 | 0.0002810321 | — | — | 22.6117 | 0.0000 | 0.4511 |
| 8 | 800 | 0.7446 | 0.000278311 | — | — | 22.6289 | 0.0000 | 0.4238 |
| 9 | 900 | 0.7122 | 0.0002755869 | — | — | 22.6352 | 0.0000 | 0.4509 |
| 10 | 1000 | 0.6705 | 0.0002728598 | 0.4947 | 0.1309 | 22.6430 | 66.5678 | 0.4952 |
| 11 | 1100 | 0.6138 | 0.0002701297 | — | — | 22.5585 | 0.0000 | 0.4233 |
| 12 | 1200 | 0.5978 | 0.0002673965 | — | — | 22.6093 | 0.0000 | 0.4454 |
| 13 | 1300 | 0.5527 | 0.0002646602 | — | — | 22.6324 | 0.0000 | 0.4353 |
| 14 | 1400 | 0.5859 | 0.0002619207 | — | — | 22.6441 | 0.0000 | 0.4307 |
| 15 | 1500 | 0.5580 | 0.0002591781 | — | — | 22.6581 | 0.0000 | 0.4847 |
| 16 | 1600 | 0.5509 | 0.0002564322 | — | — | 22.6196 | 0.0000 | 0.4568 |
| 17 | 1700 | 0.5291 | 0.0002536831 | — | — | 22.6263 | 0.0000 | 0.4536 |
| 18 | 1800 | 0.4998 | 0.0002509307 | — | — | 22.6277 | 0.0000 | 0.4354 |
| 19 | 1900 | 0.5273 | 0.0002481749 | — | — | 22.6314 | 0.0000 | 0.4582 |
| 20 | 2000 | 0.4784 | 0.0002454156 | 0.4892 | 0.2021 | 22.6332 | 76.4038 | 0.4656 |
| 21 | 2100 | 0.4801 | 0.000242653 | — | — | 22.5636 | 0.0000 | 0.3941 |
| 22 | 2200 | 0.4730 | 0.0002398868 | — | — | 22.5816 | 0.0000 | 0.4346 |
| 23 | 2300 | 0.4599 | 0.0002371171 | — | — | 22.5987 | 0.0000 | 0.4469 |
| 24 | 2400 | 0.4605 | 0.0002343438 | — | — | 22.5922 | 0.0000 | 0.4421 |
| 25 | 2500 | 0.4166 | 0.0002315669 | — | — | 22.6075 | 0.0000 | 0.4320 |
| 26 | 2600 | 0.4590 | 0.0002287862 | — | — | 22.6171 | 0.0000 | 0.4334 |
| 27 | 2700 | 0.4172 | 0.0002260018 | — | — | 22.6228 | 0.0000 | 0.4288 |
| 28 | 2800 | 0.4110 | 0.0002232135 | — | — | 22.6351 | 0.0000 | 0.4385 |
| 29 | 2900 | 0.4156 | 0.0002204214 | — | — | 22.6312 | 0.0000 | 0.4459 |
| 30 | 3000 | 0.4146 | 0.0002176254 | 0.6293 | 0.2467 | 22.6499 | 68.8342 | 0.4676 |
| 31 | 3100 | 0.4110 | 0.0002148253 | — | — | 22.5405 | 0.0000 | 0.3994 |
| 32 | 3200 | 0.3941 | 0.0002120212 | — | — | 22.5911 | 0.0000 | 0.4294 |
| 33 | 3300 | 0.4014 | 0.000209213 | — | — | 22.6189 | 0.0000 | 0.4417 |
| 34 | 3400 | 0.4030 | 0.0002064005 | — | — | 22.6424 | 0.0000 | 0.4423 |
| 35 | 3500 | 0.3894 | 0.0002035838 | — | — | 22.6309 | 0.0000 | 0.4359 |
| 36 | 3600 | 0.3906 | 0.0002007628 | — | — | 22.6252 | 0.0000 | 0.4356 |
| 37 | 3700 | 0.3709 | 0.0001979373 | — | — | 22.6297 | 0.0000 | 0.4529 |
| 38 | 3800 | 0.3851 | 0.0001951074 | — | — | 22.6318 | 0.0000 | 0.4382 |
| 39 | 3900 | 0.3790 | 0.0001922729 | — | — | 22.7778 | 0.0000 | 0.4340 |
| 40 | 4000 | 0.3599 | 0.0001894338 | 0.6125 | 0.2187 | 22.6376 | 69.4702 | 0.4369 |
| 41 | 4100 | 0.4113 | 0.0001865899 | — | — | 22.5577 | 0.0000 | 0.4321 |
| 42 | 4200 | 0.3704 | 0.0001837412 | — | — | 22.5970 | 0.0000 | 0.4418 |
| 43 | 4300 | 0.3874 | 0.0001808875 | — | — | 22.6291 | 0.0000 | 0.4420 |
| 44 | 4400 | 0.3461 | 0.0001780289 | — | — | 22.6119 | 0.0000 | 0.4516 |
| 45 | 4500 | 0.3472 | 0.0001751651 | — | — | 22.6286 | 0.0000 | 0.4483 |
| 46 | 4600 | 0.3321 | 0.0001722962 | — | — | 22.6368 | 0.0000 | 0.4424 |
| 47 | 4700 | 0.3355 | 0.0001694219 | — | — | 22.6394 | 0.0000 | 0.4435 |
| 48 | 4800 | 0.3425 | 0.0001665422 | — | — | 22.6524 | 0.0000 | 0.4468 |
| 49 | 4900 | 0.3329 | 0.0001636569 | — | — | 22.6568 | 0.0000 | 0.4421 |
| 50 | 5000 | 0.3326 | 0.000160766 | 0.7198 | 0.2729 | 22.6613 | 75.6565 | 0.4750 |
| 51 | 5100 | 0.3536 | 0.0001578693 | — | — | 22.5440 | 0.0000 | 0.4043 |
| 52 | 5200 | 0.3327 | 0.0001549667 | — | — | 22.5912 | 0.0000 | 0.4488 |
| 53 | 5300 | 0.3256 | 0.000152058 | — | — | 22.6153 | 0.0000 | 0.4513 |
| 54 | 5400 | 0.3324 | 0.0001491431 | — | — | 22.6525 | 0.0000 | 0.4389 |
| 55 | 5500 | 0.3241 | 0.0001462219 | — | — | 22.6711 | 0.0000 | 0.4385 |
| 56 | 5600 | 0.3183 | 0.0001432942 | — | — | 22.6801 | 0.0000 | 0.4448 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-control10k-seed0.json)

| Measurement | Value |
| --- | --- |
| Native predictions completed / expected / failed | 0 / 42 / 0 |
| Measured prediction pipeline wall seconds | — |
| Complete-cohort scans per second | — |
| Recorded case latency mean / p50 / p95 seconds | — / — / — |
| Prediction allocated / reserved peak GiB | — / — |
| Standardized model-only benchmark | not_recorded |
| Model-only patches/s; p50 / p95 ms | —; — / — |

Case latency includes preprocessing, tiled inference, native reconstruction and export; in overlapped runs it also includes queue time. It is neither model-only latency nor an additive stage wall time. No speed is inferred from GPU utilization snapshots.

