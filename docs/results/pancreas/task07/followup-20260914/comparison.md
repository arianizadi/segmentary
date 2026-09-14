# Task07 model comparison

**Budget and resolution experiments:** all arms are scratch DynUNet runs with the same held-out validation split. The long arm changes both update budget and polynomial-decay horizon; the finer arm changes voxel spacing and patch dimensions to preserve physical context, with more voxels per update. These are planned recipe contrasts, not equal-compute architecture rankings.

Generated: 2026-09-14T23:41:37.068431+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

**3 completed.**

Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.

| Model | Status | Stage | Committed steps / budget | Validated step | Interim cases | Interim mass Dice | Interim pancreas Dice | Final mass Dice | Final pancreas Dice | Final cases | Screening rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2986 | 0.7607 | 0.3298 | 0.7559 | 42/42 | — |
| [dynunet-long30k-seed0](models/dynunet-long30k-seed0.md) | completed | — | 30000/30000 | 30000 | 42/42 | 0.3027 | 0.7745 | 0.3380 | 0.7262 | 42/42 | — |
| [dynunet-fine10k-seed0](models/dynunet-fine10k-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2546 | 0.7425 | 0.2820 | 0.7280 | 42/42 | — |

- **dynunet_followup_seed0_control_10000_steps_coarse** (1 planned runs): No ranking: Declared budget/resolution experiments are reported as planned contrasts, not a ranked architecture group.
- **dynunet_followup_seed0_budget_30000_steps_coarse** (1 planned runs): No ranking: Declared budget/resolution experiments are reported as planned contrasts, not a ranked architecture group.
- **dynunet_followup_seed0_resolution_10000_steps_fine** (1 planned runs): No ranking: Declared budget/resolution experiments are reported as planned contrasts, not a ranked architecture group.

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

