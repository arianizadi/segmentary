# dynunet-focal10-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T00:38:50.653104+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **4**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T00:08:44.945472+00:00 / — |
| Last worker update | 2026-09-15T00:09:27.433805+00:00 |
| Completed / budget steps | 5500 / 10000 |
| Live step / phase | 5530 / train |
| Parameters | 16543683 |
| Objective | batch_foreground_dice_plus_multiclass_focal |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.4863 |
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
| 1 | 100 | 1.0612 | 0.0002972986 | 0.2437 | 0.0000 | 23.4945 | 98.3801 | 0.5253 |
| 2 | 200 | 0.9941 | 0.0002945946 | — | — | 22.6351 | 0.0000 | 0.4211 |
| 3 | 300 | 0.9655 | 0.0002918877 | — | — | 22.6986 | 0.0000 | 0.4691 |
| 4 | 400 | 0.9108 | 0.0002891781 | — | — | 22.9037 | 0.0000 | 0.4382 |
| 5 | 500 | 0.8413 | 0.0002864656 | — | — | 22.7859 | 0.0000 | 0.4578 |
| 6 | 600 | 0.7825 | 0.0002837503 | — | — | 22.8111 | 0.0000 | 0.4740 |
| 7 | 700 | 0.7519 | 0.0002810321 | — | — | 22.8144 | 0.0000 | 0.4436 |
| 8 | 800 | 0.7145 | 0.000278311 | — | — | 22.7894 | 0.0000 | 0.4399 |
| 9 | 900 | 0.7067 | 0.0002755869 | — | — | 22.8024 | 0.0000 | 0.4416 |
| 10 | 1000 | 0.6865 | 0.0002728598 | 0.5984 | 0.0668 | 22.8060 | 72.3862 | 0.4952 |
| 11 | 1100 | 0.6364 | 0.0002701297 | — | — | 22.7195 | 0.0000 | 0.4233 |
| 12 | 1200 | 0.6107 | 0.0002673965 | — | — | 22.7733 | 0.0000 | 0.4524 |
| 13 | 1300 | 0.5845 | 0.0002646602 | — | — | 22.7865 | 0.0000 | 0.4411 |
| 14 | 1400 | 0.5694 | 0.0002619207 | — | — | 22.7940 | 0.0000 | 0.4352 |
| 15 | 1500 | 0.5294 | 0.0002591781 | — | — | 22.8044 | 0.0000 | 0.4532 |
| 16 | 1600 | 0.5475 | 0.0002564322 | — | — | 22.8099 | 0.0000 | 0.4661 |
| 17 | 1700 | 0.5114 | 0.0002536831 | — | — | 22.8111 | 0.0000 | 0.4475 |
| 18 | 1800 | 0.4939 | 0.0002509307 | — | — | 22.8228 | 0.0000 | 0.4466 |
| 19 | 1900 | 0.5124 | 0.0002481749 | — | — | 22.8260 | 0.0000 | 0.4430 |
| 20 | 2000 | 0.4643 | 0.0002454156 | 0.5944 | 0.2457 | 22.8266 | 69.1805 | 0.5251 |
| 21 | 2100 | 0.4652 | 0.000242653 | — | — | 22.8611 | 0.0000 | 0.4287 |
| 22 | 2200 | 0.4667 | 0.0002398868 | — | — | 22.7681 | 0.0000 | 0.4544 |
| 23 | 2300 | 0.4667 | 0.0002371171 | — | — | 22.8020 | 0.0000 | 0.4570 |
| 24 | 2400 | 0.4480 | 0.0002343438 | — | — | 22.8310 | 0.0000 | 0.4738 |
| 25 | 2500 | 0.4120 | 0.0002315669 | — | — | 22.8324 | 0.0000 | 0.4755 |
| 26 | 2600 | 0.4666 | 0.0002287862 | — | — | 22.8507 | 0.0000 | 0.4557 |
| 27 | 2700 | 0.4140 | 0.0002260018 | — | — | 22.8385 | 0.0000 | 0.4502 |
| 28 | 2800 | 0.4121 | 0.0002232135 | — | — | 22.8272 | 0.0000 | 0.4674 |
| 29 | 2900 | 0.4128 | 0.0002204214 | — | — | 22.8277 | 0.0000 | 0.4568 |
| 30 | 3000 | 0.3959 | 0.0002176254 | 0.6994 | 0.2853 | 22.8347 | 73.3546 | 0.5081 |
| 31 | 3100 | 0.4034 | 0.0002148253 | — | — | 22.7072 | 0.0000 | 0.4312 |
| 32 | 3200 | 0.3932 | 0.0002120212 | — | — | 22.7630 | 0.0000 | 0.4584 |
| 33 | 3300 | 0.4113 | 0.000209213 | — | — | 22.7996 | 0.0000 | 0.4694 |
| 34 | 3400 | 0.3977 | 0.0002064005 | — | — | 22.8194 | 0.0000 | 0.4693 |
| 35 | 3500 | 0.3975 | 0.0002035838 | — | — | 22.8376 | 0.0000 | 0.4683 |
| 36 | 3600 | 0.3806 | 0.0002007628 | — | — | 22.8487 | 0.0000 | 0.4521 |
| 37 | 3700 | 0.3590 | 0.0001979373 | — | — | 22.8321 | 0.0000 | 0.4645 |
| 38 | 3800 | 0.3693 | 0.0001951074 | — | — | 22.8323 | 0.0000 | 0.4672 |
| 39 | 3900 | 0.3622 | 0.0001922729 | — | — | 22.9697 | 0.0000 | 0.4554 |
| 40 | 4000 | 0.3519 | 0.0001894338 | 0.6803 | 0.2732 | 22.8421 | 68.3845 | 0.4746 |
| 41 | 4100 | 0.3838 | 0.0001865899 | — | — | 22.7220 | 0.0000 | 0.4617 |
| 42 | 4200 | 0.3473 | 0.0001837412 | — | — | 22.7870 | 0.0000 | 0.4627 |
| 43 | 4300 | 0.3718 | 0.0001808875 | — | — | 22.8088 | 0.0000 | 0.4772 |
| 44 | 4400 | 0.3502 | 0.0001780289 | — | — | 22.8010 | 0.0000 | 0.4855 |
| 45 | 4500 | 0.3464 | 0.0001751651 | — | — | 22.8011 | 0.0000 | 0.4600 |
| 46 | 4600 | 0.3194 | 0.0001722962 | — | — | 22.8137 | 0.0000 | 0.4815 |
| 47 | 4700 | 0.3310 | 0.0001694219 | — | — | 22.8230 | 0.0000 | 0.4802 |
| 48 | 4800 | 0.3472 | 0.0001665422 | — | — | 22.8309 | 0.0000 | 0.4730 |
| 49 | 4900 | 0.3253 | 0.0001636569 | — | — | 22.8295 | 0.0000 | 0.5083 |
| 50 | 5000 | 0.3453 | 0.000160766 | 0.7185 | 0.3238 | 22.8321 | 67.9470 | 0.5108 |
| 51 | 5100 | 0.3517 | 0.0001578693 | — | — | 22.7346 | 0.0000 | 0.4436 |
| 52 | 5200 | 0.3224 | 0.0001549667 | — | — | 22.7908 | 0.0000 | 0.4653 |
| 53 | 5300 | 0.3143 | 0.000152058 | — | — | 22.8139 | 0.0000 | 0.4688 |
| 54 | 5400 | 0.3354 | 0.0001491431 | — | — | 22.8035 | 0.0000 | 0.4648 |
| 55 | 5500 | 0.3107 | 0.0001462219 | — | — | 22.8135 | 0.0000 | 0.4596 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/dynunet-focal10-seed0.json)

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

