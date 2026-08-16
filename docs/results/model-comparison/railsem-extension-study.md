# RailSem19 adaptation extension study

This bounded study checked whether continuing corrected Cityscapes to RailSem19
adaptation from 20,000 to 40,000 RailSem19 iterations justified the additional
compute. Every run reused its already-trained 40,000-iteration Cityscapes
checkpoint; Cityscapes was not trained again.

## Result

| model | Rail20 / total60 mIoU | Rail40 / total80 mIoU | change after 20k more Rail iterations | Rail stage wall time through 40k | evidence |
|---|---:|---:|---:|---:|---|
| Native ConvNeXt-Tiny + UPer | 70.22 | 70.11 | 0.11 points lower | 12h 48m 36s | full common evaluation, EMA |
| SMP UPerNet + ResNet101 | 66.06 | 66.50 | 0.45 points higher | 12h 55m 41s | full common evaluation, raw weights because of running-stat BatchNorm |
| HF UPerNet + Swin-Tiny | 67.90 | 67.77 | 0.12 points lower | 17h 52m 51s | full in-training validation, EMA |

Swin-Tiny briefly reached 68.66 mIoU at the saved 36,000-iteration validation
checkpoint, 0.76 points above its 20,000-iteration value, then ended below the
20,000-iteration value at 40,000. That checkpoint is retained as `best.ckpt`.
The Swin values are training-validation measurements rather than separate
post-training common-evaluation records, so they should not be mixed into a
strict common-evaluation ranking.

## Decision

**Further RailSem19 extension was stopped.** Across the three representative
models, the extra 20,000 target-domain iterations produced two lower endpoints
and one small 0.45-point gain. This is marginal and inconsistent relative to
the additional wall time and electricity. The 20,000-iteration RailSem19
adaptation checkpoint remains the compute-efficient default; the retained
40,000-iteration and best checkpoints document the bounded experiment.

No additional post-40,000 RailSem19 training is scheduled from this study. This
decision does not stop the separate standard Cityscapes or RailSem19-only model
comparison jobs.

## Provenance

- Source commit: `57f686737f3aa22db9a92e9880b1862227160dfd`, clean worktree.
- Seed: 0.
- Target validation split: fixed RailSem19 validation split in `rail_union`.
- Evaluation window: 1024 by 1024, stride 768, no TTA.
- Corrected adaptation rates: 0.1x backbone groups and 1.0x model-declared
  decoder/head groups.
- Checkpoints retained for each completed model: Rail20, best, and final/latest.

The table intentionally reports individual measurements without dispersion
notation. It is a stopping study, not a claim that 20,000 iterations is optimal
for every architecture or seed.
