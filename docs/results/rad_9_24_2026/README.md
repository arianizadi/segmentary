# RAD 9/24 study: label fix, split policy and Paul Stanik's paper recipes

The `rad_9_24_2026` delivery (314 rail images with polygon labels) trained three ways with the same 10-model x 4-initialization-path catalog (40 jobs per arm, seed 0, checkpoint selection and early stopping on validation mud-pumping IoU), plus Paul Stanik's two paper recipes, retrained by us with his fork code. Two questions: does fixing the label render change the results (`paul` vs `fixed-stratified`), and how much does the random stratified split flatter them (`fixed-stratified` vs `fixed-grouped`)? Validation only; the test split is held out and never read.

[Dataset preparation and split decisions](../../guides/rad-9-24-2026.md) · [Comparison CSV](rad-comparison.csv)

## Arms and progress

| arm | labels | split; train/val/test | completed | other jobs | code |
| --- | --- | --- | --- | --- | --- |
| [`paul`](paul/README.md) | Paul's delivered `masks_machine` copies | stratified random (seed 0); 227/37/50 | 40/40 | — | `d864b72bd907` |
| [`fixed-stratified`](fixed-stratified/README.md) | re-rendered from the polygon JSONs | the same stratified split; 227/37/50 | 4/40 | queued 32, training 4 | `d864b72bd907` |
| [`fixed-grouped`](fixed-grouped/README.md) | re-rendered from the polygon JSONs | scene-grouped (from v1/v2); 217/37/60 | 0/40 | queued 40 | `d864b72bd907` |

