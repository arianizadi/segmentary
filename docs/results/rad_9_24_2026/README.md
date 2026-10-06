# RAD 9/24 study: split policy and Paul Stanik's paper recipes

The `rad_9_24_2026` delivery (314 rail images with polygon labels) trained two ways with the same 10-model x 4-initialization-path catalog (40 jobs per arm, seed 0, checkpoint selection and early stopping on validation mud-pumping IoU), plus Paul Stanik's two paper recipes, retrained by us with his fork code. The question: how much does Paul's random stratified split flatter the results compared with a scene-grouped split (`paul` vs `fixed-grouped`)? The two arms also differ in labels. A third arm with our re-rendered masks on the stratified split was stopped on 2026-10-05 at 8 of 40 jobs: over 8 matched eomt runs the label fix changed cab-view mud IoU on stratified val by -3.3 to +4.7 points, -0.1 on average. Validation only; the test split is held out and never read.

[Dataset preparation and split decisions](../../guides/rad-9-24-2026.md) · [Comparison CSV](rad-comparison.csv)

## Arms and progress

| arm | labels | split; train/val/test | completed | other jobs | code |
| --- | --- | --- | --- | --- | --- |
| [`paul`](paul/README.md) | Paul's delivered `masks_machine` copies | stratified random (seed 0); 227/37/50 | 40/40 | — | `d864b72bd907` |
| [`fixed-grouped`](fixed-grouped/README.md) | re-rendered from the polygon JSONs | scene-grouped (from v1/v2); 217/37/60 | 40/40 | — | `d864b72bd907` |

Each arm page has the per-model reports, `results.csv`, `status.json` and the downloadable evidence exactly as for [RTIS v2](../paul-test-rtis/v2/README.md). Fork progress is in the [paper-recipe section](#paper-recipe-fork-runs).

## Caveats

- **Single seed.** Every result is one training run (seed 0); there are no repeats or confidence intervals, so differences of a few IoU points are not established.
- **Optimistic validation numbers.** Checkpoints are selected (and training early stopped) on the same val split that is reported; fork runs pick their epoch on it too.
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

All numbers are on the validation split (paul 37, fixed-grouped 37 images); the test split is never read. Mud IoU is pixel-aggregated: confusions are summed over the subset's images first, so a few images with large mud areas decide it. The image-mean mud IoU averages per-image IoU over the images that have mud ground truth (false-positive mud on images without mud GT only lowers the pixel-aggregated IoU). GT-class mIoU is the campaign's `fixed_miou` rule (mean over classes with ground truth in the subset). `n=` in a column header is the number of val images with mud GT behind that arm's mud IoU.

**Arms.** All campaign models are trained by us. `paul` = Paul's delivered masks (the `masks_machine` copies) with the stratified split; `fixed-grouped` = our re-rendered masks with the scene-grouped split. P / FG below name these label/split arms, not who trained the model. A third arm with our re-rendered masks on the stratified split was stopped on 2026-10-05 at 8 of 40 jobs: over 8 matched eomt runs the label fix changed cab-view mud IoU on stratified val by -3.3 to +4.7 points, -0.1 on average.

**Caveats.**

- **These val numbers are optimistic.** The reported checkpoint is the one selected on this same val split (campaign selection and early stopping on `val_iou/mud-pumping`); fork runs report their `best_mud_epoch` checkpoint, also chosen on this val split. They are not held-out estimates, mud IoU least of all.
- **Single seed, no uncertainty.** Every campaign result is seed 0; there are no repeats or confidence intervals, and the subsets are small (see `n=`), so differences of a few IoU points between models or arms are not established.
- **The stratified split's pixel-aggregated mud IoU is dominated by 5 track-level close-ups from the `trackside-maintenance` scene group.** On the stratified val split (`paul` masks) 6 track-level images with mud GT hold 95.1% of all mud GT pixels and 7 cab-view images 4.9%; the `trackside-maintenance` scene group alone holds 94.9%, and the five largest images (`trackside-maintenance/0071`, `trackside-maintenance/0076`, `trackside-maintenance/0081`, `trackside-maintenance/0089`, `trackside-maintenance/0091`) 94.9%. Scene groups are directory layout names assigned from visual evidence, not confirmed recording provenance.
- On the grouped val split 17 cab-view images with mud GT hold 98.9% of the mud GT pixels, so its `all` and `cab-view` mud IoU nearly coincide. All 17 come from the `rural-overcast-cab-view` scene group; judged visually, a forward view centred on the track from a moving vehicle, but from a camera visibly lower than a locomotive cab (the ballast fills the lower frame; more like a front-bumper or draisine mount). The grouped arm's cab-view mud numbers therefore mostly measure that one camera setup.
- **`cab-view` is the deployment-relevant subset** (a camera on a moving train). Compare arms and models on mud IoU (cab-view) and image-mean mud IoU (cab-view); read `all` with the composition above in mind.
- Viewpoints come from `configs/datasets/rad_9_24_2026-viewpoints.yaml`, joined by image SHA-256: visual judgement only, from two labelling passes by AI model subagents with adjudication of disagreements. Both passes are the same model, so their agreement is not evidence from independent annotators.
- `paul` vs `fixed-grouped` changes **both** the labels and the split policy. The stopped label-fix arm (above) found the label part small on average but -3.3 to +4.7 points per run, measured on eomt models and stratified val only, so a model's FG - P difference within that range cannot be attributed to the split. The val sets are different images and the train sets differ too (227 vs 217 train images, 158 in common), so the difference mixes the training data, model generalisation and val composition. On the stratified split 17 of its 17 val scene groups also have train images; on the grouped split 0 of 3 do (scene groups are visually assigned, not confirmed recordings).
- Fork labels: in `paper-hrnet__rs19-paul__arm-paul`, `rs19-paul` means the RS19 stage uses Paul's checkpoint and `arm-paul` means the RAD stage trains on the `paul` arm (Paul's masks); the checkpoint owners column spells out who trained each stage.

