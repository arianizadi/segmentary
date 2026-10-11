# denseaspp121 — rad_9_24_2026-fixed-grouped

[RAD 9/24: Scene-grouped split](../../README.md) · [Full model records](record.json)

Primary result: the **final checkpoint** after the full step budget (no early stopping). The checkpoint with the best **mud-pumping validation IoU, pixels pooled over all validation images**, is kept as secondary evidence. A job is complete only after full statistics and isolated profiling are verified.

Study metrics of the final checkpoint, counting each class only on the validation images that contain it: mud-pumping IoU is the mean per-image IoU over the images with mud-pumping, precision and recall sum pixels over those images, and mIoU averages each class over the images that contain it, then over the classes present.

| Initialization path | Seed | Mud-pumping IoU, train-camera images with mud (%, n=17) | Mud-pumping IoU, all images with mud (%, n=18) | Mud precision, all images with mud (%) | Mud recall, all images with mud (%) | mIoU (each class over images that contain it) (%) |
| --- | --- | --- | --- | --- | --- | --- |
| rtis_only | 0 | 10.14 | 9.85 | 46.18 | 15.49 | 37.53 |

Per-class IoU: IoU (%) of every class, each averaged only over the validation images that contain the class (n = those images); — = no image contains it. mIoU averages the classes with at least one such image.

| Initialization path | Seed | mIoU (each class over images that contain it) | person (n=0) | truck (n=0) | rail-track (n=37) | vegetation-overgrowth (n=13) | car (n=3) | on-rails (n=0) | traffic-sign (n=9) | road (n=11) | sidewalk (n=12) | construction (n=12) | tram-track (n=2) | pole (n=21) | traffic-light (n=3) | mud-pumping (n=18) | fence (n=7) | terrain (n=35) | sky (n=28) | rail-embedded (n=3) | rail-raised (n=37) | trackbed (n=37) | standing-water (n=9) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rtis_only | 0 | 37.53 | — | — | 57.50 | 33.20 | 25.31 | — | 20.95 | 10.20 | 10.67 | 34.23 | 19.05 | 63.77 | 34.99 | 9.85 | 29.52 | 83.46 | 94.47 | 10.89 | 69.36 | 62.24 | 5.89 |

Everything below is the campaign's own record, with pixels pooled over all validation images: its evaluation is the checkpoint that scored best on that pooled mud IoU (secondary evidence here); the diagnostics also cover the final checkpoint (`final-auto-val`).

