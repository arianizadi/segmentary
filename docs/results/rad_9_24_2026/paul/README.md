# RAD 9/24: Paul's split (`paul`)

Every model and starting point trained on Paul's split (labels: Paul's delivered `masks_machine` copies; split: stratified random (seed 0)). Every model on this page was trained by us. The tables keep the shared RTIS report's names: an *initialization path* is the starting point (pretraining before training on these images): `rtis_only` = recipe pretrained weights, `cityscapes_to_rtis` = Cityscapes, `railsem19_to_rtis` = RailSem19, `cityscapes_to_railsem19_to_rtis` = Cityscapes → RailSem19. Mud IoU here is on all validation images; the [study page](../README.md) adds train-camera images (a forward view from a camera on the train, the real use case).

**40/40 completed · 0 failed**

Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling.

[RAD 9/24 study](../README.md) · [CSV results](results.csv) · [Full machine records](status.json)

10 models; four initialization paths; seeds [0]. Train/val/test: 227/37/50 images. Test is held out. Split grouping status: `none_stratified_random_per_paul_stanik_2026-09-23_same_recording_frames_may_cross_splits`. Seed variation does not establish independent-recording generalization.

## Quality

Validation **mIoU (%)** across classes. Cells show the mean over completed seeds. Per-seed values are retained on model pages and in machine records. Partial groups are provisional; — means unavailable. These are the existing selected-checkpoint evaluations, not newly selected mIoU-best checkpoints. Raw/EMA settings are recorded on each model page.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 68.28 | 65.86 | 70.63 | 70.22 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 70.34 | 70.96 | 72.83 | 72.23 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 59.83 | 56.91 | 61.08 | 55.44 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 60.47 | 60.45 | 64.07 | 64.19 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 58.23 | 54.16 | 66.39 | 64.37 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 59.13 | 59.12 | 69.54 | 65.09 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 41.30 | 55.72 | 62.36 | 56.87 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 52.46 | 55.53 | 60.28 | 56.97 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 54.81 | 49.42 | 57.42 | 55.50 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 61.49 | 62.64 | 66.09 | 67.21 |

## Mud-pumping

Validation **mud-pumping IoU (%)** for the same checkpoints. Precision, recall, per-class scores and examples are on each model page and in the CSV.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 90.84 | 85.79 | 89.87 | 89.07 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 92.45 | 92.67 | 94.97 | 93.50 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 90.85 | 85.83 | 76.66 | 75.49 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 4/4 | 88.84 | 89.42 | 88.43 | 90.47 |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 93.13 | 87.30 | 93.22 | 89.21 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 93.08 | 91.35 | 90.39 | 91.25 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 85.86 | 89.63 | 87.68 | 85.44 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 89.18 | 85.25 | 89.90 | 74.01 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 87.53 | 85.16 | 86.04 | 87.65 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 91.65 | 89.16 | 88.32 | 92.59 |

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

| Model | Initialization path | Seed | Status | Steps | Best step | Mud IoU (%) | Mud precision (%) | Mud recall (%) | Final mud IoU (trainer val, %) | mIoU (%) | Fixed GT-class mIoU (%) |
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

This campaign selects checkpoints and early-stops by **mud-pumping validation IoU**. Both overall mIoU and mud IoU above describe that same selected checkpoint. This report layout does not change the training objective or selection policy. mIoU averages classes with nonzero union; fixed GT-class means, mud precision/recall and raw/EMA diagnostics remain on model pages. Seed SD describes optimization variability, not independent-recording uncertainty.

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
