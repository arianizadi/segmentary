# Task07 model comparison

**Recipe experiment:** the named arms use the same DynUNet architecture, loss, split, inference protocol and fixed 10,000-update budget. Run IDs identify separate scratch initializations under declared ingredient changes; they are not different architectures. Rankings stay within each seed and require all planned arms to finish. The class111/class115 pair changes class weights; both also change background-center semantics relative to the uniform-volume control. Historical results used a different source snapshot and are not included as same-source replicates.

Generated: 2026-09-14T17:58:31.426550+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

**6 running.**

Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.

| Model | Status | Stage | Committed steps / budget | Validated step | Interim cases | Interim mass Dice | Interim pancreas Dice | Final mass Dice | Final pancreas Dice | Final cases | Screening rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control-seed0](models/dynunet-control-seed0.md) | running | train | 5600/10000 | 5000 | 42/42 | 0.2729 | 0.7198 | — | — | 0/42 | — |
| [dynunet-mass50-seed0](models/dynunet-mass50-seed0.md) | running | train | 5600/10000 | 5000 | 42/42 | 0.2736 | 0.7167 | — | — | 0/42 | — |
| [dynunet-class111-seed0](models/dynunet-class111-seed0.md) | running | train | 5600/10000 | 5000 | 42/42 | 0.2786 | 0.7275 | — | — | 0/42 | — |
| [dynunet-class115-seed0](models/dynunet-class115-seed0.md) | running | train | 5600/10000 | 5000 | 42/42 | 0.2714 | 0.6682 | — | — | 0/42 | — |
| [dynunet-rotation-seed0](models/dynunet-rotation-seed0.md) | running | train | 5600/10000 | 5000 | 42/42 | 0.2783 | 0.6704 | — | — | 0/42 | — |
| [dynunet-intensity-seed0](models/dynunet-intensity-seed0.md) | running | train | 5500/10000 | 5000 | 42/42 | 0.2607 | 0.7193 | — | — | 0/42 | — |

- **dynunet_recipe_ablation_seed0_10000_steps** (6 planned runs): No ranking: Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.

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

