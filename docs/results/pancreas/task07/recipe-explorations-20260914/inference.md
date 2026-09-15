# Native CT pipeline and standardized model inference

Generated: 2026-09-15T00:08:47.221908+00:00. Source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`.

## Native CT prediction

This measures heterogeneous full CT examinations. Case p50/p95 includes CPU work and, in overlapped runs, queue time. Scans/s is reported only from a complete successful cohort and a measured aggregate pipeline wall timer; overlapping case latencies are never summed to infer throughput. Failed and missing cases remain visible. Peak memory is Torch allocator memory, excluding the CUDA context.

| Model | Status | Cases | Failed | Pipeline wall s | Scans/s | Case p50 s | Case p95 s | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet-deep10k-seed0](models/dynunet-deep10k-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet-focal05-seed0](models/dynunet-focal05-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet-focal10-seed0](models/dynunet-focal10-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet-window-seed0](models/dynunet-window-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet-minmax-seed0](models/dynunet-minmax-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet-isotropic-seed0](models/dynunet-isotropic-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [swin_unetr-swin24-seed0](models/swin_unetr-swin24-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [swin_unetr-swin48-seed0](models/swin_unetr-swin48-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |

[Per-case numerical timings](inference-cases.csv) use stable validation case ordinals. They contain preprocessing, tiled inference, reconstruction and export when recorded. Tiled inference includes copies, softmax and CPU blending; it is not model-only forward latency.

## Standardized model-only forward

B1 synthetic inputs use each model's declared patch, context and precision. Warmup/sample counts and checkpoint/source/runtime fingerprints are retained in model records. The benchmark keeps inference-mode/autocast active across its warmup and measured calls, including a warm autocast weight cache; the clinical tile pipeline may enter autocast separately for each batch. Patches/s is the reciprocal of mean CUDA-event forward latency, not complete CT scans/s. Different 2D and 3D patch dimensions are separate workloads. Unmeasured models remain marked not_recorded until their benchmark executes.

| Model | Benchmark | Patch | Precision | Patches/s | p50 ms | p95 ms | Parameters | Weight MiB | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |
| [dynunet-deep10k-seed0](models/dynunet-deep10k-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |
| [dynunet-focal05-seed0](models/dynunet-focal05-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |
| [dynunet-focal10-seed0](models/dynunet-focal10-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |
| [dynunet-window-seed0](models/dynunet-window-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |
| [dynunet-minmax-seed0](models/dynunet-minmax-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |
| [dynunet-isotropic-seed0](models/dynunet-isotropic-seed0.md) | not_recorded | [160, 96, 96] | bf16 | — | — | — | None | — | — |
| [swin_unetr-swin24-seed0](models/swin_unetr-swin24-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |
| [swin_unetr-swin48-seed0](models/swin_unetr-swin48-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |

[Training cost](training-cost.md) · [Comparison](comparison.md)
