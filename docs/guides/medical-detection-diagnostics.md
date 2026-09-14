# PanTS-style metric names, with an explicit local diagnostic protocol

This supplemental report answers different questions from segmentation Dice. It
uses saved native predictions and leaves the selected checkpoint, training recipe,
primary evaluator and model-ranking rule unchanged. It is an exploratory analysis
of **annotated masses**, not a cancer diagnosis or clinical screening validation.

The [official PanTS benchmark](https://github.com/MrGiovanni/PanTS#pants-benchmark-official-in-distribution-test-set)
distinguishes patient sensitivity (a positive prediction anywhere in a positive
case) from tumor sensitivity (correct localization). The
[paper's metric appendix](https://arxiv.org/html/2507.01291v1) gives sensitivity,
specificity, ROC AUC and Dice formulas. These sources do not establish every
threshold and lesion-matching detail needed to reproduce the current leaderboard.
The [R-Super public evaluation demo](https://github.com/MrGiovanni/R-Super/blob/main/rsuper_train/Merlin_demo.md)
explains volume-based operating points and probability-based AUC. Our numbers
must not be compared directly with that leaderboard without matching cohort,
annotation version, patient grouping, decision threshold and official protocol.

## Fixed exploratory protocol

`exploratory_mass_detection_v1` was fixed before running this new diagnostic; it
was added after the screening campaign began. It is not a prospective study
preregistration. The 10 mm³ floor and IoU 0.1 are explicit engineering choices,
not validated clinical cutoffs or claimed PanTS defaults. Freeze the full JSON
protocol and its hash before comparing runs. Do not tune these choices on the
held-out test set.

| Metric | Exact definition |
| --- | --- |
| P-Sen | A reference-positive group has at least one class-2 voxel in any fully annotated scan. A predicted-positive group has at least one retained predicted class-2 component in any scan, irrespective of its location. Report TP/(TP+FN). |
| T-Sen | Label class-2 masks into 3D components using 26-connectivity. Retain predicted components of at least 10 mm³; never filter reference components. Match components one-to-one at IoU ≥0.1, maximizing match count before total IoU. Report matched/reference components. This is a **component-based lesion proxy**, not independently adjudicated tumor instances. |
| Specificity | TN/(TN+FP) among fully annotated reference-negative groups. Organ-only and unlabeled cases never supply negative controls. |
| AUC | ROC area from the maximum native class-2 probability, then the maximum across scans in each group. Scores come exclusively from image-only inference telemetry. Ties receive half credit. Both reference classes and valid continuous scores for every case are required. |
| Mass DSC | Unfiltered native class-2 Dice on reference-positive scans, averaged within each supplied patient group and then equally across groups. Both-empty cases are excluded. |
| Pancreas DSC | Same aggregation on the native union of classes 1 and 2, restricted to reference-positive pancreas scans. |

P-Sen's mask operating point and AUC's continuous score are separate. A scan may
have no class-2 argmax voxels while retaining a nonzero mass probability. Dice and
reference overlap are never used to construct the AUC score. Small fragments can
split a semantic mask into multiple components, and a merged prediction can
match only one reference component. Physical volume uses native millimetre
spacing; this diagnostic accepts the same unsheared geometry as the primary
native evaluator.

The current audited Task07 validation split has **42 labeled scans, all 42 with
class-2 voxels, and zero annotated negative scans**. This was checked from the
HDRFS manifest's `label_counts`, not inferred from the dataset name. Specificity
and AUC are therefore unavailable on that split. Its 42 patient keys have
`dataset_case_unverified` grouping: P-Sen is a group/case proxy until source
patient identities are confirmed. Task07 class 2 does not establish malignancy.

## Execution and evidence

Run only after the primary native evaluation has completed. Use the original
bound prediction directory so the script can check the prediction record's run
identity and checkpoint index. The script verifies the frozen manifest/split,
exact primary-evaluation cohort, label hashes, prediction hashes, native geometry,
and prediction telemetry. It loads no model or checkpoint. Old runs without
continuous telemetry can still supply mask metrics; AUC stays unavailable.

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
python scripts/evaluate_medical_detection.py \
  --manifest /path/to/manifest.json \
  --splits /path/to/splits.json \
  --partition val \
  --predictions /path/to/run/predictions/val \
  --evaluation-report /path/to/primary-evaluation/report.json \
  --output /path/to/run/clinical-detection
```

Test use requires both `--partition test` and `--final-test`. For an explicitly
amended exploratory protocol, supply `--protocol frozen-protocol.json`; every
field and threshold is validated and the content hash is saved. Keep that
amendment separate from the original report. Existing output directories are
never overwritten.

`report.json` stores every denominator, TP/TN/FP/FN count, lesion match, numerical
value, source/protocol/checkpoint hash and software version. Each unavailable
metric has a controlled `reason_code` plus readable explanation. Any failed or
missing reference/prediction withholds **all full-cohort metric values**; counts
from valid cases remain visible with an explicit partial-coverage label. These
sidecars are diagnostic and do not change the primary ranking.

The campaign reporter reads `run/clinical-detection/report.json` and shows an
all-model companion table. Its public summary exports aggregate values only;
case/patient rows remain in the approved research artifact directory.
