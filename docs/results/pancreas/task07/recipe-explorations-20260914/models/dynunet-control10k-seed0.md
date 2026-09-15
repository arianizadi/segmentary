# dynunet-control10k-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T00:38:50.653104+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **1**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T00:08:44.940263+00:00 / — |
| Last worker update | 2026-09-15T00:09:26.698089+00:00 |
| Completed / budget steps | 5500 / 10000 |
| Live step / phase | 5550 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4865 |
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
| 1 | 100 | 1.3888 | 0.0002972986 | 0.1619 | 0.0000 | 23.5484 | 97.2499 | 0.4220 |
| 2 | 200 | 1.1421 | 0.0002945946 | — | — | 22.4986 | 0.0000 | 0.4257 |
| 3 | 300 | 1.0401 | 0.0002918877 | — | — | 22.5374 | 0.0000 | 0.5062 |
| 4 | 400 | 0.9500 | 0.0002891781 | — | — | 22.7695 | 0.0000 | 0.4436 |
| 5 | 500 | 0.8793 | 0.0002864656 | — | — | 22.6092 | 0.0000 | 0.4728 |
| 6 | 600 | 0.8235 | 0.0002837503 | — | — | 22.6218 | 0.0000 | 0.4630 |
| 7 | 700 | 0.7786 | 0.0002810321 | — | — | 22.6328 | 0.0000 | 0.4433 |
| 8 | 800 | 0.7446 | 0.000278311 | — | — | 22.6507 | 0.0000 | 0.4380 |
| 9 | 900 | 0.7122 | 0.0002755869 | — | — | 22.6096 | 0.0000 | 0.4362 |
| 10 | 1000 | 0.6705 | 0.0002728598 | 0.4947 | 0.1309 | 22.6127 | 69.2859 | 0.5231 |
| 11 | 1100 | 0.6138 | 0.0002701297 | — | — | 22.5463 | 0.0000 | 0.4412 |
| 12 | 1200 | 0.5978 | 0.0002673965 | — | — | 22.5829 | 0.0000 | 0.4583 |
| 13 | 1300 | 0.5527 | 0.0002646602 | — | — | 22.5932 | 0.0000 | 0.4664 |
| 14 | 1400 | 0.5859 | 0.0002619207 | — | — | 22.6047 | 0.0000 | 0.4768 |
| 15 | 1500 | 0.5580 | 0.0002591781 | — | — | 22.5929 | 0.0000 | 0.4578 |
| 16 | 1600 | 0.5509 | 0.0002564322 | — | — | 22.5998 | 0.0000 | 0.4656 |
| 17 | 1700 | 0.5291 | 0.0002536831 | — | — | 22.6119 | 0.0000 | 0.4672 |
| 18 | 1800 | 0.4998 | 0.0002509307 | — | — | 22.6256 | 0.0000 | 0.4465 |
| 19 | 1900 | 0.5273 | 0.0002481749 | — | — | 22.6760 | 0.0000 | 0.4658 |
| 20 | 2000 | 0.4784 | 0.0002454156 | 0.4892 | 0.2021 | 22.6253 | 70.4546 | 0.5073 |
| 21 | 2100 | 0.4801 | 0.000242653 | — | — | 22.7161 | 0.0000 | 0.4197 |
| 22 | 2200 | 0.4730 | 0.0002398868 | — | — | 22.5970 | 0.0000 | 0.4595 |
| 23 | 2300 | 0.4599 | 0.0002371171 | — | — | 22.6051 | 0.0000 | 0.4678 |
| 24 | 2400 | 0.4605 | 0.0002343438 | — | — | 22.6252 | 0.0000 | 0.4622 |
| 25 | 2500 | 0.4166 | 0.0002315669 | — | — | 22.6255 | 0.0000 | 0.4584 |
| 26 | 2600 | 0.4590 | 0.0002287862 | — | — | 22.6110 | 0.0000 | 0.4552 |
| 27 | 2700 | 0.4172 | 0.0002260018 | — | — | 22.6057 | 0.0000 | 0.4556 |
| 28 | 2800 | 0.4110 | 0.0002232135 | — | — | 22.6235 | 0.0000 | 0.4582 |
| 29 | 2900 | 0.4156 | 0.0002204214 | — | — | 22.6246 | 0.0000 | 0.4634 |
| 30 | 3000 | 0.4146 | 0.0002176254 | 0.6293 | 0.2467 | 22.6305 | 78.4633 | 0.5071 |
| 31 | 3100 | 0.4110 | 0.0002148253 | — | — | 22.5327 | 0.0000 | 0.4414 |
| 32 | 3200 | 0.3941 | 0.0002120212 | — | — | 22.5885 | 0.0000 | 0.4682 |
| 33 | 3300 | 0.4014 | 0.000209213 | — | — | 22.6151 | 0.0000 | 0.4701 |
| 34 | 3400 | 0.4030 | 0.0002064005 | — | — | 22.6062 | 0.0000 | 0.4702 |
| 35 | 3500 | 0.3894 | 0.0002035838 | — | — | 22.6120 | 0.0000 | 0.4677 |
| 36 | 3600 | 0.3906 | 0.0002007628 | — | — | 22.6235 | 0.0000 | 0.4691 |
| 37 | 3700 | 0.3709 | 0.0001979373 | — | — | 22.6220 | 0.0000 | 0.4736 |
| 38 | 3800 | 0.3851 | 0.0001951074 | — | — | 22.6355 | 0.0000 | 0.5117 |
| 39 | 3900 | 0.3790 | 0.0001922729 | — | — | 22.7696 | 0.0000 | 0.5084 |
| 40 | 4000 | 0.3599 | 0.0001894338 | 0.6125 | 0.2187 | 22.6494 | 72.7945 | 0.5137 |
| 41 | 4100 | 0.4113 | 0.0001865899 | — | — | 22.5364 | 0.0000 | 0.4568 |
| 42 | 4200 | 0.3704 | 0.0001837412 | — | — | 22.5954 | 0.0000 | 0.4475 |
| 43 | 4300 | 0.3874 | 0.0001808875 | — | — | 22.6177 | 0.0000 | 0.4514 |
| 44 | 4400 | 0.3461 | 0.0001780289 | — | — | 22.6460 | 0.0000 | 0.4708 |
| 45 | 4500 | 0.3472 | 0.0001751651 | — | — | 22.6368 | 0.0000 | 0.4697 |
| 46 | 4600 | 0.3321 | 0.0001722962 | — | — | 22.6251 | 0.0000 | 0.4726 |
| 47 | 4700 | 0.3355 | 0.0001694219 | — | — | 22.6362 | 0.0000 | 0.4618 |
| 48 | 4800 | 0.3425 | 0.0001665422 | — | — | 22.6286 | 0.0000 | 0.4528 |
| 49 | 4900 | 0.3329 | 0.0001636569 | — | — | 22.6363 | 0.0000 | 0.4499 |
| 50 | 5000 | 0.3326 | 0.000160766 | 0.7198 | 0.2729 | 22.6310 | 67.6641 | 0.5047 |
| 51 | 5100 | 0.3536 | 0.0001578693 | — | — | 22.5690 | 0.0000 | 0.4339 |
| 52 | 5200 | 0.3327 | 0.0001549667 | — | — | 22.6063 | 0.0000 | 0.4716 |
| 53 | 5300 | 0.3256 | 0.000152058 | — | — | 22.6325 | 0.0000 | 0.4782 |
| 54 | 5400 | 0.3324 | 0.0001491431 | — | — | 22.6290 | 0.0000 | 0.4718 |
| 55 | 5500 | 0.3241 | 0.0001462219 | — | — | 22.6295 | 0.0000 | 0.4689 |

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

