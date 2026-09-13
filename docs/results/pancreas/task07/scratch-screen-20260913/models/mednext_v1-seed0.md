# mednext_v1

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-13T23:53:06.453616+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **8**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.248888+00:00 / — |
| Last worker update | 2026-09-13T23:18:17.459304+00:00 |
| Completed / budget steps | 2000 / 10000 |
| Live step / phase | 2060 / train |
| Parameters | 5550947 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5767 |
| Peak allocated / reserved GiB | 29.37 / 34.87 |

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
  "model": "mednext_v1",
  "model_options": {
    "kernel_size": 3,
    "model_id": "S"
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
| 1 | 100 | 0.9975 | 0.0002972986 | 0.0969 | 0.0000 |
| 2 | 200 | 0.8832 | 0.0002945946 | — | — |
| 3 | 300 | 0.8490 | 0.0002918877 | — | — |
| 4 | 400 | 0.7784 | 0.0002891781 | — | — |
| 5 | 500 | 0.7415 | 0.0002864656 | — | — |
| 6 | 600 | 0.6994 | 0.0002837503 | — | — |
| 7 | 700 | 0.6740 | 0.0002810321 | — | — |
| 8 | 800 | 0.6429 | 0.000278311 | — | — |
| 9 | 900 | 0.6191 | 0.0002755869 | — | — |
| 10 | 1000 | 0.6048 | 0.0002728598 | 0.5128 | 0.1099 |
| 11 | 1100 | 0.5732 | 0.0002701297 | — | — |
| 12 | 1200 | 0.5754 | 0.0002673965 | — | — |
| 13 | 1300 | 0.5600 | 0.0002646602 | — | — |
| 14 | 1400 | 0.5539 | 0.0002619207 | — | — |
| 15 | 1500 | 0.5485 | 0.0002591781 | — | — |
| 16 | 1600 | 0.5471 | 0.0002564322 | — | — |
| 17 | 1700 | 0.5200 | 0.0002536831 | — | — |
| 18 | 1800 | 0.4994 | 0.0002509307 | — | — |
| 19 | 1900 | 0.5483 | 0.0002481749 | — | — |
| 20 | 2000 | 0.4733 | 0.0002454156 | 0.4806 | 0.1857 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