Each arm page has the per-model reports, `results.csv`, `status.json` and the downloadable evidence exactly as for [RTIS v2](../paul-test-rtis/v2/README.md). Fork progress is in the [paper-recipe section](#paper-recipe-fork-runs).

## Caveats

- **Single seed.** Every result is one training run (seed 0); there are no repeats or confidence intervals, so differences of a few IoU points are not established.
- **Optimistic validation numbers.** Checkpoints are selected (and training early stopped) on the same val split that is reported; fork runs pick their epoch on it too.
- **Small cab-view subsets.** Val images with mud ground truth behind the deployment-relevant cab-view mud IoU: `paul` n=7, `fixed-stratified` n=7, `fixed-grouped` n=17.
- **The stratified split shares scenes.** Frames of one recording can sit in train and val; scene groups of the val split that also have train images: `paul` 17 of 17, `fixed-stratified` 17 of 17. Stratified-arm numbers measure same-recording generalisation; only `fixed-grouped` keeps scene groups apart (groups are visually assigned).

## Label defects in the delivered masks

The annotator's `masks_machine` PNGs start from a black canvas and draw exterior polygon rings only, so pixels covered by no polygon become class 0 (person) and polygon holes are filled. The `paul` arm trains on those masks; the two `fixed` arms train on the repository render of the same polygon JSONs (holes cut out, uncovered pixels ignored). Counts over all 314 images, from each prepared dataset's `audit/label-audit.json` (masks_machine versus the repository render):

| Quantity | `paul`, `fixed-stratified`, `fixed-grouped` |
| --- | --- |
| Images with any disagreement | 314 |
| Images with pixels covered by no polygon | 63 |
| Pixels covered by no polygon / of those labelled person in masks_machine | 210,762 / 210,762 |
| Pixels changed by ignoring polygon holes | 299,121 |
| Total disagreement pixels | 1,478,606 (0.20%) |
| Person pixels, repository render / masks_machine | 907,504 / 1,125,758 |
| Mud-pumping pixels differing, masks_machine / render (of all mud pixels) | 14,250 / 37,144 of 65,175,587 |

Trained labels (`label_source`): `paul` paul, `fixed-stratified` rendered, `fixed-grouped` rendered. The two renders compared are the same for every arm. Classes with the most differing pixels (larger of the two directions): terrain 284,329, person 221,586, sky 215,126, pole 212,261, rail-raised 187,904.

## Cab-view comparison (validation split)

### How to read this

All numbers are on the validation split (paul 37, fixed-stratified 37, fixed-grouped 37 images); the test split is never read. Mud IoU is pixel-aggregated: confusions are summed over the subset's images first, so a few images with large mud areas decide it. The image-mean mud IoU averages per-image IoU over the images that have mud ground truth (false-positive mud on images without mud GT only lowers the pixel-aggregated IoU). GT-class mIoU is the campaign's `fixed_miou` rule (mean over classes with ground truth in the subset). `n=` in a column header is the number of val images with mud GT behind that arm's mud IoU.

**Arms.** All campaign models are trained by us. `paul` = Paul's delivered masks (the `masks_machine` copies) with the stratified split; `fixed-stratified` = our re-rendered masks with the same stratified split; `fixed-grouped` = our re-rendered masks with the scene-grouped split. P / FS / FG below name these label/split arms, not who trained the model.

**Caveats.**

- **These val numbers are optimistic.** The reported checkpoint is the one selected on this same val split (campaign selection and early stopping on `val_iou/mud-pumping`); fork runs report their `best_mud_epoch` checkpoint, also chosen on this val split. They are not held-out estimates, mud IoU least of all.
- **Single seed, no uncertainty.** Every campaign result is seed 0; there are no repeats or confidence intervals, and the subsets are small (see `n=`), so differences of a few IoU points between models or arms are not established.
- **The stratified split's pixel-aggregated mud IoU is dominated by 5 track-level close-ups from the `trackside-maintenance` scene group.** On the stratified val split (same images for `paul` and `fixed-stratified`) 6 track-level images with mud GT hold 95.1% of all mud GT pixels and 7 cab-view images 4.9%; the `trackside-maintenance` scene group alone holds 94.9%, and the five largest images (`trackside-maintenance/0071`, `trackside-maintenance/0076`, `trackside-maintenance/0081`, `trackside-maintenance/0089`, `trackside-maintenance/0091`) 94.9%. Scene groups are directory layout names assigned from visual evidence, not confirmed recording provenance.
- On the grouped val split 17 cab-view images with mud GT hold 98.9% of the mud GT pixels, so its `all` and `cab-view` mud IoU nearly coincide. All 17 come from the `rural-overcast-cab-view` scene group; judged visually, a forward view centred on the track from a moving vehicle, but from a camera visibly lower than a locomotive cab (the ballast fills the lower frame; more like a front-bumper or draisine mount). The grouped arm's cab-view mud numbers therefore mostly measure that one camera setup.
- **`cab-view` is the deployment-relevant subset** (a camera on a moving train). Compare arms and models on mud IoU (cab-view) and image-mean mud IoU (cab-view); read `all` with the composition above in mind.
- Viewpoints come from `configs/datasets/rad_9_24_2026-viewpoints.yaml`, joined by image SHA-256: visual judgement only, from two labelling passes by AI model subagents with adjudication of disagreements. Both passes are the same model, so their agreement is not evidence from independent annotators.
- `paul` vs `fixed-stratified` is the label fix: same val images (keys and image SHA-256 checked), each arm scored against its own ground truth.
- `fixed-stratified` vs `fixed-grouped` is the split policy: the val sets are different images and the train sets differ too (227 vs 217 train images, 158 in common), so the difference mixes the training data, model generalisation and val composition. On the stratified split 17 of its 17 val scene groups also have train images; on the grouped split 0 of 3 do (scene groups are visually assigned, not confirmed recordings).
- Fork labels: in `paper-hrnet__rs19-paul__arm-paul`, `rs19-paul` means the RS19 stage uses Paul's checkpoint and `arm-paul` means the RAD stage trains on the `paul` arm (Paul's masks); the checkpoint owners column spells out who trained each stage.

### Headline: Segmentary campaign models

Percent; columns per arm: P = `paul`, FS = `fixed-stratified`, FG = `fixed-grouped`. Selected checkpoint `best-auto-val`. Empty = job not completed.

