# RAD 9/24 study: full details

[Short summary](README.md) · [Mud IoU case document](../../guides/rad-9-24-2026-mud-iou-case.md)

The `rad_9_24_2026` delivery (314 rail images with polygon labels) trained two ways, `paul` with 10 models (40 jobs, seed 0, checkpoint selection and early stopping on validation mud-pumping IoU with pixels pooled over all validation images); `fixed-grouped` with 41 models (149 jobs, seed 0, the final checkpoint after the full step budget, no early stopping), plus Paul Stanik's two paper recipes, retrained by us with his fork code. The [first scene-grouped run (10 models, best-on-validation checkpoint)](#first-scene-grouped-run-10-models-best-on-validation-checkpoint) is summarised below. The question: how much does Paul's random stratified split flatter the results compared with a scene-grouped split (`paul` vs `fixed-grouped`)? The two arms also differ in labels. A third arm with our re-rendered masks on the stratified split was stopped on 2026-10-05 at 8 of 40 jobs: over 8 matched eomt runs the label fix changed cab-view mud IoU (pixels pooled) on stratified val by -3.3 to +4.7 points, -0.1 on average. Validation only; the test split is held out and never read. Mud-pumping IoU and mIoU below count each class only on the validation images that contain it (see *How to read this*); the pixel-pooled numbers are in the CSV.

[Dataset preparation and split decisions](../../guides/rad-9-24-2026.md) · [Comparison CSV](rad-comparison.csv)

## Arms (splits) and progress

| arm | labels | split; train/val/test | completed | other jobs | code |
| --- | --- | --- | --- | --- | --- |
| [`paul`](paul/README.md) | Paul's delivered `masks_machine` copies | stratified random (seed 0); 227/37/50 | 40/40 | — | `d864b72bd907` |
| [`fixed-grouped`](fixed-grouped/README.md): 41 models, final checkpoint after the full training budget, shown | re-rendered from the polygon JSONs | scene-grouped (from v1/v2); 217/37/60 | 7/149 | queued 134, training 8 | `fce0ea0ac50b` |
| `fixed-grouped`: 10 models, best-on-validation checkpoint, superseded | re-rendered from the polygon JSONs | scene-grouped (from v1/v2); 217/37/60 | 40/40 | — | `d864b72bd907` |

Each arm page has the per-model reports, `results.csv`, `status.json` and the downloadable evidence exactly as for [RTIS v2](../paul-test-rtis/v2/README.md). Fork progress is in the [paper-recipe section](#paper-recipe-fork-runs).

## Caveats

- **Single seed.** Every result is one training run (seed 0); there are no repeats or confidence intervals, so differences of a few IoU points are not established.
- **Optimistic validation numbers.** For `paul` checkpoints are selected (and training early stopped) on the same val split that is reported, by the mud IoU with pixels pooled over all val images rather than the present-image mud IoU shown; fork runs pick their epoch on that split too. `fixed-grouped` reports the final checkpoint after the full step budget (no early stopping), so nothing is selected on the val split it is scored on.
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

- **Best-checkpoint val numbers are optimistic.** For `paul` (P) the reported checkpoint is the one selected on this same val split (campaign selection and early stopping on `val_iou/mud-pumping`, with pixels pooled over the whole split); fork runs report their `best_mud_epoch` checkpoint, also chosen on this val split. They are not held-out estimates, mud IoU least of all. `fixed-grouped` (FG) reports the final checkpoint (`final-auto-val`) after the full step budget, with no early stopping, so nothing is selected on its val images; it is still one val split, not a cross-validated estimate.
- **Single seed, no uncertainty.** Every campaign result is seed 0; there are no repeats or confidence intervals, and the subsets are small (see `n=`), so differences of a few IoU points between models or arms are not established.
- On the stratified val split (`paul` masks) 6 of the 13 images with mud GT are track-level and 7 cab-view; 5 come from the `trackside-maintenance` scene group. By pixels that group holds 94.9% of all mud GT and the five largest images (`trackside-maintenance/0071`, `trackside-maintenance/0076`, `trackside-maintenance/0081`, `trackside-maintenance/0089`, `trackside-maintenance/0091`) 94.9%, which decides only the pixel-pooled CSV columns. Scene groups are directory layout names assigned from visual evidence, not confirmed recording provenance.
- On the grouped val split 17 of the 18 images with mud GT are cab-view, so its `all` and `cab-view` mud IoU nearly coincide. All 17 cab-view ones come from the `rural-overcast-cab-view` scene group; judged visually, a forward view centred on the track from a moving vehicle, but from a camera visibly lower than a locomotive cab (the ballast fills the lower frame; more like a front-bumper or draisine mount). The grouped arm's cab-view mud numbers therefore mostly measure that one camera setup.
- **`cab-view` is the deployment-relevant subset** (a camera on a moving train). Compare arms and models on cab-view mud IoU; read `all` with the composition above in mind.
- Viewpoints come from `configs/datasets/rad_9_24_2026-viewpoints.yaml`, joined by image SHA-256: visual judgement only, from two labelling passes by AI model subagents with adjudication of disagreements. Both passes are the same model, so their agreement is not evidence from independent annotators.
- `paul` vs `fixed-grouped` changes **both** the labels and the split policy. The stopped label-fix arm (above) found the label part small on average but -3.3 to +4.7 points per run, measured on eomt models and stratified val only, so a model's FG - P difference within that range cannot be attributed to the split. The val sets are different images and the train sets differ too (227 vs 217 train images, 158 in common), so the difference mixes the training data, model generalisation and val composition. On the stratified split 17 of its 17 val scene groups also have train images; on the grouped split 0 of 3 do (scene groups are visually assigned, not confirmed recordings).
- Fork labels: in `paper-hrnet__rs19-paul__arm-paul`, `rs19-paul` means the RS19 stage uses Paul's checkpoint and `arm-paul` means the RAD stage trains on the `paul` arm (Paul's masks); the checkpoint owners column spells out who trained each stage.

