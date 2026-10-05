# Paul-fork patch series (RAD 9/24 runs)

Two forks, each patched by an ordered series. Apply with `apply_patches.sh` to a pristine
clone of the exact commit; it dry-runs the whole series (`git apply --check`, patch by
patch) in a scratch export before touching the clone, then writes
`<clone>/PAUL_PATCHES_APPLIED` (sha256 + name per patch). The recipes copy that file into
every `provenance.json` and refuse to launch if it no longer matches these patch files.
It also writes `<clone>/PAUL_PATCHES_TREE`, the content digest of the patched working tree
(`tree_digest.py`: path, executable bit and sha256 of every tracked or untracked,
non-ignored file, excluding `.git`, `__pycache__` and the two `PAUL_PATCHES_*` files).
`write_provenance.py` recomputes it before every launch and refuses on any difference, so a
hand edit to the clone after patching cannot run silently.

| Fork | Upstream | Commit |
|---|---|---|
| hrnet | https://github.com/pauls3/semantic-segmentation.git | `5e619e64803188302c54f4d3d6bcef57de2e57e2` |
| sfnet | https://github.com/pauls3/SFSegNets-2.git | `0bb9e59222bcf996ff8b2510a3318538706a7222` |

```
git clone --no-hardlinks /data/izadia1/projects/paul-semantic-segmentation-5e619e6 src/hrnet
git -C src/hrnet checkout 5e619e64803188302c54f4d3d6bcef57de2e57e2
scripts/paul_forks/patches/apply_patches.sh hrnet src/hrnet
```

## P0: the September 2026 source, unchanged

`P0-september-baseline.patch` is `git diff --binary` from the upstream commit to the exact
source the September runs used (`paul-fork-validation-20260915`):

- hrnet: `hrnet-resume-20260916.patch` (= the live September tree, including the sampler
  `self.pad` fix and the NumPy safe-globals fix) plus `compat_native_amp.py`.
