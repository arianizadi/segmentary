# Pancreas Task07: model comparison

Generated: 2026-09-15T18:11:34.573336+00:00. Source: `63a108f8b7a65a98b11ccae0e8883c54955b2099`.

**3 running.** GPU queue: 1, 2, 3.

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
exploratory single-seed architecture comparison, with no claim of a clinical or publishable
winner. Dataset case grouping has not independently established patient identity.
Task07 mass masks are segmentation targets; they do not establish PDAC diagnosis.
The held-out test partition and 139 unannotated Task07 scans are not scored here.

Training logs contain official nnU-Net patch loss and pseudo-Dice. These are not native full-volume Dice, so the native score columns remain unavailable until the full 42-case evaluation finishes. Every arm uses the same official EMA foreground patch-Dice checkpoint-selection rule.

All three arms share the complete nnU-Net preprocessing, augmentation, SGD schedule, deep-supervised CE plus per-sample foreground Dice, patch geometry, batch size and 250,000-update budget. The network topology and scratch initializer differ. Equal updates and sampled patches do not equal parameter count, FLOPs or GPU-hours. The selected-best native mass Dice is the primary comparison; this is not an official MSD test result or evidence of SOTA.

[Medical model guide](../../../../guides/medical-models.md) · [Results by dataset](../../../README.md)

## All models at a glance

| Model | Status | Steps / budget | Native mass Dice | Native pancreas Dice | Score scope | Cases |
| --- | --- | --- | --- | --- | --- | --- |
| [nnunet_resenc_l](models/nnunet_resenc_l-seed0.md) | running | 1750/250000 | — | — | in-training step — | 0/42 |
| [nnunet_planned_plainconv](models/nnunet_planned_plainconv-seed0.md) | running | 2750/250000 | — | — | in-training step — | 0/42 |
| [nnunet_planned_dynunet](models/nnunet_planned_dynunet-seed0.md) | running | 2750/250000 | — | — | in-training step — | 0/42 |
