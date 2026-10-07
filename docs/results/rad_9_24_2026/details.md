# RAD 9/24 study: full details

[Short summary](README.md) · [Mud IoU case document](../../guides/rad-9-24-2026-mud-iou-case.md)

The `rad_9_24_2026` delivery (314 rail images with polygon labels) trained two ways with the same 10-model x 4-initialization-path catalog (40 jobs per arm, seed 0, checkpoint selection and early stopping on validation mud-pumping IoU with pixels pooled over all validation images), plus Paul Stanik's two paper recipes, retrained by us with his fork code. The question: how much does Paul's random stratified split flatter the results compared with a scene-grouped split (`paul` vs `fixed-grouped`)? The two arms also differ in labels. A third arm with our re-rendered masks on the stratified split was stopped on 2026-10-05 at 8 of 40 jobs: over 8 matched eomt runs the label fix changed cab-view mud IoU (pixels pooled) on stratified val by -3.3 to +4.7 points, -0.1 on average. Validation only; the test split is held out and never read. Mud-pumping IoU and mIoU below count each class only on the validation images that contain it (see *How to read this*); the pixel-pooled numbers are in the CSV.

[Dataset preparation and split decisions](../../guides/rad-9-24-2026.md) · [Comparison CSV](rad-comparison.csv)

## Arms (splits) and progress

| arm | labels | split; train/val/test | completed | other jobs | code |
| --- | --- | --- | --- | --- | --- |
| [`paul`](paul/README.md) | Paul's delivered `masks_machine` copies | stratified random (seed 0); 227/37/50 | 40/40 | — | `d864b72bd907` |
| [`fixed-grouped`](fixed-grouped/README.md) | re-rendered from the polygon JSONs | scene-grouped (from v1/v2); 217/37/60 | 40/40 | — | `d864b72bd907` |

