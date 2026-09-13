# segmamba

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-13T23:23:04.085340+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **2**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.235345+00:00 / — |
| Last worker update | 2026-09-13T23:18:14.903773+00:00 |
| Completed / budget steps | 0 / 10000 |
| Live step / phase | — / validation |
| Parameters | 67362723 |
| Objective | dense_ce_dice |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.0768 |
| Peak allocated / reserved GiB | — / — |

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

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
