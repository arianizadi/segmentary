# Cross-validation folds, GPU guard and checkpoint policy

This guide covers three safeguards for nnU-Net Task07 campaigns: development cross-validation that preserves the frozen split, a hard guard against GPUs reserved for other users, and scoring of both the terminal and the selected checkpoint. Read the [campaign guide](medical-campaigns.md) and the [strong recipe guide](medical-strong-recipe.md) first.

## Development cross-validation manifest

```bash
python -m segmentary.medical.cli cv-split \
  --manifest /path/to/task07-manifest.json \
  --splits /path/to/task07-splits.json \
  --output /path/to/task07-cv5-seed0.json \
  --folds 5 --seed 0
```

- **Fold 0 is the frozen split.** Its train and validation lists are identical to the frozen file, in the same order. A fold-0 run under the manifest trains on exactly the cases of a run without it.
- **The other folds (1–4 with `--folds 5`) divide the frozen training cases only.** Connected patient and duplicate groups stay together. When every training case records `label_counts` and `spacing_mm`, groups are sorted by annotated mass volume and assigned in seeded blocks, which stratifies by volume. Otherwise the assignment is a seeded shuffle. The `assignment.method` field records which rule ran.
- **The held-out test cases never enter a fold.** The manifest records only their count. The validator rejects any fold that changes fold 0, contains a test case, overlaps another fold, or splits a group.
- **The manifest is a new protected file.** The command refuses to overwrite any file, including the frozen split. The manifest records its own fingerprint and the SHA-256 of the split file it was derived from.

A recipe selects a fold with three fields: `fold`, `cv_splits` (absolute path) and `cv_splits_sha256`. The fold must exist in the bound manifest (`cv-split` makes 2–20 folds); this is checked before prepare writes anything. Any fold other than 0 requires the manifest. Without it, `fold` must stay 0, as before. The prepare step writes every fold to nnU-Net's `splits_final.json`, and the binding records the manifest hash. A later edit to the manifest therefore stops the run. Raw data, planning and the imported reference cache are the same for every fold: the cache stays bound to the 239 development cases, and only `splits_final.json` differs from the reference.

Prediction and evaluation use the run's own fold. The evaluator accepts `--cv-splits PATH --cv-splits-sha256 SHA --fold K` for the `train` or `val` partition, never `test`; it refuses a manifest whose SHA-256 differs from the frozen value and records the manifest hash and fold under `cohort` in `report.json`. The campaign runner and reporter read the fold from the recipe and check the same hash. The runner also re-hashes every bound CV manifest before each stage. During training, the nnU-Net worker wraps `trainer.do_split()` and stops if nnU-Net's train or validation list is not exactly the bound fold, so nnU-Net's silent random 80:20 fallback cannot be used.

Planning still uses all 239 development cases, as in the earlier nnU-Net runs. This means every fold's validation cases informed the preprocessing statistics. Out-of-fold scores are therefore development estimates, not independent tests.

## GPU guard

`segmentary.gpu_policy.DEFAULT_FORBIDDEN_GPUS` is `{0, 1}`, as physical indices under `CUDA_DEVICE_ORDER=PCI_BUS_ID`. `SEGMENTARY_FORBIDDEN_GPUS=4,5` adds indices. It cannot remove the defaults, and a malformed value fails closed. The following refuse a forbidden GPU, with an error that names the forbidden set:

- the runner, when it loads a campaign spec (including each optional per-run `gpu` pin), and again before each stage process starts;
- the nnU-Net and Torch backends, before they expose a GPU to any child process, including runtime probes;
- both backend workers, which require `CUDA_VISIBLE_DEVICES` to be set to exactly their configured GPU (empty for a Torch CPU run) and `CUDA_DEVICE_ORDER=PCI_BUS_ID`. A worker started by hand with the variable unset is refused instead of seeing every GPU.

The forbidden set applies on every host. `scripts/medical_gpu_smoke.py` therefore has no default `--gpu`. The nnU-Net workspace binding hashes `src/segmentary/gpu_policy.py` together with `src/segmentary/medical/*.py`.

**Scope.** The forbidden set is enforced by the medical campaign runner (and so by every medical planner that validates its spec with it), the seed/fold planner and the medical backends. The generic `gpu_policy` helpers used by non-medical campaigns (`freeze`, `require_allowed`, `child_env`, `shell_prefix`) do not consult it; those campaigns keep their own GPU lists.

A run's optional `gpu` field pins it to one of the campaign's `gpus`. Use pins when each run must land on a specific card.

## Checkpoint policy

For the nnU-Net backend, the runner scores two prediction sets on the native validation fold:

| Role | Checkpoint | Runner stages | Evaluation directory |
| --- | --- | --- | --- |
| Primary | `checkpoint_final.pth` | `predict`, `evaluate` | `<state>/evaluations/<run>` |
| Secondary | `checkpoint_best.pth` | `predict_best`, `evaluate_best` | `<state>/evaluations-checkpoint-best/<run>` |

The best checkpoint was selected on the same validation cases. Its score is optimistic, and reports label it that way. Reports rank only on the primary score, and a model page's "Checkpoint selection" row says `none: terminal checkpoint_final.pth` when the primary is the final checkpoint. For historical compatibility the run state still stores the primary checkpoint's hash as `selected_checkpoint_sha256`; `checkpoint_policy` says which rule applies. A comparison group with a single run is not ranked.

The evaluator refuses a nonempty output folder. If an `evaluate` or `evaluate_best` stage is interrupted, the runner renames the partial folder to `<folder>.incomplete-<ns>` (listed in the run state's `incomplete_evaluations`) and evaluates again on resume. Nothing is deleted. The rank gate requires one checkpoint policy within each comparison group. `results.csv` adds `primary_checkpoint`, `secondary_checkpoint`, `secondary_mass_dice` and `secondary_pancreas_dice`. Each model page shows both scores.

The Torch backend keeps one evaluation of its selected-best checkpoint. The nnU-Net training worker also writes a `validation-*` export after training. That export uses `checkpoint_best.pth`, and `training-validation.json` now says so. It is not a terminal-checkpoint prediction. `predict_best` deliberately predicts the same cases again through the audited `predict` stage, so the secondary score has the same stage records and artifact hashes as the primary one; it costs a few GPU-minutes per run.

## Planning seed and fold runs

`scripts/plan_medical_seed_folds.py` freezes ResEnc L `3d_fullres` runs from one verified preprocessing reference. Each `--run GPU:FOLD:SEED` becomes one pinned run that uses the full official budget, no mirroring and tile step 0.5. The planner reads metadata only and launches nothing. Its campaigns carry the preset `task07_nnunet_seed_folds_v1`; whenever the runner loads such a spec it re-checks the manifest, split and CV hashes against the plan and checks that every recipe keeps the planned fixed fields, reference plan, CV binding, GPU pin and `nnunet_resenc_l-fold<k>-seed<s>` identity.

Region-based (overlapping pancreas ⊇ mass) labels are not implemented. The reference-cache import copies label-based preprocessing, including foreground sampling locations, so a region option needs its own planned and verified cache.
