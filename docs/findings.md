# Rail-transfer curriculum case study

This page reports one bundled Segmentary case study. It is evidence about the
specific model, datasets, label space, split, schedules, and evaluator below—not
a universal ranking of curriculum strategies.

The machine audit and generated table predate the public Segmentary rename and
retain their original tool identifiers verbatim. Their metrics and hashes were
not rewritten; the current equivalent table command is `segmentary-table`.

## Question

On one fixed RailSem19 validation target, how do four training paths compare?

- `cs_only`: Cityscapes only, evaluated zero-shot on RailSem19;
- `rs_only`: RailSem19 only;
- `cs_rs`: 40,000 Cityscapes updates followed by 20,000 RailSem19 updates;
- `joint_cs_rs`: 60,000 mixed Cityscapes/RailSem19 updates with equal sampling.

The staged and joint paths each receive 60,000 optimizer updates. The one-stage
controls receive 40,000, so not every pair is an equal-budget comparison.

## Fixed protocol

| Item | Value |
|---|---|
| Model | SegFormer-B2 |
| Canonical space | `rail_union` (21 classes; per-dataset active-class masking) |
| Seeds | optimizer seeds 0, 1, and 2 on one fixed split |
| Effective training batch | 16 |
| Common endpoint | RailSem19 `val`, fixed committed 850-image split |
| Checkpoint | unconditional true-final EMA state |
| Evaluation | 1024×1024 sliding window, stride 768, no TTA |
| Training source | clean `df91d023fb4368ebb9b1f98b2795b7f5003188a1` |

Every headline value comes from the common `eval:railsem19:val` record written
after each job. Native training-stage validation is excluded: `cs_only` and
`joint_cs_rs` validate on Cityscapes during training, while the other endpoints
are RailSem19, so those native scores are not comparable.

## Results

Values are percentage points, reported as mean ± sample standard deviation over
three seeds. The complete generated table, including the six rail-class IoUs,
is available as [Markdown](results/rail-transfer-m5/results.md) and
[CSV](results/rail-transfer-m5/results.csv). The independent portable audit is
[machine-readable JSON](results/rail-transfer-m5/audit-summary.json).

| Curriculum | mIoU | mAcc | Pixel accuracy | Boundary F1 |
|---|---:|---:|---:|---:|
| Cityscapes only | 30.24 ± 0.50 | 44.79 ± 0.61 | 58.21 ± 0.76 | 38.34 ± 0.72 |
| RailSem19 only | 70.47 ± 0.17 | 81.51 ± 0.14 | 89.89 ± 0.11 | 78.62 ± 0.13 |
| Cityscapes → RailSem19 | 66.44 ± 0.03 | 79.17 ± 0.06 | 88.17 ± 0.03 | 74.31 ± 0.09 |
| Joint Cityscapes + RailSem19 | 71.04 ± 0.23 | 81.62 ± 0.18 | 90.16 ± 0.04 | 78.98 ± 0.13 |

The wall-clock and VRAM fields in the generated table describe only the
standalone common evaluation, not total curriculum training cost.

## What the experiment shows

- Cityscapes-only zero-shot transfer was far below every RailSem-supervised arm:
  `-40.24 ± 0.52` mIoU points relative to `rs_only`, paired by seed. Direct
  target-domain supervision was essential under this protocol.
- Joint training had the highest descriptive mean mIoU and boundary F1. It was
  `+0.57 ± 0.37` mIoU points above `rs_only` and also slightly higher on each of
  the five rail infrastructure classes. With only three optimizer seeds, this
  is a small descriptive effect—not a universal or formal significance claim.
- The staged path was worse than `rs_only` for every seed: `-4.03 ± 0.20` mIoU
  points paired by seed. It was also `-4.60 ± 0.21` points below the equal-60k-
  update joint path. This is an important negative result for the shipped staged
  schedule, not evidence that staged transfer can never work.
- Thin-rail behavior followed the aggregate result. Relative to `rs_only`, the
  staged path changed mean IoU by `-6.33` on `rail-track`, `-7.97` on
  `rail-raised`, `-8.13` on `rail-embedded`, `-14.63` on `tram-track`, and
  `-5.45` on `trackbed`. Joint training stayed within roughly 0.3 point of
  `rs_only` on those five class means.

## Why the staged result is not an isolated pretraining effect

`rs_only` receives 40,000 RailSem19 updates at the base learning rate. The
RailSem19 stage of `cs_rs` receives only 20,000 target updates and uses a 0.1
learning-rate scale after Cityscapes. Therefore its `-4.03`-point difference
mixes source pretraining, target-update budget, learning-rate schedule, and stage
order. A fair causal ablation would hold the target schedule fixed and change
only the source initialization.

## What it does not show

- It does not rank architectures; every arm uses the same SegFormer-B2.
- It does not establish behavior on another dataset, taxonomy, split, or model.
- Three optimizer seeds on one fixed data split do not measure split uncertainty
  and do not support a formal significance claim.
- It does not compare best-on-validation checkpoints; every row uses the
  true-final EMA state.
- The optional `cs_rs_railbridge` ablation was outside the required matrix and
  was not run.
- Custom-data curricula were not run because no compatible custom dataset was
  supplied for this campaign.
- The frozen training commit used the union of active classes for native mixed-
  stage validation even though that loader evaluated its first dataset. That can
  depress the native joint Cityscapes-stage score. It does not affect this table:
  all four rows come from the separate common RailSem19 evaluator with the
  RailSem19 active-class mask.

## Acceptance and reproducibility

The terminal audit passed all of these checks:

- 12/12 jobs completed with train and evaluation return code zero;
- exactly 27 finite, schema-valid, provenance-clean `results.json` records;
- exactly 15 true-final checkpoints with the configured optimizer step and EMA
  count, finite matching raw/EMA tensors, and optimizer/scheduler state;
- four curricula × seeds 0/1/2 on the identical 850-image common endpoint;
- 8,500 matched RailSem19 image/mask keys and the committed 6,800/850/850 split;
- identical target support across all 12 common evaluations;
- headline, boundary, and per-class metrics reconstructed from each integer
  confusion matrix; and
- the generated mean/sample-standard-deviation table matched an independent
  recomputation.

Large checkpoints and licensed images are intentionally not committed. Their
relative artifact identities, sizes, and SHA-256 digests are retained in the
portable audit summary. For a new dataset, use this case study as a fair-
comparison example: define one common target, hold its evaluator fixed, run
multiple seeds, preserve provenance, and report negative results.
