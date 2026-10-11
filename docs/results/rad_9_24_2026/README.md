# RAD 9/24: can segmentation models find mud-pumping in rail scenes they have not seen?

## What we tested

- **Data:** Paul Stanik's `rad_9_24_2026` set: 314 rail images labelled with 21 classes, including mud-pumping (the track defect we look for).
- **Question:** how well do models find mud-pumping in scenes (videos) they did *not* see in training? We score mud-pumping IoU (overlap of predicted and true mud-pumping pixels, in percent; 100 = perfect) on each validation image that contains mud-pumping and average it over those images: all of them, and the train-camera ones (a forward view from a camera on the train, the real use case).
- **Three ways to split the images into training and validation:** (a) Paul's split, random by image, so frames of one video can be on both sides; (b) a scene-grouped split that keeps whole scenes on one side; (c) 5-fold cross-validation over scenes, where every scene is scored once by a model that never trained on it (the most reliable).
- **Models:** 41 segmentation models, each from up to 4 starting points (pretraining before training on these images); 5 of them only from recipe pretrained weights. Test images are never used.

## Key result

Paul's split looks good (median 59.7 on all images with mud-pumping, 44.6 on train-camera ones) because every validation scene of that split also has images in training; 5 of its 13 validation images with mud-pumping come from one scene, `trackside-maintenance`. On scenes the models never trained on, mud-pumping IoU on train-camera images is median 4.1 (best 41.7) with the scene-grouped split and median 24.1 (best 33.0) in cross-validation.

| Split | Model runs | Mud-pumping IoU, all images with mud | Mud-pumping IoU, train-camera images with mud | mIoU (each class over images that contain it) |
| --- | --- | --- | --- | --- |
| Paul's split | 40 | median 59.7 (best 69.3) | median 44.6 (best 60.0) | median 53.1 (best 64.4) |
| Scene-grouped split | 141 of 149 done | median 4.1 (best 39.5) | median 4.1 (best 41.7) | median 35.3 (best 55.7) |
| Cross-validation over scenes | 20 of 20 with all folds done | median 15.3 (best 19.2) | median 24.1 (best 33.0) | median 51.8 (best 59.3) |

Median and best over every finished model and starting point of each split. mIoU scores each class on the images that contain it, then averages over the classes.

## Results by split

Each table shows every model with its best starting point, picked by train-camera mud-pumping IoU on the same validation images (so slightly flattering). Starting points: recipe pretrained weights, Cityscapes, RailSem19, Cityscapes → RailSem19 (public street and rail datasets). Speed and memory: model-only forward passes on one NVIDIA L40S, batch 1, 1024x1024 input, BF16, without data loading or pre-processing.

### Paul's split

