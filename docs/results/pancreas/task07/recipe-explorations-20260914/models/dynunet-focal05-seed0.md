# dynunet-focal05-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T00:38:50.653104+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **3**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T00:08:44.943624+00:00 / — |
| Last worker update | 2026-09-15T00:09:26.482605+00:00 |
| Completed / budget steps | 5500 / 10000 |
| Live step / phase | 5501 / train |
| Parameters | 16543683 |
| Objective | batch_foreground_dice_plus_multiclass_focal |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4866 |
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
| 1 | 100 | 1.0213 | 0.0002972986 | 0.2666 | 0.0000 | 23.3429 | 97.7913 | 0.4362 |
| 2 | 200 | 0.9737 | 0.0002945946 | — | — | 22.6824 | 0.0000 | 0.4195 |
| 3 | 300 | 0.9309 | 0.0002918877 | — | — | 22.7692 | 0.0000 | 0.5071 |
| 4 | 400 | 0.8599 | 0.0002891781 | — | — | 22.9542 | 0.0000 | 0.4590 |
| 5 | 500 | 0.7895 | 0.0002864656 | — | — | 22.8584 | 0.0000 | 0.4565 |
| 6 | 600 | 0.7494 | 0.0002837503 | — | — | 22.8513 | 0.0000 | 0.4679 |
| 7 | 700 | 0.7296 | 0.0002810321 | — | — | 22.8457 | 0.0000 | 0.4696 |
| 8 | 800 | 0.6991 | 0.000278311 | — | — | 22.8512 | 0.0000 | 0.4786 |
| 9 | 900 | 0.6859 | 0.0002755869 | — | — | 22.8572 | 0.0000 | 0.4795 |
| 10 | 1000 | 0.6364 | 0.0002728598 | 0.5471 | 0.1052 | 22.8711 | 70.5556 | 0.5140 |
| 11 | 1100 | 0.5823 | 0.0002701297 | — | — | 22.7489 | 0.0000 | 0.4421 |
| 12 | 1200 | 0.5460 | 0.0002673965 | — | — | 22.8203 | 0.0000 | 0.4517 |
| 13 | 1300 | 0.5382 | 0.0002646602 | — | — | 22.8626 | 0.0000 | 0.4569 |
| 14 | 1400 | 0.5485 | 0.0002619207 | — | — | 22.8844 | 0.0000 | 0.4801 |
| 15 | 1500 | 0.5223 | 0.0002591781 | — | — | 22.9088 | 0.0000 | 0.4805 |
| 16 | 1600 | 0.5392 | 0.0002564322 | — | — | 22.8836 | 0.0000 | 0.4694 |
| 17 | 1700 | 0.5020 | 0.0002536831 | — | — | 22.8890 | 0.0000 | 0.4798 |
| 18 | 1800 | 0.4783 | 0.0002509307 | — | — | 22.8992 | 0.0000 | 0.4605 |
| 19 | 1900 | 0.5062 | 0.0002481749 | — | — | 22.8912 | 0.0000 | 0.4684 |
| 20 | 2000 | 0.4614 | 0.0002454156 | 0.4670 | 0.1965 | 22.8945 | 71.9513 | 0.5134 |
| 21 | 2100 | 0.4550 | 0.000242653 | — | — | 22.9146 | 0.0000 | 0.4310 |
| 22 | 2200 | 0.4549 | 0.0002398868 | — | — | 22.8189 | 0.0000 | 0.4597 |
| 23 | 2300 | 0.4529 | 0.0002371171 | — | — | 22.8643 | 0.0000 | 0.4571 |
| 24 | 2400 | 0.4479 | 0.0002343438 | — | — | 22.8930 | 0.0000 | 0.4588 |
| 25 | 2500 | 0.3903 | 0.0002315669 | — | — | 22.9033 | 0.0000 | 0.4728 |
| 26 | 2600 | 0.4301 | 0.0002287862 | — | — | 22.9099 | 0.0000 | 0.4826 |
| 27 | 2700 | 0.4006 | 0.0002260018 | — | — | 22.8928 | 0.0000 | 0.4729 |
| 28 | 2800 | 0.3907 | 0.0002232135 | — | — | 22.8849 | 0.0000 | 0.4845 |
| 29 | 2900 | 0.4224 | 0.0002204214 | — | — | 22.8967 | 0.0000 | 0.4680 |
| 30 | 3000 | 0.3955 | 0.0002176254 | 0.6754 | 0.2842 | 22.8807 | 70.4712 | 0.4987 |
| 31 | 3100 | 0.4031 | 0.0002148253 | — | — | 22.7592 | 0.0000 | 0.4266 |
| 32 | 3200 | 0.3805 | 0.0002120212 | — | — | 22.8279 | 0.0000 | 0.4704 |
| 33 | 3300 | 0.3892 | 0.000209213 | — | — | 22.8489 | 0.0000 | 0.4607 |
| 34 | 3400 | 0.3850 | 0.0002064005 | — | — | 22.8836 | 0.0000 | 0.4642 |
| 35 | 3500 | 0.3765 | 0.0002035838 | — | — | 22.8813 | 0.0000 | 0.4718 |
| 36 | 3600 | 0.3912 | 0.0002007628 | — | — | 22.8688 | 0.0000 | 0.4499 |
| 37 | 3700 | 0.3666 | 0.0001979373 | — | — | 22.8853 | 0.0000 | 0.4635 |
| 38 | 3800 | 0.3462 | 0.0001951074 | — | — | 22.8800 | 0.0000 | 0.4642 |
| 39 | 3900 | 0.3698 | 0.0001922729 | — | — | 23.0483 | 0.0000 | 0.4566 |
| 40 | 4000 | 0.3643 | 0.0001894338 | 0.6548 | 0.2576 | 22.8748 | 71.9319 | 0.4602 |
| 41 | 4100 | 0.3972 | 0.0001865899 | — | — | 22.8366 | 0.0000 | 0.4608 |
| 42 | 4200 | 0.3558 | 0.0001837412 | — | — | 22.7984 | 0.0000 | 0.4547 |
| 43 | 4300 | 0.3632 | 0.0001808875 | — | — | 22.8320 | 0.0000 | 0.4591 |
| 44 | 4400 | 0.3428 | 0.0001780289 | — | — | 22.8754 | 0.0000 | 0.4591 |
| 45 | 4500 | 0.3404 | 0.0001751651 | — | — | 22.8799 | 0.0000 | 0.4560 |
| 46 | 4600 | 0.3289 | 0.0001722962 | — | — | 22.9040 | 0.0000 | 0.4755 |
| 47 | 4700 | 0.3172 | 0.0001694219 | — | — | 22.9012 | 0.0000 | 0.4778 |
| 48 | 4800 | 0.3325 | 0.0001665422 | — | — | 22.8930 | 0.0000 | 0.4561 |
| 49 | 4900 | 0.3176 | 0.0001636569 | — | — | 22.8923 | 0.0000 | 0.4615 |
| 50 | 5000 | 0.3234 | 0.000160766 | 0.7020 | 0.3013 | 22.8963 | 71.9848 | 0.4999 |
| 51 | 5100 | 0.3374 | 0.0001578693 | — | — | 22.7483 | 0.0000 | 0.4209 |
| 52 | 5200 | 0.3114 | 0.0001549667 | — | — | 22.8178 | 0.0000 | 0.4601 |
| 53 | 5300 | 0.3131 | 0.000152058 | — | — | 22.8471 | 0.0000 | 0.4570 |
| 54 | 5400 | 0.3189 | 0.0001491431 | — | — | 22.8699 | 0.0000 | 0.4748 |
| 55 | 5500 | 0.3033 | 0.0001462219 | — | — | 22.8959 | 0.0000 | 0.4523 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-focal05-seed0.json)

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

