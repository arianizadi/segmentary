# RAD 9/24: can segmentation models find mud-pumping in rail scenes they have not seen?

## What we tested

- **Data:** Paul Stanik's `rad_9_24_2026` set: 314 rail images labelled with 21 classes, including mud-pumping (the track defect we look for).
- **Question:** how well do models find mud-pumping in scenes (videos) they did *not* see in training? We score mud-pumping IoU (overlap of predicted and true mud-pumping pixels, in percent; 100 = perfect) on all validation images and on train-camera images (a forward view from a camera on the train, the real use case).
- **Three ways to split the images into training and validation:** (a) Paul's split, random by image, so frames of one video can be on both sides; (b) a scene-grouped split that keeps whole scenes on one side; (c) 5-fold cross-validation over scenes, where every scene is scored once by a model that never trained on it (the most reliable).
- **Models:** 10 segmentation models, each from 4 starting points (pretraining before training on these images). Test images are never used.

## Key result

Paul's split looks good (median 89.2 on all images) because 94.9% of its validation mud-pumping pixels come from one scene, `trackside-maintenance` (track-level close-ups), and every validation scene of that split also has images in training. On scenes the models never trained on, mud-pumping IoU on train-camera images is median 13.4 (best 42.3) with the scene-grouped split and median 25.8 (best 32.6) in cross-validation.

| Split | Model runs | Mud-pumping IoU, all images | Mud-pumping IoU, train-camera images | mIoU (classes present) |
| --- | --- | --- | --- | --- |
| Paul's split | 40 | median 89.2 (best 95.0) | median 42.7 (best 61.9) | median 60.8 (best 72.8) |
| Scene-grouped split | 40 | median 6.9 (best 18.8) | median 13.4 (best 42.3) | median 44.6 (best 58.3) |
| Cross-validation over scenes | 8 of 20 with all folds done | median 2.1 (best 4.4) | median 25.8 (best 32.6) | median 57.6 (best 60.7) |

Median and best over every finished model and starting point of each split. mIoU averages IoU over the classes present in the images.

## Results by split

Each table shows every model with its best starting point, picked by train-camera mud-pumping IoU on the same validation images (so slightly flattering). Starting points: recipe pretrained weights, Cityscapes, RailSem19, Cityscapes → RailSem19 (public street and rail datasets). Speed (FPS): model-only forward passes per second on one NVIDIA L40S, batch 1, 1024x1024 input, BF16, without data loading or pre-processing.

### Paul's split

Images assigned to training and validation at random, balanced by class; 17 of its 17 validation scenes also have images in training (227 training, 37 validation images). [Every model and starting point](paul/README.md).

| Model | Best starting point | Mud-pumping IoU, train-camera images | Mud-pumping IoU, all images | mIoU (classes present) | Speed (FPS) |
| --- | --- | --- | --- | --- | --- |
| [segformer_b5](paul/models/segformer_b5/README.md) | Cityscapes → RailSem19 | 61.9 | 91.2 | 65.1 | 27.6 |
| [segformer_b2](paul/models/segformer_b2/README.md) | recipe pretrained weights | 58.7 | 93.1 | 58.2 | 53.3 |
| [eomt_large](paul/models/eomt_large/README.md) | RailSem19 | 50.7 | 95.0 | 72.8 | 45.8 |
| [upernet_convnext](paul/models/upernet_convnext/README.md) | recipe pretrained weights | 50.6 | 91.7 | 61.5 | 42.5 |
| [hrnet_w48_ocr](paul/models/hrnet_w48_ocr/README.md) | recipe pretrained weights | 49.3 | 90.8 | 59.8 | 31.3 |
| [native_convnext_tiny_uper](paul/models/native_convnext_tiny_uper/README.md) | RailSem19 | 48.5 | 88.4 | 64.1 | 76.3 |
| [smp_fpn_resnet50](paul/models/smp_fpn_resnet50/README.md) | RailSem19 | 47.4 | 89.9 | 60.3 | 159.1 |
| [smp_deeplabv3plus_resnet101](paul/models/smp_deeplabv3plus_resnet101/README.md) | RailSem19 | 47.2 | 87.7 | 62.4 | 117.7 |
| [smp_upernet_resnet101](paul/models/smp_upernet_resnet101/README.md) | RailSem19 | 42.7 | 86.0 | 57.4 | 73.9 |
| [eomt_dinov3_large](paul/models/eomt_dinov3_large/README.md) | recipe pretrained weights | 41.9 | 90.8 | 68.3 | 40.8 |

### Scene-grouped split

Whole scenes kept on one side; 0 of its 3 validation scenes have images in training (217 training, 37 validation images). [Every model and starting point](fixed-grouped/README.md).

