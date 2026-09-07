# RTIS model comparison

**330/432 completed · 0 failed**

Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling.

[Dataset and preparation](../README.md) · [Mathematical mud-pumping audit](../mud-pumping-audit/README.md) · [CSV results](results.csv) · [Full machine records](status.json)

36 models; four initialization paths; seeds [0, 1, 2]. Train/val/test: 220/37/50 images. Test is held out. Validation groups are provisional and lack person, truck and on-rails ground truth. Seed variation does not establish independent-recording generalization.

## Quality

Validation **mIoU (%)** across classes. Cells show the mean over completed seeds. Per-seed values are retained on model pages and in machine records. Partial groups are provisional; — means unavailable. These are the existing selected-checkpoint evaluations, not newly selected mIoU-best checkpoints. Raw/EMA settings are recorded on each model page.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 12/12 | 44.42 | 46.46 | 52.96 | 49.14 |
| [eomt_large](models/eomt_large/README.md) | 12/12 | 44.44 | 52.52 | 49.89 | 52.82 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 12/12 | 19.10 | 21.64 | 22.39 | 25.56 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 12/12 | 20.52 | 21.35 | 23.84 | 26.31 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 12/12 | 24.31 | 25.34 | 27.37 | 24.84 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 12/12 | 27.25 | 22.46 | 34.51 | 31.18 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 12/12 | 30.23 | 29.16 | 34.92 | 31.67 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 12/12 | 31.04 | 30.48 | 40.78 | 30.76 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 12/12 | 33.07 | 27.81 | 44.66 | 39.84 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 12/12 | 33.53 | 35.11 | 41.03 | 42.66 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 12/12 | 34.06 | 34.55 | 41.27 | 41.76 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 12/12 | 24.55 | 22.97 | 33.22 | 33.62 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 12/12 | 23.98 | 27.20 | 34.52 | 32.17 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 12/12 | 15.77 | 21.35 | 34.32 | 28.76 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 12/12 | 22.67 | 27.06 | 39.38 | 34.19 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 12/12 | 22.88 | 21.92 | 34.47 | 26.67 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 12/12 | 23.04 | 27.71 | 31.71 | 30.41 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 12/12 | 26.17 | 23.27 | 32.25 | 31.28 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 12/12 | 25.77 | 26.62 | 34.04 | 33.68 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 12/12 | 26.20 | 25.28 | 39.99 | 37.39 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 12/12 | 27.93 | 25.15 | 31.34 | 28.34 |
| [segformer_b0](models/segformer_b0/README.md) | 12/12 | 27.19 | 21.65 | 38.63 | 34.29 |
| [segformer_b2](models/segformer_b2/README.md) | 12/12 | 35.90 | 37.71 | 46.87 | 41.78 |
| [segformer_b5](models/segformer_b5/README.md) | 12/12 | 32.95 | 39.96 | 45.84 | 46.25 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | 12/12 | 27.81 | 22.33 | 43.35 | 33.57 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 12/12 | 24.55 | 30.57 | 45.38 | 41.08 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 12/12 | 23.20 | 29.08 | 40.40 | 32.53 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | 6/12 | 16.16 | 21.08 | 22.49 | 23.60 |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | 0/12 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | 0/12 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | 0/12 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | 0/12 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | 0/12 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | 0/12 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/12 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/12 | — | — | — | — |

## Mud-pumping

Validation **mud-pumping IoU (%)** for the same checkpoints. Precision, recall, per-class scores and examples are on each model page and in the CSV.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 12/12 | 8.47 | 11.26 | 20.64 | 8.41 |
| [eomt_large](models/eomt_large/README.md) | 12/12 | 15.55 | 8.84 | 9.26 | 14.16 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 12/12 | 10.69 | 6.84 | 4.74 | 4.19 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 12/12 | 2.52 | 3.73 | 3.72 | 5.63 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 12/12 | 13.16 | 25.28 | 10.59 | 16.71 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 12/12 | 19.83 | 7.94 | 12.62 | 11.25 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 12/12 | 9.61 | 2.02 | 10.26 | 5.59 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 12/12 | 14.19 | 3.67 | 7.43 | 11.41 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 12/12 | 5.84 | 12.50 | 2.84 | 7.27 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 12/12 | 10.66 | 0.79 | 2.19 | 2.34 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 12/12 | 13.21 | 4.07 | 1.67 | 5.78 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 12/12 | 2.63 | 7.36 | 4.12 | 2.62 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 12/12 | 1.58 | 0.48 | 1.41 | 1.24 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 12/12 | 1.80 | 0.93 | 2.97 | 0.67 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 12/12 | 0.59 | 1.14 | 0.61 | 1.11 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 12/12 | 0.58 | 1.37 | 1.55 | 6.13 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 12/12 | 0.81 | 1.38 | 1.18 | 3.87 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 12/12 | 2.16 | 3.31 | 1.89 | 1.50 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 12/12 | 1.16 | 0.93 | 0.86 | 1.72 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 12/12 | 1.41 | 0.52 | 5.98 | 2.37 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 12/12 | 3.98 | 3.07 | 2.00 | 4.56 |
| [segformer_b0](models/segformer_b0/README.md) | 12/12 | 2.53 | 3.30 | 3.93 | 6.64 |
| [segformer_b2](models/segformer_b2/README.md) | 12/12 | 9.90 | 19.42 | 7.64 | 20.66 |
| [segformer_b5](models/segformer_b5/README.md) | 12/12 | 2.79 | 4.05 | 5.60 | 5.09 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | 12/12 | 5.64 | 6.02 | 4.17 | 2.30 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 12/12 | 4.42 | 2.75 | 4.86 | 5.28 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 12/12 | 2.62 | 6.48 | 5.34 | 16.51 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | 6/12 | 5.26 | 13.10 | 12.68 | 12.27 |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | 0/12 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | 0/12 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | 0/12 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | 0/12 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | 0/12 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | 0/12 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/12 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/12 | — | — | — | — |

## Standardized model-only inference

**FPS**, mean across completed, profiled seeds. Input/evaluation settings, latency and peak VRAM are on the model pages; compare speeds only under compatible settings.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 12/12 | 38.85 | 39.78 | 38.93 | 40.99 |
| [eomt_large](models/eomt_large/README.md) | 12/12 | 45.35 | 45.61 | 45.74 | 45.46 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 12/12 | 2.54 | 2.53 | 2.54 | 2.50 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 12/12 | 171.36 | 170.70 | 170.92 | 171.92 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 12/12 | 34.70 | 34.83 | 34.62 | 34.50 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 12/12 | 84.17 | 84.56 | 83.42 | 84.09 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 12/12 | 129.26 | 126.50 | 132.88 | 134.46 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 12/12 | 42.19 | 42.33 | 43.00 | 42.68 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 12/12 | 30.11 | 29.87 | 29.77 | 30.37 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 12/12 | 29.04 | 28.97 | 29.07 | 28.88 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 12/12 | 76.10 | 76.18 | 75.46 | 75.37 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 12/12 | 147.84 | 148.58 | 142.84 | 141.53 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 12/12 | 162.00 | 170.75 | 169.72 | 165.96 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 12/12 | 226.78 | 234.35 | 241.43 | 231.42 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 12/12 | 65.24 | 64.37 | 64.23 | 64.99 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 12/12 | 220.44 | 219.42 | 214.88 | 221.69 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 12/12 | 247.52 | 246.62 | 247.28 | 239.55 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 12/12 | 218.28 | 217.43 | 219.87 | 224.25 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 12/12 | 134.08 | 132.34 | 129.69 | 136.24 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 12/12 | 48.32 | 48.03 | 47.73 | 47.54 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 12/12 | 209.60 | 198.92 | 211.98 | 205.61 |
| [segformer_b0](models/segformer_b0/README.md) | 12/12 | 128.28 | 131.22 | 132.38 | 133.34 |
| [segformer_b2](models/segformer_b2/README.md) | 12/12 | 52.68 | 52.69 | 52.43 | 52.68 |
| [segformer_b5](models/segformer_b5/README.md) | 12/12 | 26.82 | 27.08 | 26.70 | 26.49 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | 12/12 | 78.57 | 78.30 | 78.58 | 78.33 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 12/12 | 112.24 | 112.02 | 111.39 | 105.65 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 12/12 | 152.71 | 148.87 | 153.51 | 152.16 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | 6/12 | 169.12 | 176.81 | 166.57 | 175.88 |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | 0/12 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | 0/12 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | 0/12 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | 0/12 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | 0/12 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | 0/12 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/12 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/12 | — | — | — | — |

<details>
<summary>Individual runs: quality, mud precision/recall, steps and status</summary>

Click any model for all initialization paths, full class metrics, training/validation curves, VRAM, timing, config, checkpoint and software provenance. — means unavailable, never zero.

