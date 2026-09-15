# Failure-analysis tools: real-data verification

Validated on all 42 reserved-development validation scans for six completed Task07 recipe arms. This is exploratory validation, not the reserved test or an external benchmark.

Source: `bbfa5bf19a52506cedf90309618b88cdf1870233`. All 252 case/model records passed native geometry, input hash, checkpoint provenance and primary Dice agreement checks. No diagnostic or panel errors were recorded.

The offline review contains 6 selected cases and 324 synchronized panels: four severity-ranked cases and two sampled from the remainder. This subset is for review, not prevalence estimation. Patient-level artifacts and CT panels are kept outside Git.

## Native segmentation and component errors

Dice is the equal-weight patient mean, displayed as a percentage. All six runs use training seed 0. Pancreas is the union of organ and mass labels. Matched/partial/missed describe 26-connected components at IoU 0.1 with no prediction-size filter. Partial components have overlap but are not one-to-one detection matches; missed components have zero overlap. These are diagnostic component counts, not radiologist-adjudicated tumors or benchmark detection scores.

| Model | Mass Dice | Pancreas Dice | Matched | Partial | Zero overlap | Unmatched predictions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dynunet-control10k-seed0 | 32.98% | 75.59% | 25 | 5 | 12 | 45 |
| dynunet-deep10k-seed0 | 30.69% | 74.07% | 20 | 4 | 18 | 31 |
| dynunet-focal05-seed0 | 31.71% | 72.28% | 21 | 8 | 13 | 60 |
| dynunet-focal10-seed0 | 32.38% | 71.85% | 24 | 7 | 11 | 47 |
| dynunet-window-seed0 | 29.53% | 71.10% | 23 | 7 | 12 | 55 |
| dynunet-minmax-seed0 | 30.67% | 70.45% | 21 | 7 | 14 | 44 |

## Frozen cascade crops

Reference labels were used only to audit already-fixed validation boxes, never to make or repair them. The stage-one training crops remain in-sample rather than out-of-fold; these crop checks do not establish stage-two performance.

| Margin | Cases with some tumor outside crop | Fully excluded lesions | Partly excluded lesions | Empty-prediction fallbacks |
| --- | ---: | ---: | ---: | ---: |
| 20 mm | 1/42 | 0 | 1 | 0 |
| 40 mm | 1/42 | 0 | 1 | 0 |

## Paired recipe comparisons

Candidate minus control in percentage points, using 10,000 paired patient bootstrap resamples. Intervals condition on these trained seed-0 models; they do not quantify training-seed variability. These exploratory comparisons are not adjusted for multiple comparisons and do not establish superiority or SOTA.

| Candidate | Metric | Mean difference | Conditional 95% interval |
| --- | --- | ---: | --- |
| dynunet-deep10k-seed0 | mass_dice | -2.30 pp | [-6.34, +1.63] pp |
| dynunet-deep10k-seed0 | pancreas_dice | -1.52 pp | [-3.32, +0.23] pp |
| dynunet-focal05-seed0 | mass_dice | -1.27 pp | [-7.25, +4.11] pp |
| dynunet-focal05-seed0 | pancreas_dice | -3.31 pp | [-5.24, -1.57] pp |
| dynunet-focal10-seed0 | mass_dice | -0.60 pp | [-6.29, +4.88] pp |
| dynunet-focal10-seed0 | pancreas_dice | -3.74 pp | [-5.88, -1.82] pp |
| dynunet-minmax-seed0 | mass_dice | -2.32 pp | [-8.15, +3.02] pp |
| dynunet-minmax-seed0 | pancreas_dice | -5.14 pp | [-7.72, -2.96] pp |
| dynunet-window-seed0 | mass_dice | -3.46 pp | [-8.80, +1.20] pp |
| dynunet-window-seed0 | pancreas_dice | -4.49 pp | [-6.20, -2.90] pp |

## Verification

- Full local CPU suite: 2,589 passed, 4 skipped, 41 deselected; lint, formatting and types passed.
- [GitHub Actions](https://github.com/arianizadi/segmentary/actions/runs/34918331598/job/104220691990) passed on `segmentary-linux` for the verified source commit.
- Real-browser tests covered synchronized slices, reviewer export/import, revision history, reveal tracking, persistence, desktop/mobile layout and absence of external requests.
- The finite HDRFS verification used CPU only from a separate frozen checkout; it did not change training recipes, checkpoints or running campaign code.
- No architectural hypothesis, corrected annotation or SOTA claim is produced automatically. Radiology review and controlled multi-seed studies remain necessary.
