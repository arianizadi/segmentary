# Pancreas Task07: model comparison

Generated: 2026-09-15T08:00:34.574319+00:00. Source: `9f7615bd1f6035d65aca3f848a263b67c49f531f`.

**27 completed, 1 running.** GPU queue: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9.

1. Open [comparison.md](comparison.md) for model status and comparable validation results.
2. Open [learning-curves.md](learning-curves.md) to check whether each model is learning.
3. Follow a model link for its recipe, objective, timing, memory, coverage, and evaluation interval.
4. Read [optimization.md](optimization.md) for the throughput investigation and measurement limits.
5. Open [training-cost.md](training-cost.md) and [inference.md](inference.md) for separate training, validation, checkpoint, full-CT and model-only measurements.
6. Use [results.csv](results.csv), [epochs.csv](epochs.csv), [validation-cases.csv](validation-cases.csv), [inference-cases.csv](inference-cases.csv), and [stage-invocations.csv](stage-invocations.csv) for spreadsheets. [status.json](status.json) and [records/](records/) retain numerical evidence and provenance.
7. Read [clinical-metrics.md](clinical-metrics.md) for P-Sen, T-Sen, specificity, AUC and DSC, including why some metrics cannot be estimated on Task07.

```text
report-directory/        this report's folder
  README.md              reading guide and interpretation
  comparison.md          all models, status, validation, ranking gates
  learning-curves.md     recorded epochs; no interpolated values
  optimization.md        throughput changes and measured evidence
  training-cost.md       retained epoch phases and allocation cost
  inference.md           native CT and model-only speed/memory
  clinical-metrics.md    detection/DSC metrics and unavailable reasons
  models/<run>.md        per-model recipe, resources and evaluation
  records/<run>.json     full numerical model record and lineage
  epochs.csv             training/validation/checkpoint timings
  validation-cases.csv   per-epoch native Dice by case ordinal
  inference-cases.csv    native prediction phase timings
  stage-invocations.csv  completed/failed/cancelled stage costs
  results.csv            one aggregate row per run
  status.json            aggregate evidence and comparison gates
```

Frozen split counts: 197 training, 42 validation, 42 held-out test. Grouping status: `dataset_case_unverified`. Split SHA256: `7f4308aaea49910334b6aa900a998b4ff94623d25cc630c9dd2704d7513b25f9`.

The scheduler runs one job on each available GPU and advances through the explicit queue. A completed run means its training, native validation prediction and evaluation have finished. Queued, failed and incomplete runs remain visible. No pretrained weights are allowed; resuming an existing scratch-origin run is allowed.

All scores are on a 0-1 scale; — means unavailable, never zero. This is an
exploratory seed-0 screening study, with no claim of a clinical or publishable
winner. Dataset case grouping has not independently established patient identity.
Task07 mass masks are segmentation targets; they do not establish PDAC diagnosis.
The held-out test partition and 139 unannotated Task07 scans are not scored here.

In-training Dice is a mean over complete native validation examinations, counting
both-empty mass masks as 1. Final evaluation instead averages patient means over
reference-positive cases and excludes both-empty masks. These two columns answer
different questions and must not be substituted. A completed screening rank uses
the final evaluator's mass Dice only, after every planned run in that group has
finished on matching references, native evaluation protocol, source, split,
seed, optimizer-step budget, batch size, and checkpoint-selection rule.

Models use their declared objectives, including query and auxiliary losses.
Therefore the comparison tests architecture and objective together. 2.5D and 3D
inputs also have different spatial context. Equal optimizer steps are not equal
GPU-hours, voxels seen, or an architecture-specific tuning budget. Loss magnitudes
are useful within a run; they are not an accuracy ranking across objectives.

[Medical model guide](../../../../guides/medical-models.md) · [Results by dataset](../../../README.md)

## All models at a glance