Each arm page has the per-model reports, `results.csv`, `status.json` and the downloadable evidence exactly as for [RTIS v2](../paul-test-rtis/v2/README.md). Fork progress is in the [paper-recipe section](#paper-recipe-fork-runs).

## Caveats

- **Single seed.** Every result is one training run (seed 0); there are no repeats or confidence intervals, so differences of a few IoU points are not established.
- **Optimistic validation numbers.** Checkpoints are selected (and training early stopped) on the same val split that is reported, by the mud IoU with pixels pooled over all val images rather than the present-image mud IoU shown; fork runs pick their epoch on that split too.
- **Small cab-view subsets.** Val images with mud ground truth behind the deployment-relevant cab-view mud IoU: `paul` n=7, `fixed-grouped` n=17.
- **The stratified split shares scenes.** Frames of one recording can sit in train and val; scene groups of the val split that also have train images: `paul` 17 of 17. `paul`-arm numbers measure same-recording generalisation; only `fixed-grouped` keeps scene groups apart (groups are visually assigned).

## Label defects in the delivered masks

The annotator's `masks_machine` PNGs start from a black canvas and draw exterior polygon rings only, so pixels covered by no polygon become class 0 (person) and polygon holes are filled. The `paul` arm trains on those masks; the `fixed-grouped` arm trains on the repository render of the same polygon JSONs (holes cut out, uncovered pixels ignored). Counts over all 314 images, from each prepared dataset's `audit/label-audit.json` (masks_machine versus the repository render):

| Quantity | `paul`, `fixed-grouped` |
| --- | --- |
| Images with any disagreement | 314 |
| Images with pixels covered by no polygon | 63 |
| Pixels covered by no polygon / of those labelled person in masks_machine | 210,762 / 210,762 |
| Pixels changed by ignoring polygon holes | 299,121 |
| Total disagreement pixels | 1,478,606 (0.20%) |
| Person pixels, repository render / masks_machine | 907,504 / 1,125,758 |
| Mud-pumping pixels differing, masks_machine / render (of all mud pixels) | 14,250 / 37,144 of 65,175,587 |

Trained labels (`label_source`): `paul` paul, `fixed-grouped` rendered. The two renders compared are the same for every arm. Classes with the most differing pixels (larger of the two directions): terrain 284,329, person 221,586, sky 215,126, pole 212,261, rail-raised 187,904.

## Cab-view comparison (validation split)

### How to read this

All numbers are on the validation split (paul 37, fixed-grouped 37 images); the test split is never read. Every metric counts a class only on the images that contain it. Mud IoU is the mean of per-image mud IoU over the images with mud ground truth: images without mud are not counted, so mud predicted on clean track does not lower it, and a mud image with no mud predicted scores 0. Mud precision and recall sum mud pixels over those same images only. mIoU averages each class's IoU over the images that contain it, then over the classes present in the subset. `n=` in a column header is the number of val images with mud GT behind that arm's mud metrics. The pixel-pooled numbers (confusions summed over the subset first, as used for checkpoint selection) stay in `rad-comparison.csv` as the `*_pixel_pooled` columns.

**Arms.** All campaign models are trained by us. `paul` = Paul's delivered masks (the `masks_machine` copies) with the stratified split; `fixed-grouped` = our re-rendered masks with the scene-grouped split. P / FG below name these label/split arms, not who trained the model. A third arm with our re-rendered masks on the stratified split was stopped on 2026-10-05 at 8 of 40 jobs: over 8 matched eomt runs the label fix changed cab-view mud IoU (pixels pooled) on stratified val by -3.3 to +4.7 points, -0.1 on average.

**Caveats.**

- **These val numbers are optimistic.** The reported checkpoint is the one selected on this same val split (campaign selection and early stopping on `val_iou/mud-pumping`, with pixels pooled over the whole split); fork runs report their `best_mud_epoch` checkpoint, also chosen on this val split. They are not held-out estimates, mud IoU least of all.
- **Single seed, no uncertainty.** Every campaign result is seed 0; there are no repeats or confidence intervals, and the subsets are small (see `n=`), so differences of a few IoU points between models or arms are not established.
- On the stratified val split (`paul` masks) 6 of the 13 images with mud GT are track-level and 7 cab-view; 5 come from the `trackside-maintenance` scene group. By pixels that group holds 94.9% of all mud GT and the five largest images (`trackside-maintenance/0071`, `trackside-maintenance/0076`, `trackside-maintenance/0081`, `trackside-maintenance/0089`, `trackside-maintenance/0091`) 94.9%, which decides only the pixel-pooled CSV columns. Scene groups are directory layout names assigned from visual evidence, not confirmed recording provenance.
- On the grouped val split 17 of the 18 images with mud GT are cab-view, so its `all` and `cab-view` mud IoU nearly coincide. All 17 cab-view ones come from the `rural-overcast-cab-view` scene group; judged visually, a forward view centred on the track from a moving vehicle, but from a camera visibly lower than a locomotive cab (the ballast fills the lower frame; more like a front-bumper or draisine mount). The grouped arm's cab-view mud numbers therefore mostly measure that one camera setup.
- **`cab-view` is the deployment-relevant subset** (a camera on a moving train). Compare arms and models on cab-view mud IoU; read `all` with the composition above in mind.
- Viewpoints come from `configs/datasets/rad_9_24_2026-viewpoints.yaml`, joined by image SHA-256: visual judgement only, from two labelling passes by AI model subagents with adjudication of disagreements. Both passes are the same model, so their agreement is not evidence from independent annotators.
- `paul` vs `fixed-grouped` changes **both** the labels and the split policy. The stopped label-fix arm (above) found the label part small on average but -3.3 to +4.7 points per run, measured on eomt models and stratified val only, so a model's FG - P difference within that range cannot be attributed to the split. The val sets are different images and the train sets differ too (227 vs 217 train images, 158 in common), so the difference mixes the training data, model generalisation and val composition. On the stratified split 17 of its 17 val scene groups also have train images; on the grouped split 0 of 3 do (scene groups are visually assigned, not confirmed recordings).
- Fork labels: in `paper-hrnet__rs19-paul__arm-paul`, `rs19-paul` means the RS19 stage uses Paul's checkpoint and `arm-paul` means the RAD stage trains on the `paul` arm (Paul's masks); the checkpoint owners column spells out who trained each stage.

