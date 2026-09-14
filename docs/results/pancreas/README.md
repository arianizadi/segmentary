# Pancreas research results: reading order

These are research-development results, not a clinical diagnostic system or an independent test of cancer screening.

1. **[Official benchmark comparison](task07/official-benchmark-20260914/README.md):** exact source scores, all 27 completed local models, and a chart separating our validation cohort from the official hidden test cohort.
2. **[Native annotation review](task07/annotation-review-20260914/README.md):** measured Task07/PanTS examples, label conventions, known PanTS exclusions and questions for the radiology mentor. CT panels stay outside Git.
3. **[Convergence review](task07/convergence-review-20260914/README.md):** what the completed learning curves and failure counts show.
4. **[Completed recipe experiments](task07/recipe-ablation-20260914/README.md):** six controlled 10,000-update DynUNet arms with paired analysis.
5. **[Original model screening](task07/scratch-screen-20260913/comparison.md):** every architecture's reported status, pancreas Dice and mass Dice, including the separately budgeted official nnU-Net run.
6. **[Completed fit and inference diagnostics](task07/followup-diagnostics-20260914/README.md):** two-case memorization and the paired Gaussian-versus-uniform comparison on all 42 validation examinations.
7. **[Budget and resolution campaign](task07/followup-20260914/README.md):** the fresh 10,000-update control, 30,000-update schedule and finer-grid 10,000-update arm, with recorded status and subsequent native validation scores.

## Four follow-up questions

| Question | Protocol |
| --- | --- |
| Can the pipeline fit training anatomy and memorize two cases? | [Native fit diagnostic](../../guides/medical-training-fit-diagnostic.md) |
| Does a longer schedule help? | [Fresh 30,000-update DynUNet arm](../../guides/medical-followup-experiments.md) |
| Does preserving more in-plane detail help? | Same guide; finer spacing with matched physical crop extent |
| Does weighting window centers improve reconstruction? | [Same-checkpoint Gaussian comparison](../../guides/medical-inference-blending.md) |

All four use the existing Task07 development data. They retain the reserved test set, original references and scratch-origin requirement. Follow-up training uses a fresh matched control and separately declared budget/resolution arms; these must not be ranked as equal-compute architectures.

The [research repository's meeting guide](https://github.com/arianizadi/pancreatic-cancer-ai-research/blob/main/START_HERE.md) connects these implementation results to clinical background and the professor discussion.
