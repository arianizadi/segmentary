# Model comparison: Cityscapes and RailSem19

This live comparison covers every shipped model recipe. Compatible results are reused instead of retrained. `—` means evidence is unavailable, not zero or failure. Quality tables show one clean mean; individual seeds remain in machine records.

## Training specification

These are the resolved settings used by this campaign, not generic model defaults. Each physical job occupies one L40S and performs one optimizer update after the listed number of accumulated micro-batches.

| aspect | campaign setting |
|---|---|
| GPU topology | one NVIDIA L40S per physical job |
| seed and determinism | seed 0; deterministic algorithms not forced; fixed seeds and full provenance are retained |
| precision | bf16-mixed |
| input pipeline | 8 CPU data-loader workers per job; model-specific crop and batching are below |
| optimizer | AdamW, betas 0.9/0.999, weight decay 0.05; backbone LR and layer-wise decay are model-specific below; fresh task components use 10x LR |
| LR schedule | 1,500-iteration linear warmup from ratio 1e-6, then per-iteration polynomial decay with power 0.9; gradient clipping 1.0 |
| EMA and cadence | EMA decay 0.9998; validation and periodic checkpoint every 4,000 optimizer iterations |
| augmentation | random scale 0.5-2.0, crop, horizontal flip p=0.5, and color jitter p=0.5; crop size is model-specific below |
| dense objectives | standalone Cityscapes CE; RailSem19-only and transfer adaptation CE + 0.5 Lovasz |
| EoMT query objective | Hungarian class/mask assignment with class/mask-BCE/Dice weights 2/5/5 and 8,192 matching points |
| protocol budgets | Cityscapes 40,000; RailSem19 40,000; transfer 20,000 RailSem19 adaptation iterations |
| transfer initialization | reuse the matching 40,000-iteration Cityscapes checkpoint, reset only the incompatible classifier, and train RailSem19 for 20,000 iterations at 0.1x learning rate |
| interruption recovery | same-attempt full-state resume from newest validated periodic checkpoint; fresh attempt only when no recovery checkpoint exists |
| final quality evaluation | final EMA, batch 1, 1024x1024 sliding window, stride 768, no TTA |

### Model-specific optimizer and batching settings

The fresh-component LR is the initial LR for newly initialized heads or adapters. Transfer adaptation applies the documented 0.1x stage multiplier to both backbone and fresh-component groups.

