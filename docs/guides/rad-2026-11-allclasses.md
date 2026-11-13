# RAD November 2026 all-class scene split and fresh adaptation

Claude fable high approved the protocol on 2026-11-13. The dataset was
materialized and verified on HDRFS. GPU preflight, campaign launch, and new model
results are pending. Historical scores determine scheduling priority.

## Dataset and chosen split

The source is `rad_9_24_2026-fixed-grouped`: **314 unique annotated images**, with
21 trainable classes (IDs 0–20) and ignore ID 255. Original image bytes, rendered
semantic masks, and native annotation JSONs are preserved. The 15 legacy
CVAT-origin images `no_anomalies_0251.png` through `no_anomalies_0265.png`, including
their imported Supervisely copies, remain excluded. All 314 eligible annotated
images receive exactly one split assignment.

Candidate **0** in the [tracked split proposal](../../configs/datasets/rad_2026_11_allclasses.split.json)
is the authoritative assignment. Whole conservative scene blocks are allocated
using a constrained class-positive-image balancing problem. The minimum is five
images containing each class in **each** of train, validation, and test.

| Split | Images | Conservative blocks | Minimum positive-image support of any class |
| --- | ---: | ---: | ---: |
| Train | 187 | 11 | 10 |
| Validation | 68 | 5 | 7 |
| Test | 59 | 4 | 5 |
| Total | 314 | 20 | All 21 classes occur in every split |

The original groups `sunny-mountain-cab-view` (34 images),
`sunny-mountain-stations` (12), and `new-unmatched-2026` (5) form one **51-image
must-link block**, placed entirely in validation. This closes the documented
possible recording boundary around original training image `0252` and related
mountain test frames. Original keys are retained; the new metadata records both
the conservative block and the original visual group.

All miscellaneous groups, both 54-image mud-pumping groups, and every whole
original group containing an image with a side smaller than 1024 pixels are
pinned to training. Validation has at least four conservative blocks and no block
larger than 75% of its images; test follows the same limits. The chosen validation
set has five blocks, with the 51-image block accounting for exactly 75%. The test
set has four blocks; its largest contains 20 of 59 images.

| Validation block | Images | Test block | Images |
| --- | ---: | --- | ---: |
| flooded-road-crossing | 3 | green-water-cab-view | 5 |
| flooded-trackside-woodland | 4 | overcast-mountain-stations | 20 |
| sunny-mountain-recording-conservative-block | 51 | rural-overcast-cab-view | 19 |
| trackside-vegetation-closeups | 9 | winter-town-cab-view | 15 |
| vegetation-worksite | 1 | | |

### Exact class coverage

Counts are images with at least one nonignored ground-truth mask pixel of the
class. Images can contain several classes, so columns do not sum to split size.
Pixel support is also verified and recorded during preparation.

| ID | Class | Train | Validation | Test |
| ---: | --- | ---: | ---: | ---: |
| 0 | person | 10 | 20 | 5 |
| 1 | truck | 20 | 7 | 16 |
| 2 | rail-track | 145 | 63 | 56 |
| 3 | vegetation-overgrowth | 79 | 30 | 8 |
| 4 | car | 22 | 25 | 17 |
| 5 | on-rails | 16 | 16 | 14 |
| 6 | traffic-sign | 40 | 28 | 30 |
| 7 | road | 51 | 31 | 37 |
| 8 | sidewalk | 63 | 45 | 28 |
| 9 | construction | 100 | 52 | 45 |
| 10 | tram-track | 21 | 14 | 14 |
| 11 | pole | 99 | 53 | 55 |
| 12 | traffic-light | 23 | 12 | 20 |
| 13 | mud-pumping | 105 | 12 | 17 |
| 14 | fence | 60 | 32 | 35 |
| 15 | terrain | 158 | 65 | 59 |
| 16 | sky | 125 | 53 | 59 |
| 17 | rail-embedded | 22 | 13 | 15 |
| 18 | rail-raised | 187 | 65 | 59 |
| 19 | trackbed | 168 | 64 | 59 |
| 20 | standing-water | 38 | 7 | 5 |

