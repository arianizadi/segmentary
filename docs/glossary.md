# Glossary

This page translates the terms used in Segmentary configs, logs, and result files.
The short definition is enough for normal use; the “why it matters” sentence is
the part to read when designing an experiment.

## Data and labels

**Semantic segmentation**
A model assigns a class to every image pixel. Unlike object detection, the
output is a full map rather than a list of boxes. It is useful for exact rail
boundaries, but annotation and native-resolution evaluation are expensive.

**Class**
One meaning the model can predict, such as `human`, `rail-raised`, or `sky`.

**Native ID**
The number stored by the original dataset for a class. Native ID 1 in one
dataset does not have to mean the same thing as ID 1 in another.

**Canonical label space**
The single class list used by a Segmentary model across datasets. Mapping both
datasets into one space makes a shared output head possible, but coarser source
labels cannot be split into detail they never contained.

**Mapping / lookup table (LUT)**
The declared conversion from native IDs to canonical IDs. Segmentary compiles it
into a 256-entry array, making conversion fast and auditable. Unknown IDs become
ignore, never accidental supervision.

**`ignore_index` (255)**
A mask value that contributes no loss or metric pixels. It is appropriate for
unlabelled/padded regions; overusing it hides useful data.

**Active-class mask**
A Boolean list saying which canonical classes a particular dataset can label.
Inactive output channels are removed from that sample's training softmax so a
missing annotation category is not treated as a negative example.

**Split**
The assignment of samples to train, validation, and test. Video frames should be
grouped by recording/run before splitting to prevent near-duplicate leakage.

**Dataset name**
The logical identity recorded in batches, sampling weights, logs, and results.
It can differ from both the loader implementation and mapping filename.

**Dataset loader**
Code that indexes and reads one source format. `folder` is the portable paired
image/mask loader; a reviewed `package.module:SegDatasetSubclass` is the advanced
extension form.

**Mapping stem**
The YAML filename (without extension) under `taxonomy/<space>/`. It describes
native IDs independently of the logical dataset name.

**Loader options**
A per-dataset mapping of implementation-specific settings such as folder names,
extensions, recursion, or group requirements. Core arguments cannot be replaced
through this mapping.

**Data leakage**
Information from validation/test appears in training, often through adjacent
video frames. It can make metrics look dramatically better without improving
real generalization.

## Model pieces

**Backbone**
The large feature extractor initialized from pretrained weights. It holds most
parameters and learned visual representations.

**Head / classifier**
The final model part that turns features into raw logits. Multiclass uses one
channel per canonical class; native binary uses one class-1 positive channel
for canonical IDs 0 and 1, whose taxonomy names may be domain-specific. Segmentary uses one unified head;
`reset_head: true` deliberately reinitializes it for an ablation.

**Logit**
An unnormalized score output for a class at a pixel. Softmax converts competing
multiclass logits into probabilities and argmax selects a class. Native binary
uses sigmoid on its one class-1 positive logit and compares it with a recorded
threshold.

**Pretrained weights**
Model parameters learned on an earlier large dataset. They reduce the data and
time needed for a new task, but their source domain and license still matter.

**`hf_auto`**
The conservative generic integration for complete standard Hugging Face
semantic-segmentation checkpoints. It disables remote code and audits that only
the final classifier changes when the label count differs.

**Full tuning**
All supported model parameters learn. It offers the most adaptation and consumes
the most optimizer memory; small datasets can overfit or forget earlier domains.

**Frozen backbone**
Backbone parameters stay fixed while the head learns. This is cheap and tests
feature quality, but it caps domain adaptation.

**LoRA**
Small trainable low-rank matrices are inserted into selected layers while base
weights stay fixed. It saves trainable state, but target layer names are
architecture-specific and must be verified.

## Training and curricula

**Stage**
One dataset/mix, initialization rule, and optimizer-step budget. A stage writes
its own checkpoint and result record.

**Curriculum**
An ordered list of stages. `cs_rs` means Cityscapes first, then RailSem19. Order
can improve transfer or cause forgetting, so one-stage and joint controls are
needed.

