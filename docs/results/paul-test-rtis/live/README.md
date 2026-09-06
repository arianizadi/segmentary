# paul-test-rtis live pilot

**2/144 completed · 0 failed**

36 model recipes x four initialization paths x seed 0. Each run trains for at most 4,000 optimizer steps on the same 220 training images, with validation-based early stopping.

Validation: 37 images; best validation checkpoint, native RTIS classes, no TTA. Test: 50 held-out images, not evaluated. Recording groups are provisional; validation lacks person, truck and on-rails. These single-seed pilot results do not establish independent-recording generalization.

Frozen training code: `4f5ebf0095cc097d491ad42ea5e6f77939b7119b`. Split SHA-256: `71fef8292610c352da0709fe3bd030f3bcc18f97560394835f4b22826463b83d`.

Initialization: `rtis_only` = pretrained backbone; `cityscapes_to_rtis` = Cityscapes endpoint; `railsem19_to_rtis` = RailSem19 endpoint; `cityscapes_to_railsem19_to_rtis` = Cityscapes → RailSem19 endpoint. All transferred classifiers are reset.

[Complete results, per-class metrics, checkpoint hashes and provenance](status.json). Source diagnostics remain [separate](../README.md). Values below are **validation mIoU (%)**, not the coarse source-only diagnostic scores.

Validation every 250 steps; stop after three checks without a 0.2-point mIoU improvement. Keep the best validation checkpoint. An early stop is a completed run, not a failed run. Training and validation curves are in the linked JSON.

