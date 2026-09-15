# swin_unetr-swin24-seed0

[All models](../comparison.md) · [Reading guide](../README.md)

Generated: 2026-09-15T01:08:53.939138+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

Status: **running**. Stage: **train**. GPU: **8**.

## Recipe and resources

| Setting | Value |
| --- | --- |
| Started / finished | 2026-09-15T00:08:44.952052+00:00 / — |
| Last worker update | 2026-09-15T00:09:26.862432+00:00 |
| Completed / budget steps | 4900 / 10000 |
| Live step / phase | 4950 / train |
| Parameters | 15703029 |
| Objective | dense_ce_dice_no_auxiliary_heads |
| Checkpoint selection | maximum validation mean per-case mass Dice; empty/empty=1 |
| Selected checkpoint SHA256 | — |
| Finished-stage allocated GPU-hours | 0.0000 |
| Active-stage allocated hours (estimate) | 0.9873 |
| Peak allocated / reserved GiB | 24.69 / 37.36 |

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
  "model": "swin_unetr",
  "model_options": {
    "feature_size": 24
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
| 1 | 100 | 1.4283 | 0.0002972986 | 0.2639 | 0.0000 | 62.2466 | 98.7319 | 0.4461 |
| 2 | 200 | 1.1606 | 0.0002945946 | — | — | 60.9908 | 0.0000 | 0.4372 |
| 3 | 300 | 1.0498 | 0.0002918877 | — | — | 60.9815 | 0.0000 | 0.4574 |
| 4 | 400 | 0.9596 | 0.0002891781 | — | — | 60.9974 | 0.0000 | 0.4802 |
| 5 | 500 | 0.8916 | 0.0002864656 | — | — | 61.0188 | 0.0000 | 0.4574 |
| 6 | 600 | 0.8437 | 0.0002837503 | — | — | 61.0072 | 0.0000 | 0.4720 |
| 7 | 700 | 0.8150 | 0.0002810321 | — | — | 60.9910 | 0.0000 | 0.4785 |
| 8 | 800 | 0.7810 | 0.000278311 | — | — | 60.9927 | 0.0000 | 0.5303 |
| 9 | 900 | 0.7691 | 0.0002755869 | — | — | 61.0000 | 0.0000 | 0.4720 |
| 10 | 1000 | 0.7466 | 0.0002728598 | 0.5616 | 0.0000 | 60.9960 | 102.7959 | 0.4661 |
| 11 | 1100 | 0.7197 | 0.0002701297 | — | — | 60.9558 | 0.0000 | 0.4776 |
| 12 | 1200 | 0.7217 | 0.0002673965 | — | — | 60.9642 | 0.0000 | 0.4840 |
| 13 | 1300 | 0.6949 | 0.0002646602 | — | — | 60.9853 | 0.0000 | 0.4792 |
| 14 | 1400 | 0.6791 | 0.0002619207 | — | — | 60.9746 | 0.0000 | 0.4802 |
| 15 | 1500 | 0.6609 | 0.0002591781 | — | — | 60.9872 | 0.0000 | 0.4774 |
| 16 | 1600 | 0.6396 | 0.0002564322 | — | — | 60.9832 | 0.0000 | 0.4817 |
| 17 | 1700 | 0.6035 | 0.0002536831 | — | — | 60.9826 | 0.0000 | 0.4671 |
| 18 | 1800 | 0.5798 | 0.0002509307 | — | — | 60.9845 | 0.0000 | 0.4861 |
| 19 | 1900 | 0.6017 | 0.0002481749 | — | — | 60.9997 | 0.0000 | 0.4782 |
| 20 | 2000 | 0.5445 | 0.0002454156 | 0.4764 | 0.1845 | 60.9837 | 100.1455 | 0.5247 |
| 21 | 2100 | 0.5359 | 0.000242653 | — | — | 60.9654 | 0.0000 | 0.4464 |
| 22 | 2200 | 0.5364 | 0.0002398868 | — | — | 60.9933 | 0.0000 | 0.4936 |
| 23 | 2300 | 0.5298 | 0.0002371171 | — | — | 60.9748 | 0.0000 | 0.4813 |
| 24 | 2400 | 0.5195 | 0.0002343438 | — | — | 60.9868 | 0.0000 | 0.4719 |
| 25 | 2500 | 0.4785 | 0.0002315669 | — | — | 60.9870 | 0.0000 | 0.4653 |
| 26 | 2600 | 0.5107 | 0.0002287862 | — | — | 60.9884 | 0.0000 | 0.4882 |
| 27 | 2700 | 0.4861 | 0.0002260018 | — | — | 60.9849 | 0.0000 | 0.4586 |
| 28 | 2800 | 0.4773 | 0.0002232135 | — | — | 60.9796 | 0.0000 | 0.4720 |
| 29 | 2900 | 0.4805 | 0.0002204214 | — | — | 60.9800 | 0.0000 | 0.4647 |
| 30 | 3000 | 0.4650 | 0.0002176254 | 0.6232 | 0.1286 | 60.9827 | 94.6894 | 0.4664 |
| 31 | 3100 | 0.4752 | 0.0002148253 | — | — | 60.9793 | 0.0000 | 0.4704 |
| 32 | 3200 | 0.4559 | 0.0002120212 | — | — | 60.9790 | 0.0000 | 0.4814 |
| 33 | 3300 | 0.4568 | 0.000209213 | — | — | 60.9885 | 0.0000 | 0.4763 |
| 34 | 3400 | 0.4565 | 0.0002064005 | — | — | 60.9927 | 0.0000 | 0.4700 |
| 35 | 3500 | 0.4311 | 0.0002035838 | — | — | 60.9899 | 0.0000 | 0.4834 |
| 36 | 3600 | 0.4332 | 0.0002007628 | — | — | 60.9936 | 0.0000 | 0.4850 |
| 37 | 3700 | 0.4101 | 0.0001979373 | — | — | 60.9916 | 0.0000 | 0.4798 |
| 38 | 3800 | 0.4220 | 0.0001951074 | — | — | 60.9760 | 0.0000 | 0.4698 |
| 39 | 3900 | 0.4178 | 0.0001922729 | — | — | 61.0504 | 0.0000 | 0.4700 |
| 40 | 4000 | 0.4055 | 0.0001894338 | 0.6450 | 0.2011 | 60.9935 | 98.6185 | 0.5155 |
| 41 | 4100 | 0.4374 | 0.0001865899 | — | — | 60.9687 | 0.0000 | 0.4302 |
| 42 | 4200 | 0.4104 | 0.0001837412 | — | — | 60.9988 | 0.0000 | 0.4804 |
| 43 | 4300 | 0.4042 | 0.0001808875 | — | — | 60.9899 | 0.0000 | 0.4743 |
| 44 | 4400 | 0.3816 | 0.0001780289 | — | — | 61.0128 | 0.0000 | 0.4589 |
| 45 | 4500 | 0.4053 | 0.0001751651 | — | — | 61.0399 | 0.0000 | 0.4827 |
| 46 | 4600 | 0.3780 | 0.0001722962 | — | — | 61.0220 | 0.0000 | 0.4672 |
| 47 | 4700 | 0.3732 | 0.0001694219 | — | — | 60.9867 | 0.0000 | 0.4669 |
| 48 | 4800 | 0.3763 | 0.0001665422 | — | — | 60.9915 | 0.0000 | 0.4605 |
| 49 | 4900 | 0.3645 | 0.0001636569 | — | — | 61.0000 | 0.0000 | 0.4746 |

## Final validation evaluation

Not available yet. Training loss or a forward-pass smoke test cannot replace this evaluation.

## Recorded training and inference data

[All-model training cost](../training-cost.md) · [All-model inference](../inference.md) · [Full numerical record](../records/swin_unetr-swin24-seed0.json)

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

