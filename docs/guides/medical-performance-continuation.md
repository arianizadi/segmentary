# Performance changes and scratch checkpoint continuation

Segmentary caches image-only validation inputs and overlaps CPU preparation and
native reconstruction with serial model inference. The objective, optimizer,
sampling RNG, augmentation, tiling order, batch composition, precision, and native
interpolation remain the same. Model execution stays on one thread.

## What is cached and measured

An inference cache contains normalized CT images and audited geometry, never
validation labels. The first use in each worker verifies raw image and cache
hashes. Later epochs check file identity and change metadata. A new stage verifies
the hashes again. Cold creation retains the original preprocessing audit; warm
reuse avoids repeated decoding/resampling. Changes and corrupt caches fail loudly.
At most two mmap entries are retained; in-flight arrays remain valid on eviction.
Export still verifies the saved native NIfTI prediction.

One preparation worker and one reconstruction worker can overlap with inference;
`workers: 1` stays serial. Channel interpolation uses at most three threads.
Finite three-class native argmax preserves NumPy's first-class tie rule exactly.

Training metrics retain epoch training, validation and checkpoint seconds. The
dashboard labels checkpoint work explicitly. Validation records per-case timings,
metrics timing and cumulative cache counters. Prediction status records per-case
preprocessing, tiled inference, native reconstruction and export time, aggregate
pipeline wall time, cache counters and CUDA allocator peaks. CPU allocator peaks
are unmeasured. Case/component times overlap and must not be added to estimate
stage wall time. Tiled inference includes input copies, softmax and CPU blending;
it is not a model-only latency measurement.

Prediction records also retain the image-only maximum native class-2 probability
as an explicit continuous scan score, plus native and predicted-mass voxel
counts. This does not change segmentation or checkpoint selection. A separate
detection diagnostic may use that score for ROC-AUC only when both reference
classes exist. Task07 semantic mass components are lesion proxies, and neither
their presence nor their absence establishes a clinical cancer diagnosis.

Checkpoint loading verifies and deserializes one immutable byte snapshot and
reuses its digest in per-case output records. This temporarily holds serialized
bytes and loaded state in RAM; budget roughly twice the checkpoint size in
addition to the model. Checkpoint saving remains synchronous and atomic.

## Continue an existing scratch run after a reviewed performance change

Never edit an active frozen source tree or replace a binding hash to make an old
checkpoint load. An explicit continuation creates a **new workspace and source
identity**, retaining the parent lineage. It is the same training trajectory,
not an independent seed or another scratch experiment.

1. Finish or cleanly stop the old stage at a saved checkpoint. The importer
   requires its stage lock to be free and no active stage recorded. Preserve the
   original source snapshot and workspace.
2. Copy the resolved recipe and change only `workspace`. The model, GPU assignment,
   runtime, data, split, seed and all scientific settings must remain identical.
3. Create a reviewed JSON policy with `schema_version: 1`,
   `purpose: "performance-only"`, complete `source_code` and `target_code` maps
   from `continuation.code_hashes`, exact `allowed_changed_files`, a written
   `review`, and `verification_evidence` entries containing `path`, `sha256` and
   `description`. Hash maps pin the actual complete medical source trees.
4. Run the command below **with the recorded backend Python interpreter**. Use
   `--dry-run` first. Use `resume` for unfinished training or `predict` for a run
   that already completed its budget.

```bash
PYTHONPATH=/path/to/new-checkout/src /path/to/recorded-backend/python \
  -m segmentary.medical.cli continue-scratch \
  --source-workspace /path/to/old-run \
  --config /path/to/new-recipe.yaml \
  --source-code-root /path/to/frozen-checkout/src/segmentary/medical \
  --policy /path/to/reviewed-policy.json \
  --action resume --dry-run
```

Run again without `--dry-run`, then run normal `preprocess` before either `train
--resume` or `predict`. An existing training cache is not silently assigned a new
source identity. The campaign runner recognizes completed prediction
continuations and skips optimizer updates while still verifying training state.
Preserve the original GPU assignment when initializing a continuation campaign.

The importer preserves all indexed latest/best/final aliases and the original
checkpoint bytes in `continuation-parent/`. New checkpoint generations change
only binding/origin identity. Structural state digests verify model, optimizer,
scheduler, scaler, all recorded RNGs, epoch, step and best score. The parent
manifest, split, runtime, source and checkpoint hashes must verify. Publication is
atomic; `continuation.json` and binding lineage document the transformation.

The policy allows only explicitly reviewed implementation files and additionally
protects sampling and objective functions. It cannot establish correctness by
itself: pair it with numerical regression tests and real-data checks. Changes to
models, losses, batching, numerical methods or training budgets require a separate
scientific experiment, not this performance-only continuation mechanism.
