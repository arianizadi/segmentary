# RAD 9/24: `fixed-grouped` arm

Our 10-model x 4-initialization-path campaign on the `fixed-grouped` arm (labels: re-rendered from the polygon JSONs; split: scene-grouped (from v1/v2)). The arm name describes the labels and split, not who trained: every model on this page was trained by us. Protocol names keep the RTIS publisher's wording, where `rtis` is the final RAD training stage: "RTIS only" is pretrained backbone → RAD, "City → Rail → RTIS" is Cityscapes → RailSem19 → RAD.

**0/40 completed · 0 failed**

Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling.

[RAD 9/24 study](../README.md) · [CSV results](results.csv) · [Full machine records](status.json)

10 models; four initialization paths; seeds [0]. Train/val/test: 217/37/60 images. Test is held out. Split grouping status: `provisional_until_recording_provenance_confirmed`. Seed variation does not establish independent-recording generalization.

## Quality

Validation **mIoU (%)** across classes. Cells show the mean over completed seeds. Per-seed values are retained on model pages and in machine records. Partial groups are provisional; — means unavailable. These are the existing selected-checkpoint evaluations, not newly selected mIoU-best checkpoints. Raw/EMA settings are recorded on each model page.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 0/4 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | 0/4 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 0/4 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/4 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/4 | — | — | — | — |

## Mud-pumping

Validation **mud-pumping IoU (%)** for the same checkpoints. Precision, recall, per-class scores and examples are on each model page and in the CSV.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 0/4 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | 0/4 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 0/4 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/4 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/4 | — | — | — | — |

## Standardized model-only inference

**FPS**, mean across completed, profiled seeds. Input/evaluation settings, latency and peak VRAM are on the model pages; compare speeds only under compatible settings.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 0/4 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | 0/4 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 0/4 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/4 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/4 | — | — | — | — |

<details>
<summary>Individual runs: quality, mud precision/recall, steps and status</summary>

Click any model for all initialization paths, full class metrics, training/validation curves, VRAM, timing, config, checkpoint and software provenance. — means unavailable, never zero.

| Model | Initialization path | Seed | Status | Steps | Best step | Mud IoU (%) | Mud precision (%) | Mud recall (%) | Final mud IoU (trainer val, %) | mIoU (%) | Fixed GT-class mIoU (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |

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
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |

</details>

Resumed invocation resource measurements are not cumulative training cost. Standardized FPS/latency and parameter memory are separate profiling evidence; missing evidence is explicit on each model page. The report publisher does not modify frozen training jobs or historical Cityscapes/RailSem19 reports.
