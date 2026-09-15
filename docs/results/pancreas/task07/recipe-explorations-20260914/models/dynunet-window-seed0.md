# dynunet-window-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T00:38:50.653104+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **5**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T00:08:44.946888+00:00 / — |
| Last worker update | 2026-09-15T00:09:27.474027+00:00 |
| Completed / budget steps | 5500 / 10000 |
| Live step / phase | 5501 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4861 |
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
    -175.0,
    250.0
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
| 1 | 100 | 1.3786 | 0.0002972986 | 0.0408 | 0.0000 | 23.3990 | 98.7729 | 0.4507 |
| 2 | 200 | 1.1373 | 0.0002945946 | — | — | 22.6345 | 0.0000 | 0.4367 |
| 3 | 300 | 1.0405 | 0.0002918877 | — | — | 22.6881 | 0.0000 | 0.4750 |
| 4 | 400 | 0.9567 | 0.0002891781 | — | — | 22.8875 | 0.0000 | 0.5026 |
| 5 | 500 | 0.8872 | 0.0002864656 | — | — | 22.7574 | 0.0000 | 0.4677 |
| 6 | 600 | 0.8289 | 0.0002837503 | — | — | 22.7818 | 0.0000 | 0.4665 |
| 7 | 700 | 0.7861 | 0.0002810321 | — | — | 22.7741 | 0.0000 | 0.4641 |
| 8 | 800 | 0.7523 | 0.000278311 | — | — | 22.7723 | 0.0000 | 0.4769 |
| 9 | 900 | 0.7168 | 0.0002755869 | — | — | 22.7559 | 0.0000 | 0.4763 |
| 10 | 1000 | 0.6879 | 0.0002728598 | 0.5158 | 0.1083 | 22.7764 | 72.9269 | 0.4900 |
| 11 | 1100 | 0.6228 | 0.0002701297 | — | — | 22.6865 | 0.0000 | 0.4292 |
| 12 | 1200 | 0.6023 | 0.0002673965 | — | — | 22.7357 | 0.0000 | 0.4589 |
| 13 | 1300 | 0.5777 | 0.0002646602 | — | — | 22.7522 | 0.0000 | 0.4761 |
| 14 | 1400 | 0.5693 | 0.0002619207 | — | — | 22.7693 | 0.0000 | 0.4812 |
| 15 | 1500 | 0.5652 | 0.0002591781 | — | — | 22.7792 | 0.0000 | 0.4525 |
| 16 | 1600 | 0.5559 | 0.0002564322 | — | — | 22.7895 | 0.0000 | 0.4588 |
| 17 | 1700 | 0.5320 | 0.0002536831 | — | — | 22.7676 | 0.0000 | 0.4670 |
| 18 | 1800 | 0.5090 | 0.0002509307 | — | — | 22.7682 | 0.0000 | 0.5266 |
| 19 | 1900 | 0.5437 | 0.0002481749 | — | — | 22.7958 | 0.0000 | 0.4824 |
| 20 | 2000 | 0.4845 | 0.0002454156 | 0.4657 | 0.1923 | 22.7886 | 69.2439 | 0.4918 |
| 21 | 2100 | 0.4720 | 0.000242653 | — | — | 22.8310 | 0.0000 | 0.4323 |
| 22 | 2200 | 0.4732 | 0.0002398868 | — | — | 22.7491 | 0.0000 | 0.4708 |
| 23 | 2300 | 0.4685 | 0.0002371171 | — | — | 22.7763 | 0.0000 | 0.4848 |
| 24 | 2400 | 0.4661 | 0.0002343438 | — | — | 22.7940 | 0.0000 | 0.4846 |
| 25 | 2500 | 0.4276 | 0.0002315669 | — | — | 22.7857 | 0.0000 | 0.4764 |
| 26 | 2600 | 0.4618 | 0.0002287862 | — | — | 22.7771 | 0.0000 | 0.4728 |
| 27 | 2700 | 0.4217 | 0.0002260018 | — | — | 22.7840 | 0.0000 | 0.4779 |
| 28 | 2800 | 0.4208 | 0.0002232135 | — | — | 22.7890 | 0.0000 | 0.4670 |
| 29 | 2900 | 0.4327 | 0.0002204214 | — | — | 22.7967 | 0.0000 | 0.4504 |
| 30 | 3000 | 0.4159 | 0.0002176254 | 0.5785 | 0.2100 | 22.7971 | 67.1608 | 0.4989 |
| 31 | 3100 | 0.4188 | 0.0002148253 | — | — | 22.6912 | 0.0000 | 0.4285 |
| 32 | 3200 | 0.4079 | 0.0002120212 | — | — | 22.7434 | 0.0000 | 0.4612 |
| 33 | 3300 | 0.4095 | 0.000209213 | — | — | 22.7673 | 0.0000 | 0.4720 |
| 34 | 3400 | 0.4130 | 0.0002064005 | — | — | 22.7624 | 0.0000 | 0.4545 |
| 35 | 3500 | 0.3932 | 0.0002035838 | — | — | 22.7488 | 0.0000 | 0.4552 |
| 36 | 3600 | 0.3832 | 0.0002007628 | — | — | 22.7703 | 0.0000 | 0.4676 |
| 37 | 3700 | 0.3777 | 0.0001979373 | — | — | 22.7803 | 0.0000 | 0.4887 |
| 38 | 3800 | 0.3692 | 0.0001951074 | — | — | 22.7800 | 0.0000 | 0.5299 |
| 39 | 3900 | 0.3744 | 0.0001922729 | — | — | 22.8098 | 0.0000 | 0.4849 |
| 40 | 4000 | 0.3543 | 0.0001894338 | 0.6324 | 0.1995 | 22.7869 | 74.3657 | 0.4786 |
| 41 | 4100 | 0.4055 | 0.0001865899 | — | — | 22.6746 | 0.0000 | 0.4674 |
| 42 | 4200 | 0.3681 | 0.0001837412 | — | — | 22.7228 | 0.0000 | 0.4557 |
| 43 | 4300 | 0.3772 | 0.0001808875 | — | — | 22.7709 | 0.0000 | 0.4641 |
| 44 | 4400 | 0.3592 | 0.0001780289 | — | — | 22.7852 | 0.0000 | 0.4867 |
| 45 | 4500 | 0.3514 | 0.0001751651 | — | — | 22.7810 | 0.0000 | 0.4636 |
| 46 | 4600 | 0.3354 | 0.0001722962 | — | — | 22.7937 | 0.0000 | 0.4859 |
| 47 | 4700 | 0.3319 | 0.0001694219 | — | — | 22.7993 | 0.0000 | 0.4824 |
| 48 | 4800 | 0.3440 | 0.0001665422 | — | — | 22.7972 | 0.0000 | 0.4758 |
| 49 | 4900 | 0.3260 | 0.0001636569 | — | — | 22.7671 | 0.0000 | 0.5177 |
| 50 | 5000 | 0.3476 | 0.000160766 | 0.7110 | 0.2953 | 22.7629 | 74.2944 | 0.5195 |
| 51 | 5100 | 0.3546 | 0.0001578693 | — | — | 22.7099 | 0.0000 | 0.4485 |
| 52 | 5200 | 0.3242 | 0.0001549667 | — | — | 22.7423 | 0.0000 | 0.4613 |
| 53 | 5300 | 0.3268 | 0.000152058 | — | — | 22.7749 | 0.0000 | 0.4805 |
| 54 | 5400 | 0.3304 | 0.0001491431 | — | — | 22.7940 | 0.0000 | 0.4661 |
| 55 | 5500 | 0.3104 | 0.0001462219 | — | — | 22.7922 | 0.0000 | 0.4563 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-window-seed0.json)

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

