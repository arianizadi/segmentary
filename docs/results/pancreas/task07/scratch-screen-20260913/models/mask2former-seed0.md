# mask2former

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T01:23:13.975052+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **6**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T00:49:14.285261+00:00 / — |
| Last worker update | 2026-09-14T00:49:55.059620+00:00 |
| Completed / budget steps | 2900 / 10000 |
| Live step / phase | — / validation |
| Parameters | 47404926 |
| Objective | native_hungarian_query_loss |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5518 |
| Peak allocated / reserved GiB | 3.53 / 3.71 |

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
  "model": "mask2former",
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
| 1 | 100 | 51.6175 | 0.0002972986 | 0.0011 | 0.0000 |
| 2 | 200 | 28.9139 | 0.0002945946 | — | — |
| 3 | 300 | 26.9853 | 0.0002918877 | — | — |
| 4 | 400 | 27.0510 | 0.0002891781 | — | — |
| 5 | 500 | 25.9854 | 0.0002864656 | — | — |
| 6 | 600 | 25.8624 | 0.0002837503 | — | — |
| 7 | 700 | 25.5248 | 0.0002810321 | — | — |
| 8 | 800 | 25.5956 | 0.000278311 | — | — |
| 9 | 900 | 24.2940 | 0.0002755869 | — | — |
| 10 | 1000 | 24.3854 | 0.0002728598 | 0.1140 | 0.0101 |
| 11 | 1100 | 23.7376 | 0.0002701297 | — | — |
| 12 | 1200 | 23.9655 | 0.0002673965 | — | — |
| 13 | 1300 | 24.2847 | 0.0002646602 | — | — |
| 14 | 1400 | 24.2880 | 0.0002619207 | — | — |
| 15 | 1500 | 23.2071 | 0.0002591781 | — | — |
| 16 | 1600 | 23.9229 | 0.0002564322 | — | — |
| 17 | 1700 | 21.6067 | 0.0002536831 | — | — |
| 18 | 1800 | 21.3087 | 0.0002509307 | — | — |
| 19 | 1900 | 20.9342 | 0.0002481749 | — | — |
| 20 | 2000 | 20.3793 | 0.0002454156 | 0.2163 | 0.0205 |
| 21 | 2100 | 20.6080 | 0.000242653 | — | — |
| 22 | 2200 | 20.5480 | 0.0002398868 | — | — |
| 23 | 2300 | 21.0031 | 0.0002371171 | — | — |
| 24 | 2400 | 21.2323 | 0.0002343438 | — | — |
| 25 | 2500 | 20.0809 | 0.0002315669 | — | — |
| 26 | 2600 | 18.8818 | 0.0002287862 | — | — |
| 27 | 2700 | 19.7739 | 0.0002260018 | — | — |
| 28 | 2800 | 20.4664 | 0.0002232135 | — | — |
| 29 | 2900 | 18.7019 | 0.0002204214 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
