# Exploratory mass detection and segmentation metrics

Generated: 2026-09-15T04:44:00.800219+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

All metrics use a 0-1 scale. P-Sen flags a positive group when any retained mass component is predicted, even at the wrong location. T-Sen requires one-to-one localization matches to reference connected components. Spe is the true-negative fraction among fully annotated negative groups. AUC requires continuous image-only scores and both reference classes. DSC is segmentation overlap. These definitions are separate from clinical diagnosis.

| Model | Status | Complete cohort | P-Sen (group proxy) | T-Sen | Spe | AUC | Mass DSC | Pancreas DSC | Unavailable reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | completed | True | 0.929 | 0.595 | — | — | 0.330 | 0.756 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [dynunet-deep10k-seed0](models/dynunet-deep10k-seed0.md) | completed | True | 0.786 | 0.476 | — | — | 0.307 | 0.741 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [dynunet-focal05-seed0](models/dynunet-focal05-seed0.md) | completed | True | 0.976 | 0.500 | — | — | 0.317 | 0.723 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [dynunet-focal10-seed0](models/dynunet-focal10-seed0.md) | completed | True | 0.952 | 0.571 | — | — | 0.324 | 0.718 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [dynunet-window-seed0](models/dynunet-window-seed0.md) | completed | True | 0.976 | 0.548 | — | — | 0.295 | 0.711 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [dynunet-minmax-seed0](models/dynunet-minmax-seed0.md) | completed | True | 0.810 | 0.500 | — | — | 0.307 | 0.705 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [dynunet-isotropic-seed0](models/dynunet-isotropic-seed0.md) | completed | True | 0.929 | 0.619 | — | — | 0.348 | 0.757 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [swin_unetr-swin24-seed0](models/swin_unetr-swin24-seed0.md) | completed | True | 0.905 | 0.476 | — | — | 0.245 | 0.705 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [swin_unetr-swin48-seed0](models/swin_unetr-swin48-seed0.md) | completed | True | 0.929 | 0.524 | — | — | 0.296 | 0.737 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |

**Task07 limitations:** the current frozen 42-case validation cohort contains 42 mass-positive examinations and no fully annotated mass-negative examinations. Specificity and ROC AUC therefore cannot be estimated on this cohort. Unlabeled scans and organ-only labels are not verified negative controls. Dataset-case grouping is not established patient linkage, so P-Sen is a case/group proxy; connected components are not independently annotated lesion identities.

The diagnostic uses its recorded fixed component threshold, connectivity and IoU matching protocol. Per-model JSON records retain metric numerators/denominators, thresholds and source/checkpoint hashes. A failed or missing native reference/prediction withholds complete-cohort values. No PanTS leaderboard comparison is claimed without matching its cohort and official protocol. Class 2 means an annotated mass, not confirmed pancreatic cancer.

[All numerical records](records/) · [Primary native Dice comparison](comparison.md) · [Inference](inference.md)
