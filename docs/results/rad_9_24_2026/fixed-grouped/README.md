# RAD 9/24: Scene-grouped split (`fixed-grouped`)

Every model and starting point trained on the scene-grouped split (labels: re-rendered from the polygon JSONs; split: scene-grouped (from v1/v2)). Every model on this page was trained by us. The tables keep the shared RTIS report's names: an *initialization path* is the starting point (pretraining before training on these images): `rtis_only` = recipe pretrained weights, `cityscapes_to_rtis` = Cityscapes, `railsem19_to_rtis` = RailSem19, `cityscapes_to_railsem19_to_rtis` = Cityscapes → RailSem19. The Quality, Mud-pumping and [Per-class IoU](#per-class-iou) tables count each class only on the validation images that contain it; the per-run table, `results.csv` and the model pages also keep the campaign's own pixel-pooled numbers, which selected the checkpoints. The [study page](../README.md) compares the splits.

**40/40 completed · 0 failed**

Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling.

[RAD 9/24 study](../README.md) · [CSV results](results.csv) · [Full machine records](status.json)

10 models; four initialization paths; seeds [0]. Train/val/test: 217/37/60 images. Test is held out. Split grouping status: `provisional_until_recording_provenance_confirmed`. Seed variation does not establish independent-recording generalization.

## Quality

Validation **mIoU (%)**: each class's IoU averaged over the validation images that contain it, then over the classes present. Cells show the mean over completed seeds; — means unavailable. Raw/EMA settings are recorded on each model page.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 47.86 | 49.70 | 55.61 | 48.62 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 50.85 | 52.96 | 51.54 | 52.52 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 34.85 | 35.55 | 44.91 | 40.91 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 28.84 | 38.87 | 44.16 | 43.75 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 37.15 | 38.51 | 46.38 | 41.97 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 37.20 | 39.80 | 47.62 | 44.38 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 30.63 | 24.40 | 42.52 | 37.35 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 23.53 | 31.50 | 43.44 | 37.84 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 26.48 | 28.67 | 33.63 | 35.78 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 38.80 | 35.18 | 43.41 | 40.22 |

## Mud-pumping

Validation **mud-pumping IoU (%)** for the same checkpoints, averaged over the validation images with mud-pumping (images without it are not counted). Precision, recall and examples are on each model page.

All images with mud (n=18):

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 37.06 | 39.19 | 32.53 | 11.49 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 32.89 | 27.33 | 9.87 | 34.87 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 6.52 | 8.10 | 7.12 | 5.16 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 11.09 | 4.06 | 5.39 | 11.06 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 19.25 | 22.21 | 11.67 | 17.33 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 11.91 | 21.60 | 13.64 | 21.44 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 15.28 | 4.37 | 13.37 | 5.44 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 9.41 | 9.12 | 15.45 | 12.09 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 6.89 | 20.45 | 9.62 | 15.84 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 10.25 | 14.26 | 13.34 | 5.60 |

Train-camera images with mud (n=17):

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 39.11 | 41.38 | 34.17 | 11.50 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 34.59 | 28.75 | 10.28 | 36.52 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 6.20 | 8.38 | 7.46 | 5.46 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 11.74 | 3.74 | 5.57 | 11.19 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 19.97 | 23.08 | 11.93 | 16.92 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 12.44 | 22.79 | 14.29 | 22.59 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 15.63 | 4.57 | 13.93 | 5.58 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 9.79 | 9.02 | 16.23 | 12.15 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 7.29 | 21.50 | 9.87 | 16.20 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 10.64 | 15.00 | 13.97 | 5.80 |

## Per-class IoU

Validation IoU (%) of every class, each averaged only over the validation images that contain the class (n = those images); — = no image contains it. mIoU averages the classes with at least one such image.

