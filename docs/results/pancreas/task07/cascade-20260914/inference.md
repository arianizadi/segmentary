# Native CT pipeline and standardized model inference

Generated: 2026-09-15T01:15:00.545132+00:00. Source: `8fd7fe0dc773a9d60d333e4cdb663e3c255f9868`.

## Native CT prediction

This measures heterogeneous full CT examinations. Case p50/p95 includes CPU work and, in overlapped runs, queue time. Scans/s is reported only from a complete successful cohort and a measured aggregate pipeline wall timer; overlapping case latencies are never summed to infer throughput. Failed and missing cases remain visible. Peak memory is Torch allocator memory, excluding the CUDA context.

| Model | Status | Cases | Failed | Pipeline wall s | Scans/s | Case p50 s | Case p95 s | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | running | 0/42 | 0 | — | — | — | — | — |
| [dynunet-roi20-seed0](models/dynunet-roi20-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |
| [dynunet-roi40-seed0](models/dynunet-roi40-seed0.md) | queued | 0/42 | 0 | — | — | — | — | — |

[Per-case numerical timings](inference-cases.csv) use stable validation case ordinals. They contain preprocessing, tiled inference, reconstruction and export when recorded. Tiled inference includes copies, softmax and CPU blending; it is not model-only forward latency.

## Standardized model-only forward

B1 synthetic inputs use each model's declared patch, context and precision. Warmup/sample counts and checkpoint/source/runtime fingerprints are retained in model records. The benchmark keeps inference-mode/autocast active across its warmup and measured calls, including a warm autocast weight cache; the clinical tile pipeline may enter autocast separately for each batch. Patches/s is the reciprocal of mean CUDA-event forward latency, not complete CT scans/s. Different 2D and 3D patch dimensions are separate workloads. Unmeasured models remain marked not_recorded until their benchmark executes.

| Model | Benchmark | Patch | Precision | Patches/s | p50 ms | p95 ms | Parameters | Weight MiB | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control10k-seed0](models/dynunet-control10k-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | 16543683 | — | — |
| [dynunet-roi20-seed0](models/dynunet-roi20-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |
| [dynunet-roi40-seed0](models/dynunet-roi40-seed0.md) | not_recorded | [96, 96, 96] | bf16 | — | — | — | None | — | — |

[Training cost](training-cost.md) · [Comparison](comparison.md)
