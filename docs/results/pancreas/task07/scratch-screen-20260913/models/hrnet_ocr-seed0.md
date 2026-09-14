# hrnet_ocr

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T02:53:25.170579+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **5**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T02:25:26.921609+00:00 / — |
| Last worker update | 2026-09-14T02:26:08.390678+00:00 |
| Completed / budget steps | 2900 / 10000 |
| Live step / phase | — / validation |
| Parameters | 34919750 |
| Objective | main_ce_plus_auxiliary_ce |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4512 |
| Peak allocated / reserved GiB | 1.90 / 2.01 |

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
  "model": "hrnet_ocr",
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
| 1 | 100 | 0.2191 | 0.0002972986 | 0.0015 | 0.0000 |
| 2 | 200 | 0.0432 | 0.0002945946 | — | — |
| 3 | 300 | 0.0367 | 0.0002918877 | — | — |
| 4 | 400 | 0.0325 | 0.0002891781 | — | — |
| 5 | 500 | 0.0338 | 0.0002864656 | — | — |
| 6 | 600 | 0.0324 | 0.0002837503 | — | — |
| 7 | 700 | 0.0266 | 0.0002810321 | — | — |
| 8 | 800 | 0.0274 | 0.000278311 | — | — |
| 9 | 900 | 0.0251 | 0.0002755869 | — | — |
| 10 | 1000 | 0.0265 | 0.0002728598 | 0.3703 | 0.0000 |
| 11 | 1100 | 0.0249 | 0.0002701297 | — | — |
| 12 | 1200 | 0.0213 | 0.0002673965 | — | — |
| 13 | 1300 | 0.0229 | 0.0002646602 | — | — |
| 14 | 1400 | 0.0224 | 0.0002619207 | — | — |
| 15 | 1500 | 0.0216 | 0.0002591781 | — | — |
| 16 | 1600 | 0.0217 | 0.0002564322 | — | — |
| 17 | 1700 | 0.0196 | 0.0002536831 | — | — |
| 18 | 1800 | 0.0198 | 0.0002509307 | — | — |
| 19 | 1900 | 0.0187 | 0.0002481749 | — | — |
| 20 | 2000 | 0.0174 | 0.0002454156 | 0.1721 | 0.0000 |
| 21 | 2100 | 0.0178 | 0.000242653 | — | — |
| 22 | 2200 | 0.0184 | 0.0002398868 | — | — |
| 23 | 2300 | 0.0208 | 0.0002371171 | — | — |
| 24 | 2400 | 0.0191 | 0.0002343438 | — | — |
| 25 | 2500 | 0.0165 | 0.0002315669 | — | — |
| 26 | 2600 | 0.0148 | 0.0002287862 | — | — |
| 27 | 2700 | 0.0173 | 0.0002260018 | — | — |
| 28 | 2800 | 0.0180 | 0.0002232135 | — | — |
| 29 | 2900 | 0.0164 | 0.0002204214 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
