# DynUNet budget and resolution comparisons against the fresh control

[Model comparison](README.md) | [Aggregate data](paired-comparisons.json)

Each entry is candidate minus control in Dice percentage points. Positive values favor the candidate. Brackets show a pointwise 95% percentile bootstrap interval from 10,000 resamples of the same 42 provided case groups. All arms use seed 0 and their selected best validation checkpoint.

| Candidate | Mass Dice difference (95% CI), points | Pancreas Dice difference (95% CI), points |
| --- | ---: | ---: |
| dynunet-long30k-seed0 | +0.818 [-4.457, +5.415] | -2.968 [-5.350, -0.844] |
| dynunet-fine10k-seed0 | -4.786 [-10.265, -0.055] | -2.790 [-4.518, -1.015] |

Interpretation limits:

- Exploratory same-seed validation comparisons, not held-out or external confirmation.
- Validation selected the checkpoints and may select an arm; intervals do not correct selection optimism.
- Four pointwise 95% bootstrap intervals are not adjusted for multiple comparisons.
- Intervals resample provided case/patient groups and do not include training-seed uncertainty.
- Long30k changes the complete learning-rate schedule and uses three times as many updates; this is not an equal-compute comparison.
- Fine10k uses 1.0/1.0/2.5-mm spacing and a 96x144x144 patch versus 1.5/1.5/2.5 mm and 96 cubed; nominal physical context matches, voxel count and cost differ.
- Each arm selects its own best validation checkpoint; selected-best differences are exploratory and not an independent test.
- Mass labels do not establish pancreatic cancer diagnosis.
- Dataset-case groups are not verified independent patient identities.
- This compares different training budgets or voxel grids within DynUNet, not an equal-budget architecture ranking or clinical cancer-detection performance.

Source commit: `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`. Bootstrap seed: `20260914`.
