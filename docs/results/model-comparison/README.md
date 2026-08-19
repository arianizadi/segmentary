# Model comparison: Cityscapes and RailSem19

This live comparison covers every shipped model recipe. Compatible results are reused instead of retrained. `—` means evidence is unavailable, not zero or failure. Quality tables show one clean mean; individual seeds remain in machine records.

## Training specification

These are the resolved settings used by this campaign, not generic model defaults. Each physical job occupies one L40S and performs one optimizer update after the listed number of accumulated micro-batches.

| aspect | campaign setting |
|---|---|
| GPU topology | one NVIDIA L40S per physical job |
| seed and determinism | seed 0; deterministic algorithms not forced; fixed seeds and full provenance are retained |
| precision | bf16-mixed |
| input pipeline | 8 CPU data-loader workers per job; model-specific crop and batching are below |
| optimizer | AdamW, betas 0.9/0.999, weight decay 0.05; backbone LR and layer-wise decay are model-specific below; fresh task components use 10x LR |
| LR schedule | 1,500-iteration linear warmup from ratio 1e-6, then per-iteration polynomial decay with power 0.9; gradient clipping 1.0 |
| EMA and cadence | EMA decay 0.9998; validation and periodic checkpoint every 4,000 optimizer iterations |
| augmentation | random scale 0.5-2.0, crop, horizontal flip p=0.5, and color jitter p=0.5; crop size is model-specific below |
| dense objectives | standalone Cityscapes CE; RailSem19-only and transfer adaptation CE + 0.5 Lovasz |
| EoMT query objective | Hungarian class/mask assignment with class/mask-BCE/Dice weights 2/5/5 and 8,192 matching points |
| protocol budgets | Cityscapes 40,000; RailSem19 40,000; transfer reuses City40 and trains RailSem19 for 20,000 iterations (60,000 cumulative) |
| transfer initialization | reuse the matching 40,000-iteration Cityscapes checkpoint, reset only the incompatible classifier, and train RailSem19 for 20,000 iterations; use 0.1x for backbone groups and 1.0x for model-declared head groups; retain the final common evaluation at Rail 20,000 |
| interruption recovery | same-attempt full-state resume from newest validated periodic checkpoint; fresh attempt only when no recovery checkpoint exists |
| final quality evaluation | automatic recorded weights (raw for running-stat BatchNorm; EMA otherwise), batch 1, 1024x1024 sliding window, stride 768, no TTA |

### Model-specific optimizer and batching settings

The fresh-component LR is the initial LR for newly initialized heads or adapters. Transfer adaptation applies 0.1x to backbone groups and 1.0x to the model-declared decoder/head groups.

