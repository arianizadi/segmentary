# segmamba

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T01:23:13.975052+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **2**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.235345+00:00 / — |
| Last worker update | 2026-09-13T23:18:14.903773+00:00 |
| Completed / budget steps | 4500 / 10000 |
| Live step / phase | 4590 / train |
| Parameters | 67362723 |
| Objective | dense_ce_dice |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 2.0795 |
| Peak allocated / reserved GiB | 19.29 / 22.59 |

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
  "model": "segmamba",
  "model_options": {
    "checkpoint_mamba": true,
    "d_conv": 4,
    "d_state": 16,
    "depths": [
      2,
      2,
      2,
      2
    ],
    "expand": 2,
    "features": [
      48,
      96,
      192,
      384
    ],
    "hidden_size": 768,
    "num_slices": [
      64,
      32,
      16,
      8
    ],
    "scan_backend": "native",
    "scan_chunk_size": 256
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
| 1 | 100 | 1.1615 | 0.0002972986 | 0.2567 | 0.0000 |
| 2 | 200 | 0.9319 | 0.0002945946 | — | — |
| 3 | 300 | 0.8671 | 0.0002918877 | — | — |
| 4 | 400 | 0.8126 | 0.0002891781 | — | — |
| 5 | 500 | 0.7630 | 0.0002864656 | — | — |
| 6 | 600 | 0.7054 | 0.0002837503 | — | — |
| 7 | 700 | 0.6771 | 0.0002810321 | — | — |
| 8 | 800 | 0.6298 | 0.000278311 | — | — |
| 9 | 900 | 0.6510 | 0.0002755869 | — | — |
| 10 | 1000 | 0.6185 | 0.0002728598 | 0.4282 | 0.1412 |
| 11 | 1100 | 0.5709 | 0.0002701297 | — | — |
| 12 | 1200 | 0.5940 | 0.0002673965 | — | — |
| 13 | 1300 | 0.5771 | 0.0002646602 | — | — |
| 14 | 1400 | 0.5548 | 0.0002619207 | — | — |
| 15 | 1500 | 0.5523 | 0.0002591781 | — | — |
| 16 | 1600 | 0.5719 | 0.0002564322 | — | — |
| 17 | 1700 | 0.5608 | 0.0002536831 | — | — |
| 18 | 1800 | 0.5234 | 0.0002509307 | — | — |
| 19 | 1900 | 0.5610 | 0.0002481749 | — | — |
| 20 | 2000 | 0.5015 | 0.0002454156 | 0.5248 | 0.2232 |
| 21 | 2100 | 0.4886 | 0.000242653 | — | — |
| 22 | 2200 | 0.4950 | 0.0002398868 | — | — |
| 23 | 2300 | 0.4913 | 0.0002371171 | — | — |
| 24 | 2400 | 0.4890 | 0.0002343438 | — | — |
| 25 | 2500 | 0.4284 | 0.0002315669 | — | — |
| 26 | 2600 | 0.4810 | 0.0002287862 | — | — |
| 27 | 2700 | 0.4466 | 0.0002260018 | — | — |
| 28 | 2800 | 0.4286 | 0.0002232135 | — | — |
| 29 | 2900 | 0.4427 | 0.0002204214 | — | — |
| 30 | 3000 | 0.4291 | 0.0002176254 | 0.6318 | 0.2188 |
| 31 | 3100 | 0.4335 | 0.0002148253 | — | — |
| 32 | 3200 | 0.4182 | 0.0002120212 | — | — |
| 33 | 3300 | 0.4400 | 0.000209213 | — | — |
| 34 | 3400 | 0.4451 | 0.0002064005 | — | — |
| 35 | 3500 | 0.4264 | 0.0002035838 | — | — |
| 36 | 3600 | 0.3984 | 0.0002007628 | — | — |
| 37 | 3700 | 0.3903 | 0.0001979373 | — | — |
| 38 | 3800 | 0.3952 | 0.0001951074 | — | — |
| 39 | 3900 | 0.3879 | 0.0001922729 | — | — |
| 40 | 4000 | 0.3809 | 0.0001894338 | 0.5944 | 0.2420 |
| 41 | 4100 | 0.4098 | 0.0001865899 | — | — |
| 42 | 4200 | 0.3953 | 0.0001837412 | — | — |
| 43 | 4300 | 0.3922 | 0.0001808875 | — | — |
| 44 | 4400 | 0.3623 | 0.0001780289 | — | — |
| 45 | 4500 | 0.3655 | 0.0001751651 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
