# RTIS v2: disputed CVAT import removed

**88/144 completed · 0 failed**

Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling.

[V2 dataset and experiment](../../../guides/paul-test-rtis-v2.md) · [CSV results](results.csv) · [Full machine records](status.json)

36 models; four initialization paths; seeds [0]. Train/val/test: 205/37/50 images. Test is held out. Validation groups are provisional and lack person, truck and on-rails ground truth. Seed variation does not establish independent-recording generalization.

[V1 versus V2: paired seed-0 comparison](comparison.md) · [Comparison CSV](comparison.csv)

## Quality

Validation **mIoU (%)** across classes. Cells show the mean over completed seeds. Per-seed values are retained on model pages and in machine records. Partial groups are provisional; — means unavailable. These are the existing selected-checkpoint evaluations, not newly selected mIoU-best checkpoints. Raw/EMA settings are recorded on each model page.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 45.86 | 47.87 | 50.92 | 48.24 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 46.33 | 50.22 | 49.21 | 56.12 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 4/4 | 26.88 | 18.11 | 21.94 | 20.52 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 22.30 | 21.16 | 23.03 | 27.72 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 4/4 | 23.87 | 26.12 | 25.52 | 26.03 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 4/4 | 26.19 | 31.48 | 36.36 | 26.58 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 4/4 | 30.28 | 28.28 | 34.63 | 33.68 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 4/4 | 33.29 | 31.31 | 33.56 | 31.63 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 32.22 | 36.83 | 46.11 | 44.11 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 4/4 | 33.88 | 35.64 | 41.41 | 41.87 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 38.02 | 29.99 | 42.50 | 41.92 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 4/4 | 26.83 | 23.80 | 35.31 | 35.47 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 4/4 | 25.78 | 23.40 | 35.69 | 33.14 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 4/4 | 15.89 | 24.88 | 33.07 | 27.81 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 4/4 | 29.63 | 29.48 | 41.68 | 38.18 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 4/4 | 21.56 | 20.83 | 37.68 | 31.66 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 4/4 | 24.88 | 29.66 | 35.34 | 32.02 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 4/4 | 28.81 | 22.91 | 33.90 | 31.03 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 4/4 | 21.35 | 26.48 | 36.69 | 33.69 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 4/4 | 28.97 | 18.30 | 39.77 | 37.65 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 4/4 | 27.52 | 28.75 | 32.81 | 29.36 |
| [segformer_b0](models/segformer_b0/README.md) | 4/4 | 33.13 | 17.88 | 36.07 | 31.23 |
| [segformer_b2](models/segformer_b2/README.md) | 0/4 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 0/4 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | 0/4 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | 0/4 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/4 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/4 | — | — | — | — |

## Mud-pumping

Validation **mud-pumping IoU (%)** for the same checkpoints. Precision, recall, per-class scores and examples are on each model page and in the CSV.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 10.91 | 11.74 | 21.03 | 9.14 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 10.56 | 9.23 | 2.88 | 18.16 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 4/4 | 2.52 | 6.27 | 7.09 | 3.06 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 4.11 | 7.57 | 4.57 | 3.61 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 4/4 | 10.45 | 28.92 | 11.18 | 21.93 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 4/4 | 11.95 | 7.13 | 23.30 | 8.98 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 4/4 | 7.68 | 1.86 | 9.05 | 4.57 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 4/4 | 12.42 | 6.48 | 15.17 | 16.27 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 5.54 | 11.45 | 1.44 | 6.42 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 4/4 | 7.77 | 1.56 | 3.22 | 2.18 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 17.29 | 5.54 | 2.14 | 8.33 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 4/4 | 5.76 | 14.15 | 3.45 | 5.73 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 4/4 | 3.31 | 0.61 | 2.22 | 3.15 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 4/4 | 2.13 | 1.49 | 1.74 | 1.38 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 4/4 | 1.70 | 1.04 | 0.49 | 0.58 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 4/4 | 1.17 | 0.84 | 1.16 | 11.19 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 4/4 | 1.34 | 2.47 | 1.24 | 3.78 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 4/4 | 4.32 | 1.24 | 2.67 | 1.73 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 4/4 | 1.79 | 0.44 | 0.51 | 1.95 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 4/4 | 2.84 | 0.79 | 3.46 | 2.53 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 4/4 | 2.19 | 3.00 | 2.33 | 1.78 |
| [segformer_b0](models/segformer_b0/README.md) | 4/4 | 5.72 | 2.20 | 5.20 | 8.01 |
| [segformer_b2](models/segformer_b2/README.md) | 0/4 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 0/4 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | 0/4 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | 0/4 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/4 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/4 | — | — | — | — |

