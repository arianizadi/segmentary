# dynunet-long30k-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T21:30:08.948358+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

Status: **running**. Stage: **train**. GPU: **2**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T21:00:04.519208+00:00 / — |
| Last worker update | 2026-09-14T21:00:45.146972+00:00 |
| Completed / budget steps | 5500 / 30000 |
| Live step / phase | 5570 / train |
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
  "epochs": 300,
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
| 1 | 100 | 1.3883 | 0.0002990998 | 0.1364 | 0.0000 | 23.0673 | 88.0417 | 0.4071 |
| 2 | 200 | 1.1419 | 0.0002981994 | — | — | 22.5318 | 0.0000 | 0.4016 |
| 3 | 300 | 1.0399 | 0.0002972986 | — | — | 22.5980 | 0.0000 | 0.4187 |
| 4 | 400 | 0.9471 | 0.0002963976 | — | — | 22.8114 | 0.0000 | 0.4645 |
| 5 | 500 | 0.8792 | 0.0002954962 | — | — | 22.7164 | 0.0000 | 0.4467 |
| 6 | 600 | 0.8211 | 0.0002945946 | — | — | 22.7151 | 0.0000 | 0.4165 |
| 7 | 700 | 0.7820 | 0.0002936926 | — | — | 22.7460 | 0.0000 | 0.4450 |
| 8 | 800 | 0.7416 | 0.0002927903 | — | — | 22.7748 | 0.0000 | 0.4300 |
| 9 | 900 | 0.7084 | 0.0002918877 | — | — | 22.7611 | 0.0000 | 0.4765 |
| 10 | 1000 | 0.6750 | 0.0002909848 | 0.4807 | 0.1002 | 22.7641 | 74.0730 | 0.4702 |
| 11 | 1100 | 0.6096 | 0.0002900816 | — | — | 22.6498 | 0.0000 | 0.4334 |
| 12 | 1200 | 0.5953 | 0.0002891781 | — | — | 22.7076 | 0.0000 | 0.4249 |
| 13 | 1300 | 0.5678 | 0.0002882742 | — | — | 22.7138 | 0.0000 | 0.4549 |
| 14 | 1400 | 0.5833 | 0.0002873701 | — | — | 22.7499 | 0.0000 | 0.4246 |
| 15 | 1500 | 0.6078 | 0.0002864656 | — | — | 22.7622 | 0.0000 | 0.4346 |
| 16 | 1600 | 0.5647 | 0.0002855608 | — | — | 22.7514 | 0.0000 | 0.7160 |
| 17 | 1700 | 0.5145 | 0.0002846557 | — | — | 22.7652 | 0.0000 | 0.4508 |
| 18 | 1800 | 0.4970 | 0.0002837503 | — | — | 22.7751 | 0.0000 | 0.4463 |
| 19 | 1900 | 0.5839 | 0.0002828445 | — | — | 22.7904 | 0.0000 | 0.4519 |
| 20 | 2000 | 0.4854 | 0.0002819385 | 0.5466 | 0.2206 | 22.7995 | 66.6933 | 0.4881 |
| 21 | 2100 | 0.4725 | 0.0002810321 | — | — | 22.6597 | 0.0000 | 0.5815 |
| 22 | 2200 | 0.4770 | 0.0002801254 | — | — | 22.6961 | 0.0000 | 0.4451 |
| 23 | 2300 | 0.4814 | 0.0002792183 | — | — | 22.7162 | 0.0000 | 0.4614 |
| 24 | 2400 | 0.4864 | 0.000278311 | — | — | 22.7502 | 0.0000 | 0.4542 |
| 25 | 2500 | 0.4452 | 0.0002774033 | — | — | 22.7728 | 0.0000 | 0.4310 |
| 26 | 2600 | 0.4697 | 0.0002764952 | — | — | 22.8047 | 0.0000 | 0.4214 |
| 27 | 2700 | 0.4403 | 0.0002755869 | — | — | 22.7909 | 0.0000 | 0.4449 |
| 28 | 2800 | 0.4272 | 0.0002746782 | — | — | 22.7864 | 0.0000 | 0.4324 |
| 29 | 2900 | 0.4220 | 0.0002737691 | — | — | 22.7893 | 0.0000 | 0.4291 |
| 30 | 3000 | 0.4218 | 0.0002728598 | 0.6207 | 0.2429 | 22.7970 | 78.1285 | 0.4719 |
| 31 | 3100 | 0.4360 | 0.0002719501 | — | — | 22.6612 | 0.0000 | 0.3974 |
| 32 | 3200 | 0.4082 | 0.00027104 | — | — | 22.6827 | 0.0000 | 0.4298 |
| 33 | 3300 | 0.4331 | 0.0002701297 | — | — | 22.7236 | 0.0000 | 0.4305 |
| 34 | 3400 | 0.4136 | 0.0002692189 | — | — | 22.7515 | 0.0000 | 0.4279 |
| 35 | 3500 | 0.4106 | 0.0002683079 | — | — | 22.7368 | 0.0000 | 0.4276 |
| 36 | 3600 | 0.4052 | 0.0002673965 | — | — | 22.7637 | 0.0000 | 0.4474 |
| 37 | 3700 | 0.3851 | 0.0002664847 | — | — | 22.7715 | 0.0000 | 0.4375 |
| 38 | 3800 | 0.3951 | 0.0002655726 | — | — | 22.7870 | 0.0000 | 0.4224 |
| 39 | 3900 | 0.3958 | 0.0002646602 | — | — | 22.9270 | 0.0000 | 0.4432 |
| 40 | 4000 | 0.3749 | 0.0002637474 | 0.6527 | 0.2571 | 22.8002 | 66.5685 | 0.4735 |
| 41 | 4100 | 0.4088 | 0.0002628342 | — | — | 22.6751 | 0.0000 | 0.3954 |
| 42 | 4200 | 0.3750 | 0.0002619207 | — | — | 22.7037 | 0.0000 | 0.4307 |
| 43 | 4300 | 0.3973 | 0.0002610069 | — | — | 22.7323 | 0.0000 | 0.4295 |
| 44 | 4400 | 0.3747 | 0.0002600927 | — | — | 22.7221 | 0.0000 | 0.4251 |
| 45 | 4500 | 0.3681 | 0.0002591781 | — | — | 22.7452 | 0.0000 | 0.4361 |
| 46 | 4600 | 0.3600 | 0.0002582632 | — | — | 22.7653 | 0.0000 | 0.4486 |
| 47 | 4700 | 0.3659 | 0.0002573479 | — | — | 22.7758 | 0.0000 | 0.4479 |
| 48 | 4800 | 0.3584 | 0.0002564322 | — | — | 22.7856 | 0.0000 | 0.4286 |
| 49 | 4900 | 0.3489 | 0.0002555162 | — | — | 22.7938 | 0.0000 | 0.4376 |
| 50 | 5000 | 0.3651 | 0.0002545998 | 0.7193 | 0.2836 | 22.8131 | 71.7301 | 0.4732 |
| 51 | 5100 | 0.3743 | 0.0002536831 | — | — | 22.6695 | 0.0000 | 0.4074 |
| 52 | 5200 | 0.3861 | 0.000252766 | — | — | 22.6938 | 0.0000 | 0.4393 |
| 53 | 5300 | 0.3481 | 0.0002518485 | — | — | 22.7296 | 0.0000 | 0.4404 |
| 54 | 5400 | 0.3490 | 0.0002509307 | — | — | 22.7626 | 0.0000 | 0.4251 |
| 55 | 5500 | 0.3350 | 0.0002500124 | — | — | 22.7879 | 0.0000 | 0.4387 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-long30k-seed0.json)

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

