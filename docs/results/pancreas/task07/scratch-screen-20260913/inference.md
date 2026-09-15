# Native CT pipeline and standardized model inference

Generated: 2026-09-15T14:01:42.586856+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

## Native CT prediction

This measures heterogeneous full CT examinations. Case p50/p95 includes CPU work and, in overlapped runs, queue time. Scans/s is reported only from a complete successful cohort and a measured aggregate pipeline wall timer; overlapping case latencies are never summed to infer throughput. Failed and missing cases remain visible. Peak memory is Torch allocator memory, excluding the CUDA context.

| Model | Status | Cases | Failed | Pipeline wall s | Scans/s | Case p50 s | Case p95 s | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [nnunet_resenc_l](models/nnunet_resenc_l-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [umamba_enc](models/umamba_enc-seed0.md) | completed | 42/42 | 0 | — | — | 7.561 | 11.806 | — |
| [segmamba](models/segmamba-seed0.md) | completed | 42/42 | 0 | — | — | 8.459 | 12.950 | — |
| [umamba_bot](models/umamba_bot-seed0.md) | completed | 42/42 | 0 | — | — | 7.493 | 11.457 | — |
| [swin_unetr](models/swin_unetr-seed0.md) | completed | 42/42 | 0 | — | — | 6.656 | 9.757 | — |
| [unetr](models/unetr-seed0.md) | completed | 42/42 | 0 | — | — | 5.826 | 8.430 | — |
| [transunet_3d](models/transunet_3d-seed0.md) | completed | 42/42 | 0 | — | — | 6.108 | 8.529 | — |
| [medformer](models/medformer-seed0.md) | completed | 42/42 | 0 | — | — | 6.683 | 11.520 | — |
| [mednext_v1](models/mednext_v1-seed0.md) | completed | 42/42 | 0 | — | — | 7.202 | 10.868 | — |
| [dynunet](models/dynunet-seed0.md) | completed | 42/42 | 0 | — | — | 5.779 | 8.682 | — |
| [segresnet](models/segresnet-seed0.md) | completed | 42/42 | 0 | — | — | 7.709 | 26.154 | — |
| [unet_3d](models/unet_3d-seed0.md) | completed | 42/42 | 0 | — | — | 5.588 | 7.902 | — |
| [mask2former](models/mask2former-seed0.md) | completed | 42/42 | 0 | — | — | 11.874 | 22.366 | — |
| [maskformer](models/maskformer-seed0.md) | completed | 42/42 | 0 | — | — | 9.972 | 18.733 | — |
| [dpt](models/dpt-seed0.md) | completed | 42/42 | 0 | — | — | 6.726 | 14.906 | — |
| [swin_upernet](models/swin_upernet-seed0.md) | completed | 42/42 | 0 | — | — | 7.664 | 11.210 | — |
| [convnext_upernet](models/convnext_upernet-seed0.md) | completed | 42/42 | 0 | — | — | 7.587 | 11.209 | — |
| [segformer_b2](models/segformer_b2-seed0.md) | completed | 42/42 | 0 | — | — | 8.122 | 12.209 | — |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | completed | 42/42 | 0 | — | — | 8.968 | 13.576 | — |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | completed | 42/42 | 0 | — | — | 7.448 | 11.926 | — |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | completed | 42/42 | 0 | — | — | 6.377 | 9.544 | — |
| [fpn](models/fpn-seed0.md) | completed | 42/42 | 0 | — | — | 5.574 | 9.164 | — |
| [unet_2d](models/unet_2d-seed0.md) | completed | 42/42 | 0 | — | — | 7.261 | 9.878 | — |
| [segformer_b0](models/segformer_b0-seed0.md) | completed | 42/42 | 0 | — | — | 6.703 | 10.615 | — |
| [pidnet](models/pidnet-seed0.md) | completed | 42/42 | 0 | — | — | 6.360 | 9.293 | — |
| [ddrnet](models/ddrnet-seed0.md) | completed | 42/42 | 0 | — | — | 6.054 | 8.466 | — |
| [bisenetv2](models/bisenetv2-seed0.md) | completed | 42/42 | 0 | — | — | 5.692 | 7.810 | — |
| [lraspp](models/lraspp-seed0.md) | completed | 42/42 | 0 | — | — | 5.707 | 8.014 | — |

[Per-case numerical timings](inference-cases.csv) use stable validation case ordinals. They contain preprocessing, tiled inference, reconstruction and export when recorded. Tiled inference includes copies, softmax and CPU blending; it is not model-only forward latency.

## Standardized model-only forward

B1 synthetic inputs use each model's declared patch, context and precision. Warmup/sample counts and checkpoint/source/runtime fingerprints are retained in model records. The benchmark keeps inference-mode/autocast active across its warmup and measured calls, including a warm autocast weight cache; the clinical tile pipeline may enter autocast separately for each batch. Patches/s is the reciprocal of mean CUDA-event forward latency, not complete CT scans/s. Different 2D and 3D patch dimensions are separate workloads. Unmeasured models remain marked not_recorded until their benchmark executes.

| Model | Benchmark | Patch | Precision | Patches/s | p50 ms | p95 ms | Parameters | Weight MiB | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [nnunet_resenc_l](models/nnunet_resenc_l-seed0.md) | not_recorded | — | — | — | — | — | None | — | — |
| [umamba_enc](models/umamba_enc-seed0.md) | completed | [96, 96, 96] | bf16 | 17.114 | 58.428 | 58.497 | 22808675.0 | 87.008 | 2.666 |
| [segmamba](models/segmamba-seed0.md) | completed | [96, 96, 96] | bf16 | 20.232 | 49.414 | 49.499 | 67362723.0 | 256.968 | 1.303 |
| [umamba_bot](models/umamba_bot-seed0.md) | completed | [96, 96, 96] | bf16 | 44.958 | 22.242 | 22.273 | 22570531.0 | 86.100 | 0.850 |
| [swin_unetr](models/swin_unetr-seed0.md) | completed | [96, 96, 96] | bf16 | 32.901 | 30.348 | 30.628 | 15703029.0 | 67.083 | 1.742 |
| [unetr](models/unetr-seed0.md) | completed | [96, 96, 96] | bf16 | 64.999 | 15.378 | 15.409 | 92783859.0 | 353.942 | 0.805 |
| [transunet_3d](models/transunet_3d-seed0.md) | completed | [96, 96, 96] | bf16 | 54.498 | 18.338 | 18.664 | 102279168.0 | 390.164 | 1.061 |
| [medformer](models/medformer-seed0.md) | completed | [96, 96, 96] | bf16 | 24.731 | 40.420 | 40.543 | 39591555.0 | 151.030 | 2.082 |
| [mednext_v1](models/mednext_v1-seed0.md) | completed | [96, 96, 96] | bf16 | 39.134 | 25.553 | 25.581 | 5550947.0 | 21.175 | 0.982 |
| [dynunet](models/dynunet-seed0.md) | completed | [96, 96, 96] | bf16 | 115.027 | 8.683 | 8.805 | 16543683.0 | 126.218 | 0.625 |
| [segresnet](models/segresnet-seed0.md) | completed | [96, 96, 96] | bf16 | 39.792 | 25.121 | 25.219 | 18796035.0 | 71.701 | 0.691 |
| [unet_3d](models/unet_3d-seed0.md) | completed | [96, 96, 96] | bf16 | 704.867 | 1.410 | 1.434 | 7914603.0 | 30.192 | 0.121 |
| [mask2former](models/mask2former-seed0.md) | completed | [256, 256] | bf16 | 21.882 | 44.983 | 48.155 | 47404926.0 | 180.835 | 0.361 |
| [maskformer](models/maskformer-seed0.md) | completed | [256, 256] | bf16 | 39.298 | 25.266 | 26.218 | 41722302.0 | 159.378 | 0.283 |
| [dpt](models/dpt-seed0.md) | completed | [256, 256] | bf16 | 78.858 | 12.601 | 13.016 | 110694086.0 | 422.268 | 0.562 |
| [swin_upernet](models/swin_upernet-seed0.md) | completed | [256, 256] | bf16 | 62.544 | 15.809 | 16.891 | 59831744.0 | 228.289 | 0.432 |
| [convnext_upernet](models/convnext_upernet-seed0.md) | completed | [256, 256] | bf16 | 125.416 | 7.966 | 7.993 | 60132518.0 | 229.436 | 0.432 |
| [segformer_b2](models/segformer_b2-seed0.md) | completed | [256, 256] | bf16 | 58.446 | 17.035 | 17.468 | 27355203.0 | 104.358 | 0.289 |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | completed | [256, 256] | bf16 | 41.554 | 24.052 | 24.227 | 34919750.0 | 133.455 | 0.211 |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | completed | [256, 256] | bf16 | 215.092 | 4.636 | 4.666 | 26085171.0 | 99.587 | 0.191 |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | completed | [256, 256] | bf16 | 223.351 | 4.424 | 4.588 | 26684371.0 | 102.012 | 0.143 |
| [fpn](models/fpn-seed0.md) | completed | [256, 256] | bf16 | 279.025 | 3.569 | 3.594 | 23161923.0 | 88.421 | 0.133 |
| [unet_2d](models/unet_2d-seed0.md) | completed | [256, 256] | bf16 | 281.221 | 3.548 | 3.579 | 24442931.0 | 93.315 | 0.133 |
| [segformer_b0](models/segformer_b0-seed0.md) | completed | [256, 256] | bf16 | 114.103 | 8.675 | 8.901 | 3718051.0 | 14.185 | 0.109 |
| [pidnet](models/pidnet-seed0.md) | completed | [256, 256] | bf16 | 165.923 | 5.951 | 6.316 | 7717383.0 | 29.535 | 0.057 |
| [ddrnet](models/ddrnet-seed0.md) | completed | [256, 256] | bf16 | 230.711 | 4.299 | 4.381 | 5732838.0 | 21.946 | 0.037 |
| [bisenetv2](models/bisenetv2-seed0.md) | completed | [256, 256] | bf16 | 224.904 | 4.432 | 4.464 | 5194703.0 | 19.897 | 0.057 |
| [lraspp](models/lraspp-seed0.md) | completed | [256, 256] | bf16 | 268.764 | 3.711 | 3.737 | 3218766.0 | 12.373 | 0.037 |

[Training cost](training-cost.md) · [Comparison](comparison.md)
