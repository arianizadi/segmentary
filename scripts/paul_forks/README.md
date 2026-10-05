# Paul-fork tooling (RAD 9/24 paper-model comparison)

These are generic tools for running Paul Stanik's two paper forks on the three RAD 9/24
arms on HDRFS, next to the Segmentary top-10 campaign:

- HRNet-OCR-Mscale: `pauls3/semantic-segmentation@5e619e6`
- SFNet-R18: `pauls3/SFSegNets-2@0bb9e59`

Every result is labelled with whose checkpoint each stage of its init chain came from.
The tools do not patch the forks. The P1-P6 patches, the clones and the run directories
belong to the run workflow.

Run root on HDRFS: `RUN=/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24`.

| File | Purpose |
|---|---|
| `fork_gpu_run.py` | Fail-closed GPU launcher. Uses GPUs 2-9 only and never GPUs 0 or 1. |
| `fork_queue.py` | Ordered queue: starts each recipe run (in tmux `pf-q-<name>`) when a GPU group of 2-9 is free. Queue file `queue/rad-9-24-paper-models.yaml`; state `$RUN/queue-state.json`. See `recipes/recipes.md`. |
| `recipes/` | Recipe scripts, `write_provenance.py` and `recipes.md`. |
| `adapt_rad.py` | Converts a prepared RAD arm to the forks' flat `trainVal_/val_/test_` layout. Writes support files. |
| `make_rs19_split.py` | Builds Paul's 6800/850/850 RailSem19 `custom_split` symlink layout. |
| `score_predictions.py` | Scores a run's dumped label PNGs with the campaign's own metric code. |
| `rs19_split/` | Paul's RS19 split lists (tracked copies). |

Tests: `tests/test_paul_forks.py`. These need no GPU and no nvidia-smi.

## Run labels (use exactly)

| Label | Chain: Map→City → RS19 → RAD (checkpoint owners) |
|---|---|
| `paper-hrnet__rs19-paul` | NVIDIA `nimble-chihuahua` (`nvidia`) → Paul's RS19 `rs19_cityscapes_ep98_miou_0.7385.pth` (`paul`) → RAD (`ours`) |
| `paper-hrnet__rs19-ours` | NVIDIA `nimble-chihuahua` (`nvidia`) → our RS19, trained with Paul's HRNet RS19 recipe (`ours`) → RAD (`ours`) |
| `paper-sfnet__rs19-ours` | public SFNet Map→City `pretrained_cityscapes_mapillary_rs18_miou-0.799.pth` (`public-sfnet-authors`) → our RS19, trained with Paul's SFNet RS19 recipe (`ours`) → RAD (`ours`) |
| `paper-hrnet__mapcity-direct` | NVIDIA `nimble-chihuahua` (`nvidia`) → RAD (`ours`). No RS19 stage, so no `rs19` entry in the chain. |
| `paper-sfnet__mapcity-direct` | public SFNet Map→City (`public-sfnet-authors`) → RAD (`ours`). No RS19 stage. |
| `paper-sfnet__rs19-paul` | Reserved. Used only if Paul sends his SFNet RS19 checkpoint (`public-sfnet-authors` → `paul` → `ours`). |
| `paul-reference__rr22-0.8964` | Paul's finished RAD model. Reference only, and **never scored on our splits**, because it may have trained on our val/test images. `score_predictions.py` refuses it. |

