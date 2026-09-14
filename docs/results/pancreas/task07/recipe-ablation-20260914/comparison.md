# Task07 model comparison

**Recipe experiment:** the named arms use the same DynUNet architecture, loss, split, inference protocol and fixed 10,000-update budget. Run IDs identify separate scratch initializations under declared ingredient changes; they are not different architectures. Rankings stay within each seed and require all planned arms to finish. The class111/class115 pair changes class weights; both also change background-center semantics relative to the uniform-volume control. Historical results used a different source snapshot and are not included as same-source replicates.

Generated: 2026-09-14T18:33:30.436031+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

**6 completed.**

Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.

| Model | Status | Stage | Committed steps / budget | Validated step | Interim cases | Interim mass Dice | Interim pancreas Dice | Final mass Dice | Final pancreas Dice | Final cases | Screening rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control-seed0](models/dynunet-control-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2986 | 0.7607 | 0.3298 | 0.7559 | 42/42 | 1 |
| [dynunet-mass50-seed0](models/dynunet-mass50-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3000 | 0.7585 | 0.3030 | 0.7354 | 42/42 | 4 |
| [dynunet-class111-seed0](models/dynunet-class111-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3023 | 0.7573 | 0.3023 | 0.7573 | 42/42 | 5 |
| [dynunet-class115-seed0](models/dynunet-class115-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2847 | 0.7234 | 0.3071 | 0.7124 | 42/42 | 3 |
| [dynunet-rotation-seed0](models/dynunet-rotation-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3084 | 0.7598 | 0.3084 | 0.7598 | 42/42 | 2 |
| [dynunet-intensity-seed0](models/dynunet-intensity-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2754 | 0.7509 | 0.2973 | 0.7130 | 42/42 | 6 |

- **dynunet_recipe_ablation_seed0_10000_steps** (6 planned runs): Completed exploratory ranking available; seed replication and external evaluation remain outstanding.

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