| Model | Best starting point | Mud-pumping IoU, train-camera images | Mud-pumping IoU, all images | mIoU (classes present) | Speed (FPS) |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](fixed-grouped/models/eomt_dinov3_large/README.md) | Cityscapes | 42.3 | 10.6 | 51.4 | 37.3 |
| [eomt_large](fixed-grouped/models/eomt_large/README.md) | Cityscapes → RailSem19 | 34.6 | 15.7 | 58.2 | 45.5 |
| [segformer_b5](fixed-grouped/models/segformer_b5/README.md) | Cityscapes | 26.9 | 4.7 | 44.2 | 27.5 |
| [smp_upernet_resnet101](fixed-grouped/models/smp_upernet_resnet101/README.md) | Cityscapes | 25.5 | 16.3 | 26.1 | 73.7 |
| [segformer_b2](fixed-grouped/models/segformer_b2/README.md) | Cityscapes | 23.1 | 16.8 | 45.1 | 53.0 |
| [smp_fpn_resnet50](fixed-grouped/models/smp_fpn_resnet50/README.md) | RailSem19 | 20.7 | 12.8 | 48.8 | 159.7 |
| [upernet_convnext](fixed-grouped/models/upernet_convnext/README.md) | Cityscapes | 17.5 | 3.2 | 36.2 | 42.7 |
| [smp_deeplabv3plus_resnet101](fixed-grouped/models/smp_deeplabv3plus_resnet101/README.md) | RailSem19 | 13.7 | 5.6 | 49.2 | 119.4 |
| [native_convnext_tiny_uper](fixed-grouped/models/native_convnext_tiny_uper/README.md) | recipe pretrained weights | 13.3 | 6.9 | 29.2 | 76.1 |
| [hrnet_w48_ocr](fixed-grouped/models/hrnet_w48_ocr/README.md) | Cityscapes | 12.2 | 12.0 | 40.1 | 31.7 |

### Cross-validation over scenes

The scenes of the scene-grouped data are divided into 5 folds; each model trains on 4 folds and is scored on the remaining one, so every image is scored once by a model that never saw its scene. The result is the final checkpoint, so nothing is picked on the scored images. 44 of 100 runs done; `*` = not all folds done yet. [Full report](cross-validation/README.md).

| Model | Best starting point | Mud-pumping IoU, train-camera images | Mud-pumping IoU, all images | mIoU (classes present) | Folds done |
| --- | --- | --- | --- | --- | --- |
| eomt_dinov3_large | recipe pretrained weights | 32.6 | 1.8 | 55.8 | 5/5 |
| eomt_large | Cityscapes → RailSem19 | 26.4 | 1.5 | 60.7 | 5/5 |
| segformer_b5 | recipe pretrained weights | 22.9* | 1.2* | 46.1* | 4/5 |
| segformer_b2 | — | — | — | — | 0/5 |
| smp_upernet_resnet101 | — | — | — | — | 0/5 |

## Paul's paper model

Paul's own recipes, retrained by us with his code on each split and scored with the same code as above. Paul's finished model is never scored here: it may have trained on our validation images.

| Paul's recipe, retrained by us | Split | Mud-pumping IoU, train-camera images | Mud-pumping IoU, all images | mIoU (classes present) |
| --- | --- | --- | --- | --- |
| HRNet-OCR, Paul's RailSem19 checkpoint | Paul's split | 47.0 | 88.1 | 65.4 |
| HRNet-OCR, Paul's RailSem19 checkpoint | Scene-grouped split | trained, not scored yet | — | — |

## Caveats

- One training run per model and starting point (seed 0): differences of a few points are not established.
- Paul's split and the scene-grouped split report the checkpoint that scored best on the same validation images (flattering); cross-validation reports the final one.
- Few train-camera validation images have mud-pumping: Paul's split 7, the scene-grouped split 17 (all from one scene, `rural-overcast-cab-view`).
- In cross-validation, fold 1 holds 95.9% of all scored mud-pumping pixels, all from one scene (`trackside-maintenance`; 49 track-level images) and none of the train-camera ones, so the all-images numbers mostly measure that one scene.
- Paul's split and the scene-grouped split also differ in labels (Paul's masks vs our re-render); scenes are grouped by eye, not from recording records.

## Details

- [Paul's split: every model and starting point](paul/README.md)
- [Scene-grouped split: every model and starting point](fixed-grouped/README.md)
- [Cross-validation report](cross-validation/README.md) and its [CSV](cross-validation/cv-report.csv)
- [Why Paul's split looks so good (case document)](../../guides/rad-9-24-2026-mud-iou-case.md)
- [Full details](details.md): label defects in the delivered masks, all comparison tables, every retraining run of Paul's recipes, provenance
- [Comparison CSV](rad-comparison.csv)
- [Dataset preparation and split decisions](../../guides/rad-9-24-2026.md)
- Generated by `scripts/publish_rad_results.py` (code `dfec13219003`) from the HDRFS records, which it only reads; records last changed 2026-10-05 09:27 PM PDT.
