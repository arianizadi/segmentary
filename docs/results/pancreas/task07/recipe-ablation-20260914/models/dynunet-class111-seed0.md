# dynunet-class111-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T17:58:31.426550+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

Status: **running**. Stage: **train**. GPU: **3**.

Architecture: **dynunet**. This is a fresh recipe arm, not another architecture or a resumed historical run.

Declared ingredient changes and reference provenance:

```json
{
  "arm": "class111",
  "control_run_id": "dynunet-control-seed0",
  "changes_from_control": {
    "class_center_weights": [
      1.0,
      1.0,
      1.0
    ],
    "foreground_probability": null
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
| Started / finished | 2026-09-14T17:27:58.758642+00:00 / — |
| Last worker update | 2026-09-14T17:28:40.742416+00:00 |
| Completed / budget steps | 5600 / 10000 |
| Live step / phase | 5650 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4941 |
| Peak allocated / reserved GiB | 7.61 / 10.50 |

Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.

```json
{
  "augment": true,
  "backend": "torch",
  "batch_size": 8,
  "center_probabilities": null,
  "class_center_weights": [
    1.0,
    1.0,
    1.0
  ],
  "context_slices": 1,
  "deterministic": false,
  "epochs": 100,
  "foreground_probability": null,
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
| 1 | 100 | 1.3734 | 0.0002972986 | 0.2024 | 0.0000 | 23.0906 | 95.5393 | 0.4919 |
| 2 | 200 | 1.1185 | 0.0002945946 | — | — | 22.6234 | 0.0000 | 0.4390 |
| 3 | 300 | 0.9938 | 0.0002918877 | — | — | 22.6610 | 0.0000 | 0.4758 |
| 4 | 400 | 0.9010 | 0.0002891781 | — | — | 22.8676 | 0.0000 | 0.4577 |
| 5 | 500 | 0.8328 | 0.0002864656 | — | — | 22.6920 | 0.0000 | 0.4710 |
| 6 | 600 | 0.7791 | 0.0002837503 | — | — | 22.7038 | 0.0000 | 0.4607 |
| 7 | 700 | 0.7146 | 0.0002810321 | — | — | 22.9614 | 0.0000 | 0.4777 |
| 8 | 800 | 0.6832 | 0.000278311 | — | — | 22.7378 | 0.0000 | 0.4656 |
| 9 | 900 | 0.6161 | 0.0002755869 | — | — | 22.7500 | 0.0000 | 0.4751 |
| 10 | 1000 | 0.5836 | 0.0002728598 | 0.5475 | 0.2053 | 22.7477 | 73.5765 | 0.5054 |
| 11 | 1100 | 0.5390 | 0.0002701297 | — | — | 22.6685 | 0.0000 | 0.4356 |
| 12 | 1200 | 0.5115 | 0.0002673965 | — | — | 22.7061 | 0.0000 | 0.4606 |
| 13 | 1300 | 0.4941 | 0.0002646602 | — | — | 22.7490 | 0.0000 | 0.4792 |
| 14 | 1400 | 0.4840 | 0.0002619207 | — | — | 22.7613 | 0.0000 | 0.4659 |
| 15 | 1500 | 0.4735 | 0.0002591781 | — | — | 22.7357 | 0.0000 | 0.4642 |
| 16 | 1600 | 0.4531 | 0.0002564322 | — | — | 22.7406 | 0.0000 | 0.4697 |
| 17 | 1700 | 0.4513 | 0.0002536831 | — | — | 22.7565 | 0.0000 | 0.4717 |
| 18 | 1800 | 0.4375 | 0.0002509307 | — | — | 22.7496 | 0.0000 | 0.5214 |
| 19 | 1900 | 0.4144 | 0.0002481749 | — | — | 22.7524 | 0.0000 | 0.4676 |
| 20 | 2000 | 0.4192 | 0.0002454156 | 0.6444 | 0.2304 | 22.7739 | 75.2586 | 0.5014 |
| 21 | 2100 | 0.4114 | 0.000242653 | — | — | 22.6556 | 0.0000 | 0.4313 |
| 22 | 2200 | 0.3913 | 0.0002398868 | — | — | 22.8347 | 0.0000 | 0.4597 |
| 23 | 2300 | 0.4079 | 0.0002371171 | — | — | 22.7483 | 0.0000 | 0.4677 |
| 24 | 2400 | 0.3965 | 0.0002343438 | — | — | 22.7795 | 0.0000 | 0.4667 |
| 25 | 2500 | 0.4042 | 0.0002315669 | — | — | 22.7920 | 0.0000 | 0.4823 |
| 26 | 2600 | 0.3769 | 0.0002287862 | — | — | 22.8000 | 0.0000 | 0.7445 |
| 27 | 2700 | 0.3934 | 0.0002260018 | — | — | 22.7938 | 0.0000 | 0.4474 |
| 28 | 2800 | 0.3766 | 0.0002232135 | — | — | 22.7961 | 0.0000 | 0.4724 |
| 29 | 2900 | 0.3680 | 0.0002204214 | — | — | 22.7624 | 0.0000 | 0.4639 |
| 30 | 3000 | 0.3711 | 0.0002176254 | 0.6812 | 0.2523 | 22.7838 | 70.8562 | 0.4914 |
| 31 | 3100 | 0.3750 | 0.0002148253 | — | — | 22.6634 | 0.0000 | 0.4152 |
| 32 | 3200 | 0.3794 | 0.0002120212 | — | — | 22.7121 | 0.0000 | 0.4704 |
| 33 | 3300 | 0.3640 | 0.000209213 | — | — | 22.7450 | 0.0000 | 0.4498 |
| 34 | 3400 | 0.3395 | 0.0002064005 | — | — | 22.7604 | 0.0000 | 0.4733 |
| 35 | 3500 | 0.3487 | 0.0002035838 | — | — | 22.7920 | 0.0000 | 0.4631 |
| 36 | 3600 | 0.3469 | 0.0002007628 | — | — | 22.8022 | 0.0000 | 0.4618 |
| 37 | 3700 | 0.3324 | 0.0001979373 | — | — | 22.7998 | 0.0000 | 0.4561 |
| 38 | 3800 | 0.3199 | 0.0001951074 | — | — | 22.7829 | 0.0000 | 0.4582 |
| 39 | 3900 | 0.3195 | 0.0001922729 | — | — | 22.8013 | 0.0000 | 0.4692 |
| 40 | 4000 | 0.3344 | 0.0001894338 | 0.6935 | 0.2737 | 22.7696 | 66.1866 | 0.5090 |
| 41 | 4100 | 0.3289 | 0.0001865899 | — | — | 22.6722 | 0.0000 | 0.4247 |
| 42 | 4200 | 0.3017 | 0.0001837412 | — | — | 22.7392 | 0.0000 | 0.4607 |
| 43 | 4300 | 0.2972 | 0.0001808875 | — | — | 22.7803 | 0.0000 | 0.4777 |
| 44 | 4400 | 0.3088 | 0.0001780289 | — | — | 22.7746 | 0.0000 | 0.5154 |
| 45 | 4500 | 0.3371 | 0.0001751651 | — | — | 22.7493 | 0.0000 | 0.4793 |
| 46 | 4600 | 0.3100 | 0.0001722962 | — | — | 22.7648 | 0.0000 | 0.4519 |
| 47 | 4700 | 0.2873 | 0.0001694219 | — | — | 22.7727 | 0.0000 | 0.4683 |
| 48 | 4800 | 0.2915 | 0.0001665422 | — | — | 22.7790 | 0.0000 | 0.4714 |
| 49 | 4900 | 0.3011 | 0.0001636569 | — | — | 22.7787 | 0.0000 | 0.4500 |
| 50 | 5000 | 0.2827 | 0.000160766 | 0.7275 | 0.2786 | 22.7742 | 69.4025 | 0.5118 |
| 51 | 5100 | 0.3293 | 0.0001578693 | — | — | 22.6658 | 0.0000 | 0.4406 |
| 52 | 5200 | 0.3081 | 0.0001549667 | — | — | 22.7268 | 0.0000 | 0.4758 |
| 53 | 5300 | 0.3080 | 0.000152058 | — | — | 22.7666 | 0.0000 | 0.4746 |
| 54 | 5400 | 0.2917 | 0.0001491431 | — | — | 22.7793 | 0.0000 | 0.4594 |
| 55 | 5500 | 0.2697 | 0.0001462219 | — | — | 22.7977 | 0.0000 | 0.4544 |
| 56 | 5600 | 0.2621 | 0.0001432942 | — | — | 22.8027 | 0.0000 | 0.4717 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-class111-seed0.json)

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

