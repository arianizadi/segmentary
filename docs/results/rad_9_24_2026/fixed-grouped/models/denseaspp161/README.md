# denseaspp161 — rad_9_24_2026-fixed-grouped

[RAD 9/24: Scene-grouped split](../../README.md) · [Full model records](record.json)

Primary result: the **final checkpoint** after the full step budget (no early stopping). The checkpoint with the best **mud-pumping validation IoU, pixels pooled over all validation images**, is kept as secondary evidence. A job is complete only after full statistics and isolated profiling are verified.

Study metrics of the final checkpoint, counting each class only on the validation images that contain it: mud-pumping IoU is the mean per-image IoU over the images with mud-pumping, precision and recall sum pixels over those images, and mIoU averages each class over the images that contain it, then over the classes present.

| Initialization path | Seed | Mud-pumping IoU, train-camera images with mud (%, n=17) | Mud-pumping IoU, all images with mud (%, n=18) | Mud precision, all images with mud (%) | Mud recall, all images with mud (%) | mIoU (each class over images that contain it) (%) |
| --- | --- | --- | --- | --- | --- | --- |
| rtis_only | 0 | 3.09 | 3.02 | 12.55 | 3.96 | 36.09 |

Per-class IoU: IoU (%) of every class, each averaged only over the validation images that contain the class (n = those images); — = no image contains it. mIoU averages the classes with at least one such image.

| Initialization path | Seed | mIoU (each class over images that contain it) | person (n=0) | truck (n=0) | rail-track (n=37) | vegetation-overgrowth (n=13) | car (n=3) | on-rails (n=0) | traffic-sign (n=9) | road (n=11) | sidewalk (n=12) | construction (n=12) | tram-track (n=2) | pole (n=21) | traffic-light (n=3) | mud-pumping (n=18) | fence (n=7) | terrain (n=35) | sky (n=28) | rail-embedded (n=3) | rail-raised (n=37) | trackbed (n=37) | standing-water (n=9) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rtis_only | 0 | 36.09 | — | — | 56.80 | 29.13 | 19.06 | — | 30.76 | 6.33 | 13.11 | 46.78 | 19.17 | 67.44 | 29.41 | 3.02 | 11.06 | 82.33 | 94.22 | 4.34 | 71.90 | 63.35 | 1.52 |

Everything below is the campaign's own record, with pixels pooled over all validation images: its evaluation is the checkpoint that scored best on that pooled mud IoU (secondary evidence here); the diagnostics also cover the final checkpoint (`final-auto-val`).

