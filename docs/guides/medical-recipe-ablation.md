# Controlled CT recipe experiments

The [recipe planner](../../scripts/plan_medical_recipe_ablation.py) creates six fresh DynUNet experiments from a frozen Task07 reference campaign. It implements the first ingredient screen in the [research plan](../results/pancreas/task07/recipe-comparison-20260914/experiments.md). Planning creates configuration files; it does not launch training. Use the generated campaign's status for evidence of actual execution or results.

## What stays fixed

Each arm uses scratch initialization, the same DynUNet capacity and loss, batch 8, 96³ patches, 1.5/1.5/2.5 mm RAS spacing, HU clipping to −100…240, BF16, AdamW at 3e-4 with weight decay 1e-5, and the original schedule. The budget is 100 epochs × 100 updates = **10,000 optimizer updates and 80,000 sampled patches**, not 100 full passes through the dataset.

The original 197/42/42 training/validation/reserved-test split is required. Native validation runs at epoch 1 (100 updates), every 10 epochs (1,000 updates), and the final epoch. The highest mean native per-case validation mass Dice selects the best checkpoint. Inference and evaluation settings stay fixed.

| Run ID suffix | Change from the same-seed control |
| --- | --- |
| `control-seed0` | Original uniform-volume/foreground sampling and flips |
| `mass50-seed0` | Uniform-volume/pancreas/mass center probabilities: 0.25/0.25/0.50 |
| `class111-seed0` | Exact background/pancreas/mass class-center weights: 1:1:1 |
| `class115-seed0` | Exact background/pancreas/mass class-center weights: 1:1:5 |
| `rotation-seed0` | Original sampler and flips, plus 25% probability of rotation uniformly drawn from −15° to +15° |
| `intensity-seed0` | Original sampler and flips, plus 50% probability of intensity scaling uniformly drawn from 0.9 to 1.1 |

Each complete run ID starts with `dynunet-`; architecture metadata remains `model: dynunet`. These are recipe variants of one architecture. Optional `--seeds 0 1 2` creates all six arms for every listed seed, with separate controls and ranking groups. The initial screen uses only `--seeds 0`.

## Sampling and augmentation semantics

The legacy control first chooses a uniform-volume center, then replaces it with a foreground center with probability 0.5. When pancreas and mass are both present, this gives nominal branch probabilities 0.50/0.25/0.25. A uniform-volume center can fall on any class; it is not an exact background center.

`center_probabilities` selects among uniform volume, label-1 pancreas and label-2 mass. `class_center_weights` selects centers from exact label classes 0, 1 and 2. They are mutually exclusive, and either explicit mode requires `foreground_probability: null`. Missing classes lose their weight and the remaining weights are normalized. If none remain, selection falls back to a uniform-volume center. Requested center probabilities are **not** the frequency of tumor-containing patches: a crop can include a mass away from its center.

The `class111` versus `class115` pair isolates class weights. Comparing either with `control` also changes background-center semantics. These settings are hypotheses, not established optimal weights.

Rotation operates in the axial y/x plane after cropping and flips. Every z slice or 2.5D channel shares the same angle. Output shape stays fixed; images use linear interpolation, masks use nearest-neighbor interpolation, and constant padding is normalized intensity 0 for images and background 0 for masks. Rotation requires equal x/y spacing and can cut off content at crop edges.

Intensity augmentation multiplies the entire normalized sample by one factor and leaves labels unchanged. The base preprocessing maps clipped HU values to [0,1]; scaling applies in that normalized space with **no additional clipping**, so values can exceed 1. These operations are general 2D/2.5D/3D medical-harness options. Disabled options preserve the legacy sampler's output and RNG behavior; enabled options can change subsequent RNG draws.

## Plan, audit and run

Replace the absolute-path placeholders below. Use a clean, committed source checkout and its compatible medical environment. The reference campaign must retain `state/campaign-binding.json`, the referenced recipe and its manifest/splits. The planner checks their original hashes. New campaign/cache directories must be outside the source checkout, and the new campaign must be outside the historical campaign. GPU numbers are physical device IDs; verify availability before using this example allocation.

