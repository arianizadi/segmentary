# segmamba

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-13T23:53:06.453616+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **2**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.235345+00:00 / — |
| Last worker update | 2026-09-13T23:18:14.903773+00:00 |
| Completed / budget steps | 1100 / 10000 |
| Live step / phase | 1140 / train |
| Parameters | 67362723 |
| Objective | dense_ce_dice |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.5775 |
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

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