| Model | Initialization path | Seed | Status | Steps | Best step | Mud IoU (%) | Mud precision (%) | Mud recall (%) | Final mud IoU (trainer val, %) | mIoU (%) | Fixed GT-class mIoU (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | completed | 3054 | 1781 | 8.26 | 9.10 | 47.36 | 8.05 | 42.55 | 47.27 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 1 | completed | 3309 | 3309 | 8.29 | 9.59 | 37.90 | 8.31 | 47.51 | 52.79 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 2 | completed | 2800 | 1527 | 8.85 | 9.99 | 43.73 | 8.40 | 43.20 | 48.00 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3818 | 10.71 | 12.33 | 44.98 | 10.70 | 47.84 | 53.16 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 1 | completed | 3309 | 2036 | 11.60 | 13.21 | 48.82 | 11.52 | 45.54 | 50.60 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 2 | completed | 2545 | 1272 | 11.47 | 12.83 | 51.97 | 10.09 | 45.99 | 51.10 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3054 | 24.55 | 40.57 | 38.33 | 24.37 | 52.40 | 61.13 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 1 | completed | 3054 | 1781 | 19.44 | 26.80 | 41.45 | 18.38 | 52.49 | 61.24 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 2 | completed | 2290 | 1018 | 17.93 | 24.33 | 40.54 | 17.29 | 53.99 | 59.99 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 3818 | 9.51 | 11.92 | 32.01 | 9.51 | 48.10 | 53.44 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2290 | 1018 | 6.14 | 8.20 | 19.60 | 5.33 | 50.96 | 53.80 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2290 | 1018 | 9.57 | 11.10 | 41.04 | 7.70 | 48.35 | 53.72 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | completed | 2290 | 1018 | 12.60 | 14.96 | 44.36 | 11.17 | 46.14 | 51.27 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 1 | completed | 2290 | 1018 | 24.76 | 42.02 | 37.60 | 17.76 | 45.89 | 50.99 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 2 | completed | 2036 | 763 | 9.29 | 10.45 | 45.40 | 4.17 | 41.29 | 45.88 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | completed | 2545 | 2036 | 9.20 | 13.98 | 21.21 | 9.08 | 52.85 | 55.79 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 1 | completed | 3054 | 1781 | 11.56 | 17.05 | 26.43 | 9.88 | 53.29 | 56.25 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 2 | completed | 3054 | 1781 | 5.74 | 7.07 | 23.39 | 5.46 | 51.42 | 54.27 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | completed | 3309 | 2290 | 3.24 | 4.25 | 12.05 | 3.22 | 49.29 | 57.50 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 1 | completed | 2800 | 1527 | 3.61 | 5.02 | 11.33 | 3.33 | 49.83 | 58.13 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 2 | completed | 3563 | 2545 | 20.92 | 40.44 | 30.24 | 20.54 | 50.56 | 58.99 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3309 | 2036 | 18.04 | 26.91 | 35.38 | 17.60 | 56.39 | 59.52 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2290 | 1018 | 10.29 | 15.41 | 23.66 | 8.36 | 49.80 | 55.33 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2800 | 1781 | 14.14 | 20.57 | 31.14 | 13.37 | 52.27 | 55.18 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 0 | completed | 1527 | 254 | 23.83 | 29.99 | 53.71 | 1.05 | 20.08 | 22.31 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 1 | completed | 1527 | 254 | 5.32 | 32.20 | 5.99 | 0.45 | 18.24 | 20.27 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 2 | completed | 1527 | 254 | 2.91 | 19.85 | 3.30 | 0.04 | 18.98 | 20.03 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 0 | completed | 1781 | 509 | 11.38 | 14.59 | 34.12 | 2.94 | 21.51 | 23.90 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 1 | completed | 2290 | 1018 | 4.58 | 5.04 | 33.44 | 1.07 | 22.60 | 26.37 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 2 | completed | 2036 | 763 | 4.57 | 4.90 | 40.57 | 0.72 | 20.82 | 23.13 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 0 | completed | 2545 | 1272 | 4.83 | 5.34 | 33.54 | 0.82 | 25.77 | 30.06 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 1 | completed | 1527 | 254 | 4.33 | 4.70 | 35.21 | 0.04 | 21.37 | 22.55 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 2 | completed | 1781 | 509 | 5.06 | 6.13 | 22.64 | 1.12 | 20.04 | 23.38 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3054 | 1781 | 2.91 | 4.23 | 8.53 | 0.16 | 28.00 | 32.66 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2290 | 1018 | 4.63 | 4.98 | 39.42 | 3.12 | 26.82 | 29.80 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 1781 | 509 | 5.03 | 6.02 | 23.51 | 1.49 | 21.87 | 23.09 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | completed | 2290 | 1018 | 1.80 | 2.45 | 6.38 | 1.47 | 19.76 | 21.96 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 1 | completed | 3054 | 1781 | 2.55 | 3.43 | 9.02 | 0.98 | 21.82 | 24.25 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 2 | completed | 2545 | 1272 | 3.20 | 4.10 | 12.74 | 0.32 | 19.96 | 22.18 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3309 | 6.04 | 14.88 | 9.23 | 3.88 | 21.08 | 24.59 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 1 | completed | 4000 | 3563 | 2.50 | 3.04 | 12.27 | 1.72 | 21.90 | 25.55 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 2 | completed | 3309 | 2036 | 2.66 | 3.20 | 13.41 | 1.42 | 21.06 | 23.40 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 2290 | 1018 | 4.52 | 5.17 | 26.26 | 1.78 | 23.32 | 25.92 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 1 | completed | 1781 | 509 | 2.93 | 3.40 | 17.54 | 1.00 | 25.31 | 26.72 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 2 | completed | 2036 | 763 | 3.73 | 4.42 | 19.28 | 1.00 | 22.88 | 25.42 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3818 | 2545 | 5.93 | 15.18 | 8.86 | 5.31 | 27.84 | 32.47 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2290 | 1018 | 2.33 | 3.26 | 7.56 | 1.94 | 23.38 | 25.98 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 4000 | 2800 | 8.64 | 11.42 | 26.19 | 6.20 | 27.72 | 30.80 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | completed | 3818 | 2545 | 15.00 | 72.08 | 15.93 | 9.49 | 25.52 | 29.77 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 1 | completed | 4000 | 3563 | 11.25 | 22.76 | 18.20 | 10.20 | 23.95 | 27.94 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 2 | completed | 3309 | 2036 | 13.21 | 49.57 | 15.26 | 5.77 | 23.47 | 27.38 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 3309 | 2036 | 25.20 | 50.79 | 33.34 | 9.75 | 26.89 | 31.37 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 1 | completed | 2800 | 1527 | 23.18 | 37.21 | 38.08 | 13.61 | 24.31 | 28.36 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 2 | completed | 3309 | 2036 | 27.45 | 69.40 | 31.23 | 24.03 | 24.83 | 28.96 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 3563 | 2290 | 9.09 | 29.95 | 11.54 | 7.35 | 28.20 | 32.90 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 1 | completed | 4000 | 3309 | 12.35 | 38.05 | 15.45 | 8.46 | 27.46 | 32.04 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 2 | completed | 3563 | 2290 | 10.33 | 32.17 | 13.21 | 6.05 | 26.44 | 30.85 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2800 | 1527 | 16.38 | 43.63 | 20.78 | 11.87 | 25.58 | 29.84 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2800 | 1527 | 17.25 | 43.57 | 22.21 | 5.65 | 26.32 | 30.70 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2290 | 1018 | 16.50 | 48.05 | 20.08 | 10.75 | 22.63 | 26.40 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | completed | 2545 | 1272 | 26.86 | 60.28 | 32.63 | 21.68 | 28.81 | 33.61 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 1 | completed | 1781 | 1272 | 8.54 | 10.37 | 32.66 | 4.16 | 26.63 | 31.07 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 2 | completed | 3309 | 2036 | 24.08 | 54.60 | 30.12 | 16.11 | 26.32 | 30.71 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 1527 | 254 | 8.45 | 12.24 | 21.41 | 2.09 | 23.21 | 24.50 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 1 | completed | 1781 | 509 | 9.47 | 11.58 | 34.19 | 2.27 | 22.31 | 26.03 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 2 | completed | 1527 | 254 | 5.92 | 7.67 | 20.59 | 2.43 | 21.86 | 23.07 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 2290 | 1018 | 17.06 | 26.08 | 33.06 | 7.78 | 35.09 | 40.93 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 1 | completed | 1781 | 509 | 11.43 | 15.32 | 31.00 | 6.97 | 31.00 | 36.17 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 2 | completed | 2036 | 763 | 9.37 | 15.03 | 19.91 | 8.22 | 37.45 | 43.69 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2290 | 1018 | 9.39 | 21.42 | 14.33 | 2.16 | 32.89 | 38.38 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 1781 | 509 | 9.55 | 13.98 | 23.19 | 3.96 | 27.87 | 32.52 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 3309 | 2036 | 14.80 | 27.17 | 24.53 | 7.17 | 32.77 | 38.23 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | completed | 4000 | 2800 | 5.86 | 7.17 | 24.17 | 4.42 | 30.26 | 35.30 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 1 | completed | 4000 | 3309 | 10.13 | 14.58 | 24.92 | 7.08 | 30.91 | 36.07 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 2 | completed | 3818 | 2545 | 12.86 | 16.09 | 39.02 | 9.56 | 29.52 | 32.80 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | completed | 3818 | 2545 | 1.50 | 2.88 | 3.04 | 1.07 | 29.26 | 34.14 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 1 | completed | 4000 | 3563 | 1.44 | 2.76 | 2.91 | 1.42 | 28.70 | 33.48 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 2 | completed | 4000 | 3818 | 3.12 | 6.96 | 5.34 | 2.04 | 29.51 | 34.43 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3309 | 10.93 | 57.54 | 11.88 | 9.33 | 36.58 | 42.67 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 1 | completed | 3563 | 2290 | 10.63 | 45.28 | 12.20 | 8.56 | 35.67 | 41.61 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 2 | completed | 2290 | 1018 | 9.23 | 17.75 | 16.12 | 5.18 | 32.50 | 36.11 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3818 | 2545 | 4.52 | 22.01 | 5.39 | 2.00 | 35.56 | 39.51 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 3818 | 2545 | 5.97 | 65.54 | 6.16 | 5.44 | 33.72 | 39.34 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 1781 | 509 | 6.27 | 21.17 | 8.19 | 1.07 | 25.74 | 28.61 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | completed | 1527 | 254 | 19.92 | 22.13 | 66.64 | 2.62 | 31.08 | 34.54 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 1 | completed | 1781 | 509 | 10.30 | 11.25 | 54.87 | 6.92 | 33.09 | 38.61 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 2 | completed | 1527 | 254 | 12.35 | 16.15 | 34.38 | 3.43 | 28.93 | 32.15 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | completed | 2036 | 1018 | 2.79 | 3.63 | 10.78 | 2.41 | 32.13 | 37.48 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 1 | completed | 2036 | 763 | 2.90 | 3.45 | 15.39 | 0.39 | 32.70 | 36.33 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 2 | completed | 1781 | 509 | 5.33 | 10.68 | 9.63 | 2.73 | 26.60 | 29.56 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | completed | 1781 | 509 | 7.27 | 20.48 | 10.13 | 2.35 | 45.13 | 47.64 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 1 | completed | 1527 | 254 | 4.69 | 6.16 | 16.47 | 3.89 | 32.94 | 34.77 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 2 | completed | 2290 | 1018 | 10.33 | 13.43 | 30.91 | 2.39 | 44.26 | 49.17 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1527 | 254 | 4.74 | 6.56 | 14.63 | 1.67 | 30.09 | 33.43 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 1527 | 254 | 18.14 | 25.10 | 39.55 | 4.04 | 32.87 | 34.70 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 1527 | 254 | 11.36 | 15.02 | 31.78 | 1.99 | 29.31 | 32.57 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | completed | 3818 | 2545 | 8.60 | 30.10 | 10.75 | 1.07 | 35.24 | 41.11 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 1 | completed | 4000 | 2800 | 5.37 | 7.55 | 15.63 | 1.76 | 31.52 | 36.78 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 2 | completed | 2545 | 1527 | 3.54 | 6.73 | 6.96 | 0.72 | 32.45 | 37.85 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | completed | 1781 | 509 | 13.86 | 36.74 | 18.21 | 5.76 | 21.60 | 22.80 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 1 | completed | 2545 | 1272 | 16.12 | 92.85 | 16.32 | 2.39 | 32.26 | 37.64 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 2 | completed | 2290 | 1018 | 7.50 | 45.22 | 8.25 | 0.83 | 29.56 | 34.49 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | completed | 3309 | 2036 | 1.98 | 4.17 | 3.63 | 1.78 | 44.72 | 52.17 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 1 | completed | 2290 | 1018 | 2.75 | 3.40 | 12.56 | 0.71 | 45.37 | 52.93 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 2 | completed | 4000 | 3818 | 3.80 | 6.10 | 9.16 | 5.71 | 43.89 | 51.20 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1781 | 509 | 5.57 | 15.83 | 7.91 | 3.58 | 34.05 | 39.72 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2545 | 1272 | 12.57 | 41.92 | 15.22 | 2.06 | 45.48 | 48.01 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 3818 | 2545 | 3.66 | 12.22 | 4.97 | 2.25 | 39.99 | 46.66 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | completed | 4000 | 3563 | 6.32 | 8.91 | 17.83 | 6.33 | 32.81 | 38.27 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 1 | completed | 2290 | 1018 | 10.65 | 20.63 | 18.04 | 9.51 | 32.68 | 38.12 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 2 | completed | 3309 | 2036 | 15.01 | 30.64 | 22.72 | 13.87 | 35.12 | 40.97 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | completed | 2800 | 1527 | 0.88 | 1.30 | 2.64 | 0.82 | 35.02 | 40.85 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 1 | completed | 2036 | 1781 | 0.55 | 1.14 | 1.06 | 0.50 | 36.50 | 40.56 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 2 | completed | 3054 | 1781 | 0.94 | 1.42 | 2.73 | 0.89 | 33.79 | 39.43 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | completed | 2800 | 1527 | 2.44 | 13.18 | 2.91 | 2.36 | 40.63 | 47.40 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 1 | completed | 2545 | 1272 | 2.15 | 5.18 | 3.54 | 1.85 | 41.08 | 47.93 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 2 | completed | 3309 | 2036 | 1.99 | 5.73 | 2.96 | 1.88 | 41.38 | 45.97 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2800 | 1527 | 2.53 | 3.28 | 9.95 | 2.06 | 41.92 | 48.90 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2290 | 1018 | 2.24 | 3.89 | 5.02 | 1.65 | 41.69 | 48.64 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2036 | 1781 | 2.25 | 5.22 | 3.82 | 2.08 | 44.37 | 49.30 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | completed | 1527 | 254 | 14.15 | 46.83 | 16.85 | 7.73 | 26.55 | 28.02 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 1 | completed | 4000 | 3818 | 14.43 | 54.15 | 16.44 | 14.45 | 38.55 | 44.98 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 2 | completed | 4000 | 3818 | 11.06 | 42.22 | 13.03 | 11.06 | 37.08 | 43.27 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | completed | 2036 | 763 | 3.22 | 8.93 | 4.78 | 2.12 | 34.11 | 39.80 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 1 | completed | 2036 | 763 | 2.04 | 6.06 | 2.99 | 1.56 | 34.02 | 39.69 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 2 | completed | 2036 | 763 | 6.94 | 27.95 | 8.46 | 3.46 | 35.53 | 41.45 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | completed | 2290 | 1018 | 1.14 | 1.88 | 2.80 | 0.95 | 43.81 | 48.68 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 1 | completed | 1527 | 1527 | 1.79 | 3.27 | 3.80 | 1.79 | 40.15 | 46.84 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 2 | completed | 1781 | 509 | 2.09 | 2.89 | 7.08 | 1.41 | 39.85 | 44.27 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2800 | 1527 | 7.64 | 18.62 | 11.47 | 6.26 | 41.52 | 48.44 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 3054 | 3054 | 3.55 | 5.62 | 8.76 | 3.55 | 41.80 | 48.77 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2036 | 763 | 6.16 | 12.89 | 10.55 | 4.33 | 41.96 | 48.95 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | completed | 2290 | 1018 | 2.82 | 3.31 | 15.98 | 0.61 | 24.81 | 28.95 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 1 | completed | 1527 | 254 | 1.50 | 1.86 | 7.15 | 0.79 | 21.96 | 23.18 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 2 | completed | 3309 | 2036 | 3.58 | 6.09 | 8.00 | 1.76 | 26.87 | 31.35 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | completed | 1781 | 509 | 4.41 | 39.78 | 4.73 | 2.16 | 20.24 | 23.61 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 1 | completed | 2290 | 1018 | 10.82 | 18.44 | 20.75 | 5.67 | 23.55 | 27.48 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 2 | completed | 3054 | 1781 | 6.86 | 12.59 | 13.11 | 1.56 | 25.12 | 29.30 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | completed | 2036 | 763 | 2.36 | 3.79 | 5.89 | 0.65 | 30.53 | 35.62 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 1 | completed | 2800 | 1527 | 5.97 | 7.95 | 19.36 | 1.09 | 37.35 | 41.50 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 2 | completed | 2036 | 763 | 4.01 | 6.05 | 10.65 | 0.59 | 31.78 | 37.08 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1781 | 509 | 3.02 | 4.92 | 7.26 | 1.95 | 29.55 | 34.47 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2800 | 1527 | 1.87 | 2.10 | 14.76 | 0.34 | 35.71 | 41.66 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 3054 | 1781 | 2.96 | 4.00 | 10.16 | 0.41 | 35.61 | 41.55 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | completed | 1527 | 254 | 2.27 | 2.53 | 18.02 | 0.16 | 20.78 | 21.93 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 1 | completed | 2036 | 2036 | 0.47 | 0.92 | 0.97 | 0.48 | 28.45 | 33.19 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 2 | completed | 1781 | 509 | 1.99 | 2.44 | 9.66 | 0.88 | 22.70 | 25.22 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | completed | 2800 | 1527 | 0.67 | 0.78 | 4.59 | 0.66 | 26.64 | 31.08 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 1 | completed | 1781 | 1781 | 0.24 | 0.30 | 1.15 | 0.24 | 27.14 | 31.66 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 2 | completed | 2290 | 2290 | 0.52 | 0.68 | 2.18 | 0.52 | 27.81 | 32.45 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | completed | 2800 | 1527 | 1.90 | 2.16 | 13.52 | 0.37 | 36.09 | 42.11 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 1 | completed | 3309 | 2036 | 1.42 | 1.76 | 6.86 | 0.83 | 34.29 | 40.01 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 2 | completed | 2036 | 763 | 0.92 | 1.13 | 4.93 | 0.46 | 33.17 | 36.85 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2800 | 1527 | 0.99 | 1.26 | 4.45 | 0.37 | 33.73 | 39.35 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 1781 | 509 | 1.43 | 1.74 | 7.65 | 0.42 | 27.08 | 31.60 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2290 | 1018 | 1.30 | 1.91 | 3.93 | 0.23 | 35.69 | 41.63 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | completed | 1527 | 254 | 2.71 | 2.95 | 25.09 | 0.35 | 15.71 | 18.32 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 1 | completed | 1527 | 254 | 1.88 | 2.04 | 19.67 | 0.26 | 16.16 | 18.85 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 2 | completed | 1527 | 254 | 0.80 | 0.87 | 8.52 | 0.21 | 15.46 | 18.03 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | completed | 3818 | 2545 | 1.06 | 1.54 | 3.31 | 0.52 | 26.64 | 31.08 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 1 | completed | 1527 | 254 | 0.62 | 0.79 | 2.74 | 0.33 | 18.80 | 20.89 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 2 | completed | 1527 | 254 | 1.10 | 1.32 | 6.22 | 0.26 | 18.61 | 20.67 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3309 | 3.20 | 5.27 | 7.52 | 2.68 | 33.76 | 39.39 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 1 | completed | 3563 | 2545 | 4.10 | 5.55 | 13.59 | 2.14 | 35.39 | 39.33 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 2 | completed | 2800 | 1527 | 1.60 | 2.89 | 3.44 | 1.07 | 33.81 | 37.57 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1781 | 509 | 0.43 | 0.67 | 1.15 | 0.16 | 26.29 | 29.21 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 3054 | 1781 | 0.90 | 1.03 | 6.43 | 0.25 | 30.05 | 35.06 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 3054 | 1781 | 0.67 | 0.92 | 2.48 | 0.19 | 29.94 | 34.93 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | completed | 2290 | 1018 | 0.92 | 4.11 | 1.17 | 0.72 | 22.10 | 25.78 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 1 | completed | 1527 | 254 | 0.33 | 0.50 | 1.00 | 0.00 | 16.92 | 17.86 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 2 | completed | 3309 | 2036 | 0.52 | 1.16 | 0.93 | 0.18 | 28.99 | 33.82 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2800 | 0.79 | 1.86 | 1.36 | 0.50 | 32.59 | 38.02 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 1 | completed | 1527 | 254 | 2.10 | 2.82 | 7.58 | 0.34 | 23.12 | 24.40 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 2 | completed | 1527 | 509 | 0.52 | 0.57 | 5.03 | 0.09 | 25.47 | 26.88 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | completed | 2036 | 763 | 0.45 | 0.56 | 2.17 | 0.31 | 40.33 | 47.05 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 1 | completed | 1781 | 509 | 0.40 | 0.87 | 0.72 | 0.30 | 35.76 | 41.72 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 2 | completed | 2290 | 1018 | 0.97 | 1.83 | 2.03 | 0.76 | 42.05 | 49.06 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1527 | 1018 | 0.17 | 0.40 | 0.30 | 0.07 | 40.53 | 45.03 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 1781 | 509 | 1.56 | 10.47 | 1.80 | 1.11 | 34.81 | 38.68 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 1527 | 254 | 1.61 | 2.62 | 4.01 | 0.18 | 27.24 | 30.26 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | completed | 4000 | 2800 | 0.93 | 1.59 | 2.19 | 0.43 | 26.59 | 31.02 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 1 | completed | 2800 | 1527 | 0.37 | 1.01 | 0.59 | 0.08 | 22.54 | 26.30 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 2 | completed | 1781 | 509 | 0.45 | 0.50 | 4.03 | 0.17 | 19.51 | 20.60 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | completed | 2036 | 763 | 0.88 | 1.03 | 5.91 | 0.63 | 20.36 | 23.76 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 1 | completed | 2036 | 763 | 1.41 | 1.57 | 12.12 | 0.31 | 22.83 | 26.64 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 2 | completed | 2290 | 1018 | 1.83 | 2.07 | 13.56 | 0.63 | 22.58 | 26.34 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | completed | 2290 | 1018 | 0.68 | 0.90 | 2.80 | 0.35 | 31.92 | 35.47 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 1 | completed | 3818 | 2545 | 2.34 | 3.13 | 8.53 | 0.70 | 35.71 | 41.66 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 2 | completed | 2290 | 1018 | 1.63 | 1.95 | 8.98 | 0.29 | 35.79 | 41.75 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2036 | 763 | 7.49 | 9.61 | 25.36 | 4.24 | 25.75 | 30.04 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2036 | 763 | 3.13 | 3.71 | 16.74 | 0.52 | 28.59 | 33.35 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 1781 | 509 | 7.76 | 28.97 | 9.58 | 4.50 | 25.67 | 29.95 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | completed | 1527 | 1527 | 0.62 | 1.27 | 1.20 | 0.62 | 24.12 | 28.14 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 1 | completed | 2545 | 1272 | 1.30 | 2.05 | 3.45 | 0.24 | 22.92 | 26.75 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 2 | completed | 2290 | 1018 | 0.50 | 1.21 | 0.86 | 0.49 | 22.08 | 25.76 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | completed | 3818 | 2545 | 1.58 | 5.59 | 2.16 | 0.67 | 29.13 | 33.99 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 1 | completed | 3054 | 1781 | 1.86 | 2.79 | 5.26 | 0.57 | 24.33 | 28.38 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 2 | completed | 4000 | 2800 | 0.69 | 0.91 | 2.80 | 0.44 | 29.66 | 34.60 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | completed | 2800 | 1527 | 1.12 | 2.25 | 2.17 | 0.04 | 36.37 | 42.43 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 1 | completed | 3309 | 2036 | 1.72 | 2.21 | 7.14 | 0.30 | 32.08 | 37.43 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 2 | completed | 1781 | 509 | 0.70 | 0.84 | 3.85 | 0.39 | 26.67 | 31.12 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2036 | 763 | 2.61 | 3.15 | 13.22 | 1.44 | 28.61 | 33.38 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 3309 | 2036 | 4.21 | 5.34 | 16.53 | 1.93 | 31.68 | 36.96 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2290 | 1018 | 4.81 | 7.12 | 12.87 | 2.17 | 30.94 | 34.38 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | completed | 2800 | 1527 | 1.70 | 18.29 | 1.84 | 0.25 | 27.15 | 30.16 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 1 | completed | 2545 | 1272 | 2.14 | 9.66 | 2.68 | 1.00 | 24.97 | 27.74 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 2 | completed | 3563 | 2290 | 2.63 | 10.23 | 3.42 | 0.45 | 26.39 | 30.79 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | completed | 1781 | 509 | 2.15 | 2.44 | 15.30 | 0.32 | 21.17 | 24.70 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 1 | completed | 2290 | 1018 | 4.17 | 7.10 | 9.18 | 1.50 | 25.71 | 30.00 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 2 | completed | 1781 | 509 | 3.60 | 4.18 | 20.60 | 1.04 | 22.93 | 26.75 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | completed | 1781 | 509 | 2.90 | 3.64 | 12.55 | 0.13 | 32.05 | 37.39 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 1 | completed | 3818 | 2545 | 1.60 | 29.70 | 1.67 | 1.41 | 32.30 | 37.68 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 2 | completed | 1781 | 509 | 1.17 | 1.76 | 3.34 | 0.66 | 32.41 | 37.82 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1781 | 509 | 2.02 | 2.50 | 9.49 | 0.14 | 30.12 | 35.14 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2800 | 1527 | 0.95 | 2.25 | 1.60 | 0.44 | 31.39 | 36.62 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 1781 | 509 | 1.53 | 2.00 | 6.09 | 0.44 | 32.32 | 37.71 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | completed | 2036 | 763 | 0.63 | 1.00 | 1.67 | 0.18 | 24.60 | 28.70 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 1 | completed | 2290 | 1018 | 2.68 | 4.44 | 6.34 | 0.19 | 24.73 | 28.85 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 2 | completed | 1527 | 1527 | 0.17 | 0.33 | 0.35 | 0.17 | 27.98 | 32.65 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | completed | 3054 | 1781 | 1.33 | 3.57 | 2.08 | 0.18 | 27.75 | 32.38 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 1 | completed | 2800 | 1527 | 0.53 | 1.18 | 0.96 | 0.29 | 30.00 | 35.00 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 2 | completed | 1781 | 509 | 0.91 | 1.21 | 3.62 | 0.66 | 22.10 | 25.79 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | completed | 1781 | 509 | 0.47 | 0.61 | 2.03 | 0.41 | 33.56 | 39.16 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 1 | completed | 1781 | 509 | 1.19 | 1.36 | 8.61 | 0.93 | 35.54 | 41.47 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 2 | completed | 3054 | 1781 | 0.90 | 2.63 | 1.36 | 0.32 | 33.02 | 38.53 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3054 | 1781 | 1.46 | 3.24 | 2.59 | 0.71 | 32.15 | 37.51 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 1781 | 509 | 1.80 | 2.14 | 10.21 | 0.57 | 35.18 | 41.04 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 3054 | 1781 | 1.89 | 2.77 | 5.63 | 0.38 | 33.72 | 39.33 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | completed | 3563 | 2290 | 1.78 | 7.52 | 2.27 | 0.86 | 26.74 | 31.19 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 1 | completed | 2036 | 2036 | 0.36 | 0.54 | 1.07 | 0.36 | 28.82 | 33.62 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 2 | completed | 2290 | 1018 | 2.09 | 2.33 | 17.02 | 1.44 | 23.06 | 26.90 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | completed | 1781 | 509 | 0.62 | 5.21 | 0.69 | 0.14 | 21.98 | 25.65 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 1 | completed | 1527 | 1272 | 0.19 | 0.87 | 0.24 | 0.15 | 31.80 | 37.10 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 2 | completed | 1527 | 254 | 0.76 | 0.93 | 4.07 | 0.34 | 22.07 | 23.29 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | completed | 1781 | 509 | 11.10 | 82.48 | 11.37 | 0.12 | 39.49 | 46.07 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 1 | completed | 1527 | 1018 | 0.09 | 0.90 | 0.10 | 0.05 | 38.31 | 44.70 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 2 | completed | 2800 | 1527 | 6.74 | 30.84 | 7.94 | 0.62 | 42.16 | 46.84 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1781 | 509 | 2.29 | 2.94 | 9.47 | 1.21 | 36.84 | 42.97 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 2036 | 763 | 1.41 | 1.98 | 4.62 | 1.02 | 38.91 | 45.39 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2290 | 1018 | 3.41 | 43.16 | 3.57 | 0.87 | 36.42 | 42.49 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | completed | 2545 | 1272 | 3.95 | 52.87 | 4.09 | 1.22 | 29.66 | 32.95 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 1 | completed | 2290 | 1018 | 3.11 | 5.13 | 7.29 | 0.40 | 26.74 | 31.20 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 2 | completed | 3818 | 2545 | 4.90 | 70.06 | 5.00 | 3.00 | 27.40 | 31.97 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | completed | 1781 | 509 | 6.67 | 9.52 | 18.21 | 0.09 | 27.32 | 30.35 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 1 | completed | 3054 | 1781 | 0.81 | 2.64 | 1.15 | 0.40 | 26.54 | 30.96 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 2 | completed | 1527 | 254 | 1.73 | 4.08 | 2.93 | 0.01 | 21.59 | 22.79 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | completed | 2036 | 763 | 1.98 | 34.54 | 2.06 | 0.15 | 33.56 | 39.15 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 1 | completed | 1527 | 254 | 3.15 | 11.11 | 4.21 | 0.00 | 24.90 | 27.67 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 2 | completed | 2800 | 1527 | 0.86 | 95.21 | 0.86 | 0.01 | 35.56 | 41.49 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2036 | 763 | 7.19 | 41.31 | 8.01 | 2.41 | 30.37 | 35.43 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 1527 | 254 | 2.33 | 6.57 | 3.49 | 0.01 | 22.54 | 25.04 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2036 | 763 | 4.17 | 13.15 | 5.75 | 0.73 | 32.10 | 37.45 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | completed | 3309 | 2036 | 2.25 | 2.59 | 14.48 | 2.06 | 29.76 | 34.73 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 1 | completed | 2545 | 1272 | 3.46 | 4.96 | 10.25 | 1.60 | 26.10 | 30.45 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 2 | completed | 2545 | 1272 | 1.88 | 2.34 | 8.64 | 1.15 | 25.71 | 30.00 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | completed | 1527 | 254 | 2.91 | 3.98 | 9.75 | 1.25 | 18.50 | 18.50 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 1 | completed | 3309 | 2036 | 3.34 | 5.12 | 8.74 | 2.26 | 23.81 | 27.78 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 2 | completed | 2290 | 1018 | 3.67 | 5.08 | 11.68 | 1.42 | 22.65 | 25.17 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | completed | 3054 | 1781 | 3.76 | 7.84 | 6.74 | 3.07 | 37.22 | 43.43 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 1 | completed | 3818 | 2545 | 4.58 | 7.97 | 9.71 | 1.81 | 38.93 | 45.42 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 2 | completed | 4000 | 3309 | 3.44 | 6.00 | 7.47 | 2.82 | 39.73 | 46.36 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 3563 | 5.59 | 15.45 | 8.05 | 4.71 | 34.86 | 40.67 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 3818 | 2545 | 8.72 | 35.77 | 10.33 | 6.49 | 33.01 | 38.52 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 4000 | 3563 | 5.61 | 14.24 | 8.47 | 4.16 | 34.98 | 40.81 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | completed | 4000 | 3054 | 9.77 | 12.20 | 32.89 | 7.09 | 36.50 | 42.58 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 1 | completed | 4000 | 3818 | 13.12 | 18.75 | 30.41 | 11.68 | 36.44 | 42.52 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 2 | completed | 2545 | 1272 | 6.81 | 8.61 | 24.55 | 4.89 | 34.76 | 40.55 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3054 | 15.11 | 38.93 | 19.81 | 11.53 | 37.92 | 44.24 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 1 | completed | 3054 | 1781 | 20.70 | 40.36 | 29.82 | 16.72 | 37.70 | 43.99 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 2 | completed | 3818 | 2545 | 22.45 | 61.01 | 26.20 | 15.41 | 37.50 | 43.76 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3563 | 6.53 | 7.61 | 31.48 | 5.49 | 46.29 | 51.43 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 1 | completed | 3818 | 2545 | 7.58 | 10.22 | 22.73 | 4.96 | 46.50 | 51.67 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 2 | completed | 2800 | 1527 | 8.80 | 11.64 | 26.54 | 4.76 | 47.82 | 53.13 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3054 | 2036 | 17.93 | 77.10 | 18.94 | 11.06 | 42.56 | 47.29 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 3054 | 1781 | 22.53 | 46.38 | 30.46 | 15.76 | 41.06 | 47.90 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 3818 | 2545 | 21.53 | 58.55 | 25.40 | 17.49 | 41.73 | 46.36 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | completed | 2036 | 763 | 2.23 | 2.60 | 13.76 | 1.20 | 34.12 | 39.81 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 1 | completed | 1781 | 509 | 2.55 | 2.87 | 18.54 | 1.51 | 33.34 | 37.05 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 2 | completed | 1781 | 509 | 3.58 | 4.18 | 19.79 | 1.41 | 31.39 | 36.62 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3563 | 3.29 | 3.67 | 23.90 | 2.78 | 38.45 | 42.72 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 1 | completed | 4000 | 3054 | 4.12 | 4.65 | 26.70 | 3.74 | 40.51 | 42.76 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 2 | completed | 4000 | 3563 | 4.75 | 5.26 | 32.79 | 3.83 | 40.91 | 45.45 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | completed | 2545 | 1272 | 4.16 | 5.25 | 16.70 | 3.26 | 44.69 | 52.14 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 1 | completed | 3563 | 2290 | 7.14 | 10.12 | 19.54 | 6.44 | 46.85 | 54.66 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 2 | completed | 3818 | 2545 | 5.50 | 8.06 | 14.77 | 4.20 | 45.96 | 53.63 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3818 | 2545 | 4.04 | 4.50 | 27.96 | 3.10 | 47.39 | 50.03 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 4000 | 3818 | 6.55 | 7.36 | 37.32 | 6.20 | 45.95 | 51.06 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 3818 | 2545 | 4.69 | 5.38 | 26.63 | 3.92 | 45.41 | 50.46 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 0 | completed | 2290 | 1018 | 2.24 | 3.78 | 5.20 | 0.97 | 26.83 | 31.30 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 1 | completed | 2290 | 1018 | 10.22 | 48.39 | 11.47 | 3.29 | 26.25 | 30.62 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 2 | completed | 3309 | 2036 | 4.46 | 5.97 | 14.95 | 0.39 | 30.36 | 35.42 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 0 | completed | 1527 | 254 | 3.96 | 5.32 | 13.43 | 1.68 | 22.05 | 23.28 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 1 | completed | 1781 | 509 | 7.49 | 8.91 | 32.07 | 1.35 | 22.07 | 25.75 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 2 | completed | 1527 | 254 | 6.60 | 7.74 | 30.96 | 0.37 | 22.86 | 24.13 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 0 | completed | 2036 | 763 | 4.37 | 8.40 | 8.35 | 0.87 | 44.85 | 49.83 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 1 | completed | 2036 | 763 | 4.55 | 7.93 | 9.64 | 1.16 | 44.26 | 49.18 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 2 | completed | 2290 | 1018 | 3.60 | 5.75 | 8.76 | 0.71 | 40.94 | 47.76 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2545 | 1272 | 1.19 | 1.59 | 4.56 | 0.91 | 35.71 | 41.67 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 1781 | 509 | 3.46 | 5.85 | 7.80 | 0.60 | 29.63 | 34.57 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2290 | 1018 | 2.26 | 2.94 | 8.97 | 0.44 | 35.37 | 41.26 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | completed | 2036 | 763 | 7.11 | 8.64 | 28.75 | 1.08 | 24.85 | 29.00 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 1 | completed | 1527 | 254 | 2.70 | 4.43 | 6.45 | 0.35 | 23.64 | 24.96 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 2 | completed | 2290 | 1018 | 3.45 | 3.83 | 25.72 | 1.28 | 25.15 | 27.94 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | completed | 3563 | 2290 | 3.19 | 5.07 | 7.92 | 1.19 | 30.84 | 35.98 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 1 | completed | 2545 | 1272 | 1.21 | 1.79 | 3.62 | 0.54 | 29.30 | 34.18 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 2 | completed | 4000 | 2800 | 3.85 | 7.72 | 7.13 | 1.33 | 31.58 | 36.85 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | completed | 2036 | 763 | 4.15 | 5.60 | 13.82 | 1.88 | 46.87 | 52.07 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 1 | completed | 3309 | 2036 | 8.06 | 25.83 | 10.50 | 4.61 | 44.50 | 51.92 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 2 | completed | 3054 | 2800 | 2.37 | 4.10 | 5.33 | 1.37 | 44.76 | 52.23 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2290 | 1018 | 3.51 | 5.63 | 8.53 | 3.46 | 40.45 | 44.94 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 4000 | 2800 | 6.23 | 12.66 | 10.92 | 5.22 | 41.20 | 45.77 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2800 | 1527 | 6.10 | 8.85 | 16.40 | 2.64 | 41.59 | 46.21 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | completed | 2290 | 1018 | 3.80 | 10.71 | 5.56 | 0.91 | 23.77 | 27.73 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 1 | completed | 2290 | 1018 | 1.97 | 2.69 | 6.84 | 1.44 | 22.81 | 26.61 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 2 | completed | 1781 | 509 | 2.09 | 3.73 | 4.54 | 0.65 | 23.04 | 24.32 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | completed | 3054 | 1781 | 5.75 | 47.78 | 6.13 | 4.41 | 29.28 | 34.16 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 1 | completed | 3309 | 2036 | 5.03 | 28.63 | 5.75 | 1.78 | 30.53 | 33.92 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 2 | completed | 2545 | 1272 | 8.67 | 17.77 | 14.48 | 2.88 | 27.43 | 30.48 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | completed | 3309 | 2036 | 8.33 | 15.15 | 15.62 | 5.06 | 39.56 | 46.15 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 1 | completed | 2036 | 763 | 2.94 | 4.33 | 8.40 | 1.99 | 40.00 | 44.45 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 2 | completed | 2800 | 1527 | 4.76 | 14.76 | 6.56 | 2.66 | 41.63 | 48.56 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1781 | 509 | 19.83 | 59.69 | 22.89 | 12.56 | 33.66 | 35.53 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 1 | completed | 1781 | 509 | 14.06 | 24.85 | 24.46 | 10.40 | 28.29 | 31.43 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 2 | completed | 2545 | 1527 | 15.64 | 61.89 | 17.31 | 3.10 | 35.63 | 41.57 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 0 | completed | 1781 | 509 | 6.53 | 6.71 | 70.86 | 4.01 | 13.65 | 13.65 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 1 | completed | 4000 | 3309 | 3.99 | 13.52 | 5.36 | 2.14 | 18.67 | 18.67 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 2 | collecting | 4000 | 3309 | 5.00 | 6.53 | 17.64 | 4.25 | 17.12 | 17.12 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | training | 3949 | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 1 | completed | 3309 | 2036 | 13.10 | 31.37 | 18.36 | 3.16 | 21.08 | 22.25 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 2 | training | 3749 | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | completed | 2036 | 763 | 12.98 | 18.54 | 30.23 | 11.94 | 22.27 | 23.50 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 1 | training | 3249 | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 2 | completed | 2036 | 763 | 12.37 | 17.50 | 29.71 | 1.24 | 22.72 | 23.98 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2036 | 763 | 12.27 | 14.61 | 43.38 | 11.98 | 23.60 | 24.91 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 1 | training | 2549 | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 2 | training | 949 | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 0 | training | 599 | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 1 | training | 399 | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 2 | training | 299 | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | training | 254 | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 1 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 2 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 1 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 2 | queued | — | — | — | — | — | — | — | — |

</details>

## Training specification and interpretation

This campaign selects checkpoints and early-stops by **mud-pumping validation IoU**. Both overall mIoU and mud IoU above describe that same selected checkpoint. This report layout does not change the training objective or selection policy. mIoU averages classes with nonzero union; fixed GT-class means, mud precision/recall and raw/EMA diagnostics remain on model pages. Seed SD describes optimization variability, not independent-recording uncertainty.

`rtis_only` uses each recipe default pretrained initializer, which can include a segmentation checkpoint (EoMT: COCO panoptic; BEiT: ADE20K), not just backbone weights. Other paths load historical Cityscapes/RailSem19 endpoints and reset classifiers. Exact resolved settings are on model pages.

Validation approximately every 250 optimizer steps; stop after five checks without a 0.1 percentage-point mud-IoU improvement. At most 4,000 steps. Keep mud-selected and final full-state checkpoints; remove periodic snapshots only after complete verified collection.

Frozen training code: `066afb2626398b7be59d4d19f5a0e4644fd59adc`. Split SHA-256: `71fef8292610c352da0709fe3bd030f3bcc18f97560394835f4b22826463b83d`.

## Training cost

<details>
<summary>Per-run training and evaluation memory and time</summary>

| Model | Initialization | Seed | Train peak GiB (retained invocation) | Eval peak GiB | Train seconds (retained invocation) | Eval seconds |
| --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | 17.84 | 10.77 | 5250.70 | 22.22 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 1 | 17.84 | 10.77 | 5464.05 | 22.22 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 2 | 17.84 | 10.77 | 4391.45 | 22.40 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | 17.84 | 10.77 | 6852.63 | 22.03 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 1 | 17.84 | 10.77 | 5444.72 | 22.06 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 2 | 17.84 | 10.77 | 4286.28 | 21.95 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | 17.84 | 10.77 | 6810.59 | 22.63 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 1 | 17.84 | 10.77 | 5043.03 | 22.41 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 2 | 17.84 | 10.77 | 3639.72 | 22.46 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.84 | 10.77 | 6773.37 | 22.07 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 17.84 | 10.77 | 3667.14 | 22.29 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 17.84 | 10.77 | 3732.23 | 22.52 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | 17.70 | 10.80 | 3614.75 | 21.99 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 1 | 17.70 | 10.80 | 3498.95 | 21.48 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 2 | 17.70 | 10.80 | 3027.46 | 22.06 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | 17.70 | 10.80 | 3944.40 | 22.01 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 1 | 17.70 | 10.80 | 4670.64 | 21.83 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 2 | 17.70 | 10.80 | 4762.61 | 21.28 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | 17.75 | 10.80 | 5159.16 | 21.56 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 1 | 17.70 | 10.80 | 4286.24 | 22.02 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 2 | 17.70 | 10.80 | 5510.38 | 21.85 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.70 | 10.80 | 4831.95 | 21.44 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 17.70 | 10.80 | 3624.54 | 21.93 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 17.70 | 10.80 | 4382.64 | 21.08 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 0 | 15.36 | 7.39 | 3531.35 | 119.21 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 1 | 15.36 | 7.39 | 3577.49 | 118.87 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 2 | 15.36 | 7.39 | 3521.23 | 119.05 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 0 | 15.36 | 7.39 | 4086.40 | 120.45 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 1 | 15.36 | 7.39 | 5162.31 | 119.53 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 2 | 15.36 | 7.39 | 4715.68 | 120.59 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 0 | 15.36 | 7.39 | 5780.04 | 120.62 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 1 | 15.36 | 7.39 | 3511.52 | 119.70 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 2 | 15.36 | 7.39 | 4070.28 | 119.91 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 15.36 | 7.39 | 7102.43 | 121.65 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 15.36 | 7.39 | 5249.64 | 120.19 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 15.36 | 7.39 | 4158.44 | 120.66 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | 9.88 | 6.55 | 1933.41 | 10.49 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 1 | 9.88 | 6.55 | 2571.06 | 10.69 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 2 | 9.88 | 6.55 | 2151.71 | 10.64 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 9.88 | 6.55 | 3369.25 | 10.68 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 1 | 9.88 | 6.55 | 3377.77 | 10.55 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 2 | 9.88 | 6.55 | 2782.37 | 10.65 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | 9.88 | 6.55 | 1945.87 | 10.69 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 1 | 9.88 | 6.55 | 1519.42 | 10.83 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 2 | 9.88 | 6.55 | 1730.30 | 11.07 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.88 | 6.55 | 3215.71 | 11.33 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 9.88 | 6.55 | 1951.24 | 10.85 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 9.88 | 6.55 | 3383.54 | 10.53 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | 15.78 | 6.64 | 6331.26 | 16.66 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 1 | 15.78 | 6.64 | 6652.28 | 16.71 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 2 | 15.78 | 6.64 | 5500.81 | 16.38 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 15.78 | 6.64 | 5491.01 | 16.74 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 1 | 15.78 | 6.64 | 4665.78 | 16.52 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 2 | 15.78 | 6.64 | 5496.43 | 17.17 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | 15.78 | 6.64 | 5922.20 | 16.83 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 1 | 15.78 | 6.64 | 6643.32 | 16.82 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 2 | 15.78 | 6.64 | 5916.02 | 17.00 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 15.78 | 6.64 | 4667.37 | 16.83 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 15.78 | 6.64 | 4670.56 | 17.13 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 15.78 | 6.64 | 3835.60 | 17.35 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | 9.10 | 6.64 | 1970.60 | 12.07 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 1 | 9.10 | 6.64 | 1389.96 | 12.19 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 2 | 9.10 | 6.64 | 2537.49 | 12.22 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 9.10 | 6.64 | 1196.69 | 12.03 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 1 | 9.10 | 6.64 | 1390.27 | 12.06 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 2 | 9.10 | 6.64 | 1190.97 | 12.13 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | 9.10 | 6.64 | 1775.34 | 12.28 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 1 | 9.10 | 6.64 | 1385.54 | 12.29 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 2 | 9.10 | 6.64 | 1575.69 | 12.37 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.10 | 6.64 | 1771.30 | 12.15 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 9.10 | 6.64 | 1385.59 | 12.22 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 9.10 | 6.64 | 2536.38 | 12.50 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | 7.79 | 7.03 | 2430.35 | 14.31 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 1 | 7.79 | 7.03 | 2415.91 | 13.05 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 2 | 7.79 | 7.03 | 2303.44 | 13.31 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | 7.79 | 7.03 | 2281.77 | 13.44 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 1 | 7.79 | 7.03 | 2464.27 | 13.37 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 2 | 7.79 | 7.03 | 2384.46 | 13.20 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | 7.79 | 7.03 | 2423.54 | 13.20 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 1 | 7.79 | 7.03 | 2138.41 | 13.12 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 2 | 7.79 | 7.03 | 1381.76 | 13.36 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.79 | 7.03 | 2280.13 | 12.93 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 7.79 | 7.03 | 2269.78 | 12.92 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 7.79 | 7.03 | 1100.32 | 13.52 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | 11.71 | 7.52 | 2053.79 | 19.82 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 1 | 11.71 | 7.52 | 2432.38 | 20.21 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 2 | 11.71 | 7.52 | 2036.24 | 20.15 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | 11.71 | 7.52 | 2735.11 | 19.35 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 1 | 11.71 | 7.52 | 2725.56 | 19.74 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 2 | 11.71 | 7.52 | 2390.65 | 20.13 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | 11.71 | 7.52 | 2381.04 | 19.25 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 1 | 11.71 | 7.52 | 2046.73 | 19.53 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 2 | 11.71 | 7.52 | 3053.92 | 19.59 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.71 | 7.52 | 2040.39 | 19.58 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 11.71 | 7.52 | 2042.43 | 19.77 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 11.71 | 7.52 | 2027.11 | 20.01 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | 17.35 | 7.58 | 6538.43 | 19.01 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 1 | 17.35 | 7.58 | 6890.99 | 18.47 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 2 | 17.35 | 7.58 | 4369.42 | 19.10 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | 17.35 | 7.58 | 3070.83 | 19.51 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 1 | 17.35 | 7.58 | 4358.94 | 18.74 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 2 | 17.35 | 7.58 | 3925.00 | 18.97 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | 17.35 | 7.58 | 5624.71 | 18.46 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 1 | 17.35 | 7.58 | 3964.91 | 19.05 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 2 | 17.35 | 7.58 | 6777.19 | 18.82 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.35 | 7.58 | 3048.60 | 18.75 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 17.35 | 7.58 | 4357.98 | 18.32 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 17.35 | 7.58 | 6534.39 | 19.09 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | 15.81 | 8.11 | 6537.79 | 22.47 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 1 | 15.83 | 8.11 | 3722.47 | 22.31 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 2 | 15.83 | 8.11 | 5401.00 | 22.41 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | 15.80 | 8.11 | 4553.99 | 22.33 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 1 | 15.80 | 8.11 | 3361.33 | 22.05 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 2 | 15.80 | 8.11 | 4952.08 | 22.32 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | 15.80 | 8.11 | 4554.44 | 22.45 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 1 | 15.80 | 8.11 | 4143.10 | 22.03 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 2 | 15.83 | 8.11 | 5362.76 | 22.52 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 15.81 | 8.11 | 4560.18 | 22.61 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 15.81 | 8.11 | 3752.20 | 22.58 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 15.83 | 8.11 | 3333.57 | 22.07 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | 10.20 | 7.42 | 1281.48 | 15.66 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 1 | 10.20 | 7.42 | 3317.98 | 16.36 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 2 | 10.27 | 7.42 | 3298.56 | 16.45 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | 10.27 | 7.42 | 1684.52 | 15.66 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 1 | 10.20 | 7.42 | 1704.34 | 16.17 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 2 | 10.20 | 7.42 | 1683.32 | 16.30 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | 10.20 | 7.42 | 1892.01 | 16.06 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 1 | 10.20 | 7.42 | 1286.01 | 16.22 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 2 | 10.20 | 7.42 | 1480.19 | 16.35 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.20 | 7.42 | 2317.74 | 16.29 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 10.20 | 7.42 | 2545.70 | 16.95 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 10.27 | 7.42 | 1694.36 | 16.96 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | 8.31 | 6.78 | 1407.02 | 11.36 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 1 | 8.31 | 6.78 | 968.97 | 10.85 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 2 | 8.31 | 6.78 | 2033.74 | 10.59 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 8.31 | 6.78 | 1109.79 | 11.67 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 1 | 8.31 | 6.78 | 1409.42 | 11.16 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 2 | 8.31 | 6.78 | 1875.15 | 11.85 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 8.31 | 6.78 | 1260.55 | 10.92 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 1 | 8.31 | 6.78 | 1719.87 | 11.27 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 2 | 8.31 | 6.78 | 1252.28 | 11.04 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.31 | 6.78 | 1129.34 | 10.96 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 8.31 | 6.78 | 1740.12 | 11.34 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 8.31 | 6.78 | 1882.29 | 11.86 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | 7.46 | 6.82 | 947.45 | 11.02 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 1 | 7.46 | 6.82 | 1256.50 | 10.57 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 2 | 7.46 | 6.82 | 1110.72 | 10.74 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 7.46 | 6.82 | 1711.80 | 11.30 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 1 | 7.46 | 6.82 | 1106.43 | 11.25 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 2 | 7.46 | 6.82 | 1420.56 | 10.97 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 7.46 | 6.82 | 1734.62 | 11.35 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 1 | 7.47 | 6.82 | 2057.50 | 10.66 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 2 | 7.46 | 6.82 | 1264.31 | 11.02 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.46 | 6.82 | 1710.81 | 11.24 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 7.46 | 6.82 | 1130.46 | 10.99 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 7.46 | 6.82 | 1416.12 | 11.58 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | 6.72 | 6.51 | 952.89 | 10.51 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 1 | 6.72 | 6.51 | 981.75 | 10.36 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 2 | 6.72 | 6.51 | 950.54 | 10.41 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | 6.72 | 6.51 | 2331.62 | 10.10 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 1 | 6.72 | 6.51 | 947.72 | 10.18 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 2 | 6.72 | 6.51 | 974.97 | 11.05 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | 6.72 | 6.51 | 2378.15 | 9.96 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 1 | 6.72 | 6.51 | 2146.64 | 9.75 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 2 | 6.72 | 6.51 | 1693.42 | 10.13 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 6.72 | 6.51 | 1092.77 | 10.82 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 6.72 | 6.51 | 1850.44 | 9.96 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 6.72 | 6.51 | 1864.32 | 9.92 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | 10.87 | 7.54 | 2123.81 | 15.33 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 1 | 10.94 | 7.54 | 1434.09 | 14.98 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 2 | 10.93 | 7.54 | 3051.66 | 15.59 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | 10.87 | 7.54 | 3652.82 | 15.21 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 1 | 10.87 | 7.54 | 1429.74 | 14.93 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 2 | 10.87 | 7.54 | 1429.46 | 15.18 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | 10.87 | 7.54 | 1887.03 | 15.72 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 1 | 10.87 | 7.54 | 1657.35 | 15.29 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 2 | 10.87 | 7.54 | 2139.05 | 15.89 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.93 | 7.54 | 1440.63 | 15.12 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 10.93 | 7.54 | 1659.67 | 15.20 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 10.93 | 7.54 | 1419.53 | 14.83 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | 7.34 | 7.04 | 2373.32 | 10.76 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 1 | 7.34 | 7.04 | 1678.95 | 11.76 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 2 | 7.34 | 7.04 | 1100.41 | 11.08 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | 7.34 | 7.04 | 1239.40 | 11.05 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 1 | 7.34 | 7.04 | 1229.53 | 11.14 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 2 | 7.34 | 7.04 | 1398.13 | 10.89 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | 7.34 | 7.04 | 1393.13 | 11.71 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 1 | 7.34 | 7.04 | 2300.26 | 11.41 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 2 | 7.34 | 7.04 | 1398.02 | 11.15 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.34 | 7.04 | 1246.89 | 10.77 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 7.34 | 7.04 | 1246.83 | 10.92 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 7.34 | 7.04 | 1092.71 | 11.17 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | 7.76 | 6.87 | 965.01 | 11.88 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 1 | 7.75 | 6.87 | 1552.11 | 11.87 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 2 | 7.76 | 6.87 | 1407.46 | 11.89 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | 7.75 | 6.87 | 2363.96 | 11.76 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 1 | 7.76 | 6.87 | 1886.30 | 12.21 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 2 | 7.76 | 6.87 | 2479.27 | 11.48 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | 7.76 | 6.87 | 1715.88 | 11.92 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 1 | 7.76 | 6.87 | 1999.53 | 11.77 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 2 | 7.76 | 6.87 | 1105.87 | 12.04 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.76 | 6.87 | 1257.29 | 11.37 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 7.76 | 6.87 | 2009.96 | 12.38 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 7.76 | 6.87 | 1436.73 | 12.07 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | 8.27 | 6.75 | 2197.23 | 10.70 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 1 | 8.27 | 6.75 | 1982.04 | 10.39 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 2 | 8.27 | 6.75 | 2767.10 | 10.45 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | 8.27 | 6.75 | 1390.00 | 10.55 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 1 | 8.27 | 6.75 | 1786.99 | 10.61 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 2 | 8.27 | 6.75 | 1391.01 | 10.19 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | 8.27 | 6.75 | 1392.43 | 10.56 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 1 | 8.28 | 6.75 | 2950.14 | 10.49 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 2 | 8.27 | 6.75 | 1387.47 | 10.47 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.27 | 6.75 | 1397.19 | 10.51 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 8.27 | 6.75 | 2158.99 | 10.40 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 8.27 | 6.75 | 1394.77 | 10.81 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | 9.36 | 7.25 | 1331.45 | 11.93 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 1 | 9.36 | 7.25 | 1491.10 | 12.16 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 2 | 9.36 | 7.25 | 1002.02 | 12.02 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 9.36 | 7.25 | 1969.65 | 11.84 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 1 | 9.35 | 7.25 | 1798.77 | 11.47 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 2 | 9.36 | 7.25 | 1157.80 | 11.28 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 9.36 | 7.25 | 1169.20 | 12.06 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 1 | 9.36 | 7.25 | 1156.56 | 11.80 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 2 | 9.36 | 7.25 | 1958.32 | 11.43 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.36 | 7.25 | 1982.51 | 12.16 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 9.36 | 7.25 | 1165.34 | 11.65 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 9.36 | 7.25 | 1971.52 | 12.44 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | 11.64 | 7.02 | 4540.04 | 17.29 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 1 | 11.64 | 7.02 | 2611.72 | 16.75 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 2 | 11.64 | 7.02 | 2924.25 | 17.07 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | 11.64 | 7.02 | 2302.70 | 16.93 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 1 | 11.64 | 7.02 | 1970.94 | 16.96 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 2 | 11.64 | 7.02 | 1955.07 | 16.74 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | 11.64 | 7.02 | 2295.24 | 16.91 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 1 | 11.64 | 7.02 | 1966.99 | 17.13 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 2 | 11.64 | 7.02 | 3556.86 | 17.36 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.64 | 7.02 | 2289.87 | 17.34 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 11.64 | 7.02 | 2602.89 | 17.11 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 11.64 | 7.02 | 2917.68 | 16.98 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | 8.29 | 6.75 | 2025.59 | 10.36 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 1 | 8.29 | 6.75 | 1813.85 | 11.00 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 2 | 8.29 | 6.75 | 2983.11 | 10.71 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | 8.29 | 6.75 | 1418.13 | 10.39 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 1 | 8.29 | 6.75 | 2423.51 | 11.10 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 2 | 8.29 | 6.75 | 1215.15 | 10.24 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | 8.29 | 6.75 | 1610.56 | 11.28 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 1 | 8.29 | 6.75 | 1221.19 | 11.10 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 2 | 8.29 | 6.75 | 2192.81 | 10.74 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.29 | 6.75 | 1630.09 | 11.42 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 8.29 | 6.75 | 1214.65 | 10.80 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 8.29 | 6.75 | 1624.91 | 11.24 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | 7.79 | 7.03 | 1978.41 | 13.35 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 1 | 7.79 | 7.03 | 1554.18 | 13.06 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 2 | 7.79 | 7.03 | 1540.85 | 13.66 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | 7.79 | 7.03 | 923.21 | 13.01 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 1 | 7.79 | 7.03 | 1961.81 | 13.43 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 2 | 7.79 | 7.03 | 1402.25 | 13.19 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | 7.79 | 7.03 | 1818.24 | 13.32 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 1 | 7.79 | 7.03 | 2289.50 | 13.29 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 2 | 7.79 | 7.03 | 2410.16 | 13.16 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.79 | 7.03 | 2403.36 | 12.82 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 7.79 | 7.03 | 2269.32 | 13.09 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 7.79 | 7.03 | 2397.55 | 13.18 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | 11.73 | 7.46 | 3888.61 | 22.65 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 1 | 11.73 | 7.46 | 3863.35 | 22.22 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 2 | 11.73 | 7.46 | 2475.63 | 22.82 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | 11.73 | 7.46 | 3845.90 | 22.12 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 1 | 11.73 | 7.46 | 2923.51 | 22.22 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 2 | 11.73 | 7.46 | 3685.61 | 22.26 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | 11.73 | 7.46 | 3876.30 | 22.19 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 1 | 11.73 | 7.46 | 3703.65 | 22.71 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 2 | 11.73 | 7.46 | 2690.23 | 22.25 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.73 | 7.46 | 2949.09 | 23.13 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 11.73 | 7.46 | 2957.35 | 22.33 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 11.73 | 7.46 | 3663.09 | 22.24 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | 16.31 | 7.78 | 3335.58 | 29.50 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 1 | 16.31 | 7.78 | 2870.46 | 29.16 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 2 | 16.31 | 7.78 | 2854.54 | 29.18 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | 16.31 | 7.78 | 6356.10 | 28.75 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 1 | 16.31 | 7.78 | 6455.55 | 29.30 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 2 | 16.31 | 7.78 | 6438.35 | 29.32 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | 16.31 | 7.78 | 4111.77 | 30.07 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 1 | 16.31 | 7.78 | 5785.28 | 29.09 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 2 | 16.31 | 7.78 | 6178.75 | 29.74 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 16.31 | 7.78 | 6129.20 | 29.19 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 16.31 | 7.78 | 6523.98 | 29.38 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 16.31 | 7.78 | 6069.40 | 29.21 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 0 | 10.76 | 6.97 | 2958.52 | 11.93 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 1 | 10.76 | 6.97 | 2972.43 | 12.03 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 2 | 10.77 | 6.97 | 4239.28 | 12.20 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 0 | 10.76 | 6.97 | 1979.35 | 12.10 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 1 | 10.76 | 6.97 | 2306.78 | 12.31 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 2 | 10.76 | 6.97 | 1982.79 | 12.08 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 0 | 10.76 | 6.97 | 2632.69 | 12.43 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 1 | 10.77 | 6.97 | 2646.23 | 12.36 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 2 | 10.77 | 6.97 | 2972.74 | 12.09 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.76 | 6.97 | 3278.65 | 12.25 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 10.76 | 6.97 | 2307.35 | 12.49 |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 10.77 | 6.97 | 2977.50 | 13.04 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | 10.08 | 7.19 | 1500.57 | 11.36 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 1 | 10.08 | 7.19 | 1125.56 | 11.97 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 2 | 10.08 | 7.19 | 1704.73 | 11.80 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | 10.08 | 7.19 | 2564.21 | 12.04 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 1 | 10.08 | 7.19 | 1867.33 | 11.68 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 2 | 10.08 | 7.19 | 2886.31 | 11.78 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | 10.08 | 7.19 | 1489.44 | 11.60 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 1 | 10.08 | 7.19 | 2386.06 | 12.09 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 2 | 10.08 | 7.19 | 2226.37 | 11.46 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.08 | 7.19 | 1668.62 | 11.83 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 10.08 | 7.19 | 2918.13 | 12.39 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 10.08 | 7.19 | 2007.88 | 12.17 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | 8.69 | 7.01 | 1414.59 | 11.71 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 1 | 8.69 | 7.01 | 1453.15 | 11.98 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 2 | 8.69 | 7.01 | 1126.98 | 12.01 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | 8.69 | 7.01 | 1905.71 | 11.69 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 1 | 8.69 | 7.01 | 2077.87 | 12.11 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 2 | 8.69 | 7.01 | 1570.76 | 11.69 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | 8.69 | 7.01 | 2050.80 | 12.51 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 1 | 8.69 | 7.01 | 1308.63 | 11.62 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 2 | 8.69 | 7.01 | 1730.41 | 12.19 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.69 | 7.01 | 1115.84 | 11.74 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 1 | 8.69 | 7.01 | 1136.05 | 11.89 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 2 | 8.69 | 7.01 | 1598.53 | 12.29 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 0 | 8.04 | 6.12 | 1112.29 | 10.46 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 1 | 8.04 | 6.12 | 2430.15 | 9.65 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 2 | 8.04 | 6.12 | 2470.40 | 9.68 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 1 | 8.04 | 6.12 | 2035.11 | 10.13 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 2 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | 8.04 | 6.12 | 1278.97 | 9.93 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 1 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 2 | 8.04 | 6.12 | 1260.50 | 9.95 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.04 | 6.12 | 1271.61 | 10.64 |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 1 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 2 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 1 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 2 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 1 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 2 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 1 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 2 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 1 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 2 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 1 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 2 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 1 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 2 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 1 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 2 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 1 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 2 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 1 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 2 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 1 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 2 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 1 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 2 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 1 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 2 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 1 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 2 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 1 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 2 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 1 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 2 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 1 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 2 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 1 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 2 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 1 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 2 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 1 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 2 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 1 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 2 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 1 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 2 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 1 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 2 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 1 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 2 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 1 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 2 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 1 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 2 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 1 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 2 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 1 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 2 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 1 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 2 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 1 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 2 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 1 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 2 | — | — | — | — |

</details>

Resumed invocation resource measurements are not cumulative training cost. Standardized FPS/latency and parameter memory are separate profiling evidence; missing evidence is explicit on each model page. The report publisher does not modify frozen training jobs or historical Cityscapes/RailSem19 reports.

[Preserved original aggregate-selected pilot](https://github.com/arianizadi/segmentary/blob/aeb4157a66487fe1b2271c01a0ad9383c51b958b/docs/results/paul-test-rtis/live/README.md)