**Joint training**
Samples from multiple datasets are drawn within one stage. It removes explicit
ordering but adds a sampling-ratio choice and mixed supervision patterns.

**Optimizer step / iteration**
One parameter update. Segmentary schedules stages by steps rather than epochs so
datasets of different sizes receive an explicit compute budget.

**Epoch**
Roughly one pass through a dataset. It is familiar, but not the primary schedule
unit here because replacement sampling and mixed datasets make epochs ambiguous.

**Per-device batch size**
Images processed by each GPU per forward pass.

**Gradient accumulation (`accum`)**
Several forward/backward passes are combined before one optimizer step. It
reduces memory pressure but does not give BatchNorm a physically larger batch.

**Effective batch size**
`batch_size × devices × accum`. Match it across comparison arms unless batch is
the variable being studied.

**Learning rate (LR)**
The size of each optimizer update. Too high can destroy pretrained features; too
low can make a short later stage learn almost nothing.

**Warmup**
A gradual learning-rate increase at the beginning. It stabilizes early training
but consumes part of a short schedule.

**EMA (exponential moving average)**
A smoothed shadow of model weights. It often produces steadier evaluation, but
must be explicitly saved, loaded, and labeled as EMA rather than raw weights.

**Checkpoint**
A saved training state. `best.ckpt` is validation-selected; `last.ckpt` is the
true fixed-step final state used for curriculum handoff. They answer different
questions.

**Seed**
A number controlling reproducible random streams. Multiple optimizer seeds show
run-to-run variation; they are not cross-validation when the data split is fixed.

## Evaluation and evidence

**mIoU (mean intersection over union)**
For each scored class, overlap divided by union, then averaged. It is the primary
segmentation metric, but a mean can hide weak rare classes.

**Per-class IoU**
IoU reported separately for every class. This is essential for rare or
task-critical classes because large background regions can dominate aggregate
behavior.

**Boundary F1**
Precision/recall of predicted contours within a fixed tolerance. It exposes
blurry or displaced thin structures that region mIoU can understate.

**Sliding-window inference**
A large native image is evaluated in overlapping tiles and stitched. It preserves
small details and consumes more time than resizing the whole frame down.

**Window and stride**
Window is the tile size; stride is how far the next tile moves. Smaller stride
means more overlap and usually fewer seams, at a higher compute cost.

**TTA (test-time augmentation)**
Average predictions from scaled and/or flipped views. It can improve accuracy
and multiplies inference cost, so it is a separately named variant, not default.

**Common endpoint**
Every checkpoint is evaluated on the same dataset, split, weights policy, and
inference settings. Native stage metrics are useful diagnostics but cannot form
a fair curriculum table when their validation datasets differ.

**Mean ± sample standard deviation**
Average performance across seeds plus observed spread. Three seeds reveal basic
instability but rarely justify a strong significance claim.

**Config hash**
A stable fingerprint of the fully resolved experiment config. Different hashes
help catch records that should not be averaged as replicates.

**Provenance**
The recorded Git commit, dirty/clean state, config, seed, environment, dataset
size, timing, and hardware facts behind a result. It turns a number into an
auditable experiment.

## Export and deployment

**ONNX**
A portable model graph format. It is useful for interoperability and parity
checking, but an exported graph still needs a runtime.

**ONNX Runtime (ORT)**
One engine that executes ONNX graphs. It is simpler and more portable than a
TensorRT engine, but it was not the fastest verified backend in this project.

**TensorRT**
NVIDIA's optimizing inference engine. It can be very fast, but artifacts depend
on GPU/software compatibility and should be rebuilt after major changes.

**FP16**
16-bit floating-point inference. It usually reduces memory/compute while
retaining accuracy well, but parity must still be measured.

**INT8 and calibration**
8-bit inference needs representative calibration data to choose numeric ranges.
It can be smaller/faster, but poor calibration can seriously reduce accuracy and
the available kernels may still make it slower than FP16.