| model | protocol | GT-class mIoU P | GT-class mIoU FS | GT-class mIoU FG | mud IoU P (n=13) | mud IoU FS (n=13) | mud IoU FG (n=18) | mud IoU cab P (n=7) | mud IoU cab FS (n=7) | mud IoU cab FG (n=17) | img-mean mud IoU cab P (n=7) | img-mean mud IoU cab FS (n=7) | img-mean mud IoU cab FG (n=17) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | 70.2 |  |  | 89.1 |  |  | 38.9 |  |  | 48.0 |  |  |
| eomt_dinov3_large | cityscapes_to_rtis | 65.9 |  |  | 85.8 |  |  | 26.4 |  |  | 37.2 |  |  |
| eomt_dinov3_large | railsem19_to_rtis | 70.6 |  |  | 89.9 |  |  | 39.7 |  |  | 53.3 |  |  |
| eomt_dinov3_large | rtis_only | 68.3 |  |  | 90.8 |  |  | 41.9 |  |  | 49.2 |  |  |
| eomt_large | cityscapes_to_railsem19_to_rtis | 72.2 | 72.2 |  | 93.5 | 93.6 |  | 46.0 | 47.9 |  | 51.9 | 51.8 |  |
| eomt_large | cityscapes_to_rtis | 71.0 | 70.5 |  | 92.7 | 91.6 |  | 40.3 | 41.4 |  | 50.5 | 48.6 |  |
| eomt_large | railsem19_to_rtis | 72.8 | 73.1 |  | 95.0 | 94.8 |  | 50.7 | 50.2 |  | 49.3 | 50.4 |  |
| eomt_large | rtis_only | 70.3 | 71.5 |  | 92.5 | 92.7 |  | 42.6 | 47.3 |  | 51.3 | 56.2 |  |
| hrnet_w48_ocr | cityscapes_to_railsem19_to_rtis | 55.4 |  |  | 75.5 |  |  | 34.1 |  |  | 45.5 |  |  |
| hrnet_w48_ocr | cityscapes_to_rtis | 56.9 |  |  | 85.8 |  |  | 33.9 |  |  | 39.9 |  |  |
| hrnet_w48_ocr | railsem19_to_rtis | 61.1 |  |  | 76.7 |  |  | 46.3 |  |  | 42.4 |  |  |
| hrnet_w48_ocr | rtis_only | 59.8 |  |  | 90.8 |  |  | 49.3 |  |  | 45.7 |  |  |
| native_convnext_tiny_uper | cityscapes_to_railsem19_to_rtis | 64.2 |  |  | 90.5 |  |  | 45.0 |  |  | 43.2 |  |  |
| native_convnext_tiny_uper | cityscapes_to_rtis | 60.5 |  |  | 89.4 |  |  | 45.2 |  |  | 43.6 |  |  |
| native_convnext_tiny_uper | railsem19_to_rtis | 64.1 |  |  | 88.4 |  |  | 48.5 |  |  | 43.7 |  |  |
| native_convnext_tiny_uper | rtis_only | 60.5 |  |  | 88.8 |  |  | 47.5 |  |  | 53.3 |  |  |
| segformer_b2 | cityscapes_to_railsem19_to_rtis | 64.4 |  |  | 89.2 |  |  | 42.7 |  |  | 49.9 |  |  |
| segformer_b2 | cityscapes_to_rtis | 54.2 |  |  | 87.3 |  |  | 29.7 |  |  | 30.2 |  |  |
| segformer_b2 | railsem19_to_rtis | 66.4 |  |  | 93.2 |  |  | 57.0 |  |  | 51.6 |  |  |
| segformer_b2 | rtis_only | 58.2 |  |  | 93.1 |  |  | 58.7 |  |  | 59.2 |  |  |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | 65.1 |  |  | 91.2 |  |  | 61.9 |  |  | 60.0 |  |  |
| segformer_b5 | cityscapes_to_rtis | 59.1 |  |  | 91.3 |  |  | 46.8 |  |  | 51.9 |  |  |
| segformer_b5 | railsem19_to_rtis | 69.5 |  |  | 90.4 |  |  | 55.2 |  |  | 50.6 |  |  |
| segformer_b5 | rtis_only | 59.1 |  |  | 93.1 |  |  | 53.4 |  |  | 60.0 |  |  |
| smp_deeplabv3plus_resnet101 | cityscapes_to_railsem19_to_rtis | 56.9 |  |  | 85.4 |  |  | 39.9 |  |  | 47.2 |  |  |
| smp_deeplabv3plus_resnet101 | cityscapes_to_rtis | 55.7 |  |  | 89.6 |  |  | 45.6 |  |  | 38.2 |  |  |
| smp_deeplabv3plus_resnet101 | railsem19_to_rtis | 62.4 |  |  | 87.7 |  |  | 47.2 |  |  | 36.3 |  |  |
| smp_deeplabv3plus_resnet101 | rtis_only | 41.3 |  |  | 85.9 |  |  | 12.1 |  |  | 16.6 |  |  |
| smp_fpn_resnet50 | cityscapes_to_railsem19_to_rtis | 57.0 |  |  | 74.0 |  |  | 38.7 |  |  | 34.3 |  |  |
| smp_fpn_resnet50 | cityscapes_to_rtis | 55.5 |  |  | 85.3 |  |  | 18.4 |  |  | 14.0 |  |  |
| smp_fpn_resnet50 | railsem19_to_rtis | 60.3 |  |  | 89.9 |  |  | 47.4 |  |  | 43.3 |  |  |
| smp_fpn_resnet50 | rtis_only | 52.5 |  |  | 89.2 |  |  | 38.1 |  |  | 31.3 |  |  |
| smp_upernet_resnet101 | cityscapes_to_railsem19_to_rtis | 55.5 |  |  | 87.6 |  |  | 28.1 |  |  | 33.0 |  |  |
| smp_upernet_resnet101 | cityscapes_to_rtis | 49.4 |  |  | 85.2 |  |  | 24.9 |  |  | 25.0 |  |  |
| smp_upernet_resnet101 | railsem19_to_rtis | 57.4 |  |  | 86.0 |  |  | 42.7 |  |  | 38.4 |  |  |
| smp_upernet_resnet101 | rtis_only | 54.8 |  |  | 87.5 |  |  | 37.5 |  |  | 51.0 |  |  |
| upernet_convnext | cityscapes_to_railsem19_to_rtis | 67.2 |  |  | 92.6 |  |  | 42.3 |  |  | 38.4 |  |  |
| upernet_convnext | cityscapes_to_rtis | 62.6 |  |  | 89.2 |  |  | 38.3 |  |  | 42.2 |  |  |
| upernet_convnext | railsem19_to_rtis | 66.1 |  |  | 88.3 |  |  | 40.1 |  |  | 36.2 |  |  |
| upernet_convnext | rtis_only | 61.5 |  |  | 91.7 |  |  | 50.6 |  |  | 50.9 |  |  |

