# RAD 9/24: Scene-grouped split (`fixed-grouped`)

Every model and starting point trained on the scene-grouped split (labels: re-rendered from the polygon JSONs; split: scene-grouped (from v1/v2)). Every model on this page was trained by us. The tables keep the shared RTIS report's names: an *initialization path* is the starting point (pretraining before training on these images): `rtis_only` = recipe pretrained weights, `cityscapes_to_rtis` = Cityscapes, `railsem19_to_rtis` = RailSem19, `cityscapes_to_railsem19_to_rtis` = Cityscapes → RailSem19. The Quality, Mud-pumping and [Per-class IoU](#per-class-iou) tables count each class only on the validation images that contain it and score the final checkpoint after the full training budget (no early stopping, so nothing is selected on the validation images); the per-run table, `results.csv` and the model pages also keep the campaign's own pixel-pooled numbers of the checkpoint that scored best on validation, kept as secondary evidence. The [study page](../README.md) compares the splits.

**20/149 completed · 0 failed**

Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling.

[RAD 9/24 study](../README.md) · [CSV results](results.csv) · [Full machine records](status.json)

41 models; four initialization paths; seeds [0]. Train/val/test: 217/37/60 images. Test is held out. Split grouping status: `provisional_until_recording_provenance_confirmed`. Seed variation does not establish independent-recording generalization.

## Quality

Validation **mIoU (%)**: each class's IoU averaged over the validation images that contain it, then over the classes present. Cells show the mean over completed seeds; — means unavailable. Raw/EMA settings are recorded on each model page.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [bisenetv1_r18](models/bisenetv1_r18/README.md) | 1/1 | 28.89 | — | — | — |
| [bisenetv2](models/bisenetv2/README.md) | 1/1 | 19.26 | — | — | — |
| [denseaspp121](models/denseaspp121/README.md) | 1/1 | 37.53 | — | — | — |
| [denseaspp161](models/denseaspp161/README.md) | 1/1 | 36.09 | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 48.87 | 51.26 | 55.60 | 52.26 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 52.80 | 52.81 | 50.72 | 55.75 |
| [espnet](models/espnet/README.md) | 1/1 | 18.77 | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 3/4 | 25.72 | 29.04 | 29.98 | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 25.07 | 25.33 | 29.71 | 30.12 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 0/4 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 0/4 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | 0/4 | — | — | — | — |
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

Validation **mud-pumping IoU (%)** for the same checkpoints, averaged over the validation images with mud-pumping (images without it are not counted). Precision, recall and examples are on each model page.

All images with mud (n=18):

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [bisenetv1_r18](models/bisenetv1_r18/README.md) | 1/1 | 7.70 | — | — | — |
| [bisenetv2](models/bisenetv2/README.md) | 1/1 | 3.91 | — | — | — |
| [denseaspp121](models/denseaspp121/README.md) | 1/1 | 9.85 | — | — | — |
| [denseaspp161](models/denseaspp161/README.md) | 1/1 | 3.02 | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 37.58 | 39.48 | 28.04 | 16.14 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 30.03 | 25.73 | 8.62 | 31.43 |
| [espnet](models/espnet/README.md) | 1/1 | 3.88 | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 3/4 | 1.67 | 0.15 | 3.78 | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 0.54 | 6.24 | 9.20 | 11.72 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 0/4 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 0/4 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | 0/4 | — | — | — | — |
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

Train-camera images with mud (n=17):

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [bisenetv1_r18](models/bisenetv1_r18/README.md) | 1/1 | 7.84 | — | — | — |
| [bisenetv2](models/bisenetv2/README.md) | 1/1 | 3.96 | — | — | — |
| [denseaspp121](models/denseaspp121/README.md) | 1/1 | 10.14 | — | — | — |
| [denseaspp161](models/denseaspp161/README.md) | 1/1 | 3.09 | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 39.66 | 41.67 | 29.17 | 16.87 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 31.60 | 27.07 | 9.00 | 32.89 |
| [espnet](models/espnet/README.md) | 1/1 | 4.10 | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 3/4 | 1.74 | 0.10 | 3.80 | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 0.50 | 6.46 | 9.70 | 12.31 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 0/4 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 0/4 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | 0/4 | — | — | — | — |
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

## Per-class IoU

Validation IoU (%) of every class, each averaged only over the validation images that contain the class (n = those images); — = no image contains it. mIoU averages the classes with at least one such image.

