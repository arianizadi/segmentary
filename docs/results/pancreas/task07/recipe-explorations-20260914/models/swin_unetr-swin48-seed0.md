# swin_unetr-swin48-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T02:39:05.694984+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **1**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T01:04:57.844081+00:00 / — |
| Last worker update | 2026-09-15T01:05:37.335208+00:00 |
| Completed / budget steps | 4600 / 10000 |
| Live step / phase | 4620 / train |
| Parameters | 62186757 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 1.5545 |
| Peak allocated / reserved GiB | 16.82 / 26.65 |

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
  "model": "swin_unetr",
  "model_options": {
    "feature_size": 48,
    "use_checkpoint": true
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
| 1 | 100 | 1.3993 | 0.0002972986 | 0.2634 | 0.0000 | 107.0925 | 116.2074 | 1.6074 |
| 2 | 200 | 1.0939 | 0.0002945946 | — | — | 106.4928 | 0.0000 | 1.5744 |
| 3 | 300 | 0.9974 | 0.0002918877 | — | — | 106.5982 | 0.0000 | 1.7553 |
| 4 | 400 | 0.9125 | 0.0002891781 | — | — | 106.5372 | 0.0000 | 1.6609 |
| 5 | 500 | 0.8550 | 0.0002864656 | — | — | 106.5306 | 0.0000 | 1.6436 |
| 6 | 600 | 0.8132 | 0.0002837503 | — | — | 106.5704 | 0.0000 | 1.6456 |
| 7 | 700 | 0.7964 | 0.0002810321 | — | — | 106.5070 | 0.0000 | 1.6518 |
| 8 | 800 | 0.7554 | 0.000278311 | — | — | 106.5853 | 0.0000 | 1.6371 |
| 9 | 900 | 0.7276 | 0.0002755869 | — | — | 106.5392 | 0.0000 | 1.6817 |
| 10 | 1000 | 0.6899 | 0.0002728598 | 0.5145 | 0.0608 | 106.5458 | 114.7343 | 2.2458 |
| 11 | 1100 | 0.6366 | 0.0002701297 | — | — | 106.5533 | 0.0000 | 1.5698 |
| 12 | 1200 | 0.6338 | 0.0002673965 | — | — | 106.5342 | 0.0000 | 1.6559 |
| 13 | 1300 | 0.5916 | 0.0002646602 | — | — | 106.5383 | 0.0000 | 1.6155 |
| 14 | 1400 | 0.5828 | 0.0002619207 | — | — | 106.6116 | 0.0000 | 1.6694 |
| 15 | 1500 | 0.5806 | 0.0002591781 | — | — | 106.5279 | 0.0000 | 1.6861 |
| 16 | 1600 | 0.5860 | 0.0002564322 | — | — | 106.5348 | 0.0000 | 1.7004 |
| 17 | 1700 | 0.5628 | 0.0002536831 | — | — | 106.5717 | 0.0000 | 1.6659 |
| 18 | 1800 | 0.5370 | 0.0002509307 | — | — | 106.5555 | 0.0000 | 1.7172 |
| 19 | 1900 | 0.5605 | 0.0002481749 | — | — | 106.6105 | 0.0000 | 1.6826 |
| 20 | 2000 | 0.5175 | 0.0002454156 | 0.5304 | 0.1286 | 106.5663 | 115.0394 | 1.8178 |
| 21 | 2100 | 0.5089 | 0.000242653 | — | — | 106.4933 | 0.0000 | 1.5549 |
| 22 | 2200 | 0.5128 | 0.0002398868 | — | — | 106.5775 | 0.0000 | 1.6506 |
| 23 | 2300 | 0.5104 | 0.0002371171 | — | — | 106.5401 | 0.0000 | 1.6465 |
| 24 | 2400 | 0.5003 | 0.0002343438 | — | — | 106.5455 | 0.0000 | 1.6462 |
| 25 | 2500 | 0.4611 | 0.0002315669 | — | — | 106.5364 | 0.0000 | 1.6707 |
| 26 | 2600 | 0.5011 | 0.0002287862 | — | — | 106.5417 | 0.0000 | 1.7143 |
| 27 | 2700 | 0.4686 | 0.0002260018 | — | — | 106.5834 | 0.0000 | 1.6473 |
| 28 | 2800 | 0.4738 | 0.0002232135 | — | — | 106.5242 | 0.0000 | 1.6860 |
| 29 | 2900 | 0.4582 | 0.0002204214 | — | — | 106.5271 | 0.0000 | 1.6761 |
| 30 | 3000 | 0.4702 | 0.0002176254 | 0.6552 | 0.1815 | 106.5390 | 115.5843 | 1.8092 |
| 31 | 3100 | 0.4870 | 0.0002148253 | — | — | 106.5411 | 0.0000 | 1.6102 |
| 32 | 3200 | 0.4536 | 0.0002120212 | — | — | 106.5892 | 0.0000 | 1.6292 |
| 33 | 3300 | 0.4412 | 0.000209213 | — | — | 106.6603 | 0.0000 | 1.7037 |
| 34 | 3400 | 0.4408 | 0.0002064005 | — | — | 106.5991 | 0.0000 | 1.6539 |
| 35 | 3500 | 0.4177 | 0.0002035838 | — | — | 106.6078 | 0.0000 | 1.7203 |
| 36 | 3600 | 0.4251 | 0.0002007628 | — | — | 106.6046 | 0.0000 | 1.6583 |
| 37 | 3700 | 0.3906 | 0.0001979373 | — | — | 106.5841 | 0.0000 | 1.6791 |
| 38 | 3800 | 0.3965 | 0.0001951074 | — | — | 106.6204 | 0.0000 | 1.6682 |
| 39 | 3900 | 0.3911 | 0.0001922729 | — | — | 106.5921 | 0.0000 | 1.6641 |
| 40 | 4000 | 0.3777 | 0.0001894338 | 0.6876 | 0.2272 | 106.6478 | 114.9133 | 1.7651 |
| 41 | 4100 | 0.4215 | 0.0001865899 | — | — | 106.5552 | 0.0000 | 1.5870 |
| 42 | 4200 | 0.3988 | 0.0001837412 | — | — | 106.5400 | 0.0000 | 1.9420 |
| 43 | 4300 | 0.4007 | 0.0001808875 | — | — | 106.6108 | 0.0000 | 1.6881 |
| 44 | 4400 | 0.3738 | 0.0001780289 | — | — | 106.5865 | 0.0000 | 1.6819 |
| 45 | 4500 | 0.3704 | 0.0001751651 | — | — | 106.5650 | 0.0000 | 1.5928 |
| 46 | 4600 | 0.3646 | 0.0001722962 | — | — | 106.6127 | 0.0000 | 1.6527 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/swin_unetr-swin48-seed0.json)

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

