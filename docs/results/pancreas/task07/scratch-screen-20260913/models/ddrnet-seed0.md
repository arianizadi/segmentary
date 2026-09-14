# ddrnet

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T03:53:32.241578+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **6**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T03:40:39.395819+00:00 / — |
| Last worker update | 2026-09-14T03:41:20.185166+00:00 |
| Completed / budget steps | 1900 / 10000 |
| Live step / phase | — / validation |
| Parameters | 5732838 |
| Objective | main_ce_plus_auxiliary_ce |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.1998 |
| Peak allocated / reserved GiB | 0.23 / 0.25 |

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
  "model": "ddrnet",
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
| 1 | 100 | 0.7847 | 0.0002972986 | 0.0012 | 0.0000 |
| 2 | 200 | 0.0527 | 0.0002945946 | — | — |
| 3 | 300 | 0.0455 | 0.0002918877 | — | — |
| 4 | 400 | 0.0401 | 0.0002891781 | — | — |
| 5 | 500 | 0.0413 | 0.0002864656 | — | — |
| 6 | 600 | 0.0397 | 0.0002837503 | — | — |
| 7 | 700 | 0.0336 | 0.0002810321 | — | — |
| 8 | 800 | 0.0356 | 0.000278311 | — | — |
| 9 | 900 | 0.0331 | 0.0002755869 | — | — |
| 10 | 1000 | 0.0344 | 0.0002728598 | 0.0717 | 0.0000 |
| 11 | 1100 | 0.0319 | 0.0002701297 | — | — |
| 12 | 1200 | 0.0286 | 0.0002673965 | — | — |
| 13 | 1300 | 0.0314 | 0.0002646602 | — | — |
| 14 | 1400 | 0.0311 | 0.0002619207 | — | — |
| 15 | 1500 | 0.0303 | 0.0002591781 | — | — |
| 16 | 1600 | 0.0289 | 0.0002564322 | — | — |
| 17 | 1700 | 0.0272 | 0.0002536831 | — | — |
| 18 | 1800 | 0.0279 | 0.0002509307 | — | — |
| 19 | 1900 | 0.0260 | 0.0002481749 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
