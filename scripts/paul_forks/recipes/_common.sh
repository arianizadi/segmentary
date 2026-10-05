# shellcheck shell=bash
# shellcheck disable=SC2034  # variables are consumed by the recipes that source this file
# Shared helpers for the Paul-fork recipe scripts. Sourced, never executed.
#
# Every recipe: parses --arm/--gpus/--run-dir (plus its own options), refuses GPUs outside
# 2-9 itself (fork_gpu_run.py is the first line of defence, this is the second), writes
# provenance.json into a fresh run directory BEFORE launching, gives the run its own empty
# centroid cache, and launches through fork_gpu_run.py. --dry-run (or PAUL_FORK_DRY_RUN=1)
# writes provenance.json with "dry_run": true and prints the command instead of running it.
#
# Paths default to the HDRFS layout and can be overridden through the environment:
#   PAUL_FORK_RUN_ROOT   /data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24
#   PAUL_FORK_ENV        /data/izadia1/envs/paul-segmentation-20260915
#   PAUL_FORK_RS19_ROOT  /data/izadia1/datasets/railsem19-paul-split
#   FORK_GPU_RUN         <recipes>/../fork_gpu_run.py
#   PAUL_FORK_PATCHES    <recipes>/../patches

PF_RECIPES_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PF_RUN_ROOT=${PAUL_FORK_RUN_ROOT:-/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24}
PF_ENV=${PAUL_FORK_ENV:-/data/izadia1/envs/paul-segmentation-20260915}
PF_PYTHON=${PAUL_FORK_PYTHON:-$PF_ENV/bin/python}
PF_TOOL_PYTHON=${PAUL_FORK_TOOL_PYTHON:-$PF_PYTHON}
PF_LAUNCHER=${FORK_GPU_RUN:-$PF_RECIPES_DIR/../fork_gpu_run.py}
PF_PATCHES=${PAUL_FORK_PATCHES:-$PF_RECIPES_DIR/../patches}
PF_RS19_ROOT=${PAUL_FORK_RS19_ROOT:-/data/izadia1/datasets/railsem19-paul-split}
PF_CKPT=$PF_RUN_ROOT/checkpoints
PF_ARMS=(paul fixed-stratified fixed-grouped)

# Checkpoints staged under $PF_RUN_ROOT/checkpoints (symlinks + SHA256SUMS).
PF_NVIDIA_MAPCITY=$PF_CKPT/hrnet/cityscapes_trainval_ocr.HRNet_Mscale_nimble-chihuahua.pth
PF_PAUL_HRNET_RS19=$PF_CKPT/hrnet/rs19_cityscapes_ep98_miou_0.7385.pth
PF_HRNET_IMAGENET=$PF_CKPT/hrnet/hrnet_w48_timm_imagenet.pth
PF_SFNET_MAPCITY=$PF_CKPT/sfnet/pretrained_cityscapes_mapillary_rs18_miou-0.799.pth
PF_SFNET_IMAGENET=$PF_CKPT/sfnet/resnet18-deep-inplane128.pth

pf_die() {
  echo "REFUSING: $*" >&2
  exit 2
}