### Headline: Segmentary campaign models

Percent; columns per arm: P = `paul`, FG = `fixed-grouped`. Checkpoint: P `best-auto-val` (selected on validation), FG `final-auto-val` (final checkpoint after the full step budget). Empty = job not completed.

| model | protocol | mIoU P | mIoU FG | mud IoU P (n=13) | mud IoU FG (n=18) | mud IoU cab P (n=7) | mud IoU cab FG (n=17) | mud precision cab P (n=7) | mud precision cab FG (n=17) | mud recall cab P (n=7) | mud recall cab FG (n=17) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bisenetv1_r18 | rtis_only |  | 28.9 |  | 7.7 |  | 7.8 |  | 95.0 |  | 11.8 |
| bisenetv2 | rtis_only |  | 19.3 |  | 3.9 |  | 4.0 |  | 95.4 |  | 5.9 |
| denseaspp121 | rtis_only |  | 37.5 |  | 9.8 |  | 10.1 |  | 92.4 |  | 14.8 |
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | 62.3 | 52.3 | 63.9 | 16.1 | 48.0 | 16.9 | 82.4 | 98.6 | 61.3 | 18.8 |
| eomt_dinov3_large | cityscapes_to_rtis | 56.7 | 51.3 | 57.1 | 39.5 | 37.2 | 41.7 | 83.6 | 90.2 | 47.1 | 46.4 |
| eomt_dinov3_large | railsem19_to_rtis | 64.0 | 55.6 | 65.4 | 28.0 | 53.3 | 29.2 | 85.3 | 97.6 | 64.2 | 32.8 |
| eomt_dinov3_large | rtis_only | 59.8 | 48.9 | 63.3 | 37.6 | 49.2 | 39.7 | 81.1 | 93.4 | 65.2 | 43.6 |
| eomt_large | cityscapes_to_railsem19_to_rtis | 64.2 |  | 65.6 |  | 51.9 |  | 87.9 |  | 65.0 |  |
| eomt_large | cityscapes_to_rtis | 61.7 |  | 64.5 |  | 50.5 |  | 87.8 |  | 62.0 |  |
| eomt_large | railsem19_to_rtis | 64.4 |  | 64.3 |  | 49.3 |  | 85.2 |  | 63.1 |  |
| eomt_large | rtis_only | 62.5 |  | 64.8 |  | 51.3 |  | 84.3 |  | 64.6 |  |
| hrnet_w48_ocr | cityscapes_to_railsem19_to_rtis | 51.2 |  | 55.8 |  | 45.5 |  | 61.1 |  | 75.9 |  |
| hrnet_w48_ocr | cityscapes_to_rtis | 48.0 |  | 56.9 |  | 39.9 |  | 72.7 |  | 58.1 |  |
| hrnet_w48_ocr | railsem19_to_rtis | 55.7 |  | 54.0 |  | 42.4 |  | 67.5 |  | 65.2 |  |
| hrnet_w48_ocr | rtis_only | 53.1 |  | 61.1 |  | 45.7 |  | 84.6 |  | 59.5 |  |
| native_convnext_tiny_uper | cityscapes_to_railsem19_to_rtis | 57.0 |  | 59.6 |  | 43.2 |  | 81.4 |  | 62.8 |  |
| native_convnext_tiny_uper | cityscapes_to_rtis | 52.0 |  | 59.9 |  | 43.6 |  | 78.8 |  | 58.6 |  |
| native_convnext_tiny_uper | railsem19_to_rtis | 56.8 |  | 59.0 |  | 43.7 |  | 77.0 |  | 59.6 |  |
| native_convnext_tiny_uper | rtis_only | 51.1 |  | 64.9 |  | 53.3 |  | 81.0 |  | 69.5 |  |
| segformer_b2 | cityscapes_to_railsem19_to_rtis | 52.4 |  | 63.1 |  | 49.9 |  | 90.2 |  | 60.0 |  |
| segformer_b2 | cityscapes_to_rtis | 42.9 |  | 51.5 |  | 30.2 |  | 84.8 |  | 36.2 |  |
| segformer_b2 | railsem19_to_rtis | 56.2 |  | 64.7 |  | 51.6 |  | 81.4 |  | 66.4 |  |
| segformer_b2 | rtis_only | 52.0 |  | 68.8 |  | 59.2 |  | 82.1 |  | 78.4 |  |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | 54.7 |  | 68.4 |  | 60.0 |  | 89.5 |  | 72.8 |  |
| segformer_b5 | cityscapes_to_rtis | 50.8 |  | 64.6 |  | 51.9 |  | 83.0 |  | 65.5 |  |
| segformer_b5 | railsem19_to_rtis | 58.8 |  | 63.3 |  | 50.6 |  | 78.1 |  | 67.3 |  |
| segformer_b5 | rtis_only | 53.1 |  | 69.3 |  | 60.0 |  | 88.8 |  | 72.9 |  |
| smp_deeplabv3plus_resnet101 | cityscapes_to_railsem19_to_rtis | 50.7 |  | 65.3 |  | 47.2 |  | 83.5 |  | 59.4 |  |
| smp_deeplabv3plus_resnet101 | cityscapes_to_rtis | 48.0 |  | 56.6 |  | 38.2 |  | 80.2 |  | 57.8 |  |
| smp_deeplabv3plus_resnet101 | railsem19_to_rtis | 54.6 |  | 54.9 |  | 36.3 |  | 81.9 |  | 56.3 |  |
| smp_deeplabv3plus_resnet101 | rtis_only | 35.0 |  | 43.9 |  | 16.6 |  | 77.6 |  | 16.1 |  |
| smp_fpn_resnet50 | cityscapes_to_railsem19_to_rtis | 49.4 |  | 50.1 |  | 34.3 |  | 87.0 |  | 43.2 |  |
| smp_fpn_resnet50 | cityscapes_to_rtis | 46.3 |  | 42.1 |  | 14.0 |  | 92.6 |  | 19.7 |  |
| smp_fpn_resnet50 | railsem19_to_rtis | 53.1 |  | 59.2 |  | 43.3 |  | 81.8 |  | 59.8 |  |
| smp_fpn_resnet50 | rtis_only | 43.7 |  | 53.9 |  | 31.3 |  | 70.7 |  | 49.0 |  |
| smp_upernet_resnet101 | cityscapes_to_railsem19_to_rtis | 49.8 |  | 54.6 |  | 33.0 |  | 79.2 |  | 48.4 |  |
| smp_upernet_resnet101 | cityscapes_to_rtis | 41.7 |  | 48.9 |  | 25.0 |  | 65.1 |  | 43.1 |  |
| smp_upernet_resnet101 | railsem19_to_rtis | 52.5 |  | 56.0 |  | 38.4 |  | 73.2 |  | 62.8 |  |
| smp_upernet_resnet101 | rtis_only | 49.0 |  | 63.4 |  | 51.0 |  | 75.9 |  | 70.9 |  |
| upernet_convnext | cityscapes_to_railsem19_to_rtis | 56.9 |  | 57.9 |  | 38.4 |  | 77.4 |  | 56.2 |  |
| upernet_convnext | cityscapes_to_rtis | 53.6 |  | 59.5 |  | 42.2 |  | 77.2 |  | 61.2 |  |
| upernet_convnext | railsem19_to_rtis | 57.2 |  | 56.2 |  | 36.2 |  | 80.2 |  | 53.3 |  |
| upernet_convnext | rtis_only | 54.5 |  | 64.5 |  | 50.9 |  | 79.5 |  | 68.9 |  |

