# RAD 9/24: can segmentation models find mud-pumping in rail scenes they have not seen?

## What we tested

- **Data:** Paul Stanik's `rad_9_24_2026` set: 314 rail images labelled with 21 classes, including mud-pumping (the track defect we look for).
- **Question:** how well do models find mud-pumping in scenes (videos) they did *not* see in training? We score mud-pumping IoU (overlap of predicted and true mud-pumping pixels, in percent; 100 = perfect) on each validation image that contains mud-pumping and average it over those images: all of them, and the train-camera ones (a forward view from a camera on the train, the real use case).
- **Three ways to split the images into training and validation:** (a) Paul's split, random by image, so frames of one video can be on both sides; (b) a scene-grouped split that keeps whole scenes on one side; (c) 5-fold cross-validation over scenes, where every scene is scored once by a model that never trained on it (the most reliable).
- **Models:** 10 segmentation models, each from 4 starting points (pretraining before training on these images). Test images are never used.

## Key result

Paul's split looks good (median 59.7 on all images with mud-pumping, 44.6 on train-camera ones) because every validation scene of that split also has images in training; 5 of its 13 validation images with mud-pumping come from one scene, `trackside-maintenance`. On scenes the models never trained on, mud-pumping IoU on train-camera images is median 12.3 (best 41.4) with the scene-grouped split and median 24.1 (best 33.0) in cross-validation.

| Split | Model runs | Mud-pumping IoU, all images with mud | Mud-pumping IoU, train-camera images with mud | mIoU (each class over images that contain it) |
| --- | --- | --- | --- | --- |
| Paul's split | 40 | median 59.7 (best 69.3) | median 44.6 (best 60.0) | median 53.1 (best 64.4) |
| Scene-grouped split | 40 | median 12.0 (best 39.2) | median 12.3 (best 41.4) | median 40.0 (best 55.6) |
| Cross-validation over scenes | 20 of 20 with all folds done | median 15.3 (best 19.2) | median 24.1 (best 33.0) | median 51.8 (best 59.3) |

Median and best over every finished model and starting point of each split. mIoU scores each class on the images that contain it, then averages over the classes.

## Results by split

Each table shows every model with its best starting point, picked by train-camera mud-pumping IoU on the same validation images (so slightly flattering). Starting points: recipe pretrained weights, Cityscapes, RailSem19, Cityscapes → RailSem19 (public street and rail datasets). Speed and memory: model-only forward passes on one NVIDIA L40S, batch 1, 1024x1024 input, BF16, without data loading or pre-processing.

### Paul's split

