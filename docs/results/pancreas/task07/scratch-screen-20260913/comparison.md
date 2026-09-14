# Task07 model comparison

Generated: 2026-09-14T22:59:02.286662+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

**27 completed, 1 running.**

Interim values are shown in campaign order, not sorted by apparent accuracy. Different validated step counts cannot establish a winner.

| Model | Status | Stage | Committed steps / budget | Validated step | Interim cases | Interim mass Dice | Interim pancreas Dice | Final mass Dice | Final pancreas Dice | Final cases | Screening rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [nnunet_resenc_l](models/nnunet_resenc_l-seed0.md) | running | train | 130250/250000 | — | 0/42 | — | — | — | — | 0/42 | — |
| [umamba_enc](models/umamba_enc-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3451 | 0.7695 | 0.3571 | 0.7541 | 42/42 | 1 |
| [segmamba](models/segmamba-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3118 | 0.7423 | 0.3212 | 0.7355 | 42/42 | 5 |
| [umamba_bot](models/umamba_bot-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3063 | 0.7621 | 0.3216 | 0.7276 | 42/42 | 4 |
| [swin_unetr](models/swin_unetr-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2270 | 0.7166 | 0.2446 | 0.7045 | 42/42 | 12 |
| [unetr](models/unetr-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.0965 | 0.4813 | 0.1116 | 0.4810 | 42/42 | 23 |
| [transunet_3d](models/transunet_3d-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3041 | 0.7554 | 0.3101 | 0.7354 | 42/42 | 6 |
| [medformer](models/medformer-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.3057 | 0.7331 | 0.3272 | 0.7187 | 42/42 | 3 |
| [mednext_v1](models/mednext_v1-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2606 | 0.7246 | 0.2845 | 0.6888 | 42/42 | 8 |
| [dynunet](models/dynunet-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2986 | 0.7607 | 0.3298 | 0.7559 | 42/42 | 2 |
| [segresnet](models/segresnet-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2991 | 0.7063 | 0.3090 | 0.6610 | 42/42 | 7 |
| [unet_3d](models/unet_3d-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1603 | 0.6428 | 0.1833 | 0.6084 | 42/42 | 14 |
| [mask2former](models/mask2former-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1490 | 0.5844 | 0.1490 | 0.5844 | 42/42 | 16 |
| [maskformer](models/maskformer-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.0000 | 0.0087 | 0.0005 | 0.0044 | 42/42 | 27 |
| [dpt](models/dpt-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.0199 | 0.4083 | 0.0637 | 0.3644 | 42/42 | 25 |
| [swin_upernet](models/swin_upernet-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1000 | 0.6046 | 0.1391 | 0.5348 | 42/42 | 19 |
| [convnext_upernet](models/convnext_upernet-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1200 | 0.6297 | 0.1278 | 0.6405 | 42/42 | 20 |
| [segformer_b2](models/segformer_b2-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1203 | 0.4105 | 0.1218 | 0.3313 | 42/42 | 21 |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1279 | 0.6756 | 0.1701 | 0.6618 | 42/42 | 15 |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2367 | 0.6919 | 0.2601 | 0.6722 | 42/42 | 9 |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2420 | 0.6483 | 0.2598 | 0.6229 | 42/42 | 10 |
| [fpn](models/fpn-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.2037 | 0.6731 | 0.2399 | 0.6382 | 42/42 | 13 |
| [unet_2d](models/unet_2d-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1816 | 0.6723 | 0.2555 | 0.6631 | 42/42 | 11 |
| [segformer_b0](models/segformer_b0-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1117 | 0.4684 | 0.1156 | 0.4408 | 42/42 | 22 |
| [pidnet](models/pidnet-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.0202 | 0.5500 | 0.0324 | 0.5757 | 42/42 | 26 |
| [ddrnet](models/ddrnet-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.0432 | 0.5746 | 0.0806 | 0.5269 | 42/42 | 24 |
| [bisenetv2](models/bisenetv2-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1039 | 0.5888 | 0.1464 | 0.5664 | 42/42 | 17 |
| [lraspp](models/lraspp-seed0.md) | completed | — | 10000/10000 | 10000 | 42/42 | 0.1044 | 0.5543 | 0.1463 | 0.5191 | 42/42 | 18 |

- **nnunet_official_resenc_l_seed0** (1 planned runs): No ranking: Not all planned runs have completed; Native validation coverage is incomplete; Complete scratch training evidence is unavailable; Required source, split or checkpoint provenance is unavailable; Evaluation is not bound to the declared best validation checkpoint; Declared optimization budget has not been completed; Mass Dice is unavailable.
- **torch_common_scratch_seed0_10000_steps** (27 planned runs): Completed exploratory ranking available; seed replication and external evaluation remain outstanding.

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

