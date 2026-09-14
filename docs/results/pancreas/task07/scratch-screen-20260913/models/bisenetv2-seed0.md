# bisenetv2

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T03:53:32.241578+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **4**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T03:42:24.457302+00:00 / — |
| Last worker update | 2026-09-14T03:43:04.385701+00:00 |
| Completed / budget steps | 2100 / 10000 |
| Live step / phase | 2150 / train |
| Parameters | 5194703 |
| Objective | main_ce_plus_four_booster_ce |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.1710 |
| Peak allocated / reserved GiB | 0.50 / 0.64 |

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
  "model": "bisenetv2",
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
| 1 | 100 | 11.1969 | 0.0002972986 | 0.1131 | 0.0301 |
| 2 | 200 | 0.6262 | 0.0002945946 | — | — |
| 3 | 300 | 0.4163 | 0.0002918877 | — | — |
| 4 | 400 | 0.2822 | 0.0002891781 | — | — |
| 5 | 500 | 0.2425 | 0.0002864656 | — | — |
| 6 | 600 | 0.2220 | 0.0002837503 | — | — |
| 7 | 700 | 0.1816 | 0.0002810321 | — | — |
| 8 | 800 | 0.1852 | 0.000278311 | — | — |
| 9 | 900 | 0.1660 | 0.0002755869 | — | — |
| 10 | 1000 | 0.1663 | 0.0002728598 | 0.2930 | 0.0038 |
| 11 | 1100 | 0.1586 | 0.0002701297 | — | — |
| 12 | 1200 | 0.1387 | 0.0002673965 | — | — |
| 13 | 1300 | 0.1536 | 0.0002646602 | — | — |
| 14 | 1400 | 0.1738 | 0.0002619207 | — | — |
| 15 | 1500 | 0.1432 | 0.0002591781 | — | — |
| 16 | 1600 | 0.1378 | 0.0002564322 | — | — |
| 17 | 1700 | 0.1289 | 0.0002536831 | — | — |
| 18 | 1800 | 0.1317 | 0.0002509307 | — | — |
| 19 | 1900 | 0.1277 | 0.0002481749 | — | — |
| 20 | 2000 | 0.1213 | 0.0002454156 | 0.3041 | 0.0000 |
| 21 | 2100 | 0.1213 | 0.000242653 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
