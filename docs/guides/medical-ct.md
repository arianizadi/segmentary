# Medical CT volumes

`segmentary-medical` is a separate medical-volume workflow. It uses audited NIfTI volumes and the official nnU-Net v2 trainer instead of treating CT as RGB PNG images. Existing `segmentary-train` and object workflows retain their current contracts.

For the larger PanTS cohort, follow the [PanTS setup guide](medical-pants.md) for
release downloads, mask conversion, known annotation issues and protected splits.

## Install and inspect

Use a dedicated Python 3.11 environment. Install the appropriate platform PyTorch build first; then install the optional workflow:

```bash
python -m pip install -e '.[medical]'
python -m venv /path/to/nnunet-env
# Install the matching CUDA PyTorch build inside nnunet-env first.
/path/to/nnunet-env/bin/python -m pip install -r requirements/medical-training.txt
segmentary-medical doctor --require-training --backend-python /path/to/nnunet-env/bin/python
```

For CPU-only data conversion and evaluation, `pip install -e '.[medical]'` is sufficient. The training adapter is pinned to `nnunetv2==2.8.1`; medical data/metrics use NiBabel 5.4.2, pydicom 3.0.2 and surface-distance 0.1. Framework upgrades require adapter validation and a new experiment identity.

The training environment is separate because nnU-Net's dynamic-network-architectures dependency requires `timm<1.0.23`, while Segmentary pins `timm==1.0.28`. Do not install the full Segmentary package into that backend environment or downgrade the existing stack. Set `backend_python` in the experiment configuration; the harness passes its versioned medical worker source to the external interpreter.

Doctor checks installed dependencies and driver visibility without allocating GPU tensors. It is not a training benchmark. Jobs run directly under your account with a lock per GPU; Slurm and sudo are not used. Run long commands in your usual persistent terminal/tmux session. Different GPUs and workspaces can run concurrently; start with one job and measure storage/CPU throughput before filling the server.

## Supported scope and label meaning

The first backend trains exclusive labels **0 background, 1 pancreas, 2 mass**. The evaluator defaults to pancreas = union of labels 1 and 2, with a separate mass score; `--pancreas-exclusive` explicitly scores label 1 instead. Task07's source label says cancer, but its mask alone does not establish pathology-confirmed PDAC.

Task07's unannotated test scans remain unannotated. NIH organ-only masks must not become negative tumor labels. The manifest/evaluator represent organ-only and unknown supervision explicitly; this joint nnU-Net training adapter rejects organ-only cases in training/validation. Combining those cohorts for mixed partial supervision requires a separate scientifically defined training objective. It is not enabled by relabeling missing targets to zero.

The backend supports nnU-Net ResEnc M/L/XL and `3d_fullres` or `2d`. The latter is nnU-Net's own volume-aware 2D configuration, not a conversion of every existing Segmentary model into a 3D model. Prompted annotation, synthetic generation, clinical PDAC classification and 3D instance/panoptic training are separate research extensions, not implied capabilities of this segmentation workflow.

## Audit the source and make immutable splits

Replace `/data/pancreas/...` with your actual source/artifact locations. Keep artifacts outside Git.

```bash
segmentary-medical audit \
  --dataset-root /data/pancreas/raw/Task07_Pancreas \
  --output /data/pancreas/manifests/task07.json

segmentary-medical split \
  --manifest /data/pancreas/manifests/task07.json \
  --output /data/pancreas/manifests/split-seed0.json \
  --train-fraction 0.70 --val-fraction 0.15 --seed 0
```

Audit fully decodes CT/masks and checks finiteness, physical units, shape, affine, label values, file hashes and decoded-image hashes. It rejects missing or contradictory spatial metadata instead of silently fixing it. Inspect real overlays before committing GPU hours.

If an independently established patient crosswalk is available, add `--groups groups.json` with a `{"groups": {"case_id": "patient_id"}}` mapping covering all source cases, including unlabeled cases. Without it, grouping is explicitly marked `dataset_case_unverified`; filename grouping does not prove clinical patient independence. The splitter links known duplicate image contents and patient groups, including indirect links through excluded cases. It refuses incomplete/disjointness violations and never puts unannotated or organ-only cases into the joint supervised split.