### Headline: Segmentary campaign models

Percent; columns per arm: P = `paul`, FG = `fixed-grouped`. Selected checkpoint `best-auto-val`. Empty = job not completed.

| model | protocol | mIoU P | mIoU FG | mud IoU P (n=13) | mud IoU FG (n=18) | mud IoU cab P (n=7) | mud IoU cab FG (n=17) | mud precision cab P (n=7) | mud precision cab FG (n=17) | mud recall cab P (n=7) | mud recall cab FG (n=17) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | 62.3 | 48.6 | 63.9 | 11.5 | 48.0 | 11.5 | 82.4 | 98.8 | 61.3 | 13.2 |
| eomt_dinov3_large | cityscapes_to_rtis | 56.7 | 49.7 | 57.1 | 39.2 | 37.2 | 41.4 | 83.6 | 87.9 | 47.1 | 47.0 |
| eomt_dinov3_large | railsem19_to_rtis | 64.0 | 55.6 | 65.4 | 32.5 | 53.3 | 34.2 | 85.3 | 96.5 | 64.2 | 38.3 |
| eomt_dinov3_large | rtis_only | 59.8 | 47.9 | 63.3 | 37.1 | 49.2 | 39.1 | 81.1 | 93.0 | 65.2 | 43.0 |
| eomt_large | cityscapes_to_railsem19_to_rtis | 64.2 | 52.5 | 65.6 | 34.9 | 51.9 | 36.5 | 87.9 | 92.2 | 65.0 | 38.6 |
| eomt_large | cityscapes_to_rtis | 61.7 | 53.0 | 64.5 | 27.3 | 50.5 | 28.7 | 87.8 | 95.9 | 62.0 | 27.9 |
| eomt_large | railsem19_to_rtis | 64.4 | 51.5 | 64.3 | 9.9 | 49.3 | 10.3 | 85.2 | 94.5 | 63.1 | 10.7 |
| eomt_large | rtis_only | 62.5 | 50.9 | 64.8 | 32.9 | 51.3 | 34.6 | 84.3 | 93.8 | 64.6 | 34.9 |
| hrnet_w48_ocr | cityscapes_to_railsem19_to_rtis | 51.2 | 40.9 | 55.8 | 5.2 | 45.5 | 5.5 | 61.1 | 97.0 | 75.9 | 6.7 |
| hrnet_w48_ocr | cityscapes_to_rtis | 48.0 | 35.5 | 56.9 | 8.1 | 39.9 | 8.4 | 72.7 | 95.3 | 58.1 | 12.5 |
| hrnet_w48_ocr | railsem19_to_rtis | 55.7 | 44.9 | 54.0 | 7.1 | 42.4 | 7.5 | 67.5 | 99.7 | 65.2 | 8.3 |
| hrnet_w48_ocr | rtis_only | 53.1 | 34.8 | 61.1 | 6.5 | 45.7 | 6.2 | 84.6 | 95.8 | 59.5 | 7.2 |
| native_convnext_tiny_uper | cityscapes_to_railsem19_to_rtis | 57.0 | 43.8 | 59.6 | 11.1 | 43.2 | 11.2 | 81.4 | 98.4 | 62.8 | 12.1 |
| native_convnext_tiny_uper | cityscapes_to_rtis | 52.0 | 38.9 | 59.9 | 4.1 | 43.6 | 3.7 | 78.8 | 97.6 | 58.6 | 3.6 |
| native_convnext_tiny_uper | railsem19_to_rtis | 56.8 | 44.2 | 59.0 | 5.4 | 43.7 | 5.6 | 77.0 | 98.4 | 59.6 | 4.7 |
| native_convnext_tiny_uper | rtis_only | 51.1 | 28.8 | 64.9 | 11.1 | 53.3 | 11.7 | 81.0 | 92.5 | 69.5 | 13.5 |
| segformer_b2 | cityscapes_to_railsem19_to_rtis | 52.4 | 42.0 | 63.1 | 17.3 | 49.9 | 16.9 | 90.2 | 97.8 | 60.0 | 17.3 |
| segformer_b2 | cityscapes_to_rtis | 42.9 | 38.5 | 51.5 | 22.2 | 30.2 | 23.1 | 84.8 | 86.0 | 36.2 | 24.6 |
| segformer_b2 | railsem19_to_rtis | 56.2 | 46.4 | 64.7 | 11.7 | 51.6 | 11.9 | 81.4 | 98.2 | 66.4 | 13.3 |
| segformer_b2 | rtis_only | 52.0 | 37.2 | 68.8 | 19.2 | 59.2 | 20.0 | 82.1 | 97.7 | 78.4 | 20.6 |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | 54.7 | 44.4 | 68.4 | 21.4 | 60.0 | 22.6 | 89.5 | 97.0 | 72.8 | 26.6 |
| segformer_b5 | cityscapes_to_rtis | 50.8 | 39.8 | 64.6 | 21.6 | 51.9 | 22.8 | 83.0 | 94.2 | 65.5 | 29.1 |
| segformer_b5 | railsem19_to_rtis | 58.8 | 47.6 | 63.3 | 13.6 | 50.6 | 14.3 | 78.1 | 98.1 | 67.3 | 14.9 |
| segformer_b5 | rtis_only | 53.1 | 37.2 | 69.3 | 11.9 | 60.0 | 12.4 | 88.8 | 94.7 | 72.9 | 15.6 |
| smp_deeplabv3plus_resnet101 | cityscapes_to_railsem19_to_rtis | 50.7 | 37.3 | 65.3 | 5.4 | 47.2 | 5.6 | 83.5 | 91.7 | 59.4 | 8.1 |
| smp_deeplabv3plus_resnet101 | cityscapes_to_rtis | 48.0 | 24.4 | 56.6 | 4.4 | 38.2 | 4.6 | 80.2 | 32.9 | 57.8 | 6.2 |
| smp_deeplabv3plus_resnet101 | railsem19_to_rtis | 54.6 | 42.5 | 54.9 | 13.4 | 36.3 | 13.9 | 81.9 | 86.4 | 56.3 | 15.9 |
| smp_deeplabv3plus_resnet101 | rtis_only | 35.0 | 30.6 | 43.9 | 15.3 | 16.6 | 15.6 | 77.6 | 85.7 | 16.1 | 18.8 |
| smp_fpn_resnet50 | cityscapes_to_railsem19_to_rtis | 49.4 | 37.8 | 50.1 | 12.1 | 34.3 | 12.1 | 87.0 | 86.2 | 43.2 | 16.2 |
| smp_fpn_resnet50 | cityscapes_to_rtis | 46.3 | 31.5 | 42.1 | 9.1 | 14.0 | 9.0 | 92.6 | 87.2 | 19.7 | 9.3 |
| smp_fpn_resnet50 | railsem19_to_rtis | 53.1 | 43.4 | 59.2 | 15.5 | 43.3 | 16.2 | 81.8 | 92.7 | 59.8 | 21.2 |
| smp_fpn_resnet50 | rtis_only | 43.7 | 23.5 | 53.9 | 9.4 | 31.3 | 9.8 | 70.7 | 66.7 | 49.0 | 11.3 |
| smp_upernet_resnet101 | cityscapes_to_railsem19_to_rtis | 49.8 | 35.8 | 54.6 | 15.8 | 33.0 | 16.2 | 79.2 | 89.3 | 48.4 | 20.0 |
| smp_upernet_resnet101 | cityscapes_to_rtis | 41.7 | 28.7 | 48.9 | 20.5 | 25.0 | 21.5 | 65.1 | 73.6 | 43.1 | 29.7 |
| smp_upernet_resnet101 | railsem19_to_rtis | 52.5 | 33.6 | 56.0 | 9.6 | 38.4 | 9.9 | 73.2 | 83.4 | 62.8 | 12.9 |
| smp_upernet_resnet101 | rtis_only | 49.0 | 26.5 | 63.4 | 6.9 | 51.0 | 7.3 | 75.9 | 74.7 | 70.9 | 8.5 |
| upernet_convnext | cityscapes_to_railsem19_to_rtis | 56.9 | 40.2 | 57.9 | 5.6 | 38.4 | 5.8 | 77.4 | 91.2 | 56.2 | 6.0 |
| upernet_convnext | cityscapes_to_rtis | 53.6 | 35.2 | 59.5 | 14.3 | 42.2 | 15.0 | 77.2 | 84.9 | 61.2 | 18.2 |
| upernet_convnext | railsem19_to_rtis | 57.2 | 43.4 | 56.2 | 13.3 | 36.2 | 14.0 | 80.2 | 67.5 | 53.3 | 14.4 |
| upernet_convnext | rtis_only | 54.5 | 38.8 | 64.5 | 10.3 | 50.9 | 10.6 | 79.5 | 85.6 | 68.9 | 12.1 |

