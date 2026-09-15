# Controlled Dice-reduction study

Declared after the September 15 diagnostic audit and before these runs train. This is a targeted exploratory experiment, not a complete nnU-Net recipe reproduction.

## Hypothesis

The common dense objective pools numerator and denominator across the batch before averaging foreground classes. Larger annotated regions within a batch can have more influence. nnU-Net's actual full-resolution plan uses per-sample Dice. Compute foreground Dice separately for each **patch**, then average patches and classes, to test whether that improves mass learning and native-volume generalization.

Per-patch does not guarantee equal patient weighting: a batch can contain several patches from one patient. Cross-entropy, smoothing, class definitions and the sampling distribution remain unchanged. Empty foreground classes retain an explicit tested smoothing convention. No improvement is assumed in advance.

## Four scratch runs

| Run | Seed | Dice reduction | Role |
| --- | ---: | --- | --- |
| dynunet-batch-seed0 | 0 | batch | Matched control |
| dynunet-per-sample-seed0 | 0 | per patch, then average | Candidate |
| dynunet-batch-seed1 | 1 | batch | Second matched control |
| dynunet-per-sample-seed1 | 1 | per patch, then average | Second candidate |

Every arm uses the existing DynUNet architecture, 96³ patches, XYZ spacing 1.5/1.5/2.5 mm, HU [-100,240] to [0,1], batch 8, the original foreground sampling and flips, AdamW LR 0.0003, weight decay 0.00001, and a 10,000-update polynomial schedule. Native validation is checked after the first 100 updates and every 1,000 thereafter. Use the same frozen 197/42/42 partition; test payloads remain unopened. There is no early stopping or imported checkpoint.

Inference remains the historical uniform probability blending, independently of the inference-only ablations. Deep supervision stays off. Do not combine factors in this experiment.

## Decision and reporting

Primary outcome: full-native mean per-case mass Dice from the selected-best checkpoint, using the existing selection rule. Report endpoint Dice separately. Secondary outcomes: pancreas-union Dice, complete misses, reference-positive coverage, training/validation curves, inference cost and memory. Show all four arms, including failures.

Compute candidate-minus-control paired case differences within each seed. The evaluator groups dataset-case patient proxies; independent patient identity is unverified. Report the two seed contrasts and their spread; a patient bootstrap conditions on each fixed trained pair and does not measure training-seed uncertainty. Two seeds support exploration, not a final robustness claim. Keep the 42 validation cases in every denominator and do not optimize a clinical threshold or remove difficult cases.

Before launch require numerical loss/gradient tests, historical-default equivalence, explicit configuration identity, full-batch GPU forward/backward feasibility and an unchanged data split. The normal Segmentary runner owns GPU locks, immutable recipes, scratch provenance, native evaluation, latest/best checkpoint retention, dashboard lifecycle and resume guards.

## Verification and status

Implementation `f9051656be4a9800d415b8e99ba782b23632a968` passed [GitHub Actions](https://github.com/arianizadi/segmentary/actions/runs/34995340720) on the self-hosted `segmentary-linux` runner. The [exact GPU preflight receipt](dice-reduction-preflight.json) passed at 09:52 Pacific on September 15, 2026. Both loss routes completed batch 8 with three warmup and five measured forward/backward/optimizer steps, finite losses, and 7.61 GiB peak allocated CUDA memory. This establishes feasibility rather than convergence.

The input audit covered all 197 training scans, opened zero evaluation payloads, and retained all 198 reference connected components after resampling. Train/validation/test membership remains fixed. The two random seeds alter training randomness; they **do not test sensitivity to the data split**.

**Launched September 15 at 09:57 Pacific.** All four runs have confirmed optimizer updates, random initialization and zero external weight loads. Within each seed, the two reduction arms have matching initial-weight hashes; seeds 0 and 1 have different hashes. GPUs 4/5 run batch/per-patch seed 0, and GPUs 6/7 run batch/per-patch seed 1. The original nnU-Net training continues separately on GPU 0.

At 10:01 Pacific each run had reached 490–501 updates with finite loss; [the verified launch receipt](dice-reduction-launch.json) records the exact source and initial-weight hashes. These are operational checks, not completed accuracy results. Measured optimization throughput is about 4.4 updates/second, excluding validation and reporting overhead; allow approximately an hour from launch for training and native evaluation, subject to actual progress.

The ordinary Segmentary runner manages the automatic training dashboard and latest/best checkpoint retention. A finite completion wrapper will calculate the two within-seed contrasts and publish the aggregate [campaign comparison](../dice-reduction-20260915/README.md), including `paired-seeds.md/json` when all four native evaluations verify. It performs initial/final publication and exits; no recurring Codex monitoring was created. Detailed case-level validation and operator logs stay with the private artifacts.
