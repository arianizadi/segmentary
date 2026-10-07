# RAD 9/24: cross-validation over scenes (`rad_9_24_2026-cv`)

[RAD 9/24 study](../README.md) · [How the cross-validation works](../../../guides/cross-validation.md) · [All metrics (CSV)](cv-report.csv)

## Summary

Stratified group 5-fold cross-validation: the 243 scored images in 17 scenes of `rad_9_24_2026-fixed-grouped` are divided into 5 folds of whole scenes, balanced on the rare classes. Each model trains on the other folds and is scored on its own, so every image is scored once by a model that never trained on its scene (*pooled* results average over all those images). The result is the final checkpoint after the full training budget, so nothing is picked on the scored images. The test images are never used.

Percent, final checkpoint. 100 of 100 runs done; `*` = not all folds done yet (pooled over the finished folds only, not comparable). Train-camera images: a forward view from a camera on the train, the real use case. Mud-pumping IoU is the per-image IoU averaged over the scored images with mud (images without it are not counted); precision and recall sum pixels over those images; mIoU scores each class on the images that contain it, then averages over the classes.

| Model | Starting point | Folds done | Mud-pumping IoU, train-camera images with mud (n=68) | Precision, train-camera images with mud | Recall, train-camera images with mud | mIoU (each class over images that contain it), all images |
| --- | --- | --- | --- | --- | --- | --- |
| `eomt_dinov3_large` | Cityscapes → RailSem19 | 5/5 | 5.9 | 95.1 | 11.2 | 57.0 |
| `eomt_dinov3_large` | Cityscapes | 5/5 | 30.1 | 64.8 | 40.9 | 55.6 |
| `eomt_dinov3_large` | RailSem19 | 5/5 | 30.0 | 71.5 | 37.0 | 59.3 |
| `eomt_dinov3_large` | recipe pretrained weights | 5/5 | 33.0 | 74.0 | 40.4 | 57.3 |
| `eomt_large` | Cityscapes → RailSem19 | 5/5 | 29.6 | 79.3 | 33.4 | 58.1 |
| `eomt_large` | Cityscapes | 5/5 | 27.7 | 74.6 | 31.2 | 56.3 |
| `eomt_large` | RailSem19 | 5/5 | 19.3 | 82.1 | 22.8 | 57.8 |
| `eomt_large` | recipe pretrained weights | 5/5 | 27.1 | 57.3 | 34.4 | 58.4 |
| `segformer_b2` | Cityscapes → RailSem19 | 5/5 | 22.4 | 63.2 | 28.2 | 49.4 |
| `segformer_b2` | Cityscapes | 5/5 | 23.6 | 69.3 | 24.9 | 44.8 |
| `segformer_b2` | RailSem19 | 5/5 | 27.7 | 48.1 | 41.1 | 52.2 |
| `segformer_b2` | recipe pretrained weights | 5/5 | 29.4 | 81.7 | 31.5 | 45.2 |
| `segformer_b5` | Cityscapes → RailSem19 | 5/5 | 22.0 | 36.5 | 40.7 | 51.4 |
| `segformer_b5` | Cityscapes | 5/5 | 29.7 | 60.3 | 38.3 | 46.3 |
| `segformer_b5` | RailSem19 | 5/5 | 20.2 | 36.3 | 34.8 | 54.0 |
| `segformer_b5` | recipe pretrained weights | 5/5 | 24.7 | 83.4 | 23.5 | 46.2 |
| `smp_upernet_resnet101` | Cityscapes → RailSem19 | 5/5 | 13.5 | 25.0 | 27.7 | 45.6 |
| `smp_upernet_resnet101` | Cityscapes | 5/5 | 14.8 | 28.6 | 28.2 | 41.5 |
| `smp_upernet_resnet101` | RailSem19 | 5/5 | 18.6 | 37.5 | 29.1 | 48.1 |
| `smp_upernet_resnet101` | recipe pretrained weights | 5/5 | 21.3 | 33.6 | 38.1 | 41.9 |

