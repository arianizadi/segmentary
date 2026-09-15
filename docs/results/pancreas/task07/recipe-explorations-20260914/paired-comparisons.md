# Task07 recipe exploration comparisons against the fresh control

[Model comparison](README.md) | [Aggregate data](paired-comparisons.json)

Each entry is candidate minus control in Dice percentage points. Positive values favor the candidate. Brackets show a pointwise 95% percentile bootstrap interval from 10,000 resamples of the same 42 provided case groups. All arms use seed 0 and their selected best validation checkpoint.

| Candidate | Mass Dice difference (95% CI), points | Pancreas Dice difference (95% CI), points |
| --- | ---: | ---: |
| dynunet-deep10k-seed0 | -2.296 [-6.323, +1.728] | -1.517 [-3.272, +0.243] |
| dynunet-focal05-seed0 | -1.270 [-7.103, +4.238] | -3.312 [-5.304, -1.544] |
| dynunet-focal10-seed0 | -0.600 [-6.279, +5.055] | -3.741 [-5.857, -1.848] |
| dynunet-window-seed0 | -3.457 [-8.720, +1.204] | -4.486 [-6.152, -2.897] |
| dynunet-minmax-seed0 | -2.318 [-7.977, +2.971] | -5.137 [-7.677, -2.944] |
| dynunet-isotropic-seed0 | +1.850 [-2.399, +6.655] | +0.100 [-1.318, +1.662] |
| swin_unetr-swin24-seed0 | -8.523 [-14.825, -3.008] | -5.138 [-7.685, -2.780] |
| swin_unetr-swin48-seed0 | -3.405 [-8.109, +0.863] | -1.885 [-3.760, -0.042] |

Interpretation limits:

- Exploratory same-seed validation comparisons, not held-out or external confirmation.
- Validation selected the checkpoints and may select an arm; intervals do not correct selection optimism.
- Pointwise 95% bootstrap intervals are not adjusted for multiple comparisons.
- Intervals resample provided case/patient groups and do not include training-seed uncertainty.
- All runs use 10,000 updates; compute and voxel exposure can differ. See each frozen arm declaration.
- Cascade training crops use in-sample stage-one predictions; out-of-fold confirmation remains future work. Full-native evaluation retains stage-one misses.
- Each arm selects its own best validation checkpoint; selected-best differences are exploratory and not an independent test.
- Mass labels do not establish pancreatic cancer diagnosis.
- Dataset-case groups are not verified independent patient identities.
- These are multiple exploratory validation comparisons, not an equal-compute architecture ranking or clinical cancer-detection assessment.

Source commit: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`. Bootstrap seed: `20260914`.
