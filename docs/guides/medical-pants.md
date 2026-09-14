# PanTS: download, audit, then train

PanTS can support a separate comparison of pancreas/mass segmentation and scan-level
tumor flagging. The public **PanTSMini** release contains **9,000 official training
scans and 901 official test scans**. These are not all 36,390 scans described in the
paper. Tumor-negative means no annotated pancreatic tumor; it does not mean a
universally healthy person. The shared lesion mask combines tumor types and does
not establish pathology-confirmed PDAC.

Start here, then read [scratch model recipes](medical-models.md),
[training and evaluation](medical-ct.md), and [campaign management](medical-campaigns.md).
The existing Task07 campaign keeps its original data, split, runtime and source.
PanTS requires new manifests, workspaces and experiment identities.

## Files and server location

```text
segmentary/
  scripts/download_medical_pants.py       # pinned download, checksums, safe extraction
  src/segmentary/medical/pants.py         # metadata, mask conversion, protected split
  configs/medical/pants/known-issues-20260913.json
  docs/guides/medical-pants.md            # this guide

/data/izadia1/datasets/pancreas/pants/release-3b1cd611/
  archives/                             # original downloads; never commit to Git
  data/
    metadata.xlsx
    ImageTr/PanTS_########/ct.nii.gz
    ImageTe/PanTS_########/ct.nii.gz
    LabelTr/PanTS_########/segmentations/*.nii.gz
    LabelTe/PanTS_########/segmentations/*.nii.gz
    SegmentaryPrepared/                 # separate, content-addressed derived files
  provenance/                           # release specification and upstream snapshot
  state/                                # integrity, extraction and audit records
  logs/
```

Images plus labels total about **361 GB compressed (336 GiB)**. Retain room for
archives, extracted data and training caches. HDRFS has sufficient space at setup;
check current free space before another copy. Downloads/extraction run in tmux,
without Slurm, sudo or GPU allocations.

## Download and verify

The downloader pins `BodyMaps/PanTSMini` revision
`3b1cd61108116b58ea5c1ddb3512c1847d965f96`. The separate JHU label archive is pinned
by its observed size and HTTP ETag. The image and metadata SHA-256 values come
from Hugging Face LFS. JHU publishes no label checksum: the recorded label SHA-256
is locally calculated, and gzip CRC checks transport integrity, not authorship.

```bash
PANTS_ROOT=/data/izadia1/datasets/pancreas/pants/release-3b1cd611
python scripts/download_medical_pants.py --root "$PANTS_ROOT" \
  --hf /data/izadia1/envs/pancreas-campaign-20260913/bin/hf
```

On the current server, image downloads are already running in `pants-images-download`.
The label transfer has finished. A separate `pants-verify-extract` session runs:

```bash
python scripts/download_medical_pants.py --root "$PANTS_ROOT" \
  --verify-extract-only --watch --wait-seconds 172800 --poll-seconds 30
```

Do not start a duplicate transfer while those sessions are active. The watcher
processes complete archives as they arrive. It rejects traversal, links, unexpected
members, duplicate paths and incomplete case coverage before publishing extracted
cases. Interruptions retain staging for verified reuse. Corrupt complete archives
stop the process with evidence; they are not silently replaced. Inspect
`state/progress.json` and `logs/verify-extract.log`. Download completion alone does
not establish training readiness.

The server's `pants-intake` session waits for all twelve pinned assets to finish
verification/extraction, then runs the strict full audit and, only if it passes,
creates the reserved-test split. Its script is retained at
`provenance/pants-intake-v2.sh`, with output in `logs/intake-v2.log`. It uses the separate
source snapshot `/data/izadia1/projects/segmentary-pants-intake-v2-20260913`; it does
not start a GPU campaign. These server processes continue independently of app
reminders. At the end of this setup, the app reported that the earlier 30-minute
follow-up no longer existed; it was not recreated automatically.

## Audit labels and physical geometry

Only the binary `pancreas.nii.gz` and `pancreatic_lesion.nii.gz` masks enter the
initial adapter. It creates **0 background, 1 pancreas, 2 mass**, with mass taking
precedence where masks overlap. All original multi-organ masks and combined labels
are preserved. The current medical models output three classes, not all 28 source
structures. Pancreas Dice defaults to the union of classes 1 and 2; disclose that
definition when comparing with a paper's organ metric.

Audit checks binary values, nonempty pancreas, finite CT, physical geometry,
source/derived hashes and agreement with the workbook's `tumor?` flag. Missing
lesion files are errors. `--allow-missing-negative-lesion` is an explicit alternative
for metadata-negative cases; do not enable it without reviewing annotation coverage.
Positive metadata with an empty lesion is an error. Lesion voxels outside the raw
pancreas are counted and retained, not clipped away.

The first real-data intake attempt found a scaled value of approximately
`1.000000059` instead of exactly `1` in the verified lesion mask for
`PanTS_00000026`. This tiny NIfTI scaling residue triggered the strict binary
check; it does not establish an incorrectly drawn annotation. The audit withheld
the manifest and preserved the failed attempt in
`state/engineering-smoke-20260913/audit-report.json` for review.

The explicit `--normalize-binary-roundoff` option handles only finite decoded
mask values within `1e-6` of 0 or 1 (absolute tolerance, zero relative tolerance).
It creates a separate exact uint8 mask and records the source scaling, maximum
change and raw/derived hashes. It rejects substantive fractional values and
does not change geometry or the original file. The ordinary medical validator
still requires exact labels. This normalization is recorded in the new cohort's
identity, not silently applied to an existing experiment.