| Model | Initialization path | Seed | Status | Steps | Best step | Best-checkpoint mud IoU, pixels pooled (%) | Best-checkpoint mud precision, pixels pooled (%) | Best-checkpoint mud recall, pixels pooled (%) | Final mud IoU (trainer val, pixels pooled, %) | Best-checkpoint mIoU, pixels pooled (%) | Best-checkpoint fixed GT-class mIoU, pixels pooled (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| denseaspp161 | rtis_only | 0 | completed | 4000 | 1296 | 6.00 | 22.68 | 7.55 | 1.21 | 30.86 | 36.00 |

Training: 217 images. Validation: 37 images. Test: 60 held out. Seeds: [0]. Seed variation measures optimization variability, not independent-recording uncertainty. Historical source checkpoints stay fixed across adaptation seeds.

Training code: `fce0ea0ac50b334d4252812c396e0e593def375d`. Split SHA-256: `12d7b367c72cda61d57686ff2ac28223530d0af49debd9fb7a0fbc68b908bc93`.

## rtis_only — seed 0

Status: **completed**. Started: 2026-10-10T22:04:17.351814+00:00. Finished: 2026-10-11T00:24:56.859110+00:00.

Recipe pretrained initializer: `timm densenet161.tv_in1k ImageNet backbone; fresh DenseASPP head`.

`rtis_only` uses the recipe initializer, which may include pretrained segmentation components. Transfer paths load the exact historical source checkpoint below and reset the classifier; they do not reset all query/decoder features.

Source checkpoint: `Recipe pretrained initialization`.

Config SHA-256: `51ebae9eda87d82166ff801a499d52af06902d7607179f49ac38c942abb0d215`. Weights used for validation: `raw`.

### Mud-pumping and aggregate quality

| Metric | Selected checkpoint | Final training validation |
| --- | --- | --- |
| Mud IoU | 6.00 | 1.21 |
| Mud precision | 22.68 | 1.71 |
| Mud recall | 7.55 | 3.96 |
| Mud Dice/F1 | 11.33 | 2.39 |
| mIoU | 30.86 | 33.05 |
| Mean accuracy | 44.38 | 46.29 |
| Mean precision | 53.09 | 53.90 |
| Mean Dice | 40.06 | 42.81 |
| Mean specificity | 98.83 | 98.89 |
| Pixel accuracy | 82.72 | 82.77 |
| Frequency-weighted IoU | 71.71 | 73.38 |
| Fixed GT-present class mIoU | 36.00 | 38.55 |
| Boundary F1 | 37.04 | 38.91 |

The selected checkpoint has independent evaluation evidence. Final values are the trainer's final validation record, not a new independent evaluation. mIoU averages classes with nonzero union, so false positives on absent classes can change its denominator. The fixed GT-class mean is supplementary and excludes absent classes; their false positives remain in the confusion matrix.

### Resource usage and timing

| Measurement | Value |
| --- | --- |
| Peak training VRAM, retained training invocation (GiB) | 23.73 |
| Peak evaluation VRAM (GiB) | 8.07 |
| Retained training invocation wall time (seconds) | 8223.21 |
| Retained training invocation GPU-hours (one GPU) | 2.28 |
| Evaluation wall time (seconds) | 16.54 |
| Full evaluation pipeline images/second | 2.24 |
| Best full-state checkpoint (MiB) | 543.13 |
| Final full-state checkpoint (MiB) | 543.10 |
| Verified periodic checkpoints removed (GiB) | 4.24 |

VRAM uses the recorded allocator high-water mark; it is not total device usage including CUDA context. Resumed jobs' retained training invocation times and peaks are **not whole-campaign totals**. Earlier invocation resource records are not reconstructed here. Evaluation throughput includes loader, sliding-window inference and metrics; it is not model-only latency/FPS. Missing measurements are shown as —, never inferred from another dataset's run.

### Standardized inference performance

Dedicated model-only profiling waits for an idle worker-locked L40S: BF16, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed public forwards. It excludes loading, preprocessing, tiling and metrics.

| Status | Parameters | Weight MiB | FPS | p50 ms | p95 ms | Peak reserved GiB |
| --- | --- | --- | --- | --- | --- | --- |
| complete | 35398917 | 135.04 | 34.62 | 28.89 | 28.93 | 1.24 |

```json
{
  "schema_version": 1,
  "model_id": "denseaspp161",
  "measured_at": "2026-10-11T00:24:50+00:00",
  "status": "complete",
  "benchmark_scope": "rtis_selected_checkpoint_model_only",
  "applies_to": [
    "denseaspp161--rtis_only--seed-0"
  ],
  "source": {
    "campaign_git_sha": "fce0ea0ac50b334d4252812c396e0e593def375d",
    "git_dirty": false,
    "config_hash": "ad61d27e64b7",
    "resolved_config": "/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fgall-seed0-20261007/configs/denseaspp161--rtis_only--seed-0.yaml",
    "config_sha256": "51ebae9eda87d82166ff801a499d52af06902d7607179f49ac38c942abb0d215",
    "checkpoint_sha256": "6462963d26271d3ec60456745eda91268fd2062215c33bc8bb176be00a884f57",
    "checkpoint_global_step": 1296,
    "checkpoint_bytes": 569515666,
    "checkpoint_kind": "resume checkpoint with optimizer and EMA state",
    "weights": "raw",
    "measured_checkpoint_job_id": "denseaspp161--rtis_only--seed-0",
    "result_sha256": "9204cfc8201db4658e1ecd86caaf25fd5414ef56e8ef78a31df01f7b83b9718f",
    "result_git_sha": "fce0ea0ac50b334d4252812c396e0e593def375d",
    "result_stage": "eval:rad_9_24_2026-fixed-grouped:val",
    "result_seed": 0
  },
  "hardware": {
    "gpu_name": "NVIDIA L40S",
    "gpu_uuid": "GPU-a5ad49e5-0536-5229-ba8a-f8a902808f53",
    "logical_device": "cuda:0",
    "physical_visibility_token": "7",
    "compute_capability": [
      8,
      9
    ],
    "total_memory_bytes": 47677177856
  },
  "model": {
    "parameter_count": 35398917,
    "trainable_parameter_count": 35398917,
    "resident_parameter_bytes": 141595668,
    "parameter_dtype_counts": {
      "float32": 35398917
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
      "p50_ms": 28.887039184570312,
      "p95_ms": 28.929586982727052,
      "mean_ms": 28.888534297943114,
      "minimum_ms": 28.833759307861328,
      "maximum_ms": 29.087743759155273,
      "fps": 34.615809500283326,
      "raw_ms": [
        28.913663864135742,
        28.895231246948242,
        28.891136169433594,
        28.862464904785156,
        28.9116153717041,
        28.880895614624023,
        28.877824783325195,
        28.872703552246094,
        28.866559982299805,
        28.898303985595703,
        28.872703552246094,
        28.864511489868164,
        28.875776290893555,
        28.865535736083984,
        28.865535736083984,
        28.872703552246094,
        28.903423309326172,
        28.860416412353516,
        28.849151611328125,
        28.9484806060791,
        28.9116153717041,
        28.95667266845703,
        28.873727798461914,
        28.903423309326172,
        28.892160415649414,
        28.866559982299805,
        28.846080780029297,
        28.833759307861328,
        28.852224349975586,
        28.865503311157227,
        28.881919860839844,
        28.876800537109375,
        28.893184661865234,
        28.9116153717041,
        28.881919860839844,
        28.852224349975586,
        28.884992599487305,
        28.849151611328125,
        28.873727798461914,
        28.881919860839844,
        28.839935302734375,
        28.905471801757812,
        28.878847122192383,
        28.95052719116211,
        28.888063430786133,
        28.859392166137695,
        28.88092803955078,
        28.865535736083984,
        28.861440658569336,
        28.873727798461914,
        29.087743759155273,
        28.893152236938477,
        28.887039184570312,
        28.905471801757812,
        28.873727798461914,
        28.887039184570312,
        28.906496047973633,
        28.880895614624023,
        28.848127365112305,
        28.890111923217773,
        28.888063430786133,
        28.886016845703125,
        28.863487243652344,
        28.893184661865234,
        28.901376724243164,
        28.891136169433594,
        28.867584228515625,
        28.890111923217773,
        28.891136169433594,
        28.862464904785156,
        28.887039184570312,
        28.871679306030273,
        28.900352478027344,
        28.925952911376953,
        28.914688110351562,
        28.940288543701172,
        28.879871368408203,
        28.887039184570312,
        28.901376724243164,
        28.889087677001953,
        28.880895614624023,
        28.91059112548828,
        28.894208908081055,
        28.890111923217773,
        28.887039184570312,
        28.921855926513672,
        28.913663864135742,
        28.864511489868164,
        28.891136169433594,
        28.889087677001953,
        28.891136169433594,
        28.895231246948242,
        28.92902374267578,
        28.903423309326172,
        28.893184661865234,
        28.896255493164062,
        28.880895614624023,
        28.915712356567383,
        28.892160415649414,
        28.879871368408203
      ],
      "percentile_method": "numpy linear interpolation"
    },
    "peak_reserved_bytes": 1329594368,
    "memory_kind": "pytorch_cuda_allocator_peak_reserved_excluding_context",
    "process_total_bytes": 1858076672,
    "process_total_kind": "nvidia-smi used_memory of this PID on the benchmark GPU after the timed loop, including the CUDA context; null when the driver could not attribute memory to this PID",
    "benchmark_wall_clock_s": 28.48033981770277
  },
  "started_at": "2026-10-11T00:24:21+00:00",
  "finished_at": "2026-10-11T00:24:50+00:00",
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
    "cuda_visible_devices": "7",
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
| car | 29664 | 8.43 | 37.51 | 9.81 | 15.55 | 37.28 |
| construction | 311585 | 32.10 | 37.68 | 68.46 | 48.60 | 30.16 |
| fence | 265137 | 19.85 | 40.67 | 27.93 | 33.12 | 35.87 |
| mud-pumping | 1226250 | 6.00 | 22.68 | 7.55 | 11.33 | 9.98 |
| on-rails | 0 | 0.00 | 0.00 | — | 0.00 | 0.00 |
| person | 0 | 0.00 | 0.00 | — | 0.00 | 0.00 |
| pole | 628038 | 66.97 | 77.11 | 83.60 | 80.22 | 87.50 |
| rail-embedded | 16799 | 2.79 | 100.00 | 2.79 | 5.43 | 10.39 |
| rail-raised | 2969797 | 76.45 | 82.42 | 91.33 | 86.65 | 90.01 |
| rail-track | 6323197 | 36.81 | 77.71 | 41.15 | 53.81 | 47.51 |
| road | 1048831 | 2.44 | 8.82 | 3.26 | 4.76 | 6.33 |
| sidewalk | 1297367 | 21.34 | 68.13 | 23.71 | 35.17 | 12.31 |
| sky | 19121606 | 96.08 | 99.44 | 96.61 | 98.00 | 86.22 |
| standing-water | 95802 | 1.38 | 1.61 | 8.73 | 2.72 | 8.03 |
| terrain | 39239306 | 81.71 | 83.85 | 96.96 | 89.93 | 45.62 |
| trackbed | 10643081 | 61.45 | 68.29 | 85.99 | 76.13 | 55.46 |
| traffic-light | 19510 | 36.65 | 76.62 | 41.27 | 53.65 | 56.36 |
| traffic-sign | 13285 | 39.13 | 70.20 | 46.93 | 56.25 | 63.29 |
| tram-track | 56179 | 34.56 | 83.45 | 37.10 | 51.37 | 33.47 |
| truck | 0 | 0.00 | 0.00 | — | 0.00 | 0.00 |
| vegetation-overgrowth | 5901821 | 23.93 | 78.77 | 25.58 | 38.62 | 61.98 |

### Full-run accounting

| Measurement | Value |
| --- | --- |
| Full GPU-reserved wall seconds, all recorded worker attempts | 8451.30 |
| Full reserved GPU-hours | 2.35 |
| Whole-run timing complete | True |

| Phase | Wall seconds including failed attempts |
| --- | --- |
| training | 8229.96 |
| diagnostics | 134.01 |
| performance | 37.11 |

GPU-reserved time includes model loading, training, validation, collection, profiling, checkpoint I/O and orchestration while the worker owns one GPU. It is not GPU kernel-active time. Phase timings and sampled device memory/power/utilization are retained separately; sampled device memory is not the allocator high-water mark.

### Train/validation and raw/EMA diagnostics

| Checkpoint / weights / split | Images | Mud IoU (%) | Mud precision (%) | Mud recall (%) |
| --- | --- | --- | --- | --- |
| best-auto-train / raw | 217 | 94.57 | 98.26 | 96.18 |
| best-auto-val / raw | 37 | 6.00 | 22.68 | 7.55 |
| best-alternate-val / ema | 37 | 2.59 | 5.62 | 4.59 |
| final-auto-val / raw | 37 | 1.21 | 1.71 | 3.96 |

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
| 258 | 27.24 | 0.17 |
| 518 | 26.64 | 0.56 |
| 777 | 27.19 | 0.47 |
| 1036 | 29.95 | 1.85 |
| 1295 | 30.88 | 6.01 |
| 1555 | 30.29 | 5.05 |
| 1814 | 30.91 | 1.29 |
| 2073 | 30.73 | 5.25 |
| 2332 | 32.34 | 2.21 |
| 2592 | 32.54 | 1.13 |
| 2851 | 30.68 | 1.34 |
| 3110 | 31.17 | 2.33 |
| 3369 | 33.01 | 1.63 |
| 3629 | 33.53 | 1.05 |
| 3888 | 32.83 | 1.37 |
| 4000 | 33.05 | 1.21 |

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
      "path": "/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fgall-seed0-20261007/future-runs/denseaspp161--rtis_only--seed-0_seed0/rtis/best.ckpt",
      "sha256": "6462963d26271d3ec60456745eda91268fd2062215c33bc8bb176be00a884f57",
      "global_step": 1296,
      "bytes": 569515666
    },
    "final": {
      "path": "/data/izadia1/projects/segmentary-runs/rad_9_24_2026/fgall-seed0-20261007/future-runs/denseaspp161--rtis_only--seed-0_seed0/rtis/last.ckpt",
      "sha256": "b730dddf4ebeb2c3a9b9ea7ad93d75601cfc7203212bae45316fbecc2af243d4",
      "global_step": 4000,
      "bytes": 569481746
    }
  },
  "cleanup_error": null
}
```

### Resolved training, initialization and evaluation settings

The optimizer block is the base configuration. Stage LR scales are applied at runtime, and stage warmup is capped at min(base warmup, floor(stage budget / 10), stage budget - 1): 400 steps for this 4,000-step pilot. Model-internal native input grids may differ from augmentation crops (EoMT uses its 640 grid).

```json
{
  "name": "denseaspp161--rtis_only--seed-0",
  "model": {
    "arch": "denseaspp161",
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
    "cuda_visible_devices": "7",
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
    "model_parameter_count": 35398917,
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
    "trainable_parameter_count": 35398917,
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
    "cuda_visible_devices": "7",
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