### Arm effects

Differences in IoU points for model x protocol pairs completed in both arms, single seed, no uncertainty. Split = FG - P: different labels, val images and train images (the label part is small on average but up to about 5 points per run; see How to read this).

| model | protocol | effect | mIoU | mud IoU | mud IoU cab | mud precision cab | mud recall cab |
|---|---|---:|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | split | -13.7 | -52.4 | -36.5 | +16.4 | -48.1 |
| eomt_dinov3_large | cityscapes_to_rtis | split | -7.0 | -17.9 | +4.2 | +4.4 | -0.0 |
| eomt_dinov3_large | railsem19_to_rtis | split | -8.4 | -32.9 | -19.2 | +11.1 | -26.0 |
| eomt_dinov3_large | rtis_only | split | -12.0 | -26.3 | -10.1 | +11.9 | -22.3 |
| eomt_large | cityscapes_to_railsem19_to_rtis | split | -11.7 | -30.7 | -15.3 | +4.3 | -26.4 |
| eomt_large | cityscapes_to_rtis | split | -8.7 | -37.2 | -21.7 | +8.1 | -34.1 |
| eomt_large | railsem19_to_rtis | split | -12.9 | -54.4 | -39.1 | +9.3 | -52.4 |
| eomt_large | rtis_only | split | -11.7 | -31.9 | -16.7 | +9.6 | -29.7 |
| hrnet_w48_ocr | cityscapes_to_railsem19_to_rtis | split | -10.3 | -50.6 | -40.0 | +36.0 | -69.2 |
| hrnet_w48_ocr | cityscapes_to_rtis | split | -12.4 | -48.8 | -31.6 | +22.6 | -45.6 |
| hrnet_w48_ocr | railsem19_to_rtis | split | -10.8 | -46.8 | -35.0 | +32.2 | -56.9 |
| hrnet_w48_ocr | rtis_only | split | -18.3 | -54.6 | -39.5 | +11.2 | -52.4 |
| native_convnext_tiny_uper | cityscapes_to_railsem19_to_rtis | split | -13.2 | -48.5 | -32.0 | +17.0 | -50.7 |
| native_convnext_tiny_uper | cityscapes_to_rtis | split | -13.1 | -55.8 | -39.8 | +18.8 | -55.0 |
| native_convnext_tiny_uper | railsem19_to_rtis | split | -12.6 | -53.6 | -38.1 | +21.3 | -54.9 |
| native_convnext_tiny_uper | rtis_only | split | -22.2 | -53.9 | -41.5 | +11.5 | -56.1 |
| segformer_b2 | cityscapes_to_railsem19_to_rtis | split | -10.4 | -45.8 | -32.9 | +7.6 | -42.7 |
| segformer_b2 | cityscapes_to_rtis | split | -4.3 | -29.3 | -7.1 | +1.2 | -11.6 |
| segformer_b2 | railsem19_to_rtis | split | -9.8 | -53.0 | -39.7 | +16.7 | -53.1 |
| segformer_b2 | rtis_only | split | -14.9 | -49.5 | -39.2 | +15.6 | -57.8 |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | split | -10.4 | -47.0 | -37.4 | +7.5 | -46.2 |
| segformer_b5 | cityscapes_to_rtis | split | -11.0 | -43.0 | -29.1 | +11.2 | -36.4 |
| segformer_b5 | railsem19_to_rtis | split | -11.2 | -49.7 | -36.3 | +20.0 | -52.4 |
| segformer_b5 | rtis_only | split | -15.9 | -57.4 | -47.6 | +5.9 | -57.3 |
| smp_deeplabv3plus_resnet101 | cityscapes_to_railsem19_to_rtis | split | -13.4 | -59.9 | -41.7 | +8.1 | -51.3 |
| smp_deeplabv3plus_resnet101 | cityscapes_to_rtis | split | -23.6 | -52.3 | -33.6 | -47.3 | -51.6 |
| smp_deeplabv3plus_resnet101 | railsem19_to_rtis | split | -12.1 | -41.5 | -22.4 | +4.5 | -40.4 |
| smp_deeplabv3plus_resnet101 | rtis_only | split | -4.4 | -28.6 | -1.0 | +8.1 | +2.7 |
| smp_fpn_resnet50 | cityscapes_to_railsem19_to_rtis | split | -11.5 | -38.0 | -22.1 | -0.8 | -27.0 |
| smp_fpn_resnet50 | cityscapes_to_rtis | split | -14.8 | -33.0 | -5.0 | -5.4 | -10.4 |
| smp_fpn_resnet50 | railsem19_to_rtis | split | -9.6 | -43.7 | -27.1 | +10.9 | -38.6 |
| smp_fpn_resnet50 | rtis_only | split | -20.2 | -44.5 | -21.5 | -4.0 | -37.7 |
| smp_upernet_resnet101 | cityscapes_to_railsem19_to_rtis | split | -14.0 | -38.8 | -16.8 | +10.1 | -28.4 |
| smp_upernet_resnet101 | cityscapes_to_rtis | split | -13.1 | -28.4 | -3.5 | +8.5 | -13.4 |
| smp_upernet_resnet101 | railsem19_to_rtis | split | -18.8 | -46.4 | -28.5 | +10.2 | -49.9 |
| smp_upernet_resnet101 | rtis_only | split | -22.5 | -56.5 | -43.8 | -1.3 | -62.5 |
| upernet_convnext | cityscapes_to_railsem19_to_rtis | split | -16.6 | -52.3 | -32.6 | +13.8 | -50.2 |
| upernet_convnext | cityscapes_to_rtis | split | -18.4 | -45.2 | -27.2 | +7.7 | -43.0 |
| upernet_convnext | railsem19_to_rtis | split | -13.8 | -42.8 | -22.2 | -12.7 | -38.9 |
| upernet_convnext | rtis_only | split | -15.7 | -54.2 | -40.3 | +6.1 | -56.8 |

