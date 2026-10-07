# RAD 9/24: Paul's split (`paul`)

Every model and starting point trained on Paul's split (labels: Paul's delivered `masks_machine` copies; split: stratified random (seed 0)). Every model on this page was trained by us. The tables keep the shared RTIS report's names: an *initialization path* is the starting point (pretraining before training on these images): `rtis_only` = recipe pretrained weights, `cityscapes_to_rtis` = Cityscapes, `railsem19_to_rtis` = RailSem19, `cityscapes_to_railsem19_to_rtis` = Cityscapes → RailSem19. The Quality, Mud-pumping and [Per-class IoU](#per-class-iou) tables count each class only on the validation images that contain it; the per-run table, `results.csv` and the model pages also keep the campaign's own pixel-pooled numbers, which selected the checkpoints. The [study page](../README.md) compares the splits.

**40/40 completed · 0 failed**

Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling.

[RAD 9/24 study](../README.md) · [CSV results](results.csv) · [Full machine records](status.json)

10 models; four initialization paths; seeds [0]. Train/val/test: 227/37/50 images. Test is held out. Split grouping status: `none_stratified_random_per_paul_stanik_2026-09-23_same_recording_frames_may_cross_splits`. Seed variation does not establish independent-recording generalization.

## Quality

Validation **mIoU (%)**: each class's IoU averaged over the validation images that contain it, then over the classes present. Cells show the mean over completed seeds; — means unavailable. Raw/EMA settings are recorded on each model page.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 59.84 | 56.70 | 64.02 | 62.32 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 62.52 | 61.65 | 64.40 | 64.19 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 53.10 | 47.96 | 55.72 | 51.21 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 51.08 | 51.99 | 56.78 | 57.00 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 52.05 | 42.86 | 56.23 | 52.36 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 53.09 | 50.77 | 58.78 | 54.73 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 34.99 | 47.95 | 54.58 | 50.70 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 43.69 | 46.33 | 53.08 | 49.36 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 48.99 | 41.74 | 52.48 | 49.83 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 54.52 | 53.59 | 57.20 | 56.86 |

## Mud-pumping

Validation **mud-pumping IoU (%)** for the same checkpoints, averaged over the validation images with mud-pumping (images without it are not counted). Precision, recall and examples are on each model page.

All images with mud (n=13):

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 63.35 | 57.08 | 65.39 | 63.93 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 64.81 | 64.54 | 64.25 | 65.55 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 61.07 | 56.87 | 53.96 | 55.78 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 64.94 | 59.90 | 58.96 | 59.57 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 68.76 | 51.49 | 64.70 | 63.08 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 69.33 | 64.59 | 63.29 | 68.40 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 43.89 | 56.65 | 54.88 | 65.35 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 53.92 | 42.11 | 59.20 | 50.12 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 63.41 | 48.86 | 56.03 | 54.64 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 64.48 | 59.49 | 56.17 | 57.94 |

Train-camera images with mud (n=7):

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 49.18 | 37.15 | 53.34 | 48.03 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 51.27 | 50.45 | 49.35 | 51.85 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 45.67 | 39.93 | 42.42 | 45.50 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 53.28 | 43.57 | 43.70 | 43.16 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 59.16 | 30.17 | 51.60 | 49.87 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 60.00 | 51.87 | 50.58 | 60.04 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 16.61 | 38.17 | 36.30 | 47.24 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 31.27 | 14.03 | 43.33 | 34.29 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 51.04 | 25.03 | 38.40 | 32.98 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 50.94 | 42.23 | 36.18 | 38.37 |

## Per-class IoU

Validation IoU (%) of every class, each averaged only over the validation images that contain the class (n = those images); — = no image contains it. mIoU averages the classes with at least one such image.

