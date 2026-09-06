# Results by dataset and protocol

| Study | What the models learn | Evaluation |
| --- | --- | --- |
| [Cityscapes and RailSem19](cityscapes-railsem19/README.md) | Cityscapes only; RailSem19 only; Cityscapes → RailSem19 | Original Cityscapes/RailSem19 splits and taxonomies |
| [paul-test-rtis live pilot](paul-test-rtis/live/README.md) | Pretrained backbone → RTIS; Cityscapes → RTIS; RailSem19 → RTIS; Cityscapes → RailSem19 → RTIS | The separately versioned RTIS split and native 21-class taxonomy |

These studies have different label definitions, data, and training budgets.
Their mIoU values are not interchangeable. RTIS diagnostics do not update the
Cityscapes/RailSem19 model leaderboard.

[RTIS preparation and source-only diagnostics](paul-test-rtis/README.md) are recorded separately from the live adaptation campaign.