Some observed release masks omit NIfTI spatial units. The optional
`--normalize-unknown-units-from-metadata` permits a **derived copy** declaring mm
only when the workbook spacing agrees with the source grid. It does not resample,
repair mismatched affines, reinterpret known non-mm units, or modify original
archives. This is a recorded interpretation of source spacing and must be disclosed.
The ordinary medical geometry checks remain strict.

The authors confirmed nine artifact lesion annotations. The checked-in exclusion
file lists exactly those cases with an evidence link; it does not remove arbitrary
small tumors. Other defects require their own documented resolution. A cohort
with exclusions is reported as such, never as the complete benchmark cohort.

After complete extraction:

```bash
segmentary-medical audit-pants --dataset-root "$PANTS_ROOT/data" \
  --output "$PANTS_ROOT/state/manifest.json" \
  --exclude-cases configs/medical/pants/known-issues-20260913.json \
  --normalize-unknown-units-from-metadata \
  --normalize-binary-roundoff \
  --audit-report "$PANTS_ROOT/state/audit-report.json"

segmentary-medical split-pants --manifest "$PANTS_ROOT/state/manifest.json" \
  --output "$PANTS_ROOT/state/split-seed0.json" --val-fraction 0.15 --seed 0
```

An audit report collects case failures while preserving completed case journals;
no training manifest is published when failures remain. Outputs refuse overwrite.
Use a new output filename for a rerun after resolving issues. For a bounded
engineering smoke, pass explicit `--case-id PanTS_########` arguments to the audit;
only official training cases are allowed, and the manifest is marked smoke-only.
Choose actual verified positive and negative cases after inspection.

## Protect the test and patient boundary

`split-pants` derives internal validation from the official training pool only.
The 901 official test IDs remain reserved. Both the generic splitter and downstream
split validation reject attempts to put official PanTS test cases into training
or validation. Known patient groups and exact image duplicates are linked; a
duplicate across the official boundary is an error to resolve, not permission to
move the test case into training.

The workbook has no original patient/source-case crosswalk. Without independently
verified grouping, cases are labeled `dataset_case_unverified`; scan IDs do not
prove patient independence. PanTS includes MSD and NIH source datasets, so it
cannot automatically be an independent test for Task07-trained models. Preserve
provenance and resolve overlap before any external-generalization claim.

The workbook's site, phase, reports and demographics are retained as provenance.
They are not network inputs. In particular, diagnostic report text must not leak
into an image-only tumor prediction experiment.

## Models and evaluation plan

The first real-data CPU smoke passed audit, a 2-train/2-validation split,
preparation, preprocessing, two scratch updates, full native-volume validation,
prediction and evaluation on cases 1, 2, 3 and 29. It used a tiny U-Net and 8 mm
preprocessing solely to verify execution. No official test case or GPU was used.
Evidence: `state/engineering-smoke-20260913-v2/evidence.json`. This does not prove
overfitting, useful accuracy, full-cohort quality or convergence.

A second frozen source snapshot also passed that entire CPU workflow on cases
1, 2, 3 and 26, exercising the explicit binary-roundoff normalization against the
previously rejected real mask. Evidence is in
`state/engineering-smoke-roundoff-20260913/evidence.json`; the earlier source,
failed audit and completed smoke workspace remain separate and preserved.

The adapter produces the same three-class contract consumed by the **27 existing
Torch recipes and official nnU-Net ResEnc backend**. They can therefore be trained
on an audited PanTS cohort with new configurations; availability is not evidence
that all have run on PanTS. Start with a real-data execution/overfit check, then
nnU-Net and a small set such as MedNeXt, MedFormer and a 2.5D model. Use our own
random initialization and scratch-origin resumes throughout.

Use the ordinary `prepare`, `preprocess`, `train`, `predict --partition val` and
`evaluate` commands with the new PanTS manifest/split and a new workspace.
The [model guide](medical-models.md) provides complete configurations. Set an
explicit PanTS training budget: copying Task07's 10,000 updates onto thousands
more scans does not provide comparable exposure. Document case sampling and
positive/negative balance as well as compute, updates and convergence.

Report mass Dice and pancreas Dice, plus scan sensitivity/specificity, lesion
localization, false-positive burden and confidence intervals. PanTS's README
patient sensitivity does not require correct localization; tumor sensitivity does.
Published leaderboard scores require matching cohorts, postprocessing and metric
definitions before comparison. A short internal validation run is not a reproduced
leaderboard result. Reserve final test scoring until the protocol is frozen.

## Sources and use terms

- [PanTS repository and baseline table](https://github.com/MrGiovanni/PanTS)
- [Pinned public dataset](https://huggingface.co/datasets/BodyMaps/PanTSMini/tree/3b1cd61108116b58ea5c1ddb3512c1847d965f96)
- [PanTS paper](https://www.cs.jhu.edu/~zongwei/publication/li2025pants.pdf)
- [Dataset license clarification](https://github.com/MrGiovanni/PanTS/issues/3#issuecomment-3165975004): dataset **CC BY-NC-SA 4.0**; separate upstream repository/model terms must be checked for those materials.
- [Author-confirmed artifact annotations](https://github.com/MrGiovanni/PanTS/issues/12#issuecomment-4538401573)
- [Other mask/geometry reports](https://github.com/MrGiovanni/PanTS/issues/4)
- [Original-source mapping discussion](https://github.com/MrGiovanni/PanTS/issues/15)

Our adapter is independently implemented; it does not import PanTS upstream code
or download pretrained checkpoints. Keep attribution and transformation records.
The data license does not itself establish institutional approval for a study.