**Fold caveat:** Fold 2 holds 48 of the 68 scored train-camera images with mud-pumping, all from one scene (`sunny-mainline-cab-view`). Pooled, the train-camera numbers mostly measure that scene, scored by models that never trained on it.

## Per-class IoU

Pooled over all scored images, final checkpoint. IoU (%) of every class, each averaged only over the validation images that contain the class (n = those images); — = no image contains it. mIoU averages the classes with at least one such image.

| Model | Starting point | mIoU (each class over images that contain it) | person (n=24) | truck (n=27) | rail-track (n=202) | vegetation-overgrowth (n=89) | car (n=31) | on-rails (n=37) | traffic-sign (n=66) | road (n=78) | sidewalk (n=93) | construction (n=144) | tram-track (n=24) | pole (n=148) | traffic-light (n=36) | mud-pumping (n=118) | fence (n=88) | terrain (n=214) | sky (n=175) | rail-embedded (n=26) | rail-raised (n=240) | trackbed (n=223) | standing-water (n=40) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `eomt_dinov3_large` | Cityscapes → RailSem19 | 57.0 | 77.3 | 60.1 | 73.8 | 29.5 | 49.4 | 80.2 | 51.0 | 53.8 | 44.7 | 62.6 | 30.1 | 61.3 | 56.6 | 5.5 | 56.5 | 85.7 | 96.2 | 54.4 | 75.7 | 72.3 | 19.7 |
| `eomt_dinov3_large` | Cityscapes | 55.6 | 75.0 | 60.2 | 69.1 | 28.7 | 50.7 | 81.0 | 46.7 | 50.9 | 41.1 | 61.4 | 34.9 | 60.6 | 56.4 | 17.7 | 55.7 | 84.1 | 96.0 | 28.0 | 74.1 | 70.2 | 25.0 |
| `eomt_dinov3_large` | RailSem19 | 59.3 | 77.7 | 58.7 | 76.8 | 30.5 | 44.7 | 81.5 | 50.8 | 52.9 | 49.6 | 61.7 | 64.9 | 60.4 | 53.1 | 18.7 | 55.1 | 84.6 | 96.2 | 58.8 | 76.6 | 73.3 | 19.3 |
| `eomt_dinov3_large` | recipe pretrained weights | 57.3 | 81.3 | 61.7 | 72.5 | 28.7 | 44.7 | 82.7 | 33.8 | 49.3 | 50.4 | 61.5 | 50.6 | 55.4 | 53.1 | 19.2 | 55.9 | 83.7 | 96.1 | 35.5 | 74.6 | 72.0 | 40.6 |
| `eomt_large` | Cityscapes → RailSem19 | 58.1 | 77.1 | 66.1 | 75.0 | 31.0 | 43.2 | 80.7 | 49.5 | 48.7 | 46.3 | 61.8 | 52.0 | 61.6 | 56.3 | 17.2 | 56.2 | 84.7 | 95.9 | 55.8 | 76.1 | 71.5 | 12.6 |
| `eomt_large` | Cityscapes | 56.3 | 75.2 | 63.5 | 68.8 | 33.3 | 46.1 | 80.9 | 48.6 | 50.1 | 47.4 | 63.2 | 35.4 | 60.9 | 53.9 | 16.5 | 54.7 | 83.5 | 95.9 | 30.9 | 74.4 | 68.3 | 31.6 |
| `eomt_large` | RailSem19 | 57.8 | 77.2 | 60.3 | 75.4 | 30.0 | 38.9 | 79.0 | 50.7 | 51.1 | 46.2 | 59.7 | 70.7 | 60.8 | 53.8 | 11.2 | 53.8 | 84.5 | 96.0 | 59.8 | 75.8 | 69.8 | 10.1 |
| `eomt_large` | recipe pretrained weights | 58.4 | 79.7 | 64.6 | 70.8 | 32.7 | 40.3 | 81.3 | 41.3 | 51.1 | 51.0 | 64.6 | 47.1 | 57.8 | 56.3 | 16.0 | 57.1 | 85.0 | 96.1 | 46.5 | 76.0 | 71.2 | 39.9 |
| `segformer_b2` | Cityscapes → RailSem19 | 49.4 | 69.3 | 40.4 | 67.1 | 28.2 | 27.8 | 70.0 | 35.5 | 42.3 | 34.3 | 53.4 | 52.0 | 57.3 | 41.8 | 13.2 | 40.6 | 82.0 | 95.3 | 41.4 | 67.8 | 67.4 | 10.6 |
| `segformer_b2` | Cityscapes | 44.8 | 66.4 | 35.6 | 53.5 | 21.1 | 25.5 | 66.3 | 29.9 | 37.8 | 30.2 | 50.2 | 36.4 | 55.4 | 41.5 | 13.8 | 34.1 | 79.1 | 95.1 | 35.0 | 65.1 | 60.5 | 9.0 |
| `segformer_b2` | RailSem19 | 52.2 | 68.1 | 47.7 | 71.7 | 32.4 | 27.7 | 75.4 | 37.5 | 45.7 | 32.3 | 54.5 | 62.9 | 58.9 | 41.8 | 16.2 | 43.2 | 80.9 | 95.9 | 52.7 | 70.0 | 71.1 | 10.4 |
| `segformer_b2` | recipe pretrained weights | 45.2 | 60.1 | 34.3 | 58.1 | 28.3 | 21.7 | 64.3 | 32.8 | 36.5 | 32.6 | 48.4 | 41.7 | 53.8 | 36.8 | 18.3 | 29.9 | 76.3 | 95.6 | 37.7 | 68.5 | 63.2 | 10.1 |
| `segformer_b5` | Cityscapes → RailSem19 | 51.4 | 71.3 | 43.4 | 67.4 | 28.3 | 32.6 | 73.2 | 40.7 | 42.4 | 35.4 | 52.2 | 59.3 | 59.6 | 42.9 | 13.3 | 42.2 | 82.5 | 95.9 | 49.2 | 70.6 | 69.0 | 8.9 |
| `segformer_b5` | Cityscapes | 46.3 | 67.7 | 39.8 | 56.4 | 21.5 | 28.6 | 68.8 | 33.6 | 38.8 | 29.5 | 51.1 | 40.4 | 56.7 | 41.1 | 17.4 | 36.4 | 77.9 | 95.3 | 35.7 | 65.3 | 61.5 | 8.0 |
| `segformer_b5` | RailSem19 | 54.0 | 66.6 | 54.2 | 71.3 | 31.8 | 34.6 | 73.4 | 41.3 | 49.9 | 37.1 | 57.1 | 67.2 | 60.5 | 44.5 | 12.9 | 45.8 | 82.9 | 96.1 | 57.3 | 69.9 | 69.4 | 9.3 |
| `segformer_b5` | recipe pretrained weights | 46.2 | 61.6 | 34.9 | 60.9 | 25.9 | 17.1 | 68.5 | 32.1 | 39.9 | 33.5 | 49.6 | 44.8 | 55.6 | 37.0 | 14.6 | 29.8 | 78.3 | 95.5 | 42.6 | 72.0 | 64.5 | 12.2 |
| `smp_upernet_resnet101` | Cityscapes → RailSem19 | 45.6 | 58.7 | 37.5 | 64.7 | 18.2 | 24.5 | 64.4 | 37.2 | 38.1 | 28.9 | 47.3 | 48.7 | 55.0 | 38.4 | 12.9 | 32.8 | 74.7 | 94.3 | 40.2 | 66.3 | 65.8 | 8.0 |
| `smp_upernet_resnet101` | Cityscapes | 41.5 | 61.0 | 32.6 | 58.3 | 16.3 | 21.5 | 61.5 | 24.5 | 35.6 | 27.0 | 42.8 | 38.5 | 53.1 | 30.3 | 11.1 | 29.1 | 71.4 | 92.3 | 36.1 | 63.4 | 61.0 | 4.9 |
| `smp_upernet_resnet101` | RailSem19 | 48.1 | 59.8 | 37.4 | 69.1 | 18.0 | 24.8 | 64.1 | 38.6 | 39.2 | 32.9 | 49.4 | 65.7 | 54.4 | 41.5 | 14.3 | 33.6 | 76.6 | 94.9 | 56.7 | 66.4 | 68.2 | 5.2 |
| `smp_upernet_resnet101` | recipe pretrained weights | 41.9 | 48.7 | 30.6 | 62.4 | 20.7 | 13.0 | 56.2 | 23.5 | 35.2 | 29.0 | 45.7 | 44.7 | 50.0 | 29.1 | 18.1 | 28.4 | 75.2 | 93.6 | 42.8 | 64.2 | 64.6 | 4.9 |

