# Results by dataset and protocol

| Study | What the models learn | Evaluation |
| --- | --- | --- |
| [Cityscapes and RailSem19](cityscapes-railsem19/README.md) | Cityscapes only; RailSem19 only; Cityscapes → RailSem19 | Original Cityscapes/RailSem19 splits and taxonomies |
| [paul-test-rtis v1 (original import)](paul-test-rtis/live/README.md) | Pretrained backbone → RTIS; Cityscapes → RTIS; RailSem19 → RTIS; Cityscapes → RailSem19 → RTIS | 220/37/50 split; contains 15 disputed CVAT-import training images; 21 training classes |
| [paul-test-rtis_v2](paul-test-rtis/v2/README.md) · [V1 vs V2](paul-test-rtis/v2/comparison.md) | Same 36 models and four initialization paths; seed 0 only; disputed import removed | 205/37/50; identical validation/test images and masks; paired against v1 seed 0 |
| [Task07 pancreas scratch sweep](pancreas/task07/scratch-screen-20260913/README.md) · [Performance continuation](pancreas/task07/performance-continuation-20260914/README.md) | 27 scratch Torch architectures plus a separate nnU-Net ResEnc L comparator | 197/42/42; native validation mass and pancreas-union Dice; held-out test reserved |

These studies have different label definitions, data, and training budgets.
Their mIoU values are not interchangeable. RTIS diagnostics do not update the
Cityscapes/RailSem19 model leaderboard.

For the pancreatic CT study, read the [published recipe comparison and proposed
experiments](pancreas/task07/recipe-comparison-20260914/README.md) before interpreting
the architecture ranking. Pancreas results use Dice, with different training
budgets and protocols from the scene-segmentation studies above.

[RTIS preparation and source-only diagnostics](paul-test-rtis/README.md) are recorded separately from the live adaptation campaign.

## Implementation and data validation

- [Instance and panoptic validation](object-validation/README.md): real Cityscapes
  GPU execution, pretrained AP/PQ, official evaluator parity, and full resume checks.
