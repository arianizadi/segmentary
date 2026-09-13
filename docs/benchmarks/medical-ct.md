# Medical CT validation record

The medical workflow is validated separately from the existing 2D results. Synthetic correctness tests establish software behavior, not clinical accuracy.

## CPU contracts

The test suite exercises complete synthetic Task07 auditing, changed file/manifest hashes, patient/duplicate leakage including transitive links, subset lineage, unlabeled/organ-only semantics, physical NIfTI geometry, DICOM slice ordering and per-slice HU scaling, strict native exports, empty/missing prediction policies, surfel-area physical distances, patient bootstrap/paired comparisons, held-out staging, command-line integration and backend lifecycle/identity checks.

The combined synthetic CLI workflow checks audit -> split -> prepare -> saved-mask evaluation -> Markdown report. A perfect anisotropic prediction yields Dice 1 and HD95 0; held-out images are absent from nnU-Net's development layout.

Release checks passed: 104 medical tests, the complete 1,688-test passing repository suite (41 skipped), Ruff lint/format, mypy, `pip check`, repository documentation links and `git diff --check`. Skipped GPU/external-dataset checks are not counted as executed; the separately described real GPU smoke supplies the live backend evidence.

## Live verification

Verified on September 13, 2026, using one NVIDIA L40S on HDRFS (46,068 MiB reported VRAM, driver 570.133.20). The isolated Python 3.11 runtimes used PyTorch 2.11.0+cu128 and nnU-Net 2.8.1. Both environments passed `pip check`. Jobs ran directly as the account user, without Slurm or sudo.

| Check | Observed result | Limit |
|---|---|---|
| Dataset transfer | 19,646 files / 22,244,600,936 bytes matched their source SHA-256 hashes; zero missing, extra or mismatched files | Copy integrity does not establish clinical validity |
| Complete Task07 audit | All 420 CTs and 281 masks decoded; finite values, millimeter units, affine consistency, labels and paired geometry passed | Patient identity remains `dataset_case_unverified`; masks do not establish pathology-confirmed PDAC |
| NIH DICOM conversion | One 240-slice series converted to 512 × 512 × 240; output/mask affine difference was zero; 15 independent world-coordinate and HU comparisons had zero error | One of 80 series checked; not a complete NIH conversion audit |
| GPU lifecycle | A separate two-volume ResEnc M `3d_fullres` run was interrupted after a checkpoint, then resumed to epoch 3 with checkpoint lineage intact | Three epochs with two training updates per epoch is an execution smoke, not a memorization or convergence test |
| Native prediction and evaluation | Full-volume prediction completed for the one validation case; saved-mask geometry and reference checks passed; evaluation and review overlay exported without failures | The undertrained prediction visibly remains poor; no segmentation quality result is claimed |

The smoke used one training volume and one separate validation volume, seed 0, two augmentation workers, and `deterministic: false`. The latest passing attempt is `gpu-smoke-20260913-v3`; the preceding failed attempts remain recorded. Those checks exposed and fixed a zero-thread preprocessing setting and an unsupported strict-deterministic CUDA cross-entropy operation. Strict mode remains explicit and fails on unsupported operations; it is never silently relaxed.

Measured in the resumed stage:

| Measurement | Value |
|---|---|
| Peak allocated GPU memory | 10,818,433,024 bytes (10.08 GiB) |
| Peak reserved GPU memory | 12,392,071,168 bytes (11.54 GiB) |
| Training telemetry time | 24.80 seconds |
| Full-volume validation telemetry time | 24.19 seconds |
| Resumed training stage wall time, including startup/export | 63.33 seconds |
| Separate validation prediction stage wall time | 31.83 seconds |

These are measurements of the small smoke recipe, not throughput or memory estimates for the full ResEnc L baseline. The training-stage GPU-hours were 0.01759 and separate prediction-stage GPU-hours were 0.00884; initial planning and the interrupted stage are additional costs.

The server retains `smoke-result.json`, checkpoint hashes, trainer settings, runtime/plan identities, stage logs, telemetry, native predictions and evaluation outputs under the dataset's `verification/gpu-smoke-20260913-v3/` directory. Real manifests, CTs, checkpoints and review images remain outside Git. The reproducible helper is [medical_gpu_smoke.py](../../scripts/medical_gpu_smoke.py).

## Acceptance boundary

The CPU suite and real GPU run establish the implemented execution and evaluation contracts. Before interpreting a baseline, still establish patient grouping, review varied real-case overlays with the clinical collaborators, demonstrate a prespecified small-case overfit target, and run the frozen complete development baseline. No clinical accuracy, PDAC detection performance, external generalization or publishable result is established by this record.
