# swin_upernet

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T01:53:16.378237+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **4**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T01:48:39.463116+00:00 / — |
| Last worker update | 2026-09-14T01:49:19.927713+00:00 |
| Completed / budget steps | 0 / 10000 |
| Live step / phase | — / validation |
| Parameters | 59831744 |
| Objective | main_ce_plus_auxiliary_ce |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.0623 |
| Peak allocated / reserved GiB | — / — |

Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.

```json
{
  "augment": true,
  "backend": "torch",
  "batch_size": 8,
  "context_slices": 5,
  "deterministic": false,
  "epochs": 100,
  "foreground_probability": 0.5,
  "gradient_clip": 12.0,
  "hu_window": [
    -100.0,
    240.0
  ],
  "inference_batch_size": 8,
  "learning_rate": 0.0003,
  "mode": "2.5d",
  "model": "swin_upernet",
  "model_options": {
    "profile": "standard"
  },
  "overlap": 0.5,
  "patch_size": [
    256,
    256
  ],
  "precision": "bf16",
  "prefetch_batches": true,
  "progress_interval": 10,
  "purpose": "baseline",
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

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice |
| --- | --- | --- | --- | --- | --- |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