Images assigned to training and validation at random, balanced by class; 17 of its 17 validation scenes also have images in training (227 training, 37 validation images). [Every model and starting point](paul/README.md); [IoU of every class](paul/README.md#per-class-iou).

| Model | Best starting point | Mud-pumping IoU, train-camera images with mud | Mud-pumping IoU, all images with mud | mIoU (each class over images that contain it) | Speed (FPS) | GPU memory, total (GB) | Parameters (M) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [segformer_b5](paul/models/segformer_b5/README.md) | Cityscapes → RailSem19 | 60.0 | 68.4 | 54.7 | 27.6 | 2.76† | 84.6 |
| [segformer_b2](paul/models/segformer_b2/README.md) | recipe pretrained weights | 59.2 | 68.8 | 52.0 | 53.3 | 2.42† | 27.4 |
| [eomt_dinov3_large](paul/models/eomt_dinov3_large/README.md) | RailSem19 | 53.3 | 65.4 | 64.0 | 37.8 | 3.36† | 314.9 |
| [native_convnext_tiny_uper](paul/models/native_convnext_tiny_uper/README.md) | recipe pretrained weights | 53.3 | 64.9 | 51.1 | 76.1 | 1.34† | 36.8 |
| [eomt_large](paul/models/eomt_large/README.md) | Cityscapes → RailSem19 | 51.9 | 65.6 | 64.2 | 45.5 | 3.35† | 316.6 |
| [smp_upernet_resnet101](paul/models/smp_upernet_resnet101/README.md) | recipe pretrained weights | 51.0 | 63.4 | 49.0 | 73.9 | 1.55† | 56.3 |
| [upernet_convnext](paul/models/upernet_convnext/README.md) | recipe pretrained weights | 50.9 | 64.5 | 54.5 | 42.5 | 2.66† | 80.9 |
| [smp_deeplabv3plus_resnet101](paul/models/smp_deeplabv3plus_resnet101/README.md) | Cityscapes → RailSem19 | 47.2 | 65.3 | 50.7 | 119.5 | 0.70† | 45.7 |
| [hrnet_w48_ocr](paul/models/hrnet_w48_ocr/README.md) | recipe pretrained weights | 45.7 | 61.1 | 53.1 | 31.3 | 1.35† | 73.2 |
| [smp_fpn_resnet50](paul/models/smp_fpn_resnet50/README.md) | RailSem19 | 43.3 | 59.2 | 53.1 | 159.1 | 0.78† | 26.1 |

† Allocator only (PyTorch peak reserved memory in the speed benchmark): excludes the CUDA context (driver overhead, a few hundred MB).

### Scene-grouped split

Whole scenes kept on one side; 0 of its 3 validation scenes have images in training (217 training, 37 validation images). [Every model and starting point](fixed-grouped/README.md); [IoU of every class](fixed-grouped/README.md#per-class-iou).

| Model | Best starting point | Mud-pumping IoU, train-camera images with mud | Mud-pumping IoU, all images with mud | mIoU (each class over images that contain it) | Speed (FPS) | GPU memory, total (GB) | Parameters (M) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](fixed-grouped/models/eomt_dinov3_large/README.md) | Cityscapes | 41.4 | 39.2 | 49.7 | 37.3 | 3.36† | 314.9 |
| [eomt_large](fixed-grouped/models/eomt_large/README.md) | Cityscapes → RailSem19 | 36.5 | 34.9 | 52.5 | 45.5 | 3.35† | 316.6 |
| [segformer_b2](fixed-grouped/models/segformer_b2/README.md) | Cityscapes | 23.1 | 22.2 | 38.5 | 53.0 | 2.42† | 27.4 |
| [segformer_b5](fixed-grouped/models/segformer_b5/README.md) | Cityscapes | 22.8 | 21.6 | 39.8 | 27.5 | 2.76† | 84.6 |
| [smp_upernet_resnet101](fixed-grouped/models/smp_upernet_resnet101/README.md) | Cityscapes | 21.5 | 20.5 | 28.7 | 73.7 | 1.65† | 56.3 |
| [smp_fpn_resnet50](fixed-grouped/models/smp_fpn_resnet50/README.md) | RailSem19 | 16.2 | 15.5 | 43.4 | 159.7 | 0.78† | 26.1 |
| [smp_deeplabv3plus_resnet101](fixed-grouped/models/smp_deeplabv3plus_resnet101/README.md) | recipe pretrained weights | 15.6 | 15.3 | 30.6 | 119.7 | 0.70† | 45.7 |
| [upernet_convnext](fixed-grouped/models/upernet_convnext/README.md) | Cityscapes | 15.0 | 14.3 | 35.2 | 42.7 | 2.66† | 80.9 |
| [native_convnext_tiny_uper](fixed-grouped/models/native_convnext_tiny_uper/README.md) | recipe pretrained weights | 11.7 | 11.1 | 28.8 | 76.1 | 1.34† | 36.8 |
| [hrnet_w48_ocr](fixed-grouped/models/hrnet_w48_ocr/README.md) | Cityscapes | 8.4 | 8.1 | 35.5 | 31.7 | 1.35† | 73.2 |

† Allocator only (PyTorch peak reserved memory in the speed benchmark): excludes the CUDA context (driver overhead, a few hundred MB).

### Cross-validation over scenes

The scenes of the scene-grouped data are divided into 5 folds; each model trains on 4 folds and is scored on the remaining one, so every image is scored once by a model that never saw its scene. The result is the final checkpoint, so nothing is picked on the scored images. 100 of 100 runs done; `*` = not all folds done yet. [Full report](cross-validation/README.md); [IoU of every class](cross-validation/README.md#per-class-iou).

| Model | Best starting point | Mud-pumping IoU, train-camera images with mud | Mud-pumping IoU, all images with mud | mIoU (each class over images that contain it) | Speed (FPS) | GPU memory, total (GB) | Parameters (M) | Folds done |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eomt_dinov3_large | recipe pretrained weights | 33.0 | 19.2 | 57.3 | 39.3 | 3.36† | 314.9 | 5/5 |
| segformer_b5 | Cityscapes | 29.7 | 17.4 | 46.3 | 27.0 | 2.76† | 84.6 | 5/5 |
| eomt_large | Cityscapes → RailSem19 | 29.6 | 17.2 | 58.1 | 45.4 | 3.35† | 316.6 | 5/5 |
| segformer_b2 | recipe pretrained weights | 29.4 | 18.3 | 45.2 | 52.4 | 2.42† | 27.4 | 5/5 |
| smp_upernet_resnet101 | recipe pretrained weights | 21.3 | 18.1 | 41.9 | 72.5 | 1.65† | 56.3 | 5/5 |

† Allocator only (PyTorch peak reserved memory in the speed benchmark): excludes the CUDA context (driver overhead, a few hundred MB).

## Paul's paper model

Paul's own recipes, retrained by us with his code on each split and scored with the same code as above. Paul's finished model is never scored here: it may have trained on our validation images.

| Paul's recipe, retrained by us | Split | Mud-pumping IoU, train-camera images with mud | Mud-pumping IoU, all images with mud | mIoU (each class over images that contain it) |
| --- | --- | --- | --- | --- |
| HRNet-OCR, Paul's RailSem19 checkpoint | Paul's split | 52.4 | 63.7 | 60.3 |
| HRNet-OCR, Paul's RailSem19 checkpoint | Scene-grouped split | 16.2 | 15.4 | 46.0 |

## Caveats

- One training run per model and starting point (seed 0): differences of a few points are not established.
- Images without mud-pumping are not counted, so mud predicted on clean track does not lower the mud-pumping IoU.
- Paul's split and the scene-grouped split report the checkpoint that scored best on the same validation images (flattering), and that checkpoint was still selected on the older mud-pumping IoU with pixels pooled over all validation images (training is unchanged); cross-validation reports the final checkpoint.
- Few train-camera validation images have mud-pumping: Paul's split 7, the scene-grouped split 17 (all from one scene, `rural-overcast-cab-view`).
- In cross-validation, fold 2 holds 48 of the 68 scored train-camera images with mud-pumping, all from one scene (`sunny-mainline-cab-view`), so the train-camera numbers mostly measure that scene.
- Paul's split and the scene-grouped split also differ in labels (Paul's masks vs our re-render); scenes are grouped by eye, not from recording records.

## Details

- [Paul's split: every model and starting point](paul/README.md)
- [Scene-grouped split: every model and starting point](fixed-grouped/README.md)
- [Cross-validation report](cross-validation/README.md) and its [CSV](cross-validation/cv-report.csv)
- [Why Paul's split looks so good (case document)](../../guides/rad-9-24-2026-mud-iou-case.md)
- [Full details](details.md): label defects in the delivered masks, all comparison tables, every retraining run of Paul's recipes, provenance
- [Comparison CSV](rad-comparison.csv)
- [Dataset preparation and split decisions](../../guides/rad-9-24-2026.md)
- Generated by `scripts/publish_rad_results.py` (code `ac2501a83780`) from the HDRFS records, which it only reads; records last changed 2026-10-05 09:27 PM PDT.
