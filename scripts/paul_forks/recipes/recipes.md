# Paul-fork recipes for the RAD 9/24 comparison

Paul's checkpoints and our own retrained RailSem19 (RS19) stages are run side by side. Every
run label says whose checkpoint each stage came from.

## Run labels

| Label | Init chain (owner) | Recipe script |
|---|---|---|
| `hrnet-rs19-ours` | Map→City `nimble-chihuahua` (**nvidia**) → RS19 (**ours**) | `hrnet-rs19-ours.sh` |
| `sfnet-rs19-ours` | Map→City `rs18 79.9` (**public-sfnet-authors**) → RS19 (**ours**) | `sfnet-rs19-ours.sh` |
| `paper-hrnet__rs19-paul__arm-<arm>` | **nvidia** → RS19 `0.7385` (**paul**) → RAD (**ours**) | `paper-hrnet.sh --rs19 paul` |
| `paper-hrnet__rs19-ours__arm-<arm>` | **nvidia** → RS19 from `hrnet-rs19-ours` (**ours**) → RAD (**ours**) | `paper-hrnet.sh --rs19 ours --rs19-ckpt …` |
| `paper-sfnet__rs19-ours__arm-<arm>` | **public-sfnet-authors** → RS19 from `sfnet-rs19-ours` (**ours**) → RAD (**ours**) | `paper-sfnet.sh --rs19 ours --rs19-ckpt …` |
| `paper-sfnet__rs19-paul__arm-<arm>` | reserved: only if Paul sends `railsem19_sfnet_resnet18_mean-iu_0.75268.pth`. Refused (by `write_provenance.py` and the scorer) until its SHA-256 is pinned as `("paul","rs19","sfnet")` in `write_provenance.PINS` and `("paper-sfnet","rs19-paul")` in `score_predictions.PINNED` | `paper-sfnet.sh --rs19 paul --rs19-ckpt …` |
| `paul-reference__rr22-0.8964` | Paul's finished RAD model | **no recipe.** Reference only; NEVER scored on our splits: it may have trained on our val/test images. |

`<arm>` ∈ `paul`, `fixed-stratified`, `fixed-grouped`. Only these labels can be written
(`write_provenance.py` holds the frozen set). Table rows must use the label, for example
"HRNet Map→City(NVIDIA)→RS19(Paul)→RAD" versus "HRNet Map→City(NVIDIA)→RS19(ours)→RAD".

## What every recipe does

- `set -euo pipefail`; flags `--arm`, `--gpus`, `--run-dir` (absolute), `--dry-run`.
- Refuses any GPU outside 2-9, duplicates, and the wrong GPU count, before anything else.
  This is the second line of defence; `scripts/paul_forks/fork_gpu_run.py` is the first.
  It also refuses if `CUDA_VISIBLE_DEVICES` is set in the calling shell; only `--dry-run`
  accepts `CUDA_VISIBLE_DEVICES=""` (it never starts the launcher).
- Outside `--dry-run`, the launcher must be the `fork_gpu_run.py` next to these recipes
  (`FORK_GPU_RUN` may point elsewhere only for dry runs), the fork clone's content digest
  must equal `PAUL_PATCHES_TREE` written by `apply_patches.sh`, every checkpoint we did not
  train must have a pinned SHA-256, the RAD adapter's `manifest.json` must name
  `rad_9_24_2026-<arm>` and that arm's `splits.json`/`classes.json`/`audit/samples.json`
  must be unchanged since the adapter was built, and an `--rs19 ours` checkpoint must come
  from a run whose `gpu-assignment.json` says `exited` with exit code 0.