### Headline: Segmentary campaign models

Percent; columns per arm: P = `paul`, FG = `fixed-grouped`. Selected checkpoint `best-auto-val`. Empty = job not completed.

| model | protocol | GT-class mIoU P | GT-class mIoU FG | mud IoU P (n=13) | mud IoU FG (n=18) | mud IoU cab P (n=7) | mud IoU cab FG (n=17) | img-mean mud IoU cab P (n=7) | img-mean mud IoU cab FG (n=17) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | 70.2 | 52.3 | 89.1 | 8.2 | 38.9 | 12.1 | 48.0 | 11.5 |
| eomt_dinov3_large | cityscapes_to_rtis | 65.9 | 51.4 | 85.8 | 10.6 | 26.4 | 42.3 | 37.2 | 41.4 |
| eomt_dinov3_large | railsem19_to_rtis | 70.6 | 58.3 | 89.9 | 18.8 | 39.7 | 37.2 | 53.3 | 34.2 |
| eomt_dinov3_large | rtis_only | 68.3 | 48.7 | 90.8 | 8.7 | 41.9 | 40.7 | 49.2 | 39.1 |
| eomt_large | cityscapes_to_railsem19_to_rtis | 72.2 | 58.2 | 93.5 | 15.7 | 46.0 | 34.6 | 51.9 | 36.5 |
| eomt_large | cityscapes_to_rtis | 71.0 | 56.4 | 92.7 | 9.4 | 40.3 | 25.3 | 50.5 | 28.7 |
| eomt_large | railsem19_to_rtis | 72.8 | 58.0 | 95.0 | 3.3 | 50.7 | 10.4 | 49.3 | 10.3 |
| eomt_large | rtis_only | 70.3 | 53.2 | 92.5 | 12.7 | 42.6 | 33.6 | 51.3 | 34.6 |
| hrnet_w48_ocr | cityscapes_to_railsem19_to_rtis | 55.4 | 49.6 | 75.5 | 6.5 | 34.1 | 6.6 | 45.5 | 5.5 |
| hrnet_w48_ocr | cityscapes_to_rtis | 56.9 | 40.1 | 85.8 | 12.0 | 33.9 | 12.2 | 39.9 | 8.4 |
| hrnet_w48_ocr | railsem19_to_rtis | 61.1 | 51.3 | 76.7 | 2.4 | 46.3 | 8.2 | 42.4 | 7.5 |
| hrnet_w48_ocr | rtis_only | 59.8 | 37.2 | 90.8 | 3.6 | 49.3 | 7.0 | 45.7 | 6.2 |
| native_convnext_tiny_uper | cityscapes_to_railsem19_to_rtis | 64.2 | 49.0 | 90.5 | 9.1 | 45.0 | 12.0 | 43.2 | 11.2 |
| native_convnext_tiny_uper | cityscapes_to_rtis | 60.5 | 41.1 | 89.4 | 3.1 | 45.2 | 3.6 | 43.6 | 3.7 |
| native_convnext_tiny_uper | railsem19_to_rtis | 64.1 | 49.5 | 88.4 | 2.1 | 48.5 | 4.7 | 43.7 | 5.6 |
| native_convnext_tiny_uper | rtis_only | 60.5 | 29.2 | 88.8 | 6.9 | 47.5 | 13.3 | 53.3 | 11.7 |
| segformer_b2 | cityscapes_to_railsem19_to_rtis | 64.4 | 47.6 | 89.2 | 15.9 | 42.7 | 16.6 | 49.9 | 16.9 |
| segformer_b2 | cityscapes_to_rtis | 54.2 | 45.1 | 87.3 | 16.8 | 29.7 | 23.1 | 30.2 | 23.1 |
| segformer_b2 | railsem19_to_rtis | 66.4 | 52.7 | 93.2 | 6.1 | 57.0 | 13.1 | 51.6 | 11.9 |
| segformer_b2 | rtis_only | 58.2 | 39.8 | 93.1 | 10.1 | 58.7 | 19.9 | 59.2 | 20.0 |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | 65.1 | 50.3 | 91.2 | 5.0 | 61.9 | 25.2 | 60.0 | 22.6 |
| segformer_b5 | cityscapes_to_rtis | 59.1 | 44.2 | 91.3 | 4.7 | 46.8 | 26.9 | 51.9 | 22.8 |
| segformer_b5 | railsem19_to_rtis | 69.5 | 53.9 | 90.4 | 5.6 | 55.2 | 14.7 | 50.6 | 14.3 |
| segformer_b5 | rtis_only | 59.1 | 41.7 | 93.1 | 5.2 | 53.4 | 14.9 | 60.0 | 12.4 |
| smp_deeplabv3plus_resnet101 | cityscapes_to_railsem19_to_rtis | 56.9 | 40.9 | 85.4 | 3.7 | 39.9 | 8.0 | 47.2 | 5.6 |
| smp_deeplabv3plus_resnet101 | cityscapes_to_rtis | 55.7 | 23.6 | 89.6 | 1.4 | 45.6 | 3.4 | 38.2 | 4.6 |
| smp_deeplabv3plus_resnet101 | railsem19_to_rtis | 62.4 | 49.2 | 87.7 | 5.6 | 47.2 | 13.7 | 36.3 | 13.9 |
| smp_deeplabv3plus_resnet101 | rtis_only | 41.3 | 30.2 | 85.9 | 6.6 | 12.1 | 10.8 | 16.6 | 15.6 |
| smp_fpn_resnet50 | cityscapes_to_railsem19_to_rtis | 57.0 | 41.1 | 74.0 | 14.4 | 38.7 | 15.8 | 34.3 | 12.1 |
| smp_fpn_resnet50 | cityscapes_to_rtis | 55.5 | 32.2 | 85.3 | 8.2 | 18.4 | 9.1 | 14.0 | 9.0 |
| smp_fpn_resnet50 | railsem19_to_rtis | 60.3 | 48.8 | 89.9 | 12.8 | 47.4 | 20.7 | 43.3 | 16.2 |
| smp_fpn_resnet50 | rtis_only | 52.5 | 22.4 | 89.2 | 4.8 | 38.1 | 10.3 | 31.3 | 9.8 |
| smp_upernet_resnet101 | cityscapes_to_railsem19_to_rtis | 55.5 | 37.3 | 87.6 | 15.9 | 28.1 | 19.3 | 33.0 | 16.2 |
| smp_upernet_resnet101 | cityscapes_to_rtis | 49.4 | 26.1 | 85.2 | 16.3 | 24.9 | 25.5 | 25.0 | 21.5 |
| smp_upernet_resnet101 | railsem19_to_rtis | 57.4 | 35.2 | 86.0 | 8.7 | 42.7 | 12.4 | 38.4 | 9.9 |
| smp_upernet_resnet101 | rtis_only | 54.8 | 25.6 | 87.5 | 6.8 | 37.5 | 8.1 | 51.0 | 7.3 |
| upernet_convnext | cityscapes_to_railsem19_to_rtis | 67.2 | 44.2 | 92.6 | 2.4 | 42.3 | 5.9 | 38.4 | 5.8 |
| upernet_convnext | cityscapes_to_rtis | 62.6 | 36.2 | 89.2 | 3.2 | 38.3 | 17.5 | 42.2 | 15.0 |
| upernet_convnext | railsem19_to_rtis | 66.1 | 49.4 | 88.3 | 7.8 | 40.1 | 13.4 | 36.2 | 14.0 |
| upernet_convnext | rtis_only | 61.5 | 42.1 | 91.7 | 4.7 | 50.6 | 11.7 | 50.9 | 10.6 |

