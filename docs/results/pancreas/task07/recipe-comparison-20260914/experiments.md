# Transferable recipe experiments

These are proposed experiments, not implemented features or launched runs. Read the [verified recipe comparison](README.md) first.

## First: measure the input our models actually see

Use training cases for the data audit. Keep validation for model selection and the 42 reserved test cases untouched.

1. For every training mass, compare native versus resampled voxel count, physical volume and connected components. Identify masses that vanish or change markedly after resampling. Review overlays with the radiology collaborator before calling a lesion clinically “small.”
2. Draw a fixed diagnostic set of crops and count: tumor-containing crops, pancreas-only crops, empty crops, mass fraction, clipping and padding. Report requested center class and actual content separately. A 96³ crop can contain tumor even when its center is background.
3. Check image-only body cropping as a separate change. Training labels may guide training patch selection; inference crops must come from the CT or an independently trained pancreas predictor, with a whole-volume fallback on localization failure.
4. Retain a tiny memorization and native inference/export check for any changed loss, resampling or augmentation path. Numerically inspect labels and alignment, not just the loss curve.

## Staged comparison

Use DynUNet for the first diagnostic comparisons because its completed run is relatively cheap. Recheck actual throughput for changed patches; do not extrapolate the old runtime to higher resolution.

| Arm | Change from its declared control | Question | Applicability / readiness |
| --- | --- | --- | --- |
| A0 | Exact existing scratch recipe | Can the baseline be reproduced? | Existing recipe supported; retain existing seed-0 result as historical control |
| S1 | Make center selection explicit: uniform-volume / pancreas / tumor = 0.50 / 0.25 / 0.25 | Does the refactor preserve the existing distribution? | Needs sampler implementation and deterministic equivalence checks |
| S2 | Change only those probabilities to 0.25 / 0.25 / 0.50 | Does more tumor-centered training help? | General 2.5D and 3D applicability; track false positive burden |
| S3 | Exact class-center sampling, background/pancreas/tumor = 1:1:1 versus 1:1:5 | Does the Universal Model's stronger class weighting help? | Two-arm comparison isolates weights; background-class sampling differs from uniform-volume sampling, so S3 is not a one-variable comparison to A0 |
| A1 | Add bounded in-plane rotation to the control; transform image and label together | Does spatial variety reduce overfitting? | Needs medical augmentation support; define angle/interpolation/padding and respect anisotropy |
| A2 | Add bounded intensity perturbation alone | Does plausible contrast variation help? | Needs exact HU/normalized-space definition and recorded magnitude; no generic RGB color jitter |
| R1 | Test 1.0/1.0/2.5 mm spacing with 96/144/144 z/y/x patches on DynUNet | Does finer in-plane detail help at approximately the same 144/144/240 mm field of view? | Geometry knobs exist; memory smoke needed; 2.25× input voxels, so report extra compute |
| D1 | Add weighted auxiliary decoder losses to the same model | Does supervision at several scales improve optimization? | Appropriate for DynUNet/U-Mamba/MedNeXt after adapter work; keep a full-resolution loss because small masses may disappear at coarse scales |
| L1 | Replace no-warmup polynomial schedule with declared warmup + cosine at the same update budget | Does schedule shape help, particularly for attention models? | New medical schedule option needed; test independently of width/LR changes |
| C1 | Swin feature width 24 → 48, all else fixed | Is the smaller variant limiting our result? | Width option exists; GPU capacity test required; still random initialization |
| I1 | Uniform → Gaussian window blending using the same checkpoint | Are tile boundaries hurting predictions? | Needs Torch inference option; new inference protocol, no retraining required |
| I2 | Add mirroring at inference, with checkpoint/blending fixed | Is the accuracy gain worth added latency? | Separate TTA result, never silently mixed into baseline rankings |

Arm values are our proposals, not claims that the papers established optimal settings. In particular, 1:1:5 may increase false positives. A larger foreground fraction is not automatically better.

R1's 144-sized axes are suitable for this proposed DynUNet geometry; they are not automatically valid for Swin's hierarchy. Each architecture requires a compatible patch, and changing patch shape must be reflected in the experiment identity and physical-context comparison. At batch 8, R1 consumes 2.25× as many input voxels per update before considering additional augmentation or architecture costs. If memory forces a smaller batch, that becomes a declared additional variable; do not silently downsize.

## Budgets and checkpoints

Use 10,000 updates for the first paired ingredient screen to preserve comparability with the existing starting budget. It is a diagnostic budget, not a convergence claim. Keep validation frequency, checkpoint selection, split and loss constant unless the arm explicitly changes one of them.

For longer-training studies, declare a new total budget and schedule at initialization, then train from random weights. A 30,000-update arm would be a pragmatic 3× budget probe, not a literature reproduction. Extending a completed 10,000-step run whose polynomial LR already reached zero is a different restart/schedule experiment; do not label it an uninterrupted long scratch run.

If a run with an unchanged declared recipe is interrupted, resume its latest checkpoint with optimizer, scheduler, scaler and RNG state intact. A changed sampler, spacing, loss, architecture or schedule gets a new workspace and configuration identity. Keep latest and selected best checkpoints; periodic middle generations need not accumulate.

Once a useful recipe is selected, verify it across **DynUNet, U-Mamba Encoder and MedFormer**, with seeds 0, 1 and 2 for both control and candidate. Add Swin 24/48 and MedNeXt S under their clearly named variants as resources permit. Report paired per-case differences and uncertainty, not just the top seed.

## Borrow the idea, preserve its meaning

- **Sampling and augmentation** transfer to most model families. A 2.5D augmentation must preserve alignment across neighboring slices from the same scan.
- **Resolution and context** affect CNNs, transformers and state-space models. Report both millimeters and voxels.
- **Deep supervision** requires architecture-specific heads and weighted losses. Query-mask models already have their own auxiliary/matching objectives; do not replace them wholesale with a CNN's Dice loss.
- **Optimizer choices** can be model specific. MedNeXt's AdamW setup and U-Mamba's SGD setup motivate bounded tests, not changing all architectures to one paper's optimizer at once.
- **Partial-label learning** is useful when organ-only data or PanTS enters later. Unannotated mass voxels are unknown, not automatically negative. Dataset mixing also requires a new overlap audit and experiment identity.
- **Pretraining and ensembles** explain part of the benchmark mismatch. External pretrained encoders/text embeddings remain excluded by our scratch-only policy. Ensembles of our own scratch models could be a later explicitly labeled experiment with their combined inference cost.

## What to report for every arm

Record native mean per-case mass Dice and pancreas-union Dice, per-case changes and uncertainty, training patch exposure, optimizer updates, wall time, GPU time where actually measured, memory peaks and complete-CT inference latency. Include crop composition, mass-size strata, miss examples and false positive components per scan.

Our 42 validation scans are all mass-positive; specificity and patient-level ROC AUC remain unavailable. A clean-CT or PanTS addition is a separate study stage. A recipe improvement on this repeatedly inspected validation set needs final confirmation on the reserved test only after the protocol is fixed and patient/source grouping is audited.

This plan creates no monitoring schedule and launches no jobs.