### Validation composition (labels only)

Images / images with mud GT / share of the split's mud GT pixels, by viewpoint.

| arm | images | cab-view | track-level | other | mud GT px | trackside-maintenance mud share % |
|---|---|---:|---:|---:|---:|---:|
| paul | 37 | 28 / 7 / 4.9% | 8 / 6 / 95.1% | 1 / 0 / 0.0% | 7,435,760 | 94.9 |
| fixed-grouped | 37 | 27 / 17 / 98.9% | 9 / 1 / 1.1% | 1 / 0 / 0.0% | 1,226,250 | 0.0 |

### Inputs

- viewpoints: `rad_9_24_2026-viewpoints.yaml (sha256 7dfc4f730cbe)`
- campaign fixed-grouped: [published arm](fixed-grouped/README.md); source `/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fixed-grouped-seed0-20261005-r2`
- campaign paul: [published arm](paul/README.md); source `/data/izadia1/projects/segmentary-runs/rad_9_24_2026/paul-seed0-20261005-r2`
- fork runs: `/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24/runs`
- samples paul: `sha256 2338c1e5cd84`
- samples fixed-grouped: `sha256 46e5b404cb1e`

Every subset metric of every completed job is in `rad-comparison.csv` (subsets `all`, `cab-view`, `not-cab-view`, `excl-trackside-maintenance`).

