# Why the GPUs pause during the Task07 campaign

Measured 2026-09-14, 03:41–03:45 UTC for host/epoch/preprocessing evidence, with a later paired argmax microbenchmark (September 13 evening Pacific).
Frozen training source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

**The main observed bottleneck is CPU work between GPU inference bursts during full-volume validation and prediction.** Faster models spend much more recorded time validating than updating weights. Some zero-utilization intervals are expected CPU-only evaluation/preparation. The training dashboard also labels checkpoint saves as training, so that phase does not guarantee kernels are running.

This investigation changed no active source, recipe, environment, checkpoints, validation cadence, or training process. It used live host telemetry, existing epoch records, source review, and a separate CPU-only diagnostic on a training examination. [Numerical evidence](evidence.json) accompanies this report. The [previous optimization report](../scratch-screen-20260913/optimization.md) describes improvements already in the frozen campaign.

## What the GPUs actually did

One 61-sample window at approximately one-second intervals, 03:41:39–03:42:39 UTC. State was read every five samples. These arithmetic sample means describe this window, not the full campaign; an intermittent task can have substantially different utilization later.

| GPU | Activity observed | Mean GPU utilization | Zero readings /61 |
| --- | --- | ---: | ---: |
| 0 | nnU-Net training | 94.9% | 2 |
| 1 | U-Mamba encoder validation | 37.7% | 34 |
| 2 | SegMamba training | 99.8% | 0 |
| 3 | DeepLabV3+ final prediction | 4.8% | 54 |
| 4 | FPN CPU evaluation → BiSeNetV2 preparation/preprocessing | 0.0% | 61 |
| 5 | HRNet+OCR training (includes checkpoint gaps) | 47.4% | 2 |
| 6 | DDRNet preprocessing/training → validation | 4.6% | 51 |
| 7 | PIDNet validation | 4.5% | 52 |
| 8 | SegFormer B 0 training → validation | 16.2% | 24 |
| 9 | U-Net 2D validation | 7.6% | 50 |

The sampled inference/validation worker processes generally consumed 1.3–1.9 CPU cores. Their physical read counters were essentially zero while logical reads advanced: the page cache was serving the files, but decoding, hashing, array operations, and resampling still cost CPU time. This does not establish that storage will never bottleneck another workload. The earlier short `vmstat` observation showed 94–95% aggregate CPU idle, no active swapping, and zero reported I/O wait.

HRNet's worker wrote about 2.35 GiB and logically read 2.44 GiB during the minute, consistent with checkpoint work in the reviewed implementation. Its recorded median training step was 0.0998 s, versus 0.1235 s in the prelaunch capacity diagnostic. Those measurements have different scopes, so they do not prove a speedup; they do not establish a training throughput regression either. We have not traced individual live CUDA kernels or measured the exact split between training synchronization and checkpoint gaps.

