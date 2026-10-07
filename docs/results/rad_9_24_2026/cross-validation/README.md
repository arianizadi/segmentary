# RAD 9/24: cross-validation over scenes (`rad_9_24_2026-cv`)

[RAD 9/24 study](../README.md) · [How the cross-validation works](../../../guides/cross-validation.md) · [All metrics (CSV)](cv-report.csv)

## Summary

Stratified group 5-fold cross-validation: the 243 scored images in 17 scenes of `rad_9_24_2026-fixed-grouped` are divided into 5 folds of whole scenes, balanced on the rare classes. Each model trains on the other folds and is scored on its own, so every image is scored once by a model that never trained on its scene (*pooled* results add up those scores). The result is the final checkpoint after the full training budget, so nothing is picked on the scored images. The test images are never used.

Percent, final checkpoint. 57 of 100 runs done; `*` = not all folds done yet (pooled over the finished folds only, not comparable). Train-camera images: a forward view from a camera on the train, the real use case.

| Model | Starting point | Folds done | Mud-pumping IoU, train-camera images | Precision, train-camera | Recall, train-camera | mIoU (classes present), all images |
| --- | --- | --- | --- | --- | --- | --- |
| `eomt_dinov3_large` | Cityscapes → RailSem19 | 5/5 | 9.2 | 34.9 | 11.2 | 56.4 |
| `eomt_dinov3_large` | Cityscapes | 5/5 | 27.6 | 45.9 | 40.9 | 55.7 |
| `eomt_dinov3_large` | RailSem19 | 5/5 | 30.1 | 61.8 | 37.0 | 57.4 |
| `eomt_dinov3_large` | recipe pretrained weights | 5/5 | 32.6 | 62.6 | 40.4 | 55.8 |
| `eomt_large` | Cityscapes → RailSem19 | 5/5 | 26.4 | 55.9 | 33.4 | 60.7 |
| `eomt_large` | Cityscapes | 5/5 | 23.7 | 49.8 | 31.2 | 58.1 |
| `eomt_large` | RailSem19 | 5/5 | 20.5 | 67.0 | 22.8 | 57.8 |
| `eomt_large` | recipe pretrained weights | 5/5 | 25.2 | 48.5 | 34.4 | 57.9 |
| `segformer_b2` | Cityscapes → RailSem19 | 0/5 | — | — | — | — |
| `segformer_b2` | Cityscapes | 0/5 | — | — | — | — |
| `segformer_b2` | RailSem19 | 0/5 | — | — | — | — |
| `segformer_b2` | recipe pretrained weights | 0/5 | — | — | — | — |
| `segformer_b5` | Cityscapes → RailSem19 | 2/5 | 30.0* | 32.7* | 78.7* | 51.1* |
| `segformer_b5` | Cityscapes | 5/5 | 27.6 | 49.7 | 38.3 | 47.1 |
| `segformer_b5` | RailSem19 | 5/5 | 20.8 | 34.0 | 34.8 | 55.5 |
| `segformer_b5` | recipe pretrained weights | 5/5 | 20.2 | 59.6 | 23.5 | 46.3 |
| `smp_upernet_resnet101` | Cityscapes → RailSem19 | 0/5 | — | — | — | — |
| `smp_upernet_resnet101` | Cityscapes | 0/5 | — | — | — | — |
| `smp_upernet_resnet101` | RailSem19 | 0/5 | — | — | — | — |
| `smp_upernet_resnet101` | recipe pretrained weights | 0/5 | — | — | — | — |

**Fold caveat:** fold 1 holds 95.9% of all scored mud-pumping pixels, all from one scene (`trackside-maintenance`; 49 track-level images) and none of the train-camera ones. Pooled all-image numbers therefore mostly measure that scene, scored by models that never trained on it; the train-camera numbers are the headline.

## Full report: How to read this

- 5 folds of whole groups; each job trains on the other folds and scores its own val fold. The holdout (test) is never trained on or scored.
- **Primary = `final-auto-val`** (final checkpoint, full step budget, no early stopping): nothing is chosen on the held-out fold. The best-on-val checkpoint (`best-auto-val`) is selected on the fold it is scored on and appears only in the secondary table.
- **Pooled** sums the per-image confusions of every fold's val images, so each scored image counts once; `*` marks a model whose folds are not all done (not comparable). **Per-fold** is the mean over folds with the sample SD and n folds; focus-class metrics only over folds whose subset has focus-class ground truth.
- Pixel-aggregated IoU is dominated by images with large areas of the class; the image-mean IoU averages per-image IoU over images with ground truth of the class. GT-class mIoU averages over classes with ground truth in the subset.
- One seed per job unless several seeds are listed: the per-fold spread mixes model variance with very different fold compositions (see below).

## Full report: Primary: final checkpoint

Percent.

