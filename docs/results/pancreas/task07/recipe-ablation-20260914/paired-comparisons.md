# DynUNet recipe comparisons against the control

[Model comparison](README.md) | [Aggregate data](paired-comparisons.json)

Each entry is candidate minus control in Dice percentage points. Positive values favor the candidate. Brackets show a pointwise 95% percentile bootstrap interval from 10,000 resamples of the same 42 provided case groups. All arms use seed 0 and their selected best validation checkpoint.

| Candidate | Mass Dice difference (95% CI), points | Pancreas Dice difference (95% CI), points |
| --- | ---: | ---: |
| dynunet-mass50-seed0 | -2.687 [-7.566, +1.925] | -2.054 [-3.483, -0.758] |
| dynunet-class111-seed0 | -2.752 [-8.100, +2.007] | +0.140 [-1.474, +1.714] |
| dynunet-class115-seed0 | -2.273 [-7.343, +2.235] | -4.347 [-6.576, -2.469] |
| dynunet-rotation-seed0 | -2.144 [-7.446, +2.627] | +0.387 [-1.047, +1.865] |
| dynunet-intensity-seed0 | -3.257 [-8.139, +1.571] | -4.285 [-6.787, -2.085] |

Interpretation limits:

- Exploratory same-seed validation comparisons, not held-out or external confirmation.
- Validation selected the checkpoints and may select an arm; intervals do not correct selection optimism.
- Ten pointwise 95% bootstrap intervals are not adjusted for multiple comparisons.
- Intervals resample provided case/patient groups and do not include training-seed uncertainty.
- Mass labels do not establish pancreatic cancer diagnosis.
- Dataset-case groups are not verified independent patient identities.
- This is a recipe comparison within DynUNet, not an architecture ranking or a claim of clinical cancer-detection performance.

Source commit: `9714becaed028d7f0b03e1cf1782f68eb8c52853`. Bootstrap seed: `20260914`.