- sfnet: `paul-sfsegnets-0bb9e59.patch` (= the live September tree, including
  `sf_load_fix.py`'s restricted loader) plus `compat_native_amp.py`.

The other untracked files in the September trees (`adapt*.py`, `fix_*.py`,
`native_amp_port.py`, `compatibility*.py`, `prepare_resume.py`, `check_*.py`) are the
scripts that produced those edits; they are not imported at run time. Verified on HDRFS:
a fresh clone with only P0 applied is byte-identical to the September working tree in
every tracked file and in `compat_native_amp.py` (73 hrnet files, 132 sfnet files).

## Our patches (one concern each)

| Patch | Concern | Files |
|---|---|---|
| P1 env-paths | Fail-closed environment paths replace every hardcoded data path: `PAUL_ADAPTER_ROOT` (RAD adapter + its `classes.json`), `PAUL_RS19_ROOT` (RailSem19 split + `rs19-config.json`), `PAUL_CENTROID_ROOT` (per-run class-uniform cache; HRNet `uniform.py`, SFNet's CWD-relative `rtisrail22{tile}.json` / `railsem19{tile}.json`), and the build-time ImageNet weights (`PAUL_HRNET_IMAGENET_CKPT`, `PAUL_SFNET_R18_IMAGENET_CKPT`, the latter was `./pretrained_models/...` relative to CWD). Unset, relative or missing → `RuntimeError`. SFNet's centroid cache is written atomically (every rank builds and writes it). | `paul_env.py`, `config.py`, `datasets/{rtisrail22,railsem19}.py`, hrnet `datasets/uniform.py` + `network/hrnetv2.py`, sfnet `network/resnet_d.py` |
| P1b rs19-loader-wiring (sfnet) | 0bb9e59 imports `RailSem19` as a class and the September port commented it out, so `--dataset railsem19` could not run. Re-wire the module as SFSegNets-1 @ 25f315e did. | `datasets/__init__.py` |
| P2 shape-matched-init | `--snapshot` loads by name + shape (DDP `module.` prefix ignored) and writes `init-coverage.json` (loaded/skipped tensors with shapes, unused checkpoint tensors, source sha256). Fails unless every skipped tensor is a final classifier tensor of the arch (`HEAD_TENSORS`) whose shape differs (a head tensor missing from the checkpoint fails) or matches an explicit `--allow_skip` pattern; a pattern that matches nothing also fails; an unknown arch fails. hrnet: legacy checkpoints need `torch.load(weights_only=False)` (they pickle argparse/NumPy objects; the user trusts them). | `paul_init.py`, `train.py` |
| P3 best-mud-checkpoint | Extra `best_mud_epoch_<N>.pth` whenever val IoU of class 13 improves (ties: higher mIoU; NaN never improves); state in `best_mud.json`; class 13 must be `mud-pumping` in the adapter's `classes.json`. RAD (`rtisrail22`) training runs only. Paul's best-by-mIoU checkpoint is unchanged. | `paul_best_mud.py`, `utils/misc.py` |
| P4 dump-preds | Eval-only `--dump_preds <dir>` writes one uint8 label PNG per image, named `<group>__<stem>.png` like the adapter's files, refuses an existing dir or duplicates, and writes `<dir>.manifest.json` beside the directory (so it holds only PNGs, as `score_predictions.py` requires) only after checking that exactly the split's images were dumped. hrnet: with `--eval val|test` (single scale = `--n_scales 1.0`; whole image). sfnet: `--dump_split val|test` (adds the missing test mode to the loader; whole image, single scale) and returns before training. | `paul_dump.py`, `train.py`, sfnet `datasets/__init__.py` |
| P5 throughput | Restore Paul's data-loading parallelism: sfnet `num_workers = 4 * ngpu` (September: 2) and centroid `Pool(32)` (September: 4); hrnet centroid `Pool(80)` (September: 4). hrnet `num_workers` is a CLI default (4); the recipes no longer pass `--num_workers 2`. No effect on the training math. | `datasets/uniform.py`, sfnet `datasets/__init__.py` |
| P6 resume-rng-scaler (hrnet) | Checkpoints also store per-rank RNG states (Python, NumPy, torch CPU, CUDA; gathered with `all_gather_object`) and the GradScaler state, in `weights_only`-safe types so runx's reload still works; `--resume` restores them (rank count must match). cuDNN stays non-deterministic. sfnet has no resume path (`--start_epoch` restores neither optimizer nor schedule), so P6 is hrnet only. | `paul_resume_state.py`, `train.py`, `utils/misc.py` |

## Series and sha256

| Patch | sha256 |
|---|---|
| hrnet/P0-september-baseline.patch | `8d4e7755a97ef880b8cda63ae0023871cea0ac10e91d32c44695da001fb4c6b7` |
| hrnet/P1-env-paths.patch | `3666914d8ae46ffcc5aea652b7735684c7f6aa6a7acb10ce20d960b708baa6b1` |
| hrnet/P2-shape-matched-init.patch | `de8bd3e2da7a9e11381424d061700af3b045e47fb507d766da0e14391c36e969` |
| hrnet/P3-best-mud-checkpoint.patch | `e47b47ab94e809570037407f317f091c15a200c4d292cdcf7f4f56c61c4db7b9` |
| hrnet/P4-dump-preds.patch | `e5bdd55bfce1f678e7f9c9b4cd086fa09ff316430298ec7f31aadfaeb7c38275` |
| hrnet/P5-throughput.patch | `57c6e703404915b7124af6f41fdb296ea972e86850342edd7a3b1b9a80d6816a` |
| hrnet/P6-resume-rng-scaler.patch | `63ac7da9f48fdc2da21391ab689478d274afbbccece297d0bc139acbdbd6f915` |
| sfnet/P0-september-baseline.patch | `6ac91d2ee39aeb7fea879cc03b51905e9db9271776871c0cfa543c71947d970a` |
| sfnet/P1-env-paths.patch | `80d6ed8060aad20fa623e4dc85fa9128559992688dbd9b212857000594065a29` |
| sfnet/P1b-rs19-loader-wiring.patch | `4ee2851f3e4fae8e7bb0e4d398552b6817ff6f8ea4739352c81ae1068e45413e` |
| sfnet/P2-shape-matched-init.patch | `9527bfa65b22109c8d77395cec94fae30de53f20b256b198135190c512762e26` |
| sfnet/P3-best-mud-checkpoint.patch | `f8654bc44c4c719dbe75542fa6544ea4f3c002579b9a57193ba51ea48ed53a94` |
| sfnet/P4-dump-preds.patch | `fa7363799a67c60c1a93eb2ec69d30356d42de0d10a7ddb31d841c6c66a3bd34` |
| sfnet/P5-throughput.patch | `03c9bc41bbf3f41e03d5066f2a4abd774496aa3aa9e7218d32973461a1bee938` |

`tests/test_paul_fork_recipes.py` checks that this table matches the files, that the
series in `apply_patches.sh` matches the files on disk, and unit-tests the helper modules
(`paul_env`, `paul_init`, `paul_best_mud`, `paul_dump`, `paul_resume_state`) extracted
from the patches. The hrnet and sfnet copies of the shared helpers must be identical.

## P2 coverage, checked on HDRFS (CPU only, `CUDA_VISIBLE_DEVICES=""`, no CUDA context)

Script and JSON reports: `$RUN/checks/p2_cpu_check.py`, `$RUN/checks/p2-coverage/*.json`
(`$RUN=/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24`).

| Checkpoint → model | Loaded / total tensors | Skipped |
|---|---|---|
| hrnet `nimble-chihuahua` (NVIDIA, arch `ocrnet_sup.HRNet_Mscale`, ep 174) → 19-class RS19 `ocrnet.HRNet_Mscale` | 1903 / 1903 | none |
| hrnet `nimble-chihuahua` → 21-class | 1899 / 1903 | `ocr.cls_head.{weight,bias}`, `ocr.aux_head.2.{weight,bias}` (heads only) |
| hrnet `rs19_cityscapes_ep98_miou_0.7385` (Paul, ep 98) → 21-class RAD | 1899 / 1903 (72,212,492 / 72,238,406 elements) | the same 4 head tensors only |
| sfnet public Map→City → 19-class RS19, no `--allow_skip` | 202 / 224 | **FAILED** (22 stem tensors, as designed) |
| sfnet public Map→City → 19-class RS19, stem `--allow_skip` | 202 / 224 | 22 stem tensors (`layer0.*`, `layer1.0.conv1.weight`, `layer1.0.downsample.*`; the checkpoint's stem is 32/64 wide, SFSegNets builds 64/128); they keep the ImageNet deep-stem init, as Paul's forgiving loader did |
| sfnet public Map→City → 21-class RAD, stem `--allow_skip` | 200 / 224 (12,684,962 elements, identical to September's `sfnet-init-coverage.json`) | the same 22 + `head.conv_last.1.{weight,bias}` |

In a real run `MscaleOCR` takes its class count from `cfg.DATASET.NUM_CLASSES`, which
`setup_loaders` sets from the dataset (19 `railsem19`, 21 `rtisrail22`).
