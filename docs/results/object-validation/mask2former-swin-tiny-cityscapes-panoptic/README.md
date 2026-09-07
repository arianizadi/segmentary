# Mask2Former Swin-T / Cityscapes panoptic

Panoptic segmentation; 3 validation images. Scores are percentages.

| PQ | SQ | RQ |
| ---: | ---: | ---: |
| 76.27 | 83.52 | 90.30 |

## Per-class results

| Class | Kind | PQ | SQ | RQ | TP | FP | FN |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| road | stuff | 97.37 | 97.37 | 100.00 | 3 | 0 | 0 |
| sidewalk | stuff | 82.94 | 82.94 | 100.00 | 3 | 0 | 0 |
| building | stuff | 97.16 | 97.16 | 100.00 | 3 | 0 | 0 |
| wall | stuff | — | — | — | 0 | 0 | 0 |
| fence | stuff | 52.77 | 79.15 | 66.67 | 1 | 0 | 1 |
| pole | stuff | 45.14 | 67.71 | 66.67 | 2 | 1 | 1 |
| traffic light | stuff | — | — | — | 0 | 0 | 0 |
| traffic sign | stuff | 80.64 | 80.64 | 100.00 | 3 | 0 | 0 |
| vegetation | stuff | 90.36 | 90.36 | 100.00 | 3 | 0 | 0 |
| terrain | stuff | — | — | — | 0 | 0 | 0 |
| sky | stuff | 93.76 | 93.76 | 100.00 | 2 | 0 | 0 |
| person | thing | 70.72 | 76.61 | 92.31 | 6 | 1 | 0 |
| rider | thing | 61.60 | 77.00 | 80.00 | 2 | 0 | 1 |
| car | thing | 82.66 | 84.38 | 97.96 | 24 | 0 | 1 |
| truck | thing | — | — | — | 0 | 0 | 0 |
| bus | thing | — | — | — | 0 | 0 | 0 |
| train | thing | — | — | — | 0 | 0 | 0 |
| motorcycle | thing | — | — | — | 0 | 0 | 0 |
| bicycle | thing | 60.08 | 75.10 | 80.00 | 2 | 0 | 1 |

| Group | PQ | SQ | RQ | Evaluated classes |
| --- | ---: | ---: | ---: | ---: |
| things | 68.77 | 78.27 | 87.57 | 4 |
| stuff | 80.02 | 86.14 | 91.67 | 8 |

## Speed and memory

| Measurement | FPS | Mean ms | Median ms | P95 ms |
| --- | ---: | ---: | ---: | ---: |
| model only | 11.46 | 87.27 | 88.21 | 88.61 |
| end to end | 3.30 | 303.25 | 276.80 | 350.39 |

Peak allocated VRAM (GiB): 0.84.

Peak reserved VRAM (GiB): 1.68.

Batch size 1; float32 evaluation; input [512, 1024]; 2 untimed model warmup forwards; synchronized CUDA/MPS timing. Model-only excludes resize and transfer. End-to-end includes image/target decoding, normalization, resize, transfer, forward, native-size postprocessing and CPU prediction transfer; excludes metric calculation, hashing and prediction export. File caches are not flushed.

Hardware: {'platform': 'Linux-5.15.0-139-generic-x86_64-with-glibc2.35', 'machine': 'x86_64', 'processor': 'x86_64', 'device': 'cuda:0', 'torch_threads': 2, 'cuda_runtime': '12.8', 'gpu': 'NVIDIA L40S', 'gpu_total_bytes': 47677177856, 'gpu_free_bytes_at_end': 28738322432, 'compute_capability': [8, 9]}. GPU exclusivity was not enforced; concurrent jobs can affect speed and available memory. VRAM is this process's PyTorch allocator peak, including loaded model weights, not total device usage or training VRAM.

## Provenance

- Checkpoint SHA256: `580f9480a0ade87b1b5afd738fbb7a0fc0b162f9c166d898f232033a5324a4f1`
- Checkpoint step: 0
- Dataset fingerprint: `8afd01b628c2b183cb6a233321a464b4e443437362f413f6bfa2f1d1c37f3dab`
- Architecture: `mask2former_swin_tiny`
- Initializer configuration: `{"arch": "mask2former_swin_tiny", "backbone_path": null, "batch_norm_momentum": null, "checkpoint": "facebook/mask2former-swin-tiny-cityscapes-panoptic", "classifier_path": null, "drop_path": null, "encoder_name": null, "encoder_weights": null, "head": "unified_head", "head_paths": [], "inactive_parameter_paths": [], "local_files_only": false, "lora_alpha": 32, "lora_dropout": 0.05, "lora_r": 16, "lora_targets": [], "native": null, "revision": "9118379c4bbadaf4ac7aa3607c897dcb9952c890", "smp_arch": null, "subfolder": null, "trust_remote_code": false, "tuning": "full"}`
- Evaluation code: `unknown`; dirty: True

Full resolved configuration, embedded checkpoint architecture, category mapping, thresholds, seed, package versions, hardware, per-image timings and input file hashes: [report.json](report.json). Exported native predictions: [predictions.json](predictions/predictions.json).

## Reference evaluator

PASS: cocodataset/panopticapi pq_compute_single_core + PQStat.pq_average; absolute tolerance 1e-08. Details are recorded in report.json.
