# dynunet-rotation-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T17:58:31.426550+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

Status: **running**. Stage: **train**. GPU: **5**.

Architecture: **dynunet**. This is a fresh recipe arm, not another architecture or a resumed historical run.

Declared ingredient changes and reference provenance:

```json
{
  "arm": "rotation",
  "control_run_id": "dynunet-control-seed0",
  "changes_from_control": {
    "rotation_degrees": [
      -15.0,
      15.0
    ],
    "rotation_padding_value": 0.0,
    "rotation_probability": 0.25
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
| Started / finished | 2026-09-14T17:27:58.762714+00:00 / — |
| Last worker update | 2026-09-14T17:28:41.294872+00:00 |
| Completed / budget steps | 5600 / 10000 |
| Live step / phase | 5640 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4940 |
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
  "rotation_probability": 0.25,
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
| 1 | 100 | 1.3851 | 0.0002972986 | 0.0580 | 0.0000 | 24.8450 | 93.3779 | 0.4639 |
| 2 | 200 | 1.1317 | 0.0002945946 | — | — | 22.7117 | 0.0000 | 0.5072 |
| 3 | 300 | 1.0266 | 0.0002918877 | — | — | 22.7909 | 0.0000 | 0.5087 |
| 4 | 400 | 0.9429 | 0.0002891781 | — | — | 23.1063 | 0.0000 | 0.5577 |
| 5 | 500 | 0.8664 | 0.0002864656 | — | — | 22.8838 | 0.0000 | 0.4944 |
| 6 | 600 | 0.8182 | 0.0002837503 | — | — | 22.9506 | 0.0000 | 0.5115 |
| 7 | 700 | 0.7781 | 0.0002810321 | — | — | 22.9573 | 0.0000 | 0.5776 |
| 8 | 800 | 0.7263 | 0.000278311 | — | — | 22.8201 | 0.0000 | 0.4564 |
| 9 | 900 | 0.6852 | 0.0002755869 | — | — | 22.8603 | 0.0000 | 0.4855 |
| 10 | 1000 | 0.6429 | 0.0002728598 | 0.5155 | 0.1432 | 22.7938 | 68.4439 | 0.5388 |
| 11 | 1100 | 0.6206 | 0.0002701297 | — | — | 22.7692 | 0.0000 | 0.4399 |
| 12 | 1200 | 0.5781 | 0.0002673965 | — | — | 22.7468 | 0.0000 | 0.4597 |
| 13 | 1300 | 0.5483 | 0.0002646602 | — | — | 22.9648 | 0.0000 | 0.4647 |
| 14 | 1400 | 0.5441 | 0.0002619207 | — | — | 22.8945 | 0.0000 | 0.4659 |
| 15 | 1500 | 0.4942 | 0.0002591781 | — | — | 22.8419 | 0.0000 | 0.4652 |
| 16 | 1600 | 0.5018 | 0.0002564322 | — | — | 22.9307 | 0.0000 | 0.4671 |
| 17 | 1700 | 0.4922 | 0.0002536831 | — | — | 22.8607 | 0.0000 | 0.4672 |
| 18 | 1800 | 0.4831 | 0.0002509307 | — | — | 22.7575 | 0.0000 | 0.4492 |
| 19 | 1900 | 0.4850 | 0.0002481749 | — | — | 22.8908 | 0.0000 | 0.4749 |
| 20 | 2000 | 0.4495 | 0.0002454156 | 0.5366 | 0.1869 | 22.8439 | 69.3631 | 0.4811 |
| 21 | 2100 | 0.4523 | 0.000242653 | — | — | 23.2397 | 0.0000 | 0.4307 |
| 22 | 2200 | 0.4586 | 0.0002398868 | — | — | 23.1336 | 0.0000 | 0.4507 |
| 23 | 2300 | 0.4756 | 0.0002371171 | — | — | 22.9699 | 0.0000 | 0.4822 |
| 24 | 2400 | 0.4230 | 0.0002343438 | — | — | 22.8101 | 0.0000 | 0.4654 |
| 25 | 2500 | 0.4029 | 0.0002315669 | — | — | 22.8217 | 0.0000 | 0.5070 |
| 26 | 2600 | 0.4325 | 0.0002287862 | — | — | 23.0491 | 0.0000 | 0.4641 |
| 27 | 2700 | 0.4277 | 0.0002260018 | — | — | 23.0309 | 0.0000 | 0.5074 |
| 28 | 2800 | 0.4329 | 0.0002232135 | — | — | 22.9200 | 0.0000 | 0.4611 |
| 29 | 2900 | 0.4230 | 0.0002204214 | — | — | 23.0350 | 0.0000 | 0.5161 |
| 30 | 3000 | 0.3755 | 0.0002176254 | 0.6683 | 0.2689 | 22.8373 | 71.5813 | 0.5013 |
| 31 | 3100 | 0.4088 | 0.0002148253 | — | — | 22.8238 | 0.0000 | 0.4240 |
| 32 | 3200 | 0.3948 | 0.0002120212 | — | — | 22.9142 | 0.0000 | 0.4474 |
| 33 | 3300 | 0.4068 | 0.000209213 | — | — | 22.9156 | 0.0000 | 0.4606 |
| 34 | 3400 | 0.4147 | 0.0002064005 | — | — | 22.8773 | 0.0000 | 0.4639 |
| 35 | 3500 | 0.3777 | 0.0002035838 | — | — | 22.8149 | 0.0000 | 0.4501 |
| 36 | 3600 | 0.4089 | 0.0002007628 | — | — | 22.8309 | 0.0000 | 0.4637 |
| 37 | 3700 | 0.3506 | 0.0001979373 | — | — | 22.9376 | 0.0000 | 0.4653 |
| 38 | 3800 | 0.3708 | 0.0001951074 | — | — | 22.7808 | 0.0000 | 0.4641 |
| 39 | 3900 | 0.3662 | 0.0001922729 | — | — | 23.1242 | 0.0000 | 0.4669 |
| 40 | 4000 | 0.3971 | 0.0001894338 | 0.7010 | 0.2861 | 22.8652 | 70.1440 | 0.4777 |
| 41 | 4100 | 0.3708 | 0.0001865899 | — | — | 22.6965 | 0.0000 | 0.4389 |
| 42 | 4200 | 0.3614 | 0.0001837412 | — | — | 22.9573 | 0.0000 | 0.4521 |
| 43 | 4300 | 0.3490 | 0.0001808875 | — | — | 22.9212 | 0.0000 | 0.4643 |
| 44 | 4400 | 0.3519 | 0.0001780289 | — | — | 22.8932 | 0.0000 | 0.5134 |
| 45 | 4500 | 0.3268 | 0.0001751651 | — | — | 22.9996 | 0.0000 | 0.4552 |
| 46 | 4600 | 0.3599 | 0.0001722962 | — | — | 22.8515 | 0.0000 | 0.4491 |
| 47 | 4700 | 0.3630 | 0.0001694219 | — | — | 22.9733 | 0.0000 | 0.4518 |
| 48 | 4800 | 0.3565 | 0.0001665422 | — | — | 22.9944 | 0.0000 | 0.4658 |
| 49 | 4900 | 0.3368 | 0.0001636569 | — | — | 22.9783 | 0.0000 | 0.4515 |
| 50 | 5000 | 0.3391 | 0.000160766 | 0.6704 | 0.2783 | 22.8126 | 71.5874 | 0.4518 |
| 51 | 5100 | 0.3490 | 0.0001578693 | — | — | 22.7823 | 0.0000 | 0.4507 |
| 52 | 5200 | 0.3124 | 0.0001549667 | — | — | 22.8884 | 0.0000 | 0.4491 |
| 53 | 5300 | 0.3535 | 0.000152058 | — | — | 22.8592 | 0.0000 | 0.4656 |
| 54 | 5400 | 0.3462 | 0.0001491431 | — | — | 22.8475 | 0.0000 | 0.4628 |
| 55 | 5500 | 0.3485 | 0.0001462219 | — | — | 22.8024 | 0.0000 | 0.4635 |
| 56 | 5600 | 0.3226 | 0.0001432942 | — | — | 23.0391 | 0.0000 | 0.4633 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-rotation-seed0.json)

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

