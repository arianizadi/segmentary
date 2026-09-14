# Native CT pipeline and standardized model inference

Generated: 2026-09-14T04:50:38.113018+00:00. Source: `86363b101aa3685782defdf524face6af43edb2d`.

## Native CT prediction

This measures heterogeneous full CT examinations. Case p50/p95 includes CPU work and, in overlapped runs, queue time. Scans/s is reported only from a complete successful cohort and a measured aggregate pipeline wall timer; overlapping case latencies are never summed to infer throughput. Failed and missing cases remain visible. Peak memory is Torch allocator memory, excluding the CUDA context.

| Model | Status | Cases | Failed | Pipeline wall s | Scans/s | Case p50 s | Case p95 s | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [umamba_enc](models/umamba_enc-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [segmamba](models/segmamba-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [umamba_bot](models/umamba_bot-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [swin_unetr](models/swin_unetr-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [unetr](models/unetr-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [transunet_3d](models/transunet_3d-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [medformer](models/medformer-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [mednext_v1](models/mednext_v1-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet](models/dynunet-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [segresnet](models/segresnet-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [unet_3d](models/unet_3d-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [mask2former](models/mask2former-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [maskformer](models/maskformer-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [dpt](models/dpt-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [swin_upernet](models/swin_upernet-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [convnext_upernet](models/convnext_upernet-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [segformer_b2](models/segformer_b2-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [fpn](models/fpn-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [unet_2d](models/unet_2d-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [segformer_b0](models/segformer_b0-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [pidnet](models/pidnet-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [ddrnet](models/ddrnet-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [bisenetv2](models/bisenetv2-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [lraspp](models/lraspp-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |

[Per-case numerical timings](inference-cases.csv) use stable validation case ordinals. They contain preprocessing, tiled inference, reconstruction and export when recorded. Tiled inference includes copies, softmax and CPU blending; it is not model-only forward latency.

## Standardized model-only forward

B1 synthetic inputs use each model's declared patch, context and precision. Warmup/sample counts and checkpoint/source/runtime fingerprints are retained in model records. The benchmark keeps inference-mode/autocast active across its warmup and measured calls, including a warm autocast weight cache; the clinical tile pipeline may enter autocast separately for each batch. Patches/s is the reciprocal of mean CUDA-event forward latency, not complete CT scans/s. Different 2D and 3D patch dimensions are separate workloads. Unmeasured models remain marked not_recorded until their benchmark executes.

| Model | Benchmark | Patch | Precision | Patches/s | p50 ms | p95 ms | Parameters | Weight MiB | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [umamba_enc](models/umamba_enc-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 22808675 | — | — |
| [segmamba](models/segmamba-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 67362723 | — | — |
| [umamba_bot](models/umamba_bot-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 22570531 | — | — |
| [swin_unetr](models/swin_unetr-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 15703029 | — | — |
| [unetr](models/unetr-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 92783859 | — | — |
| [transunet_3d](models/transunet_3d-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 102279168 | — | — |
| [medformer](models/medformer-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 39591555 | — | — |
| [mednext_v1](models/mednext_v1-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 5550947 | — | — |
| [dynunet](models/dynunet-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 16543683 | — | — |
| [segresnet](models/segresnet-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 18796035 | — | — |
| [unet_3d](models/unet_3d-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 7914603 | — | — |
| [mask2former](models/mask2former-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 47404926 | — | — |
| [maskformer](models/maskformer-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 41722302 | — | — |
| [dpt](models/dpt-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 110694086 | — | — |
| [swin_upernet](models/swin_upernet-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 59831744 | — | — |
| [convnext_upernet](models/convnext_upernet-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 60132518 | — | — |
| [segformer_b2](models/segformer_b2-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 27355203 | — | — |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 34919750 | — | — |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 26085171 | — | — |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 26684371 | — | — |
| [fpn](models/fpn-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 23161923 | — | — |
| [unet_2d](models/unet_2d-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 24442931 | — | — |
| [segformer_b0](models/segformer_b0-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 3718051 | — | — |
| [pidnet](models/pidnet-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 7717383 | — | — |
| [ddrnet](models/ddrnet-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 5732838 | — | — |
| [bisenetv2](models/bisenetv2-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 5194703 | — | — |
| [lraspp](models/lraspp-seed0.md) | not_recorded | [256, 256] | bf16 | — | — | — | 3218766 | — | — |

[Training cost](training-cost.md) · [Comparison](comparison.md)