| model | train crop | batch/GPU | accumulation | effective batch | backbone LR | fresh-component LR | LLRD | objective |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| [eomt_dinov3_large](../../catalog/models/builtin-eomt-dinov3-large/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-5 | 1.0e-4 | 0.75 | Hungarian query |
| [eomt_large](../../catalog/models/builtin-eomt-large/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-5 | 1.0e-4 | 0.75 | Hungarian query |
| [hf_auto_beit_base_ade](../../catalog/models/hf-auto-beit-base-ade/README.md) | 640x640 | 4 | 4 | 16 | 2.0e-5 | 2.0e-4 | 0.80 | dense semantic |
| [upernet_convnext](../../catalog/models/builtin-upernet-convnext/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [segformer_b5](../../catalog/models/builtin-segformer-b5/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [hf_auto_upernet_swin_tiny](../../catalog/models/hf-auto-upernet-swin-tiny/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 0.90 | dense semantic |
| [hrnet_w48_ocr](../../catalog/models/builtin-hrnet-w48-ocr/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet101_uper](../../catalog/models/native-resnet101-uper/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [segformer_b2](../../catalog/models/builtin-segformer-b2/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [smp_upernet_resnet101](../../catalog/models/smp-upernet-resnet101/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_deeplabv3plus_resnet101](../../catalog/models/smp-deeplabv3plus-resnet101/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [deeplabv3plus_r101](../../catalog/models/builtin-deeplabv3plus-r101-alias/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_convnext_tiny_uper](../../catalog/models/native-convnext-tiny-uper/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_convnext_tiny_channelmapper_dpt](../../catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_pan_resnext50](../../catalog/models/smp-pan-resnext50/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet50_deeplabv3plus](../../catalog/models/native-resnet50-deeplabv3plus/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet50_fpn_ocr](../../catalog/models/native-resnet50-fpn-ocr/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet50_psp](../../catalog/models/native-resnet50-psp/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet50_aspp](../../catalog/models/native-resnet50-aspp/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_deeplabv3_resnet50](../../catalog/models/smp-deeplabv3-resnet50/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_fpn_resnet50](../../catalog/models/smp-fpn-resnet50/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_upernet_mit_b0](../../catalog/models/smp-upernet-mit-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [segformer_b0](../../catalog/models/builtin-segformer-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [hf_auto_segformer_b0](../../catalog/models/hf-auto-segformer-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 6.0e-5 | 6.0e-4 | 1.00 | dense semantic |
| [smp_unet_resnet34](../../catalog/models/smp-unet-resnet34/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_unetplusplus_efficientnet_b0](../../catalog/models/smp-unetplusplus-efficientnet-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_manet_efficientnet_b0](../../catalog/models/smp-manet-efficientnet-b0/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_efficientnet_b0_deeplabv3plus](../../catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [hf_auto_mobilevitv2_deeplabv3](../../catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [hf_auto_mobilevit_xxs_deeplabv3](../../catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [hf_auto_mobilenetv2_deeplabv3](../../catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_mobilenetv3_large_deeplabv3plus](../../catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_mobilenetv3_large_lraspp](../../catalog/models/native-mobilenetv3-large-lraspp/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_pspnet_mobilenet_v2](../../catalog/models/smp-pspnet-mobilenet-v2/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [smp_linknet_mobilenet_v2](../../catalog/models/smp-linknet-mobilenet-v2/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet18_fpn_segformer_aux](../../catalog/models/native-resnet18-fpn-segformer-aux/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |
| [native_resnet18_fpn_fcn](../../catalog/models/native-resnet18-fpn-fcn/README.md) | 1024x1024 | 2 | 8 | 16 | 1.0e-4 | 1.0e-3 | 1.00 | dense semantic |

## Quality

| priority | model | status | Cityscapes mIoU (iterations) | RailSem19 mIoU (iterations) | Cityscapes → RailSem19 mIoU (iterations) |
|---:|---|---|---:|---:|---:|
| 1 | [eomt_dinov3_large](../../catalog/models/builtin-eomt-dinov3-large/README.md) | complete | 82.96 (40,000/40,000) | 71.42 (40,000/40,000) | 66.61 (20,000/20,000) |
| 2 | [eomt_large](../../catalog/models/builtin-eomt-large/README.md) | running | 82.74 (40,000/40,000) | — | 67.92 (20,000/20,000) |
| 3 | [hf_auto_beit_base_ade](../../catalog/models/hf-auto-beit-base-ade/README.md) | running | 57.26 (40,000/40,000) | — | 49.89 (20,000/20,000) |
| 4 | [upernet_convnext](../../catalog/models/builtin-upernet-convnext/README.md) | complete | 81.03 (40,000/40,000) | 70.74 (40,000/40,000) | 67.97 (20,000/20,000) |
| 5 | [segformer_b5](../../catalog/models/builtin-segformer-b5/README.md) | running | — | 71.95 (40,000/40,000) | — |
| 6 | [hf_auto_upernet_swin_tiny](../../catalog/models/hf-auto-upernet-swin-tiny/README.md) | running | — | — | — |
| 7 | [hrnet_w48_ocr](../../catalog/models/builtin-hrnet-w48-ocr/README.md) | running | — | — | — |
| 8 | [native_resnet101_uper](../../catalog/models/native-resnet101-uper/README.md) | running | 78.46 (40,000/40,000) | — | 64.26 (20,000/20,000) |
| 9 | [segformer_b2](../../catalog/models/builtin-segformer-b2/README.md) | running | 80.65 (40,000/40,000) | — | 65.71 (20,000/20,000) |
| 10 | [smp_upernet_resnet101](../../catalog/models/smp-upernet-resnet101/README.md) | running | — | 66.82 (40,000/40,000) | — |
| 11 | [smp_deeplabv3plus_resnet101](../../catalog/models/smp-deeplabv3plus-resnet101/README.md) | queued | — | — | — |
| 12 | [deeplabv3plus_r101](../../catalog/models/builtin-deeplabv3plus-r101-alias/README.md) | queued | — | — | — |
| 13 | [native_convnext_tiny_uper](../../catalog/models/native-convnext-tiny-uper/README.md) | running | — | — | — |
| 14 | [native_convnext_tiny_channelmapper_dpt](../../catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) | running | — | — | — |
| 15 | [smp_pan_resnext50](../../catalog/models/smp-pan-resnext50/README.md) | queued | — | — | — |
| 16 | [native_resnet50_deeplabv3plus](../../catalog/models/native-resnet50-deeplabv3plus/README.md) | queued | — | — | — |
| 17 | [native_resnet50_fpn_ocr](../../catalog/models/native-resnet50-fpn-ocr/README.md) | running | 78.73 (40,000/40,000) | — | 61.77 (20,000/20,000) |
| 18 | [native_resnet50_psp](../../catalog/models/native-resnet50-psp/README.md) | queued | — | — | — |
| 19 | [native_resnet50_aspp](../../catalog/models/native-resnet50-aspp/README.md) | queued | — | — | — |
| 20 | [smp_deeplabv3_resnet50](../../catalog/models/smp-deeplabv3-resnet50/README.md) | running | — | — | — |
| 21 | [smp_fpn_resnet50](../../catalog/models/smp-fpn-resnet50/README.md) | queued | — | — | — |
| 22 | [smp_upernet_mit_b0](../../catalog/models/smp-upernet-mit-b0/README.md) | queued | — | — | — |
| 23 | [segformer_b0](../../catalog/models/builtin-segformer-b0/README.md) | queued | — | — | — |
| 24 | [hf_auto_segformer_b0](../../catalog/models/hf-auto-segformer-b0/README.md) | queued | — | — | — |
| 25 | [smp_unet_resnet34](../../catalog/models/smp-unet-resnet34/README.md) | queued | — | — | — |
| 26 | [smp_unetplusplus_efficientnet_b0](../../catalog/models/smp-unetplusplus-efficientnet-b0/README.md) | queued | — | — | — |
| 27 | [smp_manet_efficientnet_b0](../../catalog/models/smp-manet-efficientnet-b0/README.md) | queued | — | — | — |
| 28 | [native_efficientnet_b0_deeplabv3plus](../../catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) | queued | — | — | — |
| 29 | [hf_auto_mobilevitv2_deeplabv3](../../catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) | queued | — | — | — |
| 30 | [hf_auto_mobilevit_xxs_deeplabv3](../../catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) | queued | — | — | — |
| 31 | [hf_auto_mobilenetv2_deeplabv3](../../catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) | queued | — | — | — |
| 32 | [native_mobilenetv3_large_deeplabv3plus](../../catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) | queued | — | — | — |
| 33 | [native_mobilenetv3_large_lraspp](../../catalog/models/native-mobilenetv3-large-lraspp/README.md) | queued | — | — | — |
| 34 | [smp_pspnet_mobilenet_v2](../../catalog/models/smp-pspnet-mobilenet-v2/README.md) | queued | — | — | — |
| 35 | [smp_linknet_mobilenet_v2](../../catalog/models/smp-linknet-mobilenet-v2/README.md) | queued | — | — | — |
| 36 | [native_resnet18_fpn_segformer_aux](../../catalog/models/native-resnet18-fpn-segformer-aux/README.md) | queued | — | — | — |
| 37 | [native_resnet18_fpn_fcn](../../catalog/models/native-resnet18-fpn-fcn/README.md) | queued | — | — | — |

## Standardized model-only inference

Each unique physical model is measured exactly once from its RailSem19-only 21-class final EMA checkpoint. Contract: NVIDIA L40S, PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed iterations. It includes internal query-to-dense collapse and excludes I/O, preprocessing, sliding windows, argmax, and metrics.
The benchmark runs only after that model's RailSem19 training and final quality evaluation succeed, so FPS can remain pending while Cityscapes mIoU is already available.

Weight memory is the resident parameter tensors; the resume checkpoint also contains optimizer and EMA state; peak VRAM is allocator-reserved memory excluding the CUDA context.

| model | parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak VRAM (reserved, excl. context) |
|---|---:|---:|---:|---:|---:|---:|---:|
| [eomt_dinov3_large](../../catalog/models/builtin-eomt-dinov3-large/README.md) | 314,917,910 | 1201.3 MiB | 4805.9 MiB | 40.92 | 24.24 | 25.57 | 3.13 GiB |
| [eomt_large](../../catalog/models/builtin-eomt-large/README.md) | — | — | — | — | — | — | — |
| [hf_auto_beit_base_ade](../../catalog/models/hf-auto-beit-base-ade/README.md) | — | — | — | — | — | — | — |
| [upernet_convnext](../../catalog/models/builtin-upernet-convnext/README.md) | 80,887,221 | 308.6 MiB | 1235.0 MiB | 42.35 | 23.53 | 24.03 | 2.48 GiB |
| [segformer_b5](../../catalog/models/builtin-segformer-b5/README.md) | 84,609,493 | 322.8 MiB | 1292.9 MiB | 25.13 | 39.28 | 43.62 | 2.57 GiB |
| [hf_auto_upernet_swin_tiny](../../catalog/models/hf-auto-upernet-swin-tiny/README.md) | — | — | — | — | — | — | — |
| [hrnet_w48_ocr](../../catalog/models/builtin-hrnet-w48-ocr/README.md) | — | — | — | — | — | — | — |
| [native_resnet101_uper](../../catalog/models/native-resnet101-uper/README.md) | — | — | — | — | — | — | — |
| [segformer_b2](../../catalog/models/builtin-segformer-b2/README.md) | — | — | — | — | — | — | — |
| [smp_upernet_resnet101](../../catalog/models/smp-upernet-resnet101/README.md) | 56,281,941 | 214.7 MiB | 860.4 MiB | 72.48 | 13.70 | 14.30 | 1.44 GiB |
| [smp_deeplabv3plus_resnet101](../../catalog/models/smp-deeplabv3plus-resnet101/README.md) | — | — | — | — | — | — | — |
| [deeplabv3plus_r101](../../catalog/models/builtin-deeplabv3plus-r101-alias/README.md) | — | — | — | — | — | — | — |
| [native_convnext_tiny_uper](../../catalog/models/native-convnext-tiny-uper/README.md) | — | — | — | — | — | — | — |
| [native_convnext_tiny_channelmapper_dpt](../../catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) | — | — | — | — | — | — | — |
| [smp_pan_resnext50](../../catalog/models/smp-pan-resnext50/README.md) | — | — | — | — | — | — | — |
| [native_resnet50_deeplabv3plus](../../catalog/models/native-resnet50-deeplabv3plus/README.md) | — | — | — | — | — | — | — |
| [native_resnet50_fpn_ocr](../../catalog/models/native-resnet50-fpn-ocr/README.md) | — | — | — | — | — | — | — |
| [native_resnet50_psp](../../catalog/models/native-resnet50-psp/README.md) | — | — | — | — | — | — | — |
| [native_resnet50_aspp](../../catalog/models/native-resnet50-aspp/README.md) | — | — | — | — | — | — | — |
| [smp_deeplabv3_resnet50](../../catalog/models/smp-deeplabv3-resnet50/README.md) | — | — | — | — | — | — | — |
| [smp_fpn_resnet50](../../catalog/models/smp-fpn-resnet50/README.md) | — | — | — | — | — | — | — |
| [smp_upernet_mit_b0](../../catalog/models/smp-upernet-mit-b0/README.md) | — | — | — | — | — | — | — |
| [segformer_b0](../../catalog/models/builtin-segformer-b0/README.md) | — | — | — | — | — | — | — |
| [hf_auto_segformer_b0](../../catalog/models/hf-auto-segformer-b0/README.md) | — | — | — | — | — | — | — |
| [smp_unet_resnet34](../../catalog/models/smp-unet-resnet34/README.md) | — | — | — | — | — | — | — |
| [smp_unetplusplus_efficientnet_b0](../../catalog/models/smp-unetplusplus-efficientnet-b0/README.md) | — | — | — | — | — | — | — |
| [smp_manet_efficientnet_b0](../../catalog/models/smp-manet-efficientnet-b0/README.md) | — | — | — | — | — | — | — |
| [native_efficientnet_b0_deeplabv3plus](../../catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) | — | — | — | — | — | — | — |
| [hf_auto_mobilevitv2_deeplabv3](../../catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) | — | — | — | — | — | — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](../../catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) | — | — | — | — | — | — | — |
| [hf_auto_mobilenetv2_deeplabv3](../../catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_deeplabv3plus](../../catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) | — | — | — | — | — | — | — |
| [native_mobilenetv3_large_lraspp](../../catalog/models/native-mobilenetv3-large-lraspp/README.md) | — | — | — | — | — | — | — |
| [smp_pspnet_mobilenet_v2](../../catalog/models/smp-pspnet-mobilenet-v2/README.md) | — | — | — | — | — | — | — |
| [smp_linknet_mobilenet_v2](../../catalog/models/smp-linknet-mobilenet-v2/README.md) | — | — | — | — | — | — | — |
| [native_resnet18_fpn_segformer_aux](../../catalog/models/native-resnet18-fpn-segformer-aux/README.md) | — | — | — | — | — | — | — |
| [native_resnet18_fpn_fcn](../../catalog/models/native-resnet18-fpn-fcn/README.md) | — | — | — | — | — | — | — |

## Training cost

Wall time and GPU-hours include every curriculum stage; peak is per-device allocator-reserved training VRAM.

| model | Cityscapes wall / GPU-h | RailSem19 wall / GPU-h | transfer wall / GPU-h | peak train VRAM |
|---|---:|---:|---:|---:|
| [eomt_dinov3_large](../../catalog/models/builtin-eomt-dinov3-large/README.md) | 14h 06m 17s / 14.10 | 13h 41m 29s / 13.69 | 7h 41m 23s / 7.69 | 17.02 GiB |
| [eomt_large](../../catalog/models/builtin-eomt-large/README.md) | 13h 26m 42s / 13.45 | — / — | 7h 17m 52s / 7.30 | 16.86 GiB |
| [hf_auto_beit_base_ade](../../catalog/models/hf-auto-beit-base-ade/README.md) | 14h 40m 07s / 14.67 | — / — | 11h 00m 38s / 11.01 | 19.53 GiB |
| [upernet_convnext](../../catalog/models/builtin-upernet-convnext/README.md) | 13h 28m 59s / 13.48 | 16h 57m 54s / 16.96 | 9h 25m 59s / 9.43 | 10.60 GiB |
| [segformer_b5](../../catalog/models/builtin-segformer-b5/README.md) | — / — | 19h 38m 19s / 19.64 | — / — | 16.94 GiB |
| [hf_auto_upernet_swin_tiny](../../catalog/models/hf-auto-upernet-swin-tiny/README.md) | — / — | — / — | — / — | — |
| [hrnet_w48_ocr](../../catalog/models/builtin-hrnet-w48-ocr/README.md) | — / — | — / — | — / — | — |
| [native_resnet101_uper](../../catalog/models/native-resnet101-uper/README.md) | 7h 54m 19s / 7.91 | — / — | 6h 49m 53s / 6.83 | 6.85 GiB |
| [segformer_b2](../../catalog/models/builtin-segformer-b2/README.md) | 8h 10m 00s / 8.17 | — / — | 7h 09m 12s / 7.15 | 12.12 GiB |
| [smp_upernet_resnet101](../../catalog/models/smp-upernet-resnet101/README.md) | — / — | 12h 55m 26s / 12.92 | — / — | 6.70 GiB |
| [smp_deeplabv3plus_resnet101](../../catalog/models/smp-deeplabv3plus-resnet101/README.md) | — / — | — / — | — / — | — |
| [deeplabv3plus_r101](../../catalog/models/builtin-deeplabv3plus-r101-alias/README.md) | — / — | — / — | — / — | — |
| [native_convnext_tiny_uper](../../catalog/models/native-convnext-tiny-uper/README.md) | — / — | — / — | — / — | — |
| [native_convnext_tiny_channelmapper_dpt](../../catalog/models/native-convnext-tiny-channelmapper-dpt/README.md) | — / — | — / — | — / — | — |
| [smp_pan_resnext50](../../catalog/models/smp-pan-resnext50/README.md) | — / — | — / — | — / — | — |
| [native_resnet50_deeplabv3plus](../../catalog/models/native-resnet50-deeplabv3plus/README.md) | — / — | — / — | — / — | — |
| [native_resnet50_fpn_ocr](../../catalog/models/native-resnet50-fpn-ocr/README.md) | 12h 42m 58s / 12.72 | — / — | 11h 27m 30s / 11.46 | 8.59 GiB |
| [native_resnet50_psp](../../catalog/models/native-resnet50-psp/README.md) | — / — | — / — | — / — | — |
| [native_resnet50_aspp](../../catalog/models/native-resnet50-aspp/README.md) | — / — | — / — | — / — | — |
| [smp_deeplabv3_resnet50](../../catalog/models/smp-deeplabv3-resnet50/README.md) | — / — | — / — | — / — | — |
| [smp_fpn_resnet50](../../catalog/models/smp-fpn-resnet50/README.md) | — / — | — / — | — / — | — |
| [smp_upernet_mit_b0](../../catalog/models/smp-upernet-mit-b0/README.md) | — / — | — / — | — / — | — |
| [segformer_b0](../../catalog/models/builtin-segformer-b0/README.md) | — / — | — / — | — / — | — |
| [hf_auto_segformer_b0](../../catalog/models/hf-auto-segformer-b0/README.md) | — / — | — / — | — / — | — |
| [smp_unet_resnet34](../../catalog/models/smp-unet-resnet34/README.md) | — / — | — / — | — / — | — |
| [smp_unetplusplus_efficientnet_b0](../../catalog/models/smp-unetplusplus-efficientnet-b0/README.md) | — / — | — / — | — / — | — |
| [smp_manet_efficientnet_b0](../../catalog/models/smp-manet-efficientnet-b0/README.md) | — / — | — / — | — / — | — |
| [native_efficientnet_b0_deeplabv3plus](../../catalog/models/native-efficientnet-b0-deeplabv3plus/README.md) | — / — | — / — | — / — | — |
| [hf_auto_mobilevitv2_deeplabv3](../../catalog/models/hf-auto-mobilevitv2-deeplabv3/README.md) | — / — | — / — | — / — | — |
| [hf_auto_mobilevit_xxs_deeplabv3](../../catalog/models/hf-auto-mobilevit-xxs-deeplabv3/README.md) | — / — | — / — | — / — | — |
| [hf_auto_mobilenetv2_deeplabv3](../../catalog/models/hf-auto-mobilenetv2-deeplabv3/README.md) | — / — | — / — | — / — | — |
| [native_mobilenetv3_large_deeplabv3plus](../../catalog/models/native-mobilenetv3-large-deeplabv3plus/README.md) | — / — | — / — | — / — | — |
| [native_mobilenetv3_large_lraspp](../../catalog/models/native-mobilenetv3-large-lraspp/README.md) | — / — | — / — | — / — | — |
| [smp_pspnet_mobilenet_v2](../../catalog/models/smp-pspnet-mobilenet-v2/README.md) | — / — | — / — | — / — | — |
| [smp_linknet_mobilenet_v2](../../catalog/models/smp-linknet-mobilenet-v2/README.md) | — / — | — / — | — / — | — |
| [native_resnet18_fpn_segformer_aux](../../catalog/models/native-resnet18-fpn-segformer-aux/README.md) | — / — | — / — | — / — | — |
| [native_resnet18_fpn_fcn](../../catalog/models/native-resnet18-fpn-fcn/README.md) | — / — | — / — | — / — | — |

## Fixed protocol and files

- Cityscapes: 40,000 iterations, standard 19-class 500-image validation.
- RailSem19: 40,000 iterations, `rail_union`, fixed 850-image validation.
- Transfer: reuse the matching 40,000-iteration Cityscapes checkpoint, then run 20,000 RailSem19 adaptation iterations; Cityscapes is never trained twice.
- Transfer warm-starts every compatible learned tensor and reinitialises only the 19-class to `rail_union` classifier mismatch.
- Quality evaluation: EMA, 1024x1024 sliding window, stride 768, no TTA.
- [`results.csv`](results.csv): spreadsheet-friendly mean metrics, iterations, and resources.
- [`status.json`](status.json): machine-readable scope and completion state.
- [`records/`](records/): full class IoUs, retained seeds, resources, and provenance.

Campaign source SHA: `db1e951f289fc6c09294e9a019945695ad2d94d2`.