## Preparation and integrity

[scripts/prepare_rad_allclasses.py](../../scripts/prepare_rad_allclasses.py)
requires an explicit candidate index, the hash-pinned source sample audit, and a
new destination. It verifies every source image, decoded mask, native annotation,
class-ID range, and actual class-pixel count. It checks encoded and decoded-image
uniqueness, whole-group assignment, the must-link block, train-only groups, and
reviewed support/diversity constraints. It copies into a separate staging directory,
checks copied bytes, then publishes the completed version by renaming it.

The new dataset records `audit/selected-candidate.json`, `audit/class-coverage.json`,
`audit/copied-files.json`, `audit/samples.json`, `audit/validation.json`, and the
copied proposal. The new version is at
`/data/izadia1/datasets/rad_2026_11_allclasses` on HDRFS. Preparation verified
942 copied files, all 314 distinct encoded/decoded images, and actual class
support in all three splits.

| Artifact | SHA-256 |
| --- | --- |
| Reviewed proposal | `dc5762fa2b00d0a01afb939f71f0162320fd34029ac5bcc5d3330501e773b351` |
| Materialized splits | `6913657d4f98b24c58c643c9bc9d51e8c8fffbe42154b5bcdde55125c28ce3da` |
| Materialized sample audit | `0ec86e5aa8cf1346f1d7ae4f919e3c77d02d2ad8bcf12cccd81eed434b6d478a` |
| Source checkpoint manifest | `85ed2f16e8d2c32b8435821851a768cad1025b2e5e1b395cd4c5ad382f589075` |

## Fresh training campaign

The [campaign manifest](../../configs/campaigns/rad_2026_11_allclasses.yaml) plans
**149 jobs across 41 models**, with seed 0 and a full **4,000-step** budget per
job. There is no early stopping. The final checkpoint supplies the primary
reported result; the best validation checkpoint is retained as secondary evidence.
Full quality diagnostics, checkpoint provenance, timing, speed, and memory
collection are required before a job counts as complete.

Each model starts its new RAD adaptation from its declared non-RAD initializer:

- Recipe pretrained weights.
- A Cityscapes endpoint.
- A RailSem19 endpoint.
- A Cityscapes → RailSem19 endpoint.

The 36 established models have all four paths, using the **108 existing non-RAD
source checkpoints** plus their recipe initializers. BiSeNetV1, BiSeNetV2, ESPNet,
DenseASPP-121, and DenseASPP-161 use recipe initialization only. Recipe weights
can include pretrained segmentation components. Each new RAD job receives fresh
optimizer state and the approved recipe or source-stage weights.

[scripts/verify_rad_initializers.py](../../scripts/verify_rad_initializers.py)
checks the pinned source manifest, actual source configuration spaces/stages,
approved pretrained model identifiers, and each new job’s initializer. Source
configuration hashes are frozen. The runtime separately verifies the actual
source checkpoint bytes before use. An independent CPU content audit passed for
all 108 endpoint files, totaling 82,196,185,679 bytes.

Four historical transfer references have explicit qualified City predecessors.
Three accepted configs retain dependency placeholders. Their retained City40 →
Rail20 inventory, transfer config, evaluation receipt, and City training receipt
bind the actual input and endpoint checkpoint hashes. The original transfer-run
directories are unavailable. The retained checkpoints and receipts support the
qualified lineage.

MobileNetV2’s transfer used the original raw City checkpoint. Its standalone City
baseline was later BN-recalibrated. The qualified manifest records that original
raw input separately from the baseline endpoint. All 108 endpoint selections are
reused exactly as recorded. The four qualified predecessor files and their
receipts are hash-checked before training.

The [priority file](../../configs/campaigns/rad_2026_11_allclasses.priority.json)
uses the old PDF ranking to schedule models and initialization paths in descending
historical validation mIoU order.

## Evaluation and reporting

