# Training throughput and resource checks

Generated: 2026-09-15T20:36:04.494272+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

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

Measurement scope: Prelaunch capacity profiles on one real audited training CT, standard architectures, scratch AdamW, gradient clipping at 12. Median step time after two warmup updates includes CPU patch sampling from one in-memory preprocessed case, CPU-to-GPU transfers, forward, loss, backward, optimizer and CUDA synchronization. It excludes NIfTI loading, per-run cache checks, full-volume validation, checkpoint writes and final evaluation. Profiles ran concurrently across GPUs and share CPU/storage. Remaining fifteen 2D profiles plus rerun HRNet use configured AdamW weight decay 1e-5; the older eight 3D profiles and U-Net++ used the optimizer default 0.01. These measurements establish capacity and numerical liveness only, not quality or expected whole-campaign duration. All three Mamba rows use the compiled native selective-scan kernel and explicit pure-mixer activation checkpointing, preserving standard capacity and effective batch8. Their AdamW honors the harness no-weight-decay SSM parameter groups. U-MambaEnc originally exceeded memory without activation checkpointing; the failed evidence is preserved separately. Native Mamba reserved allocator memory was not recorded and is left unavailable. These capacity runs predate enabling ordered CPU batch prefetch in the campaign.. GPU: NVIDIA L40S 48GB. Warmup / measured steps: 2 / 8.

| Model | Status | Precision | Batch | Patch | Scan / recompute | Seconds / training step | Peak allocated GiB | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bisenetv2 | passed | bf16 | 8 | [256, 256] | — / — | 0.0574 | 0.50 | 0.64 |
| convnext_upernet | passed | bf16 | 8 | [256, 256] | — / — | 0.0838 | 2.36 | 2.50 |
| ddrnet | passed | bf16 | 8 | [256, 256] | — / — | 0.0566 | 0.23 | 0.25 |
| deeplabv3_plus | passed | bf16 | 8 | [256, 256] | — / — | 0.0585 | 1.07 | 1.13 |
| dpt | passed | bf16 | 8 | [256, 256] | — / — | 0.0959 | 3.06 | 3.46 |
| dynunet | passed | bf16 | 8 | [96, 96, 96] | — / — | 0.3270 | 7.61 | — |
| fpn | passed | bf16 | 8 | [256, 256] | — / — | 0.0539 | 0.76 | 0.79 |
| hrnet_ocr | passed | bf16 | 8 | [256, 256] | — / — | 0.1235 | 1.85 | 1.97 |
| lraspp | passed | bf16 | 8 | [256, 256] | — / — | 0.0568 | 0.37 | 0.43 |
| mask2former | passed | bf16 | 8 | [256, 256] | — / — | 0.2056 | 3.47 | 3.69 |
| maskformer | passed | bf16 | 8 | [256, 256] | — / — | 0.1295 | 2.20 | 2.26 |
| medformer | passed | bf16 | 8 | [96, 96, 96] | — / — | 0.8881 | 29.91 | — |
| mednext_v1 | passed | bf16 | 8 | [96, 96, 96] | — / — | 0.7665 | 29.37 | — |
| pidnet | passed | bf16 | 8 | [256, 256] | — / — | 0.0600 | 0.31 | 0.31 |
| segformer_b0 | passed | bf16 | 8 | [256, 256] | — / — | 0.0617 | 0.62 | 0.75 |
| segformer_b2 | passed | bf16 | 8 | [256, 256] | — / — | 0.0840 | 2.07 | 2.35 |
| segmamba | passed | bf16 | 8 | [96, 96, 96] | native / True | 1.3965 | 19.29 | — |
| segresnet | passed | bf16 | 8 | [96, 96, 96] | — / — | 0.4678 | 17.07 | — |
| swin_unetr | passed | bf16 | 8 | [96, 96, 96] | — / — | 0.7106 | 24.69 | — |
| swin_upernet | passed | bf16 | 8 | [256, 256] | — / — | 0.0960 | 2.53 | 2.74 |
| transunet_3d | passed | bf16 | 8 | [96, 96, 96] | — / — | 0.3697 | 9.79 | — |
| umamba_bot | passed | bf16 | 8 | [96, 96, 96] | native / True | 0.6392 | 15.40 | — |
| umamba_enc | passed | bf16 | 8 | [96, 96, 96] | native / True | 1.5352 | 33.50 | — |
| unet_2d | passed | bf16 | 8 | [256, 256] | — / — | 0.0585 | 0.78 | 0.84 |
| unet_3d | passed | bf16 | 8 | [96, 96, 96] | — / — | 0.1243 | 1.13 | — |
| unet_plus_plus | passed | bf16 | 8 | [256, 256] | — / — | 0.0719 | 1.39 | — |
| unetr | passed | bf16 | 8 | [96, 96, 96] | — / — | 0.2829 | 6.71 | — |

A short profile measures runtime feasibility, not model quality. These values do not estimate whole-campaign runtime unless their measurement scope includes the cache, CPU transfers, native validation and checkpoint writes. Do not extrapolate small-patch SGD smoke tests to full AdamW training. Recheck real epoch timings after launch; concurrent jobs share CPU, memory and storage bandwidth.

GPU utilization snapshots, vmstat, process CPU/RSS, file descriptors and, when needed, a bounded NVIDIA Nsight Systems trace can identify stalls. A profiler being installed is not evidence that a trace was captured or analyzed. The model pages retain actual stage allocation times and memory evidence; missing measurements remain unknown.

