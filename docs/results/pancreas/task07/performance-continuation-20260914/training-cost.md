# Recorded training cost

Generated: 2026-09-14T04:57:14.189490+00:00. Source: `86363b101aa3685782defdf524face6af43edb2d`.

All models remain visible. Seconds are sums of retained committed epoch measurements; coverage shows recorded timings / retained epochs in that segment. Missing legacy checkpoint timings are unknown, never zero. Parent segments describe the same training lineage, not additional seeds. Current stage GPU-hours include failed/cancelled invocations and startup; they are allocation time, not GPU utilization.

| Model | Status | History segment | Training seconds (coverage) | Validation seconds (coverage) | Checkpoint seconds (coverage) | Current finished-stage GPU-h |
| --- | --- | --- | --- | --- | --- | --- |
| [umamba_enc](models/umamba_enc-seed0.md) | running | parent/current | 14558.491 (100/100 epochs) | 3077.751 (100/100 epochs) | — (0/100 epochs) | — |
| [segmamba](models/segmamba-seed0.md) | running | parent/current | 13410.504 (100/100 epochs) | 3264.442 (100/100 epochs) | — (0/100 epochs) | — |
| [umamba_bot](models/umamba_bot-seed0.md) | running | parent/current | 5611.393 (100/100 epochs) | 2420.435 (100/100 epochs) | — (0/100 epochs) | — |
| [swin_unetr](models/swin_unetr-seed0.md) | running | parent/current | 6108.624 (100/100 epochs) | 2481.646 (100/100 epochs) | — (0/100 epochs) | — |
| [unetr](models/unetr-seed0.md) | running | parent/current | 1790.747 (100/100 epochs) | 2057.885 (100/100 epochs) | — (0/100 epochs) | — |
| [transunet_3d](models/transunet_3d-seed0.md) | running | parent/current | 2684.921 (100/100 epochs) | 2121.689 (100/100 epochs) | — (0/100 epochs) | — |
| [medformer](models/medformer-seed0.md) | running | parent/current | 7848.535 (100/100 epochs) | 2579.506 (100/100 epochs) | — (0/100 epochs) | — |
| [mednext_v1](models/mednext_v1-seed0.md) | running | parent/current | 6693.810 (100/100 epochs) | 2585.652 (100/100 epochs) | — (0/100 epochs) | — |
| [dynunet](models/dynunet-seed0.md) | running | parent/current | 2280.595 (100/100 epochs) | 2077.312 (100/100 epochs) | — (0/100 epochs) | — |
| [segresnet](models/segresnet-seed0.md) | queued | parent/current | 3667.421 (100/100 epochs) | 2450.831 (100/100 epochs) | — (0/100 epochs) | — |
| [unet_3d](models/unet_3d-seed0.md) | queued | parent/current | 589.034 (100/100 epochs) | 1961.772 (100/100 epochs) | — (0/100 epochs) | — |
| [mask2former](models/mask2former-seed0.md) | queued | parent/current | 2170.475 (100/100 epochs) | 3745.172 (100/100 epochs) | — (0/100 epochs) | — |
| [maskformer](models/maskformer-seed0.md) | queued | parent/current | 1306.719 (100/100 epochs) | 3043.039 (100/100 epochs) | — (0/100 epochs) | — |
| [dpt](models/dpt-seed0.md) | queued | parent/current | 650.647 (100/100 epochs) | 2711.209 (100/100 epochs) | — (0/100 epochs) | — |
| [swin_upernet](models/swin_upernet-seed0.md) | queued | parent/current | 732.418 (100/100 epochs) | 2841.904 (100/100 epochs) | — (0/100 epochs) | — |
| [convnext_upernet](models/convnext_upernet-seed0.md) | queued | parent/current | 567.285 (100/100 epochs) | 3100.860 (100/100 epochs) | — (0/100 epochs) | — |
| [segformer_b2](models/segformer_b2-seed0.md) | queued | parent/current | 684.528 (100/100 epochs) | 2751.496 (100/100 epochs) | — (0/100 epochs) | — |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | queued | parent/current | 994.145 (100/100 epochs) | 3787.693 (100/100 epochs) | — (0/100 epochs) | — |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | queued | parent/current | 385.313 (100/100 epochs) | 2595.286 (100/100 epochs) | — (0/100 epochs) | — |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | queued | parent/current | 327.168 (100/100 epochs) | 2637.679 (100/100 epochs) | — (0/100 epochs) | — |
| [fpn](models/fpn-seed0.md) | queued | parent/current | 263.531 (100/100 epochs) | 1909.189 (100/100 epochs) | — (0/100 epochs) | — |
| [unet_2d](models/unet_2d-seed0.md) | queued | parent/current | 267.669 (100/100 epochs) | 2241.869 (100/100 epochs) | — (0/100 epochs) | — |
| [segformer_b0](models/segformer_b0-seed0.md) | queued | parent/current | 359.930 (100/100 epochs) | 2749.426 (100/100 epochs) | — (0/100 epochs) | — |
| [pidnet](models/pidnet-seed0.md) | queued | parent/current | 366.843 (100/100 epochs) | 2579.273 (100/100 epochs) | — (0/100 epochs) | — |
| [ddrnet](models/ddrnet-seed0.md) | queued | parent/current | 288.634 (100/100 epochs) | 2273.764 (100/100 epochs) | — (0/100 epochs) | — |
| [bisenetv2](models/bisenetv2-seed0.md) | queued | parent/current | 306.101 (100/100 epochs) | 1956.263 (100/100 epochs) | — (0/100 epochs) | — |
| [lraspp](models/lraspp-seed0.md) | queued | parent/current | 284.348 (100/100 epochs) | 2324.526 (100/100 epochs) | — (0/100 epochs) | — |

[Epoch numerical records](epochs.csv) · [Stage invocations, including failures](stage-invocations.csv) · [Comparison](comparison.md)

The official nnU-Net log retains patch-loss/pseudo-Dice and completed epoch timing separately in each JSON record. An official epoch combines its own training and patch validation work; it cannot be split into the Torch harness timing categories without recorded evidence.