- Every `provenance.json` lists the P0 behaviour changes as deviations: every rank seeded
  with 0 (Paul's code was unseeded) and, for HRNet, the RMI loss computed in FP32.
- Refuses a non-empty run directory, then creates `<run_dir>/centroids/` (empty).
  `PAUL_CENTROID_ROOT` points there, so no September or cross-arm centroid cache is reused.
- Writes `<run_dir>/provenance.json` **before** launching (refuses to overwrite one):
  `label`, `owner_of_each_checkpoint_in_chain` (stage, owner, role, path, resolved path,
  sha256), `checkpoints`, `build_time_weights` (ImageNet files the model constructor loads),
  `fork_git` (origin, commit, each applied patch + sha256 checked against
  `scripts/paul_forks/patches`, sha256 of the live `git diff`), `recipe` (source commit/file,
  script sha256, `args_verbatim`), `deviations`, `gpu_assignment` (indices, UUIDs, PCI bus ids
  from the launcher's frozen table), `data` (sha256 of the adapter's `classes.json` etc.),
  `environment` (`PAUL_*`), `probe_epochs`, `dry_run`.
- Launches `python fork_gpu_run.py --gpus <G> --run-dir <run_dir> --python <env python> --
  <env python> -m torch.distributed.run --standalone --nproc_per_node=<N> <src>/train.py …`
  with `--apex` (DDP, one process per GPU), from `<run_dir>` as working directory, appending
  to `<run_dir>/console.log`. The launcher adds `gpu-assignment.json` and telemetry.
- `--dry-run` (or `PAUL_FORK_DRY_RUN=1`) writes provenance with `"dry_run": true` and prints
  the launch command instead of running it.
- `PROBE_EPOCHS=1|2` sets `--max_epoch` to 1 or 2 for timing (the poly LR curve then differs:
  never a result). The run directory name must contain `probe`; provenance records it.

Defaults (override through the environment): `PAUL_FORK_RUN_ROOT=/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24`,
`PAUL_FORK_ENV=/data/izadia1/envs/paul-segmentation-20260915`,
`PAUL_FORK_RS19_ROOT=/data/izadia1/datasets/railsem19-paul-split`,
`PAUL_FORK_ADAPTERS=$PAUL_FORK_RUN_ROOT/adapters` (one `adapt_rad.py` output per arm),
`FORK_GPU_RUN=<recipes>/../fork_gpu_run.py`, `PAUL_FORK_PATCHES=<recipes>/../patches`.

## Recipes and where they come from

**Defaults (2026-10-05): the hyperparameter files Paul shared for this work**, tracked in
`scripts/paul_forks/hyperparameters/` (SHA256SUMS; HDRFS copy
`/data/izadia1/checkpoints/paul-hyperparameters-drive`). Variant `paul-shared-20260923`:

| Recipe | Shared file | Settings |
|---|---|---|
| `hrnet-rs19-ours` | `hrnet/train_rs19.yml` | lr 1e-4, 150 epochs, mscale weight 0.1, n_scales 0.5,1.0,2.0 |
| `paper-hrnet` | `hrnet/train_rtisrail22.yml` | lr 7e-5, 1000 epochs, mscale weight 0.05, n_scales 0.5,1.0,1.5 |
| `paper-sfnet` | `sfnet/train_rtisrail22_sfnet_res18.sh` | lr 0.002, 1000 epochs |
| `sfnet-rs19-ours` | `sfnet/train_railsem19_sfnet_res18.sh` | unchanged (lr 0.0025, 400 epochs) |

These differ from the commands stored inside Paul's checkpoints (0.7385: lr 5e-4, 300
epochs, weight 0.05; 0.8964: train_2, lr 1e-4, 500 epochs). Those remain selectable as
`HRNET_RS19_RECIPE=ckpt-0.7385`, `HRNET_RAD_RECIPE=train_2` and `SFNET_RAD_RECIPE=train_2`;
each run records its variant in `provenance.json`. The sections below describe the
checkpoint-embedded variants.

### `hrnet-rs19-ours` (4 GPUs, bs_trn 1 each)

Variant `HRNET_RS19_RECIPE=ckpt-0.7385`:

```
--dataset railsem19 --cv 0 --syncbn --apex --fp16 --gblur --brt_aug --crop_size 1080,1920
--bs_trn 1 --poly_exp 2 --lr 5e-4 --rmi_loss --max_epoch 300 --n_scales 0.5,1.0,2.0
--supervised_mscale_loss_wt 0.05 --snapshot <nimble-chihuahua> --arch ocrnet.HRNet_Mscale
```

**This contradicts the plan / verify report (lr 1e-4, 150 epochs, weight 0.1), on purpose.**
That is git HEAD `scripts/train_rs19.yml` @ 9fbd50f (2022-02-17), but Paul's own
`rs19_cityscapes_ep98_miou_0.7385.pth` stores the command that produced it:
`--lr 5e-4 --max_epoch 300 --supervised_mscale_loss_wt 0.05 … --result_dir
logs/rs19/cityscapes_sota_rs19_finetune_bs_1`, identical to `train_rs19.yml` @ 8c2a170
(2022-02-08). The 9fbd50f settings went to a new result dir (`…_bs_2`) whose checkpoint is
not the one Paul used downstream. `HRNET_RS19_RECIPE=git-head-9fbd50f` selects them anyway
and records the deviation. Best epoch of Paul's run was 98 of 300; whether that run
finished all 300 epochs is unknown. The poly schedule depends on `max_epoch`, so stopping
early is not the same recipe.

