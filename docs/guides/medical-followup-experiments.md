# Controlled budget and resolution experiments

This follow-up asks whether the original DynUNet recipe needs a longer training schedule or finer CT sampling. It complements the separate fit/reconstruction check and same-checkpoint Gaussian-blending experiment. It does not open the reserved test set.

The planner writes three **fresh scratch runs** with seed 0. The original sampler, flips, model, optimizer, loss, validation scans, and checkpoint selection remain fixed. A fresh control on the current frozen source lets us compare code/runtime-matched runs with each other.

| Arm | Optimizer updates | CT spacing, x/y/z | Crop voxels, z/y/x | Nominal physical extent, x/y/z |
| --- | ---: | --- | --- | --- |
| `dynunet-control10k-seed0` | 10,000 | 1.5/1.5/2.5 mm | 96/96/96 | 144/144/240 mm |
| `dynunet-long30k-seed0` | 30,000 | 1.5/1.5/2.5 mm | 96/96/96 | 144/144/240 mm |
| `dynunet-fine10k-seed0` | 10,000 | 1.0/1.0/2.5 mm | 96/144/144 | 144/144/240 mm |

Batch size is eight for all three. The physical extent above is voxel count times spacing; the distance between the first and last voxel centers is one spacing shorter. Fine sampling processes 2.25 times more voxels per crop, so the comparison preserves nominal anatomical context and update count but not computational cost. GPU memory and throughput must pass a full-capacity preflight before launch. No silent batch-size reduction is allowed.

The longer arm starts with a 30,000-update polynomial schedule. This is a test of the longer recipe: its learning rate decays more slowly from the beginning. Resuming the finished 10,000-update checkpoint after its learning rate has reached zero would answer a different question.

## Plan and launch

Run the planner from the committed source that will perform training. The output directory must not exist. Paths below are placeholders for the concrete frozen source, reference campaign, interpreter, dataset cache, and new campaign directories.

```bash
python scripts/plan_medical_followup.py \
  --source-root /absolute/frozen-source \
  --campaign-dir /absolute/new-followup-campaign \
  --reference-campaign /absolute/completed-recipe-campaign/campaign.json \
  --reference-run-id dynunet-control-seed0 \
  --python /absolute/training-environment/bin/python \
  --cache-root /absolute/training-cache \
  --gpus 1 2 3
```

The planner verifies the reference campaign against its runner binding, the original 197/42/42 split hashes, the unmodified original control recipe, the clean source commit, and the configured Python 3.11 training runtime. It records exact recipes, source hashes, runtime package versions, reference snapshots, and planned contrasts. Planning reads manifest/split metadata, not CT, label, or checkpoint payloads; it does not allocate GPUs.

After input auditing and a real full-size GPU preflight, use the ordinary runner:

```bash
python scripts/run_medical_campaign.py \
  --spec /absolute/new-followup-campaign/campaign.json \
  --state-dir /absolute/new-followup-campaign/state
```

The existing runner owns GPU locks, the training dashboard, latest/best checkpoint retention, and resume from each run's own checkpoint. It may resume an interrupted arm with its original schedule, but it cannot import another experiment's learned weights or alter the arm's scientific recipe.

## Reading the results

Compare `long30k` against `control10k` for the longer schedule, and `fine10k` against `control10k` for finer in-plane sampling. Ordinary architecture rankings keep all three in separate comparison groups because budgets or geometry differ. The explicit follow-up analysis should report the differences, curves, per-scan failures, paired uncertainty, and GPU time.

All arms validate after the first 100 updates and then every 1,000 updates. The selected best checkpoint uses mean native-space validation mass Dice. The longer arm gets more checkpoint-selection opportunities, so also compare the fixed final checkpoint's Dice and the full curves. This single-seed round is exploratory; a promising difference still needs independent seeds and an evaluation that has not been repeatedly used to choose recipes.

Shared training caches are content-addressed by source data, spacing, HU window, preprocessing source, and dependencies. The two coarse-grid arms can reuse arrays; fine-grid arrays receive different identities in the same cache root. Validation uses image-only preprocessing and does not consult training cache labels. The 42 reserved test scans remain untouched. The all-positive validation cohort cannot estimate patient specificity or ROC AUC, and a mass label does not establish malignant disease.
