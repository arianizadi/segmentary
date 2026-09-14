# Task07 model comparison

Generated: 2026-09-14T03:53:32.241578+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

**19 completed, 9 running.**

Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.

| Model | Status | Stage | Committed steps / budget | Validated step | Interim mass Dice | Final mass Dice | Final pancreas Dice | Screening rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [nnunet_resenc_l](models/nnunet_resenc_l-seed0.md) | running | train | 0/— | — | — | — | — | — |
| [umamba_enc](models/umamba_enc-seed0.md) | running | train | 9300/10000 | 9000 | 0.3499 | — | — | — |
| [segmamba](models/segmamba-seed0.md) | running | train | 9900/10000 | 9000 | 0.3212 | — | — | — |
| [umamba_bot](models/umamba_bot-seed0.md) | completed | — | 10000/10000 | 10000 | 0.3063 | 0.3216 | 0.7276 | — |
| [swin_unetr](models/swin_unetr-seed0.md) | completed | — | 10000/10000 | 10000 | 0.2270 | 0.2446 | 0.7045 | — |
| [unetr](models/unetr-seed0.md) | completed | — | 10000/10000 | 10000 | 0.0965 | 0.1116 | 0.4810 | — |
| [transunet_3d](models/transunet_3d-seed0.md) | completed | — | 10000/10000 | 10000 | 0.3041 | 0.3101 | 0.7354 | — |
| [medformer](models/medformer-seed0.md) | completed | — | 10000/10000 | 10000 | 0.3057 | 0.3272 | 0.7187 | — |
| [mednext_v1](models/mednext_v1-seed0.md) | completed | — | 10000/10000 | 10000 | 0.2606 | 0.2845 | 0.6888 | — |
| [dynunet](models/dynunet-seed0.md) | completed | — | 10000/10000 | 10000 | 0.2986 | 0.3298 | 0.7559 | — |
| [segresnet](models/segresnet-seed0.md) | completed | — | 10000/10000 | 10000 | 0.2991 | 0.3090 | 0.6610 | — |
| [unet_3d](models/unet_3d-seed0.md) | completed | — | 10000/10000 | 10000 | 0.1603 | 0.1833 | 0.6084 | — |
| [mask2former](models/mask2former-seed0.md) | completed | — | 10000/10000 | 10000 | 0.1490 | 0.1490 | 0.5844 | — |
| [maskformer](models/maskformer-seed0.md) | completed | — | 10000/10000 | 10000 | 0.0000 | 0.0005 | 0.0044 | — |
| [dpt](models/dpt-seed0.md) | completed | — | 10000/10000 | 10000 | 0.0199 | 0.0637 | 0.3644 | — |
| [swin_upernet](models/swin_upernet-seed0.md) | completed | — | 10000/10000 | 10000 | 0.1000 | 0.1391 | 0.5348 | — |
| [convnext_upernet](models/convnext_upernet-seed0.md) | completed | — | 10000/10000 | 10000 | 0.1200 | 0.1278 | 0.6405 | — |
| [segformer_b2](models/segformer_b2-seed0.md) | completed | — | 10000/10000 | 10000 | 0.1203 | 0.1218 | 0.3313 | — |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | running | predict | 10000/10000 | 10000 | 0.1279 | — | — | — |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | completed | — | 10000/10000 | 10000 | 0.2367 | 0.2601 | 0.6722 | — |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | completed | — | 10000/10000 | 10000 | 0.2420 | 0.2598 | 0.6229 | — |
| [fpn](models/fpn-seed0.md) | completed | — | 10000/10000 | 10000 | 0.2037 | 0.2399 | 0.6382 | — |
| [unet_2d](models/unet_2d-seed0.md) | completed | — | 10000/10000 | 10000 | 0.1816 | 0.2555 | 0.6631 | — |
| [segformer_b0](models/segformer_b0-seed0.md) | running | train | 7900/10000 | 7000 | 0.1126 | — | — | — |
| [pidnet](models/pidnet-seed0.md) | running | train | 4900/10000 | 4000 | 0.0214 | — | — | — |
| [ddrnet](models/ddrnet-seed0.md) | running | train | 1900/10000 | 1000 | 0.0000 | — | — | — |
| [bisenetv2](models/bisenetv2-seed0.md) | running | train | 2100/10000 | 2000 | 0.0000 | — | — | — |
| [lraspp](models/lraspp-seed0.md) | running | train | 900/10000 | 100 | 0.0000 | — | — | — |

- **nnunet_official_resenc_l_seed0** (1 planned runs): No ranking: Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **torch_common_scratch_seed0_10000_steps** (27 planned runs): No ranking: Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Cohort, protocol, source, split, seed, budget, batch, or selection differs; Mass Dice is unavailable.

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

