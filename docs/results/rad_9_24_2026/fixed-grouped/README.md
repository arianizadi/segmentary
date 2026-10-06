# RAD 9/24: `fixed-grouped` arm

Our 10-model x 4-initialization-path campaign on the `fixed-grouped` arm (labels: re-rendered from the polygon JSONs; split: scene-grouped (from v1/v2)). The arm name describes the labels and split, not who trained: every model on this page was trained by us. Protocol names keep the RTIS publisher's wording, where `rtis` is the final RAD training stage: "RTIS only" is pretrained backbone → RAD, "City → Rail → RTIS" is Cityscapes → RailSem19 → RAD.

**39/40 completed · 0 failed**

Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling.

[RAD 9/24 study](../README.md) · [CSV results](results.csv) · [Full machine records](status.json)

10 models; four initialization paths; seeds [0]. Train/val/test: 217/37/60 images. Test is held out. Split grouping status: `provisional_until_recording_provenance_confirmed`. Seed variation does not establish independent-recording generalization.

## Quality

Validation **mIoU (%)** across classes. Cells show the mean over completed seeds. Per-seed values are retained on model pages and in machine records. Partial groups are provisional; — means unavailable. These are the existing selected-checkpoint evaluations, not newly selected mIoU-best checkpoints. Raw/EMA settings are recorded on each model page.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 43.80 | 46.27 | 49.96 | 44.82 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 47.84 | 53.42 | 49.72 | 55.15 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 31.91 | 34.37 | 46.15 | 44.68 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 3/4 | 27.69 | 35.19 | 42.40 | — |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 34.14 | 38.62 | 45.16 | 42.83 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 35.71 | 39.76 | 46.16 | 45.26 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 25.88 | 22.34 | 44.32 | 36.83 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 20.13 | 28.95 | 41.83 | 35.26 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 21.93 | 22.37 | 30.14 | 31.95 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 36.12 | 31.04 | 42.36 | 37.88 |

## Mud-pumping

Validation **mud-pumping IoU (%)** for the same checkpoints. Precision, recall, per-class scores and examples are on each model page and in the CSV.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 8.67 | 10.58 | 18.84 | 8.22 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 12.73 | 9.40 | 3.33 | 15.70 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 3.60 | 12.02 | 2.40 | 6.51 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 3/4 | 6.90 | 3.11 | 2.07 | — |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 10.08 | 16.81 | 6.09 | 15.88 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 5.19 | 4.69 | 5.60 | 5.02 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 6.62 | 1.38 | 5.65 | 3.72 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 4.80 | 8.24 | 12.82 | 14.43 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 6.81 | 16.34 | 8.67 | 15.90 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 4.68 | 3.21 | 7.82 | 2.44 |

## Standardized model-only inference

**FPS**, mean across completed, profiled seeds. Input/evaluation settings, latency and peak VRAM are on the model pages; compare speeds only under compatible settings.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 4/4 | 38.25 | 37.25 | 41.47 | 41.38 |
| [eomt_large](models/eomt_large/README.md) | 4/4 | 45.95 | 45.80 | 45.26 | 45.50 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 4/4 | 30.81 | 31.72 | 30.76 | 31.50 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 3/4 | 76.06 | 75.90 | 76.52 | — |
| [segformer_b2](models/segformer_b2/README.md) | 4/4 | 53.92 | 53.02 | 53.93 | 53.87 |
| [segformer_b5](models/segformer_b5/README.md) | 4/4 | 27.84 | 27.53 | 27.73 | 27.85 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 4/4 | 119.75 | 108.60 | 119.35 | 117.12 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 4/4 | 160.29 | 160.41 | 159.67 | 159.09 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 4/4 | 73.39 | 73.74 | 74.57 | 74.26 |
| [upernet_convnext](models/upernet_convnext/README.md) | 4/4 | 42.30 | 42.72 | 41.95 | 42.62 |

<details>
<summary>Individual runs: quality, mud precision/recall, steps and status</summary>

Click any model for all initialization paths, full class metrics, training/validation curves, VRAM, timing, config, checkpoint and software provenance. — means unavailable, never zero.