## Full report: How to read this

- 5 folds of whole groups; each job trains on the other folds and scores its own val fold. The holdout (test) is never trained on or scored.
- **Primary = `final-auto-val`** (final checkpoint, full step budget, no early stopping): nothing is chosen on the held-out fold. The best-on-val checkpoint (`best-auto-val`) is selected on the fold it is scored on and appears only in the secondary table.
- **Pooled** scores every fold's val images together, so each scored image counts once; `*` marks a model whose folds are not all done (not comparable). **Per-fold** is the mean over folds with the sample SD and n folds; focus-class metrics only over folds whose subset has focus-class ground truth.
- Every metric counts a class only on the images that contain it: the focus-class IoU is the mean of per-image IoU over the images with its ground truth (images without it are not counted, so false positives on them do not lower it; a missed image scores 0), and mIoU averages each class's IoU over the images that contain it, then over the classes present in the subset. The pixel-pooled metrics (confusions summed first, so images with large areas of a class dominate) are in the CSV as `*_pixel_pooled`.
- One seed per job unless several seeds are listed: the per-fold spread mixes model variance with very different fold compositions (see below).

## Full report: Primary: final checkpoint

Percent.

| model | protocol | seed | folds | pooled mIoU | pooled mud-pumping IoU all (n=118) | pooled mud-pumping IoU cab-view (n=68) | per-fold mIoU | per-fold mud-pumping IoU all | per-fold mud-pumping IoU cab-view |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 57.0 | 5.5 | 5.9 | 56.9 (SD 5.1, n=5) | 16.2 (SD 18.1, n=5) | 21.5 (SD 19.3, n=4) |
| eomt_dinov3_large | cityscapes_to_rtis | 0 | 5/5 | 55.6 | 17.7 | 30.1 | 55.2 (SD 4.0, n=5) | 24.6 (SD 19.0, n=5) | 32.5 (SD 12.4, n=4) |
| eomt_dinov3_large | railsem19_to_rtis | 0 | 5/5 | 59.3 | 18.7 | 30.0 | 58.8 (SD 4.0, n=5) | 23.5 (SD 18.9, n=5) | 28.2 (SD 18.1, n=4) |
| eomt_dinov3_large | rtis_only | 0 | 5/5 | 57.3 | 19.2 | 33.0 | 57.0 (SD 4.9, n=5) | 24.5 (SD 19.6, n=5) | 31.9 (SD 13.9, n=4) |
| eomt_large | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 58.1 | 17.2 | 29.6 | 58.1 (SD 4.9, n=5) | 23.3 (SD 21.3, n=5) | 28.1 (SD 21.2, n=4) |
| eomt_large | cityscapes_to_rtis | 0 | 5/5 | 56.3 | 16.5 | 27.7 | 56.3 (SD 4.1, n=5) | 22.0 (SD 20.9, n=5) | 26.6 (SD 21.0, n=4) |
| eomt_large | railsem19_to_rtis | 0 | 5/5 | 57.8 | 11.2 | 19.3 | 57.3 (SD 4.3, n=5) | 18.2 (SD 20.0, n=5) | 22.8 (SD 19.8, n=4) |
| eomt_large | rtis_only | 0 | 5/5 | 58.4 | 16.0 | 27.1 | 58.1 (SD 5.0, n=5) | 22.7 (SD 23.7, n=5) | 27.9 (SD 23.8, n=4) |
| segformer_b2 | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 49.4 | 13.2 | 22.4 | 48.9 (SD 3.8, n=5) | 22.2 (SD 26.1, n=5) | 27.1 (SD 27.3, n=4) |
| segformer_b2 | cityscapes_to_rtis | 0 | 5/5 | 44.8 | 13.8 | 23.6 | 44.6 (SD 4.3, n=5) | 20.4 (SD 22.2, n=5) | 24.5 (SD 23.4, n=4) |
| segformer_b2 | railsem19_to_rtis | 0 | 5/5 | 52.2 | 16.2 | 27.7 | 52.2 (SD 3.5, n=5) | 22.9 (SD 23.4, n=5) | 28.1 (SD 23.5, n=4) |
| segformer_b2 | rtis_only | 0 | 5/5 | 45.2 | 18.3 | 29.4 | 45.0 (SD 3.4, n=5) | 26.2 (SD 27.6, n=5) | 31.6 (SD 28.8, n=4) |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 51.4 | 13.3 | 22.0 | 51.4 (SD 4.6, n=5) | 23.3 (SD 28.7, n=5) | 28.5 (SD 30.3, n=4) |
| segformer_b5 | cityscapes_to_rtis | 0 | 5/5 | 46.3 | 17.4 | 29.7 | 46.3 (SD 3.2, n=5) | 22.2 (SD 24.4, n=5) | 27.4 (SD 24.7, n=4) |
| segformer_b5 | railsem19_to_rtis | 0 | 5/5 | 54.0 | 12.9 | 20.2 | 53.8 (SD 3.6, n=5) | 19.5 (SD 22.1, n=5) | 23.7 (SD 23.1, n=4) |
| segformer_b5 | rtis_only | 0 | 5/5 | 46.2 | 14.6 | 24.7 | 46.2 (SD 4.0, n=5) | 23.7 (SD 27.4, n=5) | 30.2 (SD 27.2, n=4) |
| smp_upernet_resnet101 | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 45.6 | 12.9 | 13.5 | 44.5 (SD 3.9, n=5) | 18.1 (SD 21.6, n=5) | 18.2 (SD 25.8, n=4) |
| smp_upernet_resnet101 | cityscapes_to_rtis | 0 | 5/5 | 41.5 | 11.1 | 14.8 | 40.9 (SD 3.1, n=5) | 17.0 (SD 20.2, n=5) | 19.3 (SD 22.6, n=4) |
| smp_upernet_resnet101 | railsem19_to_rtis | 0 | 5/5 | 48.1 | 14.3 | 18.6 | 47.8 (SD 3.3, n=5) | 17.0 (SD 16.4, n=5) | 18.6 (SD 18.7, n=4) |
| smp_upernet_resnet101 | rtis_only | 0 | 5/5 | 41.9 | 18.1 | 21.3 | 41.1 (SD 2.6, n=5) | 19.8 (SD 17.9, n=5) | 20.6 (SD 21.3, n=4) |

