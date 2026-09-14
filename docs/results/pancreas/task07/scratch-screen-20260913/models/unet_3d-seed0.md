# unet_3d

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T00:53:11.494509+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **9**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T00:37:28.525341+00:00 / — |
| Last worker update | 2026-09-14T00:38:09.130686+00:00 |
| Completed / budget steps | 2900 / 10000 |
| Live step / phase | — / validation |
| Parameters | 7914603 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.2473 |
| Peak allocated / reserved GiB | 1.13 / 1.46 |

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
  "model": "unet_3d",
  "model_options": {
    "channels": [
      32,
      64,
      128,
      256,
      512
    ],
    "num_res_units": 0
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
| 1 | 100 | 1.5259 | 0.0002972986 | 0.0001 | 0.0000 |
| 2 | 200 | 1.1163 | 0.0002945946 | — | — |
| 3 | 300 | 1.0187 | 0.0002918877 | — | — |
| 4 | 400 | 0.9398 | 0.0002891781 | — | — |
| 5 | 500 | 0.8902 | 0.0002864656 | — | — |
| 6 | 600 | 0.8542 | 0.0002837503 | — | — |
| 7 | 700 | 0.8277 | 0.0002810321 | — | — |
| 8 | 800 | 0.7888 | 0.000278311 | — | — |
| 9 | 900 | 0.7813 | 0.0002755869 | — | — |
| 10 | 1000 | 0.7466 | 0.0002728598 | 0.4024 | 0.0512 |
| 11 | 1100 | 0.7093 | 0.0002701297 | — | — |
| 12 | 1200 | 0.6950 | 0.0002673965 | — | — |
| 13 | 1300 | 0.6572 | 0.0002646602 | — | — |
| 14 | 1400 | 0.6594 | 0.0002619207 | — | — |
| 15 | 1500 | 0.6318 | 0.0002591781 | — | — |
| 16 | 1600 | 0.6361 | 0.0002564322 | — | — |
| 17 | 1700 | 0.5914 | 0.0002536831 | — | — |
| 18 | 1800 | 0.5832 | 0.0002509307 | — | — |
| 19 | 1900 | 0.6152 | 0.0002481749 | — | — |
| 20 | 2000 | 0.5569 | 0.0002454156 | 0.3280 | 0.0754 |
| 21 | 2100 | 0.5532 | 0.000242653 | — | — |
| 22 | 2200 | 0.5530 | 0.0002398868 | — | — |
| 23 | 2300 | 0.5436 | 0.0002371171 | — | — |
| 24 | 2400 | 0.5371 | 0.0002343438 | — | — |
| 25 | 2500 | 0.5000 | 0.0002315669 | — | — |
| 26 | 2600 | 0.5240 | 0.0002287862 | — | — |
| 27 | 2700 | 0.4985 | 0.0002260018 | — | — |
| 28 | 2800 | 0.4873 | 0.0002232135 | — | — |
| 29 | 2900 | 0.4820 | 0.0002204214 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
