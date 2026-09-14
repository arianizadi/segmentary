# maskformer

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T01:53:16.378237+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **9**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T01:26:30.047348+00:00 / — |
| Last worker update | 2026-09-14T01:27:10.852191+00:00 |
| Completed / budget steps | 3400 / 10000 |
| Live step / phase | 3430 / train |
| Parameters | 41722302 |
| Objective | native_hungarian_query_loss |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4315 |
| Peak allocated / reserved GiB | 2.32 / 2.57 |

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
  "model": "maskformer",
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
| 1 | 100 | 47.9177 | 0.0002972986 | 0.0000 | 0.0000 |
| 2 | 200 | 8.8772 | 0.0002945946 | — | — |
| 3 | 300 | 7.4496 | 0.0002918877 | — | — |
| 4 | 400 | 7.1950 | 0.0002891781 | — | — |
| 5 | 500 | 6.9924 | 0.0002864656 | — | — |
| 6 | 600 | 6.8809 | 0.0002837503 | — | — |
| 7 | 700 | 6.6200 | 0.0002810321 | — | — |
| 8 | 800 | 6.6179 | 0.000278311 | — | — |
| 9 | 900 | 6.3875 | 0.0002755869 | — | — |
| 10 | 1000 | 6.4229 | 0.0002728598 | 0.0044 | 0.0005 |
| 11 | 1100 | 6.2972 | 0.0002701297 | — | — |
| 12 | 1200 | 6.2385 | 0.0002673965 | — | — |
| 13 | 1300 | 6.2403 | 0.0002646602 | — | — |
| 14 | 1400 | 6.1446 | 0.0002619207 | — | — |
| 15 | 1500 | 6.0481 | 0.0002591781 | — | — |
| 16 | 1600 | 6.0046 | 0.0002564322 | — | — |
| 17 | 1700 | 5.8036 | 0.0002536831 | — | — |
| 18 | 1800 | 5.8675 | 0.0002509307 | — | — |
| 19 | 1900 | 5.8213 | 0.0002481749 | — | — |
| 20 | 2000 | 5.7161 | 0.0002454156 | 0.0044 | 0.0005 |
| 21 | 2100 | 6.6499 | 0.000242653 | — | — |
| 22 | 2200 | 5.9253 | 0.0002398868 | — | — |
| 23 | 2300 | 5.8459 | 0.0002371171 | — | — |
| 24 | 2400 | 5.6786 | 0.0002343438 | — | — |
| 25 | 2500 | 5.5593 | 0.0002315669 | — | — |
| 26 | 2600 | 5.3749 | 0.0002287862 | — | — |
| 27 | 2700 | 5.5773 | 0.0002260018 | — | — |
| 28 | 2800 | 5.5830 | 0.0002232135 | — | — |
| 29 | 2900 | 5.4021 | 0.0002204214 | — | — |
| 30 | 3000 | 5.2825 | 0.0002176254 | 0.0074 | 0.0000 |
| 31 | 3100 | 5.3605 | 0.0002148253 | — | — |
| 32 | 3200 | 5.3116 | 0.0002120212 | — | — |
| 33 | 3300 | 5.2749 | 0.000209213 | — | — |
| 34 | 3400 | 5.3212 | 0.0002064005 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
