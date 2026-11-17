# RAD paper campaign

The confirmed campaign contains eight models and 24 fresh RAD adaptation runs. Every model follows the same public recipe → Cityscapes → RailSem19 → RAD chain. Archived source-training seed-0 checkpoints are reused, and the RAD stage runs seeds 0, 1 and 2. The preparation helper receives `--matrix staged24 --split-policy finalfit` explicitly.

## Models and stages

The accuracy cohort contains EoMT Large, EoMT DINOv3 Large, SegFormer B5 and ConvNeXt Tiny ChannelMapper DPT. The fast cohort contains SMP FPN ResNet50, SMP DeepLabV3+ ResNet101, SMP PAN ResNeXt50 and native MobileNetV3 Large LR-ASPP. All eight models enter the main comparison.

| Checkpoint stage | Evaluation dataset | Reported split and repetitions |
| --- | --- | --- |
| Cityscapes | Cityscapes native label space | Native validation, archived source seed 0 |
| Cityscapes → RailSem19 | RailSem19 native label space | Native validation, archived source seed 0 |
| Cityscapes → RailSem19 → RAD | RAD 21-class label space | Fixed 59-image test, RAD seeds 0, 1 and 2 |

Each stage reports metrics on its own native benchmark. The stage tables retain dataset and taxonomy identity because scores across these different label spaces measure different evaluation tasks.

Each archived source checkpoint receives a fresh deterministic native-validation evaluation under the current auto weight-bank policy, followed by a fresh BF16 deployment profile using that exact bank. Source-stage tables retain the complete original training receipts and identify the fresh evaluation receipts. A pinned surviving RailSem19 split file replaces retired configuration paths with byte-identical split content.

Queue order is seed-major. Models descend by their best final-checkpoint, class-positive-image development mIoU. PAN and LR-ASPP follow the scored models while complete current-development results are unavailable. Every planned job uses the same City→Rail source chain. Its source checkpoint manifest remains bound by SHA.

## Data and fitting

The approved corpus contains 314 native annotated images and 21 trainable classes. The inherited development split contains 187 training, 68 validation and 59 test images.

The [parent all-class split](rad-2026-11-allclasses.md) assigns whole conservative visual blocks through the reviewed class-positive-image balancing proposal. Candidate 0 requires at least five positive images of every class in each development split. Its 51-image sunny-mountain must-link block closes a documented possible recording boundary. The final-fit merge retains those block boundaries and the parent's exact test membership. All 314 images have distinct encoded files and decoded RGB content. Original recording independence remains unconfirmed.

The confirmed `finalfit` policy uses the exact 255-image union of parent training and validation, an explicit empty validation split, and the same 59 test images. `prepare_rad_finalfit.py` binds the parent split SHA, verifies image, mask and annotation bytes, retains sample and group identities, and writes parent provenance. The materialized dataset contains the original approved sample set. The legacy CVAT-origin additions stay excluded.

Each RAD adaptation receives 4,000 optimizer steps with batch size 2 and gradient accumulation 8, giving effective batch size 16. Training uses BF16 mixed precision and the final checkpoint. The auto weight-bank policy uses EMA where the model supports its running-statistics policy and raw weights for models with running-stat BatchNorm. The current recipe EMA decay is 0.9998. Checkpoint metadata records the bank actually loaded.

The effective batch of 16 is nominal. With 255 training images and `drop_last=true`, each epoch contains 127 two-image microbatches. Lightning performs 15 full eight-microbatch updates and one seven-microbatch update, whose effective batch is 14. An uninterrupted 4,000-update run therefore spans 250 epochs and 63,500 augmented image draws. Actual telemetry and interruption history accompany the final report.

The stored stage optimizer resolves backbone and head scales before training. Backbone LR is `base_backbone_lr * stage.lr_scale`. Declared-head LR is `base_backbone_lr * base_head_lr_mult * head_group_lr_scale`. The current transfer scales are 0.1 for the backbone and 1.0 for declared head groups. Layerwise decay can further scale individual backbone groups. Scheduler warmup is clipped to `min(base_warmup, floor(total_steps/10), total_steps-1)`, giving 400 warmup updates for the 4,000-update RAD fit. The saved effective optimizer accompanies the base configuration and stage scales.

