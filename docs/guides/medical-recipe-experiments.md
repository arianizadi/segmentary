# Task07 recipe experiments: what we are testing

Read this first, then the [existing follow-up results](../results/pancreas/task07/followup-20260914/README.md) and [completed fit/inference diagnostics](../results/pancreas/task07/followup-diagnostics-20260914/README.md). Live reports for this new work belong in `docs/results/pancreas/task07/recipe-explorations-20260914/` and `cascade-20260914/` once their campaigns are materialized.

These are exploratory validation experiments, not clinical performance claims. Mass labels do not certify malignant disease. We retain the original 197 training / 42 validation / 42 reserved-test partition. Reserved test CT/label payloads and the official 139 test CTs stay out of these experiments. NIH controls and PanTS are not introduced here.

## Why these experiments

Some pancreas and mass boundaries have weak contrast against adjacent tissue. A crop can reduce distracting anatomy and make foreground more frequent, but it cannot make an invisible boundary visible. Localization itself can fail. That is why the cascade is evaluated on the **whole original CT**, including tumors outside its predicted crop.

The [PANORAMA baseline](https://github.com/DIAGNijmegen/PANORAMA_baseline) uses a low-resolution pancreas segmenter followed by an ROI-based PDAC detector. Our first cascade borrows the localization/cropping idea; it is not a reproduction of their nnU-Net trainers, data, losses or detection threshold selection. Their README's stated crop units should not be copied without checking the actual implementation.

## Matrix A: loss, intensities, geometry and shifted-window attention

Every arm starts from random weights, uses seed 0, 10,000 optimizer updates (100 × 100), batch 8, the same sampling and flips, AdamW, and its own polynomial learning-rate schedule. Native validation occurs after 100 updates and then every 1,000. No early stopping. Equal updates do not mean equal GPU-hours or voxel exposure.

| Arm | Change from fresh DynUNet control | What it tests |
|---|---|---|
| control10k | None | Reproducibility under the new frozen source |
| deep10k | Two decoder auxiliary heads at half/quarter resolution; normalized loss weights 4/7, 2/7, 1/7 | Additional training signals at intermediate scales |
| focal05 | Dice + 0.5 × focal, γ=2 | Lower weight on the focal term |
| focal10 | Dice + 1.0 × focal, γ=2 | Equal numeric coefficients on Dice and focal |
| window | HU clipping [-175,250] followed by fixed [0,1] scaling | A wider predeclared intensity window |
| minmax | Full-native-volume min/max scaling without fixed HU clipping | Adaptive image-only scaling; potentially sensitive to outliers |
| isotropic | XYZ spacing 1.5/1.5/1.5 mm; ZYX patch 160/96/96 | Isotropic resampling at matched nominal physical input extent |
| swin24 | Scratch Swin UNETR, feature size 24 | Repeat the already-screened shifted-window architecture under this source |
| swin48 | Scratch Swin UNETR, feature size 48, activation checkpointing | Larger capacity; checkpointing reduces activation memory at added compute cost |

The existing baseline already clips HU to [-100,240] and scales that fixed interval to [0,1]. It already resamples to XYZ 1.5/1.5/2.5 mm. The isotropic experiment interpolates the through-plane direction; it does **not** create newly acquired anatomical information. It preserves 144 × 144 × 240 mm nominal patch extent but changes voxel count and physical receptive field.

Focal alpha here is the coefficient multiplying the **whole focal loss**, not a class-balancing alpha. Multiclass focal is `mean((1-p_target)^gamma * -log(p_target))`, including background. Dice is unchanged: batch soft Dice averaged over classes 1 and 2, excluding background, with smoothing 1e-5. Gamma 0 and coefficient 1 recover the existing CE+Dice objective. The first matrix does not combine deep supervision and focal; combining factors comes after interpreting their separate contrasts.

Deep supervision keeps the original main-network initialization and post-construction random state matched. Auxiliary heads receive fresh random weights; they never run during inference. Categorical auxiliary targets use nearest-neighbor reduction, so small masses can disappear at coarse scales. The input audit records that loss of target coverage; the full-resolution term is always retained. This is a controlled implementation, not a claim to reproduce official nnU-Net deep supervision exactly.

[Swin UNETR paper](https://arxiv.org/abs/2201.01266) · [Focal loss paper](https://arxiv.org/abs/1708.02002)

## Matrix B: predicted bounding-box cascade

Three further fresh DynUNet runs: a full-CT control, predicted-organ ROI +20 mm, and predicted-organ ROI +40 mm. Keep stage-two spacing, loss, patch size and schedule fixed. Coarse cropping and the bounding-box proposal are tested here as one intervention, rather than duplicate experiments under different names.

1. Verify the completed original DynUNet control's checkpoint, scratch origin, source and dataset binding using the historical source.
2. Freeze it as a localization predictor. Predict exactly the 239 development CTs. Do not load ground-truth label payloads during localization.
3. Combine its predicted exclusive class 1 (parenchyma) and class 2 (mass) into a whole-organ envelope, then add the predeclared physical margin. Use all predicted components. Empty organ prediction falls back to the full CT; no patient is excluded.
4. Hash each native prediction and image, plus the stage-one checkpoint/binding and resulting ROI manifest. Crop CT and resample paired training targets onto that physical grid. The normalization bounds remain image-only.
5. Train stage two independently from random initialization. Stage-one learned weights are used only for localization; they are not imported into stage two.
6. Backproject stage-two probabilities into the full native CT; outside the crop is background. Evaluate all 42 validation cases. Record crop coverage, stage-one misses/fallbacks and total two-stage cost separately from stage-two-only inference timing.

Training localization predictions come from a stage-one model trained on those training patients: **in-sample, not out-of-fold**. Validation patients were excluded from its gradient training, but the checkpoint was selected on validation. This is an exploratory development study. A confirmatory cascade should generate out-of-fold training crops and use a separately held-out test set after the protocol is fixed. Never replace model-predicted validation crops with reference pancreas boxes; that would leak the desired location.

## What the earlier experiments mean

- The 27-model screen compared starting recipes, not each architecture's best possible training method. U-Mamba Encoder led that screen at about 35.7% mass Dice; this is not proof of architectural superiority.
- The six 10k DynUNet sampling/augmentation arms did not show a clear paired mass-Dice improvement over the roughly 33.0% control. Their intervals included zero. This does not establish that augmentation or foreground sampling cannot help under other settings or budgets.
- The small fitting diagnostic reached roughly 90% mass Dice on two training examples. That demonstrates that the pipeline can fit those examples; it does not prove annotation quality, generalization or absence of subtler bugs.
- Paired Gaussian tiling increased the original control's validation mass Dice by about 1.97 percentage points, but its 95% paired interval included zero. Pancreas improved by about 2.13 points. Keep inference changes separate from training changes.
- The 30k-duration and finer-in-plane arms are separate ongoing/completing experiments. Use their current reports for status; compare best-selected and final checkpoints, and account for the longer arm's additional selection opportunities.
- nnU-Net's live patch/pseudo-Dice is not comparable to our native whole-scan Dice. Wait for its native evaluation; do not subtract an arbitrary number of points from patch Dice.

The [nnU-Net Revisited paper](https://arxiv.org/abs/2404.09556) supports careful control of implementation and training configuration when making architecture claims. It does not establish which of these specific changes will improve our split.

## Failure analysis and architecture research

Use the [failure-analysis workflow](medical-failure-analysis.md) to review completed native predictions, audit crop exclusions and record radiologist feedback. The [architecture-study planner](medical-architecture-studies.md) declares matched controls and multiple seeds without launching or changing current experiments.

## Reporting and operational requirements

The ordinary Segmentary runner supplies live views, progress/learning curves, immutable run bindings, checkpoint selection and retention, native evaluation, and cleanup of its owned dashboard panes. Keep latest and best only. New scientific recipes require new scratch runs; resuming is only for that run's own unchanged recipe and checkpoint.

For every arm report mass Dice, exclusive pancreas Dice, whole-pancreas-union Dice, HD95/NSD where available, training/validation loss curves, update count, selected checkpoint, endpoint result, GPU-hours, memory and inference timing. Clinical reporting includes patient/tumor sensitivity according to its declared matching rule; specificity and ROC AUC remain unavailable if all reference cases are positive. Do not substitute zero for undefined metrics.

Compare candidates with the frozen control using paired patient differences and confidence intervals, then confirm promising changes across seeds. With many one-seed comparisons on the same validation set, apparent winners can reflect selection noise. Do not claim a universal Dice ceiling from a small annotation sample or unrelated inter-reader study.

## Files and commands

- `src/segmentary/medical/followup.py`: exact experiment definitions and drift rejection.
- `scripts/plan_medical_followup.py --experiment recipe-explorations`: writes Matrix A's immutable recipes; does not train.
- `scripts/predict_medical_localizer.py`: read-only historical checkpoint verification, then image-only stage-one predictions.
- `scripts/build_medical_roi_manifest.py`: binds predicted native boxes and their margins.
- `scripts/plan_medical_followup.py --experiment cascade --roi-manifests <mapping.json>`: writes Matrix B after stage-one predictions exist.
- `scripts/audit_medical_training_inputs.py`: training-only input, geometry, component and auxiliary-target audits.
- `scripts/profile_medical_pipeline.py`: full-batch feasibility and input-pipeline checks before launch.
- `scripts/run_medical_campaign.py`, `scripts/report_medical_campaign.py`, `scripts/publish_medical_campaign.py`: existing common runner/reporting workflow.

The ROI mapping is `{"20":{"path":"/absolute/roi20.json","sha256":"..."},"40":{"path":"/absolute/roi40.json","sha256":"..."}}`. Any changed manifest requires a new campaign binding. Live operator receipts distinguish planned, preflight, running, completed and failed states; this guide alone is not proof that a run launched.