### Arm effects

Differences in IoU points for model x protocol pairs completed in both arms, single seed, no uncertainty. Split = FG - P: different labels, val images and train images (the label part is small on average but up to about 5 points per run; see How to read this). The arms also report different checkpoints (P best, FG final), which the difference mixes in too.

| model | protocol | effect | mIoU | mud IoU | mud IoU cab | mud precision cab | mud recall cab |
|---|---|---:|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | split | -10.1 | -47.8 | -31.2 | +16.2 | -42.5 |
| eomt_dinov3_large | cityscapes_to_rtis | split | -5.4 | -17.6 | +4.5 | +6.6 | -0.7 |
| eomt_dinov3_large | railsem19_to_rtis | split | -8.4 | -37.3 | -24.2 | +12.3 | -31.4 |
| eomt_dinov3_large | rtis_only | split | -11.0 | -25.8 | -9.5 | +12.3 | -21.6 |

### Validation composition (labels only)

Images / images with mud GT / share of the split's mud GT pixels, by viewpoint.

| arm | images | cab-view | track-level | other | mud GT px | trackside-maintenance mud share % |
|---|---|---:|---:|---:|---:|---:|
| paul | 37 | 28 / 7 / 4.9% | 8 / 6 / 95.1% | 1 / 0 / 0.0% | 7,435,760 | 94.9 |
| fixed-grouped | 37 | 27 / 17 / 98.9% | 9 / 1 / 1.1% | 1 / 0 / 0.0% | 1,226,250 | 0.0 |