## Paper-recipe fork runs

Paul Stanik's two paper recipes (HRNet-OCR-Mscale `pauls3/semantic-segmentation@5e619e6`, SFNet-R18 `pauls3/SFSegNets-2@0bb9e59`), retrained by us with his fork code on the same two arms: every RAD stage (`rad:ours`) is trained by us, and earlier stages may start from Paul's or public checkpoints. The run label states the init chain; checkpoint owners name who trained each stage (`paul` = Paul's checkpoint, `ours` = trained by us, `nvidia` / `public-sfnet-authors` = public). The `arm-<arm>` part of a label is the RAD dataset arm, not an owner.

**Scored** runs use Segmentary's metric code on our val split (`score_predictions.py`, whole-image single-scale) and are comparable with the campaign tables above. **In-training** numbers are the fork's own validation printout (multi-scale fork evaluator, its own class handling, epoch picked on the same val split): progress only, **not comparable** with any scored number. Epoch numbers are the fork's own 0-based indices. RS19-stage runs (pretraining on RailSem19) show their status only: their printouts are not RAD validation numbers.

| label | arm | checkpoint owners | status | scored: mIoU / mud IoU / mud IoU cab / mud precision cab / mud recall cab | fork's own in-training best (not comparable) |
| --- | --- | --- | --- | --- | --- |
| `paper-hrnet__rs19-paul__arm-fixed-grouped` | fixed-grouped | map_city:nvidia -> rs19:paul -> rad:ours | scored (val) | 46.0 / 15.4 / 16.2 / 88.9 / 21.2 | — |
| `paper-hrnet__rs19-paul__arm-paul` | paul | map_city:nvidia -> rs19:paul -> rad:ours | scored (val) | 60.3 / 63.7 / 52.4 / 78.7 / 69.0 | — |
| `hrnet-rs19-ours` | — (RS19 stage) | — | queue: pending | — | — |
| `paper-hrnet__mapcity-direct__arm-fixed-grouped` | fixed-grouped | — | queue: pending | — | — |
| `paper-hrnet__mapcity-direct__arm-paul` | paul | — | queue: pending | — | — |
| `paper-hrnet__rs19-ours__arm-fixed-grouped` | fixed-grouped | — | queue: pending | — | — |
| `paper-hrnet__rs19-ours__arm-paul` | paul | — | queue: pending | — | — |
| `paper-hrnet__rs19-paul__arm-fixed-grouped__recipe-train_2` | fixed-grouped | — | queue: pending | — | — |
| `paper-hrnet__rs19-paul__arm-paul` (run `probe2-paper-hrnet__rs19-paul__arm-paul`) | paul | map_city:nvidia -> rs19:paul -> rad:ours | excluded (probe_epochs) | — | — |
| `paper-hrnet__rs19-paul__arm-paul__recipe-train_2` | paul | — | queue: pending | — | — |
| `paper-sfnet__mapcity-direct__arm-fixed-grouped` | fixed-grouped | — | queue: pending | — | — |
| `paper-sfnet__mapcity-direct__arm-paul` | paul | — | queue: pending | — | — |
| `paper-sfnet__rs19-ours__arm-fixed-grouped` | fixed-grouped | — | queue: pending | — | — |
| `paper-sfnet__rs19-ours__arm-paul` | paul | — | queue: pending | — | — |
| `sfnet-rs19-ours` | — (RS19 stage) | — | queue: pending | — | — |

`paul-reference__rr22-0.8964` (Paul's finished RAD model) may have trained on our val/test images and is never scored on our splits. Deviations from Paul's protocol are recorded in each run's `provenance.json` on HDRFS.

## About this page

Generated by `scripts/publish_rad_results.py` from the HDRFS campaign records, the prepared datasets and the fork run directories, which it only reads. Absolute paths are provenance on HDRFS, not links. Prediction masks are not published.

- Publisher code: `ac2501a83780`
- Campaign records last changed: 2026-10-05 09:27 PM PDT