| Model | Initialization path | Seed | mIoU (each class over images that contain it) | person (n=12) | truck (n=5) | rail-track (n=31) | vegetation-overgrowth (n=14) | car (n=6) | on-rails (n=6) | traffic-sign (n=10) | road (n=12) | sidewalk (n=16) | construction (n=26) | tram-track (n=5) | pole (n=25) | traffic-light (n=8) | mud-pumping (n=13) | fence (n=17) | terrain (n=34) | sky (n=28) | rail-embedded (n=5) | rail-raised (n=36) | trackbed (n=32) | standing-water (n=6) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | 59.84 | 26.79 | 41.38 | 78.88 | 47.64 | 63.45 | 85.48 | 24.72 | 55.64 | 65.22 | 60.20 | 40.85 | 58.19 | 57.93 | 63.35 | 66.64 | 88.20 | 97.09 | 33.28 | 74.26 | 83.16 | 44.39 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | 56.70 | 26.66 | 52.67 | 75.98 | 48.24 | 65.21 | 70.86 | 34.26 | 56.32 | 63.96 | 62.16 | 26.90 | 61.09 | 51.51 | 57.08 | 64.50 | 88.95 | 96.74 | 0.40 | 71.69 | 82.02 | 33.50 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | 64.02 | 26.20 | 34.17 | 80.33 | 50.92 | 68.53 | 89.41 | 44.45 | 60.80 | 68.91 | 60.32 | 64.43 | 61.81 | 53.89 | 65.39 | 68.20 | 88.10 | 97.11 | 56.29 | 78.39 | 81.91 | 44.94 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 62.32 | 26.37 | 53.20 | 79.43 | 49.41 | 65.25 | 76.61 | 48.48 | 68.57 | 67.54 | 62.65 | 31.85 | 62.74 | 56.19 | 63.93 | 66.46 | 88.10 | 97.06 | 50.95 | 76.84 | 82.25 | 34.79 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | 62.52 | 25.33 | 38.81 | 78.06 | 52.34 | 64.02 | 88.47 | 41.93 | 69.14 | 69.54 | 63.37 | 40.33 | 59.42 | 61.28 | 64.81 | 67.05 | 87.49 | 97.16 | 42.88 | 75.11 | 82.38 | 43.99 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | 61.65 | 26.68 | 48.54 | 77.50 | 50.27 | 66.59 | 73.55 | 50.15 | 64.29 | 62.77 | 62.52 | 48.56 | 63.47 | 57.70 | 64.54 | 66.08 | 87.82 | 97.06 | 34.46 | 74.60 | 81.87 | 35.70 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | 64.40 | 25.67 | 44.53 | 78.65 | 50.38 | 66.46 | 77.38 | 50.48 | 64.51 | 66.54 | 59.09 | 67.82 | 61.94 | 61.23 | 64.25 | 65.69 | 86.81 | 97.08 | 60.57 | 78.48 | 82.19 | 42.62 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 64.19 | 25.85 | 44.62 | 77.61 | 50.21 | 69.08 | 78.28 | 55.44 | 66.20 | 67.60 | 60.77 | 53.94 | 63.40 | 59.52 | 65.55 | 68.38 | 87.80 | 97.20 | 58.57 | 76.55 | 82.33 | 39.10 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | 53.10 | 17.41 | 2.79 | 75.52 | 51.61 | 32.30 | 70.00 | 24.62 | 51.16 | 54.96 | 49.69 | 68.52 | 60.20 | 31.89 | 61.07 | 41.31 | 85.71 | 97.07 | 63.95 | 74.53 | 79.42 | 21.45 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | 47.96 | 21.70 | 20.37 | 67.58 | 39.56 | 39.37 | 51.06 | 26.33 | 32.33 | 50.79 | 48.09 | 33.20 | 59.46 | 39.87 | 56.87 | 44.73 | 80.76 | 94.61 | 32.53 | 71.04 | 73.36 | 23.52 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | 55.72 | 22.79 | 28.22 | 74.08 | 37.30 | 57.11 | 59.42 | 24.03 | 48.58 | 58.56 | 56.09 | 79.30 | 57.72 | 46.25 | 53.96 | 51.89 | 80.94 | 96.83 | 58.33 | 73.61 | 79.58 | 25.52 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 51.21 | 22.91 | 26.75 | 69.86 | 41.64 | 40.01 | 58.66 | 35.60 | 51.07 | 46.45 | 50.08 | 55.43 | 60.17 | 35.60 | 55.78 | 52.56 | 79.59 | 96.52 | 47.63 | 68.98 | 76.37 | 3.82 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | 51.08 | 18.33 | 9.43 | 73.82 | 49.94 | 32.15 | 73.60 | 18.21 | 47.86 | 51.59 | 51.25 | 45.86 | 57.42 | 19.89 | 64.94 | 47.26 | 85.81 | 96.90 | 47.46 | 71.83 | 79.95 | 29.23 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | 51.99 | 21.70 | 23.75 | 72.16 | 47.20 | 43.03 | 75.71 | 32.78 | 47.61 | 48.19 | 48.93 | 32.13 | 60.50 | 29.05 | 59.90 | 49.11 | 85.05 | 97.02 | 44.01 | 72.20 | 75.34 | 26.42 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | 56.78 | 19.73 | 32.08 | 76.06 | 49.06 | 49.62 | 79.51 | 25.80 | 50.10 | 56.04 | 57.31 | 67.89 | 60.66 | 30.49 | 58.96 | 57.71 | 87.10 | 97.39 | 56.64 | 75.64 | 80.01 | 24.63 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 57.00 | 22.80 | 27.79 | 75.45 | 47.59 | 56.11 | 80.20 | 41.15 | 49.26 | 53.84 | 54.25 | 53.66 | 61.48 | 39.56 | 59.57 | 55.03 | 86.14 | 97.17 | 51.49 | 72.99 | 79.48 | 32.06 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | 52.05 | 18.82 | 9.10 | 74.84 | 48.13 | 50.68 | 68.23 | 18.93 | 38.36 | 54.18 | 50.60 | 44.54 | 58.39 | 24.24 | 68.76 | 44.91 | 84.30 | 97.01 | 47.48 | 72.87 | 80.98 | 37.69 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | 42.86 | 20.55 | 13.07 | 55.34 | 27.42 | 40.53 | 49.08 | 21.36 | 47.21 | 44.98 | 47.64 | 22.26 | 53.73 | 10.33 | 51.49 | 40.16 | 79.17 | 95.94 | 21.60 | 67.01 | 64.77 | 26.43 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | 56.23 | 21.37 | 18.18 | 74.06 | 45.66 | 55.17 | 69.37 | 24.28 | 48.68 | 54.51 | 54.70 | 66.25 | 61.99 | 29.33 | 64.70 | 58.93 | 84.42 | 97.19 | 61.90 | 73.90 | 80.67 | 35.60 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 52.36 | 21.13 | 19.93 | 74.65 | 40.78 | 45.53 | 50.07 | 27.37 | 43.62 | 53.92 | 51.98 | 49.25 | 60.33 | 28.01 | 63.08 | 57.63 | 84.42 | 96.95 | 42.17 | 74.07 | 79.61 | 35.07 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | 53.09 | 18.88 | 15.90 | 75.05 | 55.00 | 44.01 | 74.96 | 29.95 | 52.33 | 50.36 | 53.89 | 41.77 | 57.23 | 18.27 | 69.33 | 40.32 | 85.83 | 97.03 | 54.33 | 74.98 | 79.08 | 26.30 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | 50.77 | 22.24 | 9.16 | 70.52 | 43.02 | 58.36 | 66.72 | 29.04 | 32.91 | 52.64 | 48.69 | 32.92 | 59.00 | 19.71 | 64.59 | 54.99 | 84.58 | 96.97 | 51.56 | 72.14 | 76.76 | 19.64 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | 58.78 | 20.71 | 30.08 | 76.73 | 44.16 | 57.57 | 80.46 | 25.44 | 63.68 | 58.97 | 61.88 | 72.12 | 60.50 | 32.65 | 63.29 | 61.02 | 86.44 | 97.25 | 58.28 | 73.52 | 80.76 | 28.91 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 54.73 | 22.28 | 20.93 | 76.91 | 43.42 | 58.44 | 67.35 | 26.17 | 36.72 | 54.35 | 53.65 | 58.77 | 61.13 | 23.93 | 68.40 | 60.42 | 87.49 | 97.18 | 53.33 | 73.79 | 81.17 | 23.57 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | 34.99 | 9.33 | 2.32 | 62.94 | 36.68 | 3.94 | 62.49 | 0.00 | 33.45 | 32.16 | 36.50 | 33.30 | 32.43 | 0.00 | 43.89 | 26.25 | 72.67 | 94.35 | 0.00 | 61.35 | 68.96 | 21.77 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | 47.95 | 17.68 | 14.76 | 68.28 | 39.89 | 40.81 | 63.99 | 17.63 | 43.19 | 44.40 | 48.71 | 51.36 | 53.79 | 17.32 | 56.65 | 40.71 | 83.71 | 96.03 | 44.80 | 68.74 | 74.23 | 20.33 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | 54.58 | 18.86 | 18.29 | 75.11 | 42.46 | 47.78 | 67.59 | 22.78 | 50.32 | 56.33 | 50.47 | 77.57 | 58.97 | 34.40 | 54.88 | 54.19 | 85.05 | 96.92 | 65.93 | 73.98 | 80.17 | 14.05 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 50.70 | 18.22 | 25.94 | 71.62 | 36.88 | 49.42 | 73.52 | 33.26 | 32.12 | 48.91 | 48.79 | 45.58 | 58.72 | 28.44 | 65.35 | 47.53 | 84.38 | 96.71 | 43.61 | 70.49 | 76.70 | 8.59 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | 43.69 | 12.00 | 15.14 | 65.03 | 39.53 | 27.49 | 61.24 | 6.18 | 45.26 | 47.39 | 40.05 | 39.64 | 45.45 | 15.73 | 53.92 | 35.35 | 80.80 | 95.37 | 32.40 | 66.71 | 73.66 | 19.17 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | 46.33 | 20.68 | 12.49 | 65.35 | 36.34 | 30.89 | 54.75 | 16.65 | 39.66 | 48.72 | 44.61 | 52.81 | 54.28 | 17.83 | 42.11 | 47.24 | 83.62 | 95.82 | 44.02 | 68.04 | 74.35 | 22.71 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | 53.08 | 19.00 | 6.11 | 74.10 | 43.89 | 51.56 | 70.36 | 19.59 | 44.92 | 58.08 | 50.55 | 60.72 | 58.61 | 26.37 | 59.20 | 52.32 | 81.86 | 96.63 | 64.23 | 72.25 | 77.15 | 27.18 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 49.36 | 21.37 | 9.03 | 71.88 | 38.99 | 30.49 | 58.20 | 23.81 | 46.40 | 53.16 | 49.91 | 56.44 | 58.09 | 24.09 | 50.12 | 51.26 | 84.12 | 96.41 | 52.73 | 69.12 | 76.05 | 14.90 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | 48.99 | 18.49 | 14.26 | 72.60 | 40.67 | 31.24 | 70.61 | 30.89 | 41.20 | 49.87 | 46.15 | 35.29 | 57.46 | 20.81 | 63.41 | 42.40 | 81.60 | 96.53 | 49.37 | 71.44 | 75.75 | 18.86 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | 41.74 | 17.64 | 6.54 | 60.66 | 31.02 | 29.61 | 63.57 | 0.00 | 46.85 | 47.02 | 42.77 | 29.52 | 52.65 | 0.00 | 48.86 | 40.06 | 82.88 | 94.89 | 21.60 | 66.96 | 68.95 | 24.59 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | 52.48 | 19.04 | 15.87 | 73.31 | 44.74 | 48.14 | 55.70 | 31.54 | 42.94 | 51.62 | 47.75 | 74.39 | 56.63 | 29.00 | 56.03 | 50.07 | 82.38 | 96.53 | 61.00 | 70.38 | 77.21 | 17.72 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 49.83 | 17.59 | 15.76 | 73.54 | 42.92 | 43.59 | 58.36 | 32.81 | 51.14 | 52.86 | 46.07 | 51.02 | 56.60 | 27.79 | 54.64 | 41.26 | 83.30 | 96.82 | 37.59 | 71.62 | 74.57 | 16.52 |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | 54.52 | 19.57 | 23.36 | 75.01 | 51.76 | 58.02 | 69.47 | 40.21 | 46.44 | 54.34 | 54.84 | 49.70 | 59.35 | 18.26 | 64.48 | 48.87 | 84.61 | 97.54 | 47.49 | 73.62 | 76.99 | 30.89 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | 53.59 | 22.11 | 26.63 | 72.19 | 48.40 | 52.46 | 78.62 | 37.31 | 41.98 | 52.01 | 49.82 | 37.67 | 61.48 | 31.69 | 59.49 | 45.10 | 85.00 | 97.45 | 45.16 | 73.28 | 76.12 | 31.35 |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | 57.20 | 21.93 | 25.04 | 77.55 | 45.40 | 59.44 | 67.15 | 44.04 | 48.30 | 53.22 | 53.55 | 77.74 | 59.99 | 36.22 | 56.17 | 53.65 | 84.14 | 96.69 | 59.89 | 73.64 | 78.89 | 28.59 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 56.86 | 20.80 | 36.12 | 76.38 | 46.80 | 58.89 | 77.73 | 33.13 | 45.67 | 57.57 | 55.30 | 52.73 | 61.94 | 36.08 | 57.94 | 57.82 | 85.80 | 97.42 | 46.98 | 74.76 | 77.91 | 36.20 |

