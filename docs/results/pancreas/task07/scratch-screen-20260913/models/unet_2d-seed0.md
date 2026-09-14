# unet_2d

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T03:23:29.603988+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **9**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T02:59:10.935385+00:00 / — |
| Last worker update | 2026-09-14T02:59:51.831671+00:00 |
| Completed / budget steps | 4900 / 10000 |
| Live step / phase | — / validation |
| Parameters | 24442931 |
| Objective | common_dice_ce |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.3903 |
| Peak allocated / reserved GiB | 0.78 / 0.84 |

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
  "model": "unet_2d",
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
| 1 | 100 | 1.4786 | 0.0002972986 | 0.0000 | 0.0000 |
| 2 | 200 | 1.0655 | 0.0002945946 | — | — |
| 3 | 300 | 0.9487 | 0.0002918877 | — | — |
| 4 | 400 | 0.8737 | 0.0002891781 | — | — |
| 5 | 500 | 0.8580 | 0.0002864656 | — | — |
| 6 | 600 | 0.8221 | 0.0002837503 | — | — |
| 7 | 700 | 0.7938 | 0.0002810321 | — | — |
| 8 | 800 | 0.7508 | 0.000278311 | — | — |
| 9 | 900 | 0.7385 | 0.0002755869 | — | — |
| 10 | 1000 | 0.7415 | 0.0002728598 | 0.3107 | 0.0832 |
| 11 | 1100 | 0.7017 | 0.0002701297 | — | — |
| 12 | 1200 | 0.6829 | 0.0002673965 | — | — |
| 13 | 1300 | 0.6419 | 0.0002646602 | — | — |
| 14 | 1400 | 0.6500 | 0.0002619207 | — | — |
| 15 | 1500 | 0.6289 | 0.0002591781 | — | — |
| 16 | 1600 | 0.6092 | 0.0002564322 | — | — |
| 17 | 1700 | 0.6199 | 0.0002536831 | — | — |
| 18 | 1800 | 0.6078 | 0.0002509307 | — | — |
| 19 | 1900 | 0.6018 | 0.0002481749 | — | — |
| 20 | 2000 | 0.5938 | 0.0002454156 | 0.3293 | 0.1093 |
| 21 | 2100 | 0.5812 | 0.000242653 | — | — |
| 22 | 2200 | 0.5659 | 0.0002398868 | — | — |
| 23 | 2300 | 0.5756 | 0.0002371171 | — | — |
| 24 | 2400 | 0.5763 | 0.0002343438 | — | — |
| 25 | 2500 | 0.5870 | 0.0002315669 | — | — |
| 26 | 2600 | 0.5521 | 0.0002287862 | — | — |
| 27 | 2700 | 0.5636 | 0.0002260018 | — | — |
| 28 | 2800 | 0.5341 | 0.0002232135 | — | — |
| 29 | 2900 | 0.5285 | 0.0002204214 | — | — |
| 30 | 3000 | 0.5140 | 0.0002176254 | 0.5603 | 0.2063 |
| 31 | 3100 | 0.5496 | 0.0002148253 | — | — |
| 32 | 3200 | 0.5382 | 0.0002120212 | — | — |
| 33 | 3300 | 0.5080 | 0.000209213 | — | — |
| 34 | 3400 | 0.5229 | 0.0002064005 | — | — |
| 35 | 3500 | 0.5165 | 0.0002035838 | — | — |
| 36 | 3600 | 0.5189 | 0.0002007628 | — | — |
| 37 | 3700 | 0.5147 | 0.0001979373 | — | — |
| 38 | 3800 | 0.5159 | 0.0001951074 | — | — |
| 39 | 3900 | 0.5341 | 0.0001922729 | — | — |
| 40 | 4000 | 0.5037 | 0.0001894338 | 0.5935 | 0.1970 |
| 41 | 4100 | 0.4648 | 0.0001865899 | — | — |
| 42 | 4200 | 0.5097 | 0.0001837412 | — | — |
| 43 | 4300 | 0.4876 | 0.0001808875 | — | — |
| 44 | 4400 | 0.4803 | 0.0001780289 | — | — |
| 45 | 4500 | 0.5105 | 0.0001751651 | — | — |
| 46 | 4600 | 0.4814 | 0.0001722962 | — | — |
| 47 | 4700 | 0.5087 | 0.0001694219 | — | — |
| 48 | 4800 | 0.4730 | 0.0001665422 | — | — |
| 49 | 4900 | 0.4822 | 0.0001636569 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
