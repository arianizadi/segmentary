# dynunet-deep10k-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T00:38:50.653104+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **2**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T00:08:44.942069+00:00 / — |
| Last worker update | 2026-09-15T00:09:26.169813+00:00 |
| Completed / budget steps | 5400 / 10000 |
| Live step / phase | 5410 / train |
| Parameters | 16544265 |
| Objective | dense_ce_dice_with_two_native_decoder_auxiliary_losses |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4866 |
| Peak allocated / reserved GiB | 7.74 / 10.92 |

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
    "deep_supervision": true,
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
| 1 | 100 | 1.3371 | 0.0002972986 | 0.0000 | 0.0000 | 24.0869 | 99.0008 | 0.5279 |
| 2 | 200 | 1.0885 | 0.0002945946 | — | — | 22.9518 | 0.0000 | 0.4309 |
| 3 | 300 | 0.9952 | 0.0002918877 | — | — | 22.9680 | 0.0000 | 0.4749 |
| 4 | 400 | 0.9086 | 0.0002891781 | — | — | 23.1750 | 0.0000 | 0.5224 |
| 5 | 500 | 0.8507 | 0.0002864656 | — | — | 23.0507 | 0.0000 | 0.4434 |
| 6 | 600 | 0.8010 | 0.0002837503 | — | — | 23.0445 | 0.0000 | 0.4594 |
| 7 | 700 | 0.7571 | 0.0002810321 | — | — | 23.0719 | 0.0000 | 0.4565 |
| 8 | 800 | 0.7162 | 0.000278311 | — | — | 23.0548 | 0.0000 | 0.4391 |
| 9 | 900 | 0.6815 | 0.0002755869 | — | — | 23.0321 | 0.0000 | 0.5224 |
| 10 | 1000 | 0.6436 | 0.0002728598 | 0.5324 | 0.0964 | 23.0587 | 71.9528 | 0.4871 |
| 11 | 1100 | 0.5863 | 0.0002701297 | — | — | 22.9301 | 0.0000 | 0.4317 |
| 12 | 1200 | 0.5902 | 0.0002673965 | — | — | 22.9872 | 0.0000 | 0.4670 |
| 13 | 1300 | 0.5551 | 0.0002646602 | — | — | 22.9803 | 0.0000 | 0.4556 |
| 14 | 1400 | 0.5579 | 0.0002619207 | — | — | 23.0221 | 0.0000 | 0.4615 |
| 15 | 1500 | 0.5382 | 0.0002591781 | — | — | 23.0024 | 0.0000 | 0.4649 |
| 16 | 1600 | 0.5362 | 0.0002564322 | — | — | 23.0428 | 0.0000 | 0.4433 |
| 17 | 1700 | 0.5255 | 0.0002536831 | — | — | 23.0438 | 0.0000 | 0.4683 |
| 18 | 1800 | 0.4903 | 0.0002509307 | — | — | 23.0665 | 0.0000 | 0.4737 |
| 19 | 1900 | 0.5258 | 0.0002481749 | — | — | 23.0706 | 0.0000 | 0.4437 |
| 20 | 2000 | 0.4554 | 0.0002454156 | 0.5546 | 0.2097 | 23.0652 | 73.7933 | 0.4863 |
| 21 | 2100 | 0.4476 | 0.000242653 | — | — | 23.0781 | 0.0000 | 0.4258 |
| 22 | 2200 | 0.4698 | 0.0002398868 | — | — | 22.9238 | 0.0000 | 0.4536 |
| 23 | 2300 | 0.4486 | 0.0002371171 | — | — | 22.9835 | 0.0000 | 0.4488 |
| 24 | 2400 | 0.4523 | 0.0002343438 | — | — | 23.0237 | 0.0000 | 0.4530 |
| 25 | 2500 | 0.4204 | 0.0002315669 | — | — | 23.0367 | 0.0000 | 0.4548 |
| 26 | 2600 | 0.4638 | 0.0002287862 | — | — | 23.0498 | 0.0000 | 0.4534 |
| 27 | 2700 | 0.4234 | 0.0002260018 | — | — | 23.0453 | 0.0000 | 0.4727 |
| 28 | 2800 | 0.4148 | 0.0002232135 | — | — | 23.0710 | 0.0000 | 0.4672 |
| 29 | 2900 | 0.4007 | 0.0002204214 | — | — | 23.0671 | 0.0000 | 0.4608 |
| 30 | 3000 | 0.4068 | 0.0002176254 | 0.6702 | 0.2413 | 23.0374 | 73.5640 | 0.5013 |
| 31 | 3100 | 0.4113 | 0.0002148253 | — | — | 22.8972 | 0.0000 | 0.4336 |
| 32 | 3200 | 0.4170 | 0.0002120212 | — | — | 22.9264 | 0.0000 | 0.4690 |
| 33 | 3300 | 0.4220 | 0.000209213 | — | — | 23.0113 | 0.0000 | 0.4536 |
| 34 | 3400 | 0.4098 | 0.0002064005 | — | — | 23.0436 | 0.0000 | 0.4695 |
| 35 | 3500 | 0.3887 | 0.0002035838 | — | — | 23.0600 | 0.0000 | 0.4684 |
| 36 | 3600 | 0.3931 | 0.0002007628 | — | — | 23.0533 | 0.0000 | 0.4571 |
| 37 | 3700 | 0.3791 | 0.0001979373 | — | — | 23.0294 | 0.0000 | 0.4707 |
| 38 | 3800 | 0.3554 | 0.0001951074 | — | — | 23.0295 | 0.0000 | 0.4525 |
| 39 | 3900 | 0.3653 | 0.0001922729 | — | — | 23.1471 | 0.0000 | 0.4640 |
| 40 | 4000 | 0.3429 | 0.0001894338 | 0.6762 | 0.2508 | 23.0215 | 74.8181 | 0.4928 |
| 41 | 4100 | 0.3938 | 0.0001865899 | — | — | 22.8790 | 0.0000 | 0.4208 |
| 42 | 4200 | 0.3595 | 0.0001837412 | — | — | 22.9594 | 0.0000 | 0.4717 |
| 43 | 4300 | 0.3664 | 0.0001808875 | — | — | 23.0101 | 0.0000 | 0.4715 |
| 44 | 4400 | 0.3573 | 0.0001780289 | — | — | 23.0425 | 0.0000 | 0.4574 |
| 45 | 4500 | 0.3499 | 0.0001751651 | — | — | 23.0648 | 0.0000 | 0.4799 |
| 46 | 4600 | 0.3195 | 0.0001722962 | — | — | 23.0271 | 0.0000 | 0.4733 |
| 47 | 4700 | 0.3184 | 0.0001694219 | — | — | 23.0188 | 0.0000 | 0.4557 |
| 48 | 4800 | 0.3398 | 0.0001665422 | — | — | 22.9976 | 0.0000 | 0.4774 |
| 49 | 4900 | 0.3273 | 0.0001636569 | — | — | 23.0035 | 0.0000 | 0.4613 |
| 50 | 5000 | 0.3486 | 0.000160766 | 0.6899 | 0.2585 | 23.0867 | 73.8134 | 0.5076 |
| 51 | 5100 | 0.3586 | 0.0001578693 | — | — | 22.9408 | 0.0000 | 0.4379 |
| 52 | 5200 | 0.3262 | 0.0001549667 | — | — | 22.9869 | 0.0000 | 0.4711 |
| 53 | 5300 | 0.3246 | 0.000152058 | — | — | 23.0115 | 0.0000 | 0.4682 |
| 54 | 5400 | 0.3310 | 0.0001491431 | — | — | 23.0193 | 0.0000 | 0.4577 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-deep10k-seed0.json)

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