Paul's HRNet RailSem19 loader trains on `train_images` (6800) and validates on
`test_images` (850): his RS19 checkpoint was selected on test. We keep that for fidelity
(it only selects the upstream checkpoint; RAD selection is on our held-out val).

### `sfnet-rs19-ours` (Paul: 4 GPUs × bs_mult 8)

SFSegNets-1 @ 25f315e `scripts/train_railsem19_sfnet_res18.sh` (the plan's
`scripts/railsem19/…` path does not exist at that commit), verbatim:

```
--dataset railsem19 --cv 0 --arch network.sfnet_resnet.DeepR18_SF_deeply
--class_uniform_pct 0.5 --class_uniform_tile 1080 --lr 0.0025 --lr_schedule poly --poly_exp 1.0
--repoly 1.5 --rescale 1.0 --syncbn --sgd --ohem --crop_size 1080 --scale_min 0.5 --scale_max 2.0
--color_aug 0.25 --gblur --bblur --max_epoch 400 --wt_bound 1.0 --bs_mult 8 --apex
--snapshot <pretrained_cityscapes_mapillary_rs18_miou-0.799.pth>
```

All 27 flags exist in SFSegNets-2 @ 0bb9e59's argparse (none missing). Ours adds only
`--allow_skip layer0.*,layer1.0.conv1.weight,layer1.0.downsample.*` (P2) and our
`--exp/--ckpt/--tb_path`. Code drift 25f315e → 0bb9e59 on the training path:
`resnet_d.py`, `loss.py`, `optimizer.py`, `datasets/sampler.py`, `network/__init__.py`,
`network/nn/mynn.py`, `DeepR18_SF_deeply`, `PSPModule` are identical; the RailSem19 loader
differs only by a print; **`AlignedModule` calls `grid_sample(..., align_corners=True)` in
0bb9e59 versus the torch default (False) in 25f315e** (recorded deviation; Paul's own RAD
stage ran the newer code); `uniform.py` tolerates absent classes; misc transform changes are
not on the training path. Trains on `trainVal_images` (7650), selects on `val_images` (850).
2 GPUs × 16 or 8 × 4 keep global batch 32 and are recorded as deviations.

### `paper-hrnet` (4 GPUs, bs_trn 1 each)

Variant `HRNET_RAD_RECIPE=train_2` = `scripts/train_rtisrail22.yml` @ d90f254, which is
exactly the command stored in Paul's `rr22_rs19_city_miou_0.8964.pth` (epoch 464,
`--result_dir logs/rr22/rtisrail22_train_2`). This settles the plan's open train_1/train_2
question for the HRNet paper model:

```
--dataset rtisrail22 --cv 0 --syncbn --apex --fp16 --gblur --brt_aug --crop_size 1080,1920
--bs_trn 1 --poly_exp 2 --lr 1e-4 --rmi_loss --max_epoch 500 --n_scales 0.5,1.0,1.5
--supervised_mscale_loss_wt 0.05 --snapshot <RS19 checkpoint> --arch ocrnet.HRNet_Mscale
```

Alternative kept for the record, `HRNET_RAD_RECIPE=train_1` (808d442 / 6d369c5 / 0cc4a7e):
lr 1e-4, 500 epochs, mscale weight **0.1**, n_scales **0.5,1.0,2.0**. Note train_1 also ran
at one point on 8 GPUs (6d369c5, global batch 8) and, before that, with crop 1024,1920 and
no snapshot (808d442). The recipe never uses the September values (lr 7e-5, 1000 epochs =
abandoned train_4).

In-training validation uses the recipe's `n_scales` (Mscale inference); the primary score
uses the P4 single-scale dump (`--n_scales 1.0`), secondary `--scales native` = 0.5,1.0,2.0
(`scripts/eval_rr22.yml`).

### `paper-sfnet` (Paul: 4 GPUs × bs_mult 8; plan 2B: 2 × 16)

SFSegNets-2 `scripts/rtisrail/train_rtisrail22_sfnet_res18.sh` @ fcc42b6 (train_2):

