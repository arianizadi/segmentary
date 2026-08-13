# Model comparison: Cityscapes and RailSem19

This is the live comparison folder for every shipped Segmentary model recipe. Completed compatible results are imported instead of retrained; missing cells run in best-first order. Every long job runs in a named detached tmux session.

Values are mean percent mIoU. Parentheses show completed training iterations;
the transfer total is the sum of both stages. `—` means the result does not exist
yet—not zero and not a failure. Detailed machine records retain individual seeds,
while this human-facing table deliberately shows one clean number.

| priority | model | status | Cityscapes mIoU (iterations) | RailSem19 mIoU (iterations) | Cityscapes → RailSem19 mIoU (iterations) |
|---:|---|---|---:|---:|---:|
| 1 | `eomt_dinov3_large` | queued | — | — | — |
| 2 | `eomt_large` | queued | — | — | — |
| 3 | `hf_auto_beit_base_ade` | queued | — | — | — |
| 4 | `upernet_convnext` | queued | — | — | — |
| 5 | `segformer_b5` | queued | — | — | — |
| 6 | `hf_auto_upernet_swin_tiny` | queued | — | — | — |
| 7 | `hrnet_w48_ocr` | queued | — | — | — |
| 8 | `native_resnet101_uper` | queued | — | — | — |
| 9 | [`segformer_b2`](../../catalog/models/builtin-segformer-b2/README.md) | complete | 80.51 (40,000) | 70.47 (40,000) | 66.44 (60,000) |
| 10 | `deeplabv3plus_r101` | queued | — | — | — |
| 11 | `hf_auto_mobilenetv2_deeplabv3` | queued | — | — | — |
| 12 | `hf_auto_mobilevit_xxs_deeplabv3` | queued | — | — | — |
| 13 | `hf_auto_mobilevitv2_deeplabv3` | queued | — | — | — |
| 14 | `hf_auto_segformer_b0` | queued | — | — | — |
| 15 | `native_convnext_tiny_channelmapper_dpt` | queued | — | — | — |
| 16 | `native_convnext_tiny_uper` | queued | — | — | — |
| 17 | `native_efficientnet_b0_deeplabv3plus` | queued | — | — | — |
| 18 | `native_mobilenetv3_large_deeplabv3plus` | queued | — | — | — |
| 19 | `native_mobilenetv3_large_lraspp` | queued | — | — | — |
| 20 | `native_resnet18_fpn_fcn` | queued | — | — | — |
| 21 | `native_resnet18_fpn_segformer_aux` | queued | — | — | — |
| 22 | `native_resnet50_aspp` | queued | — | — | — |
| 23 | `native_resnet50_deeplabv3plus` | queued | — | — | — |
| 24 | `native_resnet50_fpn_ocr` | queued | — | — | — |
| 25 | `native_resnet50_psp` | queued | — | — | — |
| 26 | `segformer_b0` | queued | — | — | — |
| 27 | `smp_deeplabv3_resnet50` | queued | — | — | — |
| 28 | `smp_deeplabv3plus_resnet101` | queued | — | — | — |
| 29 | `smp_fpn_resnet50` | queued | — | — | — |
| 30 | `smp_linknet_mobilenet_v2` | queued | — | — | — |
| 31 | `smp_manet_efficientnet_b0` | queued | — | — | — |
| 32 | `smp_pan_resnext50` | queued | — | — | — |
| 33 | `smp_pspnet_mobilenet_v2` | queued | — | — | — |
| 34 | `smp_unet_resnet34` | queued | — | — | — |
| 35 | `smp_unetplusplus_efficientnet_b0` | queued | — | — | — |
| 36 | `smp_upernet_mit_b0` | queued | — | — | — |
| 37 | `smp_upernet_resnet101` | queued | — | — | — |

## Fixed comparison protocol

- **Cityscapes:** standard 19-class validation protocol, 40,000 training steps, complete 500-image validation split.
- **RailSem19:** `rail_union`, 40,000 training steps, fixed 6,800/850/850 split, complete 850-image validation split.
- **Cityscapes → RailSem19:** 40,000 Cityscapes steps followed by 20,000 RailSem19 steps at one-tenth learning rate without resetting the shared head, then the same 850-image validation split.
- **Evaluation:** final EMA, 1024×1024 sliding window, stride 768, no TTA.
- **Seeds:** missing cells use seed 0. Existing compatible extra seeds remain visible and are never discarded.

The staged transfer result's 60,000 total iterations are 40,000 on Cityscapes
plus 20,000 on RailSem19. Its final RailSem19 checkpoint therefore correctly
records final-stage `global_step=20,000`.

## Efficiency evidence

These are historical training measurements from the exact result records, not
the standardized inference benchmark. Multi-seed wall time and GPU-hours are
means per run. A dash means the measurement is intentionally still pending.

| model / protocol | parameters | final checkpoint | train wall / run | GPU-hours / run | peak train VRAM / GPU | inference FPS | latency | inference VRAM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SegFormer-B2 / Cityscapes | 27,362,772 | — | 1h 37m 16s | 12.97 | 11.83 GiB | — | — | — |
| SegFormer-B2 / RailSem19 | 27,364,310 | 418.1 MiB | 3h 33m 10s | 14.21 | 21.95 GiB | — | — | — |
| SegFormer-B2 / Cityscapes → RailSem19 | 27,364,310 | 418.1 MiB | 5h 14m 02s | 20.94 | 21.95 GiB | — | — | — |

Standardized inference FPS, latency, and inference VRAM are pending one shared
benchmark protocol across all models. They are left blank rather than mixing in
measurements made with different inputs or runtime settings. The exact
40,000-iteration Cityscapes checkpoint was not retained, so its final checkpoint
size is also unavailable.

The older three-seed Cityscapes stage from the rail-transfer case study used
the 21-channel `rail_union` space, so it is intentionally excluded from the
standard Cityscapes-19 column. The retained `80.51` result is the comparable
19-class endpoint.

## Files

- [`results.csv`](results.csv): compact spreadsheet-friendly leaderboard/status table.
- [`status.json`](status.json): machine-readable scope and completion state.
- [`records/segformer_b2.json`](records/segformer_b2.json): normalized aggregate, individual seeds, all class IoUs/support, and source/checkpoint hashes for the reused model.

Compatibility/admission probes are not quality results and never populate this table. The DeepLabV3+/R101 compatibility alias shares one physical training result with its explicit SMP recipe, avoiding duplicate training.
