# Native CT pipeline and standardized model inference

Generated: 2026-09-14T21:30:08.948358+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

## Native CT prediction

This measures heterogeneous full CT examinations. Case p50/p95 includes CPU work and, in overlapped runs, queue time. Scans/s is reported only from a complete successful cohort and a measured aggregate pipeline wall timer; overlapping case latencies are never summed to infer throughput. Failed and missing cases remain visible. Peak memory is Torch allocator memory, excluding the CUDA context.

| Model | Status | Cases | Failed | Pipeline wall s | Scans/s | Case p50 s | Case p95 s | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet-long30k-seed0](models/dynunet-long30k-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet-fine10k-seed0](models/dynunet-fine10k-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |

[Per-case numerical timings](inference-cases.csv) use stable validation case ordinals. They contain preprocessing, tiled inference, reconstruction and export when recorded. Tiled inference includes copies, softmax and CPU blending; it is not model-only forward latency.

## Standardized model-only forward

B1 synthetic inputs use each model's declared patch, context and precision. Warmup/sample counts and checkpoint/source/runtime fingerprints are retained in model records. The benchmark keeps inference-mode/autocast active across its warmup and measured calls, including a warm autocast weight cache; the clinical tile pipeline may enter autocast separately for each batch. Patches/s is the reciprocal of mean CUDA-event forward latency, not complete CT scans/s. Different 2D and 3D patch dimensions are separate workloads. Unmeasured models remain marked not_recorded until their benchmark executes.

| Model | Benchmark | Patch | Precision | Patches/s | p50 ms | p95 ms | Parameters | Weight MiB | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 16543683 | — | — |
| [dynunet-long30k-seed0](models/dynunet-long30k-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 16543683 | — | — |
| [dynunet-fine10k-seed0](models/dynunet-fine10k-seed0.md) | not_recorded | [96, 144, 144] | bf16 | — | — | — | 16543683 | — | — |

[Training cost](training-cost.md) · [Comparison](comparison.md)
