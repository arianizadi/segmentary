# nnunet_resenc_l

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T17:42:40.743272+00:00. Source: `63a108f8b7a65a98b11ccae0e8883c54955b2099`.

Status: **prepared**. Stage: **—**. GPU: **1**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T17:38:21.348484+00:00 / 2026-09-15T17:39:01.913309+00:00 |
| Last worker update | 2026-09-15T17:39:01.913327+00:00 |
| Completed / budget steps | 0 / — |
| Live step / phase | — / — |
| Parameters | — |
| Objective | — |
| Checkpoint selection | official_ema_foreground_dice |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | — |
| Active-stage allocated hours (estimate) | — |
| Peak allocated / reserved GiB | — / — |

Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.

```json
{
  "architecture": "resenc",
  "configuration": "3d_fullres",
  "deterministic": false,
  "fold": 0,
  "num_epochs": null,
  "num_iterations_per_epoch": null,
  "purpose": "baseline",
  "resenc": "L",
  "seed": 0,
  "workers": 4,
  "patch_size": [
    56,
    320,
    256
  ],
  "batch_size": 2,
  "spacing": [
    2.5,
    0.8125,
    0.8125
  ],
  "batch_dice": false,
  "normalization_schemes": [
    "CTNormalization"
  ]
}
```

## Native validation

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/nnunet_resenc_l-seed0.json)

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