| Model | Initialization path | Seed | mIoU (each class over images that contain it) | person (n=0) | truck (n=0) | rail-track (n=37) | vegetation-overgrowth (n=13) | car (n=3) | on-rails (n=0) | traffic-sign (n=9) | road (n=11) | sidewalk (n=12) | construction (n=12) | tram-track (n=2) | pole (n=21) | traffic-light (n=3) | mud-pumping (n=18) | fence (n=7) | terrain (n=35) | sky (n=28) | rail-embedded (n=3) | rail-raised (n=37) | trackbed (n=37) | standing-water (n=9) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | 47.86 | — | — | 68.31 | 26.02 | 34.48 | — | 26.02 | 11.40 | 26.06 | 39.60 | 36.60 | 70.87 | 44.80 | 37.06 | 40.86 | 87.47 | 96.79 | 2.54 | 78.08 | 75.07 | 59.37 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | 49.70 | — | — | 68.39 | 29.04 | 63.82 | — | 33.70 | 15.12 | 27.14 | 58.85 | 21.58 | 73.47 | 51.71 | 39.19 | 44.23 | 87.82 | 96.92 | 0.00 | 75.99 | 73.20 | 34.36 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | 55.61 | — | — | 75.43 | 45.38 | 54.51 | — | 37.55 | 15.24 | 44.79 | 57.14 | 46.09 | 72.82 | 46.03 | 32.53 | 47.17 | 88.65 | 97.24 | 48.90 | 78.28 | 77.40 | 35.92 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 48.62 | — | — | 69.47 | 36.29 | 63.20 | — | 35.01 | 17.01 | 40.29 | 60.71 | 0.25 | 73.35 | 52.88 | 11.49 | 45.06 | 87.07 | 96.89 | 28.68 | 76.83 | 73.78 | 6.81 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | 50.85 | — | — | 69.38 | 38.54 | 9.97 | — | 33.26 | 12.31 | 53.19 | 57.83 | 34.19 | 71.60 | 42.41 | 32.89 | 45.62 | 89.60 | 96.71 | 31.11 | 76.74 | 76.63 | 43.40 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | 52.96 | — | — | 65.68 | 43.62 | 62.98 | — | 39.26 | 13.28 | 39.58 | 55.54 | 27.37 | 73.80 | 57.93 | 27.33 | 54.55 | 88.50 | 97.08 | 15.77 | 75.84 | 75.25 | 39.89 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | 51.54 | — | — | 68.36 | 43.45 | 52.33 | — | 41.63 | 16.68 | 52.71 | 53.93 | 49.67 | 72.51 | 50.16 | 9.87 | 47.38 | 88.52 | 96.83 | 42.81 | 76.00 | 64.86 | 0.00 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 52.52 | — | — | 71.09 | 38.43 | 46.27 | — | 44.45 | 9.50 | 52.84 | 58.97 | 41.15 | 74.05 | 56.96 | 34.87 | 51.07 | 87.54 | 97.02 | 30.01 | 75.75 | 75.39 | 0.00 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | 34.85 | — | — | 58.80 | 30.55 | 20.79 | — | 26.51 | 12.33 | 10.80 | 33.99 | 2.89 | 66.10 | 40.68 | 6.52 | 7.09 | 78.08 | 92.85 | 6.57 | 70.37 | 61.23 | 1.10 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | 35.55 | — | — | 53.13 | 15.80 | 19.90 | — | 39.19 | 20.42 | 5.65 | 39.85 | 7.79 | 71.56 | 50.92 | 8.10 | 9.34 | 76.71 | 90.73 | 4.46 | 70.37 | 55.63 | 0.26 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | 44.91 | — | — | 60.62 | 35.89 | 30.95 | — | 43.22 | 9.10 | 13.09 | 45.50 | 52.15 | 73.27 | 41.79 | 7.12 | 27.15 | 86.44 | 96.10 | 41.18 | 74.58 | 70.17 | 0.12 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 40.91 | — | — | 65.47 | 17.59 | 38.01 | — | 41.62 | 17.17 | 10.95 | 40.18 | 29.04 | 72.80 | 55.59 | 5.16 | 15.76 | 83.08 | 96.84 | 11.20 | 73.23 | 62.78 | 0.00 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | 28.84 | — | — | 54.63 | 12.32 | 0.00 | — | 0.00 | 9.40 | 15.29 | 29.70 | 1.38 | 53.99 | 0.00 | 11.09 | 25.77 | 82.06 | 94.40 | 0.00 | 69.88 | 58.66 | 0.50 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | 38.87 | — | — | 55.23 | 39.75 | 31.79 | — | 31.38 | 6.21 | 7.09 | 43.40 | 14.81 | 70.96 | 38.65 | 4.06 | 37.88 | 83.75 | 93.29 | 6.24 | 72.31 | 58.19 | 4.71 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | 44.16 | — | — | 58.99 | 30.75 | 37.98 | — | 40.89 | 6.36 | 16.27 | 54.35 | 31.09 | 72.60 | 41.19 | 5.39 | 34.32 | 85.96 | 96.96 | 36.64 | 76.36 | 66.10 | 2.65 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 43.75 | — | — | 60.58 | 40.89 | 42.37 | — | 37.60 | 10.27 | 18.14 | 42.36 | 21.31 | 71.16 | 44.18 | 11.06 | 38.00 | 87.42 | 96.04 | 18.52 | 75.49 | 65.29 | 6.88 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | 37.15 | — | — | 55.17 | 43.07 | 11.64 | — | 31.15 | 5.71 | 17.75 | 37.12 | 5.86 | 67.02 | 30.09 | 19.25 | 17.31 | 80.76 | 96.80 | 11.13 | 72.67 | 62.56 | 3.71 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | 38.51 | — | — | 58.46 | 42.55 | 33.53 | — | 31.65 | 4.23 | 12.20 | 29.19 | 9.27 | 68.47 | 42.16 | 22.21 | 18.16 | 82.99 | 96.70 | 9.36 | 72.90 | 56.07 | 3.09 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | 46.38 | — | — | 57.93 | 45.23 | 35.92 | — | 37.59 | 11.72 | 15.43 | 57.95 | 45.00 | 72.45 | 45.60 | 11.67 | 37.46 | 85.30 | 96.70 | 36.76 | 74.69 | 60.75 | 6.79 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 41.97 | — | — | 57.81 | 45.87 | 36.63 | — | 34.84 | 18.55 | 14.25 | 45.59 | 9.44 | 70.73 | 46.69 | 17.33 | 21.92 | 86.19 | 96.62 | 12.00 | 73.73 | 62.50 | 4.81 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | 37.20 | — | — | 55.73 | 35.01 | 15.74 | — | 19.72 | 9.31 | 13.99 | 42.08 | 7.59 | 67.69 | 39.60 | 11.91 | 5.46 | 88.22 | 96.58 | 18.96 | 72.61 | 63.04 | 6.34 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | 39.80 | — | — | 52.60 | 29.37 | 35.92 | — | 29.84 | 13.33 | 11.52 | 31.85 | 23.29 | 69.81 | 44.58 | 21.60 | 18.34 | 86.22 | 96.61 | 16.65 | 72.75 | 55.20 | 6.97 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | 47.62 | — | — | 61.60 | 41.03 | 35.71 | — | 46.93 | 17.13 | 16.69 | 56.43 | 48.26 | 73.95 | 46.52 | 13.64 | 30.59 | 87.39 | 96.76 | 40.87 | 74.72 | 64.98 | 3.99 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 44.38 | — | — | 57.87 | 42.88 | 36.17 | — | 40.24 | 11.57 | 9.47 | 30.38 | 33.50 | 72.27 | 46.18 | 21.44 | 27.55 | 87.17 | 96.74 | 35.98 | 75.12 | 64.37 | 9.88 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | 30.63 | — | — | 54.25 | 20.91 | 0.00 | — | 1.86 | 8.45 | 15.55 | 32.28 | 12.32 | 57.74 | 22.21 | 15.28 | 14.76 | 79.91 | 90.53 | 0.07 | 61.14 | 62.79 | 1.28 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | 24.40 | — | — | 38.40 | 0.00 | 0.00 | — | 0.00 | 0.70 | 12.52 | 24.48 | 0.00 | 59.09 | 0.00 | 4.37 | 21.67 | 72.81 | 93.74 | 0.00 | 62.05 | 49.37 | 0.00 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | 42.52 | — | — | 63.97 | 34.85 | 8.37 | — | 34.84 | 8.68 | 16.26 | 49.89 | 47.78 | 70.02 | 44.69 | 13.37 | 23.20 | 84.14 | 94.40 | 37.33 | 69.58 | 63.12 | 0.86 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 37.35 | — | — | 55.55 | 23.94 | 26.64 | — | 22.90 | 4.80 | 16.24 | 45.70 | 4.91 | 71.04 | 53.31 | 5.44 | 22.08 | 83.44 | 95.71 | 1.78 | 72.07 | 66.25 | 0.45 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | 23.53 | — | — | 39.37 | 16.84 | 0.00 | — | 0.00 | 7.71 | 10.93 | 21.41 | 0.00 | 40.38 | 0.00 | 9.41 | 9.61 | 75.25 | 85.47 | 0.00 | 56.20 | 51.01 | 0.00 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | 31.50 | — | — | 49.50 | 15.81 | 15.33 | — | 11.83 | 13.57 | 4.65 | 32.52 | 0.00 | 65.09 | 27.79 | 9.12 | 23.63 | 79.24 | 93.29 | 0.00 | 67.03 | 58.62 | 0.02 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | 43.44 | — | — | 62.19 | 26.91 | 29.09 | — | 33.28 | 28.58 | 15.47 | 43.12 | 49.65 | 62.82 | 47.85 | 15.45 | 23.38 | 85.54 | 96.25 | 23.83 | 71.03 | 65.71 | 1.81 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 37.84 | — | — | 58.39 | 28.49 | 22.48 | — | 29.20 | 25.53 | 14.49 | 42.85 | 11.27 | 64.58 | 36.55 | 12.09 | 23.46 | 81.53 | 94.67 | 0.14 | 70.41 | 62.93 | 2.11 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | 26.48 | — | — | 48.68 | 19.19 | 2.05 | — | 0.00 | 19.85 | 7.21 | 25.08 | 0.00 | 58.06 | 0.59 | 6.89 | 15.06 | 58.29 | 92.64 | 0.00 | 65.82 | 56.87 | 0.36 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | 28.67 | — | — | 48.10 | 15.60 | 0.00 | — | 0.00 | 12.25 | 4.18 | 36.64 | 0.00 | 59.76 | 0.00 | 20.45 | 31.51 | 74.45 | 92.78 | 0.00 | 66.14 | 53.78 | 0.43 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | 33.63 | — | — | 60.56 | 16.88 | 0.00 | — | 0.00 | 11.16 | 14.45 | 48.61 | 35.26 | 67.82 | 0.00 | 9.62 | 29.31 | 78.18 | 94.86 | 0.00 | 72.60 | 64.36 | 1.72 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 35.78 | — | — | 55.04 | 37.24 | 0.00 | — | 29.28 | 19.52 | 9.84 | 41.95 | 0.10 | 69.39 | 36.41 | 15.84 | 19.89 | 82.36 | 95.70 | 0.00 | 71.65 | 58.39 | 1.44 |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | 38.80 | — | — | 53.44 | 37.82 | 19.00 | — | 34.09 | 3.82 | 15.38 | 47.18 | 12.39 | 69.65 | 48.62 | 10.25 | 18.70 | 84.71 | 96.22 | 8.42 | 72.21 | 64.06 | 2.39 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | 35.18 | — | — | 50.55 | 22.64 | 21.02 | — | 22.63 | 5.26 | 8.10 | 46.33 | 5.76 | 69.57 | 39.45 | 14.26 | 16.46 | 83.00 | 94.23 | 4.54 | 70.04 | 58.90 | 0.44 |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | 43.41 | — | — | 56.55 | 19.49 | 35.46 | — | 34.92 | 5.39 | 13.95 | 53.23 | 33.69 | 72.54 | 52.69 | 13.34 | 30.62 | 80.68 | 97.06 | 35.32 | 72.36 | 62.42 | 11.73 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 40.22 | — | — | 55.93 | 17.17 | 35.86 | — | 38.17 | 8.14 | 16.06 | 56.68 | 22.78 | 72.49 | 47.54 | 5.60 | 15.13 | 79.81 | 96.20 | 18.75 | 73.81 | 61.16 | 2.68 |

