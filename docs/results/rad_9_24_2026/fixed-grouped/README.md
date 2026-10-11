# RAD 9/24: Scene-grouped split (`fixed-grouped`)

Every model and starting point trained on the scene-grouped split (labels: re-rendered from the polygon JSONs; split: scene-grouped (from v1/v2)). Every model on this page was trained by us. The tables keep the shared RTIS report's names: an *initialization path* is the starting point (pretraining before training on these images): `rtis_only` = recipe pretrained weights, `cityscapes_to_rtis` = Cityscapes, `railsem19_to_rtis` = RailSem19, `cityscapes_to_railsem19_to_rtis` = Cityscapes → RailSem19. The Quality, Mud-pumping and [Per-class IoU](#per-class-iou) tables count each class only on the validation images that contain it and score the final checkpoint after the full training budget (no early stopping, so nothing is selected on the validation images); the per-run table, `results.csv` and the model pages also keep the campaign's own pixel-pooled numbers of the checkpoint that scored best on validation, kept as secondary evidence. The [study page](../README.md) compares the splits.

**92/149 completed · 0 failed**

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
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 4/4 | 25.72 | 29.04 | 29.98 | 30.71 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 25.07 | 25.33 | 29.71 | 30.12 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 4/4 | 27.61 | 31.19 | 33.35 | 32.31 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 4/4 | 31.46 | 33.08 | 37.85 | 35.32 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 4/4 | 34.04 | 31.45 | 40.46 | 36.52 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 4/4 | 37.78 | 34.89 | 43.28 | 39.81 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 38.36 | 35.48 | 44.06 | 40.91 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 4/4 | 39.68 | 38.74 | 46.75 | 43.59 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 40.76 | 38.95 | 43.26 | 44.14 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 4/4 | 31.01 | 32.80 | 36.73 | 35.68 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 4/4 | 31.26 | 33.28 | 39.60 | 35.58 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 4/4 | 29.41 | 29.52 | 34.44 | 32.10 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 4/4 | 35.95 | 35.21 | 43.45 | 41.01 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 4/4 | 32.07 | 30.55 | 38.69 | 36.63 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 4/4 | 30.19 | 31.96 | 37.07 | 34.77 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 4/4 | 31.00 | 30.52 | 34.31 | 32.39 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 4/4 | 33.50 | 34.47 | 38.62 | 37.83 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 4/4 | 34.09 | 36.77 | 42.48 | 41.57 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 4/4 | 30.26 | 30.45 | 34.52 | 33.68 |
| [segformer_b0](models/segformer_b0/README.md) | 3/4 | 34.32 | 31.09 | 41.38 | — |
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
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 4/4 | 1.67 | 0.15 | 3.78 | 0.05 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 0.54 | 6.24 | 9.20 | 11.72 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 4/4 | 5.88 | 16.36 | 15.34 | 10.15 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 4/4 | 5.85 | 18.03 | 28.03 | 26.78 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 4/4 | 17.26 | 2.42 | 8.79 | 4.10 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 4/4 | 11.52 | 1.95 | 2.12 | 8.77 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 1.09 | 5.30 | 3.81 | 4.89 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 4/4 | 12.70 | 1.45 | 3.05 | 9.03 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 8.76 | 2.40 | 2.63 | 9.52 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 4/4 | 0.14 | 1.47 | 1.16 | 3.84 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 4/4 | 1.54 | 1.55 | 1.80 | 0.31 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 4/4 | 0.60 | 2.34 | 9.02 | 1.16 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 4/4 | 1.98 | 0.20 | 0.17 | 0.09 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 4/4 | 0.43 | 0.26 | 0.35 | 2.38 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 4/4 | 0.01 | 1.07 | 1.33 | 4.60 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 4/4 | 0.49 | 0.90 | 2.92 | 0.55 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 4/4 | 0.89 | 0.22 | 0.36 | 0.45 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 4/4 | 1.77 | 1.03 | 0.45 | 3.85 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 4/4 | 2.57 | 0.06 | 0.21 | 0.79 |
| [segformer_b0](models/segformer_b0/README.md) | 3/4 | 6.56 | 4.09 | 8.49 | — |
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
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 4/4 | 1.74 | 0.10 | 3.80 | 0.00 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 0.50 | 6.46 | 9.70 | 12.31 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 4/4 | 6.23 | 17.32 | 16.24 | 10.65 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 4/4 | 6.10 | 19.03 | 29.59 | 28.27 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 4/4 | 18.14 | 2.31 | 9.08 | 4.30 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 4/4 | 12.03 | 1.95 | 2.10 | 9.13 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 1.01 | 3.83 | 3.98 | 4.91 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 4/4 | 13.42 | 1.35 | 2.98 | 9.48 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 8.64 | 2.00 | 2.60 | 9.49 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 4/4 | 0.14 | 1.51 | 1.20 | 4.03 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 4/4 | 1.44 | 1.58 | 1.81 | 0.33 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 4/4 | 0.46 | 2.36 | 9.48 | 1.18 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 4/4 | 0.31 | 0.09 | 0.10 | 0.03 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 4/4 | 0.06 | 0.18 | 0.35 | 2.51 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 4/4 | 0.00 | 0.75 | 1.20 | 4.80 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 4/4 | 0.51 | 0.88 | 3.06 | 0.52 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 4/4 | 0.69 | 0.17 | 0.36 | 0.34 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 4/4 | 0.06 | 0.30 | 0.47 | 2.60 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 4/4 | 2.35 | 0.07 | 0.22 | 0.09 |
| [segformer_b0](models/segformer_b0/README.md) | 3/4 | 6.81 | 4.25 | 8.88 | — |
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
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 30.71 | — | — | 20.93 | 21.23 | 25.05 | — | 34.86 | 10.26 | 15.58 | 29.24 | 0.00 | 57.63 | 46.12 | 0.05 | 7.95 | 80.12 | 96.36 | 0.00 | 36.37 | 46.60 | 24.37 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | 25.07 | — | — | 51.61 | 18.27 | 0.00 | — | 0.00 | 7.77 | 7.73 | 21.01 | 0.46 | 48.65 | 0.00 | 0.54 | 7.03 | 74.78 | 90.29 | 0.00 | 67.21 | 55.63 | 0.28 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 25.33 | — | — | 42.73 | 5.46 | 0.00 | — | 3.33 | 6.92 | 1.81 | 20.24 | 0.00 | 56.89 | 2.85 | 6.24 | 22.49 | 77.13 | 89.24 | 0.00 | 66.67 | 53.54 | 0.49 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | 29.71 | — | — | 52.55 | 11.26 | 0.76 | — | 15.68 | 10.91 | 5.89 | 30.82 | 0.02 | 60.40 | 24.62 | 9.20 | 10.20 | 78.87 | 88.46 | 1.08 | 71.36 | 62.73 | 0.07 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 30.12 | — | — | 51.05 | 11.16 | 1.91 | — | 17.71 | 13.08 | 3.82 | 34.54 | 0.62 | 54.23 | 25.22 | 11.72 | 24.53 | 79.33 | 84.37 | 0.00 | 68.72 | 60.08 | 0.12 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | 27.61 | — | — | 49.98 | 18.21 | 2.32 | — | 0.33 | 7.77 | 6.92 | 33.62 | 0.00 | 50.37 | 21.31 | 5.88 | 5.61 | 77.63 | 94.89 | 0.00 | 63.03 | 58.62 | 0.52 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 31.19 | — | — | 52.02 | 25.96 | 22.81 | — | 9.15 | 6.50 | 5.83 | 31.82 | 0.00 | 54.24 | 31.38 | 16.36 | 9.31 | 80.91 | 94.44 | 0.00 | 67.49 | 52.56 | 0.69 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | 33.35 | — | — | 55.71 | 12.24 | 9.84 | — | 18.62 | 6.57 | 15.05 | 44.98 | 16.29 | 56.14 | 23.96 | 15.34 | 13.20 | 83.32 | 96.51 | 2.84 | 66.81 | 62.66 | 0.27 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 32.31 | — | — | 53.98 | 21.89 | 16.95 | — | 16.04 | 9.74 | 8.51 | 43.51 | 0.00 | 54.00 | 31.05 | 10.15 | 13.53 | 80.48 | 95.85 | 2.25 | 69.03 | 53.99 | 0.55 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | 31.46 | — | — | 55.25 | 36.69 | 18.79 | — | 9.79 | 5.08 | 7.92 | 30.50 | 0.00 | 55.98 | 24.66 | 5.85 | 12.77 | 78.43 | 95.36 | 3.50 | 65.85 | 55.94 | 3.85 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 33.08 | — | — | 50.76 | 12.13 | 29.12 | — | 21.62 | 11.61 | 9.78 | 27.18 | 0.12 | 57.54 | 50.98 | 18.03 | 14.14 | 79.01 | 93.83 | 0.67 | 66.73 | 51.83 | 0.29 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | 37.85 | — | — | 57.24 | 28.09 | 36.87 | — | 20.57 | 11.26 | 15.11 | 43.46 | 0.01 | 60.13 | 50.77 | 28.03 | 19.24 | 83.94 | 96.18 | 2.14 | 69.10 | 54.79 | 4.41 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 35.32 | — | — | 53.28 | 17.50 | 34.72 | — | 20.99 | 18.68 | 12.60 | 31.09 | 0.95 | 58.39 | 49.00 | 26.78 | 15.52 | 80.72 | 95.78 | 4.44 | 65.48 | 49.86 | 0.05 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | 34.04 | — | — | 49.79 | 40.68 | 16.46 | — | 11.90 | 24.65 | 12.48 | 29.20 | 9.32 | 60.64 | 5.52 | 17.26 | 12.93 | 84.14 | 96.45 | 6.19 | 72.93 | 57.36 | 4.77 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | 31.45 | — | — | 47.74 | 36.36 | 5.00 | — | 9.79 | 8.36 | 6.74 | 29.51 | 11.36 | 63.20 | 30.15 | 2.42 | 8.18 | 82.19 | 96.06 | 8.80 | 70.26 | 49.46 | 0.51 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | 40.46 | — | — | 57.24 | 39.64 | 14.77 | — | 22.04 | 8.72 | 15.03 | 49.81 | 32.16 | 69.03 | 45.25 | 8.79 | 29.61 | 84.72 | 96.91 | 20.74 | 72.35 | 60.40 | 1.03 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 36.52 | — | — | 54.00 | 35.59 | 21.05 | — | 17.34 | 19.12 | 4.04 | 42.12 | 14.07 | 67.03 | 45.42 | 4.10 | 17.74 | 81.02 | 97.12 | 9.82 | 71.27 | 55.93 | 0.68 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | 37.78 | — | — | 55.35 | 38.07 | 9.62 | — | 30.08 | 4.04 | 9.50 | 46.58 | 0.41 | 66.01 | 50.11 | 11.52 | 15.55 | 82.88 | 96.19 | 5.76 | 75.01 | 66.42 | 16.97 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | 34.89 | — | — | 52.80 | 36.69 | 19.46 | — | 28.20 | 4.91 | 6.61 | 40.85 | 0.06 | 66.13 | 50.27 | 1.95 | 7.15 | 82.07 | 90.34 | 6.53 | 72.65 | 58.54 | 2.85 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | 43.28 | — | — | 58.52 | 43.61 | 39.08 | — | 33.39 | 6.47 | 15.89 | 55.16 | 36.00 | 69.66 | 50.50 | 2.12 | 23.32 | 84.52 | 95.64 | 19.53 | 73.61 | 67.09 | 4.95 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 39.81 | — | — | 57.70 | 34.66 | 30.23 | — | 37.81 | 6.66 | 13.10 | 51.62 | 1.03 | 68.38 | 51.49 | 8.77 | 24.57 | 85.68 | 95.50 | 6.56 | 70.72 | 64.77 | 7.28 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | 38.36 | — | — | 56.83 | 20.09 | 27.42 | — | 32.62 | 11.43 | 7.21 | 46.01 | 28.90 | 68.40 | 41.17 | 1.09 | 12.17 | 84.06 | 96.18 | 14.29 | 74.53 | 65.99 | 2.15 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | 35.48 | — | — | 53.57 | 19.35 | 34.71 | — | 36.24 | 20.18 | 4.65 | 40.99 | 1.42 | 72.33 | 35.55 | 5.30 | 10.90 | 78.10 | 90.93 | 3.71 | 72.07 | 57.94 | 0.68 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | 44.06 | — | — | 57.35 | 35.78 | 34.05 | — | 52.83 | 11.21 | 16.66 | 44.85 | 34.36 | 73.91 | 40.17 | 3.81 | 28.12 | 84.85 | 96.06 | 32.29 | 74.66 | 69.46 | 2.72 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 40.91 | — | — | 62.50 | 19.17 | 38.91 | — | 40.80 | 19.27 | 12.26 | 38.88 | 29.13 | 74.84 | 52.11 | 4.89 | 18.08 | 81.97 | 96.72 | 8.84 | 72.65 | 62.72 | 2.65 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | 39.68 | — | — | 58.85 | 36.87 | 17.76 | — | 28.02 | 19.07 | 6.96 | 52.49 | 17.89 | 68.41 | 32.95 | 12.70 | 23.08 | 83.92 | 93.50 | 19.09 | 74.27 | 63.65 | 4.82 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | 38.74 | — | — | 57.22 | 36.19 | 36.70 | — | 37.32 | 4.75 | 6.51 | 36.78 | 14.02 | 68.82 | 44.79 | 1.45 | 31.39 | 84.06 | 90.25 | 6.97 | 72.44 | 60.50 | 7.11 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | 46.75 | — | — | 63.05 | 36.76 | 31.91 | — | 41.66 | 15.98 | 21.30 | 47.92 | 64.44 | 69.69 | 34.69 | 3.05 | 33.76 | 85.69 | 96.82 | 52.29 | 76.46 | 65.69 | 0.36 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 43.59 | — | — | 58.78 | 33.21 | 36.56 | — | 47.82 | 17.56 | 16.66 | 50.74 | 26.17 | 72.44 | 47.22 | 9.03 | 28.03 | 85.09 | 95.15 | 19.34 | 73.37 | 62.97 | 4.45 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | 40.76 | — | — | 59.15 | 38.14 | 22.16 | — | 30.45 | 19.38 | 9.49 | 48.77 | 20.31 | 69.63 | 42.67 | 8.76 | 21.40 | 86.87 | 94.93 | 17.64 | 75.74 | 62.80 | 5.43 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | 38.95 | — | — | 55.86 | 40.34 | 38.12 | — | 42.28 | 9.30 | 3.63 | 45.24 | 13.40 | 70.61 | 35.80 | 2.40 | 32.83 | 82.88 | 87.23 | 5.82 | 73.17 | 59.87 | 2.36 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | 43.26 | — | — | 58.91 | 32.33 | 37.46 | — | 42.26 | 4.54 | 16.65 | 54.27 | 28.04 | 71.72 | 36.61 | 2.63 | 34.04 | 85.85 | 96.94 | 32.34 | 75.45 | 66.61 | 2.08 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 44.14 | — | — | 59.69 | 39.88 | 42.86 | — | 42.37 | 12.06 | 17.84 | 49.73 | 21.04 | 72.03 | 45.09 | 9.52 | 36.41 | 87.53 | 96.26 | 14.40 | 75.39 | 64.81 | 7.69 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | 31.01 | — | — | 54.62 | 27.37 | 0.07 | — | 13.62 | 2.14 | 15.13 | 41.72 | 0.00 | 59.87 | 17.12 | 0.14 | 18.30 | 83.28 | 95.21 | 2.43 | 70.20 | 56.99 | 0.00 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 32.80 | — | — | 53.44 | 23.67 | 23.34 | — | 22.34 | 3.35 | 6.90 | 39.28 | 0.64 | 63.52 | 34.65 | 1.47 | 12.72 | 82.13 | 93.81 | 1.97 | 68.33 | 58.64 | 0.15 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 36.73 | — | — | 56.57 | 18.82 | 24.33 | — | 21.98 | 10.36 | 13.79 | 45.90 | 27.41 | 67.98 | 36.76 | 1.16 | 11.41 | 84.23 | 96.26 | 10.07 | 72.72 | 61.45 | 0.00 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 35.68 | — | — | 55.47 | 19.08 | 30.03 | — | 23.13 | 9.45 | 10.35 | 41.81 | 2.65 | 67.15 | 41.31 | 3.84 | 17.31 | 84.32 | 95.56 | 6.76 | 71.13 | 61.24 | 1.60 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | 31.26 | — | — | 57.45 | 29.57 | 1.55 | — | 4.07 | 9.61 | 15.50 | 38.63 | 0.39 | 63.35 | 21.96 | 1.54 | 9.85 | 85.46 | 95.59 | 0.00 | 67.99 | 60.10 | 0.00 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 33.28 | — | — | 51.73 | 23.60 | 23.96 | — | 11.73 | 7.96 | 5.71 | 35.23 | 3.20 | 65.41 | 44.08 | 1.55 | 14.15 | 82.03 | 95.33 | 5.62 | 69.82 | 57.95 | 0.00 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 39.60 | — | — | 61.28 | 25.58 | 15.64 | — | 21.48 | 8.55 | 14.22 | 44.57 | 38.94 | 70.10 | 46.72 | 1.80 | 18.84 | 85.42 | 96.48 | 28.23 | 70.41 | 64.50 | 0.00 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 35.58 | — | — | 56.55 | 29.83 | 18.85 | — | 29.46 | 7.58 | 11.09 | 38.71 | 2.86 | 67.90 | 45.85 | 0.31 | 17.33 | 83.82 | 95.67 | 4.48 | 69.99 | 60.03 | 0.17 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | 29.41 | — | — | 51.38 | 31.77 | 3.14 | — | 10.79 | 8.30 | 12.01 | 27.13 | 0.23 | 56.69 | 14.71 | 0.60 | 10.51 | 84.36 | 94.42 | 0.00 | 65.31 | 56.16 | 1.94 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | 29.52 | — | — | 46.25 | 13.87 | 5.81 | — | 13.24 | 4.92 | 8.06 | 34.81 | 0.71 | 55.40 | 25.49 | 2.34 | 15.07 | 83.54 | 94.59 | 0.00 | 63.13 | 55.22 | 8.95 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | 34.44 | — | — | 56.62 | 20.10 | 13.37 | — | 26.68 | 9.18 | 15.70 | 34.14 | 12.28 | 62.67 | 27.83 | 9.02 | 19.38 | 87.21 | 96.41 | 2.03 | 64.94 | 62.36 | 0.00 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 32.10 | — | — | 50.33 | 25.98 | 19.91 | — | 17.39 | 7.66 | 14.66 | 32.92 | 2.15 | 60.31 | 32.44 | 1.16 | 7.17 | 85.38 | 95.60 | 0.25 | 64.87 | 58.86 | 0.81 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | 35.95 | — | — | 56.08 | 30.67 | 33.80 | — | 25.29 | 17.40 | 7.83 | 30.73 | 15.69 | 66.11 | 31.17 | 1.98 | 9.02 | 81.85 | 93.49 | 12.42 | 72.82 | 60.79 | 0.00 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | 35.21 | — | — | 50.00 | 20.07 | 25.52 | — | 35.69 | 13.69 | 7.83 | 40.81 | 0.01 | 67.93 | 36.17 | 0.20 | 21.17 | 81.80 | 93.19 | 5.95 | 71.39 | 60.65 | 1.73 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | 43.45 | — | — | 56.66 | 33.02 | 37.14 | — | 48.48 | 9.12 | 17.32 | 56.01 | 25.53 | 72.59 | 43.71 | 0.17 | 23.85 | 86.84 | 96.16 | 36.76 | 73.45 | 65.24 | 0.00 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 41.01 | — | — | 55.65 | 31.57 | 25.81 | — | 44.30 | 11.93 | 17.13 | 51.65 | 21.20 | 71.19 | 49.92 | 0.09 | 23.82 | 85.89 | 95.76 | 13.60 | 73.32 | 65.39 | 0.00 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | 32.07 | — | — | 54.83 | 31.68 | 1.43 | — | 12.36 | 11.90 | 8.87 | 28.35 | 7.42 | 59.78 | 27.17 | 0.43 | 20.13 | 80.78 | 93.72 | 12.16 | 67.51 | 54.02 | 4.75 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | 30.55 | — | — | 45.78 | 20.40 | 5.88 | — | 14.06 | 9.65 | 4.72 | 38.52 | 4.81 | 64.61 | 21.95 | 0.26 | 17.37 | 80.97 | 95.35 | 2.38 | 68.74 | 53.24 | 1.26 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | 38.69 | — | — | 53.41 | 28.97 | 32.61 | — | 28.16 | 14.38 | 14.44 | 41.48 | 19.75 | 67.01 | 42.87 | 0.35 | 17.48 | 86.11 | 95.83 | 11.15 | 68.92 | 61.59 | 11.91 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 36.63 | — | — | 56.49 | 35.84 | 12.29 | — | 30.15 | 12.51 | 8.41 | 41.99 | 12.73 | 67.46 | 37.54 | 2.38 | 12.93 | 81.80 | 95.78 | 12.35 | 67.96 | 61.38 | 9.38 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | 30.19 | — | — | 53.22 | 30.22 | 1.78 | — | 10.07 | 4.61 | 12.62 | 28.48 | 0.48 | 59.85 | 38.82 | 0.01 | 12.55 | 77.24 | 90.99 | 1.70 | 69.15 | 48.15 | 3.49 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | 31.96 | — | — | 47.47 | 16.85 | 15.07 | — | 16.31 | 13.61 | 3.52 | 28.64 | 4.36 | 64.99 | 40.83 | 1.07 | 20.60 | 80.25 | 93.42 | 1.78 | 69.72 | 56.17 | 0.56 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | 37.07 | — | — | 55.26 | 33.23 | 29.96 | — | 23.41 | 16.52 | 14.95 | 37.82 | 8.22 | 67.90 | 47.56 | 1.33 | 15.87 | 85.35 | 95.80 | 0.03 | 70.17 | 60.58 | 3.35 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 34.77 | — | — | 54.76 | 20.32 | 26.70 | — | 25.48 | 19.87 | 5.48 | 41.73 | 3.48 | 67.12 | 44.97 | 4.60 | 8.50 | 80.56 | 93.19 | 1.24 | 68.04 | 57.70 | 2.18 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | 31.00 | — | — | 53.40 | 25.02 | 7.26 | — | 15.58 | 21.01 | 14.32 | 34.95 | 4.78 | 39.80 | 27.14 | 0.49 | 14.99 | 82.74 | 92.93 | 7.94 | 59.24 | 56.33 | 0.10 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | 30.52 | — | — | 50.99 | 15.08 | 23.71 | — | 17.87 | 10.10 | 12.32 | 37.97 | 1.28 | 42.47 | 26.39 | 0.90 | 22.69 | 78.81 | 93.89 | 1.92 | 57.37 | 52.97 | 2.58 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | 34.31 | — | — | 54.68 | 21.80 | 16.48 | — | 18.01 | 19.92 | 15.48 | 41.63 | 3.02 | 46.65 | 42.20 | 2.92 | 14.63 | 84.04 | 95.10 | 14.79 | 65.81 | 60.42 | 0.00 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 32.39 | — | — | 53.45 | 19.06 | 20.12 | — | 17.82 | 19.78 | 14.01 | 39.91 | 9.60 | 46.96 | 23.53 | 0.55 | 17.78 | 81.38 | 94.68 | 4.75 | 63.39 | 55.88 | 0.28 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | 33.50 | — | — | 56.49 | 29.93 | 6.33 | — | 16.90 | 18.16 | 15.03 | 34.56 | 0.96 | 62.45 | 33.56 | 0.89 | 14.16 | 83.57 | 94.12 | 7.59 | 69.10 | 58.90 | 0.33 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 34.47 | — | — | 52.19 | 23.44 | 19.80 | — | 18.97 | 12.24 | 10.74 | 45.98 | 3.74 | 67.71 | 35.20 | 0.22 | 21.87 | 80.71 | 91.86 | 7.46 | 68.27 | 59.82 | 0.23 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 38.62 | — | — | 56.56 | 31.38 | 19.51 | — | 37.19 | 14.89 | 16.17 | 50.69 | 9.35 | 70.13 | 37.58 | 0.36 | 16.93 | 84.69 | 96.19 | 19.29 | 71.63 | 62.70 | 0.00 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 37.83 | — | — | 55.63 | 37.18 | 21.71 | — | 32.10 | 20.91 | 16.44 | 53.74 | 5.81 | 69.79 | 31.67 | 0.45 | 20.17 | 84.96 | 95.57 | 5.64 | 67.54 | 61.06 | 0.56 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | 34.09 | — | — | 52.50 | 35.18 | 6.35 | — | 20.19 | 16.63 | 11.50 | 35.14 | 0.02 | 66.62 | 40.70 | 1.77 | 11.94 | 83.07 | 94.02 | 7.79 | 72.44 | 56.80 | 0.91 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | 36.77 | — | — | 49.36 | 25.22 | 20.86 | — | 26.54 | 17.27 | 15.16 | 35.18 | 16.35 | 67.87 | 44.71 | 1.03 | 18.09 | 83.23 | 94.61 | 12.78 | 69.91 | 61.23 | 2.45 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | 42.48 | — | — | 60.16 | 42.38 | 29.50 | — | 45.50 | 15.86 | 17.07 | 53.34 | 26.22 | 68.76 | 37.47 | 0.45 | 19.73 | 86.35 | 95.73 | 29.04 | 73.29 | 63.53 | 0.21 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 41.57 | — | — | 55.22 | 36.98 | 24.23 | — | 44.55 | 20.77 | 16.19 | 44.07 | 23.97 | 70.22 | 49.27 | 3.85 | 19.40 | 85.33 | 95.80 | 24.31 | 69.82 | 64.33 | 0.00 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | 30.26 | — | — | 53.20 | 33.95 | 6.75 | — | 9.10 | 7.47 | 8.07 | 33.34 | 8.19 | 34.57 | 23.87 | 2.57 | 18.94 | 82.64 | 92.66 | 5.48 | 61.83 | 62.09 | 0.00 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | 30.45 | — | — | 48.67 | 26.57 | 19.85 | — | 17.15 | 14.76 | 10.15 | 29.01 | 5.02 | 39.63 | 31.82 | 0.06 | 13.15 | 79.57 | 94.17 | 4.03 | 59.28 | 54.92 | 0.21 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | 34.52 | — | — | 56.77 | 34.31 | 20.19 | — | 23.05 | 16.42 | 17.20 | 38.89 | 12.40 | 45.23 | 27.16 | 0.21 | 17.45 | 83.36 | 95.29 | 8.03 | 66.44 | 58.93 | 0.00 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 33.68 | — | — | 55.00 | 30.16 | 22.40 | — | 20.34 | 16.45 | 15.36 | 36.96 | 12.37 | 43.93 | 31.09 | 0.79 | 19.39 | 81.61 | 95.35 | 2.19 | 62.23 | 59.77 | 0.92 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | 34.32 | — | — | 49.65 | 42.49 | 7.71 | — | 8.52 | 24.08 | 21.01 | 34.24 | 1.43 | 57.25 | 45.51 | 6.56 | 10.78 | 84.37 | 96.00 | 5.59 | 71.16 | 50.74 | 0.69 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | 31.09 | — | — | 43.78 | 38.00 | 8.32 | — | 11.66 | 10.07 | 2.71 | 27.72 | 5.03 | 63.30 | 39.77 | 4.09 | 5.15 | 80.63 | 95.71 | 1.98 | 66.15 | 51.11 | 4.33 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | 41.38 | — | — | 57.12 | 42.18 | 18.58 | — | 23.38 | 19.30 | 16.96 | 41.03 | 42.68 | 67.46 | 40.54 | 8.49 | 21.35 | 85.67 | 96.76 | 30.51 | 70.60 | 60.50 | 1.79 |
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
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 4/4 | 2.54 | 2.54 | 2.53 | 2.53 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 4/4 | 174.47 | 174.54 | 169.45 | 173.50 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 4/4 | 34.67 | 34.69 | 34.64 | 34.86 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 4/4 | 82.88 | 84.79 | 82.98 | 83.15 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 4/4 | 133.19 | 135.52 | 130.58 | 136.44 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 4/4 | 42.03 | 42.99 | 42.35 | 41.74 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 30.28 | 30.43 | 29.73 | 30.86 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 4/4 | 28.92 | 29.11 | 29.04 | 28.95 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 76.13 | 76.08 | 76.52 | 74.32 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 4/4 | 140.26 | 148.70 | 142.93 | 142.82 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 4/4 | 170.58 | 160.52 | 152.77 | 165.04 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 4/4 | 220.66 | 221.73 | 236.75 | 205.45 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 4/4 | 61.65 | 64.27 | 64.06 | 66.98 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 4/4 | 221.20 | 221.22 | 221.81 | 216.54 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 4/4 | 256.01 | 252.54 | 257.07 | 255.38 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 4/4 | 225.57 | 221.58 | 226.09 | 210.83 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 4/4 | 136.44 | 140.32 | 138.15 | 134.72 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 4/4 | 47.85 | 47.95 | 48.18 | 48.44 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 4/4 | 214.58 | 213.70 | 219.18 | 214.13 |
| [segformer_b0](models/segformer_b0/README.md) | 3/4 | 133.40 | 135.12 | 136.27 | — |
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
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 259 | 2.01 | 2.36 | 12.11 | 0.15 | 21.68 | 22.88 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | completed | 4000 | 2592 | 2.36 | 4.62 | 4.59 | 0.41 | 21.16 | 23.51 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2592 | 5.94 | 8.52 | 16.38 | 4.58 | 20.98 | 24.48 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 2333 | 6.45 | 7.93 | 25.65 | 3.47 | 26.04 | 28.93 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2851 | 7.15 | 10.38 | 18.69 | 5.22 | 28.13 | 31.25 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | completed | 4000 | 3629 | 11.12 | 63.09 | 11.90 | 6.24 | 24.74 | 28.87 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3629 | 22.68 | 53.08 | 28.38 | 13.68 | 29.35 | 34.24 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3629 | 14.13 | 27.98 | 22.20 | 12.51 | 28.86 | 33.67 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 777 | 14.61 | 51.56 | 16.93 | 8.70 | 22.92 | 26.74 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | completed | 4000 | 2851 | 5.01 | 30.17 | 5.67 | 4.21 | 29.04 | 33.88 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1296 | 6.38 | 7.02 | 41.17 | 4.12 | 27.52 | 32.11 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 2333 | 15.02 | 18.19 | 46.27 | 9.82 | 35.32 | 41.21 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2333 | 7.97 | 9.84 | 29.60 | 5.25 | 34.65 | 38.50 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | completed | 4000 | 2333 | 7.00 | 7.79 | 40.86 | 4.18 | 30.17 | 35.20 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2074 | 1.62 | 3.03 | 3.35 | 1.37 | 27.82 | 32.46 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3629 | 9.30 | 33.68 | 11.38 | 7.56 | 40.21 | 44.67 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 3629 | 4.53 | 13.59 | 6.36 | 3.78 | 35.02 | 40.85 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | completed | 4000 | 777 | 9.19 | 14.97 | 19.24 | 5.77 | 32.68 | 38.13 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 518 | 2.42 | 2.83 | 14.43 | 0.59 | 24.51 | 28.59 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 518 | 4.89 | 6.54 | 16.25 | 0.93 | 43.14 | 45.54 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 1296 | 3.67 | 4.68 | 14.49 | 2.57 | 38.50 | 44.91 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | completed | 4000 | 1296 | 4.65 | 12.09 | 7.02 | 0.46 | 33.82 | 39.46 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2074 | 9.46 | 71.43 | 9.83 | 5.22 | 35.66 | 41.60 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 2592 | 3.04 | 4.22 | 9.84 | 1.06 | 44.19 | 51.56 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 1555 | 5.98 | 66.73 | 6.16 | 5.06 | 44.39 | 49.32 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | completed | 4000 | 3888 | 5.14 | 7.33 | 14.67 | 5.14 | 33.78 | 39.41 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1814 | 0.85 | 1.25 | 2.60 | 0.78 | 36.13 | 42.16 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 1555 | 3.09 | 11.21 | 4.10 | 2.35 | 44.28 | 49.20 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 3888 | 1.80 | 2.16 | 9.77 | 1.81 | 41.24 | 48.11 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | completed | 4000 | 259 | 9.31 | 13.56 | 22.90 | 5.60 | 27.47 | 29.00 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 777 | 2.97 | 11.34 | 3.87 | 1.59 | 35.48 | 41.39 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 1037 | 2.06 | 3.11 | 5.75 | 1.48 | 42.40 | 49.46 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 1555 | 9.81 | 27.46 | 13.25 | 8.60 | 41.84 | 48.81 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | completed | 4000 | 1555 | 0.89 | 1.09 | 4.67 | 0.07 | 27.68 | 32.29 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1555 | 4.93 | 6.04 | 21.14 | 0.96 | 24.98 | 29.14 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 1555 | 1.22 | 1.41 | 8.37 | 0.33 | 39.29 | 43.66 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 777 | 6.31 | 12.74 | 11.12 | 1.07 | 29.65 | 34.59 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | completed | 4000 | 3370 | 1.11 | 4.38 | 1.47 | 0.74 | 29.77 | 34.73 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2851 | 0.77 | 0.99 | 3.34 | 0.53 | 31.30 | 36.51 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 1814 | 1.40 | 2.69 | 2.84 | 0.86 | 38.01 | 44.34 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 1814 | 0.78 | 1.15 | 2.41 | 0.08 | 35.79 | 41.76 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | completed | 4000 | 259 | 1.96 | 2.16 | 17.74 | 0.58 | 16.15 | 18.84 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2074 | 2.04 | 5.56 | 3.11 | 1.01 | 25.95 | 30.27 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 1555 | 2.87 | 3.74 | 11.00 | 2.87 | 35.39 | 41.29 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 1037 | 0.93 | 1.27 | 3.44 | 0.40 | 29.84 | 34.82 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | completed | 4000 | 2592 | 1.55 | 3.07 | 3.04 | 0.84 | 31.65 | 36.93 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1037 | 0.59 | 0.75 | 2.64 | 0.22 | 29.28 | 34.15 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 518 | 0.34 | 0.44 | 1.52 | 0.12 | 40.89 | 47.70 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 518 | 0.34 | 0.64 | 0.73 | 0.09 | 38.65 | 42.94 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | completed | 4000 | 3888 | 0.41 | 1.03 | 0.68 | 0.21 | 27.40 | 31.96 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 518 | 1.04 | 1.16 | 8.88 | 0.24 | 20.97 | 24.47 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 2592 | 0.54 | 0.67 | 2.55 | 0.09 | 36.33 | 42.39 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 1296 | 7.02 | 70.55 | 7.23 | 2.81 | 32.41 | 36.01 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | completed | 4000 | 259 | 0.53 | 0.85 | 1.41 | 0.01 | 18.57 | 19.60 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1296 | 1.93 | 2.67 | 6.54 | 1.03 | 24.68 | 28.80 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 1037 | 1.61 | 2.19 | 5.78 | 0.90 | 34.11 | 39.80 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 1037 | 4.64 | 5.73 | 19.66 | 2.19 | 32.62 | 36.24 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | completed | 4000 | 777 | 7.89 | 48.61 | 8.61 | 0.44 | 25.06 | 27.85 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1814 | 1.66 | 2.48 | 4.75 | 0.62 | 27.85 | 32.49 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 1814 | 2.55 | 3.60 | 8.00 | 1.34 | 33.24 | 38.78 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 3370 | 1.10 | 1.79 | 2.74 | 0.38 | 31.24 | 36.45 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | completed | 4000 | 1037 | 2.40 | 7.36 | 3.43 | 0.59 | 24.74 | 28.86 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 777 | 5.01 | 6.55 | 17.57 | 0.18 | 28.95 | 33.78 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 777 | 0.72 | 1.98 | 1.11 | 0.19 | 38.77 | 45.24 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 777 | 0.92 | 1.76 | 1.89 | 0.56 | 34.55 | 40.31 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | completed | 4000 | 2074 | 0.88 | 70.10 | 0.88 | 0.56 | 31.55 | 36.80 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1296 | 2.53 | 34.65 | 2.65 | 0.35 | 29.36 | 34.25 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 518 | 4.42 | 10.01 | 7.32 | 0.45 | 35.53 | 41.45 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2851 | 4.60 | 26.09 | 5.28 | 3.86 | 38.60 | 45.03 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | completed | 4000 | 2074 | 11.85 | 41.74 | 14.20 | 1.88 | 28.19 | 32.89 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1037 | 2.17 | 5.87 | 3.33 | 0.06 | 30.73 | 35.85 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 518 | 1.11 | 22.70 | 1.15 | 0.22 | 34.66 | 40.44 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2333 | 1.54 | 7.33 | 1.92 | 0.46 | 34.39 | 40.13 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | completed | 4000 | 3629 | 2.86 | 3.58 | 12.46 | 2.29 | 32.25 | 37.63 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 1296 | 3.40 | 4.17 | 15.53 | 1.37 | 22.52 | 26.27 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 1296 | 6.48 | 9.38 | 17.31 | 3.82 | 35.29 | 41.17 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | collecting | 4000 | 3370 | 6.57 | 14.44 | 10.76 | 6.08 | 33.34 | 38.90 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | training | 2499 | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | training | 2499 | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | training | 2449 | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | training | 2199 | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | training | 199 | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | training | 49 | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | training | 49 | — | — | — | — | — | — | — |
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
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | 15.78 | 6.64 | 6564.47 | 17.05 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 15.78 | 6.64 | 6542.56 | 17.38 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | 15.78 | 6.64 | 6522.17 | 17.08 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 15.78 | 6.64 | 6555.15 | 17.09 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | 9.10 | 6.64 | 3006.22 | 12.36 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | 9.10 | 6.64 | 2993.37 | 12.12 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | 9.10 | 6.64 | 3025.85 | 12.38 |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.10 | 6.64 | 3028.56 | 12.04 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | 7.79 | 7.03 | 2325.18 | 12.95 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | 7.79 | 7.03 | 2332.50 | 12.75 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | 7.79 | 7.03 | 2351.23 | 12.62 |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.79 | 7.03 | 2360.35 | 12.78 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | 11.71 | 7.52 | 5305.24 | 19.56 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | 11.71 | 7.52 | 5216.66 | 19.47 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | 11.71 | 7.52 | 5202.44 | 19.65 |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.71 | 7.52 | 5217.79 | 19.55 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | 17.35 | 7.58 | 6705.33 | 18.69 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | 17.35 | 7.58 | 6726.33 | 18.38 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | 17.35 | 7.58 | 6778.40 | 18.36 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.35 | 7.58 | 6757.72 | 18.59 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | 15.83 | 8.11 | 6529.41 | 22.39 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | 15.80 | 8.11 | 6416.83 | 23.07 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | 15.83 | 8.11 | 6388.54 | 22.37 |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 15.80 | 8.11 | 6435.06 | 22.72 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | 10.27 | 7.42 | 3205.85 | 16.20 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | 10.20 | 7.42 | 3226.91 | 15.74 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | 10.20 | 7.42 | 3253.81 | 15.73 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.20 | 7.42 | 3244.54 | 16.06 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | 8.31 | 6.78 | 2410.16 | 11.63 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 8.31 | 6.78 | 2369.81 | 11.08 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 8.31 | 6.78 | 2385.98 | 11.15 |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.31 | 6.78 | 2386.38 | 11.33 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | 7.46 | 6.82 | 2406.65 | 11.16 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 7.46 | 6.82 | 2398.43 | 11.25 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 7.46 | 6.82 | 2357.71 | 10.37 |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.46 | 6.82 | 2374.31 | 10.95 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | 6.72 | 6.51 | 2380.82 | 9.83 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | 6.72 | 6.51 | 2379.77 | 9.71 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | 6.72 | 6.51 | 2324.21 | 9.67 |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 6.72 | 6.51 | 2366.41 | 9.69 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | 10.93 | 7.54 | 3656.79 | 14.78 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | 10.93 | 7.54 | 3605.91 | 14.91 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | 10.87 | 7.54 | 3590.72 | 15.05 |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.94 | 7.54 | 3597.02 | 15.23 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | 7.34 | 7.04 | 2406.97 | 10.79 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | 7.34 | 7.04 | 2334.12 | 10.76 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | 7.34 | 7.04 | 2333.52 | 10.68 |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.34 | 7.04 | 2377.14 | 11.25 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | 7.76 | 6.87 | 2383.70 | 11.75 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | 7.76 | 6.87 | 2440.64 | 11.50 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | 7.76 | 6.87 | 2357.76 | 11.35 |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.76 | 6.87 | 2400.81 | 11.52 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | 8.27 | 6.75 | 3054.42 | 10.51 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | 8.27 | 6.75 | 3056.16 | 10.15 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | 8.27 | 6.75 | 3054.85 | 10.26 |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.27 | 6.75 | 3055.27 | 10.25 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | 9.36 | 7.25 | 2546.36 | 11.34 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | 9.36 | 7.25 | 2523.16 | 12.41 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | 9.35 | 7.25 | 2525.65 | 11.25 |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.36 | 7.25 | 2544.49 | 11.63 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | 11.64 | 7.02 | 4998.53 | 16.90 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | 11.64 | 7.02 | 5005.67 | 16.93 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | 11.64 | 7.02 | 4974.99 | 16.97 |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.64 | 7.02 | 5017.66 | 17.34 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | 8.29 | 6.75 | 3090.53 | 10.42 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | 8.29 | 6.75 | 3117.71 | 10.78 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | 8.29 | 6.75 | 3069.61 | 10.61 |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.29 | 6.75 | 3095.76 | 10.29 |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | 7.79 | 7.03 | 2398.89 | 12.87 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | 7.80 | 7.03 | 2343.87 | 13.01 |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | 7.79 | 7.03 | 2317.60 | 13.23 |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 7.79 | 7.03 | 2342.72 | 12.66 |
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