Images assigned to training and validation at random, balanced by class; 17 of its 17 validation scenes also have images in training (227 training, 37 validation images). 10 models, each at its best-on-validation checkpoint (flattering). [Every model and starting point](paul/README.md); [IoU of every class](paul/README.md#per-class-iou).

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

Whole scenes kept on one side; 0 of its 3 validation scenes have images in training (217 training, 37 validation images). 41 models, each at its final checkpoint after the full training budget, so nothing is picked on the validation images. 141 of 149 runs done; `*` = not all starting points of that model done yet. [Every model and starting point](fixed-grouped/README.md); [IoU of every class](fixed-grouped/README.md#per-class-iou).

| Model | Best starting point | Mud-pumping IoU, train-camera images with mud | Mud-pumping IoU, all images with mud | mIoU (each class over images that contain it) | Speed (FPS) | GPU memory, total (GB) | Parameters (M) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](fixed-grouped/models/eomt_dinov3_large/README.md) | Cityscapes | 41.7 | 39.5 | 51.3 | 41.2 | 3.90 | 314.9 |
| [eomt_large](fixed-grouped/models/eomt_large/README.md) | Cityscapes → RailSem19 | 32.9 | 31.4 | 55.7 | 45.4 | 3.89 | 316.6 |
| [hf_auto_mobilevitv2_deeplabv3](fixed-grouped/models/hf_auto_mobilevitv2_deeplabv3/README.md) | RailSem19 | 29.6 | 28.0 | 37.9 | 83.0 | 0.95 | 13.3 |
| [segformer_b5](fixed-grouped/models/segformer_b5/README.md) | Cityscapes → RailSem19 | 23.8 | 22.6 | 44.8 | 26.2 | 3.29 | 84.6 |
| [segformer_b2](fixed-grouped/models/segformer_b2/README.md) | recipe pretrained weights | 21.5 | 20.5 | 39.5 | 53.6 | 2.96 | 27.4 |
| [smp_upernet_mit_b0](fixed-grouped/models/smp_upernet_mit_b0/README.md) | Cityscapes → RailSem19 | 20.1 | 19.5 | 38.8 | 54.2 | 1.71 | 10.7 |
| [hf_auto_segformer_b0](fixed-grouped/models/hf_auto_segformer_b0/README.md) | recipe pretrained weights | 18.1 | 17.3 | 34.0 | 133.2 | 1.50 | 3.7 |
| [hf_auto_mobilevit_xxs_deeplabv3](fixed-grouped/models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | Cityscapes | 17.3 | 16.4 | 31.2 | 34.7 | 4.09 | 1.9 |
| [smp_unet_resnet34](fixed-grouped/models/smp_unet_resnet34/README.md) | RailSem19 | 16.7 | 15.9 | 39.6 | 145.2 | 1.25 | 24.4 |
| [smp_pan_resnext50](fixed-grouped/models/smp_pan_resnext50/README.md) | RailSem19 | 13.8 | 13.4 | 39.9 | 183.8 | 0.96 | 23.7 |
| [native_convnext_tiny_channelmapper_dpt](fixed-grouped/models/native_convnext_tiny_channelmapper_dpt/README.md) | recipe pretrained weights | 13.4 | 12.7 | 39.7 | 28.9 | 2.63 | 38.2 |
| [smp_linknet_mobilenet_v2](fixed-grouped/models/smp_linknet_mobilenet_v2/README.md) | RailSem19 | 12.6 | 12.0 | 26.9 | 169.7 | 0.87 | 4.3 |
| [hf_auto_mobilenetv2_deeplabv3](fixed-grouped/models/hf_auto_mobilenetv2_deeplabv3/README.md) | Cityscapes → RailSem19 | 12.3 | 11.7 | 30.1 | 173.5 | 1.01 | 2.5 |
| [hf_auto_upernet_swin_tiny](fixed-grouped/models/hf_auto_upernet_swin_tiny/README.md) | recipe pretrained weights | 12.0 | 11.5 | 37.8 | 42.0 | 3.12 | 59.0 |
| [smp_manet_efficientnet_b0](fixed-grouped/models/smp_manet_efficientnet_b0/README.md) | Cityscapes → RailSem19 | 11.1 | 10.6 | 32.6 | 95.5 | 1.15 | 9.1 |
| [smp_fpn_resnet50](fixed-grouped/models/smp_fpn_resnet50/README.md) | RailSem19 | 10.8 | 10.7 | 44.5 | 157.3 | 1.31 | 26.1 |
| [smp_unetplusplus_efficientnet_b0](fixed-grouped/models/smp_unetplusplus_efficientnet_b0/README.md) | Cityscapes → RailSem19 | 10.4 | 10.0 | 31.8 | 70.6 | 1.49 | 6.6 |
| [denseaspp121](fixed-grouped/models/denseaspp121/README.md) | recipe pretrained weights (only starting point) | 10.1 | 9.8 | 37.5 | 99.9 | 0.94 | 8.3 |
| [native_convnext_tiny_uper](fixed-grouped/models/native_convnext_tiny_uper/README.md) | Cityscapes → RailSem19 | 9.5 | 9.5 | 44.1 | 74.3 | 1.87 | 36.8 |
| [native_mobilenetv3_large_lraspp](fixed-grouped/models/native_mobilenetv3_large_lraspp/README.md) | RailSem19 | 9.5 | 9.0 | 34.4 | 236.7 | 0.85 | 3.2 |
| [segformer_b0](fixed-grouped/models/segformer_b0/README.md) | RailSem19 | 8.9 | 8.5 | 41.4 | 136.3 | 1.50 | 3.7 |
| [smp_pspnet_mobilenet_v2](fixed-grouped/models/smp_pspnet_mobilenet_v2/README.md) | recipe pretrained weights | 8.3 | 7.9 | 16.8 | 337.5 | 0.91 | 2.4 |
| [bisenetv1_r18](fixed-grouped/models/bisenetv1_r18/README.md) | recipe pretrained weights (only starting point) | 7.8 | 7.7 | 28.9 | 346.8 | 0.87 | 13.4 |
| [smp_deeplabv3plus_resnet101](fixed-grouped/models/smp_deeplabv3plus_resnet101/README.md) | recipe pretrained weights | 5.6 | 5.9 | 35.8 | 107.2 | 1.23 | 45.7 |
| [hrnet_w48_ocr](fixed-grouped/models/hrnet_w48_ocr/README.md) | Cityscapes → RailSem19 | 4.9 | 4.9 | 40.9 | 30.9 | 1.89 | 73.2 |
| [native_resnet18_fpn_segformer_aux](fixed-grouped/models/native_resnet18_fpn_segformer_aux/README.md) | Cityscapes → RailSem19 | 4.8 | 4.6 | 34.8 | 255.4 | 1.18 | 12.1 |
| [espnet](fixed-grouped/models/espnet/README.md) | recipe pretrained weights (only starting point) | 4.1 | 3.9 | 18.8 | 189.3 | 0.90 | 0.4 |
| [native_efficientnet_b0_deeplabv3plus](fixed-grouped/models/native_efficientnet_b0_deeplabv3plus/README.md) | Cityscapes → RailSem19 | 4.0 | 3.8 | 35.7 | 142.8 | 0.99 | 5.7 |
| [bisenetv2](fixed-grouped/models/bisenetv2/README.md) | recipe pretrained weights (only starting point) | 4.0 | 3.9 | 19.3 | 258.2 | 0.87 | 5.2 |
| [hf_auto_beit_base_ade](fixed-grouped/models/hf_auto_beit_base_ade/README.md) | RailSem19 | 3.8 | 3.8 | 30.0 | 2.5 | 4.59 | 161.5 |
| [smp_deeplabv3_resnet50](fixed-grouped/models/smp_deeplabv3_resnet50/README.md) | RailSem19 | 3.4 | 3.3 | 40.9 | 77.7 | 1.25 | 39.6 |
| [denseaspp161](fixed-grouped/models/denseaspp161/README.md) | recipe pretrained weights (only starting point) | 3.1 | 3.0 | 36.1 | 34.6 | 1.86 | 35.4 |
| [native_resnet50_aspp](fixed-grouped/models/native_resnet50_aspp/README.md) | RailSem19 | 3.1 | 2.9 | 34.3 | 226.1 | 1.10 | 39.0 |
| [native_resnet50_fpn_ocr](fixed-grouped/models/native_resnet50_fpn_ocr/README.md) | Cityscapes → RailSem19 | 2.6 | 3.8 | 41.6 | 48.4 | 2.10 | 32.6 |
| [native_resnet18_fpn_fcn](fixed-grouped/models/native_resnet18_fpn_fcn/README.md) | Cityscapes → RailSem19 | 2.5 | 2.4 | 36.6 | 216.5 | 1.21 | 12.6 |
| [native_resnet50_psp](fixed-grouped/models/native_resnet50_psp/README.md) | recipe pretrained weights | 2.3 | 2.6 | 30.3 | 214.6 | 1.09 | 37.1 |
| [native_mobilenetv3_large_deeplabv3plus](fixed-grouped/models/native_mobilenetv3_large_deeplabv3plus/README.md) | RailSem19 | 1.8 | 1.8 | 39.6 | 152.8 | 1.00 | 8.1 |
| [native_resnet50_deeplabv3plus](fixed-grouped/models/native_resnet50_deeplabv3plus/README.md) | recipe pretrained weights | 0.7 | 0.9 | 33.5 | 136.4 | 1.41 | 40.4 |
| [native_resnet101_uper](fixed-grouped/models/native_resnet101_uper/README.md) | recipe pretrained weights | 0.3 | 2.0 | 36.0 | 61.7 | 1.93 | 61.3 |

No finished run yet: `smp_upernet_resnet101`, `upernet_convnext`.

The first scene-grouped run (10 models, best-on-validation checkpoint) is in [the details](details.md#first-scene-grouped-run-10-models-best-on-validation-checkpoint).

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
- Paul's split reports the checkpoint that scored best on the same validation images (flattering), and that checkpoint was still selected on the older mud-pumping IoU with pixels pooled over all validation images (training is unchanged); the scene-grouped split and cross-validation report the final checkpoint after the full training budget, so nothing is picked on their scored images.
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
- Generated by `scripts/publish_rad_results.py` (code `f35265fa8dfd`) from the HDRFS records, which it only reads; records last changed 2026-10-11 11:16 AM PDT.