### Arm effects

Differences in IoU points for model x protocol pairs completed in both arms, single seed, no uncertainty. Split = FG - P: different labels, val images and train images (the label part is small on average but up to about 5 points per run; see How to read this).

| model | protocol | effect | GT-class mIoU | mud IoU | mud IoU cab | img-mean mud IoU cab |
|---|---|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | split | -17.9 | -80.9 | -26.8 | -36.5 |
| eomt_dinov3_large | cityscapes_to_rtis | split | -14.4 | -75.2 | +16.0 | +4.2 |
| eomt_dinov3_large | railsem19_to_rtis | split | -12.3 | -71.0 | -2.5 | -19.2 |
| eomt_dinov3_large | rtis_only | split | -19.6 | -82.2 | -1.1 | -10.1 |
| eomt_large | cityscapes_to_railsem19_to_rtis | split | -14.0 | -77.8 | -11.3 | -15.3 |
| eomt_large | cityscapes_to_rtis | split | -14.6 | -83.3 | -15.0 | -21.7 |
| eomt_large | railsem19_to_rtis | split | -14.8 | -91.6 | -40.3 | -39.1 |
| eomt_large | rtis_only | split | -17.2 | -79.7 | -9.0 | -16.7 |
| hrnet_w48_ocr | cityscapes_to_railsem19_to_rtis | split | -5.8 | -69.0 | -27.5 | -40.0 |
| hrnet_w48_ocr | cityscapes_to_rtis | split | -16.8 | -73.8 | -21.6 | -31.6 |
| hrnet_w48_ocr | railsem19_to_rtis | split | -9.8 | -74.3 | -38.1 | -35.0 |
| hrnet_w48_ocr | rtis_only | split | -22.6 | -87.3 | -42.4 | -39.5 |
| native_convnext_tiny_uper | cityscapes_to_railsem19_to_rtis | split | -15.2 | -81.4 | -33.0 | -32.0 |
| native_convnext_tiny_uper | cityscapes_to_rtis | split | -19.4 | -86.3 | -41.6 | -39.8 |
| native_convnext_tiny_uper | railsem19_to_rtis | split | -14.6 | -86.4 | -43.8 | -38.1 |
| native_convnext_tiny_uper | rtis_only | split | -31.2 | -81.9 | -34.2 | -41.5 |
| segformer_b2 | cityscapes_to_railsem19_to_rtis | split | -16.8 | -73.3 | -26.1 | -32.9 |
| segformer_b2 | cityscapes_to_rtis | split | -9.1 | -70.5 | -6.5 | -7.1 |
| segformer_b2 | railsem19_to_rtis | split | -13.7 | -87.1 | -43.9 | -39.7 |
| segformer_b2 | rtis_only | split | -18.4 | -83.0 | -38.9 | -39.2 |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | split | -14.8 | -86.2 | -36.7 | -37.4 |
| segformer_b5 | cityscapes_to_rtis | split | -14.9 | -86.7 | -19.9 | -29.1 |
| segformer_b5 | railsem19_to_rtis | split | -15.7 | -84.8 | -40.5 | -36.3 |
| segformer_b5 | rtis_only | split | -17.5 | -87.9 | -38.5 | -47.6 |
| smp_deeplabv3plus_resnet101 | cityscapes_to_railsem19_to_rtis | split | -15.9 | -81.7 | -31.9 | -41.7 |
| smp_deeplabv3plus_resnet101 | cityscapes_to_rtis | split | -32.1 | -88.3 | -42.2 | -33.6 |
| smp_deeplabv3plus_resnet101 | railsem19_to_rtis | split | -13.1 | -82.0 | -33.6 | -22.4 |
| smp_deeplabv3plus_resnet101 | rtis_only | split | -11.1 | -79.2 | -1.3 | -1.0 |
| smp_fpn_resnet50 | cityscapes_to_railsem19_to_rtis | split | -15.8 | -59.6 | -23.0 | -22.1 |
| smp_fpn_resnet50 | cityscapes_to_rtis | split | -23.4 | -77.0 | -9.3 | -5.0 |
| smp_fpn_resnet50 | railsem19_to_rtis | split | -11.5 | -77.1 | -26.7 | -27.1 |
| smp_fpn_resnet50 | rtis_only | split | -30.1 | -84.4 | -27.8 | -21.5 |
| smp_upernet_resnet101 | cityscapes_to_railsem19_to_rtis | split | -18.2 | -71.7 | -8.8 | -16.8 |
| smp_upernet_resnet101 | cityscapes_to_rtis | split | -23.3 | -68.8 | +0.6 | -3.5 |
| smp_upernet_resnet101 | railsem19_to_rtis | split | -22.3 | -77.4 | -30.3 | -28.5 |
| smp_upernet_resnet101 | rtis_only | split | -29.2 | -80.7 | -29.4 | -43.8 |
| upernet_convnext | cityscapes_to_railsem19_to_rtis | split | -23.0 | -90.2 | -36.5 | -32.6 |
| upernet_convnext | cityscapes_to_rtis | split | -26.4 | -86.0 | -20.8 | -27.2 |
| upernet_convnext | railsem19_to_rtis | split | -16.7 | -80.5 | -26.7 | -22.2 |
| upernet_convnext | rtis_only | split | -19.4 | -87.0 | -38.8 | -40.3 |

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

| label | arm | checkpoint owners | status | scored: GT-class mIoU / mud IoU / mud IoU cab / img-mean mud IoU cab | fork's own in-training best (not comparable) |
| --- | --- | --- | --- | --- | --- |
| `paper-hrnet__rs19-paul__arm-paul` | paul | map_city:nvidia -> rs19:paul -> rad:ours | scored (val) | 65.4 / 88.1 / 47.0 / 52.4 | — |
| `paper-hrnet__rs19-paul__arm-fixed-grouped` | fixed-grouped | map_city:nvidia -> rs19:paul -> rad:ours | training, epoch 392 (0-based, of 1000) | — | mud IoU 8.6 @ epoch 344; mIoU 46.4 @ epoch 387 |
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

- Publisher code: `e29c74ade580`
- Campaign records last changed: 2026-10-06 04:27 UTC
