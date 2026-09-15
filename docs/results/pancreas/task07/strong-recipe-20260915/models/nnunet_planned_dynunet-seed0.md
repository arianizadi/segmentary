# nnunet_planned_dynunet

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T18:11:34.573336+00:00. Source: `63a108f8b7a65a98b11ccae0e8883c54955b2099`.

Status: **running**. Stage: **train**. GPU: **3**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T17:50:25.436938+00:00 / — |
| Last worker update | 2026-09-15T17:50:39.474644+00:00 |
| Completed / budget steps | 2750 / 250000 |
| Live step / phase | — / — |
| Parameters | 44992082 |
| Objective | — |
| Checkpoint selection | official_ema_foreground_dice |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | — |
| Active-stage allocated hours (estimate) | 0.3457 |
| Peak allocated / reserved GiB | — / — |

Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.

```json
{
  "architecture": "dynunet",
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
  ],
  "effective_training_budget": {
    "num_epochs": 1000,
    "num_iterations_per_epoch": 250,
    "optimizer_steps": 250000,
    "sources": {
      "num_epochs": "trainer-settings",
      "num_iterations_per_epoch": "trainer-settings"
    }
  }
}
```

## Native validation

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/nnunet_planned_dynunet-seed0.json)

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


## Official nnU-Net patch telemetry

These patch pseudo-Dice values are not native full-volume Dice and are never substituted in the comparison quality columns.

| Completed epoch | Training loss | Mass PATCH pseudo-Dice | Pancreas CLASS PATCH pseudo-Dice | Epoch seconds |
| --- | --- | --- | --- | --- |
| 1 | 0.1031 | 0.0000 | 0.0000 | 121.9300 |
| 2 | -0.0132 | 0.0000 | 0.3088 | 104.3800 |
| 3 | -0.1125 | 0.0000 | 0.4686 | 104.6600 |
| 4 | -0.1985 | 0.0000 | 0.5264 | 104.6400 |
| 5 | -0.2217 | 0.0000 | 0.5694 | 104.6300 |
| 6 | -0.2587 | 0.0000 | 0.6034 | 104.6600 |
| 7 | -0.2700 | 0.0000 | 0.5846 | 104.6900 |
| 8 | -0.2877 | 0.0000 | 0.5882 | 104.6600 |
| 9 | -0.3259 | 0.0000 | 0.6326 | 104.7700 |
| 10 | -0.3346 | 0.2396 | 0.5991 | 104.8700 |
| 11 | -0.3773 | 0.2143 | 0.6383 | 104.8900 |
