# dynunet-control10k-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T02:41:56.708661+00:00. Source: `993e6413341dbc5c39ec46cdf5f846e246215b4f`.

Status: **running**. Stage: **train**. GPU: **2**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T02:11:52.009071+00:00 / — |
| Last worker update | 2026-09-15T02:12:32.864096+00:00 |
| Completed / budget steps | 5400 / 10000 |
| Live step / phase | 5480 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4864 |
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
| 1 | 100 | 1.3888 | 0.0002972986 | 0.1619 | 0.0000 | 23.0434 | 93.9606 | 0.4595 |
| 2 | 200 | 1.1421 | 0.0002945946 | — | — | 22.5723 | 0.0000 | 0.4403 |
| 3 | 300 | 1.0401 | 0.0002918877 | — | — | 22.6490 | 0.0000 | 0.4623 |
| 4 | 400 | 0.9500 | 0.0002891781 | — | — | 22.8491 | 0.0000 | 0.4726 |
| 5 | 500 | 0.8793 | 0.0002864656 | — | — | 22.7261 | 0.0000 | 0.4766 |
| 6 | 600 | 0.8235 | 0.0002837503 | — | — | 22.7429 | 0.0000 | 0.4851 |
| 7 | 700 | 0.7786 | 0.0002810321 | — | — | 22.7531 | 0.0000 | 0.4702 |
| 8 | 800 | 0.7446 | 0.000278311 | — | — | 22.7802 | 0.0000 | 0.4783 |
| 9 | 900 | 0.7122 | 0.0002755869 | — | — | 22.7999 | 0.0000 | 0.4914 |
| 10 | 1000 | 0.6705 | 0.0002728598 | 0.4947 | 0.1309 | 22.7795 | 72.0696 | 0.5040 |
| 11 | 1100 | 0.6138 | 0.0002701297 | — | — | 22.6728 | 0.0000 | 0.4498 |
| 12 | 1200 | 0.5978 | 0.0002673965 | — | — | 22.7316 | 0.0000 | 0.4861 |
| 13 | 1300 | 0.5527 | 0.0002646602 | — | — | 22.7551 | 0.0000 | 0.4565 |
| 14 | 1400 | 0.5859 | 0.0002619207 | — | — | 22.7681 | 0.0000 | 0.4618 |
| 15 | 1500 | 0.5580 | 0.0002591781 | — | — | 22.7833 | 0.0000 | 0.4594 |
| 16 | 1600 | 0.5509 | 0.0002564322 | — | — | 22.8112 | 0.0000 | 0.4656 |
| 17 | 1700 | 0.5291 | 0.0002536831 | — | — | 22.8099 | 0.0000 | 0.4817 |
| 18 | 1800 | 0.4998 | 0.0002509307 | — | — | 22.7910 | 0.0000 | 0.4569 |
| 19 | 1900 | 0.5273 | 0.0002481749 | — | — | 22.8057 | 0.0000 | 0.4609 |
| 20 | 2000 | 0.4784 | 0.0002454156 | 0.4892 | 0.2021 | 22.7913 | 72.9909 | 0.5030 |
| 21 | 2100 | 0.4801 | 0.000242653 | — | — | 22.8269 | 0.0000 | 0.4331 |
| 22 | 2200 | 0.4730 | 0.0002398868 | — | — | 22.6985 | 0.0000 | 0.4580 |
| 23 | 2300 | 0.4599 | 0.0002371171 | — | — | 22.7353 | 0.0000 | 0.4688 |
| 24 | 2400 | 0.4605 | 0.0002343438 | — | — | 22.7413 | 0.0000 | 0.4710 |
| 25 | 2500 | 0.4166 | 0.0002315669 | — | — | 22.7435 | 0.0000 | 0.4498 |
| 26 | 2600 | 0.4590 | 0.0002287862 | — | — | 22.7530 | 0.0000 | 0.4586 |
| 27 | 2700 | 0.4172 | 0.0002260018 | — | — | 22.7671 | 0.0000 | 0.4566 |
| 28 | 2800 | 0.4110 | 0.0002232135 | — | — | 22.7835 | 0.0000 | 0.4692 |
| 29 | 2900 | 0.4156 | 0.0002204214 | — | — | 22.7888 | 0.0000 | 0.4804 |
| 30 | 3000 | 0.4146 | 0.0002176254 | 0.6293 | 0.2467 | 22.8100 | 75.2066 | 0.5087 |
| 31 | 3100 | 0.4110 | 0.0002148253 | — | — | 22.6637 | 0.0000 | 0.4288 |
| 32 | 3200 | 0.3941 | 0.0002120212 | — | — | 22.6845 | 0.0000 | 0.4751 |
| 33 | 3300 | 0.4014 | 0.000209213 | — | — | 22.7213 | 0.0000 | 0.4714 |
| 34 | 3400 | 0.4030 | 0.0002064005 | — | — | 22.7228 | 0.0000 | 0.4736 |
| 35 | 3500 | 0.3894 | 0.0002035838 | — | — | 22.7487 | 0.0000 | 0.4766 |
| 36 | 3600 | 0.3906 | 0.0002007628 | — | — | 22.7676 | 0.0000 | 0.4847 |
| 37 | 3700 | 0.3709 | 0.0001979373 | — | — | 22.7841 | 0.0000 | 0.4728 |
| 38 | 3800 | 0.3851 | 0.0001951074 | — | — | 22.7864 | 0.0000 | 0.4760 |
| 39 | 3900 | 0.3790 | 0.0001922729 | — | — | 22.9291 | 0.0000 | 0.4814 |
| 40 | 4000 | 0.3599 | 0.0001894338 | 0.6125 | 0.2187 | 22.7958 | 79.4810 | 0.4988 |
| 41 | 4100 | 0.4113 | 0.0001865899 | — | — | 22.6590 | 0.0000 | 0.5630 |
| 42 | 4200 | 0.3704 | 0.0001837412 | — | — | 22.7072 | 0.0000 | 0.4862 |
| 43 | 4300 | 0.3874 | 0.0001808875 | — | — | 22.7430 | 0.0000 | 0.4640 |
| 44 | 4400 | 0.3461 | 0.0001780289 | — | — | 22.7712 | 0.0000 | 0.4533 |
| 45 | 4500 | 0.3472 | 0.0001751651 | — | — | 22.7872 | 0.0000 | 0.4529 |
| 46 | 4600 | 0.3321 | 0.0001722962 | — | — | 22.7773 | 0.0000 | 0.4795 |
| 47 | 4700 | 0.3355 | 0.0001694219 | — | — | 22.7863 | 0.0000 | 0.4867 |
| 48 | 4800 | 0.3425 | 0.0001665422 | — | — | 22.7984 | 0.0000 | 0.4831 |
| 49 | 4900 | 0.3329 | 0.0001636569 | — | — | 22.7980 | 0.0000 | 0.4544 |
| 50 | 5000 | 0.3326 | 0.000160766 | 0.7198 | 0.2729 | 22.8034 | 70.8767 | 0.5004 |
| 51 | 5100 | 0.3536 | 0.0001578693 | — | — | 22.6675 | 0.0000 | 0.4119 |
| 52 | 5200 | 0.3327 | 0.0001549667 | — | — | 22.6970 | 0.0000 | 0.4481 |
| 53 | 5300 | 0.3256 | 0.000152058 | — | — | 22.7297 | 0.0000 | 0.4528 |
| 54 | 5400 | 0.3324 | 0.0001491431 | — | — | 22.7729 | 0.0000 | 0.4622 |

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