```
--dataset rtisrail22 --cv 0 --arch network.sfnet_resnet.DeepR18_SF_deeply --class_uniform_pct 0.5
--class_uniform_tile 1080 --lr 0.001 --lr_schedule poly --poly_exp 1.0 --repoly 1.5 --rescale 1.0
--syncbn --sgd --ohem --crop_size 1080 --scale_min 0.5 --scale_max 2.0 --color_aug 0.25 --gblur
--bblur --max_epoch 1000 --wt_bound 1.0 --bs_mult 8 --apex --snapshot <RS19 checkpoint>
```

Which SFNet run produced Paul's 0.88745 (train_0/1/2) is still not established.

## Deviations shared by every RAD run (also in each provenance.json)

- Data: our RAD 9/24 arms (21 classes, mud-pumping = 13, standing-water = 20) instead of
  Paul's 2022 RAD (19 classes). `trainVal_*` holds train only; Paul's held train+val.
- 19-class RS19 head re-initialised to 21 classes; P2 proves nothing else is re-initialised.
- Apex → native AMP / torch DDP / SyncBN (September port); `torch.distributed.run`.
- September evaluation fixes kept (every val image once; int64 confusion all-reduce).
- P3 adds `best_mud_epoch_N.pth`; P5 restores Paul's data-loading parallelism.

## Commands (HDRFS)

```
T=/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24/tools/paul_forks/recipes   # rsync of scripts/paul_forks
R=/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24/runs
# timing probes first (directory name must contain "probe")
PROBE_EPOCHS=1 $T/sfnet-rs19-ours.sh --gpus 2,3,4,5 --run-dir $R/sfnet-rs19-ours-probe1
PROBE_EPOCHS=1 $T/hrnet-rs19-ours.sh --gpus 2,3,4,5 --run-dir $R/hrnet-rs19-ours-probe1
PROBE_EPOCHS=2 $T/paper-hrnet.sh --rs19 paul --arm paul --gpus 2,3,4,5 --run-dir $R/paper-hrnet__rs19-paul__arm-paul-probe2
# real runs
$T/hrnet-rs19-ours.sh --gpus 2,3,4,5 --run-dir $R/hrnet-rs19-ours
$T/sfnet-rs19-ours.sh --gpus 6,7,8,9 --run-dir $R/sfnet-rs19-ours
$T/paper-hrnet.sh --rs19 paul --arm fixed-stratified --gpus 2,3,4,5 --run-dir $R/paper-hrnet__rs19-paul__arm-fixed-stratified
$T/paper-hrnet.sh --rs19 ours --rs19-ckpt $R/hrnet-rs19-ours/train/<best_checkpoint_epN.pth> --arm paul --gpus 6,7,8,9 --run-dir $R/paper-hrnet__rs19-ours__arm-paul
$T/paper-sfnet.sh --rs19 ours --rs19-ckpt $R/sfnet-rs19-ours/ckpt/sfnet-rs19-ours/<exp>/best_epoch_*.pth --arm paul --gpus 2,3,4,5 --run-dir $R/paper-sfnet__rs19-ours__arm-paul
# P4 dumps for Segmentary scoring (one GPU; val first, test only for the final table)
$T/paper-hrnet.sh --dump val --checkpoint $R/<run>/train/best_mud_epoch_N.pth --arm <arm> --gpus 9 --run-dir $R/<run>
$T/paper-sfnet.sh --dump val --checkpoint $R/<run>/ckpt/<…>/best_mud_epoch_N.pth --arm <arm> --gpus 9 --run-dir $R/<run>
```

Run each inside its own tmux session; the recipes do not daemonise. Re-sync
`tools/paul_forks/` from the repo before launching so the launcher and patches are current.

## Checks done without a GPU (HDRFS, `CUDA_VISIBLE_DEVICES=""`)

- Patched trees `$RUN/src/{hrnet,sfnet}`: P0 alone is byte-identical to the September
  working trees; the full series applies with `apply_patches.sh`; all 53 / 66 Python files
  compile; `train.py --help` runs the whole import chain and lists the new flags.
- P2 loads of every init checkpoint: see `../patches/PATCHES.md` (heads only for HRNet;
  heads + the 22 allowed stem tensors for SFNet).
- Dry runs with the real checkpoints, pins and split (`$RUN/checks/dryrun/`):
  `hrnet-rs19-ours`, `sfnet-rs19-ours`, and `paper-hrnet__rs19-paul__arm-paul` (with a
  stand-in adapter, since the RAD adapters were not built yet). The last one's
  `recipe_args` equal the command stored in Paul's `rr22_rs19_city_miou_0.8964.pth` except
  `--snapshot` and `--result_dir`. A request for GPU 1 was refused.
