# Instance and panoptic validation

Real-data implementation checks performed on HDRFS, 6 September 2026. Existing
RTIS training continued from its frozen checkout; no campaign was restarted.

## Pretrained model results

These evaluations use **three Cityscapes validation images**, selected by sorted
filename, and published task-specific Mask2Former Swin-T weights. The subset is
for integration and evaluator parity. It is not a full benchmark, an RTIS result,
or evidence that one architecture is better than another.

| Model / initialization | Task | Mask AP | AP50 | AP75 | PQ | SQ | RQ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [Mask2Former Swin-T / Cityscapes instance](mask2former-swin-tiny-cityscapes-instance/README.md) | Instance | 53.21 | 82.10 | 56.34 | — | — | — |
| [Mask2Former Swin-T / Cityscapes panoptic](mask2former-swin-tiny-cityscapes-panoptic/README.md) | Panoptic | — | — | — | 76.27 | 83.52 | 90.30 |

Scores are percentages. Each model page includes per-class results, VRAM, FPS,
latencies, checkpoint SHA-256, exact Hub revision, and configuration. See the
[resource comparison](comparison.md). Timing was measured on a shared NVIDIA L40S,
with synchronized CUDA calls and two warmup forwards; it is not dedicated-device
throughput. Predictions and recipes are included beside each report. Original
Cityscapes images and checkpoint weights are not distributed in this repository.

Both official reference evaluators received the same exported native-resolution
predictions. COCO mask AP/AP50/AP75/AR100 and per-class values agreed within
1.12e-16; panoptic PQ/SQ/RQ and per-class values agreed within 2.23e-16.
The acceptance tolerance was 1e-8. **COCO mask AP on these annotations is not the
official Cityscapes instance AP protocol.**

The pretrained load recorded obsolete relative-position index buffers and a
missing final Swin LayerNorm. Installed SwinBackbone uses separately normalized
stage features; changing that unused final norm leaves predictions exactly
unchanged and it receives no gradients in the regression test. The recipe
records this audited exception and rejects other missing or mismatched active
weights. Both runs use initialization seed 0.

## Four-family CUDA training execution

These checks use deliberately small randomly initialized architectures and real
native Cityscapes masks. Each completed two optimizer updates and held-out forward
checks. They establish execution, gradient flow, and AMP behavior; they are not
accuracy or overfitting results.

| Family | Instance / float16 | Panoptic / bfloat16 |
| --- | --- | --- |
| [eomt_large](gpu-families/eomt_large/README.md) | Passed | Passed |
| [eomt_dinov3_large](gpu-families/eomt_dinov3_large/README.md) | Passed | Passed |
| [maskformer_swin_tiny](gpu-families/maskformer_swin_tiny/README.md) | Passed | Passed |
| [mask2former_swin_tiny](gpu-families/mask2former_swin_tiny/README.md) | Passed | Passed |

Each family links to its resource/step page. Full records:
[instance](gpu-instance.json), [panoptic](gpu-panoptic.json).

## Reproduce

Use the [benchmark recipe](../../guides/object-benchmark-validation.md),
[GPU execution recipe](../../guides/object-gpu-validation.md), and
[object reporting commands](../../guides/object-reports.md). Omit the converter's
`--limit` to prepare full official train/validation splits. Match protocols,
initializers, preprocessing, thresholds and category definitions before comparing
runs. Full pretrained training and full-dataset benchmark reproduction remain
separate experiments.

## Complete continuation evidence

CUDA float16 and bfloat16 interruption/resume tests both passed on the same L40S.
They compared model tensors, optimizer buffers, GradScaler, Python/NumPy/Torch/CUDA
random state, sample permutation/cursor, loss history, and best selection exactly
against uninterrupted execution. Float16 skipped one overflowing update; bfloat16
skipped none. Skipped attempts consume sampler groups but do not increment the
optimizer step. Evidence: [JUnit results](gpu-resume.xml).

The isolated validation checkout was a source copy rather than a Git worktree,
so the individual reports correctly leave its Git commit unavailable. The
[source manifest](source-manifest.json) records SHA-256 for all 90 Python runtime
modules and both benchmark scripts. These 92 file hashes were checked against
the release source with zero mismatches. This pins the tested code without
inventing a Git revision for uncommitted validation work.