| Model | Initialization path | Seed | mIoU (each class over images that contain it) | person (n=0) | truck (n=0) | rail-track (n=37) | vegetation-overgrowth (n=13) | car (n=3) | on-rails (n=0) | traffic-sign (n=9) | road (n=11) | sidewalk (n=12) | construction (n=12) | tram-track (n=2) | pole (n=21) | traffic-light (n=3) | mud-pumping (n=18) | fence (n=7) | terrain (n=35) | sky (n=28) | rail-embedded (n=3) | rail-raised (n=37) | trackbed (n=37) | standing-water (n=9) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [bisenetv1_r18](models/bisenetv1_r18/README.md) | rtis_only | 0 | 28.89 | — | — | 52.15 | 21.34 | 0.00 | — | 2.69 | 2.31 | 8.41 | 25.49 | 7.49 | 51.12 | 34.53 | 7.70 | 10.71 | 80.20 | 89.87 | 1.64 | 68.61 | 55.22 | 0.50 |
| [bisenetv2](models/bisenetv2/README.md) | rtis_only | 0 | 19.26 | — | — | 31.99 | 12.74 | 0.00 | — | 0.00 | 3.36 | 2.92 | 5.36 | 0.00 | 41.47 | 0.00 | 3.91 | 0.97 | 62.17 | 88.66 | 0.01 | 54.20 | 38.75 | 0.22 |
| [denseaspp121](models/denseaspp121/README.md) | rtis_only | 0 | 37.53 | — | — | 57.50 | 33.20 | 25.31 | — | 20.95 | 10.20 | 10.67 | 34.23 | 19.05 | 63.77 | 34.99 | 9.85 | 29.52 | 83.46 | 94.47 | 10.89 | 69.36 | 62.24 | 5.89 |
| [denseaspp161](models/denseaspp161/README.md) | rtis_only | 0 | 36.09 | — | — | 56.80 | 29.13 | 19.06 | — | 30.76 | 6.33 | 13.11 | 46.78 | 19.17 | 67.44 | 29.41 | 3.02 | 11.06 | 82.33 | 94.22 | 4.34 | 71.90 | 63.35 | 1.52 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | 48.87 | — | — | 67.38 | 26.31 | 34.15 | — | 26.91 | 11.56 | 23.85 | 37.10 | 38.63 | 70.80 | 46.48 | 37.58 | 40.71 | 87.55 | 96.81 | 20.93 | 78.19 | 74.68 | 59.99 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | 51.26 | — | — | 68.00 | 34.68 | 63.79 | — | 34.64 | 14.86 | 24.68 | 59.48 | 21.57 | 73.54 | 51.76 | 39.48 | 44.22 | 88.10 | 96.93 | 24.11 | 76.75 | 73.31 | 32.76 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | 55.60 | — | — | 77.32 | 46.23 | 51.41 | — | 38.13 | 19.85 | 48.16 | 57.32 | 43.68 | 72.68 | 44.89 | 28.04 | 45.87 | 89.11 | 97.23 | 48.50 | 77.93 | 77.53 | 36.97 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 52.26 | — | — | 64.87 | 33.72 | 64.17 | — | 35.76 | 14.19 | 32.55 | 58.67 | 37.89 | 74.07 | 48.92 | 16.14 | 44.84 | 87.58 | 97.12 | 33.46 | 77.16 | 75.91 | 43.70 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | 52.80 | — | — | 67.61 | 39.81 | 30.64 | — | 38.07 | 13.67 | 53.65 | 49.50 | 35.38 | 72.76 | 46.65 | 30.03 | 48.02 | 89.93 | 96.84 | 36.84 | 77.25 | 75.85 | 47.89 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | 52.81 | — | — | 65.52 | 43.20 | 62.90 | — | 39.34 | 13.37 | 41.63 | 55.21 | 25.77 | 73.76 | 59.89 | 25.73 | 55.10 | 88.48 | 97.06 | 13.49 | 75.65 | 75.21 | 39.23 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | 50.72 | — | — | 69.14 | 44.56 | 34.39 | — | 40.40 | 16.53 | 48.41 | 57.10 | 50.27 | 72.94 | 46.04 | 8.62 | 48.18 | 89.28 | 96.93 | 49.75 | 76.55 | 61.81 | 2.08 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 55.75 | — | — | 70.70 | 41.64 | 53.93 | — | 41.04 | 15.51 | 46.23 | 54.12 | 46.17 | 74.25 | 58.09 | 31.43 | 53.78 | 88.21 | 97.15 | 43.89 | 76.61 | 74.69 | 36.01 |
| [espnet](models/espnet/README.md) | rtis_only | 0 | 18.77 | — | — | 44.31 | 4.79 | 0.00 | — | 0.00 | 0.01 | 0.41 | 7.01 | 0.00 | 32.13 | 0.00 | 3.88 | 0.00 | 68.29 | 79.01 | 0.00 | 51.03 | 44.87 | 2.10 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 0 | 25.72 | — | — | 16.42 | 22.41 | 9.12 | — | 15.96 | 5.04 | 11.70 | 25.31 | 0.00 | 48.22 | 31.22 | 1.67 | 0.73 | 82.23 | 95.88 | 0.00 | 33.90 | 46.84 | 16.25 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 0 | 29.04 | — | — | 16.59 | 21.57 | 30.21 | — | 25.41 | 8.00 | 17.86 | 30.62 | 0.00 | 55.16 | 47.81 | 0.15 | 2.48 | 80.73 | 96.90 | 0.70 | 31.29 | 46.16 | 11.13 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 0 | 29.98 | — | — | 36.00 | 26.98 | 21.27 | — | 22.95 | 7.37 | 12.01 | 30.40 | 0.00 | 64.57 | 31.81 | 3.78 | 10.60 | 78.76 | 96.55 | 0.00 | 51.31 | 44.05 | 1.22 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | 25.07 | — | — | 51.61 | 18.27 | 0.00 | — | 0.00 | 7.77 | 7.73 | 21.01 | 0.46 | 48.65 | 0.00 | 0.54 | 7.03 | 74.78 | 90.29 | 0.00 | 67.21 | 55.63 | 0.28 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 25.33 | — | — | 42.73 | 5.46 | 0.00 | — | 3.33 | 6.92 | 1.81 | 20.24 | 0.00 | 56.89 | 2.85 | 6.24 | 22.49 | 77.13 | 89.24 | 0.00 | 66.67 | 53.54 | 0.49 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | 29.71 | — | — | 52.55 | 11.26 | 0.76 | — | 15.68 | 10.91 | 5.89 | 30.82 | 0.02 | 60.40 | 24.62 | 9.20 | 10.20 | 78.87 | 88.46 | 1.08 | 71.36 | 62.73 | 0.07 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 30.12 | — | — | 51.05 | 11.16 | 1.91 | — | 17.71 | 13.08 | 3.82 | 34.54 | 0.62 | 54.23 | 25.22 | 11.72 | 24.53 | 79.33 | 84.37 | 0.00 | 68.72 | 60.08 | 0.12 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |

