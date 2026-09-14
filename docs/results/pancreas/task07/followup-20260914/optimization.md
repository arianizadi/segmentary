# Training throughput and resource checks

Generated: 2026-09-14T23:00:17.977338+00:00. Source: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

The throughput investigation checks data loading, CPU work, GPU training, full-volume validation and durable result writing separately. The aim is to reduce repeated work while preserving the split, physical image geometry, objective and scratch initialization.

| Area | Campaign implementation | How to interpret it |
| --- | --- | --- |
| Repeated preprocessing | Content-addressed, immutable shared preprocessed arrays | Models share fixed image/label preprocessing; caches are bound to source and recipe hashes |
| Repeated volume decompression | Read-only NumPy memory maps with a bounded open-case cache | Avoid loading and decompressing an entire CT for every randomly chosen training patch |
| Foreground sampling | Cache foreground coordinates; select and crop the required patch | Preserve sampling semantics while reducing full-volume scans and padding |
| Validation cost | Full native validation at the first epoch, configured interval, and final epoch | Less frequent validation saves compute; it also changes checkpoint-selection opportunities, so cadence is recorded |
| Inference overhead | Configurable batches of sliding-window tiles | This batches the same coverage and blending; it does not replace native evaluation with crop scores |
| GPU scheduling | One job per GPU with existing GPU locks and an explicit queue | Ten GPUs run different models concurrently; this is not ten-GPU data parallelism for each model |
| Live diagnostics | Per-step progress, per-epoch metrics, stage logs, allocator peaks | Logs distinguish slow training from full-volume validation; allocator memory differs from total device usage |

## Measured model profiles

Measurement scope: No profile records supplied in this snapshot. GPU: not recorded. Warmup / measured steps: None / None.

| Model | Status | Precision | Batch | Patch | Scan / recompute | Seconds / training step | Peak allocated GiB | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

A short profile measures runtime feasibility, not model quality. These values do not estimate whole-campaign runtime unless their measurement scope includes the cache, CPU transfers, native validation and checkpoint writes. Do not extrapolate small-patch SGD smoke tests to full AdamW training. Recheck real epoch timings after launch; concurrent jobs share CPU, memory and storage bandwidth.

GPU utilization snapshots, vmstat, process CPU/RSS, file descriptors and, when needed, a bounded NVIDIA Nsight Systems trace can identify stalls. A profiler being installed is not evidence that a trace was captured or analyzed. The model pages retain actual stage allocation times and memory evidence; missing measurements remain unknown.

[All model results](comparison.md) · [Learning curves](learning-curves.md)

## Pipeline measurements

No detailed pipeline evidence supplied in this snapshot.
