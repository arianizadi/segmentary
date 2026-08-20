# Raw versus EMA checkpoint weights

This paired analysis evaluates raw and exponential-moving-average (EMA) weights from the same final checkpoint. Dataset, validation split, seed, taxonomy, sliding window, stride, precision, and no-TTA policy are identical; only the selected weight set changes.

The main [model comparison](README.md) uses raw weights for every quality cell so the paper compares architectures under one uniform rule. Standardized FPS and memory are not repeated because raw and EMA use the same model graph and tensor shapes.

These are single-seed descriptive differences, not confidence intervals or evidence of statistical significance. The higher-endpoint column carries the direction so the human-facing table does not use signed or error-bar notation.
The 36 paired cells are a selected subset: they are endpoints previously admitted with EMA, generally architectures without running-stat BatchNorm. They do not form a random sample of all 111 quality cells.

## Summary

- Paired cells: 36.
- Raw higher: 14; EMA higher: 22; exact ties: 0.
- Across these cells, EMA averaged 0.05 mIoU percentage points higher.
- Raw and EMA give the same rank order across all 15 paired RailSem19 cells.

## Paired results

| model | protocol | raw mIoU | EMA mIoU | absolute difference (points) | higher endpoint |
|---|---|---:|---:|---:|---|
| `eomt_dinov3_large` | Cityscapes | 82.94 | 82.96 | 0.02 | EMA |
| `eomt_large` | Cityscapes | 82.72 | 82.74 | 0.02 | EMA |
| `hf_auto_beit_base_ade` | Cityscapes | 57.06 | 57.26 | 0.21 | EMA |
| `hf_auto_upernet_swin_tiny` | Cityscapes | 78.76 | 78.90 | 0.15 | EMA |
| `native_convnext_tiny_channelmapper_dpt` | Cityscapes | 80.50 | 80.72 | 0.22 | EMA |
| `native_convnext_tiny_uper` | Cityscapes | 81.35 | 81.48 | 0.14 | EMA |
| `native_resnet101_uper` | Cityscapes | 78.36 | 78.46 | 0.11 | EMA |
| `native_resnet50_aspp` | Cityscapes | 71.93 | 71.87 | 0.06 | raw |
| `native_resnet50_fpn_ocr` | Cityscapes | 78.67 | 78.73 | 0.06 | EMA |
| `segformer_b0` | Cityscapes | 74.55 | 74.81 | 0.26 | EMA |
| `segformer_b2` | Cityscapes | 80.48 | 80.65 | 0.17 | EMA |
| `segformer_b5` | Cityscapes | 82.30 | 82.40 | 0.11 | EMA |
| `smp_pan_resnext50` | Cityscapes | 67.25 | 67.15 | 0.10 | raw |
| `smp_upernet_mit_b0` | Cityscapes | 75.74 | 75.47 | 0.27 | raw |
| `smp_upernet_resnet101` | Cityscapes | 78.15 | 78.57 | 0.42 | EMA |
| `upernet_convnext` | Cityscapes | 80.88 | 81.03 | 0.14 | EMA |
| `eomt_dinov3_large` | Cityscapes to RailSem19 | 69.84 | 69.50 | 0.34 | raw |
| `eomt_large` | Cityscapes to RailSem19 | 69.96 | 69.66 | 0.30 | raw |
| `hf_auto_upernet_swin_tiny` | Cityscapes to RailSem19 | 67.26 | 67.90 | 0.63 | EMA |
| `native_convnext_tiny_channelmapper_dpt` | Cityscapes to RailSem19 | 70.42 | 70.31 | 0.12 | raw |
| `native_convnext_tiny_uper` | Cityscapes to RailSem19 | 69.61 | 70.22 | 0.61 | EMA |
| `eomt_dinov3_large` | RailSem19 | 71.45 | 71.42 | 0.02 | raw |
| `eomt_large` | RailSem19 | 72.14 | 72.13 | 0.01 | raw |
| `hf_auto_beit_base_ade` | RailSem19 | 54.17 | 53.98 | 0.19 | raw |
| `hf_auto_upernet_swin_tiny` | RailSem19 | 69.75 | 69.90 | 0.15 | EMA |
| `hrnet_w48_ocr` | RailSem19 | 68.52 | 68.62 | 0.11 | EMA |
| `native_convnext_tiny_channelmapper_dpt` | RailSem19 | 70.55 | 70.70 | 0.14 | EMA |
| `native_convnext_tiny_uper` | RailSem19 | 70.10 | 70.38 | 0.28 | EMA |
| `native_resnet101_uper` | RailSem19 | 68.48 | 68.44 | 0.05 | raw |
| `native_resnet50_deeplabv3plus` | RailSem19 | 66.38 | 66.41 | 0.02 | EMA |
| `segformer_b2` | RailSem19 | 70.42 | 70.39 | 0.03 | raw |
| `segformer_b5` | RailSem19 | 71.87 | 71.95 | 0.08 | EMA |
| `smp_deeplabv3_resnet50` | RailSem19 | 68.41 | 68.18 | 0.22 | raw |
| `smp_upernet_mit_b0` | RailSem19 | 66.85 | 66.56 | 0.29 | raw |
| `smp_upernet_resnet101` | RailSem19 | 67.17 | 66.82 | 0.34 | raw |
| `upernet_convnext` | RailSem19 | 70.66 | 70.74 | 0.08 | EMA |

## Interpretation

EMA smooths parameter updates and can improve validation quality, but it is not universally better. Architectures with running-stat BatchNorm can be especially sensitive because parameter EMA does not automatically provide matching averaged running buffers. Raw-only reporting avoids architecture-dependent endpoint selection and avoids choosing the better endpoint on the same validation set.

Machine-readable hashes, metrics, and provenance are retained in [`raw-evaluation-manifest.json`](raw-evaluation-manifest.json) and each model's record under [`records/`](records/).
