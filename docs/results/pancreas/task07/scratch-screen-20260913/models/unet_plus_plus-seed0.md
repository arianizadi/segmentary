# unet_plus_plus

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T02:53:25.170579+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **6**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T02:41:46.784958+00:00 / — |
| Last worker update | 2026-09-14T02:42:27.830007+00:00 |
| Completed / budget steps | 1300 / 10000 |
| Live step / phase | 1330 / train |
| Parameters | 26085171 |
| Objective | common_dice_ce |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.1792 |
| Peak allocated / reserved GiB | 1.39 / 1.57 |

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
  "model": "unet_plus_plus",
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
| 1 | 100 | 1.1946 | 0.0002972986 | 0.1798 | 0.0000 |
| 2 | 200 | 0.9290 | 0.0002945946 | — | — |
| 3 | 300 | 0.8681 | 0.0002918877 | — | — |
| 4 | 400 | 0.8250 | 0.0002891781 | — | — |
| 5 | 500 | 0.8239 | 0.0002864656 | — | — |
| 6 | 600 | 0.7927 | 0.0002837503 | — | — |
| 7 | 700 | 0.7742 | 0.0002810321 | — | — |
| 8 | 800 | 0.7279 | 0.000278311 | — | — |
| 9 | 900 | 0.7152 | 0.0002755869 | — | — |
| 10 | 1000 | 0.6984 | 0.0002728598 | 0.3664 | 0.1053 |
| 11 | 1100 | 0.6651 | 0.0002701297 | — | — |
| 12 | 1200 | 0.6655 | 0.0002673965 | — | — |
| 13 | 1300 | 0.6243 | 0.0002646602 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