`nvidia-smi` utilization is the fraction of a sampling period with GPU kernels executing, not the fraction of theoretical compute capacity achieved. Refreshing the display at 0.2 s does not redefine the device's underlying measurement window. See [NVIDIA's definition](https://docs.nvidia.com/deploy/nvidia-smi/).

## Where recorded job time goes

The table includes every model. Completed epoch records only: a currently running epoch or validation is omitted until its metrics record is written. Validation percentage is `validation_seconds / (training_seconds + validation_seconds)`. It excludes initial setup, preprocessing, checkpoint/output overhead outside epoch timers, final prediction and final evaluation. Multiple jobs execute concurrently, so summing their durations is **not campaign wall time**.

| Model | Finished epoch records | Training minutes | Validation minutes | Validation share |
| --- | ---: | ---: | ---: | ---: |
| nnunet_resenc_l | Separate nnU-Net log | — | — | — |
| umamba_enc | 89 | 216.14 | 42.12 | 16.3% |
| segmamba | 95 | 212.50 | 48.95 | 18.7% |
| umamba_bot | 100 | 93.52 | 40.34 | 30.1% |
| swin_unetr | 100 | 101.81 | 41.36 | 28.9% |
| unetr | 100 | 29.85 | 34.30 | 53.5% |
| transunet_3d | 100 | 44.75 | 35.36 | 44.1% |
| medformer | 100 | 130.81 | 42.99 | 24.7% |
| mednext_v1 | 100 | 111.56 | 43.09 | 27.9% |
| dynunet | 100 | 38.01 | 34.62 | 47.7% |
| segresnet | 100 | 61.12 | 40.85 | 40.1% |
| unet_3d | 100 | 9.82 | 32.70 | 76.9% |
| mask2former | 100 | 36.17 | 62.42 | 63.3% |
| maskformer | 100 | 21.78 | 50.72 | 70.0% |
| dpt | 100 | 10.84 | 45.19 | 80.6% |
| swin_upernet | 100 | 12.21 | 47.37 | 79.5% |
| convnext_upernet | 100 | 9.45 | 51.68 | 84.5% |
| segformer_b2 | 100 | 11.41 | 45.86 | 80.1% |
| hrnet_ocr | 99 | 16.41 | 57.79 | 77.9% |
| unet_plus_plus | 100 | 6.42 | 43.25 | 87.1% |
| deeplabv3_plus | 100 | 5.45 | 43.96 | 89.0% |
| fpn | 100 | 4.39 | 31.82 | 87.9% |
| unet_2d | 100 | 4.46 | 37.36 | 89.3% |
| segformer_b0 | 59 | 3.52 | 25.20 | 87.7% |
| pidnet | 29 | 1.76 | 12.39 | 87.6% |
| ddrnet | 0 | — | — | — |
| bisenetv2 | 0 | — | — | — |
| lraspp | 0 | — | — | — |

Across the 24 Torch models with completed epoch records: 19.90 summed hours of training and 16.53 summed hours of validation. Validation was 45.4% of their combined time. This mixed-model aggregate hides the stronger problem for fast networks: complete U-Net 2D spent 4.46 minutes updating weights and 37.36 minutes validating; ConvNeXt+UPerNet spent 9.45 minutes training and 51.68 minutes validating. Heavy MedFormer spent 130.81 minutes training and 42.99 minutes validating.

nnU-Net uses its own training/patch-validation loop. Its log showed 94 finished epochs with a 160.98 s median; that log does not separate the two components, so its time is not mixed into the Torch native-validation table.

## Measured CPU work and code causes

A separate diagnostic used the median native voxel-count examination in the frozen **training** partition: 512×512×93 voxels, processed to 93×306×306. No labels were opened, no checkpoint was loaded, and CUDA was hidden. Two profiled preprocessing runs took 2.280 s and 2.246 s. Filesystem cache was uncontrolled; profiler overhead is included.

| Component | Time | Interpretation |
| --- | ---: | --- |
| Entire preprocessing | 2.246–2.280 s | Real training CT |
| Full CT audit within preprocessing | 0.702–0.746 s | Included in preprocessing; do not add again |
| Affine resampling within preprocessing | 0.725–0.869 s | Included in preprocessing |
| Native probability reconstruction | 1.263 s | Existing three-channel parallel implementation; synthetic zero probabilities with real geometry |
| Stack three channels and choose each voxel's class | 1.360 s | Synthetic reconstructed arrays |

The real preprocessing plus synthetic reconstruction/argmax total is approximately 4.9 s for this geometry, excluding model inference, metrics, and export. This is an illustrative component total, **not** a measured complete prediction or a cohort-wide speed estimate.

The frozen implementation explains the waits:

1. `torch_data.preprocess_case` calls `geometry.validate_nifti`, then reloads and decodes the image before CPU resampling. The audit hashes the compressed file twice, fully decodes it, checks values/geometry, and hashes a canonical decoded representation. The same work repeats on every validation pass. The training cache/prefetch does not cover this inference path.
2. `torch_backend._validation` processes one case completely before starting the next. CPU preprocessing and reconstruction do not overlap GPU inference for another case.
3. `torch_data.predict_case` runs 2.5D slices sequentially. The measured geometry produces four tiles per slice, so configured batch 8 actually runs batches of 4, with 93 forward calls. Raising the batch limit alone cannot combine slices.
4. `tiled_probabilities` synchronizes to check finite logits and copy probabilities to CPU, then blends on CPU before the next batch. This is a candidate for a dedicated CUDA timeline; its individual cost was not measured here.
5. Final export repeats a full audit of the reference CT. Prediction-status updates hash the whole checkpoint after **each case**, outside the per-case timer. For 42 cases, current checkpoint sizes imply about 16.46 GiB of repeated hash input for HRNet, 28.24 GiB for ConvNeXt, and 51.97 GiB for DPT. Those are logical bytes, not measured physical disk traffic or measured hash duration.
6. Every 100 training updates, checkpoint saving copies/serializes state, flushes to disk, and hashes the result. The recorded epoch timer ends before that save. The following epoch's cumulative wall time captures the previous gap, but the dashboard phase remains `train`.

## One measured optimization candidate

A separate paired CPU benchmark compared the current stack/argmax/uint8 operation with finite three-channel comparisons that preserve earliest-class ties. Seeded synthetic float32 arrays had the same native shape; the three timed pairs alternated execution order.

| Operation | Median of three runs |
| --- | ---: |
| Current stack → argmax → uint8 | 0.4525 s |
| Pairwise comparison candidate | 0.1122 s |

The candidate was **4.03× faster for this operation**, saving approximately 0.34 s on these arrays. Labels matched exactly on all 24,379,392 voxels in every repetition, including nine explicit tie/class patterns. This requires exactly three finite channels. Inputs were synthetic, with no real model probability validation and no production change. The earlier 1.360 s zero-array timing came from a separate run; use these paired measurements for the speedup estimate. No whole-case or training speedup has been measured.

## Prioritized next changes

| Priority | Change to test | Required verification |
| --- | --- | --- |
| 1 | Immutable image-only validation/inference cache; audit once at controlled stage boundaries | Key by image hash, preprocessing config, geometry, implementation and dependency identity; reject changed/corrupt sources; preserve all predictions; do not expose label-bearing training cache to inference |
| 2 | Avoid repeated checkpoint hashing and unnecessary repeated reference-image audits after verified immutable input capture | Keep strong integrity checks and failure behavior; verify hashes at meaningful boundaries and record exactly which bytes produced predictions |
| 3 | Avoid full three-channel stacking for native class selection | Exact finite-value and tie behavior; benchmark memory/time and verify real-model outputs |
| 4 | Bounded CPU preprocessing/reconstruction overlap around serial model execution | Preserve result ordering, exception propagation, memory limits, and metric calculation; compare outputs exactly where arithmetic is unchanged |
| 5 | Batch 2.5D tiles across slices; evaluate device-side blending/transfer overlap | Measure real training-case probabilities and native mask disagreements; BF16 batch changes can change rounding, so use a new experiment identity |
| 6 | Explicit `checkpoint`, `preprocess`, `inference`, `reconstruction`, and `metrics` timing | Explain GPU gaps and record entire stage time, including hashing/export; keep instrumentation overhead separate from throughput |

The existing three-channel interpolation already improves the synthetic geometry benchmark from 3.807 s to 1.263 s with identical arrays. Training prefetch, compact transfers, mapped training cache, and tile batch 8 are also already enabled; they should not be presented as missing fixes.

Do not reduce validation cadence or change batch/spacing/model settings merely to raise utilization: those changes alter checkpoint selection or scientific comparison. A new implementation should be verified separately and used in a new campaign identity. There is no measured end-to-end speedup for the proposed pipeline changes yet.


## Source and measurement boundaries

Implementation references at the frozen commit: [preprocessing and tiled prediction](https://github.com/arianizadi/segmentary/blob/9f7615bd1f6035d65aca3f848a263b67c49f531f/src/segmentary/medical/torch_data.py), [training, validation and checkpoint status](https://github.com/arianizadi/segmentary/blob/9f7615bd1f6035d65aca3f848a263b67c49f531f/src/segmentary/medical/torch_backend.py), and [geometry auditing/export](https://github.com/arianizadi/segmentary/blob/9f7615bd1f6035d65aca3f848a263b67c49f531f/src/segmentary/medical/geometry.py).

The evidence JSON records sampling times, all 28 model rows, stage-timer limits, runtime versions, and source/script hashes. Raw process telemetry and diagnostic scripts remain in the local task's `work/performance-investigation-20260914` folder. Published records omit process IDs, CT filenames, raw images, labels, and model checkpoints. No live kernel timeline, cache implementation, pipeline overlap, or cross-slice batching was tested; those remain proposed follow-up experiments.
