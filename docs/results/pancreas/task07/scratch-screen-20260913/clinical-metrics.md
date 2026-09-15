# Exploratory mass detection and segmentation metrics

Generated: 2026-09-15T16:02:08.483429+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

All metrics use a 0-1 scale. P-Sen flags a positive group when any retained mass component is predicted, even at the wrong location. T-Sen requires one-to-one localization matches to reference connected components. Spe is the true-negative fraction among fully annotated negative groups. AUC requires continuous image-only scores and both reference classes. DSC is segmentation overlap. These definitions are separate from clinical diagnosis.

| Model | Status | Complete cohort | P-Sen (group proxy) | T-Sen | Spe | AUC | Mass DSC | Pancreas DSC | Unavailable reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [nnunet_resenc_l](models/nnunet_resenc_l-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [umamba_enc](models/umamba_enc-seed0.md) | completed | True | 0.857 | 0.595 | — | — | 0.357 | 0.754 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [segmamba](models/segmamba-seed0.md) | completed | True | 0.881 | 0.524 | — | — | 0.321 | 0.736 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [umamba_bot](models/umamba_bot-seed0.md) | completed | True | 0.857 | 0.500 | — | — | 0.322 | 0.728 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [swin_unetr](models/swin_unetr-seed0.md) | completed | True | 0.905 | 0.476 | — | — | 0.245 | 0.705 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [unetr](models/unetr-seed0.md) | completed | True | 0.905 | 0.262 | — | — | 0.112 | 0.481 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [transunet_3d](models/transunet_3d-seed0.md) | completed | True | 0.857 | 0.524 | — | — | 0.310 | 0.735 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [medformer](models/medformer-seed0.md) | completed | True | 0.833 | 0.571 | — | — | 0.327 | 0.719 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [mednext_v1](models/mednext_v1-seed0.md) | completed | True | 0.881 | 0.500 | — | — | 0.284 | 0.689 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [dynunet](models/dynunet-seed0.md) | completed | True | 0.929 | 0.595 | — | — | 0.330 | 0.756 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [segresnet](models/segresnet-seed0.md) | completed | True | 0.929 | 0.619 | — | — | 0.309 | 0.661 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [unet_3d](models/unet_3d-seed0.md) | completed | True | 0.762 | 0.405 | — | — | 0.183 | 0.608 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [mask2former](models/mask2former-seed0.md) | completed | True | 0.905 | 0.333 | — | — | 0.149 | 0.584 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [maskformer](models/maskformer-seed0.md) | completed | True | 1.000 | 0.000 | — | — | 0.000 | 0.004 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [dpt](models/dpt-seed0.md) | completed | True | 0.786 | 0.167 | — | — | 0.064 | 0.364 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [swin_upernet](models/swin_upernet-seed0.md) | completed | True | 0.952 | 0.357 | — | — | 0.139 | 0.535 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [convnext_upernet](models/convnext_upernet-seed0.md) | completed | True | 0.786 | 0.286 | — | — | 0.128 | 0.641 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [segformer_b2](models/segformer_b2-seed0.md) | completed | True | 0.952 | 0.429 | — | — | 0.122 | 0.331 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | completed | True | 0.833 | 0.405 | — | — | 0.170 | 0.662 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | completed | True | 1.000 | 0.571 | — | — | 0.260 | 0.672 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | completed | True | 0.929 | 0.619 | — | — | 0.260 | 0.623 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [fpn](models/fpn-seed0.md) | completed | True | 1.000 | 0.619 | — | — | 0.240 | 0.638 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [unet_2d](models/unet_2d-seed0.md) | completed | True | 0.976 | 0.476 | — | — | 0.255 | 0.663 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [segformer_b0](models/segformer_b0-seed0.md) | completed | True | 0.952 | 0.333 | — | — | 0.116 | 0.441 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [pidnet](models/pidnet-seed0.md) | completed | True | 0.500 | 0.071 | — | — | 0.032 | 0.576 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [ddrnet](models/ddrnet-seed0.md) | completed | True | 0.833 | 0.167 | — | — | 0.081 | 0.527 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [bisenetv2](models/bisenetv2-seed0.md) | completed | True | 0.929 | 0.310 | — | — | 0.146 | 0.566 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |
| [lraspp](models/lraspp-seed0.md) | completed | True | 0.929 | 0.381 | — | — | 0.146 | 0.519 | No fully annotated reference-negative groups.; ROC AUC requires positive and negative reference groups. |

**Task07 limitations:** the current frozen 42-case validation cohort contains 42 mass-positive examinations and no fully annotated mass-negative examinations. Specificity and ROC AUC therefore cannot be estimated on this cohort. Unlabeled scans and organ-only labels are not verified negative controls. Dataset-case grouping is not established patient linkage, so P-Sen is a case/group proxy; connected components are not independently annotated lesion identities.

The diagnostic uses its recorded fixed component threshold, connectivity and IoU matching protocol. Per-model JSON records retain metric numerators/denominators, thresholds and source/checkpoint hashes. A failed or missing native reference/prediction withholds complete-cohort values. No PanTS leaderboard comparison is claimed without matching its cohort and official protocol. Class 2 means an annotated mass, not confirmed pancreatic cancer.

[All numerical records](records/) · [Primary native Dice comparison](comparison.md) · [Inference](inference.md)