# Second line of defence: only 2-9, no duplicates, and the exact count the recipe needs.
pf_check_gpus() {
  local gpus=$1
  shift
  [[ $gpus =~ ^[2-9](,[2-9])*$ ]] || pf_die "--gpus '$gpus' must list GPUs from 2-9 only (0 and 1 are reserved for other people)"
  local -a list
  IFS=, read -r -a list <<<"$gpus"
  local sorted
  sorted=$(printf '%s\n' "${list[@]}" | sort -u | wc -l | tr -d ' ')
  [[ $sorted -eq ${#list[@]} ]] || pf_die "--gpus '$gpus' has duplicates"
  local n=${#list[@]} ok=0 want
  for want in "$@"; do [[ $n -eq $want ]] && ok=1; done
  [[ $ok -eq 1 ]] || pf_die "--gpus '$gpus' has $n GPUs; this recipe needs one of: $*"
  PF_NGPU=$n
}

pf_parse_common() {
  PF_ARM="" PF_GPUS="" PF_RUN_DIR="" PF_DRY_RUN=${PAUL_FORK_DRY_RUN:-0}
  PF_RS19="" PF_RS19_CKPT="" PF_DUMP="" PF_DUMP_CKPT="" PF_DUMP_SCALES=single
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --arm) PF_ARM=${2:?}; shift 2 ;;
      --gpus) PF_GPUS=${2:?}; shift 2 ;;
      --run-dir) PF_RUN_DIR=${2:?}; shift 2 ;;
      --rs19) PF_RS19=${2:?}; shift 2 ;;
      --rs19-ckpt) PF_RS19_CKPT=${2:?}; shift 2 ;;
      --dump) PF_DUMP=${2:?}; shift 2 ;;
      --checkpoint) PF_DUMP_CKPT=${2:?}; shift 2 ;;
      --scales) PF_DUMP_SCALES=${2:?}; shift 2 ;;
      --dry-run) PF_DRY_RUN=1; shift ;;
      -h|--help) pf_usage; exit 0 ;;
      *) pf_die "unknown argument $1" ;;
    esac
  done
  [[ -n $PF_GPUS ]] || pf_die "--gpus is required"
  [[ -n $PF_RUN_DIR ]] || pf_die "--run-dir is required"
  [[ $PF_RUN_DIR = /* ]] || pf_die "--run-dir must be absolute"
  # A real launch needs a clean shell (fork_gpu_run.py refuses inherited GPU variables too).
  # --dry-run never starts the launcher, so the workflow rule CUDA_VISIBLE_DEVICES="" is fine.
  if [[ -n ${CUDA_VISIBLE_DEVICES+x} ]]; then
    [[ $PF_DRY_RUN == 1 && -z $CUDA_VISIBLE_DEVICES ]] \
      || pf_die "CUDA_VISIBLE_DEVICES is set in this shell; unset it, the launcher assigns GPUs"
  fi
}

# Behaviour changes of the September baseline patch (P0) shared by every recipe.
PF_P0_DEVIATIONS=(
  "P0 seeds random, numpy and torch (CPU and CUDA) with 0 at import in every rank; Paul's code was unseeded. All ranks therefore share the same RNG streams (class-uniform tile lists, augmentation draws and DataLoader worker base seeds are identical across ranks; each rank still reads different images through the DistributedSampler)"
)
# HRNet only (SFNet has no RMI loss).
PF_P0_RMI_DEVIATION="P0 changes 'logits_4D.float()' (a no-op in Paul's code) to 'logits_4D = logits_4D.float()' in loss/rmi.py, so the RMI loss is computed in FP32 rather than in the autocast dtype"

# The adapter must have been built from rad_9_24_2026-<arm>, and that arm must not have been
# re-prepared since (splits, classes and audit sha256 recorded by adapt_rad.py).
pf_check_adapter() {
  local adapter=$1 arm=$2
  "$PF_TOOL_PYTHON" - "$adapter" "$arm" <<'PY' || pf_die "adapter $adapter does not match arm $arm (see above)"
import hashlib, json, sys
from pathlib import Path
adapter, arm = Path(sys.argv[1]), sys.argv[2]
manifest = json.loads((adapter / "manifest.json").read_text())
want = f"rad_9_24_2026-{arm}"
if manifest.get("arm_name") != want:
    sys.exit(f"{adapter}/manifest.json: arm_name {manifest.get('arm_name')!r}, expected {want!r}")
root = Path(manifest["arm_root"])
for name, key in (("splits.json", "splits_sha256"), ("classes.json", "classes_sha256"),
                  ("audit/samples.json", "samples_sha256")):
    digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
    if digest != manifest.get(key):
        sys.exit(f"{root / name} changed since the adapter was built ({key}); rebuild the adapter")
PY
}

pf_check_arm() {
  local a
  for a in "${PF_ARMS[@]}"; do [[ $PF_ARM == "$a" ]] && return 0; done
  pf_die "--arm must be one of: ${PF_ARMS[*]} (got '$PF_ARM')"
}

# Probe runs (PROBE_EPOCHS=1|2) only time the recipe: they must go to a *probe* directory.
pf_probe_epochs() {
  PF_PROBE=${PROBE_EPOCHS:-}
  if [[ -n $PF_PROBE ]]; then
    [[ $PF_PROBE == 1 || $PF_PROBE == 2 ]] || pf_die "PROBE_EPOCHS must be 1 or 2"
    [[ $(basename "$PF_RUN_DIR") == *probe* ]] || pf_die "probe runs need 'probe' in the run directory name"
  fi
}

pf_fresh_run_dir() {
  if [[ -e $PF_RUN_DIR ]] && [[ -n $(ls -A "$PF_RUN_DIR") ]]; then
    pf_die "run directory $PF_RUN_DIR exists and is not empty; every run gets a fresh directory"
  fi
  mkdir -p "$PF_RUN_DIR/centroids"
}

pf_require_file() {
  [[ -f $1 ]] || pf_die "missing file $1"
}

# pf_launch <fork> <stage> <label> <recipe-source> <provenance args...> -- <command...>
pf_launch() {
  local fork=$1 stage=$2 label=$3 source=$4
  shift 4
  local -a prov=()
  while [[ $# -gt 0 && $1 != -- ]]; do prov+=("$1"); shift; done
  [[ ${1:-} == -- ]] || pf_die "internal: pf_launch needs -- before the command"
  shift
  local -a cmd=("$@")
  local -a dry=()
  [[ $PF_DRY_RUN == 1 ]] && dry=(--dry-run)
  "$PF_TOOL_PYTHON" "$PF_RECIPES_DIR/write_provenance.py" \
    --label "$label" --stage "$stage" --fork "$fork" --arm "$PF_ARM" \
    --run-dir "${PF_LAUNCH_DIR:-$PF_RUN_DIR}" --out "${PF_PROV_NAME:-provenance.json}" \
    --src "$PF_RUN_ROOT/src/$fork" --patches-dir "$PF_PATCHES" \
    --gpus "$PF_GPUS" --launcher "$PF_LAUNCHER" \
    --recipe-source "$source" --recipe-script "$PF_SCRIPT" \
    --probe-epochs "${PF_PROBE:-}" ${dry[@]+"${dry[@]}"} ${prov[@]+"${prov[@]}"} -- "${cmd[@]}" \
    || pf_die "provenance could not be written; nothing launched"
  local -a launch=("$PF_TOOL_PYTHON" "$PF_LAUNCHER" --gpus "$PF_GPUS" --run-dir "${PF_LAUNCH_DIR:-$PF_RUN_DIR}"
                   --python "$PF_PYTHON" -- "${cmd[@]}")
  if [[ $PF_DRY_RUN == 1 ]]; then
    printf 'DRY-RUN cwd=%q\n' "${PF_LAUNCH_DIR:-$PF_RUN_DIR}"
    printf 'DRY-RUN env:'
    env | grep '^PAUL_' | sort | sed 's/^/ /' | tr '\n' ' '
    printf '\nDRY-RUN command:'
    printf ' %q' "${launch[@]}"
    printf '\n'
    return 0
  fi
  cd "${PF_LAUNCH_DIR:-$PF_RUN_DIR}" || pf_die "cannot cd to the run directory"
  "${launch[@]}" >>"${PF_LAUNCH_DIR:-$PF_RUN_DIR}/console.log" 2>&1
}

# Data-loader paths for the fork code (patch P1). Exported so the launcher passes them on.
pf_export_paths() {
  export PAUL_CENTROID_ROOT=$PF_RUN_DIR/centroids
  export PAUL_HRNET_IMAGENET_CKPT=$PF_HRNET_IMAGENET
  export PAUL_SFNET_R18_IMAGENET_CKPT=$PF_SFNET_IMAGENET
}

pf_torchrun() {
  PF_TORCHRUN=("$PF_PYTHON" -m torch.distributed.run --standalone "--nproc_per_node=$1"
               "$PF_RUN_ROOT/src/$2/train.py")
}

# Eval-only prediction dump (patch P4) for a finished RAD run: one GPU, fresh dump dir.
# Uses the run's own provenance for the label; writes dumps/<name>/dump-provenance.json.
pf_dump() {
  local fork=$1
  pf_check_gpus "$PF_GPUS" 1
  [[ $PF_DUMP == val || $PF_DUMP == test ]] || pf_die "--dump must be val or test"
  [[ -f $PF_RUN_DIR/provenance.json ]] || pf_die "$PF_RUN_DIR has no provenance.json (not a recipe run)"
  pf_require_file "$PF_DUMP_CKPT"
  local real_ckpt
  real_ckpt=$(cd "$(dirname "$PF_DUMP_CKPT")" && pwd)/$(basename "$PF_DUMP_CKPT")
  [[ $real_ckpt == "$PF_RUN_DIR"/* ]] || pf_die "--checkpoint must be inside --run-dir"
  local label
  label=$("$PF_TOOL_PYTHON" -c '
import json, sys
record = json.load(open(sys.argv[1]))
if record.get("dry_run") or record.get("probe_epochs"):
    sys.exit("training provenance is a dry run or a probe, not a finished run")
print(record["label"])' "$PF_RUN_DIR/provenance.json") || pf_die "$PF_RUN_DIR is not a finished run"
  [[ $label == *__arm-"$PF_ARM" ]] || pf_die "run $label is not arm $PF_ARM"
  local name
  name=$PF_DUMP-$PF_DUMP_SCALES-$(basename "$PF_DUMP_CKPT" .pth)
  local dump_dir=$PF_RUN_DIR/dumps/$name
  [[ ! -e $dump_dir ]] || pf_die "$dump_dir exists"
  mkdir -p "$dump_dir"
  export PAUL_CENTROID_ROOT=$dump_dir/centroids
  mkdir -p "$PAUL_CENTROID_ROOT"
  PF_LAUNCH_DIR=$dump_dir
  PF_PROV_NAME=dump-provenance.json
  PF_DUMP_DIR=$dump_dir
  PF_DUMP_LABEL=$label
}

# An "ours" RS19 checkpoint must come from a finished, non-probe, non-dry-run recipe run of
# the expected label whose launcher record says it exited 0 (gpu-assignment.json written by
# fork_gpu_run.py). Prints that run's provenance.json path.
pf_check_rs19_ours() {
  local ckpt=$1 want=$2
  pf_require_file "$ckpt"
  "$PF_TOOL_PYTHON" - "$ckpt" "$want" <<'PY' || pf_die "RS19 checkpoint $ckpt is not from a finished $want recipe run"
import json, sys
from pathlib import Path
ckpt, want = Path(sys.argv[1]).resolve(), sys.argv[2]
for parent in ckpt.parents:
    prov = parent / "provenance.json"
    if prov.is_file():
        record = json.loads(prov.read_text())
        ok = (record.get("label") == want and not record.get("dry_run")
              and record.get("probe_epochs") is None)
        if not ok:
            sys.exit(f"{prov}: label={record.get('label')} dry_run={record.get('dry_run')} "
                     f"probe_epochs={record.get('probe_epochs')}")
        launch = parent / "gpu-assignment.json"
        done = json.loads(launch.read_text()) if launch.is_file() else {}
        if done.get("status") != "exited" or done.get("exit_code") != 0:
            sys.exit(f"{launch}: run not finished (status={done.get('status')} "
                     f"exit_code={done.get('exit_code')})")
        print(prov)
        sys.exit(0)
sys.exit("no provenance.json above the checkpoint")
PY
}
