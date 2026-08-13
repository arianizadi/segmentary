# All-model Cityscapes and RailSem19 campaign

The checked campaign manifest covers every shipped model recipe under three
fixed protocols:

1. Cityscapes training and validation in the standard 19-class space;
2. RailSem19-only training and validation in the 21-class `rail_union` space;
3. Cityscapes → RailSem19 staged transfer, evaluated on that same RailSem19
   split and label space.

The current manifest contains 111 logical report cells per seed. Only 108 are
physical jobs: `deeplabv3plus_r101` is a reviewed compatibility alias for
`smp_deeplabv3plus_resnet101`, so its three result cells inherit the canonical
run with explicit `alias_of` provenance.

## Safety and resumption contract

- Training runs from one frozen, clean checkout at an exact 40-character SHA.
- Every GPU lane is a named tmux session. A worker refuses to run outside tmux.
- Each lane sees one physical GPU through `CUDA_VISIBLE_DEVICES`; no job can
  accidentally allocate another lane's device.
- Jobs are assigned with deterministic longest-processing-time balancing from
  the clean admission timings. Heavy jobs start first and are spread across all
  available GPUs, minimizing the slow tail without changing the effective batch
  or adding multi-GPU communication.
- `campaign.json` is immutable. Lane status is atomically replaced after every
  transition, and every retry gets a new `attempt-NNN` directory.
- Restarting `launch` skips each validated success/reused result and retries only
  unfinished or failed cells. Earlier attempts are never overwritten.
- Existing result roots are scanned before scheduling. A clean, explicitly
  approved source revision, exact semantic config/effective-batch signature,
  correct seed/protocol/class schema, and valid metrics make a result
  reporting-complete. A missing exact checkpoint is recorded as a caveat but
  does not trigger duplicate training. When a checkpoint exists, its path and
  SHA-256 are retained as artifact provenance.
- Ambiguous equally preferred results are not guessed between. The reuse audit
  records them and leaves that cell in the queue.

## Plan without launching

```bash
python scripts/run_benchmark_campaign.py plan --seeds 0
```

The manifest's priority is an expected-quality/capacity prior, not a fabricated
benchmark ranking. EoMT/DINOv3, EoMT, BEiT/UPer, ConvNeXt/UPer, and SegFormer-B5
are scheduled first. Validated existing cells—such as SegFormer-B2—are removed
before the physical queues are written.

Both EoMT recipes receive the final
[`eomt_hungarian_query.yaml`](../../configs/campaigns/eomt_hungarian_query.yaml)
layer. It selects the native Hungarian class/mask-query objective, resets every
dense/legacy loss field, and fixes deterministic assignment sampling at 8,192
valid pixels. Their model-only YAMLs' experimental dense collapse is therefore
not part of this comparison. The default effective batch is 16 as two images
per GPU with eight-step accumulation; a local batch of two is required by
pooled-BatchNorm recipes that cannot train on a singleton tensor.

## Launch on the training server

Use an ignored run path outside the Git checkout. Repeat `--reuse-root` for each
historical campaign/result root, and explicitly whitelist each clean historical
source revision with `--reuse-sha`.

```bash
python scripts/run_benchmark_campaign.py launch \
  --campaign /path/to/runs/all-model-city-rail-seed0 \
  --expected-sha FULL_40_CHARACTER_TRAINING_SHA \
  --cityscapes-root /path/to/datasets/cityscapes \
  --railsem19-root /path/to/datasets/railsem19 \
  --gpus 0,1,2,3,4,5,6,7 \
  --seeds 0 \
  --batch-size 2 \
  --accum 8 \
  --reuse-root /path/to/existing/runs \
  --reuse-sha APPROVED_40_CHARACTER_HISTORICAL_SHA \
  --tmux-prefix segmentary-cityrail
```

Add `--dry-run` to run every read-only provenance/dataset/reuse check and print
the exact tmux commands without creating the campaign or starting a process.

The normal progress dashboard reads the resulting `lane_gpu*_status.json`
files:

```bash
segmentary-progress /path/to/runs/all-model-city-rail-seed0
```

## Incremental public reports

Documentation publishing uses a separate clean checkout. It must descend from
the frozen training SHA, but it can advance with result-only commits without
making the training checkout dirty. Pass it during launch to create a dedicated
`<prefix>-publisher` tmux session:

```bash
python scripts/run_benchmark_campaign.py launch \
  ... \
  --publisher-root /path/to/segmentary-publisher \
  --publish-remote origin \
  --publish-branch main \
  --publish-interval 30
```

Whenever another cell becomes reportable, the publisher:

1. fast-forwards the clean publisher checkout;
2. validates every available result and checkpoint/hash contract;
3. refreshes `docs/results/model-comparison/README.md` and the corresponding
   model catalog READMEs;
4. runs documentation/campaign tests and `git diff --check`;
5. commits and pushes a progress-labeled result update.

The publisher writes only generated marker regions in model READMEs and the one
comparison folder. It fails closed on unrelated edits, a non-fast-forward
branch, failed tests, or push conflicts. Publishing failures do not stop the
training tmux lanes and are visible in `publisher_status.json`.

For a read-only report preflight or a controlled one-off write:

```bash
python scripts/run_benchmark_campaign.py report \
  --campaign /path/to/runs/all-model-city-rail-seed0

python scripts/run_benchmark_campaign.py report \
  --campaign /path/to/runs/all-model-city-rail-seed0 \
  --publisher-root /path/to/segmentary-publisher \
  --write
```

The generated model sections include mIoU, mean accuracy, mean precision, mean
Dice, mean specificity, pixel accuracy, frequency-weighted IoU, boundary F1,
and full per-class IoU tables. Human-facing multi-seed cells show one clean mean;
individual seeds remain in the detailed machine provenance.
