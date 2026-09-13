# swin_unetr

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-13T23:53:06.453616+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **4**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.240332+00:00 / — |
| Last worker update | 2026-09-13T23:18:17.017403+00:00 |
| Completed / budget steps | 2200 / 10000 |
| Live step / phase | 2260 / train |
| Parameters | 15703029 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5769 |
| Peak allocated / reserved GiB | 24.69 / 37.36 |

Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.

```json
{
  "augment": true,
  "backend": "torch",
  "batch_size": 8,
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
  "learning_rate": 0.0003,
  "mode": "3d",
  "model": "swin_unetr",
  "model_options": {
    "depths": [
      2,
      2,
      2,
      2
    ],
    "feature_size": 24,
    "num_heads": [
      3,
      6,
      12,
      24
    ],
    "use_checkpoint": false,
    "window_size": 7
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
| 1 | 100 | 1.4283 | 0.0002972986 | 0.2639 | 0.0000 |
| 2 | 200 | 1.1606 | 0.0002945946 | — | — |
| 3 | 300 | 1.0498 | 0.0002918877 | — | — |
| 4 | 400 | 0.9596 | 0.0002891781 | — | — |
| 5 | 500 | 0.8916 | 0.0002864656 | — | — |
| 6 | 600 | 0.8437 | 0.0002837503 | — | — |
| 7 | 700 | 0.8150 | 0.0002810321 | — | — |
| 8 | 800 | 0.7810 | 0.000278311 | — | — |
| 9 | 900 | 0.7691 | 0.0002755869 | — | — |
| 10 | 1000 | 0.7466 | 0.0002728598 | 0.5616 | 0.0000 |
| 11 | 1100 | 0.7197 | 0.0002701297 | — | — |
| 12 | 1200 | 0.7217 | 0.0002673965 | — | — |
| 13 | 1300 | 0.6949 | 0.0002646602 | — | — |
| 14 | 1400 | 0.6791 | 0.0002619207 | — | — |
| 15 | 1500 | 0.6609 | 0.0002591781 | — | — |
| 16 | 1600 | 0.6396 | 0.0002564322 | — | — |
| 17 | 1700 | 0.6035 | 0.0002536831 | — | — |
| 18 | 1800 | 0.5798 | 0.0002509307 | — | — |
| 19 | 1900 | 0.6017 | 0.0002481749 | — | — |
| 20 | 2000 | 0.5445 | 0.0002454156 | 0.4764 | 0.1845 |
| 21 | 2100 | 0.5359 | 0.000242653 | — | — |
| 22 | 2200 | 0.5364 | 0.0002398868 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
