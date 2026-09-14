# dynunet-mass50-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T17:58:31.426550+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

Status: **running**. Stage: **train**. GPU: **2**.

Architecture: **dynunet**. This is a fresh recipe arm, not another architecture or a resumed historical run.

Declared ingredient changes and reference provenance:

```json
{
  "arm": "mass50",
  "control_run_id": "dynunet-control-seed0",
  "changes_from_control": {
    "center_probabilities": [
      0.25,
      0.25,
      0.5
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
| Started / finished | 2026-09-14T17:27:58.756921+00:00 / — |
| Last worker update | 2026-09-14T17:28:41.090851+00:00 |
| Completed / budget steps | 5600 / 10000 |
| Live step / phase | 5680 / train |
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
  "center_probabilities": [
    0.25,
    0.25,
    0.5
  ],
  "class_center_weights": null,
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
| 1 | 100 | 1.3736 | 0.0002972986 | 0.1230 | 0.0000 | 23.1428 | 95.3154 | 0.4415 |
| 2 | 200 | 1.1108 | 0.0002945946 | — | — | 22.5439 | 0.0000 | 0.4736 |
| 3 | 300 | 0.9754 | 0.0002918877 | — | — | 22.6174 | 0.0000 | 0.5017 |
| 4 | 400 | 0.8793 | 0.0002891781 | — | — | 22.7600 | 0.0000 | 0.4670 |
| 5 | 500 | 0.8134 | 0.0002864656 | — | — | 22.6661 | 0.0000 | 0.4588 |
| 6 | 600 | 0.7606 | 0.0002837503 | — | — | 22.6800 | 0.0000 | 0.4531 |
| 7 | 700 | 0.7019 | 0.0002810321 | — | — | 22.6894 | 0.0000 | 0.4726 |
| 8 | 800 | 0.6727 | 0.000278311 | — | — | 22.6960 | 0.0000 | 0.4632 |
| 9 | 900 | 0.5902 | 0.0002755869 | — | — | 22.6773 | 0.0000 | 0.4577 |
| 10 | 1000 | 0.5641 | 0.0002728598 | 0.4656 | 0.1185 | 22.6685 | 68.9588 | 0.4985 |
| 11 | 1100 | 0.5060 | 0.0002701297 | — | — | 22.6078 | 0.0000 | 0.4333 |
| 12 | 1200 | 0.5190 | 0.0002673965 | — | — | 22.6700 | 0.0000 | 0.4683 |
| 13 | 1300 | 0.4759 | 0.0002646602 | — | — | 22.6984 | 0.0000 | 0.4700 |
| 14 | 1400 | 0.4621 | 0.0002619207 | — | — | 22.7107 | 0.0000 | 0.4714 |
| 15 | 1500 | 0.4291 | 0.0002591781 | — | — | 22.7060 | 0.0000 | 0.4679 |
| 16 | 1600 | 0.4426 | 0.0002564322 | — | — | 22.7145 | 0.0000 | 0.4537 |
| 17 | 1700 | 0.4207 | 0.0002536831 | — | — | 22.7130 | 0.0000 | 0.4687 |
| 18 | 1800 | 0.4425 | 0.0002509307 | — | — | 22.7061 | 0.0000 | 0.4630 |
| 19 | 1900 | 0.4220 | 0.0002481749 | — | — | 22.6903 | 0.0000 | 0.4645 |
| 20 | 2000 | 0.3935 | 0.0002454156 | 0.5928 | 0.2194 | 22.7124 | 74.9638 | 0.5054 |
| 21 | 2100 | 0.3892 | 0.000242653 | — | — | 22.7420 | 0.0000 | 0.4207 |
| 22 | 2200 | 0.3926 | 0.0002398868 | — | — | 22.6717 | 0.0000 | 0.4758 |
| 23 | 2300 | 0.3721 | 0.0002371171 | — | — | 22.6884 | 0.0000 | 0.4585 |
| 24 | 2400 | 0.4009 | 0.0002343438 | — | — | 22.6974 | 0.0000 | 0.4542 |
| 25 | 2500 | 0.3724 | 0.0002315669 | — | — | 22.7106 | 0.0000 | 0.4605 |
| 26 | 2600 | 0.3764 | 0.0002287862 | — | — | 22.6956 | 0.0000 | 0.4666 |
| 27 | 2700 | 0.3433 | 0.0002260018 | — | — | 22.6691 | 0.0000 | 0.4696 |
| 28 | 2800 | 0.3614 | 0.0002232135 | — | — | 22.6778 | 0.0000 | 0.4552 |
| 29 | 2900 | 0.3194 | 0.0002204214 | — | — | 22.6918 | 0.0000 | 0.5197 |
| 30 | 3000 | 0.3555 | 0.0002176254 | 0.6712 | 0.2927 | 22.6736 | 69.8122 | 0.4918 |
| 31 | 3100 | 0.3251 | 0.0002148253 | — | — | 22.6267 | 0.0000 | 0.4201 |
| 32 | 3200 | 0.3083 | 0.0002120212 | — | — | 22.6776 | 0.0000 | 0.4551 |
| 33 | 3300 | 0.3395 | 0.000209213 | — | — | 22.6932 | 0.0000 | 0.4670 |
| 34 | 3400 | 0.3131 | 0.0002064005 | — | — | 22.7012 | 0.0000 | 0.4666 |
| 35 | 3500 | 0.3059 | 0.0002035838 | — | — | 22.7077 | 0.0000 | 0.4605 |
| 36 | 3600 | 0.3050 | 0.0002007628 | — | — | 22.7055 | 0.0000 | 0.4668 |
| 37 | 3700 | 0.3060 | 0.0001979373 | — | — | 22.6784 | 0.0000 | 0.4671 |
| 38 | 3800 | 0.3089 | 0.0001951074 | — | — | 22.6899 | 0.0000 | 0.4633 |
| 39 | 3900 | 0.2751 | 0.0001922729 | — | — | 22.8219 | 0.0000 | 0.4590 |
| 40 | 4000 | 0.3247 | 0.0001894338 | 0.7107 | 0.2634 | 22.6831 | 70.4452 | 0.4727 |
| 41 | 4100 | 0.3011 | 0.0001865899 | — | — | 22.6102 | 0.0000 | 0.4493 |
| 42 | 4200 | 0.2951 | 0.0001837412 | — | — | 22.6721 | 0.0000 | 0.4502 |
| 43 | 4300 | 0.2945 | 0.0001808875 | — | — | 22.6860 | 0.0000 | 0.4588 |
| 44 | 4400 | 0.3023 | 0.0001780289 | — | — | 22.6946 | 0.0000 | 0.4693 |
| 45 | 4500 | 0.2993 | 0.0001751651 | — | — | 22.7207 | 0.0000 | 0.4972 |
| 46 | 4600 | 0.2639 | 0.0001722962 | — | — | 22.7146 | 0.0000 | 0.5147 |
| 47 | 4700 | 0.2710 | 0.0001694219 | — | — | 22.7220 | 0.0000 | 0.4736 |
| 48 | 4800 | 0.2661 | 0.0001665422 | — | — | 22.7167 | 0.0000 | 0.4639 |
| 49 | 4900 | 0.2594 | 0.0001636569 | — | — | 22.7206 | 0.0000 | 0.4739 |
| 50 | 5000 | 0.2650 | 0.000160766 | 0.7167 | 0.2736 | 22.7041 | 68.2137 | 0.4870 |
| 51 | 5100 | 0.2564 | 0.0001578693 | — | — | 22.6083 | 0.0000 | 0.4697 |
| 52 | 5200 | 0.2649 | 0.0001549667 | — | — | 22.6621 | 0.0000 | 0.4857 |
| 53 | 5300 | 0.2588 | 0.000152058 | — | — | 22.6836 | 0.0000 | 0.4740 |
| 54 | 5400 | 0.2602 | 0.0001491431 | — | — | 22.7016 | 0.0000 | 0.4591 |
| 55 | 5500 | 0.2455 | 0.0001462219 | — | — | 22.7147 | 0.0000 | 0.4631 |
| 56 | 5600 | 0.2554 | 0.0001432942 | — | — | 22.8894 | 0.0000 | 0.4781 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-mass50-seed0.json)

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