| Model | Status | Steps / budget | Native mass Dice | Native pancreas Dice | Score scope | Cases |
| --- | --- | --- | --- | --- | --- | --- |
| [nnunet_resenc_l](models/nnunet_resenc_l-seed0.md) | running | 180500/250000 | — | — | in-training step — | 0/42 |
| [umamba_enc](models/umamba_enc-seed0.md) | completed | 10000/10000 | 0.3571 | 0.7541 | final reference-positive mean | 42/42 |
| [segmamba](models/segmamba-seed0.md) | completed | 10000/10000 | 0.3212 | 0.7355 | final reference-positive mean | 42/42 |
| [umamba_bot](models/umamba_bot-seed0.md) | completed | 10000/10000 | 0.3216 | 0.7276 | final reference-positive mean | 42/42 |
| [swin_unetr](models/swin_unetr-seed0.md) | completed | 10000/10000 | 0.2446 | 0.7045 | final reference-positive mean | 42/42 |
| [unetr](models/unetr-seed0.md) | completed | 10000/10000 | 0.1116 | 0.4810 | final reference-positive mean | 42/42 |
| [transunet_3d](models/transunet_3d-seed0.md) | completed | 10000/10000 | 0.3101 | 0.7354 | final reference-positive mean | 42/42 |
| [medformer](models/medformer-seed0.md) | completed | 10000/10000 | 0.3272 | 0.7187 | final reference-positive mean | 42/42 |
| [mednext_v1](models/mednext_v1-seed0.md) | completed | 10000/10000 | 0.2845 | 0.6888 | final reference-positive mean | 42/42 |
| [dynunet](models/dynunet-seed0.md) | completed | 10000/10000 | 0.3298 | 0.7559 | final reference-positive mean | 42/42 |
| [segresnet](models/segresnet-seed0.md) | completed | 10000/10000 | 0.3090 | 0.6610 | final reference-positive mean | 42/42 |
| [unet_3d](models/unet_3d-seed0.md) | completed | 10000/10000 | 0.1833 | 0.6084 | final reference-positive mean | 42/42 |
| [mask2former](models/mask2former-seed0.md) | completed | 10000/10000 | 0.1490 | 0.5844 | final reference-positive mean | 42/42 |
| [maskformer](models/maskformer-seed0.md) | completed | 10000/10000 | 0.0005 | 0.0044 | final reference-positive mean | 42/42 |
| [dpt](models/dpt-seed0.md) | completed | 10000/10000 | 0.0637 | 0.3644 | final reference-positive mean | 42/42 |
| [swin_upernet](models/swin_upernet-seed0.md) | completed | 10000/10000 | 0.1391 | 0.5348 | final reference-positive mean | 42/42 |
| [convnext_upernet](models/convnext_upernet-seed0.md) | completed | 10000/10000 | 0.1278 | 0.6405 | final reference-positive mean | 42/42 |
| [segformer_b2](models/segformer_b2-seed0.md) | completed | 10000/10000 | 0.1218 | 0.3313 | final reference-positive mean | 42/42 |
| [hrnet_ocr](models/hrnet_ocr-seed0.md) | completed | 10000/10000 | 0.1701 | 0.6618 | final reference-positive mean | 42/42 |
| [unet_plus_plus](models/unet_plus_plus-seed0.md) | completed | 10000/10000 | 0.2601 | 0.6722 | final reference-positive mean | 42/42 |
| [deeplabv3_plus](models/deeplabv3_plus-seed0.md) | completed | 10000/10000 | 0.2598 | 0.6229 | final reference-positive mean | 42/42 |
| [fpn](models/fpn-seed0.md) | completed | 10000/10000 | 0.2399 | 0.6382 | final reference-positive mean | 42/42 |
| [unet_2d](models/unet_2d-seed0.md) | completed | 10000/10000 | 0.2555 | 0.6631 | final reference-positive mean | 42/42 |
| [segformer_b0](models/segformer_b0-seed0.md) | completed | 10000/10000 | 0.1156 | 0.4408 | final reference-positive mean | 42/42 |
| [pidnet](models/pidnet-seed0.md) | completed | 10000/10000 | 0.0324 | 0.5757 | final reference-positive mean | 42/42 |
| [ddrnet](models/ddrnet-seed0.md) | completed | 10000/10000 | 0.0806 | 0.5269 | final reference-positive mean | 42/42 |
| [bisenetv2](models/bisenetv2-seed0.md) | completed | 10000/10000 | 0.1464 | 0.5664 | final reference-positive mean | 42/42 |
| [lraspp](models/lraspp-seed0.md) | completed | 10000/10000 | 0.1463 | 0.5191 | final reference-positive mean | 42/42 |