## Standardized model-only inference

**FPS**, mean across completed, profiled seeds. Input/evaluation settings, latency and peak VRAM are on the model pages; compare speeds only under compatible settings.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 36.27 | 38.02 | 41.10 | 41.10 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 45.40 | 45.33 | 45.20 | 45.89 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 4/4 | 2.51 | 2.51 | 2.52 | 2.53 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 172.56 | 174.94 | 167.09 | 174.36 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 4/4 | 34.61 | 34.36 | 34.69 | 34.77 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 4/4 | 82.81 | 83.13 | 84.72 | 84.99 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 4/4 | 133.61 | 131.49 | 136.32 | 136.72 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 4/4 | 42.26 | 41.61 | 42.13 | 42.58 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 29.47 | 28.42 | 30.24 | 29.50 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 4/4 | 29.18 | 29.00 | 29.01 | 28.84 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 75.75 | 76.53 | 76.01 | 76.42 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 4/4 | 148.01 | 130.27 | 140.18 | 144.89 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 4/4 | 165.56 | 166.87 | 163.53 | 170.47 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 4/4 | 230.01 | 224.03 | 231.29 | 232.27 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 4/4 | 63.91 | 62.40 | 66.96 | 63.26 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 4/4 | 222.60 | 227.13 | 221.50 | 222.15 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 4/4 | 254.74 | 247.91 | 256.95 | 248.86 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 4/4 | 226.25 | 215.85 | 214.95 | 222.24 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 4/4 | 134.40 | 133.82 | 139.20 | 138.67 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 4/4 | 46.87 | 47.44 | 47.91 | 48.08 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 4/4 | 211.12 | 212.54 | 215.04 | 199.37 |
| [segformer_b0](models/segformer_b0/README.md) | 4/4 | 129.99 | 127.72 | 131.42 | 132.33 |
| [segformer_b2](models/segformer_b2/README.md) | 0/4 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 0/4 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | 0/4 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | 0/4 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/4 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/4 | — | — | — | — |

<details>
<summary>Individual runs: quality, mud precision/recall, steps and status</summary>

Click any model for all initialization paths, full class metrics, training/validation curves, VRAM, timing, config, checkpoint and software provenance. — means unavailable, never zero.

