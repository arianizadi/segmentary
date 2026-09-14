# Pancreas Task07: model comparison

**Controlled recipe explorations:** fresh scratch runs, 10,000 updates each, using the same development partition. The frozen campaign lists exact changes in loss, normalization, spacing, architecture or predicted-organ cropping. Compare each candidate with its control using full-native per-patient metrics. These are one-seed validation experiments, not equal-compute architecture rankings or independent test results. Cascade misses outside the crop still count.

Generated: 2026-09-14T23:58:36.669554+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

**9 queued.** GPU queue: 1, 2, 3, 4, 5, 6, 7, 8.

1. Open [comparison.md](comparison.md) for model status and comparable validation results.
2. Open [learning-curves.md](learning-curves.md) to check whether each model is learning.
3. Follow a model link for its recipe, objective, timing, memory, coverage, and evaluation interval.
4. Read [optimization.md](optimization.md) for the throughput investigation and measurement limits.
5. Open [training-cost.md](training-cost.md) and [inference.md](inference.md) for separate training, validation, checkpoint, full-CT and model-only measurements.
6. Use [results.csv](results.csv), [epochs.csv](epochs.csv), [validation-cases.csv](validation-cases.csv), [inference-cases.csv](inference-cases.csv), and [stage-invocations.csv](stage-invocations.csv) for spreadsheets. [status.json](status.json) and [records/](records/) retain numerical evidence and provenance.
7. Read [clinical-metrics.md](clinical-metrics.md) for P-Sen, T-Sen, specificity, AUC and DSC, including why some metrics cannot be estimated on Task07.

```text
report-directory/        this report's folder
  README.md              reading guide and interpretation
  comparison.md          all models, status, validation, ranking gates
  learning-curves.md     recorded epochs; no interpolated values
  optimization.md        throughput changes and measured evidence
  training-cost.md       retained epoch phases and allocation cost
  inference.md           native CT and model-only speed/memory
  clinical-metrics.md    detection/DSC metrics and unavailable reasons
  models/<run>.md        per-model recipe, resources and evaluation
  records/<run>.json     full numerical model record and lineage
  epochs.csv             training/validation/checkpoint timings
  validation-cases.csv   per-epoch native Dice by case ordinal
  inference-cases.csv    native prediction phase timings
  stage-invocations.csv  completed/failed/cancelled stage costs
  results.csv            one aggregate row per run
  status.json            aggregate evidence and comparison gates
```

Frozen split counts: 197 training, 42 validation, 42 held-out test. Grouping status: `dataset_case_unverified`. Split SHA256: `7f4308aaea49910334b6aa900a998b4ff94623d25cc630c9dd2704d7513b25f9`.

The scheduler runs one job on each available GPU and advances through the explicit queue. A completed run means its training, native validation prediction and evaluation have finished. Queued, failed and incomplete runs remain visible. No pretrained weights are allowed; resuming an existing scratch-origin run is allowed.

All scores are on a 0-1 scale; — means unavailable, never zero. This is an
exploratory seed-0 screening study, with no claim of a clinical or publishable
winner. Dataset case grouping has not independently established patient identity.
Task07 mass masks are segmentation targets; they do not establish PDAC diagnosis.
The held-out test partition and 139 unannotated Task07 scans are not scored here.

In-training Dice is a mean over complete native validation examinations, counting
both-empty mass masks as 1. Final evaluation instead averages patient means over
reference-positive cases and excludes both-empty masks. These two columns answer
different questions and must not be substituted. A completed screening rank uses
the final evaluator's mass Dice only, after every planned run in that group has
finished on matching references, native evaluation protocol, source, split,
seed, optimizer-step budget, batch size, and checkpoint-selection rule.

Models use their declared objectives, including query and auxiliary losses.
Therefore the comparison tests architecture and objective together. 2.5D and 3D
inputs also have different spatial context. Equal optimizer steps are not equal
GPU-hours, voxels seen, or an architecture-specific tuning budget. Loss magnitudes
are useful within a run; they are not an accuracy ranking across objectives.

[Medical model guide](../../../../guides/medical-models.md) · [Results by dataset](../../../README.md)

## All models at a glance

| Model | Status | Steps / budget | Native mass Dice | Native pancreas Dice | Score scope | Cases |
| --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | queued | 0/10000 | — | — | in-training step — | 0/42 |
| [dynunet-deep10k-seed0](models/dynunet-deep10k-seed0.md) | queued | 0/10000 | — | — | in-training step — | 0/42 |
| [dynunet-focal05-seed0](models/dynunet-focal05-seed0.md) | queued | 0/10000 | — | — | in-training step — | 0/42 |
| [dynunet-focal10-seed0](models/dynunet-focal10-seed0.md) | queued | 0/10000 | — | — | in-training step — | 0/42 |
| [dynunet-window-seed0](models/dynunet-window-seed0.md) | queued | 0/10000 | — | — | in-training step — | 0/42 |
| [dynunet-minmax-seed0](models/dynunet-minmax-seed0.md) | queued | 0/10000 | — | — | in-training step — | 0/42 |
| [dynunet-isotropic-seed0](models/dynunet-isotropic-seed0.md) | queued | 0/10000 | — | — | in-training step — | 0/42 |
| [swin_unetr-swin24-seed0](models/swin_unetr-swin24-seed0.md) | queued | 0/10000 | — | — | in-training step — | 0/42 |
| [swin_unetr-swin48-seed0](models/swin_unetr-swin48-seed0.md) | queued | 0/10000 | — | — | in-training step — | 0/42 |