[All model results](comparison.md) · [Learning curves](learning-curves.md)

## Warm cache loading and patch sampling

Medians from repeated warm reads; the OS page cache was not dropped. Mapping setup defers page faults, so it is not a claim that an entire CT was read in the mapping time. Patch sampling includes touching the needed mapped pages. All cases come from the training partition.

| Model | Training size | Reads | NPZ load ms | NPY mapping ms | Old patch ms | New patch ms | Exact patch/RNG |
| --- | --- | --- | --- | --- | --- | --- | --- |
| medformer | smallest | 10 | 63.20 | 0.78 | 3.37 | 1.28 | True |
| medformer | median | 10 | 106.50 | 0.78 | 5.65 | 1.44 | True |
| medformer | largest | 10 | 150.03 | 0.80 | 7.46 | 1.59 | True |
| segformer_b2 | smallest | 10 | 62.86 | 0.76 | 0.62 | 0.40 | True |
| segformer_b2 | median | 10 | 106.90 | 0.79 | 0.62 | 0.48 | True |
| segformer_b2 | largest | 10 | 150.13 | 0.80 | 0.50 | 0.45 | True |
| unet_3d | smallest | 10 | 63.24 | 0.77 | 3.80 | 1.30 | True |
| unet_3d | median | 10 | 107.09 | 0.79 | 9.40 | 1.47 | True |
| unet_3d | largest | 10 | 149.97 | 0.79 | 7.55 | 1.59 | True |

## Instrumented training stages

These measurements synchronize CUDA around every stage and may include profiler overhead. They diagnose where time goes; they are not uninstrumented steady campaign throughput. Forward includes the loss; host-to-device includes stacking CPU patches. Warmup/measured counts are stated for each model.

| Model | Warmup/measured | Barriers/profiler | Sample ms | Stack+H2D ms | Forward ms | Backward ms | Optimizer ms | Whole step ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| medformer | 3/5 | True/True | 8.66 | 12.57 | 255.09 | 515.88 | 9.80 | 802.88 |
| segformer_b2 | 3/5 | True/True | 2.07 | 2.72 | 26.06 | 33.28 | 9.27 | 75.31 |
| unet_3d | 3/5 | True/True | 8.51 | 11.42 | 11.89 | 12.08 | 1.60 | 45.86 |

## CPU prefetch and compact transfers

| Synchronous ms | Prefetch ms | Throughput ratio | Warmup/measured | Exact weights/RNG | Maximum parameter difference |
| --- | --- | --- | --- | --- | --- |
| 72.14 | 37.28 | 1.9351 | 10/50 | True/True | 0.0000 |

UNet3D, batch 8, BF16, 96-cubed patches, one median-size training CT and a warm mapped cache. This separate experiment times whole steps without per-stage barriers or a profiler; it synchronizes at the end of each step. It excludes initial cache construction, full-volume validation and checkpoint publication. Equality applies to this measured training comparison, not every optimization.

## Native reconstruction and inference batching

| Training size | Sequential inverse s | Three-thread inverse s | Exact probability channels |
| --- | --- | --- | --- |
| median | 3.5275 | 1.1762 | True |
| largest | 14.3445 | 4.7849 | True |

The inverse transform evaluates three independent probability channels with unchanged interpolation. Its equality test is separate from model inference batching.

| Model | Inference batch | Batch-1 s | Batched s | Changed argmax voxels | Native voxels | Changed percent |
| --- | --- | --- | --- | --- | --- | --- |
| medformer | 8 | 3.5166 | 3.3232 | 0 | 9699328 | 0.0000 |
| segformer_b2 | 8 | 5.8664 | 3.7761 | 3369 | 9699328 | 0.0347 |
| unet_3d | 8 | 2.4498 | 2.4744 | 9905 | 9699328 | 0.1021 |

Tile batching preserves coverage and the blending order, but BF16 kernels can change rounding and argmax labels. These early scratch predictions are a numerical comparison, not quality scores. Freeze inference_batch_size before training and keep it consistent across the comparison. Do not describe all optimizations as bitwise invariant.

## Shared cache and host capacity

| Training cases | Cache GiB | Host RAM GiB | Available RAM GiB | I/O some/full avg10 |
| --- | --- | --- | --- | --- |
| 197 | 7.51 | 755.53 | 735.23 | 0.0/0.0 |

RAM availability and Linux pressure-stall averages are a point-in-time host snapshot. A cache fitting in RAM does not guarantee every page remains resident, and zero measured I/O pressure does not establish future absence of contention.

These tables are generated from sanitized numerical records. Original trace files, scan names and server paths remain on the host. Source summary SHA256 digests:

- `4b14777e9bb761a9ada62641e85af80c78dcf9b7e21644f2d2078ddbfa75097b`
- `50725f04dd209a28888a4bfbfff1d40a7446b0f99169db95502cb3c3d848b4d0`
- `75a1f48d5ecf31a87cba60d9a0c69e940636c7135e2acc396ea012ca90046555`
- `7f820c371f5a47db817223903e221e9c43cac60172bc1ae1a240dd09871d7751`
- `da9ef29924451913ee7dc48b2cbeddf4377f4eefd3cab85f591555cba4fd1251`
- `dec77084f58547c4a1a25b4bbaedc1ba1692ad9cba924f0e2272a3cb303b3665`

Method references: [PyTorch 2.11 profiler](https://docs.pytorch.org/docs/2.11/profiler.html) and [official Mamba implementation](https://github.com/state-spaces/mamba).