### Arm effects

Differences in IoU points for model x protocol pairs completed in both arms, single seed, no uncertainty. Label fix = FS - P (same val images). Split = FG - FS (different val and train images).

| model | protocol | effect | GT-class mIoU | mud IoU | mud IoU cab | img-mean mud IoU cab |
|---|---|---:|---:|---:|---:|---:|
| eomt_large | cityscapes_to_railsem19_to_rtis | label fix | +0.0 | +0.1 | +1.9 | -0.1 |
| eomt_large | cityscapes_to_rtis | label fix | -0.5 | -1.1 | +1.1 | -1.8 |
| eomt_large | railsem19_to_rtis | label fix | +0.3 | -0.2 | -0.5 | +1.0 |
| eomt_large | rtis_only | label fix | +1.1 | +0.2 | +4.7 | +4.9 |

### Validation composition (labels only)

Images / images with mud GT / share of the split's mud GT pixels, by viewpoint.

| arm | images | cab-view | track-level | other | mud GT px | trackside-maintenance mud share % |
|---|---|---:|---:|---:|---:|---:|
| paul | 37 | 28 / 7 / 4.9% | 8 / 6 / 95.1% | 1 / 0 / 0.0% | 7,435,760 | 94.9 |
| fixed-stratified | 37 | 28 / 7 / 4.9% | 8 / 6 / 95.1% | 1 / 0 / 0.0% | 7,436,590 | 94.9 |
| fixed-grouped | 37 | 27 / 17 / 98.9% | 9 / 1 / 1.1% | 1 / 0 / 0.0% | 1,226,250 | 0.0 |

### Inputs

- viewpoints: `rad_9_24_2026-viewpoints.yaml (sha256 7dfc4f730cbe)`
- campaign fixed-grouped: [published arm](fixed-grouped/README.md); source `/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fixed-grouped-seed0-20261005-r2`
- campaign fixed-stratified: [published arm](fixed-stratified/README.md); source `/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fixed-stratified-seed0-20261005-r2`
- campaign paul: [published arm](paul/README.md); source `/data/izadia1/projects/segmentary-runs/rad_9_24_2026/paul-seed0-20261005-r2`
- fork runs: `/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24/runs`
- samples paul: `sha256 2338c1e5cd84`
- samples fixed-stratified: `sha256 048ba308159f`
- samples fixed-grouped: `sha256 46e5b404cb1e`

Every subset metric of every completed job is in `rad-comparison.csv` (subsets `all`, `cab-view`, `not-cab-view`, `excl-trackside-maintenance`).

## Paper-recipe fork runs