| model | train crop | batch/GPU | accumulation | effective batch | backbone LR | fresh-component LR | LLRD | objective |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| [eomt_dinov3_large](../../catalog/models/builtin-eomt-dinov3-large/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-5 | 1.0e-4 | 0.75 | Hungarian query |
| [eomt_large](../../catalog/models/builtin-eomt-large/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-5 | 1.0e-4 | 0.75 | Hungarian query |
| [hf_auto_beit_base_ade](../../catalog/models/hf-auto-beit-base-ade/README.md) | 640x640 | 4 | 4 | 16 | 2.0e-5 | 2.0e-4 | 0.80 | dense semantic |
| [upernet_convnext](../../catalog/models/builtin-upernet-convnext/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [segformer_b5](../../catalog/models/builtin-segformer-b5/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [hf_auto_upernet_swin_tiny](../../catalog/models/hf-auto-upernet-swin-tiny/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 0.90 | dense semantic |
| [hrnet_w48_ocr](../../catalog/models/builtin-hrnet-w48-ocr/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet101_uper](../../catalog/models/native-resnet101-uper/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [segformer_b2](../../catalog/models/builtin-segformer-b2/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [smp_upernet_resnet101](../../catalog/models/smp-upernet-resnet101/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_deeplabv3plus_resnet101](../../catalog/models/smp-deeplabv3plus-resnet101/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [deeplabv3plus_r101](../../catalog/models/builtin-deeplabv3plus-r101-alias/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_convnext_tiny_uper](../../catalog/models/native-convnext-tiny-uper/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_convnext_tiny_channelmapper_dpt](../../catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_pan_resnext50](../../catalog/models/smp-pan-resnext50/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet50_deeplabv3plus](../../catalog/models/native-resnet50-deeplabv3plus/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet50_fpn_ocr](../../catalog/models/native-resnet50-fpn-ocr/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet50_psp](../../catalog/models/native-resnet50-psp/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet50_aspp](../../catalog/models/native-resnet50-aspp/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_deeplabv3_resnet50](../../catalog/models/smp-deeplabv3-resnet50/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_fpn_resnet50](../../catalog/models/smp-fpn-resnet50/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_upernet_mit_b0](../../catalog/models/smp-upernet-mit-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [segformer_b0](../../catalog/models/builtin-segformer-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [hf_auto_segformer_b0](../../catalog/models/hf-auto-segformer-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [smp_unet_resnet34](../../catalog/models/smp-unet-resnet34/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_unetplusplus_efficientnet_b0](../../catalog/models/smp-unetplusplus-efficientnet-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_manet_efficientnet_b0](../../catalog/models/smp-manet-efficientnet-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_efficientnet_b0_deeplabv3plus](../../catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [hf_auto_mobilevitv2_deeplabv3](../../catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [hf_auto_mobilevit_xxs_deeplabv3](../../catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [hf_auto_mobilenetv2_deeplabv3](../../catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_mobilenetv3_large_deeplabv3plus](../../catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_mobilenetv3_large_lraspp](../../catalog/models/native-mobilenetv3-large-lraspp/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_pspnet_mobilenet_v2](../../catalog/models/smp-pspnet-mobilenet-v2/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_linknet_mobilenet_v2](../../catalog/models/smp-linknet-mobilenet-v2/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet18_fpn_segformer_aux](../../catalog/models/native-resnet18-fpn-segformer-aux/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet18_fpn_fcn](../../catalog/models/native-resnet18-fpn-fcn/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |

## Quality

| priority | model | status | City mIoU (40k) | Rail mIoU (40k) | City → Rail mIoU (Rail20 / total60) |
|---:|---|---|---:|---:|---:|
| 1 | [eomt_dinov3_large](../../catalog/models/builtin-eomt-dinov3-large/README.md) | complete | 82.96 | 71.42 | 69.50 |
| 2 | [eomt_large](../../catalog/models/builtin-eomt-large/README.md) | complete | 82.74 | 72.13 | 69.66 |
| 3 | [hf_auto_beit_base_ade](../../catalog/models/hf-auto-beit-base-ade/README.md) | complete | 57.26 | 53.98 | 51.42 |
| 4 | [upernet_convnext](../../catalog/models/builtin-upernet-convnext/README.md) | complete | 81.03 | 70.74 | 69.32 |
| 5 | [segformer_b5](../../catalog/models/builtin-segformer-b5/README.md) | complete | 82.40 | 71.95 | 69.30 |
| 6 | [hf_auto_upernet_swin_tiny](../../catalog/models/hf-auto-upernet-swin-tiny/README.md) | complete | 78.90 | 69.90 | 67.90 |
| 7 | [hrnet_w48_ocr](../../catalog/models/builtin-hrnet-w48-ocr/README.md) | complete | 80.75 | 68.62 | 66.03 |
| 8 | [native_resnet101_uper](../../catalog/models/native-resnet101-uper/README.md) | complete | 78.46 | 68.44 | 66.89 |
| 9 | [segformer_b2](../../catalog/models/builtin-segformer-b2/README.md) | complete | 80.65 | 70.39 | 67.37 |
| 10 | [smp_upernet_resnet101](../../catalog/models/smp-upernet-resnet101/README.md) | complete | 78.57 | 66.82 | 66.06 |
| 11 | [smp_deeplabv3plus_resnet101](../../catalog/models/smp-deeplabv3plus-resnet101/README.md) | complete | 79.18 | 67.82 | 67.25 |
| 12 | [deeplabv3plus_r101](../../catalog/models/builtin-deeplabv3plus-r101-alias/README.md) | complete | 79.18 | 67.82 | 67.25 |
| 13 | [native_convnext_tiny_uper](../../catalog/models/native-convnext-tiny-uper/README.md) | complete | 81.48 | 70.38 | 70.22 |
| 14 | [native_convnext_tiny_channelmapper_dpt](../../catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) | complete | 80.72 | 70.70 | 70.31 |
| 15 | [smp_pan_resnext50](../../catalog/models/smp-pan-resnext50/README.md) | complete | 67.25 | 60.17 | 56.02 |
| 16 | [native_resnet50_deeplabv3plus](../../catalog/models/native-resnet50-deeplabv3plus/README.md) | complete | 76.31 | 66.41 | 64.68 |
| 17 | [native_resnet50_fpn_ocr](../../catalog/models/native-resnet50-fpn-ocr/README.md) | complete | 78.73 | 67.68 | 66.31 |
| 18 | [native_resnet50_psp](../../catalog/models/native-resnet50-psp/README.md) | complete | 72.45 | 64.56 | 61.83 |
| 19 | [native_resnet50_aspp](../../catalog/models/native-resnet50-aspp/README.md) | complete | 71.87 | 63.99 | 61.00 |
| 20 | [smp_deeplabv3_resnet50](../../catalog/models/smp-deeplabv3-resnet50/README.md) | complete | 78.61 | 68.18 | 66.11 |
| 21 | [smp_fpn_resnet50](../../catalog/models/smp-fpn-resnet50/README.md) | complete | 77.08 | 67.70 | 65.34 |
| 22 | [smp_upernet_mit_b0](../../catalog/models/smp-upernet-mit-b0/README.md) | complete | 75.47 | 66.56 | 65.11 |
| 23 | [segformer_b0](../../catalog/models/builtin-segformer-b0/README.md) | complete | 74.81 | 65.26 | 60.17 |
| 24 | [hf_auto_segformer_b0](../../catalog/models/hf-auto-segformer-b0/README.md) | complete | 74.47 | 65.86 | 61.30 |
| 25 | [smp_unet_resnet34](../../catalog/models/smp-unet-resnet34/README.md) | complete | 73.88 | 61.43 | 59.78 |
| 26 | [smp_unetplusplus_efficientnet_b0](../../catalog/models/smp-unetplusplus-efficientnet-b0/README.md) | complete | 72.79 | 61.93 | 58.95 |
| 27 | [smp_manet_efficientnet_b0](../../catalog/models/smp-manet-efficientnet-b0/README.md) | complete | 71.98 | 60.05 | 56.81 |
| 28 | [native_efficientnet_b0_deeplabv3plus](../../catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) | complete | 74.38 | 63.95 | 62.30 |
| 29 | [hf_auto_mobilevitv2_deeplabv3](../../catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) | complete | 74.40 | 64.34 | 60.83 |
| 30 | [hf_auto_mobilevit_xxs_deeplabv3](../../catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) | complete | 69.99 | 60.72 | 58.02 |
| 31 | [hf_auto_mobilenetv2_deeplabv3](../../catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) | complete | 67.74 | 57.93 | 53.29 |
| 32 | [native_mobilenetv3_large_deeplabv3plus](../../catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) | complete | 72.91 | 64.19 | 62.39 |
| 33 | [native_mobilenetv3_large_lraspp](../../catalog/models/native-mobilenetv3-large-lraspp/README.md) | complete | 69.45 | 57.64 | 56.76 |
| 34 | [smp_pspnet_mobilenet_v2](../../catalog/models/smp-pspnet-mobilenet-v2/README.md) | complete | 46.87 | 42.71 | 40.39 |
| 35 | [smp_linknet_mobilenet_v2](../../catalog/models/smp-linknet-mobilenet-v2/README.md) | complete | 59.82 | 52.86 | 48.54 |
| 36 | [native_resnet18_fpn_segformer_aux](../../catalog/models/native-resnet18-fpn-segformer-aux/README.md) | running | 73.54 | — | 58.82 |
| 37 | [native_resnet18_fpn_fcn](../../catalog/models/native-resnet18-fpn-fcn/README.md) | complete | 74.33 | 62.77 | 59.26 |

## Standardized model-only inference

Each unique physical model is measured exactly once from its RailSem19-only 21-class recorded final endpoint (raw for running-stat BatchNorm; EMA otherwise). Contract: NVIDIA L40S, PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes internal query-to-dense collapse and excludes I/O, preprocessing, sliding windows, argmax, and metrics.
The benchmark runs only after that model's RailSem19 training and final quality evaluation succeed, so FPS can remain pending while Cityscapes mIoU is already available.

Weight memory is the resident parameter tensors; the resume checkpoint also contains optimizer and EMA state; peak VRAM is allocator-reserved memory excluding the CUDA context.

| model | weights | parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak VRAM (reserved, excl. context) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| [eomt_dinov3_large](../../catalog/models/builtin-eomt-dinov3-large/README.md) | ema | 314,917,910 | 1201.3 MiB | 4805.9 MiB | 41.23 | 24.12 | 24.77 | 3.13 GiB |
| [eomt_large](../../catalog/models/builtin-eomt-large/README.md) | ema | 316,580,886 | 1207.7 MiB | 4831.3 MiB | 45.91 | 21.76 | 21.86 | 3.12 GiB |
| [hf_auto_beit_base_ade](../../catalog/models/hf-auto-beit-base-ade/README.md) | ema | 161,500,245 | 616.1 MiB | 2355.5 MiB | 2.52 | 394.46 | 411.51 | 3.77 GiB |
| [upernet_convnext](../../catalog/models/builtin-upernet-convnext/README.md) | ema | 80,887,221 | 308.6 MiB | 1235.0 MiB | 43.06 | 23.19 | 23.35 | 2.48 GiB |
| [segformer_b5](../../catalog/models/builtin-segformer-b5/README.md) | ema | 84,609,493 | 322.8 MiB | 1292.9 MiB | 26.74 | 37.00 | 39.55 | 2.57 GiB |
| [hf_auto_upernet_swin_tiny](../../catalog/models/hf-auto-upernet-swin-tiny/README.md) | ema | 58,953,423 | 224.9 MiB | 900.3 MiB | 42.33 | 23.48 | 24.47 | 2.41 GiB |
| [hrnet_w48_ocr](../../catalog/models/builtin-hrnet-w48-ocr/README.md) | ema | 73,168,490 | 279.1 MiB | 1119.2 MiB | 30.75 | 32.11 | 34.73 | 1.26 GiB |
| [native_resnet101_uper](../../catalog/models/native-resnet101-uper/README.md) | ema | 61,323,093 | 233.9 MiB | 937.2 MiB | 65.20 | 15.19 | 16.65 | 1.36 GiB |
| [segformer_b2](../../catalog/models/builtin-segformer-b2/README.md) | ema | 27,362,773 | 104.4 MiB | 418.1 MiB | 53.26 | 18.63 | 19.41 | 2.25 GiB |
| [smp_upernet_resnet101](../../catalog/models/smp-upernet-resnet101/README.md) | ema | 56,281,941 | 214.7 MiB | 860.4 MiB | 71.01 | 13.70 | 17.42 | 1.44 GiB |
| [smp_deeplabv3plus_resnet101](../../catalog/models/smp-deeplabv3plus-resnet101/README.md) | raw | 45,674,853 | 174.2 MiB | 698.5 MiB | 112.74 | 8.69 | 9.70 | 0.66 GiB |
| [deeplabv3plus_r101](../../catalog/models/builtin-deeplabv3plus-r101-alias/README.md) | raw | 45,674,853 | 174.2 MiB | 698.5 MiB | 112.74 | 8.69 | 9.70 | 0.66 GiB |
| [native_convnext_tiny_uper](../../catalog/models/native-convnext-tiny-uper/README.md) | ema | 36,849,525 | 140.6 MiB | 562.6 MiB | 75.58 | 13.18 | 13.33 | 1.24 GiB |
| [native_convnext_tiny_channelmapper_dpt](../../catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) | ema | 38,230,389 | 145.8 MiB | 583.7 MiB | 29.15 | 34.30 | 34.38 | 1.95 GiB |
| [smp_pan_resnext50](../../catalog/models/smp-pan-resnext50/README.md) | raw | 23,737,468 | 90.6 MiB | 363.2 MiB | 184.06 | 5.40 | 5.73 | 0.40 GiB |
| [native_resnet50_deeplabv3plus](../../catalog/models/native-resnet50-deeplabv3plus/README.md) | ema | 40,351,925 | 153.9 MiB | 616.5 MiB | 136.37 | 7.30 | 7.61 | 0.78 GiB |
| [native_resnet50_fpn_ocr](../../catalog/models/native-resnet50-fpn-ocr/README.md) | raw | 32,646,762 | 124.5 MiB | 499.0 MiB | 48.24 | 20.57 | 21.29 | 1.46 GiB |
| [native_resnet50_psp](../../catalog/models/native-resnet50-psp/README.md) | raw | 37,149,525 | 141.7 MiB | 567.6 MiB | 212.00 | 4.64 | 5.08 | 0.52 GiB |
| [native_resnet50_aspp](../../catalog/models/native-resnet50-aspp/README.md) | raw | 39,048,277 | 149.0 MiB | 596.6 MiB | 223.41 | 4.44 | 4.67 | 0.53 GiB |
| [smp_deeplabv3_resnet50](../../catalog/models/smp-deeplabv3-resnet50/README.md) | ema | 39,638,869 | 151.2 MiB | 605.7 MiB | 77.91 | 12.83 | 12.89 | 0.67 GiB |
| [smp_fpn_resnet50](../../catalog/models/smp-fpn-resnet50/README.md) | raw | 26,118,613 | 99.6 MiB | 399.3 MiB | 156.92 | 6.26 | 6.95 | 0.73 GiB |
| [smp_upernet_mit_b0](../../catalog/models/smp-upernet-mit-b0/README.md) | ema | 10,737,525 | 41.0 MiB | 164.2 MiB | 54.28 | 18.39 | 18.66 | 1.09 GiB |
| [segformer_b0](../../catalog/models/builtin-segformer-b0/README.md) | raw | 3,719,541 | 14.2 MiB | 57.1 MiB | 136.18 | 7.29 | 7.67 | 0.89 GiB |
| [hf_auto_segformer_b0](../../catalog/models/hf-auto-segformer-b0/README.md) | raw | 3,719,541 | 14.2 MiB | 57.1 MiB | 123.43 | 7.57 | 10.28 | 0.89 GiB |
| [smp_unet_resnet34](../../catalog/models/smp-unet-resnet34/README.md) | raw | 24,439,269 | 93.2 MiB | 373.4 MiB | 143.68 | 6.87 | 7.37 | 0.67 GiB |
| [smp_unetplusplus_efficientnet_b0](../../catalog/models/smp-unetplusplus-efficientnet-b0/README.md) | raw | 6,572,481 | 25.1 MiB | 98.0 MiB | 68.98 | 14.44 | 15.20 | 0.89 GiB |
| [smp_manet_efficientnet_b0](../../catalog/models/smp-manet-efficientnet-b0/README.md) | raw | 9,095,257 | 34.7 MiB | 136.6 MiB | 90.68 | 10.82 | 11.98 | 0.57 GiB |
| [native_efficientnet_b0_deeplabv3plus](../../catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) | raw | 5,721,681 | 21.8 MiB | 88.1 MiB | 143.40 | 6.47 | 9.83 | 0.43 GiB |
| [hf_auto_mobilevitv2_deeplabv3](../../catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) | raw | 13,318,654 | 50.8 MiB | 203.8 MiB | 84.66 | 11.79 | 11.91 | 0.39 GiB |
| [hf_auto_mobilevit_xxs_deeplabv3](../../catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) | raw | 1,854,853 | 7.1 MiB | 28.9 MiB | 34.78 | 28.67 | 29.04 | 3.30 GiB |
| [hf_auto_mobilenetv2_deeplabv3](../../catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) | raw | 2,525,717 | 9.6 MiB | 36.0 MiB | 166.66 | 5.96 | 6.59 | 0.45 GiB |
| [native_mobilenetv3_large_deeplabv3plus](../../catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) | raw | 8,067,845 | 30.8 MiB | 123.7 MiB | 168.14 | 5.93 | 6.45 | 0.44 GiB |
| [native_mobilenetv3_large_lraspp](../../catalog/models/native-mobilenetv3-large-lraspp/README.md) | raw | 3,221,330 | 12.3 MiB | 49.7 MiB | 234.22 | 4.17 | 4.79 | 0.30 GiB |
| [smp_pspnet_mobilenet_v2](../../catalog/models/smp-pspnet-mobilenet-v2/README.md) | raw | 2,355,533 | 9.0 MiB | 20.0 MiB | 344.52 | 2.90 | 2.94 | 0.36 GiB |
| [smp_linknet_mobilenet_v2](../../catalog/models/smp-linknet-mobilenet-v2/README.md) | raw | 4,320,519 | 16.5 MiB | 66.6 MiB | 178.77 | 5.53 | 6.10 | 0.32 GiB |
| [native_resnet18_fpn_segformer_aux](../../catalog/models/native-resnet18-fpn-segformer-aux/README.md) | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](../../catalog/models/native-resnet18-fpn-fcn/README.md) | raw | 12,631,253 | 48.2 MiB | 193.0 MiB | 226.85 | 4.38 | 4.60 | 0.64 GiB |

## Training cost

Wall time and GPU-hours include every curriculum stage; peak is per-device allocator-reserved training VRAM.

| model | Cityscapes wall / GPU-h | RailSem19 wall / GPU-h | transfer wall / GPU-h | peak train VRAM |
|---|---:|---:|---:|---:|
| [eomt_dinov3_large](../../catalog/models/builtin-eomt-dinov3-large/README.md) | 14h 06m 17s / 14.10 | 13h 41m 29s / 13.69 | 7h 36m 59s / 7.62 | 17.02 GiB |
| [eomt_large](../../catalog/models/builtin-eomt-large/README.md) | 13h 26m 42s / 13.45 | 14h 39m 19s / 14.66 | 7h 19m 43s / 7.33 | 16.86 GiB |
| [hf_auto_beit_base_ade](../../catalog/models/hf-auto-beit-base-ade/README.md) | 14h 40m 07s / 14.67 | 21h 55m 28s / 21.92 | 11h 05m 16s / 11.09 | 19.53 GiB |
| [upernet_convnext](../../catalog/models/builtin-upernet-convnext/README.md) | 13h 28m 59s / 13.48 | 16h 57m 54s / 16.96 | 9h 28m 19s / 9.47 | 10.60 GiB |
| [segformer_b5](../../catalog/models/builtin-segformer-b5/README.md) | 17h 59m 42s / 17.99 | 19h 38m 19s / 19.64 | 10h 48m 49s / 10.81 | 16.94 GiB |
| [hf_auto_upernet_swin_tiny](../../catalog/models/hf-auto-upernet-swin-tiny/README.md) | 14h 21m 30s / 14.36 | 17h 53m 41s / 17.89 | — / — | 8.88 GiB |
| [hrnet_w48_ocr](../../catalog/models/builtin-hrnet-w48-ocr/README.md) | — / — | 27h 48m 14s / 27.80 | 13h 54m 23s / 13.91 | 17.35 GiB |
| [native_resnet101_uper](../../catalog/models/native-resnet101-uper/README.md) | 7h 54m 19s / 7.91 | 13h 39m 24s / 13.66 | 6h 50m 30s / 6.84 | 6.88 GiB |
| [segformer_b2](../../catalog/models/builtin-segformer-b2/README.md) | 8h 10m 00s / 8.17 | 14h 17m 34s / 14.29 | 7h 06m 54s / 7.12 | 12.12 GiB |
| [smp_upernet_resnet101](../../catalog/models/smp-upernet-resnet101/README.md) | 9h 21m 34s / 9.36 | 12h 55m 26s / 12.92 | — / — | 6.70 GiB |
| [smp_deeplabv3plus_resnet101](../../catalog/models/smp-deeplabv3plus-resnet101/README.md) | — / — | 11h 51m 51s / 11.86 | 5h 58m 25s / 5.97 | 5.90 GiB |
| [deeplabv3plus_r101](../../catalog/models/builtin-deeplabv3plus-r101-alias/README.md) | — / — | 11h 51m 51s / 11.86 | 5h 58m 25s / 5.97 | 5.90 GiB |
| [native_convnext_tiny_uper](../../catalog/models/native-convnext-tiny-uper/README.md) | 9h 12m 18s / 9.21 | 12h 49m 26s / 12.82 | — / — | 6.23 GiB |
| [native_convnext_tiny_channelmapper_dpt](../../catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) | — / — | 22h 57m 26s / 22.96 | 11h 27m 14s / 11.45 | 11.42 GiB |
| [smp_pan_resnext50](../../catalog/models/smp-pan-resnext50/README.md) | — / — | 10h 36m 29s / 10.61 | 4h 15m 13s / 4.25 | 4.79 GiB |
| [native_resnet50_deeplabv3plus](../../catalog/models/native-resnet50-deeplabv3plus/README.md) | — / — | 11h 13m 54s / 11.23 | 5h 38m 08s / 5.64 | 5.03 GiB |
| [native_resnet50_fpn_ocr](../../catalog/models/native-resnet50-fpn-ocr/README.md) | 12h 42m 58s / 12.72 | 22h 44m 13s / 22.74 | 11h 22m 57s / 11.38 | 8.60 GiB |
| [native_resnet50_psp](../../catalog/models/native-resnet50-psp/README.md) | — / — | 12h 20m 09s / 12.34 | 6h 15m 52s / 6.26 | 4.21 GiB |
| [native_resnet50_aspp](../../catalog/models/native-resnet50-aspp/README.md) | 8h 00m 50s / 8.01 | 12h 23m 01s / 12.38 | 6h 11m 24s / 6.19 | 4.27 GiB |
| [smp_deeplabv3_resnet50](../../catalog/models/smp-deeplabv3-resnet50/README.md) | 14h 07m 22s / 14.12 | 17h 40m 01s / 17.67 | 8h 45m 07s / 8.75 | 6.60 GiB |
| [smp_fpn_resnet50](../../catalog/models/smp-fpn-resnet50/README.md) | — / — | 10h 23m 49s / 10.40 | 5h 13m 08s / 5.22 | 4.35 GiB |
| [smp_upernet_mit_b0](../../catalog/models/smp-upernet-mit-b0/README.md) | — / — | 14h 35m 12s / 14.59 | 7h 13m 36s / 7.23 | 6.70 GiB |
| [segformer_b0](../../catalog/models/builtin-segformer-b0/README.md) | — / — | 9h 51m 21s / 9.86 | 4h 55m 50s / 4.93 | 3.24 GiB |
| [hf_auto_segformer_b0](../../catalog/models/hf-auto-segformer-b0/README.md) | 5h 39m 20s / 5.66 | 9h 48m 13s / 9.80 | 4h 56m 03s / 4.93 | 3.24 GiB |
| [smp_unet_resnet34](../../catalog/models/smp-unet-resnet34/README.md) | 6h 17m 00s / 6.28 | 10h 43m 02s / 10.72 | 5h 21m 19s / 5.36 | 4.36 GiB |
| [smp_unetplusplus_efficientnet_b0](../../catalog/models/smp-unetplusplus-efficientnet-b0/README.md) | 9h 42m 08s / 9.70 | 2h 41m 15s / 2.69 | 6h 39m 56s / 6.67 | 6.24 GiB |
| [smp_manet_efficientnet_b0](../../catalog/models/smp-manet-efficientnet-b0/README.md) | 7h 43m 24s / 7.72 | 11h 44m 14s / 11.74 | 5h 53m 46s / 5.90 | 5.48 GiB |
| [native_efficientnet_b0_deeplabv3plus](../../catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) | 5h 57m 46s / 5.96 | 10h 09m 38s / 10.16 | 5h 05m 37s / 5.09 | 4.06 GiB |
| [hf_auto_mobilevitv2_deeplabv3](../../catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) | 7h 22m 10s / 7.37 | 12h 38m 53s / 12.65 | 6h 20m 27s / 6.34 | 4.96 GiB |
| [hf_auto_mobilevit_xxs_deeplabv3](../../catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) | 18h 40m 27s / 18.67 | 22h 28m 15s / 22.47 | 11h 14m 52s / 11.25 | 15.78 GiB |
| [hf_auto_mobilenetv2_deeplabv3](../../catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) | 9h 38m 35s / 9.64 | 5h 17m 58s / 5.30 | 6h 36m 03s / 6.60 | 5.83 GiB |
| [native_mobilenetv3_large_deeplabv3plus](../../catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) | 5h 03m 01s / 5.05 | 9h 37m 04s / 9.62 | 4h 48m 27s / 4.81 | 3.23 GiB |
| [native_mobilenetv3_large_lraspp](../../catalog/models/native-mobilenetv3-large-lraspp/README.md) | 1h 41m 02s / 1.68 | 2h 31m 14s / 2.52 | 4h 12m 17s / 4.20 | 2.65 GiB |
| [smp_pspnet_mobilenet_v2](../../catalog/models/smp-pspnet-mobilenet-v2/README.md) | 4h 11m 01s / 4.18 | 9h 09m 35s / 9.16 | 0h 54m 37s / 0.91 | 3.00 GiB |
| [smp_linknet_mobilenet_v2](../../catalog/models/smp-linknet-mobilenet-v2/README.md) | 5h 27m 32s / 5.46 | 9h 59m 29s / 9.99 | 4h 59m 39s / 4.99 | 3.82 GiB |
| [native_resnet18_fpn_segformer_aux](../../catalog/models/native-resnet18-fpn-segformer-aux/README.md) | 6h 13m 46s / 6.23 | — / — | 7h 03m 58s / 7.07 | 4.11 GiB |
| [native_resnet18_fpn_fcn](../../catalog/models/native-resnet18-fpn-fcn/README.md) | 2h 12m 01s / 2.20 | 9h 13m 56s / 9.23 | 4h 36m 48s / 4.61 | 3.10 GiB |

## Fixed protocol and files

- Cityscapes: 40,000 iterations, standard 19-class 500-image validation.
- RailSem19: 40,000 iterations, `rail_union`, fixed 850-image validation.
- Transfer: reuse the matching 40,000-iteration Cityscapes checkpoint and train RailSem19 for 20,000 iterations (60,000 cumulative); Cityscapes is never trained twice.
- Transfer warm-starts every compatible learned tensor and reinitialises only the 19-class to `rail_union` classifier mismatch.
- Quality evaluation: the exact recorded `raw` or `ema` endpoint for each protocol, 1024x1024 sliding window, stride 768, no TTA.
- [`results.csv`](results.csv): spreadsheet-friendly mean metrics, iterations, and resources.
- [`status.json`](status.json): machine-readable scope and completion state.
- [`records/`](records/): full class IoUs, retained seeds, resources, and provenance.

Campaign source SHA: `b9eb3e1f390b70aad63e78b2e723bd79b5266471`.

## RailSem19 accuracy-speed leaderboard

This lists and sorts all shipped model recipes. Models with both a final RailSem19-only mIoU and standardized L40S inference benchmark are ranked first; pending models remain visible below them until their evidence is complete. The recommendation score is accuracy-first: models must reach 60% RailSem19 mIoU to qualify, then the score weights normalized mIoU at 85% and log-scaled FPS at 15%. The quality gate prevents a weak but extremely fast model from taking over the leaderboard; log scaling also gives diminishing credit to already-high FPS. Below-floor models remain listed after qualified models, with their raw accuracy and speed ranks. This is a convenience recommendation rather than a universal deployment choice. Compatibility aliases remain visible and are labelled; they share the canonical recipe's weights and measurements.

| rank | model | status | quality gate | recommendation score | RailSem19 mIoU | accuracy rank | FPS | speed rank | p50 latency | weights | model memory | peak inference VRAM |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | [eomt_large](../../catalog/models/builtin-eomt-large/README.md) | complete | qualified | 94.97 | 72.13 | 1 | 45.91 | 28 | 21.76 ms | ema | 1207.7 MiB | 3.12 GiB |
| 2 | [native_convnext_tiny_uper](../../catalog/models/native-convnext-tiny-uper/README.md) | complete | qualified | 94.69 | 70.38 | 7 | 75.58 | 21 | 13.18 ms | ema | 140.6 MiB | 1.24 GiB |
| 3 | [eomt_dinov3_large](../../catalog/models/builtin-eomt-dinov3-large/README.md) | complete | qualified | 93.78 | 71.42 | 3 | 41.23 | 31 | 24.12 ms | ema | 1201.3 MiB | 3.13 GiB |
| 4 | [smp_fpn_resnet50](../../catalog/models/smp-fpn-resnet50/README.md) | complete | qualified | 93.76 | 67.70 | 14 | 156.92 | 10 | 6.26 ms | raw | 99.6 MiB | 0.73 GiB |
| 5 | [segformer_b2](../../catalog/models/builtin-segformer-b2/README.md) | complete | qualified | 93.53 | 70.39 | 6 | 53.26 | 26 | 18.63 ms | ema | 104.4 MiB | 2.25 GiB |
| 6 | [upernet_convnext](../../catalog/models/builtin-upernet-convnext/README.md) | complete | qualified | 93.17 | 70.74 | 4 | 43.06 | 29 | 23.19 ms | ema | 308.6 MiB | 2.48 GiB |
| 7 | [smp_deeplabv3plus_resnet101](../../catalog/models/smp-deeplabv3plus-resnet101/README.md) | complete | qualified | 92.97 | 67.82 | 12 | 112.74 | 16 | 8.69 ms | raw | 174.2 MiB | 0.66 GiB |
| 8 | [deeplabv3plus_r101](../../catalog/models/builtin-deeplabv3plus-r101-alias/README.md) *(alias of `smp_deeplabv3plus_resnet101`)* | complete | qualified | 92.97 | 67.82 | 12 | 112.74 | 16 | 8.69 ms | raw | 174.2 MiB | 0.66 GiB |
| 9 | [segformer_b5](../../catalog/models/builtin-segformer-b5/README.md) | complete | qualified | 92.70 | 71.95 | 2 | 26.74 | 35 | 37.00 ms | ema | 322.8 MiB | 2.57 GiB |
| 10 | [smp_deeplabv3_resnet50](../../catalog/models/smp-deeplabv3-resnet50/README.md) | complete | qualified | 92.27 | 68.18 | 11 | 77.91 | 20 | 12.83 ms | ema | 151.2 MiB | 0.67 GiB |
| 11 | [hf_auto_upernet_swin_tiny](../../catalog/models/hf-auto-upernet-swin-tiny/README.md) | complete | qualified | 92.17 | 69.90 | 8 | 42.33 | 30 | 23.48 ms | ema | 224.9 MiB | 2.41 GiB |
| 12 | [native_resnet101_uper](../../catalog/models/native-resnet101-uper/README.md) | complete | qualified | 91.99 | 68.44 | 10 | 65.20 | 24 | 15.19 ms | ema | 233.9 MiB | 1.36 GiB |
| 13 | [native_resnet50_deeplabv3plus](../../catalog/models/native-resnet50-deeplabv3plus/README.md) | complete | qualified | 91.85 | 66.41 | 18 | 136.37 | 13 | 7.30 ms | ema | 153.9 MiB | 0.78 GiB |
| 14 | [native_convnext_tiny_channelmapper_dpt](../../catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) | complete | qualified | 91.67 | 70.70 | 5 | 29.15 | 34 | 34.30 ms | ema | 145.8 MiB | 1.95 GiB |
| 15 | [hf_auto_segformer_b0](../../catalog/models/hf-auto-segformer-b0/README.md) | complete | qualified | 90.93 | 65.86 | 19 | 123.43 | 15 | 7.57 ms | raw | 14.2 MiB | 0.89 GiB |
| 16 | [native_resnet50_psp](../../catalog/models/native-resnet50-psp/README.md) | complete | qualified | 90.83 | 64.56 | 21 | 212.00 | 5 | 4.64 ms | raw | 141.7 MiB | 0.52 GiB |
| 17 | [segformer_b0](../../catalog/models/builtin-segformer-b0/README.md) | complete | qualified | 90.50 | 65.26 | 20 | 136.18 | 14 | 7.29 ms | raw | 14.2 MiB | 0.89 GiB |
| 18 | [smp_upernet_resnet101](../../catalog/models/smp-upernet-resnet101/README.md) | complete | qualified | 90.41 | 66.82 | 16 | 71.01 | 22 | 13.70 ms | ema | 214.7 MiB | 1.44 GiB |
| 19 | [native_resnet50_aspp](../../catalog/models/native-resnet50-aspp/README.md) | complete | qualified | 90.27 | 63.99 | 24 | 223.41 | 4 | 4.44 ms | raw | 149.0 MiB | 0.53 GiB |
| 20 | [native_resnet50_fpn_ocr](../../catalog/models/native-resnet50-fpn-ocr/README.md) | complete | qualified | 90.13 | 67.68 | 15 | 48.24 | 27 | 20.57 ms | raw | 124.5 MiB | 1.46 GiB |
| 21 | [native_mobilenetv3_large_deeplabv3plus](../../catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) | complete | qualified | 89.80 | 64.19 | 23 | 168.14 | 8 | 5.93 ms | raw | 30.8 MiB | 0.44 GiB |
| 22 | [hrnet_w48_ocr](../../catalog/models/builtin-hrnet-w48-ocr/README.md) | complete | qualified | 89.58 | 68.62 | 9 | 30.75 | 33 | 32.11 ms | ema | 279.1 MiB | 1.26 GiB |
| 23 | [smp_upernet_mit_b0](../../catalog/models/smp-upernet-mit-b0/README.md) | complete | qualified | 89.26 | 66.56 | 17 | 54.28 | 25 | 18.39 ms | ema | 41.0 MiB | 1.09 GiB |
| 24 | [native_efficientnet_b0_deeplabv3plus](../../catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) | complete | qualified | 89.09 | 63.95 | 25 | 143.40 | 12 | 6.47 ms | raw | 21.8 MiB | 0.43 GiB |
| 25 | [native_resnet18_fpn_fcn](../../catalog/models/native-resnet18-fpn-fcn/README.md) | complete | qualified | 88.86 | 62.77 | 26 | 226.85 | 3 | 4.38 ms | raw | 48.2 MiB | 0.64 GiB |
| 26 | [hf_auto_mobilevitv2_deeplabv3](../../catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) | complete | qualified | 88.07 | 64.34 | 22 | 84.66 | 19 | 11.79 ms | raw | 50.8 MiB | 0.39 GiB |
| 27 | [smp_unet_resnet34](../../catalog/models/smp-unet-resnet34/README.md) | complete | qualified | 86.10 | 61.43 | 28 | 143.68 | 11 | 6.87 ms | raw | 93.2 MiB | 0.67 GiB |
| 28 | [smp_pan_resnext50](../../catalog/models/smp-pan-resnext50/README.md) | complete | qualified | 85.21 | 60.17 | 30 | 184.06 | 6 | 5.40 ms | raw | 90.6 MiB | 0.40 GiB |
| 29 | [smp_unetplusplus_efficientnet_b0](../../catalog/models/smp-unetplusplus-efficientnet-b0/README.md) | complete | qualified | 84.67 | 61.93 | 27 | 68.98 | 23 | 14.44 ms | raw | 25.1 MiB | 0.89 GiB |
| 30 | [smp_manet_efficientnet_b0](../../catalog/models/smp-manet-efficientnet-b0/README.md) | complete | qualified | 83.24 | 60.05 | 31 | 90.68 | 18 | 10.82 ms | raw | 34.7 MiB | 0.57 GiB |
| 31 | [hf_auto_mobilevit_xxs_deeplabv3](../../catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) | complete | qualified | 81.14 | 60.72 | 29 | 34.78 | 32 | 28.67 ms | raw | 7.1 MiB | 3.30 GiB |
| 32 | [hf_auto_mobilenetv2_deeplabv3](../../catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) | complete | below 60% mIoU | — | 57.93 | 32 | 166.66 | 9 | 5.96 ms | raw | 9.6 MiB | 0.45 GiB |
| 33 | [native_mobilenetv3_large_lraspp](../../catalog/models/native-mobilenetv3-large-lraspp/README.md) | complete | below 60% mIoU | — | 57.64 | 33 | 234.22 | 2 | 4.17 ms | raw | 12.3 MiB | 0.30 GiB |
| 34 | [hf_auto_beit_base_ade](../../catalog/models/hf-auto-beit-base-ade/README.md) | complete | below 60% mIoU | — | 53.98 | 34 | 2.52 | 36 | 394.46 ms | ema | 616.1 MiB | 3.77 GiB |
| 35 | [smp_linknet_mobilenet_v2](../../catalog/models/smp-linknet-mobilenet-v2/README.md) | complete | below 60% mIoU | — | 52.86 | 35 | 178.77 | 7 | 5.53 ms | raw | 16.5 MiB | 0.32 GiB |
| 36 | [smp_pspnet_mobilenet_v2](../../catalog/models/smp-pspnet-mobilenet-v2/README.md) | complete | below 60% mIoU | — | 42.71 | 36 | 344.52 | 1 | 2.90 ms | raw | 9.0 MiB | 0.36 GiB |
| — | [native_resnet18_fpn_segformer_aux](../../catalog/models/native-resnet18-fpn-segformer-aux/README.md) | pending | — | — | — | — | — | — | — | — | — | — |