The independently verified final-fit split has at least 27 positive training images and five positive test images for every class. Mud-pumping appears in 117 training images and 17 test images. The [complete class support CSV](../datasets/rad_2026_11_paper_finalfit/class-split.csv) retains exact image and pixel counts. The final split SHA-256 is `9715d453ee3161b6bf9e02c204dc4a2898f654322cd78cce7f6545e4f7149d3b` and its sample audit SHA-256 is `61fe2d3dcc7a20f61fc7a16027dd4ba85cd6dc691fcaf4965868356e57d1c962`.

Every one of the 21 classes has positive pixel support on each side of the final split. Class coverage does not imply equal prevalence. Mud-pumping occupies 10.6609 percent of valid training pixels and 0.9030 percent of valid test pixels. The report retains these counts so readers can interpret the fixed test distribution. The empty validation split follows the approved final-fitting policy after development choices were frozen.

Infrastructure recovery permits at most three attempts while retaining the same seed and configuration. A non-finite loss stops the run for investigation. Retry decisions use training and infrastructure evidence. Resume restores the global Python, NumPy, Torch CPU and CUDA random states. Worker and dataloader execution order has a broader reproducibility limit.

## Evaluation and reporting

The primary metric is pixel-pooled 21-class mIoU. Native-image confusion matrices are summed before class IoUs are calculated. The headline comparison uses the prespecified common City→Rail recipe and reports the mean over three RAD seeds.

Secondary results include class-positive-image mIoU, per-class pooled IoU, precision, recall and Dice, mud-pumping pooled and conditional scores, negative-image false alarms, and per-block class scores with support. Class-positive-image IoU averages only over images containing ground-truth pixels of that class. Negative-image false alarms therefore have a separate report. Leave-one-block-out results describe sensitivity to the inferred scene blocks.

For class `c`, pooled IoU is `sum(TP_c) / [sum(TP_c) + sum(FP_c) + sum(FN_c)]`, with sums over all test images. Primary mIoU is the arithmetic mean of the 21 class IoUs. Conditional class IoU is the arithmetic mean of individual image IoUs over the images containing ground-truth pixels of that class. Thus each conditional class score uses its own image subset. Void pixels with label 255 are excluded from every confusion matrix.

Precision is `TP / (TP + FP)`, recall is `TP / (TP + FN)`, and Dice is `2TP / (2TP + FP + FN)`. Negative-image reports retain false-positive pixels, their fraction of valid negative-image pixels, and image alarm rates at two fixed descriptive thresholds of one pixel and 0.1 percent of valid image area. The thresholds are fixed before inference. A class with no negative images has an undefined negative-image alarm rate, displayed as `N/A`.

The pooled evaluator assigns precision zero when a supported class is never predicted. An inactive native-source class has `N/A` IoU and remains visible with its actual zero ground-truth support. FPS variation across repeated profiles reflects timing variability. It has a different interpretation from the three-seed accuracy SD.

Every three-seed result includes the three values, mean, sample SD with `ddof=1`, minimum and maximum. Seed SD describes RAD adaptation variation conditional on the fixed source checkpoints. The analysis uses descriptive comparisons. Model construction and global-RNG shuffling produce architecture-dependent data orders, so matching seed labels provide no paired experimental design.

For the three observed scores `x0`, `x1` and `x2`, the mean is `(x0+x1+x2)/3` and sample SD is `sqrt([(x0-mean)^2+(x1-mean)^2+(x2-mean)^2]/2)`. The reported range is `[min(x0,x1,x2), max(x0,x1,x2)]`. These quantities describe adaptation replicates on the fixed test images. Per-block tables retain their class-specific support and macro denominator.

Qualitative examples use seed 0 and fixed image keys selected before inference. A deterministic greedy procedure uses only audited ground-truth class presence and group identity, with lexicographic ties. It covers all 21 classes, every test group and a mud-negative image. The default maximum is six images. Preparation raises an error if those requirements need a larger explicit budget.

Report model-only BF16 batch-one 1024² forward FPS separately from native-resolution sliding-window pipeline timing. Separate speed/accuracy plots retain each timing definition. Record inference allocator peak, process-total GPU memory and training peak memory with their measurement definitions. Report RAD adaptation compute, source-stage compute and available public-pretraining provenance separately.

Native timing warms each distinct stride-32 padded image shape twice before the measured pass. The benchmark retains every image key, native shape and elapsed time. The final RAD deployment pass uses one prespecified idle GPU serially. Source-stage profiles run alongside native source evaluation and retain their device identities as contextual measurements.

## Scope of interpretation

