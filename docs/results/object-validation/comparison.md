# Object segmentation model comparison

Scores are percentages. Rows are grouped by task and exact dataset fingerprint; each model links to its full report. Input size, thresholds and hardware are recorded on the model pages. Review those settings before interpreting speed or accuracy differences.

## Instance — dataset `8eab3195d7ce3d2e1b37698e14d2f7d95a1286df2c54d596cf90a59e0a2ec2a3`

| Model | Mask AP | AP50 | AP75 | Model FPS | End-to-end FPS | Peak allocated GiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [Mask2Former Swin-T / Cityscapes instance](mask2former-swin-tiny-cityscapes-instance/README.md) | 53.21 | 82.10 | 56.34 | 12.35 | 3.69 | 0.87 |

## Panoptic — dataset `8afd01b628c2b183cb6a233321a464b4e443437362f413f6bfa2f1d1c37f3dab`

| Model | PQ | SQ | RQ | Model FPS | End-to-end FPS | Peak allocated GiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [Mask2Former Swin-T / Cityscapes panoptic](mask2former-swin-tiny-cityscapes-panoptic/README.md) | 76.27 | 83.52 | 90.30 | 11.46 | 3.30 | 0.84 |
