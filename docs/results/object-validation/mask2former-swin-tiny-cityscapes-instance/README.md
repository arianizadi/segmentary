# Mask2Former Swin-T / Cityscapes instance

Instance segmentation; 3 validation images. Scores are percentages.

| Mask AP | AP50 | AP75 | AR100 |
| ---: | ---: | ---: | ---: |
| 53.21 | 82.10 | 56.34 | 53.40 |

## Per-class results

| Class | Kind | Mask AP | AP50 | AP75 | AR100 | GT objects |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| person | thing | 59.90 | 100.00 | 83.17 | 60.00 | 6 |
| rider | thing | 46.53 | 66.34 | 66.34 | 46.67 | 3 |
| car | thing | 73.24 | 95.72 | 75.86 | 73.60 | 25 |
| truck | thing | — | — | — | — | 0 |
| bus | thing | — | — | — | — | 0 |
| train | thing | — | — | — | — | 0 |
| motorcycle | thing | — | — | — | — | 0 |
| bicycle | thing | 33.17 | 66.34 | 0.00 | 33.33 | 3 |

## Speed and memory

| Measurement | FPS | Mean ms | Median ms | P95 ms |
| --- | ---: | ---: | ---: | ---: |
| model only | 12.35 | 80.98 | 85.20 | 86.81 |
| end to end | 3.69 | 271.34 | 268.69 | 302.50 |

Peak allocated VRAM (GiB): 0.87.

Peak reserved VRAM (GiB): 1.66.

Batch size 1; float32 evaluation; input [512, 1024]; 2 untimed model warmup forwards; synchronized CUDA/MPS timing. Model-only excludes resize and transfer. End-to-end includes image/target decoding, normalization, resize, transfer, forward, native-size postprocessing and CPU prediction transfer; excludes metric calculation, hashing and prediction export. File caches are not flushed.

Hardware: {'platform': 'Linux-5.15.0-139-generic-x86_64-with-glibc2.35', 'machine': 'x86_64', 'processor': 'x86_64', 'device': 'cuda:0', 'torch_threads': 2, 'cuda_runtime': '12.8', 'gpu': 'NVIDIA L40S', 'gpu_total_bytes': 47677177856, 'gpu_free_bytes_at_end': 28759293952, 'compute_capability': [8, 9]}. GPU exclusivity was not enforced; concurrent jobs can affect speed and available memory. VRAM is this process's PyTorch allocator peak, including loaded model weights, not total device usage or training VRAM.

## Provenance

- Checkpoint SHA256: `eb4110a5f421c9d0386a6e4cfbbc0ec980ddd89a9057b8196c7dc5807f0f3a17`
- Checkpoint step: 0
- Dataset fingerprint: `8eab3195d7ce3d2e1b37698e14d2f7d95a1286df2c54d596cf90a59e0a2ec2a3`
- Architecture: `mask2former_swin_tiny`
- Initializer configuration: `{"arch": "mask2former_swin_tiny", "backbone_path": null, "batch_norm_momentum": null, "checkpoint": "facebook/mask2former-swin-tiny-cityscapes-instance", "classifier_path": null, "drop_path": null, "encoder_name": null, "encoder_weights": null, "head": "unified_head", "head_paths": [], "inactive_parameter_paths": [], "local_files_only": false, "lora_alpha": 32, "lora_dropout": 0.05, "lora_r": 16, "lora_targets": [], "native": null, "revision": "3b56d06423be6d02bd19cff886eb8ac68b92f5ec", "smp_arch": null, "subfolder": null, "trust_remote_code": false, "tuning": "full"}`
- Evaluation code: `unknown`; dirty: True

Full resolved configuration, embedded checkpoint architecture, category mapping, thresholds, seed, package versions, hardware, per-image timings and input file hashes: [report.json](report.json). Exported native predictions: [predictions.json](predictions/predictions.json).

## Reference evaluator

PASS: pycocotools.cocoeval.COCOeval (segm, area=all, maxDets=100); absolute tolerance 1e-08. Details are recorded in report.json.