| model | protocol | seed | folds | pooled GT-class mIoU | pooled mud-pumping IoU all | pooled img-mean mud-pumping IoU all | pooled mud-pumping IoU cab-view | pooled img-mean mud-pumping IoU cab-view | per-fold GT-class mIoU | per-fold mud-pumping IoU all | per-fold img-mean mud-pumping IoU all | per-fold mud-pumping IoU cab-view | per-fold img-mean mud-pumping IoU cab-view |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 56.4 | 4.4 | 5.5 | 9.2 | 5.9 | 56.2 (SD 5.0, n=5) | 5.8 (SD 7.0, n=5) | 16.2 (SD 18.1, n=5) | 9.6 (SD 7.7, n=4) | 21.5 (SD 19.3, n=4) |
| eomt_dinov3_large | cityscapes_to_rtis | 0 | 5/5 | 55.7 | 2.2 | 17.7 | 27.6 | 30.1 | 55.3 (SD 5.0, n=5) | 11.2 (SD 15.3, n=5) | 24.6 (SD 19.0, n=5) | 20.2 (SD 14.7, n=4) | 32.5 (SD 12.4, n=4) |
| eomt_dinov3_large | railsem19_to_rtis | 0 | 5/5 | 57.4 | 4.4 | 18.7 | 30.1 | 30.0 | 58.1 (SD 4.2, n=5) | 13.6 (SD 13.7, n=5) | 23.5 (SD 18.9, n=5) | 21.9 (SD 14.7, n=4) | 28.2 (SD 18.1, n=4) |
| eomt_dinov3_large | rtis_only | 0 | 5/5 | 55.8 | 1.8 | 19.2 | 32.6 | 33.0 | 55.4 (SD 4.9, n=5) | 11.5 (SD 15.6, n=5) | 24.5 (SD 19.6, n=5) | 24.0 (SD 13.5, n=4) | 31.9 (SD 13.9, n=4) |
| eomt_large | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 60.7 | 1.5 | 17.2 | 26.4 | 29.6 | 59.1 (SD 4.2, n=5) | 9.0 (SD 12.5, n=5) | 23.3 (SD 21.3, n=5) | 18.8 (SD 13.9, n=4) | 28.1 (SD 21.2, n=4) |
| eomt_large | cityscapes_to_rtis | 0 | 5/5 | 58.1 | 2.4 | 16.5 | 23.7 | 27.7 | 57.2 (SD 4.6, n=5) | 8.8 (SD 9.5, n=5) | 22.0 (SD 20.9, n=5) | 17.1 (SD 12.6, n=4) | 26.6 (SD 21.0, n=4) |
| eomt_large | railsem19_to_rtis | 0 | 5/5 | 57.8 | 1.2 | 11.2 | 20.5 | 19.3 | 57.2 (SD 4.1, n=5) | 10.6 (SD 12.0, n=5) | 18.2 (SD 20.0, n=5) | 18.0 (SD 13.1, n=4) | 22.8 (SD 19.8, n=4) |
| eomt_large | rtis_only | 0 | 5/5 | 57.9 | 2.1 | 16.0 | 25.2 | 27.1 | 57.6 (SD 4.9, n=5) | 13.0 (SD 11.3, n=5) | 22.7 (SD 23.7, n=5) | 20.7 (SD 14.5, n=4) | 27.9 (SD 23.8, n=4) |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | 0 | 2/5 | 51.1* | 1.4* | 4.1* | 30.0* | 71.3* | 51.9 (SD 6.5, n=2) | 10.0 (SD 12.2, n=2) | 36.3 (SD 49.5, n=2) | 30.0 (n=1) | 71.3 (n=1) |
| segformer_b5 | cityscapes_to_rtis | 0 | 5/5 | 47.1 | 2.0 | 17.4 | 27.6 | 29.7 | 47.4 (SD 4.9, n=5) | 12.4 (SD 11.0, n=5) | 22.2 (SD 24.4, n=5) | 19.4 (SD 14.2, n=4) | 27.4 (SD 24.7, n=4) |
| segformer_b5 | railsem19_to_rtis | 0 | 5/5 | 55.5 | 3.0 | 12.9 | 20.8 | 20.2 | 55.0 (SD 4.4, n=5) | 9.8 (SD 8.4, n=5) | 19.5 (SD 22.1, n=5) | 16.6 (SD 10.4, n=4) | 23.7 (SD 23.1, n=4) |
| segformer_b5 | rtis_only | 0 | 5/5 | 46.3 | 1.5 | 14.6 | 20.2 | 24.7 | 46.0 (SD 5.1, n=5) | 10.5 (SD 9.1, n=5) | 23.7 (SD 27.4, n=5) | 17.3 (SD 9.5, n=4) | 30.2 (SD 27.2, n=4) |

## Full report: Secondary (optimistic): best-on-val checkpoint

Selected on the same fold it is scored on; shown only to size that bias.