```bash
ablation_source=/absolute/path/to/clean-segmentary-checkout
ablation_python=/absolute/path/to/medical-environment/bin/python
ablation_reference=/absolute/path/to/original-campaign/campaign.json
ablation_campaign=/absolute/path/to/new-recipe-campaign
ablation_cache=/absolute/path/to/shared-medical-cache

PYTHONPATH="$ablation_source/src" "$ablation_python" \
  "$ablation_source/scripts/plan_medical_recipe_ablation.py" \
  --source-root "$ablation_source" \
  --campaign-dir "$ablation_campaign" \
  --reference-campaign "$ablation_reference" \
  --reference-run-id dynunet-seed0 \
  --python "$ablation_python" \
  --cache-root "$ablation_cache" \
  --gpus 1 2 3 4 5 6 \
  --seeds 0
```

Inspect the generated `campaign.json`, `recipes/` and exact reference-recipe snapshot. Each arm has its own workspace, recipe fingerprint, declared changes and reference provenance. The runner rejects undeclared scientific changes or changed manifest/split hashes before creating run state.

Run the [training-input audit](../../scripts/audit_medical_training_inputs.py) from the same frozen source and configured interpreter before interpreting recipe results:

```bash
PYTHONPATH="$ablation_source/src" "$ablation_python" \
  "$ablation_source/scripts/audit_medical_training_inputs.py" \
  --campaign "$ablation_campaign/campaign.json" \
  --output "$ablation_campaign/training-input-audit" \
  --samples-per-case 8 \
  --seed 20260914
```

The audit reads training CTs and labels only. It measures native versus resampled mass volume, connected components that disappear, selected crop centers, actual crop composition, padding before added rotation, and transform application. Its `report.json` and `cases/<training-ordinal>.json` use ordinals instead of scan identifiers or source paths. It builds/verifies the shared preprocessing cache without building a network or running an optimizer. Equal diagnostic coverage per training case is **not live training-sampler telemetry**; connected components are not independently annotated tumors. Audit output must be new rather than overwritten.

After input inspection and the separate model/recipe feasibility checks, start the normal runner in a durable terminal session:

```bash
PYTHONPATH="$ablation_source/src" "$ablation_python" \
  "$ablation_source/scripts/run_medical_campaign.py" \
  --spec "$ablation_campaign/campaign.json" \
  --state-dir "$ablation_campaign/state"
```

The runner schedules one experiment per listed GPU and enables the shared training dashboard by default. `--prepare-only` stops after preparation/preprocessing; it does not prove GPU training feasibility. Neither Slurm nor sudo is required.

## Resume, retention and interpretation

Restart the same runner command after interruption. It retains committed stages and resumes an interrupted run from its own latest checkpoint, preserving optimizer, scheduler, scaler and RNG state. Investigate failures first; retry recorded failures with `--retry-failed`. Do not change the recipe to make an existing run fit: a changed sampler, augmentation, resolution, schedule, loss or model requires a new campaign/workspace and scratch origin.

Checkpoint publication retains the latest and selected best generations and prunes unindexed intermediate generations. Best may be older than latest; both can therefore be necessary. Do not manually remove retained files or lineage artifacts. After successful campaign completion, dashboard cleanup closes only unchanged panes owned by that dashboard; failures, interruptions and user-added panes are preserved.

Reports retain every run ID, its actual architecture and full ingredient settings. Mass and pancreas Dice remain separate, and final rankings require complete native coverage, the declared budget, scratch evidence and matching source, runtime, split and evaluation protocol within each seed. Equal updates are not equal compute, and one seed does not establish a reliable improvement. The fresh control uses the new frozen source; historical results are context rather than a same-source replicate.

The reserved test is untouched by this workflow. The 42 validation examinations are mass-positive, so specificity and patient-level ROC AUC cannot be estimated from this cohort. Confirm promising ingredients with new seeds and other architectures before fixing the final evaluation protocol. Resolution, deep supervision, schedule/capacity changes and inference changes remain separate proposals in the [experiment plan](../results/pancreas/task07/recipe-comparison-20260914/experiments.md).