## Full report: Secondary (optimistic): best-on-val checkpoint

Selected on the same fold it is scored on; shown only to size that bias.

| model | protocol | seed | folds | pooled mIoU | pooled mud-pumping IoU all (n=118) | pooled mud-pumping IoU cab-view (n=68) | per-fold mIoU | per-fold mud-pumping IoU all | per-fold mud-pumping IoU cab-view |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 56.7 | 7.1 | 6.2 | 56.7 (SD 4.9, n=5) | 17.1 (SD 17.6, n=5) | 21.9 (SD 19.1, n=4) |
| eomt_dinov3_large | cityscapes_to_rtis | 0 | 5/5 | 55.1 | 18.0 | 30.7 | 54.8 (SD 3.6, n=5) | 25.8 (SD 18.9, n=5) | 35.0 (SD 10.6, n=4) |
| eomt_dinov3_large | railsem19_to_rtis | 0 | 5/5 | 58.0 | 21.8 | 31.5 | 57.7 (SD 3.5, n=5) | 25.3 (SD 17.8, n=5) | 29.1 (SD 18.3, n=4) |
| eomt_dinov3_large | rtis_only | 0 | 5/5 | 53.0 | 19.8 | 33.6 | 53.1 (SD 5.8, n=5) | 25.4 (SD 19.2, n=5) | 33.3 (SD 12.4, n=4) |
| eomt_large | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 56.8 | 17.9 | 30.6 | 57.2 (SD 4.4, n=5) | 23.8 (SD 21.4, n=5) | 28.6 (SD 21.3, n=4) |
| eomt_large | cityscapes_to_rtis | 0 | 5/5 | 55.4 | 16.7 | 27.9 | 55.5 (SD 3.8, n=5) | 22.3 (SD 20.8, n=5) | 26.8 (SD 21.0, n=4) |
| eomt_large | railsem19_to_rtis | 0 | 5/5 | 57.7 | 11.7 | 19.5 | 57.1 (SD 4.2, n=5) | 18.7 (SD 19.8, n=5) | 22.9 (SD 20.2, n=4) |
| eomt_large | rtis_only | 0 | 5/5 | 54.3 | 18.0 | 30.5 | 54.7 (SD 4.1, n=5) | 26.0 (SD 23.9, n=5) | 32.8 (SD 21.5, n=4) |
| segformer_b2 | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 46.4 | 14.3 | 23.6 | 46.7 (SD 4.8, n=5) | 24.7 (SD 25.3, n=5) | 28.5 (SD 27.7, n=4) |
| segformer_b2 | cityscapes_to_rtis | 0 | 5/5 | 43.3 | 14.9 | 24.2 | 43.1 (SD 3.1, n=5) | 22.4 (SD 19.8, n=5) | 25.0 (SD 22.2, n=4) |
| segformer_b2 | railsem19_to_rtis | 0 | 5/5 | 52.0 | 17.0 | 28.7 | 52.0 (SD 3.3, n=5) | 23.9 (SD 23.1, n=5) | 29.2 (SD 23.1, n=4) |
| segformer_b2 | rtis_only | 0 | 5/5 | 43.4 | 21.1 | 34.0 | 43.1 (SD 3.8, n=5) | 28.4 (SD 26.0, n=5) | 33.5 (SD 27.1, n=4) |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 51.1 | 14.4 | 23.3 | 51.0 (SD 4.2, n=5) | 23.1 (SD 25.5, n=5) | 28.1 (SD 26.5, n=4) |
| segformer_b5 | cityscapes_to_rtis | 0 | 5/5 | 45.5 | 18.1 | 29.5 | 45.5 (SD 3.9, n=5) | 23.5 (SD 24.1, n=5) | 28.5 (SD 24.6, n=4) |
| segformer_b5 | railsem19_to_rtis | 0 | 5/5 | 53.9 | 13.8 | 21.5 | 53.7 (SD 3.4, n=5) | 20.6 (SD 22.0, n=5) | 24.9 (SD 22.8, n=4) |
| segformer_b5 | rtis_only | 0 | 5/5 | 43.3 | 18.1 | 30.6 | 43.1 (SD 5.2, n=5) | 24.1 (SD 21.1, n=5) | 29.8 (SD 19.3, n=4) |
| smp_upernet_resnet101 | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 43.4 | 20.2 | 20.0 | 43.1 (SD 3.0, n=5) | 27.5 (SD 14.0, n=5) | 23.5 (SD 21.7, n=4) |
| smp_upernet_resnet101 | cityscapes_to_rtis | 0 | 5/5 | 37.4 | 17.7 | 14.4 | 37.4 (SD 2.8, n=5) | 21.9 (SD 19.1, n=5) | 20.8 (SD 23.1, n=4) |
| smp_upernet_resnet101 | railsem19_to_rtis | 0 | 5/5 | 48.3 | 19.8 | 22.5 | 48.1 (SD 3.1, n=5) | 21.3 (SD 13.7, n=5) | 21.4 (SD 17.3, n=4) |
| smp_upernet_resnet101 | rtis_only | 0 | 5/5 | 40.2 | 22.4 | 21.7 | 39.3 (SD 1.9, n=5) | 22.5 (SD 18.3, n=5) | 21.5 (SD 22.0, n=4) |