## Standardized model-only inference

**FPS**, mean across completed, profiled seeds. Input/evaluation settings, latency and peak VRAM are on the model pages; compare speeds only under compatible settings.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [bisenetv1_r18](models/bisenetv1_r18/README.md) | 1/1 | 346.83 | — | — | — |
| [bisenetv2](models/bisenetv2/README.md) | 1/1 | 258.17 | — | — | — |
| [denseaspp121](models/denseaspp121/README.md) | 1/1 | 99.90 | — | — | — |
| [denseaspp161](models/denseaspp161/README.md) | 1/1 | 34.62 | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 40.84 | 41.25 | 41.09 | 41.23 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 45.67 | 45.56 | 45.61 | 45.38 |
| [espnet](models/espnet/README.md) | 1/1 | 189.30 | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 3/4 | 2.54 | 2.54 | 2.53 | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 174.47 | 174.54 | 169.45 | 173.50 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 0/4 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 0/4 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | 0/4 | — | — | — | — |
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

| Model | Initialization path | Seed | Status | Steps | Best step | Best-checkpoint mud IoU, pixels pooled (%) | Best-checkpoint mud precision, pixels pooled (%) | Best-checkpoint mud recall, pixels pooled (%) | Final mud IoU (trainer val, pixels pooled, %) | Best-checkpoint mIoU, pixels pooled (%) | Best-checkpoint fixed GT-class mIoU, pixels pooled (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [bisenetv1_r18](models/bisenetv1_r18/README.md) | rtis_only | 0 | completed | 4000 | 1037 | 8.43 | 14.18 | 17.21 | 3.39 | 17.25 | 20.13 |
| [bisenetv2](models/bisenetv2/README.md) | rtis_only | 0 | completed | 4000 | 3370 | 4.16 | 12.71 | 5.83 | 3.25 | 16.38 | 18.20 |
| [denseaspp121](models/denseaspp121/README.md) | rtis_only | 0 | completed | 4000 | 1296 | 7.80 | 9.42 | 31.21 | 5.57 | 30.96 | 36.12 |
| [denseaspp161](models/denseaspp161/README.md) | rtis_only | 0 | completed | 4000 | 1296 | 6.00 | 22.68 | 7.55 | 1.21 | 30.86 | 36.00 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | completed | 4000 | 3888 | 8.43 | 9.43 | 44.17 | 8.46 | 46.18 | 51.31 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2074 | 10.62 | 12.02 | 47.69 | 10.53 | 46.86 | 52.07 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3629 | 25.48 | 51.10 | 33.69 | 25.39 | 51.48 | 60.06 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2592 | 5.77 | 7.49 | 20.08 | 5.51 | 49.53 | 55.04 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | completed | 4000 | 1555 | 12.74 | 16.08 | 38.07 | 10.56 | 49.11 | 54.57 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3111 | 8.99 | 11.69 | 28.06 | 9.02 | 50.77 | 56.41 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 777 | 3.23 | 4.38 | 10.92 | 2.52 | 49.68 | 57.96 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 777 | 17.11 | 23.44 | 38.78 | 15.13 | 55.31 | 58.38 |
| [espnet](models/espnet/README.md) | rtis_only | 0 | completed | 4000 | 259 | 4.41 | 4.87 | 31.67 | 2.43 | 9.27 | 10.82 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 0 | completed | 4000 | 259 | 13.74 | 15.90 | 50.23 | 0.45 | 21.16 | 22.33 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1296 | 4.39 | 4.84 | 32.31 | 0.19 | 26.11 | 30.47 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 259 | 6.61 | 7.31 | 40.86 | 1.99 | 23.34 | 24.64 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | collecting | 4000 | 259 | 2.01 | 2.36 | 12.11 | 0.15 | 21.68 | 22.88 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | completed | 4000 | 2592 | 2.36 | 4.62 | 4.59 | 0.41 | 21.16 | 23.51 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2592 | 5.94 | 8.52 | 16.38 | 4.58 | 20.98 | 24.48 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 2333 | 6.45 | 7.93 | 25.65 | 3.47 | 26.04 | 28.93 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2851 | 7.15 | 10.38 | 18.69 | 5.22 | 28.13 | 31.25 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | training | 3699 | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | training | 3399 | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | training | 3249 | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | training | 1749 | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | training | 1799 | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | training | 1649 | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | training | 399 | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
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

This campaign reports the **final checkpoint** after the full step budget, with no early stopping: the Quality, Mud-pumping and per-class tables above describe it, counting each class only on the images that contain it, so nothing is selected on the validation images. The checkpoint that scored best on the **mud-pumping validation IoU** (pixels pooled over all validation images) is kept as secondary evidence and is what the per-run table shows. Pooled mIoU there averages classes with nonzero union; fixed GT-class means, mud precision/recall and raw/EMA diagnostics remain on model pages. Seed SD describes optimization variability, not independent-recording uncertainty.

`rtis_only` uses each recipe default pretrained initializer, which can include a segmentation checkpoint (EoMT: COCO panoptic; BEiT: ADE20K), not just backbone weights. Other paths load historical Cityscapes/RailSem19 endpoints and reset classifiers. Exact resolved settings are on model pages.

Validation approximately every 250 optimizer steps, only to keep the best-on-validation checkpoint as secondary evidence; no early stopping: every job trains the full 4,000 steps. Keep mud-selected and final full-state checkpoints; remove periodic snapshots only after complete verified collection.

Frozen training code: `fce0ea0ac50b334d4252812c396e0e593def375d`. Split SHA-256: `12d7b367c72cda61d57686ff2ac28223530d0af49debd9fb7a0fbc68b908bc93`.

## Training cost

<details>
<summary>Per-run training and evaluation memory and time</summary>

| Model | Initialization | Seed | Train peak GiB (retained invocation) | Eval peak GiB | Train seconds (retained invocation) | Eval seconds |
| --- | --- | --- | --- | --- | --- | --- |
| [bisenetv1_r18](models/bisenetv1_r18/README.md) | rtis_only | 0 | 7.52 | 6.62 | 2508.98 | 9.40 |
| [bisenetv2](models/bisenetv2/README.md) | rtis_only | 0 | 8.70 | 6.62 | 3523.29 | 9.31 |
| [denseaspp121](models/denseaspp121/README.md) | rtis_only | 0 | 12.88 | 6.64 | 3409.40 | 10.97 |
| [denseaspp161](models/denseaspp161/README.md) | rtis_only | 0 | 23.73 | 8.07 | 8223.21 | 16.54 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | 17.84 | 10.77 | 7155.23 | 22.34 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | 17.84 | 10.77 | 6615.36 | 22.41 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | 17.84 | 10.77 | 6978.57 | 22.56 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.84 | 10.77 | 6305.81 | 22.50 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | 17.70 | 10.80 | 5919.03 | 21.66 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | 17.70 | 10.80 | 6380.66 | 21.31 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | 17.70 | 10.80 | 5970.17 | 21.01 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.70 | 10.80 | 5665.24 | 21.84 |
| [espnet](models/espnet/README.md) | rtis_only | 0 | 6.77 | 6.23 | 2354.02 | 9.00 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 0 | 15.36 | 7.39 | 9065.11 | 119.96 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 0 | 15.36 | 7.39 | 8991.76 | 119.14 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 0 | 15.36 | 7.39 | 8983.49 | 118.71 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 15.36 | 7.39 | 8924.00 | 119.62 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | 9.88 | 6.55 | 3302.57 | 10.23 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 9.88 | 6.55 | 3321.84 | 10.20 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | 9.88 | 6.55 | 3291.69 | 10.05 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.88 | 6.55 | 3308.12 | 10.56 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
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
