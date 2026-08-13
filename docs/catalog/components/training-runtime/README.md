# Training runtime choices

Training is iteration-based: a stage ends after a fixed number of optimizer
steps, so different dataset sizes do not silently redefine the compute budget.

## Beginner choice

Use one visible GPU, batch size 2, no accumulation, BF16 on supported hardware,
EMA enabled, and frequent enough validation/checkpoints to catch a bad run:

```yaml
train:
  iters: 40000
  batch_size: 2
  accum: 1
  num_workers: 8
  precision: bf16-mixed
  ema_decay: 0.9998
  val_every: 4000
  ckpt_every: 4000
  seed: 0
  devices: 1
```

Print the merged config before launching. Adjust worker count to the actual
storage/CPU, then scale GPUs only after one-device correctness is established.

## Exact switches

| switch | behavior and tradeoff |
|---|---|
| `iters` | default optimizer-step budget; a stage's `iters` overrides it |
| `batch_size` | samples per device; more VRAM, often better throughput/BatchNorm statistics |
| `accum` | forward/backward batches per optimizer step; saves VRAM but does not enlarge each BatchNorm batch |
| `num_workers` | training-loader processes; `0` loads in-process and is explicitly transform-seeded |
| `precision` | non-empty Lightning precision string; hardware/runtime validates actual support |
| `ema_decay` | `(0,1)` shadow decay; `null` disables EMA and makes `eval --ema` invalid |
| `val_every` | optimizer-step interval for native validation |
| `ckpt_every` | interval for retained `step-XXXXXXXX.ckpt` recovery files |
| `seed` | initialization, sampling, worker, and augmentation replicate seed |
| `devices` | `auto` or count in config; CLI `--devices` can select count/comma-separated IDs |

Effective optimizer batch is:

```text
batch_size * number of devices * accum
```

## Checkpoints and stage handoff

- `step-XXXXXXXX.ckpt` files are periodic recovery snapshots.
- `best.ckpt` is selected by validation mIoU.
- `last.ckpt` is explicitly saved after fit at the true final optimizer step.
- EMA shadow state is stored separately inside every modern checkpoint.
- `init_from: previous` hands the evaluated EMA weights to the next stage when
  present. It starts a fresh optimizer/scheduler; it is not an interrupted-run
  resume feature.

## Multi-GPU behavior

More than one device enables synchronized BatchNorm and DDP. Full tuning uses
ordinary DDP; frozen/LoRA modes enable unused-parameter discovery because their
graphs deliberately omit base weights. `devices: auto` means all devices visible
to the process, so use `CUDA_VISIBLE_DEVICES` or explicit CLI IDs to isolate a
job. The config should mirror the real choice for auditable provenance.

Training falls back to CPU when CUDA is unavailable, but production-sized
segmentation schedules are generally impractical there and BF16 support is
hardware dependent.

## Pros and cons

Iteration budgets make differently sized datasets comparable, explicit
accumulation exposes effective batch, and saved EMA/recovery/final states make
handoff auditable. The costs are more checkpoint storage, native-validation
overhead, and additional DDP/SyncBN complexity when scaling beyond one device.
Automatic device selection is convenient but can consume every visible GPU, so
shared hosts should isolate visibility explicitly.

## Reproducibility versus speed

`segmentary-train --deterministic` requests deterministic kernels. It is useful to
reproduce a discrepancy and can reduce throughput. A deterministic single seed
does not measure uncertainty; reported model/curriculum conclusions should use
the same several seeds.

Native validation can dominate wall time, especially with overlapping windows
or TTA. Increasing `val_every` saves time but hides failures longer. Increasing
`ckpt_every` saves storage but reduces recovery granularity. These are separate
switches.

## Evidence and benchmark boundary

Tests cover stage step overrides, exact true-final checkpoint saving, periodic
cadence, EMA persistence/restore, multi-device strategy, SyncBN selection, and
seeded workers/transforms. The tracked multi-GPU Cityscapes reference is listed
on the [benchmark evidence page](../../../benchmarks/README.md). Runtime from one
model/dataset cannot be generalized to another architecture, crop, GPU, or
storage system.

## Related documentation

- [Optimization](../optimization/README.md)
- [Evaluation](../evaluation/README.md)
- [Curriculum catalog](../../curricula/README.md)
- [Configuration guide](../../../guides/configuration.md)
