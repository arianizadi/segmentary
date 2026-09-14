# Native CT pipeline and standardized model inference

Generated: 2026-09-14T05:23:18.255196+00:00. Source: `86363b101aa3685782defdf524face6af43edb2d`.

## Native CT prediction

This measures heterogeneous full CT examinations. Case p50/p95 includes CPU work and, in overlapped runs, queue time. Scans/s is reported only from a complete successful cohort and a measured aggregate pipeline wall timer; overlapping case latencies are never summed to infer throughput. Failed and missing cases remain visible. Peak memory is Torch allocator memory, excluding the CUDA context.

| Model | Status | Cases | Failed | Pipeline wall s | Scans/s | Case p50 s | Case p95 s | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [umamba_enc](models/umamba_enc-seed0.md) | completed | 42/42 | 0 | 170.087 | 0.247 | 10.869 | 14.846 | 18.801 |
| [segmamba](models/segmamba-seed0.md) | completed | 42/42 | 0 | 141.515 | 0.297 | 9.402 | 11.725 | 8.047 |
| [umamba_bot](models/umamba_bot-seed0.md) | completed | 42/42 | 0 | 138.935 | 0.302 | 9.199 | 13.821 | 5.244 |
| [swin_unetr](models/swin_unetr-seed0.md) | completed | 42/42 | 0 | 131.448 | 0.320 | 9.332 | 11.750 | 10.033 |
| [unetr](models/unetr-seed0.md) | completed | 42/42 | 0 | 137.999 | 0.304 | 9.530 | 12.361 | 3.375 |
| [transunet_3d](models/transunet_3d-seed0.md) | completed | 42/42 | 0 | 127.739 | 0.329 | 8.681 | 11.093 | 4.830 |
| [medformer](models/medformer-seed0.md) | completed | 42/42 | 0 | 137.817 | 0.305 | 9.285 | 13.747 | 15.215 |
| [mednext_v1](models/mednext_v1-seed0.md) | completed | 42/42 | 0 | 129.661 | 0.324 | 8.913 | 10.778 | 8.391 |
| [dynunet](models/dynunet-seed0.md) | completed | 42/42 | 0 | 143.446 | 0.293 | 9.569 | 14.438 | 4.479 |
| [segresnet](models/segresnet-seed0.md) | completed | 42/42 | 0 | 136.982 | 0.307 | 9.721 | 12.383 | 4.820 |
| [unet_3d](models/unet_3d-seed0.md) | completed | 42/42 | 0 | 132.983 | 0.316 | 9.950 | 12.835 | 0.943 |
| [mask2former](models/mask2former-seed0.md) | completed | 42/42 | 0 | 195.358 | 0.215 | 11.918 | 15.859 | 0.764 |
| [maskformer](models/maskformer-seed0.md) | completed | 42/42 | 0 | 149.956 | 0.280 | 10.099 | 12.401 | 0.625 |
| [dpt](models/dpt-seed0.md) | completed | 42/42 | 0 | 128.789 | 0.326 | 8.990 | 10.663 | 0.738 |
| [swin_upernet](models/swin_upernet-seed0.md) | completed | 42/42 | 0 | 119.791 | 0.351 | 8.514 | 10.385 | 0.783 |
| [convnext_upernet](models/convnext_upernet-seed0.md) | completed | 42/42 | 0 | 118.863 | 0.353 | 8.292 | 11.495 | 0.777 |
| [segformer_b2](models/segformer_b2-seed0.md) | completed | 42/42 | 0 | 123.490 | 0.340 | 8.500 | 10.295 | 0.709 |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | completed | 42/42 | 0 | 143.076 | 0.294 | 9.398 | 12.619 | 0.324 |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | completed | 42/42 | 0 | 128.023 | 0.328 | 9.189 | 11.893 | 0.469 |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | completed | 42/42 | 0 | 134.683 | 0.312 | 9.779 | 12.709 | 0.229 |
| [fpn](models/fpn-seed0.md) | completed | 42/42 | 0 | 116.070 | 0.362 | 8.147 | 11.756 | 0.242 |
| [unet_2d](models/unet_2d-seed0.md) | completed | 42/42 | 0 | 128.635 | 0.327 | 8.846 | 12.682 | 0.250 |
| [segformer_b0](models/segformer_b0-seed0.md) | completed | 42/42 | 0 | 115.383 | 0.364 | 8.300 | 10.506 | 0.254 |
| [pidnet](models/pidnet-seed0.md) | completed | 42/42 | 0 | 114.782 | 0.366 | 8.156 | 11.799 | 0.078 |
| [ddrnet](models/ddrnet-seed0.md) | completed | 42/42 | 0 | 125.627 | 0.334 | 9.130 | 13.098 | 0.061 |
| [bisenetv2](models/bisenetv2-seed0.md) | completed | 42/42 | 0 | 112.266 | 0.374 | 8.066 | 9.799 | 0.123 |
| [lraspp](models/lraspp-seed0.md) | completed | 42/42 | 0 | 121.589 | 0.345 | 8.533 | 11.661 | 0.057 |

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
