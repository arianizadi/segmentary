# Training-fit diagnostic

This checks two different questions before another broad model sweep:

1. How well does the completed control checkpoint predict a fixed subset of its own training scans, using the same native-space export and evaluator as the campaign?
2. Can a fresh model fit two training scans when augmentation is disabled?

Both answers are **in-sample diagnostics**. A high score is not independent accuracy. A low score after the bounded budget is a reason to investigate sampling, optimization, resolution, labels, and reconstruction; it does not by itself prove a pipeline bug.

## What runs

The script selects four evenly spaced ranks after sorting the audited **training partition only** by native voxel count and case ID. The first and middle selected scans form the two-case memorization subset. Selection does not inspect predictions or validation/test image or label payloads. The completed control's best checkpoint is first checked by its original frozen source and interpreter, including the bound configuration, package runtime, scratch origin, and checkpoint digest. New inference is separately attributed to the diagnostic source.

The two-case run begins independently from random weights. It retains the source control's architecture, patch size, spacing, CT window, sampler, batch size, precision, AdamW settings, gradient clipping, and native inference settings. It changes the training membership, disables augmentation, and declares a fresh 2,000-update polynomial learning-rate schedule. The production `BatchStream`, `training_loss`, native export, and evaluator are reused. The general `segmentary-overfit` command is for raster datasets, so it is not substituted for the medical volume path.

The loop records the untrained fit at update 0, then fit at 100, 500, 1,000, and 2,000. There is no accuracy threshold or early stopping. Latest and best checkpoint generations are retained; older unreferenced generations are deleted through the normal atomic checkpoint saver. Best means best **training-fit** mass Dice here, and never authorizes an independent-validation claim.

## Run on HDRFS

Run from the frozen diagnostic checkout with the original campaign Python. Choose an idle GPU other than GPU 0. A shared medical GPU lock and an idle-process check protect the assignment. The command should run inside the campaign's durable operator/tmux session.

```bash
/data/izadia1/envs/pancreas-campaign-20260913/bin/python \
  scripts/diagnose_medical_training_fit.py \
  --campaign /data/izadia1/projects/segmentary-runs/pancreas/task07-recipe-ablation-20260914 \
  --run-id dynunet-control-seed0 \
  --output /data/izadia1/projects/segmentary-runs/pancreas/training-fit-20260914 \
  --gpu 7
```

The output must be fresh. An interrupted memorization run with a committed checkpoint can continue with the same command plus `--resume`. The diagnostic plan, source, data fingerprints, configuration, scratch origin, and exact checkpoint bytes must still match. This does not extend or alter the historical control's schedule. CPU tests cover exact interrupted/resumed model weights and AdamW state; GPU bitwise resume equivalence has not been established by that CPU check.

## Server artifacts

```text
training-fit-20260914/
├── diagnostic-plan.json         # Cases, declared changes, source/data identity
├── historical-verification.json # Original-source checkpoint provenance
├── baseline-training-fit/       # Fixed training subset using control best weights
│   ├── predictions/            # Native NIfTI masks
│   ├── evaluation/             # Same Dice, surface metrics, per-case CSV and axial review
│   ├── orthogonal-review/       # Adjacent axial, coronal and sagittal panels
│   └── summary.json
├── memorization/
│   ├── scratch-origin.json      # Independent random initialization; zero external loads
│   ├── checkpoints/             # Latest and best retained generations
│   ├── metrics/                 # Loss and learning-rate history
│   ├── fit-evaluations/          # Native predictions/reviews at each declared check
│   └── training-result.json
├── cache/                       # Verified training arrays and image-only inference cache
└── summary.json                 # Written only when both diagnostics finish
```

Review images show windowed **CT without an overlay**, reference labels, and model predictions in separate columns. Five rows cover the central reference region, its adjacent axial slices, and coronal/sagittal planes. Green marks pancreas class 1; red marks mass class 2. The masks are unchanged. The existing pancreas Dice definition includes both classes 1 and 2, while mass Dice uses class 2 alone. These are annotation-review aids rather than diagnostic displays.

Images, masks, patient/case keys, and checkpoints remain in approved server storage. Only aggregate numerical results and methods should be copied into Git. Filename hashing is not a de-identification determination.
