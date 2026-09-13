# transunet_3d

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-13T23:23:04.085340+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **6**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.244617+00:00 / — |
| Last worker update | 2026-09-13T23:18:16.406471+00:00 |
| Completed / budget steps | 200 / 10000 |
| Live step / phase | 230 / train |
| Parameters | 102279168 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.0764 |
| Peak allocated / reserved GiB | 9.83 / 12.05 |

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
  "model": "transunet_3d",
  "model_options": {
    "base_num_features": 32,
    "max_num_features": 320,
    "num_pool": 4,
    "vit_depth": 12,
    "vit_hidden_size": 768,
    "vit_layer_scale": true,
    "vit_mlp_dim": 3072,
    "vit_num_heads": 12
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
| 1 | 100 | 1.5089 | 0.0002972986 | 0.0000 | 0.0000 |
| 2 | 200 | 1.2227 | 0.0002945946 | — | — |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
