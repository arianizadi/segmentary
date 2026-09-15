# dynunet-minmax-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T00:38:50.653104+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **6**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T00:08:44.948540+00:00 / — |
| Last worker update | 2026-09-15T00:09:26.902212+00:00 |
| Completed / budget steps | 5400 / 10000 |
| Live step / phase | 5490 / train |
| Parameters | 16543683 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4864 |
| Peak allocated / reserved GiB | 7.61 / 10.50 |

Allocation time measures time reserved for a stage, not hardware utilization. Peaks are Torch allocator high-water marks, not total device memory. Missing official-backend timing remains unknown.

```json
{
  "augment": true,
  "backend": "torch",
  "batch_size": 8,
  "center_probabilities": null,
  "class_center_weights": null,
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
  "intensity_scale_probability": 0.0,
  "intensity_scale_range": [
    0.9,
    1.1
  ],
  "learning_rate": 0.0003,
  "mode": "3d",
  "model": "dynunet",
  "model_options": {
    "filters": [
      32,
      64,
      128,
      256,
      320
    ],
    "res_block": false
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
  "rotation_degrees": [
    -15.0,
    15.0
  ],
  "rotation_padding_value": 0.0,
  "rotation_probability": 0.0,
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

| Epoch | Step | Training loss | Learning rate | Native pancreas Dice | Native mass Dice | Training s | Validation s | Checkpoint s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | 1.3826 | 0.0002972986 | 0.0865 | 0.0000 | 23.7124 | 101.9281 | 0.4693 |
| 2 | 200 | 1.1458 | 0.0002945946 | — | — | 22.7499 | 0.0000 | 0.4274 |
| 3 | 300 | 1.0498 | 0.0002918877 | — | — | 22.8067 | 0.0000 | 0.4562 |
| 4 | 400 | 0.9584 | 0.0002891781 | — | — | 22.9961 | 0.0000 | 0.4410 |
| 5 | 500 | 0.8807 | 0.0002864656 | — | — | 22.8473 | 0.0000 | 0.4646 |
| 6 | 600 | 0.8267 | 0.0002837503 | — | — | 22.8578 | 0.0000 | 0.5069 |
| 7 | 700 | 0.7963 | 0.0002810321 | — | — | 22.8719 | 0.0000 | 0.4438 |
| 8 | 800 | 0.7515 | 0.000278311 | — | — | 22.8767 | 0.0000 | 0.4418 |
| 9 | 900 | 0.7346 | 0.0002755869 | — | — | 22.8713 | 0.0000 | 0.4448 |
| 10 | 1000 | 0.6903 | 0.0002728598 | 0.5282 | 0.0434 | 22.8687 | 68.5189 | 0.4872 |
| 11 | 1100 | 0.6333 | 0.0002701297 | — | — | 22.7823 | 0.0000 | 0.4369 |
| 12 | 1200 | 0.6179 | 0.0002673965 | — | — | 22.8325 | 0.0000 | 0.4539 |
| 13 | 1300 | 0.5855 | 0.0002646602 | — | — | 22.8637 | 0.0000 | 0.4682 |
| 14 | 1400 | 0.5780 | 0.0002619207 | — | — | 22.8538 | 0.0000 | 0.4722 |
| 15 | 1500 | 0.5567 | 0.0002591781 | — | — | 22.8636 | 0.0000 | 0.4410 |
| 16 | 1600 | 0.5555 | 0.0002564322 | — | — | 22.8718 | 0.0000 | 0.4765 |
| 17 | 1700 | 0.5349 | 0.0002536831 | — | — | 22.8737 | 0.0000 | 0.4648 |
| 18 | 1800 | 0.5157 | 0.0002509307 | — | — | 22.8831 | 0.0000 | 0.4690 |
| 19 | 1900 | 0.5243 | 0.0002481749 | — | — | 22.8849 | 0.0000 | 0.4768 |
| 20 | 2000 | 0.4840 | 0.0002454156 | 0.5258 | 0.0777 | 22.8825 | 73.2003 | 0.5054 |
| 21 | 2100 | 0.4629 | 0.000242653 | — | — | 22.9022 | 0.0000 | 0.4242 |
| 22 | 2200 | 0.4710 | 0.0002398868 | — | — | 22.8228 | 0.0000 | 0.4893 |
| 23 | 2300 | 0.4604 | 0.0002371171 | — | — | 22.8602 | 0.0000 | 0.4816 |
| 24 | 2400 | 0.4592 | 0.0002343438 | — | — | 22.8770 | 0.0000 | 0.4602 |
| 25 | 2500 | 0.4220 | 0.0002315669 | — | — | 22.8805 | 0.0000 | 0.4577 |
| 26 | 2600 | 0.4612 | 0.0002287862 | — | — | 22.8728 | 0.0000 | 0.4674 |
| 27 | 2700 | 0.4317 | 0.0002260018 | — | — | 22.8726 | 0.0000 | 0.4644 |
| 28 | 2800 | 0.4283 | 0.0002232135 | — | — | 22.8742 | 0.0000 | 0.4777 |
| 29 | 2900 | 0.4117 | 0.0002204214 | — | — | 22.8821 | 0.0000 | 0.4662 |
| 30 | 3000 | 0.4053 | 0.0002176254 | 0.6780 | 0.2251 | 22.8698 | 69.9833 | 0.5081 |
| 31 | 3100 | 0.4323 | 0.0002148253 | — | — | 22.7702 | 0.0000 | 0.4415 |
| 32 | 3200 | 0.4026 | 0.0002120212 | — | — | 22.8228 | 0.0000 | 0.4692 |
| 33 | 3300 | 0.4219 | 0.000209213 | — | — | 22.8616 | 0.0000 | 0.4742 |
| 34 | 3400 | 0.4059 | 0.0002064005 | — | — | 22.9025 | 0.0000 | 0.4711 |
| 35 | 3500 | 0.3775 | 0.0002035838 | — | — | 22.9061 | 0.0000 | 0.4633 |
| 36 | 3600 | 0.3970 | 0.0002007628 | — | — | 22.9007 | 0.0000 | 0.4748 |
| 37 | 3700 | 0.3567 | 0.0001979373 | — | — | 22.8795 | 0.0000 | 0.4564 |
| 38 | 3800 | 0.3669 | 0.0001951074 | — | — | 22.8826 | 0.0000 | 0.4597 |
| 39 | 3900 | 0.3575 | 0.0001922729 | — | — | 23.0278 | 0.0000 | 0.4489 |
| 40 | 4000 | 0.3590 | 0.0001894338 | 0.6535 | 0.2297 | 22.8698 | 69.2429 | 0.5115 |
| 41 | 4100 | 0.3998 | 0.0001865899 | — | — | 22.7699 | 0.0000 | 0.4281 |
| 42 | 4200 | 0.3710 | 0.0001837412 | — | — | 22.8135 | 0.0000 | 0.4655 |
| 43 | 4300 | 0.3795 | 0.0001808875 | — | — | 22.8389 | 0.0000 | 0.4658 |
| 44 | 4400 | 0.3519 | 0.0001780289 | — | — | 22.8385 | 0.0000 | 0.4766 |
| 45 | 4500 | 0.3469 | 0.0001751651 | — | — | 22.8500 | 0.0000 | 0.4736 |
| 46 | 4600 | 0.3259 | 0.0001722962 | — | — | 22.8579 | 0.0000 | 0.4823 |
| 47 | 4700 | 0.3177 | 0.0001694219 | — | — | 22.8698 | 0.0000 | 0.4753 |
| 48 | 4800 | 0.3395 | 0.0001665422 | — | — | 22.8640 | 0.0000 | 0.4626 |
| 49 | 4900 | 0.3222 | 0.0001636569 | — | — | 22.8629 | 0.0000 | 0.4781 |
| 50 | 5000 | 0.3278 | 0.000160766 | 0.6717 | 0.2649 | 22.8581 | 71.8239 | 0.5085 |
| 51 | 5100 | 0.3646 | 0.0001578693 | — | — | 22.7830 | 0.0000 | 0.4499 |
| 52 | 5200 | 0.3370 | 0.0001549667 | — | — | 22.8315 | 0.0000 | 0.4767 |
| 53 | 5300 | 0.3227 | 0.000152058 | — | — | 22.8160 | 0.0000 | 0.4774 |
| 54 | 5400 | 0.3284 | 0.0001491431 | — | — | 22.8451 | 0.0000 | 0.4566 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-minmax-seed0.json)

| Measurement | Value |
| --- | --- |
| Native predictions completed / expected / failed | 0 / 42 / 0 |
| Measured prediction pipeline wall seconds | — |
| Complete-cohort scans per second | — |
| Recorded case latency mean / p50 / p95 seconds | — / — / — |
| Prediction allocated / reserved peak GiB | — / — |
| Standardized model-only benchmark | not_recorded |
| Model-only patches/s; p50 / p95 ms | —; — / — |

Case latency includes preprocessing, tiled inference, native reconstruction and export; in overlapped runs it also includes queue time. It is neither model-only latency nor an additive stage wall time. No speed is inferred from GPU utilization snapshots.

