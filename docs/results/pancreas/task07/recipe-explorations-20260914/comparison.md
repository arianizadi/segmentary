# Task07 model comparison

**Controlled recipe explorations:** fresh scratch runs, 10,000 updates each, using the same development partition. The frozen campaign lists exact changes in loss, normalization, spacing, architecture or predicted-organ cropping. Compare each candidate with its control using full-native per-patient metrics. These are one-seed validation experiments, not equal-compute architecture rankings or independent test results. Cascade misses outside the crop still count.

Generated: 2026-09-15T04:09:16.956217+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

**8 completed, 1 running.**

Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.

| Model | Status | Stage | Committed steps / budget | Validated step | Interim cases | Interim mass Dice | Interim pancreas Dice | Final mass Dice | Final pancreas Dice | Final cases | Screening rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2986 | 0.7607 | 0.3298 | 0.7559 | 42/42 | — |
| [dynunet-deep10k-seed0](models/dynunet-deep10k-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3049 | 0.7471 | 0.3069 | 0.7407 | 42/42 | — |
| [dynunet-focal05-seed0](models/dynunet-focal05-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2942 | 0.7438 | 0.3171 | 0.7228 | 42/42 | — |
| [dynunet-focal10-seed0](models/dynunet-focal10-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3094 | 0.7555 | 0.3238 | 0.7185 | 42/42 | — |
| [dynunet-window-seed0](models/dynunet-window-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2886 | 0.7341 | 0.2953 | 0.7110 | 42/42 | — |
| [dynunet-minmax-seed0](models/dynunet-minmax-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2978 | 0.7492 | 0.3067 | 0.7045 | 42/42 | — |
| [dynunet-isotropic-seed0](models/dynunet-isotropic-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3093 | 0.7606 | 0.3483 | 0.7569 | 42/42 | — |
| [swin_unetr-swin24-seed0](models/swin_unetr-swin24-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2270 | 0.7166 | 0.2446 | 0.7045 | 42/42 | — |
| [swin_unetr-swin48-seed0](models/swin_unetr-swin48-seed0.md) | running | train | 9000/10000 | 9000 | 42/42 | 0.2538 | 0.7247 | — | — | 0/42 | — |

- **dynunet_deep_supervision_seed0_control_10000_steps** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group.
- **dynunet_deep_supervision_seed0_auxiliary_10000_steps** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group.
- **recipe_focal05** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group.
- **recipe_focal10** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group.
- **recipe_hu_window** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group.
- **recipe_volume_minmax** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group.
- **recipe_isotropic** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group.
- **recipe_swin24** (1 planned runs): No ranking: Declared recipe follow-up experiments are reported as planned contrasts, not a ranked architecture group.
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

