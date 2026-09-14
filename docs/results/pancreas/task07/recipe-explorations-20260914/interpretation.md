# Why this next set of experiments

[Experiment recipes and reading guide](../../../../guides/medical-recipe-experiments.md) · [Earlier follow-up](../followup-20260914/README.md)

This note records the interpretation before results from the new recipe/cascade experiments are available. It is not a leaderboard for those new runs.

## Earlier follow-up: completed native validation

The three earlier arms each predicted all 42 validation CTs successfully. Values below use each arm's own best-selected validation checkpoint, not necessarily its final update. Pancreas is the union of exclusive labels 1 and 2.

| Arm | Mass Dice | Pancreas-union Dice | Paired mass difference vs control, percentage points |
|---|---:|---:|---:|
| Fresh DynUNet 10k control | 32.98% | 75.59% | Reference |
| Fresh DynUNet 30k schedule | 33.80% | 72.62% | +0.82 [−4.46, +5.42] |
| Finer in-plane grid, 10k | 28.20% | 72.80% | −4.79 [−10.27, −0.06] |

Intervals are pointwise 95% percentile bootstrap intervals from 10,000 paired resamples of the same 42 provided case groups (seed 20260914). They do not include training-seed uncertainty or correct for checkpoint/arm selection and multiple comparisons. The fine-grid interval barely excludes zero before those considerations. Source: the completed frozen follow-up's `postrun/paired-comparisons.json`, verified on HDRFS at 2026-09-14 23:41 UTC; training source `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`.

Interpretation: a longer schedule alone did not yield a clear mass-Dice improvement. Finer in-plane resampling at the existing fixed network depth did not help this recipe. That does not establish that high resolution is generally harmful: resampling, voxel count and the physical receptive field interact.

## Claude Fable review and our assessment

Claude completed an independent read-only review of code, existing records and online material. The installed CLI's highest supported effort was `max`, used with Fable 5.1; `ultra` was not supported. Claude had no write/edit tools. The experiments here were separately authorized afterward by the user.

Useful proposals from the review:

1. Finish the nnU-Net reference and compare its **native** results before diagnosing an architecture problem.
2. Test localization followed by pancreas-centered crops, recording localization failures. A confirmatory study should use out-of-fold training crops.
3. Improve training recipes systematically, including deep supervision and stronger augmentation/optimizer recipes. Separate-factor tests answer different questions from a bundled strong-recipe comparison.
4. Repeat promising comparisons across seeds; a single-seed screen cannot settle architecture superiority.
5. Examine missed/poorly localized tumors separately from boundary errors, and use radiologist review for difficult examples.
6. Consider overlapping whole-pancreas/mass region targets as a later alternative to the existing mutually exclusive three-class objective. This is **not implemented in the current matrix**.
7. Consider stronger physical-context/patch-geometry comparisons, test-time augmentation and PanTS scaling later, after protocol and source/patient overlap checks.

Claims we did not accept:

- Patch/pseudo-Dice cannot be converted into native whole-scan Dice by subtracting an arbitrary 5–15 points. We have no basis to declare the still-running nnU-Net superior from its patch scores.
- Claude cited patch dimensions that do not match the live nnU-Net plan. That arithmetic is not used to compare voxel exposure or justify these experiments.
- Four selected training cases cannot establish the entire training distribution's generalization gap or prove lack of augmentation is the cause.
- There is no universal “42 patients cannot resolve less than eight Dice points” rule. Paired precision depends on the distribution of differences; training-seed variance and selection also matter.
- Inter-reader Dice from another cohort is not a hard upper bound for our dataset. High voxel confidence is also not calibrated patient-level diagnostic confidence.

The review found no demonstrated gross data/geometry failure, but that is not proof that the entire pipeline is bug-free. Our tests and real-data audits supply narrower, explicit evidence.

## How to read the new results

- Compare native per-case Dice and paired differences, not the numeric total-loss values across CE+Dice, Dice+focal and multi-scale supervision.
- Show both endpoint and selected-best results. The latter uses validation to choose a checkpoint.
- Keep the fixed-window baseline: clipping and min–max normalization were already present. The new raw-volume min–max arm is an alternative, not a missing prerequisite.
- Use the cascade's full-native scores. Do not score only inside a reference-derived or predicted box and call it whole-scan performance.
- First-stage timing is saved separately for all development CTs. Standard stage-two benchmarking alone is not total cascade latency.
- Treat all these comparisons as exploratory development. Reserve the untouched test set for the fixed final protocol; repeat important findings across seeds before making a paper's central claim.

Primary reading checked during this review: [PANORAMA's two-stage baseline](https://github.com/DIAGNijmegen/PANORAMA_baseline), [nnU-Net Revisited](https://arxiv.org/abs/2404.09556), [Swin UNETR](https://arxiv.org/abs/2201.01266), and [Focal Loss](https://arxiv.org/abs/1708.02002).