## Standardized model-only inference

**FPS**, mean across completed, profiled seeds. Input/evaluation settings, latency and peak VRAM are on the model pages; compare speeds only under compatible settings.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 38.25 | 37.25 | 41.47 | 41.38 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 45.95 | 45.80 | 45.26 | 45.50 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 30.81 | 31.72 | 30.76 | 31.50 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 76.06 | 75.90 | 76.52 | 76.16 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 53.92 | 53.02 | 53.93 | 53.87 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 27.84 | 27.53 | 27.73 | 27.85 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 119.75 | 108.60 | 119.35 | 117.12 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 160.29 | 160.41 | 159.67 | 159.09 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 73.39 | 73.74 | 74.57 | 74.26 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 42.30 | 42.72 | 41.95 | 42.62 |

<details>
<summary>Individual runs: quality, mud precision/recall, steps and status</summary>

Click any model for all initialization paths, full class metrics, training/validation curves, VRAM, timing, config, checkpoint and software provenance. — means unavailable, never zero.

| Model | Initialization path | Seed | Status | Steps | Best step | Mud IoU, pixels pooled (%) | Mud precision, pixels pooled (%) | Mud recall, pixels pooled (%) | Final mud IoU (trainer val, pixels pooled, %) | mIoU, pixels pooled (%) | Fixed GT-class mIoU, pixels pooled (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | completed | 2333 | 1555 | 12.73 | 16.54 | 35.57 | 10.44 | 47.84 | 53.16 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | completed | 3370 | 2074 | 9.40 | 12.31 | 28.47 | 9.09 | 53.42 | 56.38 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | completed | 2074 | 777 | 3.33 | 4.46 | 11.57 | 3.14 | 49.72 | 58.01 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2074 | 777 | 15.70 | 20.78 | 39.08 | 15.42 | 55.15 | 58.22 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | completed | 3111 | 3111 | 8.67 | 9.77 | 43.52 | 8.67 | 43.80 | 48.67 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | completed | 3370 | 2074 | 10.58 | 11.98 | 47.54 | 10.49 | 46.27 | 51.42 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3888 | 18.84 | 26.76 | 38.89 | 18.87 | 49.96 | 58.28 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2074 | 777 | 8.22 | 16.68 | 13.94 | 4.84 | 44.82 | 52.29 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | completed | 2333 | 1037 | 5.19 | 7.12 | 16.14 | 1.06 | 35.71 | 41.66 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2851 | 4.69 | 5.27 | 29.88 | 4.44 | 39.76 | 44.18 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 2851 | 5.60 | 8.07 | 15.44 | 4.25 | 46.16 | 53.85 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2851 | 5.02 | 5.79 | 27.37 | 4.85 | 45.26 | 50.29 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | completed | 1814 | 1814 | 3.60 | 6.36 | 7.66 | 3.61 | 31.91 | 37.23 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | completed | 3370 | 2074 | 12.02 | 81.61 | 12.36 | 7.15 | 34.37 | 40.10 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | completed | 3888 | 2592 | 2.40 | 3.20 | 8.76 | 0.82 | 46.15 | 51.28 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2851 | 1555 | 6.51 | 80.38 | 6.62 | 4.49 | 44.68 | 49.65 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | completed | 3370 | 2074 | 10.08 | 16.06 | 21.30 | 6.72 | 34.14 | 39.83 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3629 | 16.81 | 33.45 | 25.25 | 12.88 | 38.62 | 45.05 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | completed | 3629 | 2333 | 6.09 | 9.81 | 13.85 | 3.93 | 45.16 | 52.69 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3888 | 2592 | 15.88 | 58.38 | 17.91 | 15.24 | 42.83 | 47.59 |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | completed | 3111 | 1814 | 4.68 | 6.98 | 12.44 | 1.31 | 36.12 | 42.14 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | completed | 2333 | 1037 | 3.21 | 3.71 | 19.08 | 2.21 | 31.04 | 36.21 |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | completed | 3629 | 2333 | 7.82 | 14.34 | 14.68 | 2.69 | 42.36 | 49.42 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2333 | 1037 | 2.44 | 3.63 | 6.88 | 0.99 | 37.88 | 44.19 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | completed | 2592 | 1296 | 6.62 | 9.14 | 19.42 | 2.70 | 25.88 | 30.19 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | completed | 1555 | 259 | 1.38 | 1.70 | 6.79 | 1.21 | 22.34 | 23.58 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | completed | 2074 | 777 | 5.65 | 7.84 | 16.77 | 2.11 | 44.32 | 49.24 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2592 | 1296 | 3.72 | 6.02 | 8.90 | 2.51 | 36.83 | 40.92 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | completed | 1555 | 259 | 4.80 | 7.36 | 12.11 | 1.15 | 20.13 | 22.37 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | completed | 2592 | 1296 | 8.24 | 31.75 | 10.01 | 3.59 | 28.95 | 32.17 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | completed | 2074 | 777 | 12.82 | 24.34 | 21.32 | 7.52 | 41.83 | 48.80 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2074 | 777 | 14.43 | 51.44 | 16.70 | 13.01 | 35.26 | 41.14 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | completed | 1555 | 259 | 6.81 | 26.48 | 8.40 | 1.14 | 21.93 | 25.58 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | completed | 1814 | 518 | 16.34 | 26.53 | 29.84 | 7.38 | 22.37 | 26.09 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | completed | 1814 | 518 | 8.67 | 19.81 | 13.36 | 4.27 | 30.14 | 35.16 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1814 | 518 | 15.90 | 41.34 | 20.53 | 7.06 | 31.95 | 37.27 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | completed | 1555 | 259 | 6.90 | 12.50 | 13.35 | 3.02 | 27.69 | 29.22 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | completed | 2074 | 777 | 3.11 | 12.24 | 4.01 | 1.94 | 35.19 | 41.06 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | completed | 2333 | 1037 | 2.07 | 3.14 | 5.73 | 1.73 | 42.40 | 49.46 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2851 | 1555 | 9.08 | 23.99 | 12.75 | 8.16 | 41.99 | 48.98 |

</details>

## Training specification and interpretation

This campaign selects checkpoints and early-stops by **mud-pumping validation IoU**. The Quality and Mud-pumping tables above describe that same selected checkpoint, counting each class only on the images that contain it; the selection itself used the mud IoU with pixels pooled over all validation images, shown in the per-run table. Pooled mIoU there averages classes with nonzero union; fixed GT-class means, mud precision/recall and raw/EMA diagnostics remain on model pages. Seed SD describes optimization variability, not independent-recording uncertainty.

`rtis_only` uses each recipe default pretrained initializer, which can include a segmentation checkpoint (EoMT: COCO panoptic; BEiT: ADE20K), not just backbone weights. Other paths load historical Cityscapes/RailSem19 endpoints and reset classifiers. Exact resolved settings are on model pages.

Validation approximately every 250 optimizer steps; stop after five checks without a 0.1 percentage-point mud-IoU improvement. At most 4,000 steps. Keep mud-selected and final full-state checkpoints; remove periodic snapshots only after complete verified collection.

Frozen training code: `d864b72bd90706260965bb1a48398d01167b6d5c`. Split SHA-256: `12d7b367c72cda61d57686ff2ac28223530d0af49debd9fb7a0fbc68b908bc93`.

## Training cost

<details>
<summary>Per-run training and evaluation memory and time</summary>

| Model | Initialization | Seed | Train peak GiB (retained invocation) | Eval peak GiB | Train seconds (retained invocation) | Eval seconds |
| --- | --- | --- | --- | --- | --- | --- |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | 17.70 | 10.80 | 3385.28 | 21.18 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | 17.70 | 10.80 | 4919.84 | 21.50 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | 17.70 | 10.80 | 2997.82 | 21.96 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.70 | 10.80 | 3095.80 | 20.96 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | 17.84 | 10.77 | 4813.20 | 21.85 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | 17.84 | 10.77 | 5104.50 | 22.01 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | 17.84 | 10.77 | 6167.97 | 21.68 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.84 | 10.77 | 3092.47 | 21.77 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | 16.31 | 7.78 | 3597.05 | 28.26 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | 16.31 | 7.78 | 6146.35 | 28.35 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | 16.31 | 7.78 | 6155.42 | 28.14 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 16.31 | 7.78 | 6165.00 | 28.79 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | 17.35 | 7.58 | 3056.72 | 18.23 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | 17.35 | 7.58 | 5591.50 | 18.36 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | 17.35 | 7.58 | 6451.88 | 18.38 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.35 | 7.58 | 4789.25 | 18.12 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | 11.73 | 7.46 | 3182.22 | 22.20 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | 11.73 | 7.46 | 3782.83 | 22.14 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | 11.73 | 7.46 | 3436.40 | 22.15 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.73 | 7.46 | 3664.52 | 22.12 |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | 13.46 | 7.68 | 4318.36 | 21.53 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | 13.46 | 7.68 | 3215.02 | 21.85 |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | 13.46 | 7.68 | 5022.16 | 21.85 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 13.46 | 7.68 | 3224.56 | 21.52 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | 10.08 | 7.19 | 1878.69 | 11.52 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | 10.08 | 7.19 | 1134.60 | 11.47 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | 10.08 | 7.19 | 1509.05 | 11.28 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.08 | 7.19 | 1872.06 | 11.14 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | 8.69 | 7.01 | 955.05 | 11.22 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | 8.69 | 7.01 | 1589.89 | 11.18 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | 8.69 | 7.01 | 1243.60 | 11.26 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.69 | 7.01 | 1247.20 | 11.14 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | 11.09 | 7.69 | 1318.68 | 15.91 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | 11.09 | 7.69 | 1541.44 | 15.56 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | 11.09 | 7.69 | 1525.88 | 15.46 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.09 | 7.69 | 1529.88 | 15.94 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | 10.20 | 7.42 | 1271.32 | 16.08 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | 10.20 | 7.42 | 1696.85 | 15.57 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | 10.20 | 7.42 | 1894.96 | 15.21 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.20 | 7.42 | 2307.25 | 15.12 |

</details>

Resumed invocation resource measurements are not cumulative training cost. Standardized FPS/latency and parameter memory are separate profiling evidence; missing evidence is explicit on each model page. The report publisher does not modify frozen training jobs or historical Cityscapes/RailSem19 reports.