| Model | Initialization path | Seed | Status | Steps | Best step | Mud IoU (%) | Mud precision (%) | Mud recall (%) | Final mud IoU (trainer val, %) | mIoU (%) | Fixed GT-class mIoU (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | completed | 2333 | 1555 | 12.73 | 16.54 | 35.57 | 10.44 | 47.84 | 53.16 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | completed | 3370 | 2074 | 9.40 | 12.31 | 28.47 | 9.09 | 53.42 | 56.38 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | completed | 2074 | 777 | 3.33 | 4.46 | 11.57 | 3.14 | 49.72 | 58.01 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2074 | 777 | 15.70 | 20.78 | 39.08 | 15.42 | 55.15 | 58.22 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | completed | 3111 | 3111 | 8.67 | 9.77 | 43.52 | 8.67 | 43.80 | 48.67 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | completed | 3370 | 2074 | 10.58 | 11.98 | 47.54 | 10.49 | 46.27 | 51.42 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 3888 | 18.84 | 26.76 | 38.89 | 18.87 | 49.96 | 58.28 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2074 | 777 | 8.22 | 16.68 | 13.94 | 4.84 | 44.82 | 52.29 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | completed | 2333 | 1037 | 5.19 | 7.12 | 16.14 | 1.06 | 35.71 | 41.66 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 2851 | 4.69 | 5.27 | 29.88 | 4.44 | 39.76 | 44.18 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | completed | 4000 | 2851 | 5.60 | 8.07 | 15.44 | 4.25 | 46.16 | 53.85 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 4000 | 2851 | 5.02 | 5.79 | 27.37 | 4.85 | 45.26 | 50.29 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | completed | 1814 | 1814 | 3.60 | 6.36 | 7.66 | 3.61 | 31.91 | 37.23 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | completed | 3370 | 2074 | 12.02 | 81.61 | 12.36 | 7.15 | 34.37 | 40.10 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | completed | 3888 | 2592 | 2.40 | 3.20 | 8.76 | 0.82 | 46.15 | 51.28 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2851 | 1555 | 6.51 | 80.38 | 6.62 | 4.49 | 44.68 | 49.65 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | completed | 3370 | 2074 | 10.08 | 16.06 | 21.30 | 6.72 | 34.14 | 39.83 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | completed | 4000 | 3629 | 16.81 | 33.45 | 25.25 | 12.88 | 38.62 | 45.05 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | completed | 3629 | 2333 | 6.09 | 9.81 | 13.85 | 3.93 | 45.16 | 52.69 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 3888 | 2592 | 15.88 | 58.38 | 17.91 | 15.24 | 42.83 | 47.59 |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | completed | 3111 | 1814 | 4.68 | 6.98 | 12.44 | 1.31 | 36.12 | 42.14 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | completed | 2333 | 1037 | 3.21 | 3.71 | 19.08 | 2.21 | 31.04 | 36.21 |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | completed | 3629 | 2333 | 7.82 | 14.34 | 14.68 | 2.69 | 42.36 | 49.42 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2333 | 1037 | 2.44 | 3.63 | 6.88 | 0.99 | 37.88 | 44.19 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | completed | 2592 | 1296 | 6.62 | 9.14 | 19.42 | 2.70 | 25.88 | 30.19 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | completed | 1555 | 259 | 1.38 | 1.70 | 6.79 | 1.21 | 22.34 | 23.58 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | completed | 2074 | 777 | 5.65 | 7.84 | 16.77 | 2.11 | 44.32 | 49.24 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2592 | 1296 | 3.72 | 6.02 | 8.90 | 2.51 | 36.83 | 40.92 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | completed | 1555 | 259 | 4.80 | 7.36 | 12.11 | 1.15 | 20.13 | 22.37 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | completed | 2592 | 1296 | 8.24 | 31.75 | 10.01 | 3.59 | 28.95 | 32.17 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | completed | 2074 | 777 | 12.82 | 24.34 | 21.32 | 7.52 | 41.83 | 48.80 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 2074 | 777 | 14.43 | 51.44 | 16.70 | 13.01 | 35.26 | 41.14 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | completed | 1555 | 259 | 6.81 | 26.48 | 8.40 | 1.14 | 21.93 | 25.58 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | completed | 1814 | 518 | 16.34 | 26.53 | 29.84 | 7.38 | 22.37 | 26.09 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | completed | 1814 | 518 | 8.67 | 19.81 | 13.36 | 4.27 | 30.14 | 35.16 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | completed | 1814 | 518 | 15.90 | 41.34 | 20.53 | 7.06 | 31.95 | 37.27 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | completed | 1555 | 259 | 6.90 | 12.50 | 13.35 | 3.02 | 27.69 | 29.22 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | completed | 2074 | 777 | 3.11 | 12.24 | 4.01 | 1.94 | 35.19 | 41.06 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | completed | 2333 | 1037 | 2.07 | 3.14 | 5.73 | 1.73 | 42.40 | 49.46 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | evaluating | 2851 | — | — | — | — | — | — | — |

</details>

## Training specification and interpretation

This campaign selects checkpoints and early-stops by **mud-pumping validation IoU**. Both overall mIoU and mud IoU above describe that same selected checkpoint. This report layout does not change the training objective or selection policy. mIoU averages classes with nonzero union; fixed GT-class means, mud precision/recall and raw/EMA diagnostics remain on model pages. Seed SD describes optimization variability, not independent-recording uncertainty.

`rtis_only` uses each recipe default pretrained initializer, which can include a segmentation checkpoint (EoMT: COCO panoptic; BEiT: ADE20K), not just backbone weights. Other paths load historical Cityscapes/RailSem19 endpoints and reset classifiers. Exact resolved settings are on model pages.

Validation approximately every 250 optimizer steps; stop after five checks without a 0.1 percentage-point mud-IoU improvement. At most 4,000 steps. Keep mud-selected and final full-state checkpoints; remove periodic snapshots only after complete verified collection.

Frozen training code: `d864b72bd90706260965bb1a48398d01167b6d5c`. Split SHA-256: `12d7b367c72cda61d57686ff2ac28223530d0af49debd9fb7a0fbc68b908bc93`.

## Training cost

<details>
<summary>Per-run training and evaluation memory and time</summary>

| Model | Initialization | Seed | Train peak GiB (retained invocation) | Eval peak GiB | Train seconds (retained invocation) | Eval seconds |
| --- | --- | --- | --- | --- | --- | --- |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | 17.70 | 10.80 | 3385.28 | 21.18 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | 17.70 | 10.80 | 4919.84 | 21.50 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | 17.70 | 10.80 | 2997.82 | 21.96 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.70 | 10.80 | 3095.80 | 20.96 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | 17.84 | 10.77 | 4813.20 | 21.85 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | 17.84 | 10.77 | 5104.50 | 22.01 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | 17.84 | 10.77 | 6167.97 | 21.68 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.84 | 10.77 | 3092.47 | 21.77 |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | 16.31 | 7.78 | 3597.05 | 28.26 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | 16.31 | 7.78 | 6146.35 | 28.35 |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | 16.31 | 7.78 | 6155.42 | 28.14 |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 16.31 | 7.78 | 6165.00 | 28.79 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | 17.35 | 7.58 | 3056.72 | 18.23 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | 17.35 | 7.58 | 5591.50 | 18.36 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | 17.35 | 7.58 | 6451.88 | 18.38 |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 17.35 | 7.58 | 4789.25 | 18.12 |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | 11.73 | 7.46 | 3182.22 | 22.20 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | 11.73 | 7.46 | 3782.83 | 22.14 |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | 11.73 | 7.46 | 3436.40 | 22.15 |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.73 | 7.46 | 3664.52 | 22.12 |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | 13.46 | 7.68 | 4318.36 | 21.53 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | 13.46 | 7.68 | 3215.02 | 21.85 |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | 13.46 | 7.68 | 5022.16 | 21.85 |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 13.46 | 7.68 | 3224.56 | 21.52 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | 10.08 | 7.19 | 1878.69 | 11.52 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | 10.08 | 7.19 | 1134.60 | 11.47 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | 10.08 | 7.19 | 1509.05 | 11.28 |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 10.08 | 7.19 | 1872.06 | 11.14 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | 8.69 | 7.01 | 955.05 | 11.22 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | 8.69 | 7.01 | 1589.89 | 11.18 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | 8.69 | 7.01 | 1243.60 | 11.26 |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 8.69 | 7.01 | 1247.20 | 11.14 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | 11.09 | 7.69 | 1318.68 | 15.91 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | 11.09 | 7.69 | 1541.44 | 15.56 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | 11.09 | 7.69 | 1525.88 | 15.46 |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | 11.09 | 7.69 | 1529.88 | 15.94 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | 10.20 | 7.42 | 1271.32 | 16.08 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | 10.20 | 7.42 | 1696.85 | 15.57 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | 10.20 | 7.42 | 1894.96 | 15.21 |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |

</details>

Resumed invocation resource measurements are not cumulative training cost. Standardized FPS/latency and parameter memory are separate profiling evidence; missing evidence is explicit on each model page. The report publisher does not modify frozen training jobs or historical Cityscapes/RailSem19 reports.
