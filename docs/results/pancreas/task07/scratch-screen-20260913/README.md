# Pancreas Task07: training every scratch model

Generated: 2026-09-14T00:23:08.775704+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

**18 queued, 10 running.** GPU queue: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9.

1. Open [comparison.md](comparison.md) for model status and comparable validation results.
2. Open [learning-curves.md](learning-curves.md) to check whether each model is learning.
3. Follow a model link for its recipe, objective, timing, memory, coverage, and evaluation interval.
4. Read [optimization.md](optimization.md) for the throughput investigation and measurement limits.
5. Use [results.csv](results.csv) for a spreadsheet or [status.json](status.json) for aggregate machine records.

```text
scratch-screen-20260913/
  README.md              reading guide and interpretation
  comparison.md          all models, status, validation, ranking gates
  learning-curves.md     recorded epochs; no interpolated values
  optimization.md        throughput changes and measured evidence
  models/<run>.md        per-model recipe, resources and evaluation
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