## Standardized model-only inference

**FPS**, mean across completed, profiled seeds. Input/evaluation settings, latency and peak VRAM are on the model pages; compare speeds only under compatible settings.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 40.82 | 37.93 | 37.84 | 38.35 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 45.09 | 45.87 | 45.76 | 45.47 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 31.33 | 31.97 | 30.50 | 30.52 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 76.06 | 75.54 | 76.28 | 76.23 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 53.30 | 53.44 | 54.25 | 54.11 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 27.28 | 27.73 | 27.47 | 27.60 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 117.36 | 115.85 | 117.75 | 119.53 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 159.79 | 158.64 | 159.13 | 159.40 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 73.86 | 69.69 | 73.86 | 71.93 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 42.55 | 42.43 | 42.56 | 41.99 |

<details>
<summary>Individual runs: quality, mud precision/recall, steps and status</summary>

Click any model for all initialization paths, full class metrics, training/validation curves, VRAM, timing, config, checkpoint and software provenance. — means unavailable, never zero.

| Model | Initialization path | Seed | Status | Steps | Best step | Mud IoU, pixels pooled (%) | Mud precision, pixels pooled (%) | Mud recall, pixels pooled (%) | Final mud IoU (trainer val, pixels pooled, %) | mIoU, pixels pooled (%) | Fixed GT-class mIoU, pixels pooled (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | completed | 3185 | 3185 | 92.45 | 96.68 | 95.49 | 92.46 | 70.34 | 70.34 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | completed | 3451 | 2123 | 92.67 | 96.41 | 95.99 | 92.61 | 70.96 | 70.96 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3981 | 94.97 | 97.83 | 97.02 | 94.98 | 72.83 | 72.83 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 3981 | 93.50 | 97.03 | 96.25 | 93.50 | 72.23 | 72.23 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | completed | 4000 | 3981 | 90.84 | 95.71 | 94.70 | 90.84 | 68.28 | 68.28 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | completed | 2389 | 1061 | 85.79 | 95.07 | 89.78 | 85.45 | 65.86 | 65.86 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | completed | 2919 | 1592 | 89.87 | 94.82 | 94.50 | 89.83 | 70.63 | 70.63 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3451 | 3185 | 89.07 | 94.39 | 94.04 | 89.06 | 70.22 | 70.22 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | completed | 3185 | 1857 | 93.08 | 95.74 | 97.10 | 92.54 | 59.13 | 59.13 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | completed | 3981 | 2919 | 91.35 | 95.44 | 95.51 | 89.86 | 59.12 | 59.12 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | completed | 3185 | 1857 | 90.39 | 94.08 | 95.84 | 89.77 | 69.54 | 69.54 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2919 | 91.25 | 96.50 | 94.37 | 89.81 | 65.09 | 65.09 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | completed | 3716 | 2654 | 90.85 | 96.91 | 93.56 | 88.49 | 59.83 | 59.83 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | completed | 3716 | 2389 | 85.83 | 91.81 | 92.94 | 72.49 | 56.91 | 56.91 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | completed | 2919 | 1592 | 76.66 | 95.66 | 79.43 | 69.22 | 61.08 | 61.08 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2389 | 1061 | 75.49 | 88.69 | 83.52 | 72.01 | 55.44 | 55.44 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | completed | 4000 | 2919 | 93.13 | 96.81 | 96.08 | 92.88 | 58.23 | 58.23 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | completed | 2123 | 796 | 87.30 | 93.26 | 93.18 | 86.68 | 54.16 | 54.16 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 2919 | 93.22 | 96.72 | 96.26 | 92.85 | 66.39 | 66.39 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2919 | 89.21 | 94.69 | 93.91 | 86.79 | 64.37 | 64.37 |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | completed | 3185 | 1857 | 91.65 | 95.95 | 95.35 | 87.17 | 61.49 | 61.49 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3981 | 89.16 | 93.30 | 95.27 | 88.59 | 62.64 | 62.64 |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | completed | 2123 | 796 | 88.32 | 93.25 | 94.36 | 85.33 | 66.09 | 66.09 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3451 | 2123 | 92.59 | 96.44 | 95.87 | 89.90 | 67.21 | 67.21 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | completed | 1857 | 530 | 85.86 | 93.22 | 91.58 | 46.35 | 41.30 | 41.30 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | completed | 3981 | 2654 | 89.63 | 95.62 | 93.47 | 89.00 | 55.72 | 55.72 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3981 | 87.68 | 96.52 | 90.55 | 83.79 | 62.36 | 62.36 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2123 | 1592 | 85.44 | 92.19 | 92.12 | 84.08 | 56.87 | 56.87 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | completed | 2389 | 1061 | 89.18 | 96.01 | 92.61 | 85.42 | 52.46 | 52.46 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | completed | 3716 | 2389 | 85.25 | 97.64 | 87.04 | 79.54 | 55.53 | 55.53 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | completed | 3451 | 2123 | 89.90 | 96.20 | 93.21 | 85.31 | 60.28 | 60.28 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3451 | 2123 | 74.01 | 96.35 | 76.15 | 71.50 | 56.97 | 56.97 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | completed | 4000 | 2919 | 87.53 | 93.30 | 93.40 | 88.47 | 54.81 | 54.81 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | completed | 2123 | 796 | 85.16 | 92.77 | 91.22 | 67.10 | 49.42 | 49.42 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | completed | 2654 | 1327 | 86.04 | 90.73 | 94.33 | 67.97 | 57.42 | 57.42 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2654 | 1327 | 87.65 | 91.57 | 95.34 | 74.91 | 55.50 | 55.50 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | completed | 2389 | 1061 | 88.84 | 93.81 | 94.37 | 85.34 | 60.47 | 60.47 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | completed | 2654 | 1327 | 89.42 | 94.94 | 93.89 | 89.22 | 60.45 | 60.45 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | completed | 2389 | 1061 | 88.43 | 96.93 | 90.98 | 87.23 | 64.07 | 64.07 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2654 | 1327 | 90.47 | 96.62 | 93.43 | 89.73 | 64.19 | 64.19 |

</details>

## Training specification and interpretation

This campaign selects checkpoints and early-stops by **mud-pumping validation IoU**. The Quality and Mud-pumping tables above describe that same selected checkpoint, counting each class only on the images that contain it; the selection itself used the mud IoU with pixels pooled over all validation images, shown in the per-run table. Pooled mIoU there averages classes with nonzero union; fixed GT-class means, mud precision/recall and raw/EMA diagnostics remain on model pages. Seed SD describes optimization variability, not independent-recording uncertainty.

`rtis_only` uses each recipe default pretrained initializer, which can include a segmentation checkpoint (EoMT: COCO panoptic; BEiT: ADE20K), not just backbone weights. Other paths load historical Cityscapes/RailSem19 endpoints and reset classifiers. Exact resolved settings are on model pages.

Validation approximately every 250 optimizer steps; stop after five checks without a 0.1 percentage-point mud-IoU improvement. At most 4,000 steps. Keep mud-selected and final full-state checkpoints; remove periodic snapshots only after complete verified collection.

Frozen training code: `d864b72bd90706260965bb1a48398d01167b6d5c`. Split SHA-256: `b16dbbc7c4aa0c5d6e0fb5a20a27b4f3f8a4f3ce535621ed7c9aeaa6e85adb77`.

## Training cost

<details>
<summary>Per-run training and evaluation memory and time</summary>

| Model | Initialization | Seed | Train peak GiB (retained invocation) | Eval peak GiB | Train seconds (retained invocation) | Eval seconds |
| --- | --- | --- | --- | --- | --- | --- |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | 17.70 | 10.80 | 4671.79 | 21.77 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | 17.70 | 10.80 | 5028.03 | 21.84 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | 17.70 | 10.80 | 6090.89 | 21.28 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.69 | 10.80 | 6013.36 | 21.77 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | 17.84 | 10.77 | 6107.49 | 22.23 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | 17.84 | 10.77 | 3456.63 | 22.21 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | 17.84 | 10.77 | 4237.33 | 22.43 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.84 | 10.80 | 5106.88 | 22.37 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | 16.31 | 7.78 | 4753.70 | 29.53 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | 16.31 | 7.78 | 5944.48 | 29.36 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | 16.31 | 7.78 | 4787.68 | 29.07 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 16.31 | 7.78 | 5986.46 | 29.19 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | 17.35 | 7.91 | 6014.62 | 18.69 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | 17.35 | 7.91 | 6055.95 | 18.91 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | 17.35 | 7.91 | 4748.85 | 18.91 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.35 | 7.91 | 3889.99 | 18.85 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | 11.73 | 7.46 | 3675.50 | 22.42 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | 11.73 | 7.46 | 1968.24 | 22.48 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | 11.73 | 7.46 | 3710.29 | 22.80 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.73 | 7.46 | 3701.10 | 23.05 |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | 13.46 | 8.01 | 4303.65 | 22.05 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | 13.46 | 8.01 | 5391.07 | 22.36 |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | 13.46 | 8.01 | 2876.71 | 22.00 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 13.46 | 8.01 | 4655.61 | 22.00 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | 10.40 | 7.51 | 1312.91 | 11.62 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | 10.40 | 7.51 | 2806.14 | 11.53 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | 10.41 | 7.51 | 2832.16 | 11.26 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.40 | 7.51 | 1521.16 | 11.59 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | 9.01 | 7.34 | 1471.03 | 11.48 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | 9.02 | 7.34 | 2319.00 | 11.33 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | 9.01 | 7.34 | 2126.39 | 11.11 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 9.01 | 7.34 | 2136.45 | 11.47 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | 11.09 | 8.02 | 3306.73 | 16.12 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | 11.08 | 8.02 | 1764.22 | 15.84 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | 11.09 | 8.02 | 2191.53 | 15.68 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.09 | 8.02 | 2181.03 | 15.96 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | 10.20 | 7.75 | 1902.85 | 16.45 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | 10.20 | 7.75 | 2114.99 | 15.90 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | 10.20 | 7.75 | 1895.32 | 15.82 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.20 | 7.75 | 2106.76 | 15.63 |

</details>

Resumed invocation resource measurements are not cumulative training cost. Standardized FPS/latency and parameter memory are separate profiling evidence; missing evidence is explicit on each model page. The report publisher does not modify frozen training jobs or historical Cityscapes/RailSem19 reports.
