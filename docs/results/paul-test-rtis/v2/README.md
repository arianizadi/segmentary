# RTIS v2: disputed CVAT import removed

**0/144 completed · 0 failed**

Overall segmentation quality and mud-pumping results across four initialization paths. Every completed job includes quality evaluation, training diagnostics and isolated performance profiling.

[V2 dataset and experiment](../../../guides/paul-test-rtis-v2.md) · [CSV results](results.csv) · [Full machine records](status.json)

36 models; four initialization paths; seeds [0]. Train/val/test: 205/37/50 images. Test is held out. Validation groups are provisional and lack person, truck and on-rails ground truth. Seed variation does not establish independent-recording generalization.

[V1 versus V2: paired seed-0 comparison](comparison.md) · [Comparison CSV](comparison.csv)

## Quality

Validation **mIoU (%)** across classes. Cells show the mean over completed seeds. Per-seed values are retained on model pages and in machine records. Partial groups are provisional; — means unavailable. These are the existing selected-checkpoint evaluations, not newly selected mIoU-best checkpoints. Raw/EMA settings are recorded on each model page.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 0/4 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | 0/4 | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 0/4 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 0/4 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | 0/4 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | 0/4 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 0/4 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | 0/4 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | 0/4 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/4 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/4 | — | — | — | — |

## Mud-pumping

Validation **mud-pumping IoU (%)** for the same checkpoints. Precision, recall, per-class scores and examples are on each model page and in the CSV.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 0/4 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | 0/4 | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 0/4 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 0/4 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | 0/4 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | 0/4 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 0/4 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | 0/4 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | 0/4 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/4 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/4 | — | — | — | — |

## Standardized model-only inference

**FPS**, mean across completed, profiled seeds. Input/evaluation settings, latency and peak VRAM are on the model pages; compare speeds only under compatible settings.

| Model | Completed runs | RTIS only | City → RTIS | Rail → RTIS | City → Rail → RTIS |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | 0/4 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | 0/4 | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | 0/4 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | 0/4 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | 0/4 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | 0/4 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | 0/4 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | 0/4 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | 0/4 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | 0/4 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | 0/4 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | 0/4 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | 0/4 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | 0/4 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | 0/4 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | 0/4 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | 0/4 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | 0/4 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | 0/4 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | 0/4 | — | — | — | — |

<details>
<summary>Individual runs: quality, mud precision/recall, steps and status</summary>

Click any model for all initialization paths, full class metrics, training/validation curves, VRAM, timing, config, checkpoint and software provenance. — means unavailable, never zero.

| Model | Initialization path | Seed | Status | Steps | Best step | Mud IoU (%) | Mud precision (%) | Mud recall (%) | Final mud IoU (trainer val, %) | mIoU (%) | Fixed GT-class mIoU (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | training | 149 | — | — | — | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | training | 99 | — | — | — | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | training | 99 | — | — | — | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | training | 99 | — | — | — | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | training | 99 | — | — | — | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | training | 99 | — | — | — | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | training | 99 | — | — | — | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | training | 99 | — | — | — | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 0 | training | 49 | — | — | — | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 0 | training | 49 | — | — | — | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | queued | — | — | — | — | — | — | — | — |

</details>

## Training specification and interpretation

This campaign selects checkpoints and early-stops by **mud-pumping validation IoU**. Both overall mIoU and mud IoU above describe that same selected checkpoint. This report layout does not change the training objective or selection policy. mIoU averages classes with nonzero union; fixed GT-class means, mud precision/recall and raw/EMA diagnostics remain on model pages. Seed SD describes optimization variability, not independent-recording uncertainty.

`rtis_only` uses each recipe default pretrained initializer, which can include a segmentation checkpoint (EoMT: COCO panoptic; BEiT: ADE20K), not just backbone weights. Other paths load historical Cityscapes/RailSem19 endpoints and reset classifiers. Exact resolved settings are on model pages.

Validation approximately every 250 optimizer steps; stop after five checks without a 0.1 percentage-point mud-IoU improvement. At most 4,000 steps. Keep mud-selected and final full-state checkpoints; remove periodic snapshots only after complete verified collection.

Frozen training code: `066afb2626398b7be59d4d19f5a0e4644fd59adc`. Split SHA-256: `18a84c0163a65ded46508bcc904c374e5f33ad8a09b8879e3c8add606e86aa9f`.

## Training cost

<details>
<summary>Per-run training and evaluation memory and time</summary>

| Model | Initialization | Seed | Train peak GiB (retained invocation) | Eval peak GiB | Train seconds (retained invocation) | Eval seconds |
| --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 0 | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 0 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | 0 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | 0 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | 0 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | 0 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | 0 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | 0 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | 0 | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | 0 | — | — | — | — |

</details>

Resumed invocation resource measurements are not cumulative training cost. Standardized FPS/latency and parameter memory are separate profiling evidence; missing evidence is explicit on each model page. The report publisher does not modify frozen training jobs or historical Cityscapes/RailSem19 reports.
