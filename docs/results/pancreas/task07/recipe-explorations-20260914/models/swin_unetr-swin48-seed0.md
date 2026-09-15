# swin_unetr-swin48-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T01:38:58.142087+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **1**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T01:04:57.844081+00:00 / — |
| Last worker update | 2026-09-15T01:05:37.335208+00:00 |
| Completed / budget steps | 1600 / 10000 |
| Live step / phase | 1610 / train |
| Parameters | 62186757 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5524 |
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