| model | protocol | seed | folds | pooled GT-class mIoU | pooled mud-pumping IoU all | pooled img-mean mud-pumping IoU all | pooled mud-pumping IoU cab-view | pooled img-mean mud-pumping IoU cab-view | per-fold GT-class mIoU | per-fold mud-pumping IoU all | per-fold img-mean mud-pumping IoU all | per-fold mud-pumping IoU cab-view | per-fold img-mean mud-pumping IoU cab-view |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 56.2 | 7.2 | 7.1 | 9.4 | 6.2 | 55.9 (SD 5.1, n=5) | 6.5 (SD 7.2, n=5) | 17.1 (SD 17.6, n=5) | 9.7 (SD 7.8, n=4) | 21.9 (SD 19.1, n=4) |
| eomt_dinov3_large | cityscapes_to_rtis | 0 | 5/5 | 54.6 | 2.3 | 18.0 | 27.6 | 30.7 | 54.5 (SD 4.9, n=5) | 11.4 (SD 15.7, n=5) | 25.8 (SD 18.9, n=5) | 20.4 (SD 14.7, n=4) | 35.0 (SD 10.6, n=4) |
| eomt_dinov3_large | railsem19_to_rtis | 0 | 5/5 | 57.2 | 9.1 | 21.8 | 29.5 | 31.5 | 57.5 (SD 4.9, n=5) | 14.8 (SD 13.2, n=5) | 25.3 (SD 17.8, n=5) | 22.5 (SD 15.1, n=4) | 29.1 (SD 18.3, n=4) |
| eomt_dinov3_large | rtis_only | 0 | 5/5 | 51.5 | 2.5 | 19.8 | 32.9 | 33.6 | 52.2 (SD 7.6, n=5) | 12.0 (SD 15.8, n=5) | 25.4 (SD 19.2, n=5) | 24.6 (SD 13.1, n=4) | 33.3 (SD 12.4, n=4) |
| eomt_large | cityscapes_to_railsem19_to_rtis | 0 | 5/5 | 59.3 | 1.8 | 17.9 | 26.4 | 30.6 | 58.0 (SD 5.3, n=5) | 9.4 (SD 12.8, n=5) | 23.8 (SD 21.4, n=5) | 19.2 (SD 14.4, n=4) | 28.6 (SD 21.3, n=4) |
| eomt_large | cityscapes_to_rtis | 0 | 5/5 | 57.1 | 2.4 | 16.7 | 23.5 | 27.9 | 56.3 (SD 5.0, n=5) | 9.0 (SD 9.7, n=5) | 22.3 (SD 20.8, n=5) | 17.2 (SD 12.7, n=4) | 26.8 (SD 21.0, n=4) |
| eomt_large | railsem19_to_rtis | 0 | 5/5 | 57.7 | 1.8 | 11.7 | 20.7 | 19.5 | 57.1 (SD 3.9, n=5) | 10.9 (SD 12.0, n=5) | 18.7 (SD 19.8, n=5) | 18.0 (SD 13.5, n=4) | 22.9 (SD 20.2, n=4) |
| eomt_large | rtis_only | 0 | 5/5 | 54.1 | 2.6 | 18.0 | 28.6 | 30.5 | 54.2 (SD 3.4, n=5) | 15.4 (SD 14.1, n=5) | 26.0 (SD 23.9, n=5) | 23.9 (SD 15.1, n=4) | 32.8 (SD 21.5, n=4) |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | 0 | 2/5 | 49.0* | 2.1* | 4.7* | 42.0* | 63.6* | 51.5 (SD 8.2, n=2) | 17.0 (SD 21.2, n=2) | 33.0 (SD 43.3, n=2) | 42.2 (n=1) | 63.6 (n=1) |
| segformer_b5 | cityscapes_to_rtis | 0 | 5/5 | 46.4 | 3.5 | 18.1 | 28.7 | 29.5 | 47.0 (SD 5.6, n=5) | 14.8 (SD 12.6, n=5) | 23.5 (SD 24.1, n=5) | 21.3 (SD 14.4, n=4) | 28.5 (SD 24.6, n=4) |
| segformer_b5 | railsem19_to_rtis | 0 | 5/5 | 55.1 | 3.4 | 13.8 | 21.7 | 21.5 | 54.8 (SD 4.3, n=5) | 11.0 (SD 9.6, n=5) | 20.6 (SD 22.0, n=5) | 17.5 (SD 10.9, n=4) | 24.9 (SD 22.8, n=4) |
| segformer_b5 | rtis_only | 0 | 5/5 | 44.0 | 2.1 | 18.1 | 27.2 | 30.6 | 43.5 (SD 4.7, n=5) | 14.8 (SD 12.8, n=5) | 24.1 (SD 21.1, n=5) | 21.1 (SD 11.4, n=4) | 29.8 (SD 19.3, n=4) |

## Full report: Coverage

| fold | completed | not completed (status count) | jobs |
|---|---|---|---:|
| 0 | 12 | queued 7, training 1 | 20 |
| 1 | 12 | queued 7, training 1 | 20 |
| 2 | 11 | collecting 1, queued 7, training 1 | 20 |
| 3 | 11 | collecting 1, queued 7, training 1 | 20 |
| 4 | 11 | queued 7, training 2 | 20 |

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
