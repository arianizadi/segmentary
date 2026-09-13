# umamba_enc

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-13T23:53:06.453616+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **1**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.233346+00:00 / — |
| Last worker update | 2026-09-13T23:18:17.236892+00:00 |
| Completed / budget steps | 1000 / 10000 |
| Live step / phase | 1030 / train |
| Parameters | 22808675 |
| Objective | dense_ce_dice |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5768 |
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

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