### Inputs

- viewpoints: `rad_9_24_2026-viewpoints.yaml (sha256 7dfc4f730cbe)`
- campaign fixed-grouped: [published arm](fixed-grouped/README.md); source `/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fgall-seed0-20261007`
- campaign paul: [published arm](paul/README.md); source `/data/izadia1/projects/segmentary-runs/rad_9_24_2026/paul-seed0-20261005-r2`
- fork runs: `/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24/runs`
- samples paul: `sha256 2338c1e5cd84`
- samples fixed-grouped: `sha256 46e5b404cb1e`

Every subset metric of every completed job is in `rad-comparison.csv` (subsets `all`, `cab-view`, `not-cab-view`, `excl-trackside-maintenance`).

## First scene-grouped run (10 models, best-on-validation checkpoint)

Source `/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fixed-grouped-seed0-20261005-r2` (code `d864b72bd907`), 40 of 40 runs done. Replaced on the study page by `fgall-seed0-20261007` (41 models, final checkpoint after the full training budget). Best starting point per model by train-camera mud-pumping IoU on the same validation images; the checkpoint itself was selected (and training early stopped) on those images, by the mud IoU with pixels pooled over all of them, so these numbers are optimistic. Percent, every class counted only on the images that contain it. [All its runs (CSV)](earlier-runs/fixed-grouped-seed0-20261005-r2.csv).

| Model | Best starting point | Mud-pumping IoU, train-camera images with mud | Mud-pumping IoU, all images with mud | mIoU (each class over images that contain it) | Speed (FPS) | GPU memory, total (GB) | Parameters (M) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| eomt_dinov3_large | Cityscapes | 41.4 | 39.2 | 49.7 | 37.3 | 3.36† | 314.9 |
| eomt_large | Cityscapes → RailSem19 | 36.5 | 34.9 | 52.5 | 45.5 | 3.35† | 316.6 |
| segformer_b2 | Cityscapes | 23.1 | 22.2 | 38.5 | 53.0 | 2.42† | 27.4 |
| segformer_b5 | Cityscapes | 22.8 | 21.6 | 39.8 | 27.5 | 2.76† | 84.6 |
| smp_upernet_resnet101 | Cityscapes | 21.5 | 20.5 | 28.7 | 73.7 | 1.65† | 56.3 |
| smp_fpn_resnet50 | RailSem19 | 16.2 | 15.5 | 43.4 | 159.7 | 0.78† | 26.1 |
| smp_deeplabv3plus_resnet101 | recipe pretrained weights | 15.6 | 15.3 | 30.6 | 119.7 | 0.70† | 45.7 |
| upernet_convnext | Cityscapes | 15.0 | 14.3 | 35.2 | 42.7 | 2.66† | 80.9 |
| native_convnext_tiny_uper | recipe pretrained weights | 11.7 | 11.1 | 28.8 | 76.1 | 1.34† | 36.8 |
| hrnet_w48_ocr | Cityscapes | 8.4 | 8.1 | 35.5 | 31.7 | 1.35† | 73.2 |

† Allocator only (PyTorch peak reserved memory in the speed benchmark): excludes the CUDA context (driver overhead, a few hundred MB).

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

- Publisher code: `f35265fa8dfd`
- Campaign records last changed: 2026-10-10 05:09 PM PDT
