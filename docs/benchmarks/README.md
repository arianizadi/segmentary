# Benchmark and evidence ledger

This page separates comparable model-quality results from compatibility smokes,
deployment-subset measurements, and work that is still incomplete. A README
number is never enough by itself; prefer a committed machine `results.json` with
the complete config, code SHA, seed, environment, split, and metrics.

> **Pre-rename evidence:** machine records created before the public Segmentary
> release preserve their original distribution, import, CLI, and evidence-kind
> strings verbatim. Those old names are provenance, not current commands. Use
> `segmentary-*` and `import segmentary` for new work.

## Evidence levels

1. **Dataset benchmark:** trained checkpoint, complete named split, fixed
   taxonomy/evaluator, and a machine result record.
2. **Deployment benchmark:** identical deterministic resized samples across
   backends plus latency methodology and degradation from one PyTorch baseline.
3. **Training smoke:** a few real/synthetic steps with finite loss/gradients and
   a checkpoint; proves plumbing, not accuracy.
4. **Construction smoke:** weights load and forward/backward works; proves
   compatibility only.
5. **Documented/blocked:** config or integration exists, but a prerequisite or
   scientifically correct objective is absent.

## Beginner reading rule

Start with the evidence level and protocol, not the largest number. Compare two
rows only when taxonomy, complete split, model/checkpoint policy, evaluator, and
seed set match. Construction and training smokes are useful because they catch
broken wiring cheaply; their limitation is that they say nothing about
generalization. A deployment subset is useful for backend choice but cannot
replace native-resolution model evaluation.

Pros: one ledger makes positive, negative, partial, and blocked evidence easy to
distinguish and prevents compatibility checks from turning into accidental
leaderboards. Cons: historical prose without a bundled machine record is less
auditable, and strict protocol matching means many otherwise interesting numbers
cannot be placed in the same comparison table.

## Tracked Cityscapes-19 reference

The repository's tracked acceptance record reports the corrected
SegFormer-B2 run with:

| protocol | evaluated state | images | mIoU | mAcc | pixel accuracy | boundary F1 |
|---|---|---:|---:|---:|---:|---:|
| Cityscapes val, `cityscapes19`, native sliding-window, 40k | in-memory EMA final validation; exact 40k checkpoint unavailable | 500 | 0.805073 | 0.874847 | 0.964518 | 0.866939 |
| same run/protocol | persisted best EMA checkpoint at 24k | 500 | 0.807275 | not recorded here | not recorded here | not recorded here |

The fixed 40k endpoint is the fair schedule-comparison row; the best checkpoint was
selected on that validation target and is labeled separately. The tracked record
states that the final result was within roughly 0.5 mIoU of its cited reference
scale.

Source: the pre-release acceptance run. The raw machine `results.json` is not
part of this repository checkout. Its 40k result is valid, while both persisted
`best.ckpt` and `last.ckpt` contain the 24k state; the exact 40k weights cannot
be replayed. Retain that checkpoint caveat whenever quoting the fixed endpoint.

## Tracked fixed-shape deployment comparison

The trained SegFormer-B2 checkpoint was measured at batch 1 and fixed 1024x1024
input using CUDA-event timing after warmup. Every backend used the same
deterministically resized evaluation samples.

| runtime | mIoU | p50 | p95 | degradation from PyTorch |
|---|---:|---:|---:|---:|
| PyTorch FP32 | 0.663273 | 29.817 ms | 30.078 ms | 0.000000 |
| ONNX Runtime FP32 | 0.663283 | 44.472 ms | 45.084 ms | -0.000010 |
| TensorRT FP16 | 0.663293 | 10.008 ms | 10.075 ms | -0.000020 |
| TensorRT INT8 | 0.494199 | 14.938 ms | 15.025 ms | 0.169075 |

Small negative “degradation” means the finite subset changed by a tiny amount
in the favorable direction; it is not evidence that quantization improves the
model. In this measured setup FP16 was fastest and effectively accuracy-neutral,
while INT8 was both slower than FP16 and 0.169075 lower on the 0–1 mIoU scale.

Source: the tracked [SegFormer-B2 export evidence
bundle](segformer-b2-export/README.md), including a compact machine
[`summary.json`](segformer-b2-export/summary.json). The source worktree was dirty,
so rerun cleanly before publication. These are deployment-backend comparisons
on fixed resized samples, not native-resolution Cityscapes model-quality
numbers. The [DeepLabV3+-R101 bundle](deeplabv3plus-r101-untrained-export/README.md)
is separately and unmistakably labeled as untrained functional evidence.

## Diagnostic overfit evidence

The tracked record reports eight-image memorization reaching `0.9524` mIoU on
Cityscapes and `0.9545` on RailSem19. This is a powerful data/model/loss wiring
check. It is not a generalization benchmark and must never appear in a model
leaderboard.

## Completed common-target case study

The [rail-transfer findings](../findings.md) and generated
[result table](../results/rail-transfer-m5/results.md) retain the completed
three-seed `cs_only`, `rs_only`, `cs_rs`, and `joint_cs_rs` comparison. Its
portable [audit summary](../results/rail-transfer-m5/audit-summary.json) proves
12/12 jobs, 27 result records, 15 true-final checkpoints, identical common
support, and independent metric/table reconstruction. These values apply only
to the recorded SegFormer-B2/RailSem19 protocol.

## Results that do not exist yet
- The custom dataset does not exist in the repository, so `direct`,
  `rs_custom`, `cs_rs_custom`, and `joint` have no valid final-stage benchmark.
- New Hugging Face and SMP recipe pages contain construction/training-smoke
  evidence where stated, but no common-protocol accuracy ranking.
- The [native component smoke ledger](native-component-smokes/README.md) records
  exact tagged pretrained feature admission, scratch component tests, and a CPU
  DDP/training smoke. It contains no native-recipe model-quality ranking.
- A DeepLabV3+-R101 TensorRT acceptance performed with untrained weights is
  deployment plumbing only. It cannot establish DeepLab quality or compare it
  with the trained SegFormer deployment table.
- Segmentary now has a native Hungarian query objective, but no comparable
  multi-seed accuracy result yet isolates it. EoMT model YAMLs retain dense CE
  unless `loss.query` is explicitly selected; dense-collapse and native-query
  results must be named separately. The retained
  [EoMT-Large native-query GPU8 record](native-component-smokes/eomt-large-query-gpu8-2026-08-13.json)
  proves only synthetic objective/gradient/optimizer compatibility; neither it,
  construction/forward evidence, nor unit tests can be compared with published
  model accuracy.
- `mask2former_dinov3` remains blocked until a valid DINOv3 adapter/feature
  pyramid and native objective are implemented and verified.

## How to add a trustworthy result

1. Write each exact checkpoint/dataset/split/EMA/TTA variant to its own
   `results.json` directory.
2. Keep the complete split, taxonomy, preprocessing, window/stride, and
   checkpoint policy identical across arms.
3. Use the same training seeds and disclose effective batch and optimizer-step
   budgets.
4. Run `segmentary-table` over one campaign root; let it reject duplicate seeds,
   config drift, dirty provenance, or mixed code SHAs.
5. Commit the generated table and, when size/policy permits, the small machine
   JSON records. Do not commit large model weights merely to support a table.
6. Report mIoU with task-critical per-class IoU/support and boundary metrics.

## Related documentation

- [Interpreting results](../tutorials/interpreting-results.md)
- [Evaluation and results](../guides/evaluation-and-results.md)
- [Export and deployment](../guides/export-and-deployment.md)
- [Curriculum catalog](../catalog/curricula/README.md)
- [Model config catalog](../../configs/models/README.md)
