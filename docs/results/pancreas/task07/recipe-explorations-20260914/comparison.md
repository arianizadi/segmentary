# Task07 model comparison

**Controlled recipe explorations:** fresh scratch runs, 10,000 updates each, using the same development partition. The frozen campaign lists exact changes in loss, normalization, spacing, architecture or predicted-organ cropping. Compare each candidate with its control using full-native per-patient metrics. These are one-seed validation experiments, not equal-compute architecture rankings or independent test results. Cascade misses outside the crop still count.

Generated: 2026-09-15T00:38:50.653104+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

**1 queued, 8 running.**

Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.

| Model | Status | Stage | Committed steps / budget | Validated step | Interim cases | Interim mass Dice | Interim pancreas Dice | Final mass Dice | Final pancreas Dice | Final cases | Screening rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | running | train | 5500/10000 | 5000 | 42/42 | 0.2729 | 0.7198 | — | — | 0/42 | — |
| [dynunet-deep10k-seed0](models/dynunet-deep10k-seed0.md) | running | train | 5400/10000 | 5000 | 42/42 | 0.2585 | 0.6899 | — | — | 0/42 | — |
| [dynunet-focal05-seed0](models/dynunet-focal05-seed0.md) | running | train | 5500/10000 | 5000 | 42/42 | 0.3013 | 0.7020 | — | — | 0/42 | — |
| [dynunet-focal10-seed0](models/dynunet-focal10-seed0.md) | running | train | 5500/10000 | 5000 | 42/42 | 0.3238 | 0.7185 | — | — | 0/42 | — |
| [dynunet-window-seed0](models/dynunet-window-seed0.md) | running | train | 5500/10000 | 5000 | 42/42 | 0.2953 | 0.7110 | — | — | 0/42 | — |
| [dynunet-minmax-seed0](models/dynunet-minmax-seed0.md) | running | train | 5400/10000 | 5000 | 42/42 | 0.2649 | 0.6717 | — | — | 0/42 | — |
| [dynunet-isotropic-seed0](models/dynunet-isotropic-seed0.md) | running | train | 3400/10000 | 3000 | 42/42 | 0.3296 | 0.6866 | — | — | 0/42 | — |
| [swin_unetr-swin24-seed0](models/swin_unetr-swin24-seed0.md) | running | train | 2300/10000 | 2000 | 42/42 | 0.1845 | 0.4764 | — | — | 0/42 | — |
| [swin_unetr-swin48-seed0](models/swin_unetr-swin48-seed0.md) | queued | — | 0/10000 | — | 0/42 | — | — | — | — | 0/42 | — |

- **dynunet_deep_supervision_seed0_control_10000_steps** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group; Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **dynunet_deep_supervision_seed0_auxiliary_10000_steps** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group; Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **recipe_focal05** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group; Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **recipe_focal10** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group; Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **recipe_hu_window** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group; Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **recipe_volume_minmax** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group; Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **recipe_isotropic** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group; Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **recipe_swin24** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group; Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **recipe_swin48** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group; Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.

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

