# nnunet_resenc_l

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-14T03:53:32.241578+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

Status: **running**. Stage: **train**. GPU: **0**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-13T23:17:33.231143+00:00 / — |
| Last worker update | 2026-09-13T23:24:13.342583+00:00 |
| Completed / budget steps | 0 / — |
| Live step / phase | — / — |
| Parameters | — |
| Objective | — |
| Checkpoint selection | — |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 4.4855 |
| Peak allocated / reserved GiB | — / — |

Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.

```json
{
  "configuration": "3d_fullres",
  "deterministic": false,
  "fold": 0,
  "num_epochs": null,
  "num_iterations_per_epoch": null,
  "purpose": "baseline",
  "resenc": "L",
  "seed": 0,
  "workers": 4
}
```

## Native validation

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice |
| --- | --- | --- | --- | --- | --- |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.
