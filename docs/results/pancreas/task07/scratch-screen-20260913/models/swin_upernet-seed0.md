# swin_upernet

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T02:23:20.851368+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **4**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-14T01:48:39.463116+00:00 / — |
| Last worker update | 2026-09-14T01:49:19.927713+00:00 |
| Completed / budget steps | 5900 / 10000 |
| Live step / phase | — / validation |
| Parameters | 59831744 |
| Objective | main_ce_plus_auxiliary_ce |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5635 |
| Peak allocated / reserved GiB | 2.57 / 2.77 |

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
  "model": "swin_upernet",
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
| 1 | 100 | 0.2956 | 0.0002972986 | 0.0000 | 0.0000 |
| 2 | 200 | 0.0523 | 0.0002945946 | — | — |
| 3 | 300 | 0.0461 | 0.0002918877 | — | — |
| 4 | 400 | 0.0404 | 0.0002891781 | — | — |
| 5 | 500 | 0.0407 | 0.0002864656 | — | — |
| 6 | 600 | 0.0383 | 0.0002837503 | — | — |
| 7 | 700 | 0.0332 | 0.0002810321 | — | — |
| 8 | 800 | 0.0360 | 0.000278311 | — | — |
| 9 | 900 | 0.0336 | 0.0002755869 | — | — |
| 10 | 1000 | 0.0337 | 0.0002728598 | 0.0393 | 0.0000 |
| 11 | 1100 | 0.0328 | 0.0002701297 | — | — |
| 12 | 1200 | 0.0288 | 0.0002673965 | — | — |
| 13 | 1300 | 0.0316 | 0.0002646602 | — | — |
| 14 | 1400 | 0.0318 | 0.0002619207 | — | — |
| 15 | 1500 | 0.0309 | 0.0002591781 | — | — |
| 16 | 1600 | 0.0302 | 0.0002564322 | — | — |
| 17 | 1700 | 0.0293 | 0.0002536831 | — | — |
| 18 | 1800 | 0.0281 | 0.0002509307 | — | — |
| 19 | 1900 | 0.0270 | 0.0002481749 | — | — |
| 20 | 2000 | 0.0252 | 0.0002454156 | 0.1964 | 0.0000 |
| 21 | 2100 | 0.0258 | 0.000242653 | — | — |
| 22 | 2200 | 0.0263 | 0.0002398868 | — | — |
| 23 | 2300 | 0.0287 | 0.0002371171 | — | — |
| 24 | 2400 | 0.0275 | 0.0002343438 | — | — |
| 25 | 2500 | 0.0264 | 0.0002315669 | — | — |
| 26 | 2600 | 0.0228 | 0.0002287862 | — | — |
| 27 | 2700 | 0.0261 | 0.0002260018 | — | — |
| 28 | 2800 | 0.0263 | 0.0002232135 | — | — |
| 29 | 2900 | 0.0247 | 0.0002204214 | — | — |
| 30 | 3000 | 0.0236 | 0.0002176254 | 0.2261 | 0.0000 |
| 31 | 3100 | 0.0253 | 0.0002148253 | — | — |
| 32 | 3200 | 0.0243 | 0.0002120212 | — | — |
| 33 | 3300 | 0.0220 | 0.000209213 | — | — |
| 34 | 3400 | 0.0236 | 0.0002064005 | — | — |
| 35 | 3500 | 0.0216 | 0.0002035838 | — | — |
| 36 | 3600 | 0.0217 | 0.0002007628 | — | — |
| 37 | 3700 | 0.0223 | 0.0001979373 | — | — |
| 38 | 3800 | 0.0208 | 0.0001951074 | — | — |
| 39 | 3900 | 0.0232 | 0.0001922729 | — | — |
| 40 | 4000 | 0.0213 | 0.0001894338 | 0.3356 | 0.0263 |
| 41 | 4100 | 0.0202 | 0.0001865899 | — | — |
| 42 | 4200 | 0.0210 | 0.0001837412 | — | — |
| 43 | 4300 | 0.0207 | 0.0001808875 | — | — |
| 44 | 4400 | 0.0214 | 0.0001780289 | — | — |
| 45 | 4500 | 0.0199 | 0.0001751651 | — | — |
| 46 | 4600 | 0.0211 | 0.0001722962 | — | — |
| 47 | 4700 | 0.0200 | 0.0001694219 | — | — |
| 48 | 4800 | 0.0199 | 0.0001665422 | — | — |
| 49 | 4900 | 0.0197 | 0.0001636569 | — | — |
| 50 | 5000 | 0.0204 | 0.000160766 | 0.2549 | 0.0174 |
| 51 | 5100 | 0.0203 | 0.0001578693 | — | — |
| 52 | 5200 | 0.0187 | 0.0001549667 | — | — |
| 53 | 5300 | 0.0183 | 0.000152058 | — | — |
| 54 | 5400 | 0.0187 | 0.0001491431 | — | — |
| 55 | 5500 | 0.0184 | 0.0001462219 | — | — |
| 56 | 5600 | 0.0188 | 0.0001432942 | — | — |
| 57 | 5700 | 0.0179 | 0.0001403598 | — | — |
| 58 | 5800 | 0.0176 | 0.0001374186 | — | — |
| 59 | 5900 | 0.0181 | 0.0001344704 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
