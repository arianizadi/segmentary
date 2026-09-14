# Native CT pipeline and standardized model inference

Generated: 2026-09-14T18:33:30.436031+00:00. Source: `9714becaed028d7f0b03e1cf1782f68eb8c52853`.

## Native CT prediction

This measures heterogeneous full CT examinations. Case p50/p95 includes CPU work and, in overlapped runs, queue time. Scans/s is reported only from a complete successful cohort and a measured aggregate pipeline wall timer; overlapping case latencies are never summed to infer throughput. Failed and missing cases remain visible. Peak memory is Torch allocator memory, excluding the CUDA context.

| Model | Status | Cases | Failed | Pipeline wall s | Scans/s | Case p50 s | Case p95 s | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control-seed0](models/dynunet-control-seed0.md) | completed | 42/42 | 0 | 124.152 | 0.338 | 8.787 | 11.853 | 4.479 |
| [dynunet-mass50-seed0](models/dynunet-mass50-seed0.md) | completed | 42/42 | 0 | 114.918 | 0.365 | 8.336 | 10.135 | 4.479 |
| [dynunet-class111-seed0](models/dynunet-class111-seed0.md) | completed | 42/42 | 0 | 119.332 | 0.352 | 8.562 | 10.371 | 4.479 |
| [dynunet-class115-seed0](models/dynunet-class115-seed0.md) | completed | 42/42 | 0 | 120.476 | 0.349 | 8.446 | 12.152 | 4.479 |
| [dynunet-rotation-seed0](models/dynunet-rotation-seed0.md) | completed | 42/42 | 0 | 120.600 | 0.348 | 8.946 | 10.645 | 4.479 |
| [dynunet-intensity-seed0](models/dynunet-intensity-seed0.md) | completed | 42/42 | 0 | 119.684 | 0.351 | 8.682 | 11.182 | 4.479 |

[Per-case numerical timings](inference-cases.csv) use stable validation case ordinals. They contain preprocessing, tiled inference, reconstruction and export when recorded. Tiled inference includes copies, softmax and CPU blending; it is not model-only forward latency.

## Standardized model-only forward

B1 synthetic inputs use each model's declared patch, context and precision. Warmup/sample counts and checkpoint/source/runtime fingerprints are retained in model records. The benchmark keeps inference-mode/autocast active across its warmup and measured calls, including a warm autocast weight cache; the clinical tile pipeline may enter autocast separately for each batch. Patches/s is the reciprocal of mean CUDA-event forward latency, not complete CT scans/s. Different 2D and 3D patch dimensions are separate workloads. Unmeasured models remain marked not_recorded until their benchmark executes.

| Model | Benchmark | Patch | Precision | Patches/s | p50 ms | p95 ms | Parameters | Weight MiB | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [dynunet-control-seed0](models/dynunet-control-seed0.md) | completed | [96, 96, 96] | bf16 | 115.820 | 8.631 | 8.656 | 16543683.0 | 126.218 | 0.625 |
| [dynunet-mass50-seed0](models/dynunet-mass50-seed0.md) | completed | [96, 96, 96] | bf16 | 115.820 | 8.632 | 8.650 | 16543683.0 | 126.218 | 0.625 |
| [dynunet-class111-seed0](models/dynunet-class111-seed0.md) | completed | [96, 96, 96] | bf16 | 115.793 | 8.627 | 8.665 | 16543683.0 | 126.218 | 0.625 |
| [dynunet-class115-seed0](models/dynunet-class115-seed0.md) | completed | [96, 96, 96] | bf16 | 115.768 | 8.637 | 8.668 | 16543683.0 | 126.218 | 0.625 |
| [dynunet-rotation-seed0](models/dynunet-rotation-seed0.md) | completed | [96, 96, 96] | bf16 | 115.790 | 8.629 | 8.667 | 16543683.0 | 126.218 | 0.625 |
| [dynunet-intensity-seed0](models/dynunet-intensity-seed0.md) | completed | [96, 96, 96] | bf16 | 115.783 | 8.630 | 8.661 | 16543683.0 | 126.218 | 0.625 |

[Training cost](training-cost.md) · [Comparison](comparison.md)