## Full report: Coverage

| fold | completed | not completed (status count) | jobs |
|---|---|---|---:|
| 0 | 20 | — | 20 |
| 1 | 20 | — | 20 |
| 2 | 20 | — | 20 |
| 3 | 20 | — | 20 |
| 4 | 20 | — | 20 |

## Full report: Fold composition (labels only)

| fold | groups | val images | mud-pumping | on-rails | person | standing-water | tram-track | truck | vegetation-overgrowth | mud-pumping px share | cab-view mud-pumping images | other mud-pumping images | track-level mud-pumping images | cab-view mud-pumping px share | other mud-pumping px share | track-level mud-pumping px share | excluded small |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | evening-water-cab-view, miscellaneous-flood-stills, miscellaneous-numbered-cab-views, new-unmatched-2026, vegetation-worksite | 34 | 2 | 5 | 6 | 10 | 2 | 3 | 19 | 0.1% | 2 | 0 | 0 | 3.5% | — | 0.0% | miscellaneous-flood-stills/0275, miscellaneous-flood-stills/0276 |
| 1 | flooded-road-crossing, green-roadside-cab-view, trackside-maintenance | 67 | 49 | 9 | 4 | 3 | 6 | 10 | 17 | 95.9% | 0 | 0 | 49 | 0.0% | — | 100.0% | trackside-maintenance/0100, trackside-maintenance/0101, trackside-maintenance/0102, trackside-maintenance/0104, trackside-maintenance/0105 |
| 2 | flooded-station-platform, sunny-mainline-cab-view | 62 | 48 | 4 | 3 | 8 | 5 | 6 | 20 | 2.0% | 48 | 0 | 0 | 47.7% | — | 0.0% | — |
| 3 | green-water-cab-view, miscellaneous-mud-cab-view, overcast-mountain-stations, trackside-vegetation-closeups | 35 | 2 | 10 | 3 | 5 | 7 | 4 | 15 | 0.1% | 1 | 0 | 1 | 1.8% | — | 0.0% | — |
| 4 | rain-water-cab-view-with-overlay, rural-overcast-cab-view, sunny-mountain-stations | 45 | 17 | 9 | 8 | 14 | 4 | 4 | 18 | 1.9% | 17 | 0 | 0 | 47.1% | — | 0.0% | — |

Label coverage warnings: none

## Full report: Inputs

- campaign: `/data/izadia1/projects/segmentary-runs/rad_9_24_2026/cv-seed0-20261006`
- code: `e7154e71fff6313106732f321edce7293c24418c`
- spec: `sha256 85e1661b0353`
- viewpoints: `rad_9_24_2026-viewpoints.yaml (sha256 7dfc4f730cbe)`
- primary checkpoint: `final`

Every metric, subset, fold and checkpoint is in [`cv-report.csv`](cv-report.csv).