| Model | Initialization path | Seed | Status | Steps | Best step | Best-checkpoint mud IoU, pixels pooled (%) | Best-checkpoint mud precision, pixels pooled (%) | Best-checkpoint mud recall, pixels pooled (%) | Final mud IoU (trainer val, pixels pooled, %) | Best-checkpoint mIoU, pixels pooled (%) | Best-checkpoint fixed GT-class mIoU, pixels pooled (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| denseaspp121 | rtis_only | 0 | completed | 4000 | 1296 | 7.80 | 9.42 | 31.21 | 5.57 | 30.96 | 36.12 |

Training: 217 images. Validation: 37 images. Test: 60 held out. Seeds: [0]. Seed variation measures optimization variability, not independent-recording uncertainty. Historical source checkpoints stay fixed across adaptation seeds.

Training code: `fce0ea0ac50b334d4252812c396e0e593def375d`. Split SHA-256: `12d7b367c72cda61d57686ff2ac28223530d0af49debd9fb7a0fbc68b908bc93`.

## rtis_only — seed 0

Status: **completed**. Started: 2026-10-10T22:04:17.415288+00:00. Finished: 2026-10-10T23:03:28.487769+00:00.

Recipe pretrained initializer: `timm densenet121.tv_in1k ImageNet backbone; fresh DenseASPP head`.

`rtis_only` uses the recipe initializer, which may include pretrained segmentation components. Transfer paths load the exact historical source checkpoint below and reset the classifier; they do not reset all query/decoder features.

Source checkpoint: `Recipe pretrained initialization`.

Config SHA-256: `f85ef449163a6324787ba29474af8b8a8e4fe58d50acbcf8645e882b190bb4b5`. Weights used for validation: `raw`.

### Mud-pumping and aggregate quality

| Metric | Selected checkpoint | Final training validation |
| --- | --- | --- |
| Mud IoU | 7.80 | 5.57 |
| Mud precision | 9.42 | 8.00 |
| Mud recall | 31.21 | 15.50 |
| Mud Dice/F1 | 14.47 | 10.56 |
| mIoU | 30.96 | 34.26 |
| Mean accuracy | 46.22 | 49.88 |
| Mean precision | 53.41 | 53.03 |
| Mean Dice | 40.67 | 44.93 |
| Mean specificity | 98.87 | 98.94 |
| Pixel accuracy | 81.53 | 82.92 |
| Frequency-weighted IoU | 72.45 | 73.84 |
| Fixed GT-present class mIoU | 36.12 | 39.97 |
| Boundary F1 | 36.26 | 39.41 |

The selected checkpoint has independent evaluation evidence. Final values are the trainer's final validation record, not a new independent evaluation. mIoU averages classes with nonzero union, so false positives on absent classes can change its denominator. The fixed GT-class mean is supplementary and excludes absent classes; their false positives remain in the confusion matrix.

### Resource usage and timing

| Measurement | Value |
| --- | --- |
| Peak training VRAM, retained training invocation (GiB) | 12.88 |
| Peak evaluation VRAM (GiB) | 6.64 |
| Retained training invocation wall time (seconds) | 3409.40 |
| Retained training invocation GPU-hours (one GPU) | 0.95 |
| Evaluation wall time (seconds) | 10.97 |
| Full evaluation pipeline images/second | 3.37 |
| Best full-state checkpoint (MiB) | 127.97 |
| Final full-state checkpoint (MiB) | 127.95 |
| Verified periodic checkpoints removed (GiB) | 1.00 |

VRAM uses the recorded allocator high-water mark; it is not total device usage including CUDA context. Resumed jobs' retained training invocation times and peaks are **not whole-campaign totals**. Earlier invocation resource records are not reconstructed here. Evaluation throughput includes loader, sliding-window inference and metrics; it is not model-only latency/FPS. Missing measurements are shown as —, never inferred from another dataset's run.

### Standardized inference performance

Dedicated model-only profiling waits for an idle worker-locked L40S: BF16, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed public forwards. It excludes loading, preprocessing, tiling and metrics.

| Status | Parameters | Weight MiB | FPS | p50 ms | p95 ms | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- |
| complete | 8282517 | 31.60 | 99.90 | 9.98 | 10.25 | 0.38 |

```json
{
  "schema_version": 1,
  "model_id": "denseaspp121",
  "measured_at": "2026-10-10T23:03:26+00:00",
  "status": "complete",
  "benchmark_scope": "rtis_selected_checkpoint_model_only",
  "applies_to": [
    "denseaspp121--rtis_only--seed-0"
  ],
  "source": {
    "campaign_git_sha": "fce0ea0ac50b334d4252812c396e0e593def375d",
    "git_dirty": false,
    "config_hash": "65b40ceb753b",
    "resolved_config": "/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fgall-seed0-20261007/configs/denseaspp121--rtis_only--seed-0.yaml",
    "config_sha256": "f85ef449163a6324787ba29474af8b8a8e4fe58d50acbcf8645e882b190bb4b5",
    "checkpoint_sha256": "9c85e1c55ebd70eb0fbee843256b6593fce9f39a3602b09d27454df50b20586b",
    "checkpoint_global_step": 1296,
    "checkpoint_bytes": 134190682,
    "checkpoint_kind": "resume checkpoint with optimizer and EMA state",
    "weights": "raw",
    "measured_checkpoint_job_id": "denseaspp121--rtis_only--seed-0",
    "result_sha256": "60a225d448e4430d5d19b225f4fc40067abef356d9dbe17a4ada011a309c5ef0",
    "result_git_sha": "fce0ea0ac50b334d4252812c396e0e593def375d",
    "result_stage": "eval:rad_9_24_2026-fixed-grouped:val",
    "result_seed": 0
  },
  "hardware": {
    "gpu_name": "NVIDIA L40S",
    "gpu_uuid": "GPU-931d0911-fc78-1638-e3d7-1ba868cbd286",
    "logical_device": "cuda:0",
    "physical_visibility_token": "2",
    "compute_capability": [
      8,
      9
    ],
    "total_memory_bytes": 47677177856
  },
  "model": {
    "parameter_count": 8282517,
    "trainable_parameter_count": 8282517,
    "resident_parameter_bytes": 33130068,
    "parameter_dtype_counts": {
      "float32": 8282517
    }
  },
  "contract": {
    "backend": "pytorch",
    "precision": "bf16_autocast",
    "batch_size": 1,
    "input_shape_nchw": [
      1,
      3,
      1024,
      1024
    ],
    "warmup_iterations": 20,
    "measured_iterations": 100,
    "timing": "per-forward CUDA events with end-event synchronization",
    "includes_preprocessing": false,
    "includes_data_loader": false,
    "includes_sliding_window": false,
    "input_resident_on_gpu": true,
    "model_only": true,
    "entrypoint": "public model(image) dense-logits forward"
  },
  "measurements": {
    "latency": {
      "p50_ms": 9.981391906738281,
      "p95_ms": 10.249316596984864,
      "mean_ms": 10.010046405792236,
      "minimum_ms": 9.864192008972168,
      "maximum_ms": 10.498047828674316,
      "fps": 99.8996367710501,
      "raw_ms": [
        10.064895629882812,
        9.994367599487305,
        9.986047744750977,
        9.987071990966797,
        9.985024452209473,
        9.946111679077148,
        9.952256202697754,
        9.884672164916992,
        10.019840240478516,
        10.049535751342773,
        10.011648178100586,
        9.883647918701172,
        9.890815734863281,
        9.907103538513184,
        9.911295890808105,
        10.063872337341309,
        9.974783897399902,
        9.995264053344727,
        9.996288299560547,
        9.919487953186035,
        9.954303741455078,
        10.010623931884766,
        9.995264053344727,
        9.920512199401855,
        10.144864082336426,
        9.993215560913086,
        10.43455982208252,
        9.973759651184082,
        10.244095802307129,
        9.875455856323242,
        9.999360084533691,
        10.160127639770508,
        9.93075180053711,
        10.091520309448242,
        9.942015647888184,
        9.926655769348145,
        10.016768455505371,
        9.94918441772461,
        10.012703895568848,
        10.087424278259277,
        9.943039894104004,
        9.920448303222656,
        10.03212833404541,
        9.966591835021973,
        9.94099235534668,
        10.133503913879395,
        9.918463706970215,
        10.178496360778809,
        9.979904174804688,
        9.952256202697754,
        9.954303741455078,
        9.921536445617676,
        9.960448265075684,
        9.933823585510254,
        10.033151626586914,
        9.936896324157715,
        9.981951713562012,
        10.095552444458008,
        9.901056289672852,
        9.914400100708008,
        9.978879928588867,
        10.080256462097168,
        9.92460823059082,
        9.864192008972168,
        9.886719703674316,
        9.943936347961426,
        9.936896324157715,
        10.073087692260742,
        10.066944122314453,
        10.073087692260742,
        10.056703567504883,
        9.878527641296387,
        9.918463706970215,
        9.905152320861816,
        9.927647590637207,
        10.02086353302002,
        10.0065279006958,
        10.378335952758789,
        10.116095542907715,
        9.901056289672852,
        10.037247657775879,
        10.027008056640625,
        10.348511695861816,
        9.912320137023926,
        9.987071990966797,
        9.97481632232666,
        10.072064399719238,
        10.055680274963379,
        10.025983810424805,
        10.119168281555176,
        9.94918441772461,
        10.167263984680176,
        9.918463706970215,
        9.98083209991455,
        10.106752395629883,
        9.924511909484863,
        10.488832473754883,
        10.498047828674316,
        9.905152320861816,
        9.881600379943848
      ],
      "percentile_method": "numpy linear interpolation"
    },
    "peak_reserved_bytes": 408944640,
    "memory_kind": "pytorch_cuda_allocator_peak_reserved_excluding_context",
    "process_total_bytes": 937426944,
    "process_total_kind": "nvidia-smi used_memory of this PID on the benchmark GPU after the timed loop, including the CUDA context; null when the driver could not attribute memory to this PID",
    "benchmark_wall_clock_s": 19.191278100013733
  },
  "started_at": "2026-10-10T23:03:06+00:00",
  "finished_at": "2026-10-10T23:03:26+00:00",
  "environment": {
    "hostname": "hdrfs-app-001",
    "python": "3.11.15",
    "platform": "Linux-5.15.0-139-generic-x86_64-with-glibc2.35",
    "torch": "2.11.0+cu128",
    "torch_cuda": "12.8",
    "cudnn": 91900,
    "driver_version": "570.133.20",
    "cuda_available": true,
    "gpu_count": 1,
    "gpu_names": [
      "NVIDIA L40S"
    ],
    "cuda_visible_devices": "2",
    "packages": {
      "segmentary": "0.1.0",
      "torch": "2.11.0+cu128",
      "torchvision": "0.26.0+cu128",
      "transformers": "5.15.0",
      "timm": "1.0.28",
      "segmentation-models-pytorch": "0.5.0",
      "albumentations": "2.0.8",
      "lightning": "2.6.5",
      "numpy": "2.4.4"
    }
  }
}
```

### Per-class validation results

| Class | GT pixels | IoU (%) | Precision (%) | Recall (%) | Dice (%) | Boundary F1 (%) |
| --- | --- | --- | --- | --- | --- | --- |
| car | 29664 | 53.07 | 79.91 | 61.24 | 69.34 | 58.79 |
| construction | 311585 | 19.09 | 21.47 | 63.25 | 32.06 | 33.10 |
| fence | 265137 | 30.62 | 45.03 | 48.90 | 46.89 | 41.52 |
| mud-pumping | 1226250 | 7.80 | 9.42 | 31.21 | 14.47 | 10.92 |
| on-rails | 0 | 0.00 | 0.00 | — | 0.00 | 0.00 |
| person | 0 | 0.00 | 0.00 | — | 0.00 | 0.00 |
| pole | 628038 | 62.07 | 81.61 | 72.16 | 76.59 | 85.09 |
| rail-embedded | 16799 | 14.77 | 61.18 | 16.29 | 25.73 | 23.90 |
| rail-raised | 2969797 | 72.22 | 79.92 | 88.23 | 83.87 | 85.79 |
| rail-track | 6323197 | 32.88 | 78.01 | 36.24 | 49.49 | 48.32 |
| road | 1048831 | 5.68 | 12.87 | 9.23 | 10.75 | 8.06 |
| sidewalk | 1297367 | 35.74 | 61.67 | 45.95 | 52.66 | 16.99 |
| sky | 19121606 | 96.13 | 99.21 | 96.87 | 98.03 | 80.08 |
| standing-water | 95802 | 2.31 | 2.93 | 9.91 | 4.52 | 4.97 |
| terrain | 39239306 | 85.57 | 88.01 | 96.86 | 92.22 | 54.66 |
| trackbed | 10643081 | 57.10 | 69.08 | 76.70 | 72.69 | 50.10 |
| traffic-light | 19510 | 9.45 | 88.81 | 9.56 | 17.27 | 38.68 |
| traffic-sign | 13285 | 23.96 | 84.11 | 25.10 | 38.66 | 43.82 |
| tram-track | 56179 | 21.59 | 70.76 | 23.71 | 35.52 | 20.31 |
| truck | 0 | 0.00 | 0.00 | — | 0.00 | 0.00 |
| vegetation-overgrowth | 5901821 | 20.04 | 87.66 | 20.62 | 33.39 | 56.41 |

### Full-run accounting

| Measurement | Value |
| --- | --- |
| Full GPU-reserved wall seconds, all recorded worker attempts | 3562.94 |
| Full reserved GPU-hours | 0.99 |
| Whole-run timing complete | True |

| Phase | Wall seconds including failed attempts |
| --- | --- |
| training | 3415.50 |
| diagnostics | 89.62 |
| performance | 26.50 |

GPU-reserved time includes model loading, training, validation, collection, profiling, checkpoint I/O and orchestration while the worker owns one GPU. It is not GPU kernel-active time. Phase timings and sampled device memory/power/utilization are retained separately; sampled device memory is not the allocator high-water mark.

### Train/validation and raw/EMA diagnostics

| Checkpoint / weights / split | Images | Mud IoU (%) | Mud precision (%) | Mud recall (%) |
| --- | --- | --- | --- | --- |
| best-auto-train / raw | 217 | 92.78 | 95.76 | 96.76 |
| best-auto-val / raw | 37 | 7.80 | 9.42 | 31.21 |
| best-alternate-val / ema | 37 | 2.75 | 3.25 | 15.10 |
| final-auto-val / raw | 37 | 5.57 | 8.00 | 15.49 |

Train uses the evaluation transform without augmentation. Compare mud train/validation metrics for the same selected weights. Alternate EMA on running-stat BatchNorm is explicitly uncalibrated and is diagnostic only. Score-threshold curves use uncalibrated normalized scores and are pixel-level diagnostics, not event detection rates or a selected deployment operating point.

### Downloadable evidence

- best-auto-train: [per-image.csv](rtis_only--seed-0/best-auto-train/per-image.csv) · [per-image-confusion.json.gz](rtis_only--seed-0/best-auto-train/per-image-confusion.json.gz) · [groups.json](rtis_only--seed-0/best-auto-train/groups.json) · [mud-score-curves.json](rtis_only--seed-0/best-auto-train/mud-score-curves.json)
- best-auto-val: [per-image.csv](rtis_only--seed-0/best-auto-val/per-image.csv) · [per-image-confusion.json.gz](rtis_only--seed-0/best-auto-val/per-image-confusion.json.gz) · [groups.json](rtis_only--seed-0/best-auto-val/groups.json) · [mud-score-curves.json](rtis_only--seed-0/best-auto-val/mud-score-curves.json) · [examples.jpg](rtis_only--seed-0/best-auto-val/examples.jpg)
- best-alternate-val: [per-image.csv](rtis_only--seed-0/best-alternate-val/per-image.csv) · [per-image-confusion.json.gz](rtis_only--seed-0/best-alternate-val/per-image-confusion.json.gz) · [groups.json](rtis_only--seed-0/best-alternate-val/groups.json) · [mud-score-curves.json](rtis_only--seed-0/best-alternate-val/mud-score-curves.json)
- final-auto-val: [per-image.csv](rtis_only--seed-0/final-auto-val/per-image.csv) · [per-image-confusion.json.gz](rtis_only--seed-0/final-auto-val/per-image-confusion.json.gz) · [groups.json](rtis_only--seed-0/final-auto-val/groups.json) · [mud-score-curves.json](rtis_only--seed-0/final-auto-val/mud-score-curves.json)
- resources: [telemetry.csv](rtis_only--seed-0/resources/telemetry.csv)

![Selected-checkpoint validation examples](rtis_only--seed-0/best-auto-val/examples.jpg)

Examples are two lowest and two highest mud-IoU positive images, plus up to two negative images with the most false-positive mud pixels. They are targeted diagnostic examples, not random samples. Green: true positive; red: false positive; yellow: false negative. Full predictions remain on HDRFS.

### Validation tracking

| Logged step | Overall mIoU (%) | Mud IoU (%) |
| --- | --- | --- |
| 258 | 19.41 | 3.79 |
| 518 | 24.95 | 0.46 |
| 777 | 28.79 | 0.61 |
| 1036 | 29.86 | 3.61 |
| 1295 | 30.96 | 7.81 |
| 1555 | 30.83 | 4.97 |
| 1814 | 33.96 | 3.65 |
| 2073 | 31.56 | 2.93 |
| 2332 | 33.04 | 2.81 |
| 2592 | 32.22 | 3.69 |
| 2851 | 32.90 | 1.69 |
| 3110 | 32.02 | 2.69 |
| 3369 | 32.05 | 2.27 |
| 3629 | 30.59 | 2.46 |
| 3888 | 33.60 | 3.49 |
| 4000 | 34.26 | 5.57 |

All retained scalar curves, including training loss and per-class IoU, are in record.json. Observed best mud on a curve is not necessarily a retained checkpoint: the pilot saved its selection-metric-best and final checkpoints. Step logging and checkpoint global_step may differ by one.

### Stopping and checkpoint provenance

```json
{
  "stopping": {
    "actual_steps": 4000,
    "maximum_steps": 4000,
    "min_delta": 0.0,
    "monitor": "val_iou/mud-pumping",
    "patience": null,
    "reason": "budget_complete"
  },
  "checkpoints": {
    "best": {
      "path": "/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fgall-seed0-20261007/future-runs/denseaspp121--rtis_only--seed-0_seed0/rtis/best.ckpt",
      "sha256": "9c85e1c55ebd70eb0fbee843256b6593fce9f39a3602b09d27454df50b20586b",
      "global_step": 1296,
      "bytes": 134190682
    },
    "final": {
      "path": "/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fgall-seed0-20261007/future-runs/denseaspp121--rtis_only--seed-0_seed0/rtis/last.ckpt",
      "sha256": "95155f4abaf5a039bb52e4e52181d6c8d472cc9948cac60162407eda20aaa1ac",
      "global_step": 4000,
      "bytes": 134164570
    }
  },
  "cleanup_error": null
}
```

### Resolved training, initialization and evaluation settings

The optimizer block is the base configuration. Stage LR scales are applied at runtime, and stage warmup is capped at min(base warmup, floor(stage budget / 10), stage budget - 1): 400 steps for this 4,000-step pilot. Model-internal native input grids may differ from augmentation crops (EoMT uses its 640 grid).

```json
{
  "name": "denseaspp121--rtis_only--seed-0",
  "model": {
    "arch": "denseaspp121",
    "checkpoint": null,
    "tuning": "full",
    "head": "unified_head",
    "lora_r": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.05,
    "lora_targets": [],
    "drop_path": null,
    "revision": null,
    "subfolder": null,
    "local_files_only": false,
    "trust_remote_code": false,
    "backbone_path": null,
    "head_paths": [],
    "classifier_path": null,
    "inactive_parameter_paths": [],
    "smp_arch": null,
    "encoder_name": null,
    "encoder_weights": null,
    "native": null,
    "batch_norm_momentum": null
  },
  "space": "paul-test-rtis",
  "taxonomy_root": "/data/izadia1/projects/segmentary-rad-fgall-fce0ea0a/taxonomy",
  "output_root": "/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fgall-seed0-20261007/future-runs",
  "optim": {
    "backbone_lr": 0.0001,
    "head_lr_mult": 10.0,
    "weight_decay": 0.05,
    "llrd": 1.0,
    "warmup_iters": 1500,
    "warmup_ratio": 1e-06,
    "poly_power": 0.9,
    "min_lr_ratio": 0.0,
    "betas": [
      0.9,
      0.999
    ],
    "grad_clip": 1.0
  },
  "train": {
    "iters": 4000,
    "batch_size": 2,
    "accum": 8,
    "num_workers": 2,
    "precision": "bf16-mixed",
    "ema_decay": 0.9998,
    "val_every": 250,
    "ckpt_every": 500,
    "selection_metric": "val_iou/mud-pumping",
    "early_stopping_patience": null,
    "early_stopping_min_delta": 0.0,
    "seed": 0,
    "devices": 1
  },
  "eval": {
    "sliding_window": true,
    "window": [
      1024,
      1024
    ],
    "stride": [
      768,
      768
    ],
    "batch_size": 1,
    "num_workers": 2,
    "tta_scales": [],
    "tta_flip": false,
    "threshold": 0.5,
    "boundary_tolerance_frac": 0.0075,
    "save_confusion": true
  },
  "loss": {
    "task": "multiclass",
    "activation": "auto",
    "terms": [],
    "aux": "none",
    "aux_weight": 0.0,
    "ce_weight": 1.0,
    "label_smoothing": 0.0,
    "class_weights": null,
    "query": null
  },
  "aug": {
    "crop": [
      1024,
      1024
    ],
    "scale_min": 0.5,
    "scale_max": 2.0,
    "hflip_p": 0.5,
    "color_jitter_p": 0.5,
    "brightness": 0.25,
    "contrast": 0.25,
    "saturation": 0.25,
    "hue": 0.05
  },
  "stages": [
    {
      "name": "rtis",
      "data": [
        {
          "name": "rad_9_24_2026-fixed-grouped",
          "root": "/data/izadia1/datasets/rad_9_24_2026-fixed-grouped",
          "variant": null,
          "split_file": "splits.json",
          "train_split": "train",
          "val_split": "val",
          "limit": null,
          "loader": "folder",
          "mapping": "paul-test-rtis",
          "loader_options": {
            "require_groups": true
          }
        }
      ],
      "iters": null,
      "lr_scale": 1.0,
      "head_group_lr_scale": 1.0,
      "init_from": "pretrained",
      "reset_head": false,
      "freeze": null,
      "sample_weights": null
    }
  ]
}
```

### Hardware and software provenance

```json
{
  "training": {
    "cuda_available": true,
    "cuda_visible_devices": "2",
    "cudnn": 91900,
    "driver_version": "570.133.20",
    "gpu_count": 1,
    "gpu_names": [
      "NVIDIA L40S"
    ],
    "hostname": "hdrfs-app-001",
    "input_normalization": {
      "channel_order": "rgb",
      "mean": [
        0.485,
        0.456,
        0.406
      ],
      "source": "timm_pretrained_cfg",
      "std": [
        0.229,
        0.224,
        0.225
      ]
    },
    "model_origins": [],
    "model_parameter_count": 8282517,
    "packages": {
      "albumentations": "2.0.8",
      "lightning": "2.6.5",
      "numpy": "2.4.4",
      "segmentary": "0.1.0",
      "segmentation-models-pytorch": "0.5.0",
      "timm": "1.0.28",
      "torch": "2.11.0+cu128",
      "torchvision": "0.26.0+cu128",
      "transformers": "5.15.0"
    },
    "platform": "Linux-5.15.0-139-generic-x86_64-with-glibc2.35",
    "python": "3.11.15",
    "torch": "2.11.0+cu128",
    "torch_cuda": "12.8",
    "trainable_parameter_count": 8282517,
    "training_stop": {
      "actual_steps": 4000,
      "maximum_steps": 4000,
      "min_delta": 0.0,
      "monitor": "val_iou/mud-pumping",
      "patience": null,
      "reason": "budget_complete"
    },
    "validation_weights": "raw"
  },
  "evaluation": {
    "cuda_available": true,
    "cuda_visible_devices": "2",
    "cudnn": 91900,
    "driver_version": "570.133.20",
    "gpu_count": 1,
    "gpu_names": [
      "NVIDIA L40S"
    ],
    "hostname": "hdrfs-app-001",
    "input_normalization": {
      "channel_order": "rgb",
      "mean": [
        0.485,
        0.456,
        0.406
      ],
      "source": "timm_pretrained_cfg",
      "std": [
        0.229,
        0.224,
        0.225
      ]
    },
    "packages": {
      "albumentations": "2.0.8",
      "lightning": "2.6.5",
      "numpy": "2.4.4",
      "segmentary": "0.1.0",
      "segmentation-models-pytorch": "0.5.0",
      "timm": "1.0.28",
      "torch": "2.11.0+cu128",
      "torchvision": "0.26.0+cu128",
      "transformers": "5.15.0"
    },
    "platform": "Linux-5.15.0-139-generic-x86_64-with-glibc2.35",
    "python": "3.11.15",
    "torch": "2.11.0+cu128",
    "torch_cuda": "12.8"
  }
}
```