The test split has historical exposure. Scene groups are inferred and original recording independence remains unconfirmed. Public pretraining datasets and source recipes vary across architectures. The EoMT public recipe includes COCO-panoptic pretraining, while other model families have their own public initialization corpora. The shared source-chain policy therefore preserves architecture-specific public pretraining exposure. RAD adaptation uses the existing transfer recipe’s 0.1× backbone learning-rate scale. Fixed source-seed checkpoints leave source-training variance outside the three-seed estimate. Three-seed SD measures adaptation variation, while the small grouped test set also carries sampling uncertainty.

## CPU preparation commands

First materialize a new 255/0/59 dataset with its frozen parent split SHA.

```bash
python scripts/prepare_rad_finalfit.py \
  --source "$PARENT_DATASET" \
  --target "$FINALFIT_DATASET" \
  --parent-split-sha256 "$PARENT_SPLIT_SHA256"
```

Point `DATASET_ROOT` at that materialized final-fit dataset. Keep `QUALIFIED_SOURCES` bound to the reviewed archived source-checkpoint manifest.

Prepare the required source-stage request using the committed code SHA, the qualified source manifest, complete archived receipts and the pinned surviving RailSem19 split. `SOURCE_STAGE_SPEC` belongs in the input directory, while `PREPARATION` names the new preparation directory.

```bash
python scripts/prepare_rad_source_stages.py \
  --qualified-sources "$QUALIFIED_SOURCES" \
  --source-metadata tmp/rad-update-20261116/source-stage-evidence.raw.json \
  --source-provenance tmp/rad-update-20261116/source-provenance.json \
  --campaign-json "$CAMPAIGN/campaign.json" \
  --code-sha "$CODE_SHA" \
  --output-root "$CAMPAIGN/paper/source-stages" \
  --rail-split-file "$RAIL_SPLIT" \
  --rail-split-sha256 "$RAIL_SPLIT_SHA256" \
  --out "$SOURCE_STAGE_SPEC"
```

The `staged24` preparation requires `--source-stage-spec`. Its bytes are bound into the research protocol before the planner prepares training configurations.

```bash
python scripts/prepare_rad_paper_campaign.py \
  --matrix staged24 \
  --split-policy finalfit \
  --dataset-root "$DATASET_ROOT" \
  --source-checkpoints "$QUALIFIED_SOURCES" \
  --source-stage-spec "$SOURCE_STAGE_SPEC" \
  --development-scores tmp/rad-update-20261116/latest-rankings.json \
  --out "$PREPARATION"

python scripts/plan_rtis_campaign.py \
  --manifest "$PREPARATION/manifest.yaml" \
  --checkpoints "$QUALIFIED_SOURCES" \
  --dataset-root "$DATASET_ROOT" \
  --out "$CAMPAIGN" \
  --gpus 0,1,2,3,4,5,6,7,8,9

python scripts/prioritize_rad_plan.py \
  --plan "$CAMPAIGN/plan.json" \
  --priority "$PREPARATION/training-priority.json"
```

The manifest binds GPU indices 0–9 through an explicit campaign policy with idle-device checks and shared ownership locks. These commands prepare CPU artifacts. Campaign initialization, source re-hashing, smoke verification and worker launch follow the chosen protocol through the existing campaign tools.

## Source-stage request

`SOURCE_STAGE_SPEC` identifies the frozen input for [the source evaluator](../../scripts/evaluate_rad_source_stages.py). It contains the eight models and their sixteen Cityscapes/City-to-Rail source endpoints. Each endpoint binds the original configuration, checkpoint, optimizer step and complete historical training receipt by SHA-256. Public checkpoint provenance accompanies each endpoint.

Each endpoint also records `evaluation_data` with an explicit dataset root and split-file identity. Cityscapes uses its 500-image official validation split. RailSem19 uses the original 850-image validation membership from the hash-pinned source split. A surviving byte-identical split file can replace an unavailable historical path through the explicit evaluator override. The original model configuration retains its own provenance.

Fresh deterministic auto-bank evaluation and a separate nondeterministic deployment profile use the same source checkpoint and parameter bank. The immutable `source-stage-reports.json` contains both native evaluations and their artifact hashes. Historical training receipts provide the recorded training cost and recipe. The fresh evaluations provide the source-stage scores displayed in the paper.

## Execute and resume

Install the PDF dependencies into the execution environment.

```bash
python -m pip install -e '.[reports]'
python scripts/run_rtis_campaign.py init --campaign "$CAMPAIGN"
```

Run the new final-fit GPU smoke campaign on the same committed code, dataset and collection contract. Bind its completed collection evidence to the main campaign.

