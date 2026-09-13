# unetr

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-13T23:53:06.453616+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **5**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.242379+00:00 / — |
| Last worker update | 2026-09-13T23:18:14.807483+00:00 |
| Completed / budget steps | 4900 / 10000 |
| Live step / phase | — / validation |
| Parameters | 92783859 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5774 |
| Peak allocated / reserved GiB | 6.71 / 7.33 |

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
  "model": "unetr",
  "model_options": {
    "feature_size": 16,
    "hidden_size": 768,
    "mlp_dim": 3072,
    "num_heads": 12
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
| 1 | 100 | 1.5419 | 0.0002972986 | 0.0000 | 0.0000 |
| 2 | 200 | 1.2758 | 0.0002945946 | — | — |
| 3 | 300 | 1.1601 | 0.0002918877 | — | — |
| 4 | 400 | 1.0836 | 0.0002891781 | — | — |
| 5 | 500 | 1.0279 | 0.0002864656 | — | — |
| 6 | 600 | 0.9902 | 0.0002837503 | — | — |
| 7 | 700 | 0.9638 | 0.0002810321 | — | — |
| 8 | 800 | 0.9366 | 0.000278311 | — | — |
| 9 | 900 | 0.9284 | 0.0002755869 | — | — |
| 10 | 1000 | 0.9004 | 0.0002728598 | 0.2084 | 0.0000 |
| 11 | 1100 | 0.8775 | 0.0002701297 | — | — |
| 12 | 1200 | 0.8759 | 0.0002673965 | — | — |
| 13 | 1300 | 0.8680 | 0.0002646602 | — | — |
| 14 | 1400 | 0.8635 | 0.0002619207 | — | — |
| 15 | 1500 | 0.8562 | 0.0002591781 | — | — |
| 16 | 1600 | 0.8526 | 0.0002564322 | — | — |
| 17 | 1700 | 0.8412 | 0.0002536831 | — | — |
| 18 | 1800 | 0.8304 | 0.0002509307 | — | — |
| 19 | 1900 | 0.8344 | 0.0002481749 | — | — |
| 20 | 2000 | 0.8224 | 0.0002454156 | 0.1381 | 0.0000 |
| 21 | 2100 | 0.8117 | 0.000242653 | — | — |
| 22 | 2200 | 0.8114 | 0.0002398868 | — | — |
| 23 | 2300 | 0.8252 | 0.0002371171 | — | — |
| 24 | 2400 | 0.8110 | 0.0002343438 | — | — |
| 25 | 2500 | 0.7942 | 0.0002315669 | — | — |
| 26 | 2600 | 0.7921 | 0.0002287862 | — | — |
| 27 | 2700 | 0.7849 | 0.0002260018 | — | — |
| 28 | 2800 | 0.7821 | 0.0002232135 | — | — |
| 29 | 2900 | 0.7755 | 0.0002204214 | — | — |
| 30 | 3000 | 0.7678 | 0.0002176254 | 0.2990 | 0.0000 |
| 31 | 3100 | 0.7647 | 0.0002148253 | — | — |
| 32 | 3200 | 0.7617 | 0.0002120212 | — | — |
| 33 | 3300 | 0.7619 | 0.000209213 | — | — |
| 34 | 3400 | 0.7505 | 0.0002064005 | — | — |
| 35 | 3500 | 0.7243 | 0.0002035838 | — | — |
| 36 | 3600 | 0.7091 | 0.0002007628 | — | — |
| 37 | 3700 | 0.7107 | 0.0001979373 | — | — |
| 38 | 3800 | 0.6991 | 0.0001951074 | — | — |
| 39 | 3900 | 0.6748 | 0.0001922729 | — | — |
| 40 | 4000 | 0.6691 | 0.0001894338 | 0.3566 | 0.0275 |
| 41 | 4100 | 0.6859 | 0.0001865899 | — | — |
| 42 | 4200 | 0.6671 | 0.0001837412 | — | — |
| 43 | 4300 | 0.6797 | 0.0001808875 | — | — |
| 44 | 4400 | 0.6603 | 0.0001780289 | — | — |
| 45 | 4500 | 0.6594 | 0.0001751651 | — | — |
| 46 | 4600 | 0.6449 | 0.0001722962 | — | — |
| 47 | 4700 | 0.6411 | 0.0001694219 | — | — |
| 48 | 4800 | 0.6475 | 0.0001665422 | — | — |
| 49 | 4900 | 0.6535 | 0.0001636569 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