Outputs are versioned by contents and refuse overwrite. Patient-level confidence intervals remain conditional on the validity of those group identities. Source/pretraining overlap that is not visible in these files still needs a provenance audit.

## Configure, prepare and train

Copy [medical-pancreas.yaml](../../configs/examples/medical-pancreas.yaml) into your experiment folder. Set its workspace and GPU explicitly. Relative workspace paths resolve against the configuration file's directory.

```bash
segmentary-medical prepare --config pancreas.yaml \
  --manifest /data/pancreas/manifests/task07.json \
  --splits /data/pancreas/manifests/split-seed0.json --dry-run

segmentary-medical prepare --config pancreas.yaml \
  --manifest /data/pancreas/manifests/task07.json \
  --splits /data/pancreas/manifests/split-seed0.json

segmentary-medical preprocess --config pancreas.yaml
segmentary-medical train --config pancreas.yaml
```

Prepare creates an isolated nnU-Net layout using read-only source access and explicit `splits_final.json`. Only training and validation enter the development layout. Held-out test images/labels are excluded from planning and training. **Planning/fingerprinting uses training plus validation**, as in ordinary nnU-Net development-set preprocessing; do not describe this as strictly training-fold-only fitting of all preprocessing statistics.

The resolved nnU-Net plan chooses physical resampling, patch size and batch size. The official trainer supplies augmentation, loss/deep supervision, optimizer, mixed precision and validation checkpoint selection. The adapter records the plan and resolved trainer settings. Default execution records seeds while allowing nondeterministic CUDA operations and uses the configured augmentation workers. `deterministic: true` requests strict deterministic kernels and synchronous augmentation; unsupported CUDA operations fail rather than silently relaxing the policy. PyTorch 2.11 CUDA cross-entropy was observed to reject strict mode on the tested L40S runtime. Compilation is disabled and recorded. Neither mode promises bitwise mid-epoch replay.

One workspace is one immutable recipe. Data contents, manifest/splits, source code, environment, plan and checkpoint lineage are checked. Changes require a new workspace, not an in-place continuation. Partially prepared/unbound caches are rejected. Keep the source revision and environment fixed for the experiment.

## Smoke, overfit and resume

Before a baseline, create a separate subset and workspace:

```bash
segmentary-medical subset --manifest /data/pancreas/manifests/task07.json \
  --output /data/pancreas/manifests/smoke.json \
  --case-id pancreas_001 --case-id pancreas_002
segmentary-medical split --manifest /data/pancreas/manifests/smoke.json \
  --output /data/pancreas/manifests/smoke-split.json \
  --train-fraction 0.5 --val-fraction 0.5
```

Use actual existing case IDs. Set a new workspace and `purpose: smoke` (or `overfit`) in a copied configuration. Only these purposes allow positive `num_epochs`, `num_iterations_per_epoch` and `num_val_iterations_per_epoch` overrides. A short smoke proves execution; an overfit experiment requires a prespecified memorization target and enough iterations to assess it. Neither is a baseline result. Predict the training partition to measure memorization; keep validation patients separate.

```bash
segmentary-medical resume --config pancreas.yaml
segmentary-medical resume --config pancreas.yaml --checkpoint checkpoint_latest.pth
segmentary-medical cancel --config pancreas.yaml
```

Resume selects an existing identity-bound recovery checkpoint, or fails; it never falls back to fresh training. Recovery is at saved epoch boundaries, with RNG state recorded. Missing/mismatched checkpoints are errors. Cancellation targets only the recorded live worker process group with PID-identity checks on Linux. The saved checkpoint cadence determines how much work can be recovered.

## Predict without labels, then evaluate saved masks

```bash
segmentary-medical predict --config pancreas.yaml --partition val
```

The command prints the output directory. It uses image paths only, performs full-volume inference and verifies that exported NIfTI masks match each input's native geometry. Probabilities, mirroring and sliding-window step size are explicit frozen configuration fields. Training/validation/unlabeled prediction can be invoked separately; test prediction requires `--partition test --final-test`.

Use that printed directory below:

