# Reviewed performance changes

The [investigation](README.md) found repeated CPU preprocessing and reconstruction
around short GPU inference bursts. The implementation now caches image-only
inputs across validation epochs, overlaps bounded CPU work around serial model
inference, and uses exact finite three-class argmax without a full channel stack.
It also removes repeated prediction checkpoint hashing and records checkpoint,
validation and prediction component times explicitly.

## Real CT check on HDRFS

Two audited **training** CTs, with 9,699,328 and 24,379,392 native voxels, used the
same verified scratch-origin U-Net2D best checkpoint (epoch 70, step 7,000), BF16
recipe and GPU. Labels were not opened. Synthetic warmup was outside the timing.
The original source and checkpoint were unchanged. The diagnostic acquired the
ordinary medical GPU lock and ran on an otherwise idle GPU.

| Path | Two-case wall seconds | Relative to original |
|---|---:|---:|
| Original serial pipeline | 6.675 | 1.00× |
| New pipeline, building derived caches | 4.561 | 1.46× |
| New pipeline, same-loader warm caches | 2.427 | 2.75× |

Both new passes produced **zero native label differences across 34,078,720
voxels**. All 166 model-forward input shapes, dtypes and their order matched.
The three changed inference modules are pinned in the
[verification record](real-ct-verification.json).

The final telemetry-inclusive source was rechecked after the initial 7.210 /
4.928 / 2.698-second pass, again with exact native labels. The table pins this
final-source check. These were sequential original/cold/warm measurements on two cases and one
model. They exclude NIfTI export and scoring. They do not establish a general
2.75× campaign speedup, model quality improvement, or equality for every model.
Cold startup and new-stage verification remain real costs. Full-cohort outputs
and timing are collected separately under the continuation source identity.

## Claude Fable review and integration decisions

The requested command was `claude -p --model fable --effort high`, in a separate
worktree. The completed CLI response reports `claude-fable-5-1` as the main review
model, with high effort recorded in its transcript. It inspected source, live
read-only server metrics, upstream implementation details and ran local tests.
Its worktree patch was reviewed and integrated selectively, then tested again in
the combined implementation.

Accepted:

- Read checkpoint bytes once in the worker, verify their SHA against the bound
  index, deserialize those exact bytes and record that digest for each prediction.
  This removes per-case rereading and the gap between hash and deserialize.
- Label initial and epoch-end checkpoint saves as their own progress phase and
  measure duration. Saving, fsync and index publication remain synchronous.
- Keep export validation, cache invalidation and finite/tie behavior strict.

Review qualifications and deferred experiments:

- Stage wall minus summed case timers includes startup and other unmeasured work;
  it does **not** prove that the entire residual is checkpoint hashing. Likewise,
  the prior inter-epoch gap is not a direct isolated checkpoint benchmark.
- Adding separately measured CPU components gives an illustration, not a
  per-model CPU floor. A launch-bound explanation for transformer timing remains
  an inference without a CUDA timeline. Larger cuBLAS workspace alone does not
  prove a setting cannot reduce performance.
- Diagonal-only resampling and cross-slice batching change floating-point
  behavior. They remain separate benchmark candidates. General valid NIfTI
  geometry must not be assumed diagonal.
- Background checkpoint writes require a complete immutable CPU snapshot and
  carefully ordered error/fsync/index handling. Their benefit is not established
  by the current paired inference measurement; they are deferred.
- MaskFormer selected an almost whole-volume mass prediction because its tiny
  positive mass Dice exceeded later zero scores. This is a failed-learning result
  to show honestly. We do not retroactively change the selection rule or suppress
  a poor model to improve rankings. Large false-positive regions can also make
  surface-distance evaluation expensive.

## Checkpoint continuation and reporting

The original source/binding guards remain in force. The new
[continuation procedure](../../../../guides/medical-performance-continuation.md)
creates another workspace with explicit parent lineage and verifies full state
preservation. Completed runs reuse their original best checkpoint for prediction;
unfinished runs resume the latest complete checkpoint. Neither path restarts from
random weights. Source-run and continuation costs must be reported separately.

Targeted tests cover corrupt/changed caches and source files, thread cleanup,
native geometry, exact ties, checkpoint integrity and continuation provenance.
Real tiny-CT interrupted/resumed training matches uninterrupted training exactly
for model, optimizer, scheduler, scaler, all recorded RNGs, epoch, step and best,
with training prefetch enabled and disabled.
