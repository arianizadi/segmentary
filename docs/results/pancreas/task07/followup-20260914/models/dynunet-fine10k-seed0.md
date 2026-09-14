# dynunet-fine10k-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T21:30:08.948358+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

Status: **running**. Stage: **train**. GPU: **3**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T21:00:04.521047+00:00 / — |
| Last worker update | 2026-09-14T21:00:53.861239+00:00 |
| Completed / budget steps | 2600 / 10000 |
| Live step / phase | 2630 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4820 |
| Peak allocated / reserved GiB | 16.84 / 23.48 |

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
    144,
    144
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
    1.0,
    1.0,
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
| 1 | 100 | 1.3814 | 0.0002972986 | 0.2422 | 0.0000 | 51.7112 | 133.8042 | 0.4147 |
| 2 | 200 | 1.1328 | 0.0002945946 | — | — | 51.3761 | 0.0000 | 0.4308 |
| 3 | 300 | 1.0354 | 0.0002918877 | — | — | 51.6076 | 0.0000 | 0.4436 |
| 4 | 400 | 0.9468 | 0.0002891781 | — | — | 51.7637 | 0.0000 | 0.4362 |
| 5 | 500 | 0.8802 | 0.0002864656 | — | — | 51.7597 | 0.0000 | 0.4363 |
| 6 | 600 | 0.8245 | 0.0002837503 | — | — | 51.7793 | 0.0000 | 0.4573 |
| 7 | 700 | 0.7833 | 0.0002810321 | — | — | 51.7277 | 0.0000 | 0.4510 |
| 8 | 800 | 0.7444 | 0.000278311 | — | — | 51.7572 | 0.0000 | 0.4440 |
| 9 | 900 | 0.7128 | 0.0002755869 | — | — | 51.7722 | 0.0000 | 0.4396 |
| 10 | 1000 | 0.6752 | 0.0002728598 | 0.5343 | 0.1483 | 51.7773 | 103.4895 | 0.4610 |
| 11 | 1100 | 0.6077 | 0.0002701297 | — | — | 51.5126 | 0.0000 | 0.4243 |
| 12 | 1200 | 0.5988 | 0.0002673965 | — | — | 51.6877 | 0.0000 | 0.4478 |
| 13 | 1300 | 0.5795 | 0.0002646602 | — | — | 51.7634 | 0.0000 | 0.4450 |
| 14 | 1400 | 0.5715 | 0.0002619207 | — | — | 51.7114 | 0.0000 | 0.4621 |
| 15 | 1500 | 0.5453 | 0.0002591781 | — | — | 51.7572 | 0.0000 | 0.4529 |
| 16 | 1600 | 0.5765 | 0.0002564322 | — | — | 51.7649 | 0.0000 | 0.4496 |
| 17 | 1700 | 0.5218 | 0.0002536831 | — | — | 51.7699 | 0.0000 | 0.4334 |
| 18 | 1800 | 0.4964 | 0.0002509307 | — | — | 51.7806 | 0.0000 | 0.4296 |
| 19 | 1900 | 0.5356 | 0.0002481749 | — | — | 51.7892 | 0.0000 | 0.4634 |
| 20 | 2000 | 0.4743 | 0.0002454156 | 0.6482 | 0.2620 | 51.7798 | 101.7590 | 0.4845 |
| 21 | 2100 | 0.4730 | 0.000242653 | — | — | 51.5351 | 0.0000 | 0.4323 |
| 22 | 2200 | 0.4814 | 0.0002398868 | — | — | 51.6824 | 0.0000 | 0.4381 |
| 23 | 2300 | 0.4679 | 0.0002371171 | — | — | 51.7674 | 0.0000 | 0.4595 |
| 24 | 2400 | 0.4712 | 0.0002343438 | — | — | 51.8192 | 0.0000 | 0.4590 |
| 25 | 2500 | 0.4139 | 0.0002315669 | — | — | 51.8581 | 0.0000 | 0.4546 |
| 26 | 2600 | 0.4704 | 0.0002287862 | — | — | 51.8784 | 0.0000 | 0.4535 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-fine10k-seed0.json)

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

