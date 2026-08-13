# Project history and acceptance record

Segmentary began as a staged-transfer research harness for Cityscapes and
RailSem19, then grew into a general semantic-segmentation library. The rail
configs and results remain as a demanding, reproducible case study; they are not
required defaults and do not define the scope of the package.

This page preserves the public conclusions of the pre-release work without
publishing private infrastructure paths or internal orchestration transcripts.
The tutorials, `pyproject.toml`, component catalog, and roadmap are the
authoritative sources for current behavior.

## Release acceptance

The final pre-release executable tree passed all 1,248 collected tests with no
failures, errors, or skips. The serial acceptance included real Cityscapes and
RailSem19 data, every slow and GPU test, ONNX Runtime CUDA, TensorRT FP16 and
calibrated INT8, a real two-stage curriculum, and every opt-in model catalog:

- 12 of 12 native recipes;
- 6 of 6 revision-pinned Hugging Face recipes; and
- 11 of 11 Segmentation Models PyTorch recipes.

Aggregate branch-aware coverage was 85.094% (87.666% statement coverage and
78.189% branch coverage). A later documentation/package-only change did not
alter executable code, tests, or configs. The rename to Segmentary changes
package and command identities, so its distribution and regression checks are
recorded separately in the release history.

Final dataset-verifier runs used pinned OpenCV 4.14.0.94, scanned 200 samples
from each bundled research dataset, and produced 20 reviewed overlays per
dataset. Licensed images and model checkpoints are intentionally not committed.

## Model-quality reference

The tracked Cityscapes-19 reference reports SegFormer-B2 at a fixed 40,000-update
endpoint:

| protocol | state | images | mIoU | mAcc | pixel accuracy | boundary F1 |
|---|---|---:|---:|---:|---:|---:|
| Cityscapes val, native sliding-window | in-memory final EMA | 500 | 0.805073 | 0.874847 | 0.964518 | 0.866939 |
| same protocol | persisted best EMA at 24,000 updates | 500 | 0.807275 | not retained | not retained | not retained |

The exact 40,000-update weights were not persisted by the original checkpoint
callback, so that endpoint cannot be replayed. Both old `best.ckpt` and
`last.ckpt` contain the 24,000-update state. This limitation must accompany the
reference number.

## Deployment reference

One trained SegFormer-B2 checkpoint was compared on a fixed 1024×1024 deployment
subset. TensorRT FP16 was fastest and effectively accuracy-neutral in that
measurement; INT8 was slower than FP16 and materially less accurate. The
committed [deployment evidence](benchmarks/README.md) labels the source-tree
provenance limitation and distinguishes fixed-shape deployment evidence from
native-resolution model quality.

## Completed rail-transfer case study

The final campaign completed 12 of 12 jobs, 27 result records, 15 true-final
checkpoints, and all 12 common RailSem19 evaluations. Its independently audited
three-seed mIoU results were:

| training path | common RailSem19 mIoU |
|---|---:|
| Cityscapes only | 30.24 ± 0.50% |
| RailSem19 only | 70.47 ± 0.17% |
| Cityscapes then RailSem19 | 66.44 ± 0.03% |
| joint Cityscapes and RailSem19 | 71.04 ± 0.23% |

The joint path had the highest descriptive mean under this exact protocol. The
staged schedule performed below direct RailSem19 training, but it also used half
as many target updates and a lower target learning rate; it is not an isolated
test of source pretraining. See the full [findings](findings.md), generated
[table](results/rail-transfer-m5/results.md), and portable
[audit](results/rail-transfer-m5/audit-summary.json).

## Scope boundary

Segmentary is a broad, composable semantic-segmentation suite, not literal
feature parity with MMSegmentation. Multilabel end-to-end evaluation,
instance/panoptic/video/depth/multimodal task protocols, a public distillation
teacher provider, PointRend/cascade refinement, more real-time families,
conventional Mask2Former, and architecture-wide export admission remain
explicit roadmap work. See the [full-suite roadmap](roadmap/full-suite.md).
