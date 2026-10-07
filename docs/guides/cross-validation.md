# Cross-validation: stratified group k-fold

A single validation split is noisy when the data is small and comes in groups (scenes, recordings,
patients): a random frame-level split leaks near-identical frames of one group into both train and
val, and a fixed group split rests on the handful of groups that happen to land in val.
Stratified group k-fold fixes both. Whole groups are assigned to K folds, every fold is scored
once by a model that never trained on any frame of its groups, and the folds are balanced on
the classes you care about.

The workflow is four steps: **make folds → plan one campaign → launch → read the report.**

## 1. Make folds

Input is any prepared folder dataset in the campaign layout (`images/<split>/<key>.<ext>`,
`masks/<split>/<key>.png`) whose `splits.json` has a `groups` map. Class presence is read from the
masks; class names come from `classes.json` when present. RTIS campaigns also need the
`audit/samples.json` that `scripts/prepare_rad.py` and `scripts/prepare_rtis.py` write; it is
carried into every fold view.

```bash
segmentary-make-split --scheme stratified-group-kfold --root data/my_dataset \
  --folds 5 --seed 0 --restarts 2000 \
  --anomaly-classes defect,crack --rare-threshold 50 \
  --pool train,val --holdout test \
  --require-class defect \
  --spec-out configs/datasets/my_dataset-cv-spec.json      # prints the fold table
segmentary-make-split --scheme stratified-group-kfold --root data/my_dataset \
  --spec configs/datasets/my_dataset-cv-spec.json --out-root data/my_dataset-cv
```

- **Pool and holdout.** Images of the `--pool` splits are divided into folds; the `--holdout`
  splits are copied into every fold as `test` and are never trained on or scored.
- **Stratification.** Per image: presence of each `--anomaly-classes` class and of every class
  present in fewer than `--rare-threshold` images. Groups are indivisible, so the tool runs
  `--restarts` seeded searches (iterative stratification over groups, then moves and swaps of
  whole groups) and keeps the folds that minimise the squared deviation of every label's and the
  image count's per-fold share from 1/K. The search is exact-integer and deterministic.
- **Checks.** `--require-class` fails unless the class is scored in at least two folds. Labels
  with fewer source groups than folds cannot reach every fold; they are listed as warnings.
- **`--val-min-side N`** never scores images whose shorter side is below N px. In the fold of
  their group they are left out entirely (so no frame of a scored group trains); elsewhere they
  train.
- **Output.** `cv-spec.json` (tracked: commit the `--spec-out` file) and one ordinary prepared
  dataset per fold, `fold-<k>/` (val = fold k, train = the other pool groups, test = holdout),
  whose files are hardlinks to the source dataset. `--viewpoints` (YAML `images: {sha256:
  {viewpoint: ...}}`) adds per-viewpoint counts to the fold table.

## 2. Plan one campaign

Add a `cross_validation` block to an RTIS campaign manifest. The planner expands it into one job
per model × protocol × fold × seed, named `<model>--<protocol>--fold-<k>--seed-<s>`, inside one
campaign (one `plan.json`, one `campaign.json`, one launcher, one report). Each job trains on its
fold's dataset view; the planner refuses a block that disagrees with the dataset's
`cv-spec.json`.

```yaml
cross_validation:
  scheme: stratified-group-kfold
  folds: 5
  seed: 0
  restarts: 2000
  stratify: {anomaly_classes: [defect, crack], rare_threshold: 50}
  pool: [train, val]
  holdout: [test]
  primary_checkpoint: final       # the default for cross-validation
  # run_folds: [1]                # optional subset (smoke runs)
```

**No selection on the held-out fold.** With `primary_checkpoint: final` the manifest must not set
`early_stopping_patience`: every job trains the full `target_steps` and its final checkpoint is
the result. The best-on-val checkpoint is still kept and scored, but the report shows it only as
an optimistic secondary. `model_protocols: {model: [protocol, ...]}` restricts protocols per
model (for example the best protocol of each model).

```bash
python scripts/plan_rtis_campaign.py --manifest configs/campaigns/<name>.yaml \
  --checkpoints <source-checkpoints.json> --dataset-root data/my_dataset-cv \
  --out <campaign-root> --gpus 2,3,4,5,6,7,8,9
```

## 3. Launch

