# dynunet-class115-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T17:58:31.426550+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

Status: **running**. Stage: **train**. GPU: **4**.

Architecture: **dynunet**. This is a fresh recipe arm, not another architecture or a resumed historical run.

Declared ingredient changes and reference provenance:

```json
{
  "arm": "class115",
  "control_run_id": "dynunet-control-seed0",
  "changes_from_control": {
    "class_center_weights": [
      1.0,
      1.0,
      5.0
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
| Started / finished | 2026-09-14T17:27:58.760939+00:00 / — |
| Last worker update | 2026-09-14T17:28:41.595532+00:00 |
| Completed / budget steps | 5600 / 10000 |
| Live step / phase | 5660 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4938 |
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
    5.0
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
| 1 | 100 | 1.3676 | 0.0002972986 | 0.1765 | 0.0000 | 23.2893 | 94.5269 | 0.4887 |
| 2 | 200 | 1.0916 | 0.0002945946 | — | — | 22.6132 | 0.0000 | 0.4687 |
| 3 | 300 | 0.9617 | 0.0002918877 | — | — | 22.6964 | 0.0000 | 0.5248 |
| 4 | 400 | 0.8661 | 0.0002891781 | — | — | 23.0131 | 0.0000 | 0.5251 |
| 5 | 500 | 0.7990 | 0.0002864656 | — | — | 22.7008 | 0.0000 | 0.4783 |
| 6 | 600 | 0.7315 | 0.0002837503 | — | — | 22.7726 | 0.0000 | 0.5417 |
| 7 | 700 | 0.6723 | 0.0002810321 | — | — | 22.7303 | 0.0000 | 0.4736 |
| 8 | 800 | 0.6064 | 0.000278311 | — | — | 22.7425 | 0.0000 | 0.4555 |
| 9 | 900 | 0.5315 | 0.0002755869 | — | — | 22.7539 | 0.0000 | 0.4446 |
| 10 | 1000 | 0.5014 | 0.0002728598 | 0.5695 | 0.1564 | 22.7563 | 69.3158 | 0.5501 |
| 11 | 1100 | 0.4837 | 0.0002701297 | — | — | 22.6473 | 0.0000 | 0.4285 |
| 12 | 1200 | 0.4693 | 0.0002673965 | — | — | 22.6986 | 0.0000 | 0.4806 |
| 13 | 1300 | 0.4195 | 0.0002646602 | — | — | 22.7211 | 0.0000 | 0.4576 |
| 14 | 1400 | 0.4139 | 0.0002619207 | — | — | 22.7401 | 0.0000 | 0.4641 |
| 15 | 1500 | 0.4308 | 0.0002591781 | — | — | 22.7121 | 0.0000 | 0.4538 |
| 16 | 1600 | 0.3910 | 0.0002564322 | — | — | 22.7198 | 0.0000 | 0.4659 |
| 17 | 1700 | 0.3985 | 0.0002536831 | — | — | 22.7200 | 0.0000 | 0.4489 |
| 18 | 1800 | 0.3875 | 0.0002509307 | — | — | 22.7200 | 0.0000 | 0.4653 |
| 19 | 1900 | 0.3700 | 0.0002481749 | — | — | 22.7274 | 0.0000 | 0.4656 |
| 20 | 2000 | 0.3631 | 0.0002454156 | 0.4976 | 0.1438 | 22.7275 | 72.7869 | 0.4711 |
| 21 | 2100 | 0.3634 | 0.000242653 | — | — | 22.7829 | 0.0000 | 0.4663 |
| 22 | 2200 | 0.3458 | 0.0002398868 | — | — | 22.6850 | 0.0000 | 0.4662 |
| 23 | 2300 | 0.3475 | 0.0002371171 | — | — | 22.7151 | 0.0000 | 0.4708 |
| 24 | 2400 | 0.3565 | 0.0002343438 | — | — | 22.7108 | 0.0000 | 0.4699 |
| 25 | 2500 | 0.3409 | 0.0002315669 | — | — | 22.7186 | 0.0000 | 0.4648 |
| 26 | 2600 | 0.3371 | 0.0002287862 | — | — | 22.7203 | 0.0000 | 0.4623 |
| 27 | 2700 | 0.3530 | 0.0002260018 | — | — | 22.7241 | 0.0000 | 0.4917 |
| 28 | 2800 | 0.3290 | 0.0002232135 | — | — | 22.7242 | 0.0000 | 0.4792 |
| 29 | 2900 | 0.3078 | 0.0002204214 | — | — | 22.7319 | 0.0000 | 0.4666 |
| 30 | 3000 | 0.3099 | 0.0002176254 | 0.6124 | 0.2228 | 22.7382 | 74.6211 | 0.4855 |
| 31 | 3100 | 0.2939 | 0.0002148253 | — | — | 22.6364 | 0.0000 | 0.4391 |
| 32 | 3200 | 0.2954 | 0.0002120212 | — | — | 22.6860 | 0.0000 | 0.4811 |
| 33 | 3300 | 0.2818 | 0.000209213 | — | — | 22.7034 | 0.0000 | 0.4610 |
| 34 | 3400 | 0.2882 | 0.0002064005 | — | — | 22.7079 | 0.0000 | 0.4676 |
| 35 | 3500 | 0.3044 | 0.0002035838 | — | — | 22.7069 | 0.0000 | 0.4665 |
| 36 | 3600 | 0.2689 | 0.0002007628 | — | — | 22.7161 | 0.0000 | 0.4651 |
| 37 | 3700 | 0.2495 | 0.0001979373 | — | — | 22.7204 | 0.0000 | 0.4634 |
| 38 | 3800 | 0.2552 | 0.0001951074 | — | — | 22.7264 | 0.0000 | 0.4693 |
| 39 | 3900 | 0.2465 | 0.0001922729 | — | — | 22.8874 | 0.0000 | 0.4667 |
| 40 | 4000 | 0.2848 | 0.0001894338 | 0.6550 | 0.1869 | 22.7304 | 67.5414 | 0.4569 |
| 41 | 4100 | 0.2675 | 0.0001865899 | — | — | 22.6554 | 0.0000 | 0.4657 |
| 42 | 4200 | 0.2608 | 0.0001837412 | — | — | 22.7072 | 0.0000 | 0.4520 |
| 43 | 4300 | 0.2441 | 0.0001808875 | — | — | 22.7394 | 0.0000 | 0.4468 |
| 44 | 4400 | 0.2408 | 0.0001780289 | — | — | 22.7474 | 0.0000 | 0.4462 |
| 45 | 4500 | 0.2388 | 0.0001751651 | — | — | 22.7973 | 0.0000 | 0.4711 |
| 46 | 4600 | 0.2490 | 0.0001722962 | — | — | 22.7605 | 0.0000 | 0.4503 |
| 47 | 4700 | 0.2314 | 0.0001694219 | — | — | 22.7728 | 0.0000 | 0.4574 |
| 48 | 4800 | 0.2218 | 0.0001665422 | — | — | 22.7483 | 0.0000 | 0.4695 |
| 49 | 4900 | 0.2650 | 0.0001636569 | — | — | 22.7354 | 0.0000 | 0.4672 |
| 50 | 5000 | 0.2312 | 0.000160766 | 0.6682 | 0.2714 | 22.7483 | 69.9895 | 0.4820 |
| 51 | 5100 | 0.2356 | 0.0001578693 | — | — | 22.6499 | 0.0000 | 0.4135 |
| 52 | 5200 | 0.2235 | 0.0001549667 | — | — | 22.7026 | 0.0000 | 0.4686 |
| 53 | 5300 | 0.2137 | 0.000152058 | — | — | 22.7274 | 0.0000 | 0.4479 |
| 54 | 5400 | 0.2101 | 0.0001491431 | — | — | 22.7442 | 0.0000 | 0.4713 |
| 55 | 5500 | 0.2069 | 0.0001462219 | — | — | 22.7556 | 0.0000 | 0.4774 |
| 56 | 5600 | 0.2179 | 0.0001432942 | — | — | 22.7668 | 0.0000 | 0.4640 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-class115-seed0.json)

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

