# Dice reduction: matched comparisons by seed

All four runs passed complete native-result verification.

Per-sample means per patch. All models start from scratch, with the same 10,000-update schedule and 42-case native validation cohort.

| Run | Status | Mass Dice | Pancreas union Dice | Endpoint mass Dice |
|---|---|---:|---:|---:|
| dynunet-batch-seed0 | verified complete | 32.98% | 75.59% | 29.86% |
| dynunet-per-sample-seed0 | verified complete | 32.67% | 77.68% | 32.67% |
| dynunet-batch-seed1 | verified complete | 30.46% | 73.24% | 28.59% |
| dynunet-per-sample-seed1 | verified complete | 36.10% | 77.26% | 36.10% |

Candidate minus control; differences and intervals are percentage points. Bootstrap units are dataset-case proxies (`dataset_case_unverified`), not verified independent patients.

| Seed | Mass gain [case-proxy bootstrap 95% CI] | Pancreas gain [case-proxy 95% CI] |
|---|---:|---:|
| 0 | -0.32 [-3.41, +2.78] | +2.09 [+1.01, +3.24] |
| 1 | +5.64 [+1.06, +11.37] | +4.02 [+2.33, +5.93] |

Grouping is dataset_case_unverified: bootstrap units are dataset-case proxies, not independently verified patients. Each interval conditions on one trained control/candidate pair. The same 42 dataset cases recur across seeds and are not 84 independent cases. Two seeds supply descriptive replication, not a reliable estimate of training-seed uncertainty.

Latest/endpoint values are separate from selected-best checkpoint scores. Failures remain in the table and do not produce a complete paired comparison. No held-out test payloads were opened.

Frozen training source: `f9051656be4a9800d415b8e99ba782b23632a968`. Exact source/operator/recipe/checkpoint and evaluation hashes are recorded in [paired-seeds.json](paired-seeds.json).