Each RAD-stage label carries its arm: `__arm-paul`, `__arm-fixed-stratified` or
`__arm-fixed-grouped`. For example: `paper-hrnet__rs19-paul__arm-fixed-grouped`. A recipe
other than the default (Paul's shared 2026-09-23 files) appends `__recipe-<variant>`:
`paper-hrnet__rs19-paul__arm-fixed-grouped__recipe-train_2` (variants per chain in
`recipes/recipes.md`; `mapcity-direct` has none). An RS19-stage run (one we train ourselves)
carries the base label without an arm suffix.

Checkpoints that we did not train are pinned by SHA-256 in `score_predictions.py`:

| Checkpoint | SHA-256 |
|---|---|
| NVIDIA `cityscapes_trainval_ocr.HRNet_Mscale_nimble-chihuahua.pth` | `9c3779cd266b0c8474bfa01026e701be623738a304b2d08bfa61df60395a77ae` |
| Paul `rs19_cityscapes_ep98_miou_0.7385.pth` | `873fa92ca7ceb4286a5b80ae24434180e36b0768065c37092be213d4f09ea08f` |
| Paul `rr22_rs19_city_miou_0.8964.pth` (reference only) | `6f518fe54c2b399e18265de9054128cb514cdab5740dce7a670b3b5c5b885f97` |
| SFNet authors `pretrained_cityscapes_mapillary_rs18_miou-0.799.pth` | `133f1b6a1502ef7e685ef4c1a32569c75a03f233f3c6d009a0a0aafc73dd4c0f` |

The HRNet files are in `/data/izadia1/checkpoints/paul-hrnet-ocr-drive-1GtwJjX1/`
(`SHA256SUMS` is in the same directory). They come from Paul's public Drive folder.

## `provenance.json` (required in every run directory)

`score_predictions.py` checks this file and embeds it in `results.json`.

```json
{
  "label": "paper-hrnet__rs19-paul__arm-paul",
  "owner_of_each_checkpoint_in_chain": {"map_city": "nvidia", "rs19": "paul", "rad": "ours"},
  "checkpoints": {
    "map_city": {"path": "...nimble-chihuahua.pth", "sha256": "9c3779cd..."},
    "rs19": {"path": "...rs19_cityscapes_ep98_miou_0.7385.pth", "sha256": "873fa92c..."},
    "rad": {"path": "<run_dir>/ckpt/.../best_mud_epoch_N.pth", "sha256": "..."}
  },
  "fork": {"name": "hrnet", "git_commit": "5e619e6...", "patches": [{"path": "...", "sha256": "..."}]},
  "recipe_args": ["<the train.py argv, verbatim>"],
  "deviations": ["lr 7e-5 -> 1e-4 (train_2)", "..."],
  "gpu_assignment": {"indices": [2, 3, 4, 5], "uuids": ["GPU-931d0911-...", "..."]}
}
```

Owner values are `paul`, `nvidia`, `ours` and `public-sfnet-authors`. The scorer refuses a
file in any of these cases:

- The owners do not equal the label's chain.
- The SHA-256 of a pinned checkpoint differs from the table above.
- A GPU index lies outside 2-9.
- A forbidden UUID appears.
- A required key is missing.

## `fork_gpu_run.py`: the GPU rule

The script uses only the standard library and does not import campaign code.

```
cd $RUN/<run> && PAUL_ADAPTER_ROOT=... PAUL_CENTROID_ROOT=$PWD/centroids \
python3 $RUN/tools/paul_forks/fork_gpu_run.py --gpus 2,3 --run-dir $PWD \
  --python /data/izadia1/envs/paul-segmentation-20260915/bin/python -- \
  /data/izadia1/envs/paul-segmentation-20260915/bin/python -m torch.distributed.run \
  --standalone --nproc_per_node=2 $RUN/src/sfnet/train.py ... --apex ...
```

The script performs these checks and actions, in order:

1. **Allowlist.** It holds a frozen allowlist of indices 2-9, each pinned to its full UUID and PCI bus id. GPUs 0 (`GPU-84f5ca4d-…`, 07:00) and 1 (`GPU-d411d86a-…`, 08:00) are explicitly forbidden. There is no override flag.
2. **Request checks.** It refuses an empty, duplicate or non-allowlisted `--gpus` value.
3. **Inherited environment.** It refuses to run if `CUDA_VISIBLE_DEVICES`, `CUDA_DEVICE_ORDER` or `NVIDIA_VISIBLE_DEVICES` is inherited, even when the value is empty. Launch it from a clean shell, without the `CUDA_VISIBLE_DEVICES=""` used for CPU-only work.
4. **Live inventory.** The live `nvidia-smi` inventory must equal the frozen table, including all 10 GPUs.
5. **Locks.** It takes a non-blocking `flock` per GPU on `/tmp/segmentary-exclusive-gpu-<idx>.lock` (the September launcher's name) and on `/tmp/segmentary-gpu-<uuid>.lock`.
   - `src/segmentary/gpu_policy.py` has no host-level lock. Its campaign locks are `<campaign>/locks/gpu-<idx>.lock`, which this launcher cannot see.
   - **The Segmentary campaign and the fork runs must therefore be planned on disjoint GPU sets.** Plan the catalog with `plan_rtis_campaign.py --gpus` set to its own partition.
   - The idle check and the watchdog are a second line of defence, not a substitute for this.
6. **Idle check.** It makes three passes 1 s apart. Each requested GPU must have no compute app, memory use of at most 100 MiB and 0 % utilisation.
7. **Child environment.** The child gets `CUDA_DEVICE_ORDER=PCI_BUS_ID`, `CUDA_VISIBLE_DEVICES=<UUIDs sorted by index>` and `OMP_NUM_THREADS=2`.
8. **Preflight.** It runs `--python` in exactly that environment. Torch's `device_count()` must equal the number of assigned GPUs, and every device UUID must be one of the assigned UUIDs.
   - This creates a CUDA context on the assigned GPUs, so never run it in a workflow that must not use a GPU.
   - Pass the same interpreter that the command uses.
9. **Launch.** The launcher makes itself the child subreaper (`prctl(PR_SET_CHILD_SUBREAPER)`; Linux only, refused elsewhere), then starts the command with `start_new_session=True`. torchrun starts every worker in its own session, so if the torchrun agent dies its workers are re-parented to the launcher (not to init) and stay watched; they are terminated before the GPU locks are released and listed in `orphans_terminated`. A command that cannot be started exits 2 with status `launch-failed`.
10. **Watchdog.** Every 10 s it reads the process tree from `/proc`: descendants by ppid, plus every process left in the child's session or process group, plus every orphan adopted by the launcher (zombies are reaped and ignored). It compares the tree with `nvidia-smi --query-compute-apps`.
    - If any process of the tree is on an unassigned UUID, the whole tree gets SIGTERM, then SIGKILL after 30 s.
    - The script then writes `gpu-violation.json` and exits with code 3.
    - Three consecutive failed inspections are treated the same way.
11. **Records.** It writes `<run_dir>/gpu-assignment.json` at launch and rewrites it at exit. It appends to `<run_dir>/gpu-telemetry.jsonl` every 30 s, for the assigned UUIDs only.
12. **Signals.** SIGTERM, SIGINT, SIGHUP (closed ssh, killed tmux session) or SIGQUIT sent to the launcher is forwarded to the whole tree (SIGHUP and SIGQUIT as SIGTERM), with SIGKILL after 30 s.
13. **Exit code.** It returns the child's exit code, or 128 + the signal number. A refusal returns exit code 2.

Launch rules that the script does not enforce:

- Always pass `--apex` to HRNet and SFNet, so that DDP calls `set_device(LOCAL_RANK)`.
- FRRN-B (`DataParallel` over every visible device) must get exactly one GPU.

## `adapt_rad.py`

```
CUDA_VISIBLE_DEVICES="" python adapt_rad.py /data/izadia1/datasets/rad_9_24_2026-<arm> $RUN/adapters/<arm>
```

The script reads `splits.json` (`train`, `val`, `test`), `classes.json` and `audit/samples.json`
from an arm written by `scripts/prepare_rad.py`. It writes:

- `{trainVal,val,test}_{images,masks}/<group>__<stem>.png`: absolute symlinks.
- `classes.json` as `{"labels": [{"id","name","color"}]}`, the format both forks' `rtisrail22` loaders read.
- `manifest.json`.
- `validation-support.json` and `test-support.json`, with exact per-class pixel counts.

**Image naming.** Every image link is named `.png`, including the 9 JPEG sources:

- HRNet's `find_images` globs `*.png` only.
- SFNet lists the directory and derives the mask name with `.replace('.jpg','.png')`.
- Both forks decode images with PIL, which detects the format from content, so a JPEG behind a `.png` name loads correctly.
- The real extension is kept in `manifest.json`. September's `adapt.py` handled the JPEGs the same way.

**Checks.** The script fails closed if any of these checks fail:

- 21 classes, with class 13 = mud-pumping and ignore = 255.
- Image and mask SHA-256 match the audit.
- Mask values are within {0..20, 255}.
- Each mask is the same size as its image.
- No key appears in more than one split.
- The arm has 314 images.
- In the grouped arm, no group spans two splits.
- Per-split pixel counts match the audit's `class_pixels`.

**Output location.** The output is built under `<out>.partial` and renamed when complete. The output directory must not already exist.

## `make_rs19_split.py`

```
python make_rs19_split.py --rs19 /data/izadia1/datasets/railsem19 \
  --split-dir $RUN/tools/paul_forks/rs19_split --out /data/izadia1/datasets/railsem19-paul-split
```

The script reads sources from `jpgs/rs19_val/<id>.jpg` and `uint8/rs19_val/<id>.png`.

| Directory | Contents | Read by |
|---|---|---|
| `trainVal_*` | train + val (7650), as Paul did | SFNet `railsem19.py` train |
| `train_*` | train (6800) | HRNet `railsem19.py` train (`train_images`, Paul's `custom_split` name) |
| `val_*` | val (850), also inside `trainVal_` | SFNet val. Selection is in-sample, which is Paul's protocol. |
| `test_*` | test (850) | SFNet `test=True`. HRNet uses it for **both** val and test (`datasets/railsem19.py:57`), so HRNet RS19 selects on test. |
| `rs19-config.json` | symlink to the release's class config | both loaders (after the run workflow's path patch) |

By default every mask is decoded and checked: single-channel uint8, values in {0..18, 255}, and the same size as its image.

**Output location.** The output is built in place, and `manifest.json` is written last. A directory without `manifest.json` is incomplete.

### Paul's split files (`rs19_split/`)

The files were copied verbatim from `pauls3/rail_segmentation@28191e5`
(`scripts/ai_server_splits/`). The three lists are disjoint and contain 8500 ids in total.

| File | Ids | SHA-256 |
|---|---:|---|
| `train_split.txt` | 6800 | `01a51754dfee8b6d46a83ad4a1e05f031974bd8772f1d4b2865b8ba9ebc9f436` |
| `val_split.txt` | 850 | `0cb50dc131e36a1065867af4ecdcebcf988aaff6b9924af686706349035840d4` |
| `test_split.txt` | 850 | `e458ba6cdfd44cce3d30f00b81233b9c4d1a7facfda752619957bdba9f8e09a7` |

## `score_predictions.py`

```
# a snapshot of this branch's metric code, once per commit (no checkout of it exists on HDRFS)
git archive HEAD scripts src | ssh HDRFS "mkdir -p $RUN/tools/segmentary-<commit> && tar -x -C $RUN/tools/segmentary-<commit> && echo <commit> > $RUN/tools/segmentary-<commit>/SNAPSHOT_COMMIT"
D=<run_dir>/dumps/test-single-best_mud_epoch_N
CUDA_VISIBLE_DEVICES="" SEGMENTARY_REPO=$RUN/tools/segmentary-<commit> \
  $CAMPAIGN_ENV/bin/python $RUN/tools/paul_forks/score_predictions.py \
  --pred-dir $D/pred --arm-root /data/izadia1/datasets/rad_9_24_2026-<arm> --split test \
  --provenance $D/dump-provenance.json --out <run_dir>/results-test.json
```

**Metric code location.** The metric code is imported from `$SEGMENTARY_REPO` (default: the
checkout the script sits in). A directory without `src/segmentary/engine/metrics.py`,
`scripts/collect_rtis_statistics.py` and `scripts/publish_rtis_results.py` is refused, so a
staged copy of the scorer never silently picks up the stale `/data/izadia1/projects/segmentary`
checkout that the campaign env (`$CAMPAIGN_ENV`, the Segmentary python env on HDRFS) has installed. `metric_code` in the result records the repo, its git
commit (or `SNAPSHOT_COMMIT`) and the SHA-256 of those three files.

**Inputs.** The script needs one uint8 label PNG per split image, named `<group>__<stem>.png`. The set must be exact: no missing and no extra files.

**Metric code.** It computes metrics with the campaign's own code:

- `segmentary.engine.metrics.ConfusionMatrix` (ignore 255).
- `scripts/collect_rtis_statistics.py` `matrix_metrics` and `mud_counts`.
- `scripts/publish_rtis_results.py` `fixed_miou`.

The mIoU rule is the mean over classes with non-zero union, which is what the campaign reports. Mud-pumping (class 13) IoU, precision and recall come from `mud_counts`. The fixed GT-class mIoU is reported alongside.

**Checks (all fail closed).**

- Label: a RAD-stage label `<base>__arm-<arm>[__recipe-<variant>]` whose arm is the scored arm, whose variant is one the chain has, and whose training run recorded that `recipe_variant`; owners and the exact set of chain stages match the label (`mapcity-direct`: `map_city` and `rad` only); every checkpoint we did not train matches its pin, and a label whose non-ours checkpoint has no pin (`paper-sfnet__rs19-paul`) is refused; the reference label is refused; no dry run, probe or pins override.
- Tie to the run: `--provenance` is the `dump-provenance.json` beside `--pred-dir`, and its command's `--dump_preds` is `--pred-dir`; the dump and the training run both exited 0 (`gpu-assignment.json`); the P4 manifest `<pred-dir>.manifest.json` names the split, the exact image set and the dumped checkpoint's SHA-256 (= `checkpoints.rad`); the dump's `init-coverage.json` loaded that checkpoint with zero skipped tensors; the training `provenance.json` is the one the dump recorded (SHA-256), with the same label, chain and adapter; the dumped checkpoint and the dump are inside that run.
- Inference: whole-image single-scale only; `--allow-multi-scale` scores a `native` dump and labels it as a secondary number.
- Data: the adapter `manifest.json` matches the run's provenance, was built from `rad_9_24_2026-<arm>` (`arm_name`), and the arm's `splits.json`, `classes.json` and `audit/samples.json` are unchanged since; ground-truth masks match the audit's SHA-256; the confusion matrix's ground-truth row sums equal the audit's `class_pixels` and the adapter's `validation-support.json` / `test-support.json` (mandatory).

**Output.** It writes `results.json` with the label, the inference mode, the embedded provenance, the dump/manifest/coverage records and the prediction hashes.

## Deviations from Paul's protocol

These are recorded in the manifests and in each run's `deviations`.

- RAD `trainVal_` holds train only. Paul trained on train + val and selected on val, which was in-sample. Our val is held out, so lower numbers are expected.
- RAD classes: we use 21 classes; the paper uses 19 plus void. Our splits are 314 images (227/37/50 and 217/37/60); the paper's are 152 images (106/30/16).
- RS19 stage: the protocol is Paul's, kept for fidelity. SFNet selects on val, which is inside trainVal. HRNet selects on test.
- We score with Segmentary's metric code on our splits, not with the forks' own numbers.
