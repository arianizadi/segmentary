# Transfer the full nnU-Net recipe across architectures

This experiment tests whether the complete stronger training pipeline improves alternative architectures on the **same Task07 development split**. It follows the [failure investigation](../results/pancreas/task07/investigation-20260915/README.md), where verified nnU-Net snapshots reached about 55% native mass Dice while the initial DynUNet control reached 33%. Those results motivated this experiment; they do not identify which ingredient caused the difference.

The implementation supplies a planner, three architecture choices inside the pinned nnU-Net backend, and reuse of an independently verified preprocessing cache. Implementation and successful preflight are separate from actual training progress. Use the campaign's generated comparison for launch/completion status.

## What is being compared

| Arm | Architecture | Role |
| --- | --- | --- |
| `nnunet_resenc_l-seed0` | Original planned ResEnc L | Fresh matched control |
| `nnunet_planned_plainconv-seed0` | PlainConvUNet, two convolutions per encoder/decoder stage | Plain convolution alternative |
| `nnunet_planned_dynunet-seed0` | DynUNet, basic two-convolution blocks | Transfer to the original control family |

All three use the same seven-stage anisotropic grids and feature widths. Block depth, convolution bias, initialization and parameter counts retain the declared architecture differences. This is neither equal-parameter matching nor an exact recreation of each architecture's published submission. The architectures start from random weights; copying preprocessing arrays does not copy learned weights.

The common recipe is the full nnU-Net 2.8.1 pipeline: its preprocessing, augmentation, foreground sampling, SGD/Nesterov optimizer, epoch-based polynomial schedule, CE plus per-patch foreground Dice, native decoder deep supervision, checkpoint selection and native inference. This avoids calling a few similar Torch configuration values a complete pipeline reproduction.

## Fixed data, geometry and budget

- **197 training / 42 validation / 42 reserved test cases.** Keep the existing groups, split file and reference hashes. The split uses connected case/duplicate groups, with `dataset_case_unverified` patient identity status. It does not stratify histology.
- **Planning uses the 239-case training-plus-validation cohort.** This matches the existing nnU-Net experiment and is explicitly different from fitting preprocessing on training alone. Test images and labels stay excluded from planning, training and evaluation.
- **Spacing z/y/x:** 2.5 / 0.8125 / 0.8125 mm. **Patch z/y/x:** 56 × 320 × 256. No implicit change to depth 64, reduced batch or smaller patches after failure.
- **Normalization:** the frozen reference CT statistics, including clipping to −92 / 215 HU, mean 79.774 and standard deviation 71.162.
- **250,000 optimizer updates**, arranged as the standard 1,000 epochs × 250 updates. Batch 2 means 500,000 sampled patches per arm. Seed 0, no early stopping.
- **Inference:** nnU-Net native restoration, Gaussian logit blending, tile step 0.5, no mirroring, ensemble or imported model checkpoint.

250,000 is the complete upstream recipe budget, not a proven optimum for every model. Equal updates, batch and patch geometry match nominal input exposure; they do not equalize FLOPs, memory, wall time or tuning opportunity. The earlier 10k run's duration does not predict these much larger experiments. At the reference's September 15 throughput, a full ResEnc L run takes approximately 45 GPU-hours before native evaluation; measure each new architecture before estimating its duration.

The initial three-arm round is exploratory and uses one seed. A promising transfer should be repeated alongside its matched control with additional seeds. Keep the separate [Dice-reduction experiment](../results/pancreas/task07/investigation-20260915/dice-reduction-protocol.md) intact; its 10k budget and common Torch recipe answer a different question.

## Plan, verify, then train

Use a clean frozen source checkout, a fresh campaign directory, and the existing original ResEnc L workspace as the immutable preprocessing reference. The planner accepts explicit interpreter paths and preserves virtual-environment symlinks. It does not install packages or reserve GPUs.

```bash
python scripts/plan_medical_strong_recipe.py \
  --source-root /path/to/frozen-segmentary \
  --campaign-dir /path/to/task07-strong-recipe \
  --python /path/to/harness-env/bin/python \
  --nnunet-python /path/to/nnunet-env/bin/python \
  --manifest /path/to/task07-manifest.json \
  --splits /path/to/task07-splits.json \
  --reference-workspace /path/to/original-nnunet-resenc-l \
  --gpus 1 2 3
```

The planner verifies the original bound 197/42/42 cohort, planning scope, ontology, four small preprocessing metadata files, fold membership and exact audited geometry. It records their hashes in `campaign.json`. It reads no CT, mask or large preprocessing-array payloads. **Full cache verification happens in the backend import and is required before training.** The imported cache belongs to the new experiment; it must not be writable through links to the original run.

Before a full launch, verify the copied arrays and transformed plan, scratch initialization, full-batch forward/backward loss and gradients, decoder-grid alignment, inference output shape and feasible GPU memory for all three architectures. Any failed architecture remains a documented failure until its explicitly versioned fix passes; the runner does not silently resize its recipe.

The normal runner supports preprocessing without optimization:

```bash
python scripts/run_medical_campaign.py \
  --spec /path/to/task07-strong-recipe/campaign.json \
  --state-dir /path/to/task07-strong-recipe/state \
  --prepare-only
```

After the architecture GPU checks pass, run the same command without `--prepare-only`. Exactly three GPU IDs bound the campaign's concurrent allocation to three runs. The normal GPU locks, immutable state, resume checks and automatic tmux training dashboard remain active. Its dashboard cleans up only its owned panes after completion; the operator's tmux session has its own lifecycle.

Use the normal [campaign reporting and publication tools](medical-campaigns.md). Run `publish_medical_campaign.py --once` for a finite publication; this experiment does not require a recurring 30-minute monitor. Publication uses a dedicated clean checkout, separate from the frozen training source.

## Reading the results

The primary score is **equal-case mean native mass Dice across all 42 validation cases**, from each run's best checkpoint selected by the same official EMA foreground patch-Dice rule. Pancreas Dice is the union of labels 1 and 2; it is not the exclusive label-1 training class. Live patch/pseudo-Dice is a training diagnostic and is not interchangeable with native whole-volume Dice.

Keep every arm in the table, including failures. Record pancreas union Dice, zero mass-overlap cases, lesion metrics, surface Dice/HD95, evaluation coverage, training curves, source/runtime/plan identities, training time, inference time per complete CT and measured peak CUDA memory. Full case-level records remain private; publish aggregate results. Pair case-proxy differences to the fresh control and disclose the unverified independent-patient grouping.

The normal runner automatically evaluates the selected-best checkpoint. The terminal checkpoint is retained and can support a separately named native endpoint comparison; do not claim that second evaluation occurred just because training finished. Do not choose between best and terminal checkpoints by whichever native validation score is higher after inspection.

Only named latest, selected-best and terminal checkpoints are needed. Resume the same recipe from its own latest committed checkpoint with its training state; a changed recipe gets a new workspace. Do not extend a completed short polynomial schedule at zero learning rate and call it an uninterrupted 250k run.

Task07 validation contains annotated masses and cannot estimate clean-scan specificity or patient-level ROC AUC. Mass masks do not establish malignant pathology. Repeated inspection of this small validation cohort makes final independent confirmation important, but the reserved test stays untouched until the study protocol and patient/source audit are settled.
