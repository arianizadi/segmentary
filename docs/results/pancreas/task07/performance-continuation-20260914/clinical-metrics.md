# Exploratory mass detection and segmentation metrics

Generated: 2026-09-14T04:57:14.189490+00:00. Source: `86363b101aa3685782defdf524face6af43edb2d`.

All metrics use a 0-1 scale. P-Sen flags a positive group when any retained mass component is predicted, even at the wrong location. T-Sen requires one-to-one localization matches to reference connected components. Spe is the true-negative fraction among fully annotated negative groups. AUC requires continuous image-only scores and both reference classes. DSC is segmentation overlap. These definitions are separate from clinical diagnosis.

| Model | Status | Complete cohort | P-Sen (group proxy) | T-Sen | Spe | AUC | Mass DSC | Pancreas DSC | Unavailable reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [umamba_enc](models/umamba_enc-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [segmamba](models/segmamba-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [umamba_bot](models/umamba_bot-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [swin_unetr](models/swin_unetr-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [unetr](models/unetr-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [transunet_3d](models/transunet_3d-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [medformer](models/medformer-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [mednext_v1](models/mednext_v1-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [dynunet](models/dynunet-seed0.md) | running | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [segresnet](models/segresnet-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [unet_3d](models/unet_3d-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [mask2former](models/mask2former-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [maskformer](models/maskformer-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [dpt](models/dpt-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [swin_upernet](models/swin_upernet-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [convnext_upernet](models/convnext_upernet-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [segformer_b2](models/segformer_b2-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [fpn](models/fpn-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [unet_2d](models/unet_2d-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [segformer_b0](models/segformer_b0-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [pidnet](models/pidnet-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [ddrnet](models/ddrnet-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [bisenetv2](models/bisenetv2-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |
| [lraspp](models/lraspp-seed0.md) | queued | False | — | — | — | — | — | — | Diagnostic has not run yet. |

**Task07 limitations:** the current frozen 42-case validation cohort contains 42 mass-positive examinations and no fully annotated mass-negative examinations. Specificity and ROC AUC therefore cannot be estimated on this cohort. Unlabeled scans and organ-only labels are not verified negative controls. Dataset-case grouping is not established patient linkage, so P-Sen is a case/group proxy; connected components are not independently annotated lesion identities.

The diagnostic uses its recorded fixed component threshold, connectivity and IoU matching protocol. Per-model JSON records retain metric numerators/denominators, thresholds and source/checkpoint hashes. A failed or missing native reference/prediction withholds complete-cohort values. No PanTS leaderboard comparison is claimed without matching its cohort and official protocol. Class 2 means an annotated mass, not confirmed pancreatic cancer.

[All numerical records](records/) · [Primary native Dice comparison](comparison.md) · [Inference](inference.md)
