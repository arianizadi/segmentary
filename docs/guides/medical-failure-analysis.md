# Finding failures before designing a new architecture

Use this workflow after a run finishes its native validation evaluation. It reads saved CTs, labels and predictions; it never trains, loads model weights, edits labels or restarts a campaign. The running campaigns keep their frozen source and recipes.

## What is available

| Tool | Purpose |
| --- | --- |
| `scripts/analyze_medical_failures.py` | Whole-cohort lesion errors, native overlap/boundary scores, size/spacing buckets, model comparisons and offline review |
| `scripts/audit_medical_roi_coverage.py` | Count annotated tumor outside a frozen predicted crop, before stage-two results are available |
| `scripts/compare_medical_failure_reports.py` | Pair the same patients across models/seeds, with bootstrap intervals and separate seed variation |
| `scripts/plan_medical_architecture_study.py` | Specify hypotheses, baseline/component/capacity controls and multiple scratch seeds; validate saved plans |
| `scripts/audit_medical_cohort_overlap.py` | Check exact content and documented identity overlaps between audited manifests; absence of matches does not prove independence |
| `scripts/analyze_medical_failures.py --review-report ... --decisions ...` | Validate reviewer exports against the exact report and case evidence |

Existing training-input audits, fitting diagnostics, full-batch GPU profiling, inference benchmarking, controlled recipes, checkpoint lineage and retention continue to supply the training infrastructure. See [recipe experiments](medical-recipe-experiments.md) and [architecture study design](medical-architecture-studies.md).

The first [real-data verification and aggregate comparison](../results/pancreas/task07/failure-review-20260914/README.md) covers six completed models on all 42 Task07 validation scans, with 324 review panels and both cascade crop audits.

## Make a report from a completed campaign

Run inside the new checked-out Segmentary source with its medical dependencies. Use an artifact directory outside the repository. Set `PYTHONPATH=src` if this checkout is not the installed source.

```bash
PYTHONPATH=src python scripts/analyze_medical_failures.py \
  --campaign /data/izadia1/projects/segmentary-runs/pancreas/task07-recipe-explorations-20260914 \
  --run-ids dynunet-control10k-seed0 dynunet-deep10k-seed0 dynunet-focal10-seed0 \
  --output /data/izadia1/projects/segmentary-failure-review-example \
  --review-limit 8 --review-random 2 --slices-per-plane 3
```

Only explicitly selected **completed** runs are accepted by the campaign adapter. A new output directory is required. For cross-campaign models, pass `--spec analysis.json` containing:

```json
{
  "manifest": "/absolute/audited-manifest.json",
  "splits": "/absolute/frozen-splits.json",
  "partition": "val",
  "models": [
    {
      "id": "baseline",
      "seed": 0,
      "prediction_dir": "/absolute/workspace/predictions/val",
      "evaluation_report": "/absolute/native-evaluation/report.json"
    }
  ]
}
```

Each prediction must retain its original binding, checkpoint index and prediction receipt. nnU-Net's timestamped native prediction directories are supported. No checkpoint tensor is loaded. Seeds come from the bound training config; a caller cannot rename one checkpoint as multiple seeds. Add `roi_manifest` and `roi_manifest_sha256` for ROI-trained models, exactly matching their bound config. Evaluation cohorts, whole-pancreas definition and scientific metric protocols must match.

Only train/validation partitions are available. Explicit test requests are rejected before reading payloads. Existing image/reference/prediction hashes and native affines are checked. Missing or invalid cases remain visible; they cannot silently improve the denominator. Bucket summaries over valid cases are descriptive and carry coverage; they are not complete-cohort performance claims.

## Read the output

```text
failure-review/
  README.md                 coverage and reading instructions
  report.json               full metrics, per-lesion records and evidence
  cases.csv                 one row per case/model
  failure-patterns.md        readable size/spacing/error summaries
  lesions.csv               physical lesion records and extra prediction components
  crop-coverage.csv         per-case/per-lesion crop exclusions, where available
  model-disagreements.csv   paired case differences and shared misses
  progress.json             mutable progress during report generation
  private-errors.json       local diagnostic errors if any
  review.html               offline multi-model review and reviewer feedback
  panels/<case>/<model>/     synchronized axial/coronal/sagittal PNGs
  private-source-map.json    source-key mapping and original input paths
```

