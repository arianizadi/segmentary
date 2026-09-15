# dynunet-isotropic-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T00:38:50.653104+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **7**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T00:08:44.950388+00:00 / — |
| Last worker update | 2026-09-15T00:09:29.401132+00:00 |
| Completed / budget steps | 3400 / 10000 |
| Live step / phase | 3430 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4844 |
| Peak allocated / reserved GiB | 12.53 / 17.41 |

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
    160,
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
    1.5
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
| 1 | 100 | 1.3852 | 0.0002972986 | 0.0000 | 0.0000 | 38.7068 | 117.5803 | 0.4459 |
| 2 | 200 | 1.1382 | 0.0002945946 | — | — | 38.1953 | 0.0000 | 0.4247 |
| 3 | 300 | 1.0365 | 0.0002918877 | — | — | 38.3086 | 0.0000 | 0.5398 |
| 4 | 400 | 0.9501 | 0.0002891781 | — | — | 38.4826 | 0.0000 | 0.4769 |
| 5 | 500 | 0.8878 | 0.0002864656 | — | — | 38.3759 | 0.0000 | 0.4722 |
| 6 | 600 | 0.8277 | 0.0002837503 | — | — | 38.3840 | 0.0000 | 0.4824 |
| 7 | 700 | 0.7898 | 0.0002810321 | — | — | 38.3823 | 0.0000 | 0.4697 |
| 8 | 800 | 0.7354 | 0.000278311 | — | — | 38.4070 | 0.0000 | 0.4734 |
| 9 | 900 | 0.6984 | 0.0002755869 | — | — | 38.4192 | 0.0000 | 0.4782 |
| 10 | 1000 | 0.6653 | 0.0002728598 | 0.4933 | 0.1124 | 38.4135 | 93.0417 | 0.4864 |
| 11 | 1100 | 0.6079 | 0.0002701297 | — | — | 38.1522 | 0.0000 | 0.4430 |
| 12 | 1200 | 0.6050 | 0.0002673965 | — | — | 38.2739 | 0.0000 | 0.4727 |
| 13 | 1300 | 0.5696 | 0.0002646602 | — | — | 38.3436 | 0.0000 | 0.4675 |
| 14 | 1400 | 0.5581 | 0.0002619207 | — | — | 38.3871 | 0.0000 | 0.4686 |
| 15 | 1500 | 0.5391 | 0.0002591781 | — | — | 38.4050 | 0.0000 | 0.4757 |
| 16 | 1600 | 0.5662 | 0.0002564322 | — | — | 38.4237 | 0.0000 | 0.4768 |
| 17 | 1700 | 0.5376 | 0.0002536831 | — | — | 38.4210 | 0.0000 | 0.4722 |
| 18 | 1800 | 0.5304 | 0.0002509307 | — | — | 38.4214 | 0.0000 | 0.4640 |
| 19 | 1900 | 0.5280 | 0.0002481749 | — | — | 38.4219 | 0.0000 | 0.4610 |
| 20 | 2000 | 0.4692 | 0.0002454156 | 0.5030 | 0.2752 | 38.4000 | 90.9110 | 0.4886 |
| 21 | 2100 | 0.4608 | 0.000242653 | — | — | 38.2558 | 0.0000 | 0.4483 |
| 22 | 2200 | 0.4718 | 0.0002398868 | — | — | 38.2967 | 0.0000 | 0.4603 |
| 23 | 2300 | 0.4769 | 0.0002371171 | — | — | 38.3002 | 0.0000 | 0.4774 |
| 24 | 2400 | 0.4834 | 0.0002343438 | — | — | 38.2937 | 0.0000 | 0.4700 |
| 25 | 2500 | 0.4216 | 0.0002315669 | — | — | 38.3764 | 0.0000 | 0.4872 |
| 26 | 2600 | 0.4638 | 0.0002287862 | — | — | 38.2922 | 0.0000 | 0.7545 |
| 27 | 2700 | 0.4240 | 0.0002260018 | — | — | 38.3182 | 0.0000 | 0.4857 |
| 28 | 2800 | 0.4291 | 0.0002232135 | — | — | 38.3209 | 0.0000 | 0.4775 |
| 29 | 2900 | 0.4298 | 0.0002204214 | — | — | 38.3226 | 0.0000 | 0.4617 |
| 30 | 3000 | 0.4191 | 0.0002176254 | 0.6866 | 0.3296 | 38.3302 | 93.8799 | 0.4938 |
| 31 | 3100 | 0.4297 | 0.0002148253 | — | — | 38.1494 | 0.0000 | 0.4439 |
| 32 | 3200 | 0.4175 | 0.0002120212 | — | — | 38.3202 | 0.0000 | 0.4720 |
| 33 | 3300 | 0.4053 | 0.000209213 | — | — | 38.3672 | 0.0000 | 0.4808 |
| 34 | 3400 | 0.4195 | 0.0002064005 | — | — | 38.3274 | 0.0000 | 0.4654 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-isotropic-seed0.json)

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

