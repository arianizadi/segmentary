# umamba_enc

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T01:23:13.975052+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **1**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.233346+00:00 / — |
| Last worker update | 2026-09-13T23:18:17.236892+00:00 |
| Completed / budget steps | 4200 / 10000 |
| Live step / phase | 4201 / train |
| Parameters | 22808675 |
| Objective | dense_ce_dice |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 2.0789 |
| Peak allocated / reserved GiB | 33.55 / 38.72 |

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
  "model": "umamba_enc",
  "model_options": {
    "blocks": [
      2,
      2,
      2,
      2,
      2
    ],
    "checkpoint_mamba": true,
    "d_conv": 4,
    "d_state": 16,
    "decoder_blocks": [
      2,
      2,
      2,
      2
    ],
    "expand": 2,
    "features": [
      32,
      64,
      128,
      256,
      320
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
| 1 | 100 | 1.4008 | 0.0002972986 | 0.0282 | 0.0000 |
| 2 | 200 | 0.9474 | 0.0002945946 | — | — |
| 3 | 300 | 0.9151 | 0.0002918877 | — | — |
| 4 | 400 | 0.8490 | 0.0002891781 | — | — |
| 5 | 500 | 0.8363 | 0.0002864656 | — | — |
| 6 | 600 | 0.7930 | 0.0002837503 | — | — |
| 7 | 700 | 0.7543 | 0.0002810321 | — | — |
| 8 | 800 | 0.6991 | 0.000278311 | — | — |
| 9 | 900 | 0.6850 | 0.0002755869 | — | — |
| 10 | 1000 | 0.6465 | 0.0002728598 | 0.3123 | 0.1166 |
| 11 | 1100 | 0.5987 | 0.0002701297 | — | — |
| 12 | 1200 | 0.6143 | 0.0002673965 | — | — |
| 13 | 1300 | 0.5810 | 0.0002646602 | — | — |
| 14 | 1400 | 0.5729 | 0.0002619207 | — | — |
| 15 | 1500 | 0.5748 | 0.0002591781 | — | — |
| 16 | 1600 | 0.5579 | 0.0002564322 | — | — |
| 17 | 1700 | 0.5472 | 0.0002536831 | — | — |
| 18 | 1800 | 0.5247 | 0.0002509307 | — | — |
| 19 | 1900 | 0.5540 | 0.0002481749 | — | — |
| 20 | 2000 | 0.4810 | 0.0002454156 | 0.4053 | 0.1731 |
| 21 | 2100 | 0.4697 | 0.000242653 | — | — |
| 22 | 2200 | 0.4831 | 0.0002398868 | — | — |
| 23 | 2300 | 0.4930 | 0.0002371171 | — | — |
| 24 | 2400 | 0.4904 | 0.0002343438 | — | — |
| 25 | 2500 | 0.4301 | 0.0002315669 | — | — |
| 26 | 2600 | 0.4643 | 0.0002287862 | — | — |
| 27 | 2700 | 0.4371 | 0.0002260018 | — | — |
| 28 | 2800 | 0.4395 | 0.0002232135 | — | — |
| 29 | 2900 | 0.4400 | 0.0002204214 | — | — |
| 30 | 3000 | 0.4188 | 0.0002176254 | 0.6516 | 0.2359 |
| 31 | 3100 | 0.4199 | 0.0002148253 | — | — |
| 32 | 3200 | 0.4259 | 0.0002120212 | — | — |
| 33 | 3300 | 0.4428 | 0.000209213 | — | — |
| 34 | 3400 | 0.4247 | 0.0002064005 | — | — |
| 35 | 3500 | 0.4161 | 0.0002035838 | — | — |
| 36 | 3600 | 0.3890 | 0.0002007628 | — | — |
| 37 | 3700 | 0.3949 | 0.0001979373 | — | — |
| 38 | 3800 | 0.4131 | 0.0001951074 | — | — |
| 39 | 3900 | 0.4230 | 0.0001922729 | — | — |
| 40 | 4000 | 0.3828 | 0.0001894338 | 0.7144 | 0.3170 |
| 41 | 4100 | 0.4171 | 0.0001865899 | — | — |
| 42 | 4200 | 0.4175 | 0.0001837412 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