For class `c`, score each image whose ground truth contains `c` using
`IoU = TP / (TP + FP + FN)`, then average those image IoUs. Images without `c` are
excluded from that class’s score. The **mIoU is the arithmetic mean of all 21
class scores**, because every split has positive support for every class. A missed
class on a positive image contributes zero. False predictions on entirely
class-negative images require separate false-alarm statistics. Within-image false
predictions still count.

Validation is used for development and to freeze the preferred initialization for
each model. Test evaluation occurs only after that selection rule is frozen.
Test results must not retrospectively choose initialization, checkpoint, training
length, or hyperparameters. The report is ordered by mIoU, includes per-class
support and IoU, marks best values in green, and places full-image original /
ground-truth / prediction overlays directly after each model’s results. FPS,
model size, inference memory, and their measurement conditions are included.

The approved GPU indices are **0, 1, 2, 3, 7, 8, 9**. Workers must use only idle
allowed cards, hold shared GPU locks, pin visibility to one physical GPU, and
verify the assigned UUID. GPUs 4, 5, and 6 are reserved for unrelated workloads.

## Interpretation and review status

Scene groups are inferred from appearance. Original recording identifiers remain
unconfirmed.
The conservative must-link block addresses one documented possible boundary;
other same-recording overlap remains possible. Pixel areas and independent
recording counts can differ considerably despite positive-image coverage.

The historical test set has already been evaluated and some of its scenes are
reassigned here. This is a **new benchmark version**, requiring fresh adaptation
from non-RAD initialization. The prior inspection of these scenes limits claims
of a blind holdout. Single-seed results remain exploratory.

The [final Fable review](rad-2026-11-allclasses-fable-review.md) approved the
protocol. The requested invocation used `claude -p --model fable --effort high`
and returned `claude-fable-5-2`. The review read code and manifests. The subsequent
CPU materialization independently verified the proposed counts and masks.

Launch checks must confirm identical main/smoke split and sample-audit hashes,
108 verified source endpoints, 108 transfer jobs, 41 recipe jobs, and the frozen
source-manifest hash. After the first full job finishes, check its exact
standalone/diagnostic confusion match before leaving the campaign unattended.

## Reproduce planning on HDRFS

Run from the clean reviewed checkout with the Segmentary Python environment.
`RAD_SOURCES` is the durable source-checkpoint manifest outside the checkout.
`RAD_RUN` must be a new output directory. These commands prepare and verify
provenance before the separate smoke-validated launcher starts workers.

```bash
export PYTHONPATH="$PWD/src"
RAD_PY=python
RAD_DATA=/data/izadia1/datasets/rad_2026_11_allclasses
RAD_SOURCES=/data/izadia1/projects/segmentary-runs/rad_2026_11_allclasses-inputs/source-checkpoints-qualified.json
RAD_RUN=/data/izadia1/projects/segmentary-runs/rad_2026_11_allclasses-full-20261113
"$RAD_PY" scripts/plan_rtis_campaign.py \
  --manifest configs/campaigns/rad_2026_11_allclasses.yaml \
  --checkpoints "$RAD_SOURCES" --dataset-root "$RAD_DATA" \
  --out "$RAD_RUN" --gpus 0,1,2,3,7,8,9
"$RAD_PY" scripts/prioritize_rad_plan.py --plan "$RAD_RUN/plan.json" \
  --priority configs/campaigns/rad_2026_11_allclasses.priority.json
"$RAD_PY" scripts/run_rtis_campaign.py init --campaign "$RAD_RUN"
```

Prepare the six-job smoke with the adjacent `rad_2026_11_allclasses-smoke.yaml`
manifest into a separate directory. After verified smoke completion, run
`validate_rtis_launch.py --campaign "$RAD_RUN" --smoke-campaign "$RAD_SMOKE"`,
then `launch_rtis_full_campaign.py --campaign "$RAD_RUN"`. Its default dashboard
provides campaign progress through tmux. Omit the publisher checkout argument
for this benchmark preparation.
