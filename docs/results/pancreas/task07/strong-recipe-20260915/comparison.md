# Task07 model comparison

Generated: 2026-09-15T18:11:34.573336+00:00. Source: `63a108f8b7a65a98b11ccae0e8883c54955b2099`.

**3 running.**

Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.

| Model | Status | Stage | Committed steps / budget | Validated step | Interim cases | Interim mass Dice | Interim pancreas Dice | Final mass Dice | Final pancreas Dice | Final cases | Screening rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [nnunet_resenc_l](models/nnunet_resenc_l-seed0.md) | running | train | 1750/250000 | — | 0/42 | — | — | — | — | 0/42 | — |
| [nnunet_planned_plainconv](models/nnunet_planned_plainconv-seed0.md) | running | train | 2750/250000 | — | 0/42 | — | — | — | — | 0/42 | — |
| [nnunet_planned_dynunet](models/nnunet_planned_dynunet-seed0.md) | running | train | 2750/250000 | — | 0/42 | — | — | — | — | 0/42 | — |

- **nnunet_frozen_plan_scratch_seed0_250000_steps** (3 planned runs): No ranking: Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.

All scores are on a 0-1 scale; — means unavailable, never zero. This is an
exploratory single-seed architecture comparison, with no claim of a clinical or publishable
winner. Dataset case grouping has not independently established patient identity.
Task07 mass masks are segmentation targets; they do not establish PDAC diagnosis.
The held-out test partition and 139 unannotated Task07 scans are not scored here.

Training logs contain official nnU-Net patch loss and pseudo-Dice, not native full-volume Dice. Native scores remain unavailable until evaluation of all 42 validation cases. Every arm selects its checkpoint with the same official EMA foreground patch-Dice rule; selected-best native mass Dice is the primary comparison. Pancreas Dice measures the pancreas union.

All three arms share native 3D inputs, preprocessing, augmentation, sampling, SGD schedule, CE plus per-sample foreground Dice with deep supervision, patch geometry, batch size and 250,000-update budget. Architectures and their default scratch initializers differ. Equal sampled patches do not imply equal parameter counts, FLOPs or GPU-hours. This is an exploratory single-seed comparison; see [launch notes](launch-notes.md) for the fixed protocol and limitations.
