# Troubleshooting and reproducibility

Segmentary fails loudly when a plausible-looking run would be scientifically
wrong. Start with the exact error; do not weaken validation to make it disappear.

## Fast health check

```bash
cd segmentary
export PYTHONPATH=src

python -m pip check
python -m pytest -m 'not slow and not gpu' -q
ruff check src tests scripts
ruff format --check src tests scripts
nvidia-smi
```

## Config errors

**Unknown key with a dotted path**

This is usually a typo or a setting placed at the wrong nesting level. Compare
with `configs/base.yaml` and `src/segmentary/config.py`. Do not add `**kwargs` or
delete the check; an ignored experiment setting creates a false ablation.

**A list disappeared after merge**

Lists replace; they do not concatenate. An override containing `stages:` must
include the entire intended stage list. Inspect `--print-config`.

**`per_stage_head` is not implemented**

Use `model.head: unified_head`. To test classifier reinitialization, set
`reset_head: true` on the desired stage.

## Data and taxonomy errors

**RailSem19 requires `split_file`**

The dataset has no accepted official full split. Use the committed
`splits/railsem19_seed0.json` or create and version an explicit alternative.

**Custom dataset requires `splits.json` / groups overlap**

Generate it with `segmentary-make-split`. If groups overlap, rebuild the
split by run/sequence; never suppress the check or split adjacent frames.

For independent paired images, the generic `folder` loader does not require a
manifest. For video/burst data, set `require_groups: true` intentionally.

**Unknown dataset loader**

Set `loader: folder` for paired files, use a known built-in format, or provide a
reviewed `package.module:SegDatasetSubclass`. `name` is a logical identity and
does not have to equal the loader ID.

**Mask contains undeclared ids**

Inspect the raw mask values and mapping YAML. Add a deliberate mapping or ignore
rule. Keep `default: ignore_index`; never map unknown ids to a real class.

**Loss becomes NaN**

Segmentary already handles all-ignore crops. Check input logits/weights, learning
rate, corrupt image values, and whether a third-party model returns finite dense
logits. Search the first nonfinite step rather than only the final checkpoint.

## Model and checkpoint errors

**Pretrained checkpoint cannot load**

Verify network access, Hugging Face cache, model id, and license approval. The
factory intentionally has no random-init fallback. For licensed local DINOv3,
use only a schema the converter explicitly supports.

**`hf_auto` refuses a partial load or layout**

Use a complete standard `AutoModelForSemanticSegmentation` checkpoint. An
encoder-only checkpoint or discarded auxiliary head is not classifier-only
adaptation. If the standard model layout is safe but ambiguous, provide the
complete advanced path triplet; do not use `strict=False` or remote code.

**Checkpoint has missing/unexpected keys**

The config architecture/head must match the checkpoint. Stage handoff also
validates every model parameter. Do not use `strict=False` as a generic escape;
it can silently leave a backbone random.

**`--ema` says no EMA weights**

The artifact is raw-only. Evaluate without `--ema` and label it as raw, or use a
new checkpoint that persisted `ema_state_dict`. Historical calibration artifacts
cannot be retroactively converted into the in-memory EMA that produced a score.

**Mask2Former+DINOv3 is blocked**

This is architectural, not a missing-download problem. A plain DINOv3 ViT exposes
flat stride-16 features; the official segmentation system adds an adapter and
spatial-prior pyramid. Implement and verify that before enabling the arm.

## GPU and distributed issues

**Out of memory**

Reduce per-device `train.batch_size`, then use `train.accum` to preserve effective
batch if needed. Smaller crops save more memory but change context and must be
kept fixed across comparisons. Also check for another process in `nvidia-smi`.

**DDP hangs or NCCL errors**

Confirm all ranks see the same files and code, ports are unique, the requested
GPU count exists, and no rank hit an earlier exception. Capture every rank's log.
Do not retry on a dirty or changed commit under the same run directory.

**Evaluation hangs after training in one Python process**

Run standalone evaluation as a fresh process, as shown in the tutorials. A
custom program that initializes CUDA/Lightning and then forks DataLoader workers
can inherit locked runtime state. Segmentary evaluation uses fresh spawned workers
by default. Custom datasets must therefore be picklable; set
`eval.num_workers: 0` or pass `--num-workers 0` to load them in-process. Do not
fork new workers after CUDA initialization.

**Torch suddenly cannot see CUDA**

Check `torch.__version__`, `torch.version.cuda`, GPU visibility, and driver.
Restore the platform-appropriate PyTorch build instead of layering another wheel
onto the environment. The bundled reproduction host has a separate tested pin.

## Results and table errors

**Table rejects config differences beyond seed**

Those records are not replicates. Generate separate experiment names/groups or
rerun with identical settings. Learning rate, tuning mode, batch, or stage budget
differences must not collapse into one mean.

**Table rejects dirty or mixed git provenance**

Commit the intended source first and rerun. A dirty single exploratory record can
be inspected, but it cannot prove multiple seeds used identical code.

**A native stage score disagrees with a common eval**

Check dataset, split, EMA/raw selection, TTA, checkpoint (best versus final), and
label space. Native joint validation uses its first configured dataset; use an
explicit common-target evaluation for cross-curriculum conclusions.

## Reproducible long-run checklist

1. `git status --porcelain` is empty and HEAD is pushed.
2. Config is printed/validated; seed and device/effective batch are embedded.
3. Output directory does not already exist.
4. Dataset splits and taxonomy mappings are versioned.
5. Logs and run status are written outside the source tree or ignored.
6. Long jobs run under the site scheduler or a persistent session; respect GPU reservations.
7. After training, verify `last.ckpt` global step and EMA update count.
8. Evaluate every arm under one explicit common protocol.
9. Generate tables from `results.json`; do not type metrics by hand.
10. Run the complete tests, coverage, dependency check, dataset verification,
    lint, and a clean push before declaring the campaign done.