```bash
python scripts/validate_rtis_launch.py \
  --campaign "$CAMPAIGN" --smoke-campaign "$SMOKE_CAMPAIGN"

HF_HOME="$HF_CACHE" python scripts/evaluate_rad_source_stages.py \
  --request "$SOURCE_STAGE_SPEC"

python scripts/run_rad_paper.py \
  --campaign "$CAMPAIGN" \
  --benchmark-gpu 0 \
  --hf-home "$HF_CACHE"
```

The controller completes training, evaluates all sixteen source stages, freezes every completed RAD endpoint, evaluates the 59-image test set, profiles the RAD checkpoints serially on the selected benchmark GPU, and writes `paper/report/rad-paper.pdf`, `rad-paper.csv` and `rad-paper.json`. Its current phase appears in `paper-controller-status.json`. Re-running the command verifies existing artifacts and continues unfinished phases. Infrastructure recovery keeps the same configuration and seed, with the declared attempt limit. A stop marker ends the campaign before further scheduling.

Each model's PDF section includes source-stage class metrics, RAD class metrics under both IoU definitions, seed-level results, resource accounting and the common full-scene qualitative examples. The accompanying JSON retains confusions, per-block sensitivity, raw latency samples and complete artifact provenance. Interrupted timing records explicitly identify lower-bound compute and an unknown missing tail.

### Report-only revisions

Keep the frozen execution checkout available through the controller's completed state. A separate clean checkout of a later report revision can render the existing artifacts on CPU. Choose a separate output directory so the original controller retains its own outputs.

```bash
CUDA_VISIBLE_DEVICES= python scripts/build_rad_paper_report.py \
  --request "$CAMPAIGN/paper/test-request.json" \
  --out "$FINAL_REPORT"
```

The JSON records `report_code_sha` and `report_code_dirty` alongside the original `training_code_sha` and hashed evaluation artifacts. The report loader verifies the frozen inputs and completed results before rendering. Report-only revisions preserve the original execution evidence. Training durations identify latest-invocation observations and accumulated recorded process time separately, including lower-bound flags for interruptions. SMP public-origin evidence identifies its package-registry revision and whether the RAD process recorded the origin directly.

## Verified launch evidence

The campaign started on 17 November 2026 at 05:14 UTC using the clean execution commit `f92985e64accf952da73fd2979d4229a5092c5a8`. Its artifact directory is `rad_2026_11_paper-full-20261116-f92985e6`. Source checkpoint files and the final-fit dataset were frozen before launch.

Claude Fable, invoked with high effort, reviewed the methodology and implementation. The final read-only review found no code blocker and required the four runtime gates below. The execution checks were performed separately from that review.

| Runtime gate | Verified evidence before the main launch |
| --- | --- |
| Eight model training smokes | Eight 40-step final-fit jobs completed with the same dataset, code and collection contract. `launch-validation.json` passed. |
| Sixteen source endpoints | Fresh full native-validation evaluations and matching deployment profiles completed for all eight Cityscapes and eight City-to-Rail checkpoints. The 32 evaluation/profile artifact hashes were verified. |
| Train-only inference rehearsal | All eight smoke checkpoints completed evaluation and profiling on 13 training images covering all 21 classes and 12 native image shapes. Each evaluator's weight bank matched its training receipt. |
| Clean execution checkout | The execution checkout was clean at the frozen commit when the controller started. |

The rehearsal exercised `run_rad_test.py` and `run_rad_test_profiles.py` before main training. Its schema-1 request explicitly authorized `evaluation_split="train"`, `rehearsal=true` and `rehearsal_authorized=true`, with `test_evaluation_authorized=false`. It bound smoke state, configuration and final checkpoint hashes, a separate rehearsal `campaign.json`, and benchmark GPU 0. Its GPU policy used the schema-1 supported allowlist. `HF_HOME` was supplied explicitly to both commands. The request SHA-256 was `78ac61b0b9d949f0cbf0c8f32b08425e8bb81f2bd1c291f7c65a8de3c1693e6f`.

Training image selection used audited class-presence and dimension metadata. All three native test dimensions had a training-image representative. The rehearsal's results are diagnostic artifacts. The final report requires the separate frozen schema-2 request after all 24 full-budget RAD endpoints pass collection.

`extended-preflight.json` records these gates in the main artifact directory. `paper-input-preflight.json` records the controller's input checks. `paper-controller-status.json` identifies the active phase, and `launcher-status.json` records scheduling and GPU occupancy. Source results are reused only after their stored hashes and identities verify successfully.
