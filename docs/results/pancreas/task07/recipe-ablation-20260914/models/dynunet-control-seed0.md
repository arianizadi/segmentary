# dynunet-control-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T17:58:31.426550+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

Status: **running**. Stage: **train**. GPU: **1**.

Architecture: **dynunet**. This is a fresh recipe arm, not another architecture or a resumed historical run.

Declared ingredient changes and reference provenance:

```json
{
  "arm": "control",
  "control_run_id": "dynunet-control-seed0",
  "changes_from_control": {},
  "reference_source_commit": "9f7615bd1f6035d65aca3f848a263b67c49f531f",
  "reference_recipe_sha256": "d043ec219016e79541f5d061d143acbf12bb29d200a02a3439fd9211d4868a6a",
  "reference_binding_sha256": "1f6d670eb0ace3c0612dc26d498cc4bf31c94d7a2af889b556fc4ae393e01936",
  "reference_campaign_sha256": "54c079d120146be5a3f0ccfeb61bcf865203175478959569f9f7b3e700907787"
}
```

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T17:27:58.755109+00:00 / — |
| Last worker update | 2026-09-14T17:28:41.674572+00:00 |
| Completed / budget steps | 5600 / 10000 |
| Live step / phase | 5670 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4939 |
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
| 1 | 100 | 1.3888 | 0.0002972986 | 0.1619 | 0.0000 | 23.2562 | 94.6378 | 0.4974 |
| 2 | 200 | 1.1421 | 0.0002945946 | — | — | 22.5559 | 0.0000 | 0.4932 |
| 3 | 300 | 1.0401 | 0.0002918877 | — | — | 22.5923 | 0.0000 | 0.5502 |
| 4 | 400 | 0.9500 | 0.0002891781 | — | — | 22.7669 | 0.0000 | 0.4706 |
| 5 | 500 | 0.8793 | 0.0002864656 | — | — | 22.6891 | 0.0000 | 0.4687 |
| 6 | 600 | 0.8235 | 0.0002837503 | — | — | 22.6684 | 0.0000 | 0.7716 |
| 7 | 700 | 0.7786 | 0.0002810321 | — | — | 22.6622 | 0.0000 | 0.4634 |
| 8 | 800 | 0.7446 | 0.000278311 | — | — | 22.6757 | 0.0000 | 0.4739 |
| 9 | 900 | 0.7122 | 0.0002755869 | — | — | 22.6453 | 0.0000 | 0.4600 |
| 10 | 1000 | 0.6705 | 0.0002728598 | 0.4947 | 0.1309 | 22.6517 | 72.1983 | 0.4986 |
| 11 | 1100 | 0.6138 | 0.0002701297 | — | — | 22.5663 | 0.0000 | 0.4417 |
| 12 | 1200 | 0.5978 | 0.0002673965 | — | — | 22.6194 | 0.0000 | 0.4586 |
| 13 | 1300 | 0.5527 | 0.0002646602 | — | — | 22.6314 | 0.0000 | 0.4648 |
| 14 | 1400 | 0.5859 | 0.0002619207 | — | — | 22.6435 | 0.0000 | 0.4567 |
| 15 | 1500 | 0.5580 | 0.0002591781 | — | — | 22.6526 | 0.0000 | 0.4555 |
| 16 | 1600 | 0.5509 | 0.0002564322 | — | — | 22.6304 | 0.0000 | 0.4690 |
| 17 | 1700 | 0.5291 | 0.0002536831 | — | — | 22.6318 | 0.0000 | 0.4563 |
| 18 | 1800 | 0.4998 | 0.0002509307 | — | — | 22.6368 | 0.0000 | 0.4563 |
| 19 | 1900 | 0.5273 | 0.0002481749 | — | — | 22.6454 | 0.0000 | 0.4777 |
| 20 | 2000 | 0.4784 | 0.0002454156 | 0.4892 | 0.2021 | 22.6484 | 70.8646 | 0.4894 |
| 21 | 2100 | 0.4801 | 0.000242653 | — | — | 22.6125 | 0.0000 | 0.4189 |
| 22 | 2200 | 0.4730 | 0.0002398868 | — | — | 22.6137 | 0.0000 | 0.4555 |
| 23 | 2300 | 0.4599 | 0.0002371171 | — | — | 22.6282 | 0.0000 | 0.5161 |
| 24 | 2400 | 0.4605 | 0.0002343438 | — | — | 22.6418 | 0.0000 | 0.4798 |
| 25 | 2500 | 0.4166 | 0.0002315669 | — | — | 22.6359 | 0.0000 | 0.4860 |
| 26 | 2600 | 0.4590 | 0.0002287862 | — | — | 22.6225 | 0.0000 | 0.4713 |
| 27 | 2700 | 0.4172 | 0.0002260018 | — | — | 22.6317 | 0.0000 | 0.4660 |
| 28 | 2800 | 0.4110 | 0.0002232135 | — | — | 22.6337 | 0.0000 | 0.4579 |
| 29 | 2900 | 0.4156 | 0.0002204214 | — | — | 22.6379 | 0.0000 | 0.4572 |
| 30 | 3000 | 0.4146 | 0.0002176254 | 0.6293 | 0.2467 | 22.6443 | 70.8301 | 0.5025 |
| 31 | 3100 | 0.4110 | 0.0002148253 | — | — | 22.5598 | 0.0000 | 0.4324 |
| 32 | 3200 | 0.3941 | 0.0002120212 | — | — | 22.5907 | 0.0000 | 0.4606 |
| 33 | 3300 | 0.4014 | 0.000209213 | — | — | 22.6176 | 0.0000 | 0.4678 |
| 34 | 3400 | 0.4030 | 0.0002064005 | — | — | 22.6317 | 0.0000 | 0.4674 |
| 35 | 3500 | 0.3894 | 0.0002035838 | — | — | 22.6412 | 0.0000 | 0.4519 |
| 36 | 3600 | 0.3906 | 0.0002007628 | — | — | 22.6517 | 0.0000 | 0.4517 |
| 37 | 3700 | 0.3709 | 0.0001979373 | — | — | 22.6584 | 0.0000 | 0.4723 |
| 38 | 3800 | 0.3851 | 0.0001951074 | — | — | 22.6641 | 0.0000 | 0.4685 |
| 39 | 3900 | 0.3790 | 0.0001922729 | — | — | 22.7897 | 0.0000 | 0.4569 |
| 40 | 4000 | 0.3599 | 0.0001894338 | 0.6125 | 0.2187 | 22.6742 | 72.4065 | 0.4773 |
| 41 | 4100 | 0.4113 | 0.0001865899 | — | — | 22.5655 | 0.0000 | 0.4561 |
| 42 | 4200 | 0.3704 | 0.0001837412 | — | — | 22.5909 | 0.0000 | 0.4647 |
| 43 | 4300 | 0.3874 | 0.0001808875 | — | — | 22.6174 | 0.0000 | 0.4758 |
| 44 | 4400 | 0.3461 | 0.0001780289 | — | — | 22.6351 | 0.0000 | 0.4573 |
| 45 | 4500 | 0.3472 | 0.0001751651 | — | — | 22.6058 | 0.0000 | 0.4748 |
| 46 | 4600 | 0.3321 | 0.0001722962 | — | — | 22.6071 | 0.0000 | 0.5016 |
| 47 | 4700 | 0.3355 | 0.0001694219 | — | — | 22.6135 | 0.0000 | 0.4625 |
| 48 | 4800 | 0.3425 | 0.0001665422 | — | — | 22.6206 | 0.0000 | 0.4587 |
| 49 | 4900 | 0.3329 | 0.0001636569 | — | — | 22.6357 | 0.0000 | 0.4576 |
| 50 | 5000 | 0.3326 | 0.000160766 | 0.7198 | 0.2729 | 22.6287 | 72.9061 | 0.5169 |
| 51 | 5100 | 0.3536 | 0.0001578693 | — | — | 22.5595 | 0.0000 | 0.4556 |
| 52 | 5200 | 0.3327 | 0.0001549667 | — | — | 22.5942 | 0.0000 | 0.4704 |
| 53 | 5300 | 0.3256 | 0.000152058 | — | — | 22.6198 | 0.0000 | 0.4813 |
| 54 | 5400 | 0.3324 | 0.0001491431 | — | — | 22.6479 | 0.0000 | 0.4622 |
| 55 | 5500 | 0.3241 | 0.0001462219 | — | — | 22.6451 | 0.0000 | 0.4655 |
| 56 | 5600 | 0.3183 | 0.0001432942 | — | — | 22.6261 | 0.0000 | 0.4861 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-control-seed0.json)

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

