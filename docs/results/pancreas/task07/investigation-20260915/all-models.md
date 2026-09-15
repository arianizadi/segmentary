# Completed model results at the investigation snapshot

All rows have 42/42 native validation predictions on the same frozen cases and references. Pancreas means the union of labels 1 and 2. Different recipes and budgets are separate experiments; this is not a causal architecture ranking. Repeated controls are deliberate controls, not independent seeds. Dataset cases serve as patient proxies; independent patient identity is unverified. The new Dice-reduction experiment is reported separately.

## task07-scratch-screen-20260913

| Run | Mass Dice | Pancreas Dice | Zero-overlap scans |
| --- | ---: | ---: | ---: |
| bisenetv2-seed0 | 14.64% | 56.64% | 16/42 |
| convnext_upernet-seed0 | 12.78% | 64.05% | 21/42 |
| ddrnet-seed0 | 8.06% | 52.69% | 21/42 |
| deeplabv3_plus-seed0 | 25.98% | 62.29% | 13/42 |
| dpt-seed0 | 6.37% | 36.44% | 23/42 |
| dynunet-seed0 | 32.98% | 75.59% | 12/42 |
| fpn-seed0 | 23.99% | 63.82% | 8/42 |
| hrnet_ocr-seed0 | 17.01% | 66.18% | 17/42 |
| lraspp-seed0 | 14.63% | 51.91% | 19/42 |
| mask2former-seed0 | 14.90% | 58.44% | 18/42 |
| maskformer-seed0 | 0.05% | 0.44% | 0/42 |
| medformer-seed0 | 32.72% | 71.87% | 12/42 |
| mednext_v1-seed0 | 28.45% | 68.88% | 13/42 |
| pidnet-seed0 | 3.24% | 57.57% | 33/42 |
| segformer_b0-seed0 | 11.56% | 44.08% | 16/42 |
| segformer_b2-seed0 | 12.18% | 33.13% | 15/42 |
| segmamba-seed0 | 32.12% | 73.55% | 12/42 |
| segresnet-seed0 | 30.90% | 66.10% | 11/42 |
| swin_unetr-seed0 | 24.46% | 70.45% | 14/42 |
| swin_upernet-seed0 | 13.91% | 53.48% | 15/42 |
| transunet_3d-seed0 | 31.01% | 73.54% | 14/42 |
| umamba_bot-seed0 | 32.16% | 72.76% | 13/42 |
| umamba_enc-seed0 | 35.71% | 75.41% | 13/42 |
| unet_2d-seed0 | 25.55% | 66.31% | 13/42 |
| unet_3d-seed0 | 18.33% | 60.84% | 19/42 |
| unet_plus_plus-seed0 | 26.01% | 67.22% | 10/42 |
| unetr-seed0 | 11.16% | 48.10% | 19/42 |

## task07-followup-20260914

| Run | Mass Dice | Pancreas Dice | Zero-overlap scans |
| --- | ---: | ---: | ---: |
| dynunet-control10k-seed0 | 32.98% | 75.59% | 12/42 |
| dynunet-fine10k-seed0 | 28.20% | 72.80% | 16/42 |
| dynunet-long30k-seed0 | 33.80% | 72.62% | 14/42 |

## task07-recipe-ablation-20260914

| Run | Mass Dice | Pancreas Dice | Zero-overlap scans |
| --- | ---: | ---: | ---: |
| dynunet-class111-seed0 | 30.23% | 75.73% | 17/42 |
| dynunet-class115-seed0 | 30.71% | 71.24% | 14/42 |
| dynunet-control-seed0 | 32.98% | 75.59% | 12/42 |
| dynunet-intensity-seed0 | 29.73% | 71.30% | 14/42 |
| dynunet-mass50-seed0 | 30.30% | 73.54% | 16/42 |
| dynunet-rotation-seed0 | 30.84% | 75.98% | 12/42 |

## task07-recipe-explorations-20260914

| Run | Mass Dice | Pancreas Dice | Zero-overlap scans |
| --- | ---: | ---: | ---: |
| dynunet-control10k-seed0 | 32.98% | 75.59% | 12/42 |
| dynunet-deep10k-seed0 | 30.69% | 74.07% | 18/42 |
| dynunet-focal05-seed0 | 31.71% | 72.28% | 13/42 |
| dynunet-focal10-seed0 | 32.38% | 71.85% | 11/42 |
| dynunet-isotropic-seed0 | 34.83% | 75.69% | 10/42 |
| dynunet-minmax-seed0 | 30.67% | 70.45% | 14/42 |
| dynunet-window-seed0 | 29.53% | 71.10% | 12/42 |
| swin_unetr-swin24-seed0 | 24.46% | 70.45% | 14/42 |
| swin_unetr-swin48-seed0 | 29.58% | 73.70% | 9/42 |

## task07-cascade-recovery-20260914

| Run | Mass Dice | Pancreas Dice | Zero-overlap scans |
| --- | ---: | ---: | ---: |
| dynunet-control10k-seed0 | 32.98% | 75.59% | 12/42 |
| dynunet-roi20-seed0 | 31.89% | 69.48% | 13/42 |
| dynunet-roi40-seed0 | 32.96% | 73.07% | 11/42 |

## Provisional nnU-Net snapshots

These immutable snapshots were evaluated while the original run continued. Keep its official checkpoint-selection rule; the later snapshot was not selected as a new winner.

| Snapshot | Mass Dice | Pancreas Dice | Zero-overlap scans |
| --- | ---: | ---: | ---: |
| Selected best, epoch 602 | 54.68% | 84.19% | 5/42 |
| Latest, epoch 900 | 55.90% | 84.12% | 7/42 |