| Model | Initialization path | Status | Steps | Best step | Val mIoU (%) |
| --- | --- | --- | ---: | ---: | ---: |
| eomt_dinov3_large | rtis_only | training | — | — | — |
| eomt_dinov3_large | cityscapes_to_rtis | completed | 1272 | 509 | 47.03 |
| eomt_dinov3_large | railsem19_to_rtis | training | — | — | — |
| eomt_dinov3_large | cityscapes_to_railsem19_to_rtis | training | — | — | — |
| eomt_large | rtis_only | training | — | — | — |
| eomt_large | cityscapes_to_rtis | training | — | — | — |
| eomt_large | railsem19_to_rtis | training | — | — | — |
| eomt_large | cityscapes_to_railsem19_to_rtis | completed | 1527 | 763 | 58.34 |
| hf_auto_beit_base_ade | rtis_only | training | — | — | — |
| hf_auto_beit_base_ade | cityscapes_to_rtis | training | — | — | — |
| hf_auto_beit_base_ade | railsem19_to_rtis | training | — | — | — |
| hf_auto_beit_base_ade | cityscapes_to_railsem19_to_rtis | training | — | — | — |
| hf_auto_mobilenetv2_deeplabv3 | rtis_only | queued | — | — | — |
| hf_auto_mobilenetv2_deeplabv3 | cityscapes_to_rtis | queued | — | — | — |
| hf_auto_mobilenetv2_deeplabv3 | railsem19_to_rtis | queued | — | — | — |
| hf_auto_mobilenetv2_deeplabv3 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| hf_auto_mobilevit_xxs_deeplabv3 | rtis_only | queued | — | — | — |
| hf_auto_mobilevit_xxs_deeplabv3 | cityscapes_to_rtis | queued | — | — | — |
| hf_auto_mobilevit_xxs_deeplabv3 | railsem19_to_rtis | queued | — | — | — |
| hf_auto_mobilevit_xxs_deeplabv3 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| hf_auto_mobilevitv2_deeplabv3 | rtis_only | queued | — | — | — |
| hf_auto_mobilevitv2_deeplabv3 | cityscapes_to_rtis | queued | — | — | — |
| hf_auto_mobilevitv2_deeplabv3 | railsem19_to_rtis | queued | — | — | — |
| hf_auto_mobilevitv2_deeplabv3 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| hf_auto_segformer_b0 | rtis_only | queued | — | — | — |
| hf_auto_segformer_b0 | cityscapes_to_rtis | queued | — | — | — |
| hf_auto_segformer_b0 | railsem19_to_rtis | queued | — | — | — |
| hf_auto_segformer_b0 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| hf_auto_upernet_swin_tiny | rtis_only | queued | — | — | — |
| hf_auto_upernet_swin_tiny | cityscapes_to_rtis | queued | — | — | — |
| hf_auto_upernet_swin_tiny | railsem19_to_rtis | queued | — | — | — |
| hf_auto_upernet_swin_tiny | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| hrnet_w48_ocr | rtis_only | queued | — | — | — |
| hrnet_w48_ocr | cityscapes_to_rtis | queued | — | — | — |
| hrnet_w48_ocr | railsem19_to_rtis | queued | — | — | — |
| hrnet_w48_ocr | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_convnext_tiny_channelmapper_dpt | rtis_only | queued | — | — | — |
| native_convnext_tiny_channelmapper_dpt | cityscapes_to_rtis | queued | — | — | — |
| native_convnext_tiny_channelmapper_dpt | railsem19_to_rtis | queued | — | — | — |
| native_convnext_tiny_channelmapper_dpt | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_convnext_tiny_uper | rtis_only | queued | — | — | — |
| native_convnext_tiny_uper | cityscapes_to_rtis | queued | — | — | — |
| native_convnext_tiny_uper | railsem19_to_rtis | queued | — | — | — |
| native_convnext_tiny_uper | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_efficientnet_b0_deeplabv3plus | rtis_only | queued | — | — | — |
| native_efficientnet_b0_deeplabv3plus | cityscapes_to_rtis | queued | — | — | — |
| native_efficientnet_b0_deeplabv3plus | railsem19_to_rtis | queued | — | — | — |
| native_efficientnet_b0_deeplabv3plus | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_mobilenetv3_large_deeplabv3plus | rtis_only | queued | — | — | — |
| native_mobilenetv3_large_deeplabv3plus | cityscapes_to_rtis | queued | — | — | — |
| native_mobilenetv3_large_deeplabv3plus | railsem19_to_rtis | queued | — | — | — |
| native_mobilenetv3_large_deeplabv3plus | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_mobilenetv3_large_lraspp | rtis_only | queued | — | — | — |
| native_mobilenetv3_large_lraspp | cityscapes_to_rtis | queued | — | — | — |
| native_mobilenetv3_large_lraspp | railsem19_to_rtis | queued | — | — | — |
| native_mobilenetv3_large_lraspp | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_resnet101_uper | rtis_only | queued | — | — | — |
| native_resnet101_uper | cityscapes_to_rtis | queued | — | — | — |
| native_resnet101_uper | railsem19_to_rtis | queued | — | — | — |
| native_resnet101_uper | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_resnet18_fpn_fcn | rtis_only | queued | — | — | — |
| native_resnet18_fpn_fcn | cityscapes_to_rtis | queued | — | — | — |
| native_resnet18_fpn_fcn | railsem19_to_rtis | queued | — | — | — |
| native_resnet18_fpn_fcn | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_resnet18_fpn_segformer_aux | rtis_only | queued | — | — | — |
| native_resnet18_fpn_segformer_aux | cityscapes_to_rtis | queued | — | — | — |
| native_resnet18_fpn_segformer_aux | railsem19_to_rtis | queued | — | — | — |
| native_resnet18_fpn_segformer_aux | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_resnet50_aspp | rtis_only | queued | — | — | — |
| native_resnet50_aspp | cityscapes_to_rtis | queued | — | — | — |
| native_resnet50_aspp | railsem19_to_rtis | queued | — | — | — |
| native_resnet50_aspp | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_resnet50_deeplabv3plus | rtis_only | queued | — | — | — |
| native_resnet50_deeplabv3plus | cityscapes_to_rtis | queued | — | — | — |
| native_resnet50_deeplabv3plus | railsem19_to_rtis | queued | — | — | — |
| native_resnet50_deeplabv3plus | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_resnet50_fpn_ocr | rtis_only | queued | — | — | — |
| native_resnet50_fpn_ocr | cityscapes_to_rtis | queued | — | — | — |
| native_resnet50_fpn_ocr | railsem19_to_rtis | queued | — | — | — |
| native_resnet50_fpn_ocr | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| native_resnet50_psp | rtis_only | queued | — | — | — |
| native_resnet50_psp | cityscapes_to_rtis | queued | — | — | — |
| native_resnet50_psp | railsem19_to_rtis | queued | — | — | — |
| native_resnet50_psp | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| segformer_b0 | rtis_only | queued | — | — | — |
| segformer_b0 | cityscapes_to_rtis | queued | — | — | — |
| segformer_b0 | railsem19_to_rtis | queued | — | — | — |
| segformer_b0 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| segformer_b2 | rtis_only | queued | — | — | — |
| segformer_b2 | cityscapes_to_rtis | queued | — | — | — |
| segformer_b2 | railsem19_to_rtis | queued | — | — | — |
| segformer_b2 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| segformer_b5 | rtis_only | queued | — | — | — |
| segformer_b5 | cityscapes_to_rtis | queued | — | — | — |
| segformer_b5 | railsem19_to_rtis | queued | — | — | — |
| segformer_b5 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_deeplabv3_resnet50 | rtis_only | queued | — | — | — |
| smp_deeplabv3_resnet50 | cityscapes_to_rtis | queued | — | — | — |
| smp_deeplabv3_resnet50 | railsem19_to_rtis | queued | — | — | — |
| smp_deeplabv3_resnet50 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_deeplabv3plus_resnet101 | rtis_only | queued | — | — | — |
| smp_deeplabv3plus_resnet101 | cityscapes_to_rtis | queued | — | — | — |
| smp_deeplabv3plus_resnet101 | railsem19_to_rtis | queued | — | — | — |
| smp_deeplabv3plus_resnet101 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_fpn_resnet50 | rtis_only | queued | — | — | — |
| smp_fpn_resnet50 | cityscapes_to_rtis | queued | — | — | — |
| smp_fpn_resnet50 | railsem19_to_rtis | queued | — | — | — |
| smp_fpn_resnet50 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_linknet_mobilenet_v2 | rtis_only | queued | — | — | — |
| smp_linknet_mobilenet_v2 | cityscapes_to_rtis | queued | — | — | — |
| smp_linknet_mobilenet_v2 | railsem19_to_rtis | queued | — | — | — |
| smp_linknet_mobilenet_v2 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_manet_efficientnet_b0 | rtis_only | queued | — | — | — |
| smp_manet_efficientnet_b0 | cityscapes_to_rtis | queued | — | — | — |
| smp_manet_efficientnet_b0 | railsem19_to_rtis | queued | — | — | — |
| smp_manet_efficientnet_b0 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_pan_resnext50 | rtis_only | queued | — | — | — |
| smp_pan_resnext50 | cityscapes_to_rtis | queued | — | — | — |
| smp_pan_resnext50 | railsem19_to_rtis | queued | — | — | — |
| smp_pan_resnext50 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_pspnet_mobilenet_v2 | rtis_only | queued | — | — | — |
| smp_pspnet_mobilenet_v2 | cityscapes_to_rtis | queued | — | — | — |
| smp_pspnet_mobilenet_v2 | railsem19_to_rtis | queued | — | — | — |
| smp_pspnet_mobilenet_v2 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_unet_resnet34 | rtis_only | queued | — | — | — |
| smp_unet_resnet34 | cityscapes_to_rtis | queued | — | — | — |
| smp_unet_resnet34 | railsem19_to_rtis | queued | — | — | — |
| smp_unet_resnet34 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_unetplusplus_efficientnet_b0 | rtis_only | queued | — | — | — |
| smp_unetplusplus_efficientnet_b0 | cityscapes_to_rtis | queued | — | — | — |
| smp_unetplusplus_efficientnet_b0 | railsem19_to_rtis | queued | — | — | — |
| smp_unetplusplus_efficientnet_b0 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_upernet_mit_b0 | rtis_only | queued | — | — | — |
| smp_upernet_mit_b0 | cityscapes_to_rtis | queued | — | — | — |
| smp_upernet_mit_b0 | railsem19_to_rtis | queued | — | — | — |
| smp_upernet_mit_b0 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| smp_upernet_resnet101 | rtis_only | queued | — | — | — |
| smp_upernet_resnet101 | cityscapes_to_rtis | queued | — | — | — |
| smp_upernet_resnet101 | railsem19_to_rtis | queued | — | — | — |
| smp_upernet_resnet101 | cityscapes_to_railsem19_to_rtis | queued | — | — | — |
| upernet_convnext | rtis_only | queued | — | — | — |
| upernet_convnext | cityscapes_to_rtis | queued | — | — | — |
| upernet_convnext | railsem19_to_rtis | queued | — | — | — |
| upernet_convnext | cityscapes_to_railsem19_to_rtis | queued | — | — | — |

After successful evaluation, periodic checkpoints are removed with a deletion audit. Best and final checkpoints, full metrics, configs and logs remain on HDRFS. Failed-run checkpoints remain available for recovery. Historical source checkpoints are preserved.
