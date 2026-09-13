# umamba_bot

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-13T23:53:06.453616+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **3**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.237747+00:00 / — |
| Last worker update | 2026-09-13T23:18:16.506273+00:00 |
| Completed / budget steps | 2400 / 10000 |
| Live step / phase | 2480 / train |
| Parameters | 22570531 |
| Objective | dense_ce_dice |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5771 |
| Peak allocated / reserved GiB | 15.45 / 18.53 |

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
  "model": "umamba_bot",
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
| 1 | 100 | 1.0391 | 0.0002972986 | 0.2743 | 0.0488 |
| 2 | 200 | 0.8403 | 0.0002945946 | — | — |
| 3 | 300 | 0.7887 | 0.0002918877 | — | — |
| 4 | 400 | 0.6877 | 0.0002891781 | — | — |
| 5 | 500 | 0.6651 | 0.0002864656 | — | — |
| 6 | 600 | 0.6387 | 0.0002837503 | — | — |
| 7 | 700 | 0.6430 | 0.0002810321 | — | — |
| 8 | 800 | 0.5553 | 0.000278311 | — | — |
| 9 | 900 | 0.5539 | 0.0002755869 | — | — |
| 10 | 1000 | 0.5702 | 0.0002728598 | 0.5689 | 0.1493 |
| 11 | 1100 | 0.5402 | 0.0002701297 | — | — |
| 12 | 1200 | 0.5614 | 0.0002673965 | — | — |
| 13 | 1300 | 0.5117 | 0.0002646602 | — | — |
| 14 | 1400 | 0.5317 | 0.0002619207 | — | — |
| 15 | 1500 | 0.5174 | 0.0002591781 | — | — |
| 16 | 1600 | 0.5084 | 0.0002564322 | — | — |
| 17 | 1700 | 0.4653 | 0.0002536831 | — | — |
| 18 | 1800 | 0.4708 | 0.0002509307 | — | — |
| 19 | 1900 | 0.4985 | 0.0002481749 | — | — |
| 20 | 2000 | 0.4599 | 0.0002454156 | 0.5667 | 0.2102 |
| 21 | 2100 | 0.4428 | 0.000242653 | — | — |
| 22 | 2200 | 0.4552 | 0.0002398868 | — | — |
| 23 | 2300 | 0.4688 | 0.0002371171 | — | — |
| 24 | 2400 | 0.4545 | 0.0002343438 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
