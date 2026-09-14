# Exploratory mass detection and segmentation metrics

Generated: 2026-09-14T23:37:24.377968+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

All metrics use a 0-1 scale. P-Sen flags a positive group when any retained mass component is predicted, even at the wrong location. T-Sen requires one-to-one localization matches to reference connected components. Spe is the true-negative fraction among fully annotated negative groups. AUC requires continuous image-only scores and both reference classes. DSC is segmentation overlap. These definitions are separate from clinical diagnosis.

| Model | Status | Complete cohort | P-Sen (group proxy) | T-Sen | Spe | AUC | Mass DSC | Pancreas DSC | Unavailable reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | completed | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [dynunet-long30k-seed0](models/dynunet-long30k-seed0.md) | completed | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [dynunet-fine10k-seed0](models/dynunet-fine10k-seed0.md) | completed | False | — | — | — | — | — | — | Diagnostic has not run yet. |

**Task07 limitations:** the current frozen 42-case validation cohort contains 42 mass-positive examinations and no fully annotated mass-negative examinations. Specificity and ROC AUC therefore cannot be estimated on this cohort. Unlabeled scans and organ-only labels are not verified negative controls. Dataset-case grouping is not established patient linkage, so P-Sen is a case/group proxy; connected components are not independently annotated lesion identities.

The diagnostic uses its recorded fixed component threshold, connectivity and IoU matching protocol. Per-model JSON records retain metric numerators/denominators, thresholds and source/checkpoint hashes. A failed or missing native reference/prediction withholds complete-cohort values. No PanTS leaderboard comparison is claimed without matching its cohort and official protocol. Class 2 means an annotated mass, not confirmed pancreatic cancer.

[All numerical records](records/) · [Primary native Dice comparison](comparison.md) · [Inference](inference.md)