| Model | Initialization path | Seed | Status | Steps | Best step | Mud IoU (%) | Mud precision (%) | Mud recall (%) | Final mud IoU (trainer val, %) | mIoU (%) | Fixed GT-class mIoU (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | completed | 4000 | 3823 | 10.91 | 12.37 | 48.09 | 10.95 | 45.86 | 50.95 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | completed | 3313 | 2294 | 11.74 | 13.33 | 49.65 | 11.46 | 47.87 | 53.19 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3823 | 21.03 | 29.51 | 42.26 | 21.16 | 50.92 | 59.41 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2803 | 2803 | 9.14 | 11.20 | 33.28 | 9.15 | 48.24 | 53.60 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | completed | 2294 | 1019 | 10.56 | 12.31 | 42.66 | 8.86 | 46.33 | 51.47 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | completed | 2803 | 1529 | 9.23 | 13.88 | 21.57 | 7.40 | 50.22 | 55.80 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | completed | 3568 | 3568 | 2.88 | 3.48 | 14.30 | 2.88 | 49.21 | 57.42 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3313 | 2294 | 18.16 | 26.08 | 37.42 | 18.16 | 56.12 | 59.23 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 0 | completed | 3823 | 2549 | 2.52 | 3.43 | 8.68 | 1.62 | 26.88 | 29.86 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 0 | completed | 1529 | 254 | 6.27 | 6.59 | 55.96 | 1.72 | 18.11 | 19.12 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 0 | completed | 1784 | 509 | 7.09 | 7.72 | 46.52 | 1.31 | 21.94 | 25.60 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1529 | 254 | 3.06 | 3.47 | 20.47 | 1.14 | 20.52 | 21.66 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | completed | 4000 | 3568 | 4.11 | 5.93 | 11.81 | 3.61 | 22.30 | 26.02 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3313 | 7.57 | 12.79 | 15.64 | 6.21 | 21.16 | 24.68 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 2803 | 1529 | 4.57 | 5.51 | 21.09 | 3.79 | 23.03 | 26.87 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3823 | 2549 | 3.61 | 4.53 | 15.15 | 3.16 | 27.72 | 30.80 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | completed | 4000 | 3823 | 10.45 | 21.81 | 16.71 | 9.49 | 23.87 | 27.84 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 2803 | 1529 | 28.92 | 55.34 | 37.73 | 12.48 | 26.12 | 30.47 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 2803 | 1529 | 11.18 | 23.69 | 17.47 | 5.62 | 25.52 | 29.77 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2803 | 1529 | 21.93 | 47.05 | 29.12 | 7.09 | 26.03 | 30.37 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | completed | 2039 | 764 | 11.95 | 28.67 | 17.00 | 2.72 | 26.19 | 30.56 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 3313 | 2039 | 7.13 | 8.41 | 31.95 | 5.02 | 31.48 | 36.73 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 2803 | 23.30 | 45.16 | 32.49 | 12.72 | 36.36 | 42.42 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1784 | 509 | 8.98 | 11.56 | 28.74 | 3.85 | 26.58 | 31.01 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | completed | 4000 | 3058 | 7.68 | 8.74 | 38.86 | 5.84 | 30.28 | 35.33 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | completed | 3568 | 2294 | 1.86 | 3.56 | 3.74 | 1.43 | 28.28 | 32.99 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | completed | 2803 | 1529 | 9.05 | 25.88 | 12.22 | 8.80 | 34.63 | 40.40 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2803 | 4.57 | 14.17 | 6.32 | 3.50 | 33.68 | 39.29 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | completed | 2549 | 1274 | 12.42 | 15.76 | 37.01 | 2.61 | 33.29 | 38.84 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | completed | 2294 | 1019 | 6.48 | 7.63 | 30.16 | 3.14 | 31.31 | 36.53 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | completed | 1529 | 254 | 15.17 | 44.92 | 18.63 | 3.38 | 33.56 | 35.43 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1529 | 254 | 16.27 | 25.79 | 30.59 | 2.02 | 31.63 | 35.14 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | completed | 2039 | 764 | 5.54 | 7.28 | 18.79 | 4.79 | 32.22 | 37.59 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | completed | 2803 | 1529 | 11.45 | 59.18 | 12.43 | 2.14 | 36.83 | 40.92 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | completed | 2294 | 1019 | 1.44 | 2.19 | 4.08 | 0.50 | 46.11 | 53.80 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3058 | 1784 | 6.42 | 60.98 | 6.70 | 2.13 | 44.11 | 49.01 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | completed | 2294 | 1019 | 7.77 | 13.18 | 15.90 | 7.22 | 33.88 | 39.53 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | completed | 2803 | 1784 | 1.56 | 3.12 | 3.04 | 1.51 | 35.64 | 41.58 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | completed | 2803 | 1529 | 3.22 | 9.61 | 4.61 | 2.94 | 41.41 | 48.31 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2549 | 1274 | 2.18 | 2.86 | 8.35 | 1.95 | 41.87 | 48.85 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | completed | 2803 | 1529 | 17.29 | 64.29 | 19.13 | 13.76 | 38.02 | 44.36 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | completed | 1784 | 509 | 5.54 | 16.60 | 7.67 | 2.71 | 29.99 | 34.98 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | completed | 2039 | 764 | 2.14 | 3.51 | 5.23 | 1.96 | 42.50 | 49.58 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2039 | 764 | 8.33 | 19.84 | 12.56 | 7.61 | 41.92 | 48.90 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | completed | 3568 | 2294 | 5.76 | 11.93 | 10.01 | 1.54 | 26.83 | 31.30 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | completed | 2549 | 1274 | 14.15 | 18.96 | 35.83 | 1.36 | 23.80 | 27.76 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | completed | 2803 | 1529 | 3.45 | 4.43 | 13.50 | 0.37 | 35.31 | 39.23 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3568 | 2294 | 5.73 | 8.33 | 15.50 | 0.84 | 35.47 | 41.38 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | completed | 2039 | 764 | 3.31 | 4.90 | 9.23 | 0.29 | 25.78 | 30.08 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | completed | 2039 | 764 | 0.61 | 0.93 | 1.78 | 0.14 | 23.40 | 27.30 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | completed | 2039 | 764 | 2.22 | 3.48 | 5.80 | 0.85 | 35.69 | 39.65 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2039 | 764 | 3.15 | 8.36 | 4.82 | 0.49 | 33.14 | 38.67 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | completed | 1529 | 254 | 2.13 | 2.34 | 18.81 | 0.50 | 15.89 | 18.54 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | completed | 2549 | 1274 | 1.49 | 3.25 | 2.67 | 1.24 | 24.88 | 29.02 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | completed | 2549 | 1274 | 1.74 | 2.08 | 9.70 | 0.78 | 33.07 | 38.58 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2549 | 1274 | 1.38 | 1.88 | 4.91 | 0.42 | 27.81 | 32.45 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | completed | 3313 | 2039 | 1.70 | 2.49 | 5.12 | 0.97 | 29.63 | 34.57 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | completed | 2294 | 1019 | 1.04 | 1.50 | 3.33 | 0.47 | 29.48 | 32.76 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | completed | 1784 | 509 | 0.49 | 0.72 | 1.52 | 0.21 | 41.68 | 48.63 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2803 | 1529 | 0.58 | 0.93 | 1.51 | 0.20 | 38.18 | 42.43 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | completed | 2549 | 1274 | 1.17 | 1.30 | 10.32 | 0.16 | 21.56 | 25.15 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | completed | 1784 | 509 | 0.84 | 0.96 | 6.35 | 0.18 | 20.83 | 24.30 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | completed | 2294 | 1019 | 1.16 | 1.48 | 5.02 | 0.12 | 37.68 | 41.86 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2294 | 1019 | 11.19 | 63.62 | 11.95 | 4.10 | 31.66 | 36.94 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | completed | 2549 | 1274 | 1.34 | 1.60 | 7.63 | 0.10 | 24.88 | 29.03 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3313 | 2.47 | 6.54 | 3.82 | 1.20 | 29.66 | 34.60 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | completed | 3823 | 2549 | 1.24 | 1.69 | 4.47 | 0.54 | 35.34 | 41.23 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2549 | 1274 | 3.78 | 5.12 | 12.70 | 1.46 | 32.02 | 37.36 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | completed | 2803 | 1529 | 4.32 | 69.27 | 4.40 | 2.50 | 28.81 | 33.61 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | completed | 1784 | 509 | 1.24 | 1.40 | 9.75 | 0.88 | 22.91 | 26.72 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | completed | 3058 | 1784 | 2.67 | 12.36 | 3.30 | 1.38 | 33.90 | 39.55 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3058 | 1784 | 1.73 | 3.80 | 3.08 | 0.65 | 31.03 | 36.20 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | completed | 2039 | 764 | 1.79 | 3.88 | 3.20 | 0.82 | 21.35 | 24.91 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | completed | 1529 | 1274 | 0.44 | 0.71 | 1.15 | 0.03 | 26.48 | 30.90 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | completed | 2294 | 1019 | 0.51 | 1.07 | 0.96 | 0.20 | 36.69 | 42.81 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2294 | 1019 | 1.95 | 3.23 | 4.67 | 0.69 | 33.69 | 39.30 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | completed | 3058 | 1784 | 2.84 | 5.82 | 5.27 | 0.81 | 28.97 | 33.79 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | completed | 1529 | 254 | 0.79 | 2.16 | 1.23 | 0.05 | 18.30 | 18.30 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | completed | 2549 | 1274 | 3.46 | 15.54 | 4.26 | 1.02 | 39.77 | 46.40 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2294 | 1019 | 2.53 | 6.66 | 3.93 | 2.29 | 37.65 | 43.93 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | completed | 2294 | 1019 | 2.19 | 37.66 | 2.27 | 0.42 | 27.52 | 30.57 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | completed | 2294 | 1019 | 3.00 | 11.03 | 3.96 | 0.14 | 28.75 | 31.94 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | completed | 2803 | 1529 | 2.33 | 24.69 | 2.51 | 0.32 | 32.81 | 38.28 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2294 | 1019 | 1.78 | 11.65 | 2.06 | 0.43 | 29.36 | 34.25 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | completed | 3823 | 2549 | 5.72 | 7.24 | 21.38 | 3.02 | 33.13 | 38.66 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | completed | 1529 | 254 | 2.20 | 3.35 | 6.05 | 1.04 | 17.88 | 17.88 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | completed | 2549 | 1274 | 5.20 | 8.70 | 11.44 | 2.81 | 36.07 | 42.08 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3058 | 1784 | 8.01 | 22.32 | 11.12 | 6.93 | 31.23 | 36.43 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | training | 3058 | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | training | 2999 | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | training | 2649 | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | training | 2349 | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | training | 1199 | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | training | 1149 | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | training | 1049 | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | training | 899 | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 0 | training | 1099 | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 0 | training | 799 | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |

</details>

## Training specification and interpretation

This campaign selects checkpoints and early-stops by **mud-pumping validation IoU**. Both overall mIoU and mud IoU above describe that same selected checkpoint. This report layout does not change the training objective or selection policy. mIoU averages classes with nonzero union; fixed GT-class means, mud precision/recall and raw/EMA diagnostics remain on model pages. Seed SD describes optimization variability, not independent-recording uncertainty.

`rtis_only` uses each recipe default pretrained initializer, which can include a segmentation checkpoint (EoMT: COCO panoptic; BEiT: ADE20K), not just backbone weights. Other paths load historical Cityscapes/RailSem19 endpoints and reset classifiers. Exact resolved settings are on model pages.

Validation approximately every 250 optimizer steps; stop after five checks without a 0.1 percentage-point mud-IoU improvement. At most 4,000 steps. Keep mud-selected and final full-state checkpoints; remove periodic snapshots only after complete verified collection.

Frozen training code: `066afb2626398b7be59d4d19f5a0e4644fd59adc`. Split SHA-256: `18a84c0163a65ded46508bcc904c374e5f33ad8a09b8879e3c8add606e86aa9f`.

## Training cost

<details>
<summary>Per-run training and evaluation memory and time</summary>

| Model | Initialization | Seed | Train peak GiB (retained invocation) | Eval peak GiB | Train seconds (retained invocation) | Eval seconds |
| --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | 17.84 | 10.77 | 6474.24 | 22.78 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | 17.84 | 10.78 | 5475.59 | 21.95 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | 17.84 | 10.77 | 6429.36 | 22.62 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.84 | 10.77 | 4692.51 | 22.39 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | 17.70 | 10.80 | 3701.92 | 22.04 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | 17.70 | 10.80 | 4368.38 | 21.65 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | 17.69 | 10.80 | 5548.05 | 21.42 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.70 | 10.80 | 5046.25 | 21.34 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 0 | 15.36 | 7.39 | 9008.13 | 120.18 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 0 | 15.36 | 7.39 | 3629.22 | 120.44 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 0 | 15.36 | 7.39 | 4069.09 | 119.63 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 15.36 | 7.39 | 3603.95 | 120.33 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | 9.88 | 6.55 | 3380.15 | 10.82 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 9.88 | 6.55 | 3342.46 | 10.37 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | 9.88 | 6.55 | 2362.02 | 10.59 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.88 | 6.55 | 3214.53 | 10.24 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | 15.78 | 6.64 | 6677.85 | 16.66 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 15.78 | 6.64 | 4676.72 | 17.15 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | 15.78 | 6.64 | 4682.39 | 16.97 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 15.78 | 6.64 | 4694.43 | 17.35 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | 9.10 | 6.64 | 1582.13 | 12.10 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 9.10 | 6.64 | 2542.77 | 12.31 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | 9.10 | 6.64 | 3070.50 | 12.23 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.10 | 6.64 | 1378.07 | 12.37 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | 7.80 | 7.03 | 2455.29 | 12.73 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | 7.79 | 7.03 | 2134.95 | 12.89 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | 7.79 | 7.03 | 1680.63 | 13.20 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.79 | 7.03 | 2393.58 | 13.34 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | 11.71 | 7.52 | 3417.98 | 19.79 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | 11.71 | 7.52 | 3088.79 | 19.63 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | 11.71 | 7.52 | 2031.90 | 19.70 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.71 | 7.52 | 2043.39 | 19.88 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | 17.35 | 7.58 | 3506.37 | 18.86 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | 17.35 | 7.58 | 4787.87 | 19.67 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | 17.35 | 7.58 | 3983.87 | 18.91 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.35 | 7.58 | 5262.86 | 18.90 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | 15.80 | 8.11 | 3725.91 | 22.25 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | 15.80 | 8.11 | 4575.64 | 22.86 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | 15.81 | 8.11 | 4562.23 | 22.85 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 15.83 | 8.11 | 4164.58 | 22.93 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | 10.20 | 7.42 | 2339.68 | 16.70 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | 10.20 | 7.42 | 1477.61 | 15.93 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | 10.20 | 7.42 | 1691.98 | 16.64 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.27 | 7.42 | 1691.20 | 16.41 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | 8.31 | 6.78 | 2208.77 | 11.64 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 8.31 | 6.78 | 1555.05 | 11.37 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 8.31 | 6.78 | 1738.81 | 11.64 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.31 | 6.78 | 2192.83 | 11.51 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | 7.46 | 6.82 | 1269.76 | 10.67 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 7.46 | 6.82 | 1294.35 | 11.42 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 7.46 | 6.82 | 1284.42 | 11.52 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.46 | 6.82 | 1278.34 | 10.83 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | 6.72 | 6.51 | 961.77 | 10.10 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | 6.72 | 6.51 | 1581.23 | 10.86 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | 6.72 | 6.51 | 1576.52 | 10.22 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 6.72 | 6.51 | 1589.70 | 10.56 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | 10.94 | 7.54 | 3050.82 | 15.39 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | 10.87 | 7.54 | 2131.40 | 15.57 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | 10.94 | 7.54 | 1685.50 | 15.80 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.87 | 7.54 | 2586.89 | 15.08 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | 7.34 | 7.04 | 1542.96 | 11.02 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | 7.34 | 7.04 | 1095.01 | 11.49 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | 7.34 | 7.04 | 1391.66 | 11.11 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.34 | 7.04 | 1398.96 | 11.65 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | 7.76 | 6.87 | 1582.60 | 11.48 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | 7.76 | 6.87 | 2439.26 | 12.65 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | 7.76 | 6.87 | 2373.95 | 11.47 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.76 | 6.87 | 1594.29 | 11.69 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | 8.27 | 6.75 | 2172.91 | 10.41 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | 8.27 | 6.75 | 1393.41 | 11.21 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | 8.27 | 6.75 | 2391.92 | 10.32 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.27 | 6.75 | 2388.11 | 10.56 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | 9.36 | 7.25 | 1337.83 | 12.13 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 9.36 | 7.25 | 1017.77 | 11.70 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 9.36 | 7.25 | 1499.81 | 12.45 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.36 | 7.25 | 1492.37 | 11.67 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | 11.64 | 7.02 | 3902.33 | 16.89 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | 11.64 | 7.02 | 1968.06 | 17.76 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | 11.64 | 7.02 | 3238.18 | 17.19 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.64 | 7.02 | 2933.48 | 16.97 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | 8.29 | 6.75 | 1812.63 | 10.33 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | 8.29 | 6.75 | 1829.82 | 10.53 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | 8.29 | 6.75 | 2228.79 | 10.47 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.29 | 6.75 | 1827.40 | 10.89 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | 7.79 | 7.03 | 2295.25 | 12.92 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | 7.79 | 7.03 | 949.91 | 13.73 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | 7.79 | 7.03 | 1553.57 | 13.58 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.79 | 7.03 | 1808.67 | 13.03 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |

</details>

Resumed invocation resource measurements are not cumulative training cost. Standardized FPS/latency and parameter memory are separate profiling evidence; missing evidence is explicit on each model page. The report publisher does not modify frozen training jobs or historical Cityscapes/RailSem19 reports.