Exactly as any full-statistics campaign ([guide](paul-test-rtis-full-statistics.md)): `init`
hashes every sample of every fold, a smoke campaign from the same code revision validates the
GPU path, then one launcher fills the allowed GPUs.

```bash
python scripts/run_rtis_campaign.py init --campaign <campaign-root>
python scripts/validate_rtis_launch.py --campaign <campaign-root> --smoke-campaign <smoke-root>
python scripts/launch_rtis_full_campaign.py --campaign <campaign-root> --no-dashboard
```

## 4. Read the report

```bash
python scripts/cv_report.py --campaign <campaign-root> --out <report-dir> \
  [--viewpoints <viewpoints.yaml> --subset cab-view] [--focus-class defect]
```

- **Pooled out-of-fold** (the headline): per model × protocol, the per-image confusions of all
  folds' val images are pooled, so each scored image counts once, scored by the model that never
  trained on its group.
- **Per fold:** the same metrics per fold, mean and sample standard deviation (SD) over folds.
- **Metrics** count each class only on the images that contain it (at least one ground-truth
  pixel of it, 255 ignored; `segmentary.engine.present_image`), on all images and on each
  viewpoint subset:
  - focus-class IoU (default focus: the spec's first required class) = mean over the images with
    the class of the per-image IoU TP/(TP+FP+FN). Images without the class are left out, so
    false positives on them do not count; an image with the class but nothing predicted scores 0.
  - focus-class precision and recall = TP/(TP+FP) and TP/(TP+FN), summing TP, FP and FN over
    those images only.
  - per-class IoU = the same present-image IoU for every class (empty when no image contains
    it), in the CSV as `iou_present_images:<class>` with the image count `images_present:<class>`.
  - mIoU = mean, over the classes present in at least one image, of that class's present-image
    IoU.
- The pixel-pooled metrics of the summed confusion (focus-class IoU/precision/recall, GT-class
  mIoU, campaign mIoU) stay in the CSV as `*_pixel_pooled` columns.
- **Coverage** of completed jobs per fold; a model whose folds are not all done is marked `*`.

`<report-dir>/cv-report.csv` holds every metric, subset, fold and checkpoint.

## Worked example: rad_9_24_2026

The fold assignment is tracked in `configs/datasets/rad_9_24_2026-cv-spec.json`, made from the
`fixed-grouped` arm ([RAD guide](rad-9-24-2026.md)): pool = its 254 train+val images in 18 scene
groups, holdout = its 4 test groups (60 images). Eleven images with a side below 1024 px are never
scored (smp models cannot take them on the whole-image evaluation path); `flooded-stone-bridge`
has no other image, so it trains in every fold. 243 images in 17 groups are scored once each.

| fold | groups | val images | mud images | cab-view mud images | mud px share | cab-view mud px share |
|---:|---|---:|---:|---:|---:|---:|
| 0 | evening-water-cab-view, miscellaneous-flood-stills, miscellaneous-numbered-cab-views, new-unmatched-2026, vegetation-worksite | 34 | 2 | 2 | 0.1% | 3.5% |
| 1 | flooded-road-crossing, green-roadside-cab-view, trackside-maintenance | 67 | 49 | 0 | 95.9% | 0.0% |
| 2 | flooded-station-platform, sunny-mainline-cab-view | 62 | 48 | 48 | 2.0% | 47.7% |
| 3 | green-water-cab-view, miscellaneous-mud-cab-view, overcast-mountain-stations, trackside-vegetation-closeups | 35 | 2 | 1 | 0.1% | 1.8% |
| 4 | rain-water-cab-view-with-overlay, rural-overcast-cab-view, sunny-mountain-stations | 45 | 17 | 17 | 1.9% | 47.1% |

Mud-pumping comes from six scene groups, so the folds cannot be even: fold 1 holds the
`trackside-maintenance` close-ups (95.9% of scored mud pixels, all track-level), and the cab-view
mud is split between `sunny-mainline-cab-view` (fold 2) and `rural-overcast-cab-view` (fold 4).
The headline metrics weigh every image with mud the same, so fold 1's pixel share decides only
the pixel-pooled CSV columns: by images, fold 1 holds 49 and fold 2 48 of the 118 scored images
with mud, and no fold holds over half. Fold 2's `sunny-mainline-cab-view` does hold 48 of the 68
cab-view images with mud, so pooled cab-view mud IoU mostly measures that one scene. No
stratification label misses a fold. Presence is read from the masks, which makes `tram-track`
(49 painted images) rare as well.

Cost, estimated from the GPU-hours the `paul` and `fixed-grouped` arms recorded per job, scaled
to the full 4,000 steps (no early stopping): eomt_dinov3_large 1.8, eomt_large 1.7, segformer_b5
1.8, segformer_b2 1.1, smp_deeplabv3plus_resnet101 0.8 GPU-h per job.

| variant | jobs | GPU-h | wall clock, GPUs 2-9 | wall clock, GPUs 6-9 |
|---|---:|---:|---:|---:|
| 5 models × 4 protocols × 5 folds | 100 | ~144 | ~18 h | ~36 h |
| 5 models × best protocol × 5 folds (`model_protocols`) | 25 | ~36 | ~5 h | ~9.5 h |

Plus the smoke campaign (6 jobs of 40 steps on fold 1, under an hour on one GPU). Retained
checkpoints (best + final per job) need roughly 0.5 TB for the 100-job variant.

On the GPU host, from a clean checkout of the commit to run (`$SRC`):

```bash
PY=python                       # the interpreter of the campaign environment
DATA=/data/izadia1/datasets
RUNS=/data/izadia1/projects/segmentary-runs/rad_9_24_2026
CK=/data/izadia1/projects/segmentary-runs/paul-test-rtis/diagnostics/all-source-checkpoints.json
export CUDA_VISIBLE_DEVICES= PYTHONPATH=src HF_HOME=/scr/izadia1/cache/huggingface
cd $SRC

# 1. Fold views from the tracked spec (verifies the fixed-grouped arm's hashes; hardlinks).
$PY -m segmentary.make_split --scheme stratified-group-kfold \
  --root $DATA/rad_9_24_2026-fixed-grouped \
  --spec configs/datasets/rad_9_24_2026-cv-spec.json --out-root $DATA/rad_9_24_2026-cv

# 2. Smoke campaign (fold 1, GPU 9), then the CV campaign on GPUs 2-9 (or --gpus 6,7,8,9).
$PY scripts/plan_rtis_campaign.py --manifest configs/campaigns/rad_9_24_2026-cv-smoke.yaml \
  --checkpoints $CK --dataset-root $DATA/rad_9_24_2026-cv --out $RUNS/cv-smoke-20261006 --gpus 9
$PY scripts/run_rtis_campaign.py init --campaign $RUNS/cv-smoke-20261006
$PY -u scripts/launch_rtis_full_campaign.py --hf-home $HF_HOME --no-dashboard \
  --campaign $RUNS/cv-smoke-20261006            # returns when the 6 smoke jobs are done
$PY scripts/plan_rtis_campaign.py --manifest configs/campaigns/rad_9_24_2026-cv.yaml \
  --checkpoints $CK --dataset-root $DATA/rad_9_24_2026-cv --out $RUNS/cv-seed0-20261006 \
  --gpus 2,3,4,5,6,7,8,9
$PY scripts/run_rtis_campaign.py init --campaign $RUNS/cv-seed0-20261006
$PY scripts/validate_rtis_launch.py --campaign $RUNS/cv-seed0-20261006 \
  --smoke-campaign $RUNS/cv-smoke-20261006
tmux new-session -d -s rad-cv-launcher "cd $SRC && env CUDA_VISIBLE_DEVICES= PYTHONPATH=src \
  HF_HOME=$HF_HOME $PY -u scripts/launch_rtis_full_campaign.py --hf-home $HF_HOME \
  --no-dashboard --campaign $RUNS/cv-seed0-20261006 >> $RUNS/cv-seed0-20261006/launcher.log 2>&1"

# 3. Report (CPU only, read-only on the campaign).
PYTHONPATH=.:src $PY scripts/cv_report.py --campaign $RUNS/cv-seed0-20261006 \
  --viewpoints configs/datasets/rad_9_24_2026-viewpoints.yaml --subset cab-view \
  --out $RUNS/cv-report
```

The launcher starts a worker only on an allowed GPU with no compute process, so it waits for GPUs
still used by other campaigns rather than sharing them.
