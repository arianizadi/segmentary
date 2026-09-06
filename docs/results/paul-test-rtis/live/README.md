# paul-test-rtis — mud-pumping detection

**12/144 completed · 0 failed**

Mud-pumping is the primary application. This pilot still selects checkpoints and stops by overall validation mIoU. Mud metrics are prominent here so aggregate accuracy cannot hide detection failures. A future mud-focused selection policy must be versioned; historical results are not relabeled.

[Dataset and preparation](../README.md) · [Mathematical mud-pumping audit](../mud-pumping-audit/README.md) · [CSV results](results.csv) · [Full machine records](status.json)

36 model recipes x four initialization paths x seed 0. Train/val/test: 220/37/50 images. Test is held out. Validation groups are provisional and lack person, truck and on-rails ground truth. Single-seed differences are descriptive.

## Mud-pumping and quality

Click any model for all initialization paths, full class metrics, training/validation curves, VRAM, timing, config, checkpoint and software provenance. — means unavailable, never zero.

| Model | Initialization path | Status | Steps | Best step | Mud IoU (%) | Mud precision (%) | Mud recall (%) | Final mud IoU (trainer val, %) | mIoU (%) | Fixed GT-class mIoU (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | completed | 3309 | 3054 | 9.52 | 10.75 | 45.40 | 9.53 | 45.58 | 50.64 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | completed | 1272 | 509 | 2.06 | 2.71 | 7.95 | 12.46 | 47.03 | 49.64 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | completed | 1781 | 1018 | 17.34 | 24.29 | 37.74 | 26.13 | 54.56 | 60.62 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | completed | 1781 | 1018 | 7.85 | 9.50 | 31.21 | 8.39 | 50.65 | 53.47 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | completed | 4000 | 3818 | 9.68 | 11.78 | 35.15 | 9.68 | 48.53 | 53.92 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | completed | 1527 | 1527 | 10.26 | 13.26 | 31.21 | 10.26 | 50.69 | 53.50 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | completed | 1781 | 1018 | 4.40 | 5.81 | 15.31 | 3.64 | 53.74 | 59.71 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | completed | 1527 | 763 | 13.33 | 16.58 | 40.49 | 14.81 | 58.34 | 58.34 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | training | 2949 | — | — | — | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | training | 2949 | — | — | — | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | training | 1949 | — | — | — | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | training | 1749 | — | — | — | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | completed | 3054 | 2290 | 0.42 | 0.61 | 1.36 | 3.66 | 22.18 | 24.64 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | completed | 1781 | 1018 | 1.38 | 2.59 | 2.86 | 1.67 | 21.79 | 23.00 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | completed | 1272 | 509 | 2.29 | 2.68 | 13.43 | 2.34 | 25.51 | 26.93 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | completed | 3309 | 2545 | 5.70 | 9.73 | 12.10 | 4.39 | 29.61 | 32.90 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | queued | — | — | — | — | — | — | — | — |

## Interpretation and checkpoint selection

The current best checkpoint maximizes mIoU over classes with nonzero union. False positives on an absent class add a zero-IoU class to the mean. Fixed GT-class mIoU uses the same 18 ground-truth-present validation classes and is supplementary; it does not excuse false positives. Mud IoU, precision and recall are pixel-level segmentation measures, not event-level detection rates.

`rtis_only` uses each recipe default pretrained initializer, which can include a segmentation checkpoint (EoMT: COCO panoptic; BEiT: ADE20K), not just backbone weights. Other paths load historical Cityscapes/RailSem19 endpoints and reset classifiers. Exact resolved settings are on model pages.

Validation approximately every 250 optimizer steps; stop after three checks without 0.2 percentage-point mIoU improvement. At most 4,000 steps. Keep aggregate-best and final full-state checkpoints; periodic checkpoints are removed only after successful evaluation, with an audit.

Frozen training code: `4f5ebf0095cc097d491ad42ea5e6f77939b7119b`. Split SHA-256: `71fef8292610c352da0709fe3bd030f3bcc18f97560394835f4b22826463b83d`.

## Training resources

| Model | Initialization | Train peak GiB (retained invocation) | Eval peak GiB | Train seconds (retained invocation) | Eval seconds |
| --- | --- | --- | --- | --- | --- |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | rtis_only | 17.27 | 8.11 | 4652.15 | 13.24 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_rtis | 17.29 | 8.11 | 1103.09 | 13.62 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | railsem19_to_rtis | 17.30 | 8.11 | 2131.49 | 13.36 |
| [eomt_dinov3_large](models/eomt_dinov3_large/README.md) | cityscapes_to_railsem19_to_rtis | 17.29 | 8.11 | 2162.97 | 13.39 |
| [eomt_large](models/eomt_large/README.md) | rtis_only | 17.16 | 8.16 | 5584.85 | 12.52 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_rtis | 17.25 | 8.16 | 1679.79 | 12.67 |
| [eomt_large](models/eomt_large/README.md) | railsem19_to_rtis | 17.25 | 8.16 | 1974.41 | 12.61 |
| [eomt_large](models/eomt_large/README.md) | cityscapes_to_railsem19_to_rtis | 17.16 | 8.16 | 1511.22 | 12.63 |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | rtis_only | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_rtis | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | railsem19_to_rtis | — | — | — | — |
| [hf_auto_beit_base_ade](models/hf_auto_beit_base_ade/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | rtis_only | 9.88 | 6.20 | 2590.61 | 18.51 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_rtis | 9.88 | 6.20 | 1517.88 | 18.02 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | railsem19_to_rtis | 9.88 | 6.20 | 1089.48 | 18.39 |
| [hf_auto_mobilenetv2_deeplabv3](models/hf_auto_mobilenetv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | 9.88 | 6.20 | 2786.82 | 17.70 |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | rtis_only | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_rtis | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | railsem19_to_rtis | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](models/hf_auto_mobilevit_xxs_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | rtis_only | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_rtis | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | railsem19_to_rtis | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](models/hf_auto_mobilevitv2_deeplabv3/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | rtis_only | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_rtis | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | railsem19_to_rtis | — | — | — | — |
| [hf_auto_segformer_b0](models/hf_auto_segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | rtis_only | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_rtis | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | railsem19_to_rtis | — | — | — | — |
| [hf_auto_upernet_swin_tiny](models/hf_auto_upernet_swin_tiny/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | rtis_only | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_rtis | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | railsem19_to_rtis | — | — | — | — |
| [hrnet_w48_ocr](models/hrnet_w48_ocr/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | rtis_only | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](models/native_convnext_tiny_channelmapper_dpt/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | rtis_only | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_convnext_tiny_uper](models/native_convnext_tiny_uper/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | rtis_only | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](models/native_efficientnet_b0_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | rtis_only | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](models/native_mobilenetv3_large_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | rtis_only | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_mobilenetv3_large_lraspp](models/native_mobilenetv3_large_lraspp/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | rtis_only | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_resnet101_uper](models/native_resnet101_uper/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | rtis_only | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_resnet18_fpn_fcn](models/native_resnet18_fpn_fcn/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | rtis_only | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](models/native_resnet18_fpn_segformer_aux/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | rtis_only | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_resnet50_aspp](models/native_resnet50_aspp/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | rtis_only | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_resnet50_deeplabv3plus](models/native_resnet50_deeplabv3plus/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | rtis_only | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_resnet50_fpn_ocr](models/native_resnet50_fpn_ocr/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | rtis_only | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_rtis | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | railsem19_to_rtis | — | — | — | — |
| [native_resnet50_psp](models/native_resnet50_psp/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | rtis_only | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_rtis | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | railsem19_to_rtis | — | — | — | — |
| [segformer_b0](models/segformer_b0/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | rtis_only | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_rtis | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | railsem19_to_rtis | — | — | — | — |
| [segformer_b2](models/segformer_b2/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | rtis_only | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_rtis | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | railsem19_to_rtis | — | — | — | — |
| [segformer_b5](models/segformer_b5/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | rtis_only | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_deeplabv3_resnet50](models/smp_deeplabv3_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | rtis_only | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_deeplabv3plus_resnet101](models/smp_deeplabv3plus_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | rtis_only | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_fpn_resnet50](models/smp_fpn_resnet50/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | rtis_only | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_linknet_mobilenet_v2](models/smp_linknet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | rtis_only | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_manet_efficientnet_b0](models/smp_manet_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | rtis_only | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_pan_resnext50](models/smp_pan_resnext50/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | rtis_only | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_pspnet_mobilenet_v2](models/smp_pspnet_mobilenet_v2/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | rtis_only | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_unet_resnet34](models/smp_unet_resnet34/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | rtis_only | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](models/smp_unetplusplus_efficientnet_b0/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | rtis_only | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_upernet_mit_b0](models/smp_upernet_mit_b0/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | rtis_only | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_rtis | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | railsem19_to_rtis | — | — | — | — |
| [smp_upernet_resnet101](models/smp_upernet_resnet101/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | rtis_only | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_rtis | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | railsem19_to_rtis | — | — | — | — |
| [upernet_convnext](models/upernet_convnext/README.md) | cityscapes_to_railsem19_to_rtis | — | — | — | — |

Resumed invocation resource measurements are not cumulative training cost. Standardized FPS/latency and parameter memory are separate profiling evidence; missing evidence is explicit on each model page. The report publisher does not modify frozen training jobs or historical Cityscapes/RailSem19 reports.