Open `review.html` in a local browser with its adjacent files. Images and report data are local; there is no remote analytics or external script. Default model aliases hide identities and scores on the display. This is a convenience for review, not secure blinding: the underlying report includes model names. Revealing identities is tracked for subsequent decisions. Notes include reviewer, case/model scope, category, confidence and revision history; export them to retain a portable copy. Browser storage alone is not a research archive.

The queue retains every case's metrics and initially selects a case with exported panels when available. Use **Has image panels** to filter to the visual-review subset.

Validate an exported review without changing annotations:

```bash
PYTHONPATH=src python scripts/analyze_medical_failures.py \
  --review-report /absolute/failure-review/report.json \
  --decisions /absolute/reviewer-export.json \
  --output /absolute/validated-review.json
```

Imports reject a different report, changed case evidence, unsupported verdicts and conflicting revisions. A radiologist's note is a review observation, not automatically a corrected ground truth.

## Interpret the diagnostic categories

- **Missed component:** no predicted mass overlap. **Partial:** some overlap but insufficient IoU or a one-to-one matching conflict. Both can be detection failures. The default connected-component matching uses 26-connectivity, IoU 0.1, and no prediction-size filter. These diagnostic rules differ from any clinical report using a 10 mm³ filter; do not interchange their numbers.
- **Unmatched prediction:** a predicted component not matched one-to-one. Connected components are algorithmic proxies, not radiologist-adjudicated tumor instances.
- **Boundary distance:** native HD95 and surface Dice retain the primary evaluator's shared metric definitions. A low Dice or high distance flags review; neither proves bad annotations.
- **Size strata:** equivalent-sphere diameter from physical lesion volume, not RECIST diameter. Predeclared 10/20 mm edges and explicit denominators avoid selecting cutoffs after results.
- **Spacing strata:** canonical RAS superior-inferior voxel spacing, not a verified scanner slice-thickness field. Oblique acquisitions and acquisition differences require separate metadata review. Site, contrast phase and scanner labels are not inferred from CT appearance.
- **Crop exclusion:** reference tissue outside the fixed predicted box counts as missed. Reference labels are used only for this post-prediction audit, never to make or repair validation crops.

The first eight cases are severity-ranked review examples and two are sampled from the remainder. This is not random prevalence estimation. Every model receives exactly the same physical slice indices in each selected case. Panels use canonical RAS, physical aspect ratio, fixed HU [-100,240], reference/prediction contours and explicit mass false-negative/false-positive overlays. They are review aids, not a clinical viewer. Use `--slices-per-plane 0` to export all slices of selected cases; this can create many files. Default selected slices are not full-volume review. Increase case limits deliberately or use a medical volume viewer for exhaustive inspection.

## Audit the cascade before stage two completes

```bash
PYTHONPATH=src python scripts/audit_medical_roi_coverage.py \
  --manifest /absolute/audited-manifest.json --splits /absolute/frozen-splits.json \
  --roi /absolute/predicted-roi20.json --expected-sha256 HASH_FROM_FROZEN_RECIPE \
  --partition val --output /absolute/roi20-coverage.json
```

The crop audit preserves all reference lesions, including entirely excluded ones, and reports empty-prediction fallbacks separately. Current Task07 training crops are generated in-sample by our stage-one model; that limitation remains. Out-of-fold crop generation and an independently held-out final test are requirements for a later confirmatory cascade protocol, not implemented or implied by this audit.

## Turn errors into experiments

Have the radiology collaborator review a mixture of difficult and ordinary examples. Record whether errors are mainly localization, boundary delineation, false positives, acquisition effects or annotation ambiguity. Then predeclare one hypothesis and use the architecture-study planner for baseline, candidate, component-off and capacity-control roles across seeds. New architectural modules still need their own code, gradient/resume checks and full-batch GPU/geometry validation before launch. This tooling supplies the research process; it cannot establish novelty, clinical validity or SOTA automatically.

Keep CT panels, source mappings, patient-level metrics and reviewer notes in approved research storage. Hashed keys do not by themselves establish anonymization. Ordinary Git publishers must not publish this directory. Publish only deliberately reviewed aggregate summaries. Changes to source labels require separate adjudication, versioned datasets and new experiment bindings; none of these tools edits labels.
