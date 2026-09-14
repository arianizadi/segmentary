# Exact official test scores

All values are percentages; these are four selected submissions on 139 official test examinations.

| Submission | Mean mass Dice | Median mass Dice | Mass Dice IQR | Pancreas L1 Dice | Mass NSD | Zero mass Dice |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| [CancerVerse (QiC99)](https://decathlon-10.grand-challenge.org/evaluation/279a2fee-693e-4de0-8c9b-fd16c8c4722e/) | 67.16 | 76.32 | 56.89-83.89 | 81.78 | 86.05 | 7/139 |
| [Universal Model (zongwei.zhou)](https://decathlon-10.grand-challenge.org/evaluation/02791173-6108-423f-8061-522560778cda/) | 62.33 | 73.15 | 49.02-82.11 | 82.85 | 82.87 | 10/139 |
| [Swin_UNETR submission](https://decathlon-10.grand-challenge.org/evaluation/ca86ba5f-9e5c-44c5-8f8d-8771a8b6a8fd/) | 58.22 | 68.72 | 43.75-79.73 | 81.85 | 79.10 | 13/139 |
| [Isensee submission (historical nnU-Net reference)](https://decathlon-10.grand-challenge.org/evaluation/e7503ac3-57b3-44a1-b448-b76314701b02/) | 52.78 | 64.07 | 18.68-79.85 | 81.64 | 71.47 | 27/139 |

# Our completed 10,000-update screening runs

These use 197 training and 42 validation examinations, one scratch seed, and a selected validation checkpoint. Pancreas here means labels 1 OR 2. Do not rank this table together with the official test table. Our ongoing official-backend ResEnc L run has no final native score yet.

| Model | Mass Dice | Pancreas union Dice |
| --- | ---: | ---: |
| [umamba_enc](../performance-continuation-20260914/models/umamba_enc-seed0.md) | 35.71 | 75.41 |
| [segmamba](../performance-continuation-20260914/models/segmamba-seed0.md) | 32.12 | 73.55 |
| [umamba_bot](../performance-continuation-20260914/models/umamba_bot-seed0.md) | 32.16 | 72.76 |
| [swin_unetr](../performance-continuation-20260914/models/swin_unetr-seed0.md) | 24.46 | 70.45 |
| [unetr](../performance-continuation-20260914/models/unetr-seed0.md) | 11.16 | 48.10 |
| [transunet_3d](../performance-continuation-20260914/models/transunet_3d-seed0.md) | 31.01 | 73.54 |
| [medformer](../performance-continuation-20260914/models/medformer-seed0.md) | 32.72 | 71.87 |
| [mednext_v1](../performance-continuation-20260914/models/mednext_v1-seed0.md) | 28.45 | 68.88 |
| [dynunet](../performance-continuation-20260914/models/dynunet-seed0.md) | 32.98 | 75.59 |
| [segresnet](../performance-continuation-20260914/models/segresnet-seed0.md) | 30.90 | 66.10 |
| [unet_3d](../performance-continuation-20260914/models/unet_3d-seed0.md) | 18.33 | 60.84 |
| [mask2former](../performance-continuation-20260914/models/mask2former-seed0.md) | 14.90 | 58.44 |
| [maskformer](../performance-continuation-20260914/models/maskformer-seed0.md) | 0.05 | 0.44 |
| [dpt](../performance-continuation-20260914/models/dpt-seed0.md) | 6.37 | 36.44 |
| [swin_upernet](../performance-continuation-20260914/models/swin_upernet-seed0.md) | 13.91 | 53.48 |
| [convnext_upernet](../performance-continuation-20260914/models/convnext_upernet-seed0.md) | 12.78 | 64.05 |
| [segformer_b2](../performance-continuation-20260914/models/segformer_b2-seed0.md) | 12.18 | 33.13 |
| [hrnet_ocr](../performance-continuation-20260914/models/hrnet_ocr-seed0.md) | 17.01 | 66.18 |
| [unet_plus_plus](../performance-continuation-20260914/models/unet_plus_plus-seed0.md) | 26.01 | 67.22 |
| [deeplabv3_plus](../performance-continuation-20260914/models/deeplabv3_plus-seed0.md) | 25.98 | 62.29 |
| [fpn](../performance-continuation-20260914/models/fpn-seed0.md) | 23.99 | 63.82 |
| [unet_2d](../performance-continuation-20260914/models/unet_2d-seed0.md) | 25.55 | 66.31 |
| [segformer_b0](../performance-continuation-20260914/models/segformer_b0-seed0.md) | 11.56 | 44.08 |
| [pidnet](../performance-continuation-20260914/models/pidnet-seed0.md) | 3.24 | 57.57 |
| [ddrnet](../performance-continuation-20260914/models/ddrnet-seed0.md) | 8.06 | 52.69 |
| [bisenetv2](../performance-continuation-20260914/models/bisenetv2-seed0.md) | 14.64 | 56.64 |
| [lraspp](../performance-continuation-20260914/models/lraspp-seed0.md) | 14.63 | 51.91 |

Source CSV SHA256: `4e3db93a2773404594cac9e75db21f1e8703f40a845e544a55feaea695b4e6d6`.

The local table is generated from the campaign's validated final-evaluation records, not patch-level training estimates. See [interpretation and limitations](README.md).
