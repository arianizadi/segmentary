# Concurrent campaign utilization audit

A 30-second observation found the training stages feeding their GPUs effectively: train-labeled samples averaged **98.1% GPU utilization**. Native validation remained the main observed source of GPU idle time, averaging **17.8% utilization** in validation-labeled samples. This short window does not establish that the entire campaign is free of bottlenecks.

## Measurement scope

- Window: 2026-09-13T23:25:29.039198+00:00 through 2026-09-13T23:25:59.049104+00:00 (UTC); 11 snapshots at 3-second intervals.
- Frozen campaign source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.
- Ten NVIDIA L40S GPUs hosted active campaign jobs. This window included training and validation; nnU-Net had already finished preprocessing and was using GPU 0 for training.
- GPU utilization and power came from the NVIDIA driver; CPU, RAM, page-fault, process I/O and pressure counters came from Linux `/proc`.
- Phase labels came from backend progress records. Driver utilization has its own sampling window, and either record may straddle a phase transition. Phase means are pooled snapshots, not exact timed fractions of each operation.
- No source, recipe, model weights, scheduling settings or running jobs were changed for this audit. This is performance evidence, not a model-quality comparison.

## All ten GPUs

The phase counts describe the 11 observations for each card. Memory is the maximum driver-reported used memory during this window, including allocator reservation and CUDA overhead; it differs from PyTorch peak allocated memory in isolated capacity tests.

| GPU | Model | Observed phase samples | Mean GPU utilization | Maximum used memory | Mean power |
|---:|---|---|---:|---:|---:|
| 0 | `nnunet_resenc_l` | train 11/11 | 98.5% | 20.73 GiB | 301.7 W |
| 1 | `umamba_enc` | validation 8/11; train 3/11 | 54.8% | 39.29 GiB | 187.8 W |
| 2 | `segmamba` | validation 1/11; train 10/11 | 90.8% | 23.16 GiB | 295.4 W |
| 3 | `umamba_bot` | train 11/11 | 99.1% | 19.10 GiB | 323.5 W |
| 4 | `swin_unetr` | train 11/11 | 99.7% | 37.93 GiB | 313.5 W |
| 5 | `unetr` | validation 11/11 | 9.5% | 7.89 GiB | 110.0 W |
| 6 | `transunet_3d` | train 11/11 | 90.0% | 12.62 GiB | 292.3 W |
| 7 | `medformer` | train 11/11 | 99.5% | 34.46 GiB | 301.7 W |
| 8 | `mednext_v1` | train 11/11 | 99.5% | 35.37 GiB | 293.2 W |
| 9 | `dynunet` | train 6/11; validation 5/11 | 57.3% | 11.00 GiB | 218.8 W |

Training contributed 85 labeled GPU samples; validation contributed 25. The low overall average on UNETR and mixed averages on U-MambaEnc/DynUNet coincided with native-volume validation rather than an unassigned GPU.

## CPU, memory, cache and storage

| Measurement | Observed value |
|---|---:|
| Logical CPUs | 256 |
| Host CPU busy fraction | 5.27% |
| Maximum runnable tasks | 18 |
| Maximum one-minute load average | 15.48 |
| Minimum available RAM | 711.91 GiB |
| CPU iowait fraction | 0.00052% |
| CPU pressure, some stalled tasks | 0.0240% of interval |
| I/O pressure, some stalled tasks | 0.0067% of interval |
| Memory pressure, some stalled tasks | 0.000007% of interval |
| Tracked jobs' major page faults | 0.00/s combined |
| Storage-device reads | 14.0 KiB/s |
| Storage-device writes | 90.3 MiB/s |
| Storage-device I/O-active fraction | 5.77% |

These observations show substantial host CPU/RAM headroom and no sustained storage or memory-pressure saturation during the sample. Most file reads were served without physical storage reads or major faults, consistent with the warm shared cache and Linux page cache. Minor page faults still occurred; they do not by themselves mean disk stalls.

Process rates cover surviving main-worker descendant processes. Exited/new subprocesses may be incompletely represented, and summing process RSS can count shared pages repeatedly. The available-RAM figure comes from the host-wide memory counters instead.

## Remaining cost: full native validation

The following values were read from the first completed epoch records, independently of the 30-second utilization window. Each listed Torch arm performed 100 optimizer updates followed by validation on the complete 42-case cohort.

| Model | Optimizer updates | Training time | Native validation time | Validation cases |
|---|---:|---:|---:|---:|
| `dynunet` | 100 | 23.4 s | 188.7 s | 42 |
| `medformer` | 100 | 79.1 s | 234.4 s | 42 |
| `mednext_v1` | 100 | 67.5 s | 225.3 s | 42 |
| `segmamba` | 100 | 135.3 s | 271.3 s | 42 |
| `swin_unetr` | 100 | 61.8 s | 221.4 s | 42 |
| `transunet_3d` | 100 | 27.2 s | 190.9 s | 42 |
| `umamba_bot` | 100 | 59.8 s | 217.0 s | 42 |
| `umamba_enc` | 100 | 148.1 s | 279.4 s | 42 |
| `unetr` | 100 | 18.5 s | 187.3 s | 42 |

These first validation passes took 187.3–279.4 seconds (3.1–4.7 minutes). Training and validation have different performance profiles: image resampling, native-space reconstruction and CPU array work can leave a GPU waiting even when the host has spare cores. This audit does not time those individual components separately.

The measured 1.94× gain from ordered batch prefetch applies to the separate warm-cache training-step experiment. It is not a 1.94× reduction in full experiment duration: validation, preprocessing, checkpoint writes and final evaluation remain. Current Torch recipes validate at epoch 1, every 10 epochs and the final epoch; the first-epoch table therefore overstates validation frequency relative to the full training schedule.

Further work could profile and overlap image-only preprocessing for successive validation cases with GPU inference. That would require separate numerical and provenance checks; this audit leaves the running comparison frozen.

## Separate hardware follow-up

A later point-in-time hardware check reported GPU temperatures of 38–68°C and no active software thermal slowdown, hardware thermal slowdown or hardware power-brake slowdown on any card. All ten power limits were 350 W. Software power-cap signals were active on seven cards at those configured limits; no power settings were changed. This was a separate snapshot, not a thermal history for the whole campaign.

## Evidence

- `concurrent-campaign-profile-20260913.json`: sanitized raw snapshots, counter deltas and summary.
- `concurrent-validation-timing-20260913.json`: sanitized timing fields extracted from committed first-epoch records.
- [Optimization investigation](optimization.md): isolated data-pipeline measurements, numerical checks and capacity profiles.

The numerical artifacts remain in the research artifact store. This report contains no patient identifiers, CT content, absolute server paths, process command lines or GPU UUIDs.