Paul Stanik's two paper recipes (HRNet-OCR-Mscale `pauls3/semantic-segmentation@5e619e6`, SFNet-R18 `pauls3/SFSegNets-2@0bb9e59`), retrained by us with his fork code on the same three arms: every RAD stage (`rad:ours`) is trained by us, and earlier stages may start from Paul's or public checkpoints. The run label states the init chain; checkpoint owners name who trained each stage (`paul` = Paul's checkpoint, `ours` = trained by us, `nvidia` / `public-sfnet-authors` = public). The `arm-<arm>` part of a label is the RAD dataset arm, not an owner.

**Scored** runs use Segmentary's metric code on our val split (`score_predictions.py`, whole-image single-scale) and are comparable with the campaign tables above. **In-training** numbers are the fork's own validation printout (multi-scale fork evaluator, its own class handling, epoch picked on the same val split): progress only, **not comparable** with any scored number. Epoch numbers are the fork's own 0-based indices. RS19-stage runs (pretraining on RailSem19) show their status only: their printouts are not RAD validation numbers.

| label | arm | checkpoint owners | status | scored: GT-class mIoU / mud IoU / mud IoU cab / img-mean mud IoU cab | fork's own in-training best (not comparable) |
| --- | --- | --- | --- | --- | --- |
| `paper-hrnet__rs19-paul__arm-paul` | paul | map_city:nvidia -> rs19:paul -> rad:ours | training, epoch 640 (0-based, of 1000) | — | mud IoU 93.8 @ epoch 460; mIoU 70.3 @ epoch 607 |
| `hrnet-rs19-ours` | — (RS19 stage) | — | queue: pending | — | — |
| `paper-hrnet__mapcity-direct__arm-fixed-grouped` | fixed-grouped | — | queue: pending | — | — |
| `paper-hrnet__mapcity-direct__arm-fixed-stratified` | fixed-stratified | — | queue: pending | — | — |
| `paper-hrnet__mapcity-direct__arm-paul` | paul | — | queue: pending | — | — |
| `paper-hrnet__rs19-ours__arm-fixed-grouped` | fixed-grouped | — | queue: pending | — | — |
| `paper-hrnet__rs19-ours__arm-fixed-stratified` | fixed-stratified | — | queue: pending | — | — |
| `paper-hrnet__rs19-ours__arm-paul` | paul | — | queue: pending | — | — |
| `paper-hrnet__rs19-paul__arm-fixed-grouped__recipe-train_2` | fixed-grouped | — | queue: pending | — | — |
| `paper-hrnet__rs19-paul__arm-fixed-stratified__recipe-train_2` | fixed-stratified | — | queue: pending | — | — |
| `paper-hrnet__rs19-paul__arm-paul` (run `probe2-paper-hrnet__rs19-paul__arm-paul`) | paul | map_city:nvidia -> rs19:paul -> rad:ours | excluded (probe_epochs) | — | — |
| `paper-hrnet__rs19-paul__arm-paul__recipe-train_2` | paul | — | queue: pending | — | — |
| `paper-sfnet__mapcity-direct__arm-fixed-grouped` | fixed-grouped | — | queue: pending | — | — |
| `paper-sfnet__mapcity-direct__arm-fixed-stratified` | fixed-stratified | — | queue: pending | — | — |
| `paper-sfnet__mapcity-direct__arm-paul` | paul | — | queue: pending | — | — |
| `paper-sfnet__rs19-ours__arm-fixed-grouped` | fixed-grouped | — | queue: pending | — | — |
| `paper-sfnet__rs19-ours__arm-fixed-stratified` | fixed-stratified | — | queue: pending | — | — |
| `paper-sfnet__rs19-ours__arm-paul` | paul | — | queue: pending | — | — |
| `sfnet-rs19-ours` | — (RS19 stage) | — | queue: pending | — | — |

`paul-reference__rr22-0.8964` (Paul's finished RAD model) may have trained on our val/test images and is never scored on our splits. Deviations from Paul's protocol are recorded in each run's `provenance.json` on HDRFS.

## About this page

Generated by `scripts/publish_rad_results.py` from the HDRFS campaign records, the prepared datasets and the fork run directories, which it only reads. Absolute paths are provenance on HDRFS, not links. Prediction masks are not published.

- Publisher code: `89fdb48be1a4`
- Campaign records last changed: 2026-10-05 16:38 UTC
