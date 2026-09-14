# Exploratory mass detection and segmentation metrics

Generated: 2026-09-14T17:28:27.928232+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

All metrics use a 0-1 scale. P-Sen flags a positive group when any retained mass component is predicted, even at the wrong location. T-Sen requires one-to-one localization matches to reference connected components. Spe is the true-negative fraction among fully annotated negative groups. AUC requires continuous image-only scores and both reference classes. DSC is segmentation overlap. These definitions are separate from clinical diagnosis.

| Model | Status | Complete cohort | P-Sen (group proxy) | T-Sen | Spe | AUC | Mass DSC | Pancreas DSC | Unavailable reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control-seed0](models/dynunet-control-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [dynunet-mass50-seed0](models/dynunet-mass50-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [dynunet-class111-seed0](models/dynunet-class111-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [dynunet-class115-seed0](models/dynunet-class115-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [dynunet-rotation-seed0](models/dynunet-rotation-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [dynunet-intensity-seed0](models/dynunet-intensity-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |

**Task07 limitations:** the current frozen 42-case validation cohort contains 42 mass-positive examinations and no fully annotated mass-negative examinations. Specificity and ROC AUC therefore cannot be estimated on this cohort. Unlabeled scans and organ-only labels are not verified negative controls. Dataset-case grouping is not established patient linkage, so P-Sen is a case/group proxy; connected components are not independently annotated lesion identities.

The diagnostic uses its recorded fixed component threshold, connectivity and IoU matching protocol. Per-model JSON records retain metric numerators/denominators, thresholds and source/checkpoint hashes. A failed or missing native reference/prediction withholds complete-cohort values. No PanTS leaderboard comparison is claimed without matching its cohort and official protocol. Class 2 means an annotated mass, not confirmed pancreatic cancer.

[All numerical records](records/) · [Primary native Dice comparison](comparison.md) · [Inference](inference.md)