```bash
segmentary-medical evaluate \
  --manifest /data/pancreas/manifests/task07.json \
  --splits /data/pancreas/manifests/split-seed0.json --partition val \
  --predictions /data/pancreas/runs/baseline/predictions/val-TIMESTAMP \
  --output /data/pancreas/evaluations/baseline-val \
  --bootstrap-samples 1000 --review-overlays

segmentary-medical report \
  --input /data/pancreas/evaluations/baseline-val/report.json \
  --output /data/pancreas/evaluations/baseline-val/report.md
```

Add `--surface-tolerance-mm VALUE` after defining a clinically appropriate tolerance. HD95 and surface Dice use physical spacing and area-weighted surface elements, not 2D pixel distances. The value is a protocol choice, not a universal pancreas threshold.

The evaluator saves per-case CSV, aggregate JSON, and optional pseudonymous CT/reference/prediction PNG overlays. A missing/invalid prediction on a valid positive reference receives zero Dice. Undefined/infinite distances remain null with explicit status and coverage. Both-empty masks are reported separately rather than improving tumor means. Means first average examinations within each patient, then patients; intervals bootstrap those patient groups. Failed references remain unscorable and are counted.

`--lesion-iou-threshold VALUE` optionally evaluates connected-component lesion candidates with one-to-one matching. It reports failure coverage and unknown false positives for failed inference. Connected components are an operational definition, not a validated instance annotation or a PDAC diagnosis.

Final-test evaluation also requires an explicit `--final-test`. A flag records intent; it cannot prevent a researcher from seeing results and changing a study. Freeze model choices/thresholds before using it and document deviations.

## Compare two runs

```bash
segmentary-medical compare \
  --left /data/pancreas/evaluations/a/report.json \
  --right /data/pancreas/evaluations/b/report.json \
  --region mass --metric dice --bootstrap-samples 1000 \
  --output /data/pancreas/evaluations/paired-mass-dice.json
```

The comparison requires the same manifest, eligible cases, patient grouping and metric policy. It reports patient-bootstrap differences **B minus A**. One-sided undefined metrics are rejected rather than silently selecting a favorable subset. Dataset/site/phase/size subgroup analyses can use explicitly defined case lists through the Python evaluator; a single dataset does not establish external generalization.

## NIH DICOM conversion

```bash
segmentary-medical convert-dicom \
  --series /data/pancreas/raw/nih-one-series \
  --mask /data/pancreas/labels/label0001.nii.gz \
  --output /data/pancreas/prepared/nih_0001.nii.gz
```

This command handles one regular single-frame CT series. It sorts by physical position, validates orientation/spacing, applies per-slice HU scaling and preserves physical coordinates. Optional mask alignment permits exact axis reorientation, not arbitrary guessing or registration. Mixed, irregular, unsupported or inconsistent series fail. Convert to a new path; keep DICOM and source masks intact.

## Artifact contract and verification

```text
workspace/
  binding.json, resolved-config.json, preparation.json
  nnUNet_raw/, nnUNet_preprocessed/, nnUNet_results/
  plan-binding.json, checkpoint-index.json, trainer-settings.json
  stages/<stage-id>/request.json, runtime.json, subprocess.log, outcome.json
  active-stage.json
  predictions/<partition-id>/ native masks + provenance + geometry checks
```

Data, masks, checkpoints, real manifests, probability volumes and review images belong on approved artifact storage, not Git. Local logging is sufficient; no online experiment tracker is required. Dependency/runtime settings do not independently establish clinical data authorization or HIPAA compliance.

Verification covers synthetic anisotropic geometry, DICOM ordering/scaling, unknown-label semantics, transitive duplicate/group leakage, empty/missing predictions, metric values, patient statistics, held-out staging and the combined CPU workflow. See the [medical validation record](../benchmarks/medical-ct.md) for checks actually run and their limits. A working harness does not establish convergence, diagnostic accuracy or clinical utility.

## Reproduce the bounded GPU integration check

```bash
python scripts/medical_gpu_smoke.py \
  --manifest /data/pancreas/manifests/task07.json \
  --output /data/pancreas/verification/gpu-smoke-new \
  --backend-python /path/to/nnunet-env/bin/python --gpu 0
```

This selects two small labeled volumes, creates a separate ResEnc M smoke configuration, interrupts after a recovery checkpoint appears, resumes, and evaluates native-space validation predictions. All failures and intermediate workspaces remain distinct. It checks execution, not convergence or a clinically meaningful segmentation score.
