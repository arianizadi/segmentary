# RTIS full-statistics campaign v1

This is a fresh campaign for **mud-pumping segmentation**. It preserves the
original pilot and starts each run from the declared pretrained/source endpoint,
not from a partially trained RTIS checkpoint. Labels and the 220/37/50 grouped
train/validation/test split are unchanged. The test split stays held out.

## Experiment contract

| Setting | Value |
| --- | --- |
| Recipes | 36 physical models; aliases are not duplicate experiments |
| Initialization paths | Recipe pretrained; Cityscapes; RailSem19; Cityscapes -> RailSem19 |
| Adaptation seeds | 0, 1, 2; 432 jobs total |
| Historical endpoints | Fixed across adaptation seeds; their hashes are verified |
| Selection and early stopping | `val_iou/mud-pumping`, maximize |
| Maximum optimizer steps | 4,000 |
| Validation cadence | Approximately 250 optimizer steps |
| Early stopping | Five checks without at least 0.001 absolute IoU improvement (0.1 percentage point) |
| Effective batch | 2 images per microbatch, accumulation 8 = 16 images |
| Objectives and architectures | Same model-specific recipes as the pilot; no unreviewed label or class-weight changes |
| Checkpoints retained | Mud-selected best and final full-state checkpoints |
| Recovery | Full-state checkpoints and every attempt's timing/error evidence |
| Final evaluation | Same no-TTA, native-class protocol; automatic EMA for models without running-stat BatchNorm, raw otherwise |

Three adaptation seeds measure optimization variability conditional on this
fixed split and fixed source endpoints. They do not measure variability across
independent recordings, and they do not make the small validation set an
independent test set. Incomplete seed summaries are provisional.

## Required before a job is complete

The worker owns one GPU throughout training, evaluation, collection and
profiling. It cannot start the next model while those measurements are pending.
A trained model is marked **collecting**, not complete, until these records exist
and pass consistency checks:

1. **Training:** resolved configuration, input normalization, model origin
   metadata, parameter counts, seed, source/code/data hashes, optimizer state,
   selected/final checkpoints, stopping reason and scalar learning curves.
2. **Validation curves:** aggregate and ground-truth-present-class mIoU;
   per-class IoU, precision, recall, Dice and support; training loss. Mud IoU is
   the selection metric, so absent unrelated classes cannot change its denominator.
3. **Selected checkpoint:** standalone validation plus detailed evaluation of
   all 220 training and 37 validation images using evaluation transforms.
   The detailed validation confusion matrix must exactly reproduce the standalone
   confusion matrix. A mismatch is a collection failure requiring investigation.
4. **Comparison endpoints:** selected checkpoint with alternate raw/EMA weights
   on validation, and an independent validation pass of the final checkpoint.
   EMA with uncalibrated running-stat BatchNorm is flagged as diagnostic-only;
   it is not silently used for checkpoint selection or deployment.
5. **Per-image evidence:** CSV, full compressed confusion matrices, source-image
   and decoded-mask hashes, prediction hashes and retained prediction masks.
   Every image and mask is checked against the preparation manifest.
6. **Per-group evidence:** complete class metrics and mud confusion counts by
   scene group. Groups remain provisional until recording identities are known.
7. **Mud score diagnostics:** histograms and threshold-wise TP/FP/FN,
   precision and recall. Scores are normalized but uncalibrated, and these curves
   are diagnostic; no deployment threshold is selected on the test set.
8. **Visual evidence:** original/ground-truth/prediction-error examples from
   selected validation predictions. The deterministic selection shows low/high
   mud-IoU positive images and negative images with the most false positives.
9. **Resource accounting:** durable start/end/exit records for every worker
   attempt and subprocess phase, including failed attempts; whole GPU-reserved
   wall time and GPU-hours; sampled device memory, utilization, board power and
   temperature. Missing telemetry is explicitly recorded. An unresolved earlier
   worker-attempt duration prevents claiming complete whole-run timing.
10. **Standardized inference:** L40S, batch 1, 1024x1024, BF16 public forward,
    20 warmup and 100 CUDA-event-timed iterations. Retain parameter count,
    parameter memory/dtypes, checkpoint size, FPS, mean/p50/p95 latency and all
    timing samples, peak allocator-reserved inference VRAM, hardware UUID,
    exact checkpoint/code/config hashes and the benchmark contract.

GPU-reserved hours include initialization, checkpoint I/O and orchestration,
not just active GPU kernels. Sampled device memory includes context and can miss
brief peaks; allocator-reserved high-water marks are separate measurements.
Inference profiling shares no GPU with training, though other GPUs on the host
may still be busy. Full-pipeline evaluation throughput is separate from
model-only FPS and includes loading, tiling and metrics.

## Publication and retention

Each model's Markdown page shows all initialization paths and seeds. Machine
records retain every run. The index reports mud IoU mean and sample standard
deviation when enough seeds have completed, plus individual results and resource
measurements. Full-run timing, raw/EMA comparisons, per-image CSVs, compressed
confusion matrices, group metrics, score curves and validation examples are linked.
Large prediction-mask directories and raw attempt logs remain on HDRFS with
paths and hashes. Global status links to per-model records instead of duplicating
all detailed evidence into a single oversized JSON file.

The publisher runs from its own tools checkout and writes only the RTIS report
paths. The previous pilot stays accessible through its immutable Git commit and
its original HDRFS campaign directory. Training code and plans are frozen per
campaign. There is only one live report publisher.

Periodic checkpoints are deleted only after the complete collection contract
passes. Selected and final checkpoints are retained. A failed collection retains
its recovery checkpoints, logs and partial evidence; it is not reported as a
successful model with missing statistics.

## Interpretation limits

The labels have not been re-adjudicated. The [mud-pumping audit](../results/paul-test-rtis/mud-pumping-audit/README.md)
shows large differences in scene coverage and annotation extent. More telemetry
cannot resolve the semantic definition of mud-pumping by itself. Three seeds and
millions of correlated pixels do not justify a population confidence interval
for unseen rail recordings. Pixel segmentation metrics are not event-level
anomaly detection rates; event ground truth and an event definition would be
needed for those claims.

Training-set diagnostic inference pads RGB frames at the bottom/right to multiples of 32 before normalization, then crops predictions to the original dimensions. Padding contributes no metric pixels. Validation uses the unchanged standalone evaluation pipeline and must reproduce its confusion matrix exactly.
