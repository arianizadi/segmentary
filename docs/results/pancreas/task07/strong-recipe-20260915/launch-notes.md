# Full nnU-Net recipe transfer: preparation and launch notes

**All three full training runs launched on September 15, 2026, at 10:50 Pacific.** At 10:57 Pacific, ResEnc L had completed 500 updates, and PlainConvUNet and DynUNet had each completed 750 updates with finite losses. Their scratch-origin records and actual selected checkpoints were verified; image-only native-prediction dry runs passed for all 42 validation cases. This verifies readiness, not final accuracy. [Launch evidence](launch.json).

The training source remains frozen at `63a108f8b7a65a98b11ccae0e8883c54955b2099`. [GitHub Actions passed](https://github.com/arianizadi/segmentary/actions/runs/35002397500) on `segmentary-linux`: 2,691 tests passed, 14 skipped, and 41 deselected; lint, formatting, types and dependency checks passed. The earlier prepared-state audit and synthetic checks are preserved in the preflight record.

[Exact aggregate evidence](preflight.json) · [Full protocol and operating guide](../../../../guides/medical-strong-recipe.md) · [Investigation that motivated the experiment](../investigation-20260915/README.md)

## Why these first three architectures

This round tests whether a complete stronger training pipeline can be transferred reliably to alternative convolutional architectures. The earlier sweep applied a small common starting recipe to many models. Here, all three architectures run inside the same pinned nnU-Net pipeline, including its preprocessing, augmentation, sampling, optimizer, losses, supervision and native inference.

| Model | Role | Planned architecture differences |
| --- | --- | --- |
| nnU-Net ResEnc L | Fresh matched control | Original residual encoder block counts and decoder |
| Planned PlainConvUNet | Plain convolution alternative | Two convolutions per encoder and decoder stage |
| Planned DynUNet | Transfer to the original control family | MONAI basic two-convolution blocks, convolution bias disabled |

All share the original seven-stage anisotropic grids and feature widths. They retain different block depths, parameter counts and architecture-default initialization. The two planned alternatives are larger and geometrically different from the compact DynUNet used in the earlier sweep; this experiment is not an isolated estimate of one training ingredient.

This deliberately limited first group checks the transfer mechanism with compatible architectures. It does not establish that convolutional models are better than transformers or state-space models. MedNeXt, U-Mamba and shifted-window transformers need their own verified adaptations for this geometry and deep-supervision contract before they can join a comparable experiment.

## What is fixed

- **Data:** the existing 197 training, 42 validation and 42 reserved test cases, with unchanged grouping and hashes. No test payloads enter this campaign.
- **Planning:** the same frozen 239-case training-plus-validation plan. This follows the existing nnU-Net comparator and is explicitly not training-only preprocessing fitting.
- **Input:** batch 2, patch 56 × 320 × 256 in z/y/x, spacing 2.5 / 0.8125 / 0.8125 mm. CT normalization, resampling, physical coverage and inference restoration retain the reference settings.
- **Training:** scratch initialization, seed 0, 1,000 epochs × 250 updates = **250,000 optimizer updates per model**, with no early stopping. The official foreground sampler, full augmentation, SGD/Nesterov polynomial schedule and multiscale CE plus per-patch Dice are shared.
- **Primary selection and evaluation:** the same official EMA foreground patch-Dice selector; final native validation uses the selected-best checkpoint. Report mass Dice and pancreas union Dice over all 42 validation cases. The terminal checkpoint is retained, but a separate native terminal evaluation must be explicitly run and labeled.
- **Inference:** Gaussian logit blending, tile step 0.5, no mirroring, ensemble or pretrained checkpoint.

Equal updates, patches and input geometry do not imply equal compute or parameter count. This one-seed comparison is exploratory. Dataset-case grouping remains `dataset_case_unverified`; the split does not guarantee histology balance, and mass labels are not confirmed malignancy diagnoses.

## GPU preflight results

Every architecture passed synthetic full-patch execution on an NVIDIA L40S at the **actual batch and patch size**, using unmodified nnU-Net trainer methods.

| Model | Parameters | Training peak allocated | Training peak reserved | Median synthetic update |
| --- | ---: | ---: | ---: | ---: |
| ResEnc L | 140,989,042 | 24.30 GiB | 27.86 GiB | 0.590 s |
| Planned PlainConvUNet | 44,943,026 | 19.62 GiB | 22.19 GiB | 0.394 s |
| Planned DynUNet | 44,992,082 | 19.62 GiB | 22.67 GiB | 0.393 s |

Each check performed five optimizer steps with finite losses and gradients, excluding the first warmup step from the four-sample timing summary. It also exercised official validation, deep-supervision switching, strict checkpoint reload into the inference constructor, exact AMP inference-logit equality after reloading, optimizer/scaler restoration and a finite resumed update. The temporary synthetic checkpoints were removed. Synthetic initialization used a diagnostic seed separate from the campaign's seed 0.

These are short synchronized measurements. Real CT loading, augmentation, full training and validation add work; they are neither clinical accuracy results nor end-to-end throughput. A full reference run was taking approximately 45 GPU-hours before native evaluation. Duration estimates for the new runs should use their observed full epochs after launch.

## Prepared-cache and source verification

The independent preparation audit checked all three generated plans against the original: **every nonarchitecture plan field matches**. Each prepared architecture also exactly matches the architecture described by its synthetic preflight receipt.

Each workspace independently imported 960 indexed files, covering the same 239 development cases and excluding 42 reserved test cases. The backend verified source and copied payload hashes during import. The subsequent audit compared the frozen indexes and checked that the original and all three destinations have distinct file inodes for every indexed file. The new workspaces cannot overwrite the reference through shared mutable file links. No CT or mask payload was reopened by this metadata audit.

All three prepared code bindings match the clean frozen source and share the same currently verified runtime. The dedicated runtime preserves the historical package versions and adds MONAI 1.6.0 for DynUNet. The reference binding digest is pinned into each recipe, preventing a later replacement of the source cache or plan from silently changing the experiment.

The live GPU assignments are **ResEnc L: 1; PlainConvUNet: 2; DynUNet: 3**. Their existing run configurations and copied plans remain frozen. The normal runner supplies GPU locks, checkpoint recovery, durable metrics, and the automatic tmux dashboard with cleanup of its owned panes. Completion evidence includes hashes of scratch origin, training result and checkpoint index. Reporting publishes aggregate model/metric data; detailed case records remain private.

## Detection diagnostics after completion

The finite completion wrapper is configured to wait for the campaign runner to finish, run the existing detection evaluator for each successfully completed primary evaluation, then publish once and exit. It adds **patient-wise sensitivity (P-Sen)** and **tumor-wise sensitivity (T-Sen)** using the fixed exploratory default protocol: 26-connected components, a minimum predicted-component volume of 10 mm³, and one-to-one lesion matching at IoU ≥ 0.1. These diagnostics have not run for this new campaign yet.

P-Sen counts any retained predicted mass in a reference-positive case group, even at the wrong location. T-Sen requires spatial matching to a reference component; connected components are only proxies for separately annotated lesions. **Specificity and ROC AUC remain unavailable because all 42 validation cases are mass-positive.** These are annotated-mass diagnostics, not validated cancer screening performance or a direct PanTS leaderboard comparison. No recurring 30-minute monitor is created.

## Viewing progress and initial duration estimate

On HDRFS, attach to the automatically created view:

```bash
tmux attach -t state-controller-768704e68f
```

Detach with Ctrl+b, then d. The finite training wrapper and owned dashboard panes clean up when their work finishes. Existing unrelated tmux sessions remain available.

The first warmed epochs were approximately **157 seconds for ResEnc L** and **105 seconds for each planned alternative**. If sustained, that is roughly **44 hours** and **29–30 hours** of training, respectively, plus final native prediction/evaluation. These estimates are based on only the first few epochs and will change with observed throughput. Training patch pseudo-Dice is not the native mass/pancreas Dice used for the comparison.
