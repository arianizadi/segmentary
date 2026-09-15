# Task07 model comparison

Generated: 2026-09-15T17:54:41.384912+00:00. Source: `f9051656be4a9800d415b8e99ba782b23632a968`.

**4 completed.**

Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.

| Model | Status | Stage | Committed steps / budget | Validated step | Interim cases | Interim mass Dice | Interim pancreas Dice | Final mass Dice | Final pancreas Dice | Final cases | Screening rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-batch-seed0](models/dynunet-batch-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2986 | 0.7607 | 0.3298 | 0.7559 | 42/42 | — |
| [dynunet-per-sample-seed0](models/dynunet-per-sample-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3267 | 0.7768 | 0.3267 | 0.7768 | 42/42 | — |
| [dynunet-batch-seed1](models/dynunet-batch-seed1.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2859 | 0.7356 | 0.3046 | 0.7324 | 42/42 | — |
| [dynunet-per-sample-seed1](models/dynunet-per-sample-seed1.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3610 | 0.7726 | 0.3610 | 0.7726 | 42/42 | — |

- **dice_reduction_by_patch_two_seeds** (4 planned runs): No ranking: Cohort, protocol, source, split, seed, budget, batch, or selection differs.

All scores are on a 0-1 scale; — means unavailable, never zero. This is an
exploratory two-seed Dice-reduction study, with no claim of a clinical or publishable
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

