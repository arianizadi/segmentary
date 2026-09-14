# dynunet-intensity-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T17:58:31.426550+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

Status: **running**. Stage: **train**. GPU: **6**.

Architecture: **dynunet**. This is a fresh recipe arm, not another architecture or a resumed historical run.

Declared ingredient changes and reference provenance:

```json
{
  "arm": "intensity",
  "control_run_id": "dynunet-control-seed0",
  "changes_from_control": {
    "intensity_scale_probability": 0.5,
    "intensity_scale_range": [
      0.9,
      1.1
    ]
  },
  "reference_source_commit": "9f7615bd1f6035d65aca3f848a263b67c49f531f",
  "reference_recipe_sha256": "d043ec219016e79541f5d061d143acbf12bb29d200a02a3439fd9211d4868a6a",
  "reference_binding_sha256": "1f6d670eb0ace3c0612dc26d498cc4bf31c94d7a2af889b556fc4ae393e01936",
  "reference_campaign_sha256": "54c079d120146be5a3f0ccfeb61bcf865203175478959569f9f7b3e700907787"
}
```

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T17:27:58.764236+00:00 / — |
| Last worker update | 2026-09-14T17:28:42.040883+00:00 |
| Completed / budget steps | 5500 / 10000 |
| Live step / phase | 5580 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4937 |
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
  "intensity_scale_probability": 0.5,
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
| 1 | 100 | 1.3880 | 0.0002972986 | 0.0339 | 0.0000 | 23.4586 | 93.7662 | 0.4796 |
| 2 | 200 | 1.1394 | 0.0002945946 | — | — | 22.8346 | 0.0000 | 0.5178 |
| 3 | 300 | 1.0335 | 0.0002918877 | — | — | 22.8438 | 0.0000 | 0.5507 |
| 4 | 400 | 0.9469 | 0.0002891781 | — | — | 23.0178 | 0.0000 | 0.5454 |
| 5 | 500 | 0.8724 | 0.0002864656 | — | — | 22.8735 | 0.0000 | 0.5128 |
| 6 | 600 | 0.8164 | 0.0002837503 | — | — | 22.8834 | 0.0000 | 0.5377 |
| 7 | 700 | 0.7828 | 0.0002810321 | — | — | 22.8799 | 0.0000 | 0.4864 |
| 8 | 800 | 0.7433 | 0.000278311 | — | — | 22.8911 | 0.0000 | 0.4750 |
| 9 | 900 | 0.7183 | 0.0002755869 | — | — | 22.8982 | 0.0000 | 0.5144 |
| 10 | 1000 | 0.7011 | 0.0002728598 | 0.5184 | 0.1121 | 22.8996 | 70.7495 | 0.5249 |
| 11 | 1100 | 0.6433 | 0.0002701297 | — | — | 22.8293 | 0.0000 | 0.4411 |
| 12 | 1200 | 0.6092 | 0.0002673965 | — | — | 22.8573 | 0.0000 | 0.4483 |
| 13 | 1300 | 0.5594 | 0.0002646602 | — | — | 22.8623 | 0.0000 | 0.4679 |
| 14 | 1400 | 0.5470 | 0.0002619207 | — | — | 22.8748 | 0.0000 | 0.4551 |
| 15 | 1500 | 0.5433 | 0.0002591781 | — | — | 22.8764 | 0.0000 | 0.4671 |
| 16 | 1600 | 0.5185 | 0.0002564322 | — | — | 22.8826 | 0.0000 | 0.4706 |
| 17 | 1700 | 0.5066 | 0.0002536831 | — | — | 22.8870 | 0.0000 | 0.4743 |
| 18 | 1800 | 0.4761 | 0.0002509307 | — | — | 22.8816 | 0.0000 | 0.5236 |
| 19 | 1900 | 0.4709 | 0.0002481749 | — | — | 22.8799 | 0.0000 | 0.4652 |
| 20 | 2000 | 0.5045 | 0.0002454156 | 0.6618 | 0.2421 | 22.8836 | 70.6291 | 0.5072 |
| 21 | 2100 | 0.4483 | 0.000242653 | — | — | 22.9907 | 0.0000 | 0.4200 |
| 22 | 2200 | 0.4634 | 0.0002398868 | — | — | 22.8488 | 0.0000 | 0.4687 |
| 23 | 2300 | 0.4378 | 0.0002371171 | — | — | 22.8757 | 0.0000 | 0.4566 |
| 24 | 2400 | 0.4665 | 0.0002343438 | — | — | 22.8958 | 0.0000 | 0.4710 |
| 25 | 2500 | 0.4576 | 0.0002315669 | — | — | 22.8969 | 0.0000 | 0.4524 |
| 26 | 2600 | 0.4637 | 0.0002287862 | — | — | 22.8894 | 0.0000 | 0.4530 |
| 27 | 2700 | 0.4024 | 0.0002260018 | — | — | 22.8868 | 0.0000 | 0.4520 |
| 28 | 2800 | 0.4247 | 0.0002232135 | — | — | 22.8757 | 0.0000 | 0.4513 |
| 29 | 2900 | 0.4200 | 0.0002204214 | — | — | 22.8821 | 0.0000 | 0.4576 |
| 30 | 3000 | 0.4076 | 0.0002176254 | 0.6001 | 0.2829 | 22.8713 | 81.2944 | 0.4934 |
| 31 | 3100 | 0.3877 | 0.0002148253 | — | — | 22.8356 | 0.0000 | 0.4250 |
| 32 | 3200 | 0.3997 | 0.0002120212 | — | — | 22.8479 | 0.0000 | 0.4849 |
| 33 | 3300 | 0.4229 | 0.000209213 | — | — | 22.8660 | 0.0000 | 0.4547 |
| 34 | 3400 | 0.3961 | 0.0002064005 | — | — | 22.8803 | 0.0000 | 0.4539 |
| 35 | 3500 | 0.3838 | 0.0002035838 | — | — | 22.8884 | 0.0000 | 0.4563 |
| 36 | 3600 | 0.3872 | 0.0002007628 | — | — | 22.8927 | 0.0000 | 0.4481 |
| 37 | 3700 | 0.3909 | 0.0001979373 | — | — | 22.9005 | 0.0000 | 0.4651 |
| 38 | 3800 | 0.3727 | 0.0001951074 | — | — | 22.8979 | 0.0000 | 0.4562 |
| 39 | 3900 | 0.3651 | 0.0001922729 | — | — | 22.9275 | 0.0000 | 0.4553 |
| 40 | 4000 | 0.3630 | 0.0001894338 | 0.6848 | 0.2620 | 22.8960 | 74.1709 | 0.4491 |
| 41 | 4100 | 0.3496 | 0.0001865899 | — | — | 22.8573 | 0.0000 | 0.4837 |
| 42 | 4200 | 0.3427 | 0.0001837412 | — | — | 22.8494 | 0.0000 | 0.4591 |
| 43 | 4300 | 0.3796 | 0.0001808875 | — | — | 22.8731 | 0.0000 | 0.4570 |
| 44 | 4400 | 0.3561 | 0.0001780289 | — | — | 22.8881 | 0.0000 | 0.4583 |
| 45 | 4500 | 0.3487 | 0.0001751651 | — | — | 22.8782 | 0.0000 | 0.4528 |
| 46 | 4600 | 0.3793 | 0.0001722962 | — | — | 22.8831 | 0.0000 | 0.4667 |
| 47 | 4700 | 0.3528 | 0.0001694219 | — | — | 22.8854 | 0.0000 | 0.4701 |
| 48 | 4800 | 0.3392 | 0.0001665422 | — | — | 22.8968 | 0.0000 | 0.4728 |
| 49 | 4900 | 0.3558 | 0.0001636569 | — | — | 22.8936 | 0.0000 | 0.4540 |
| 50 | 5000 | 0.3521 | 0.000160766 | 0.7193 | 0.2607 | 22.8888 | 69.4400 | 0.4813 |
| 51 | 5100 | 0.3355 | 0.0001578693 | — | — | 22.8391 | 0.0000 | 0.4716 |
| 52 | 5200 | 0.3529 | 0.0001549667 | — | — | 22.8402 | 0.0000 | 0.4788 |
| 53 | 5300 | 0.3330 | 0.000152058 | — | — | 22.8719 | 0.0000 | 0.4629 |
| 54 | 5400 | 0.3312 | 0.0001491431 | — | — | 22.8917 | 0.0000 | 0.4543 |
| 55 | 5500 | 0.3447 | 0.0001462219 | — | — | 22.8925 | 0.0000 | 0.4603 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-intensity-seed0.json)

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

