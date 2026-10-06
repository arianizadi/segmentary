#!/usr/bin/env bash
# hrnet-rs19-ours: OUR RailSem19 stage of Paul's HRNet-OCR-Mscale chain.
#   NVIDIA Map->City (nimble-chihuahua) -> RailSem19 (this run, ours)
#
#   hrnet-rs19-ours.sh --gpus 2,3,4,5 --run-dir <dir> [--dry-run]
#
# Recipe (HRNET_RS19_RECIPE):
#   paul-shared-20260923 (default)  hrnet/train_rs19.yml from the hyperparameters Paul shared
#                          for this work: lr 1e-4, 150 epochs, supervised mscale weight 0.1.
#   ckpt-0.7385            the command embedded in Paul's rs19_cityscapes_ep98_miou_0.7385.pth,
#                          identical to scripts/train_rs19.yml @ 8c2a170 (2022-02-08):
#                          lr 5e-4, 300 epochs, supervised mscale weight 0.05.
#   git-head-9fbd50f       the later git HEAD yml (2022-02-17): lr 1e-4, 150 epochs, weight 0.1.
#                          It is NOT the recipe that produced 0.7385 (see recipes.md).
# Shared: 4 GPUs x bs_trn 1, crop 1080x1920, poly 2, RMI, n_scales 0.5,1.0,2.0, fp16 (native
# AMP), syncbn, gblur, brt_aug, class-uniform tile 1024. Paul's loader trains on train_images
# (6800) and validates on test_images (850): checkpoint selection on test, as Paul did.
set -euo pipefail
PF_SCRIPT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")
# shellcheck source=_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
pf_usage() { sed -n '2,17p' "$PF_SCRIPT"; }

pf_parse_common "$@"
[[ -z $PF_ARM || $PF_ARM == none ]] || pf_die "the RailSem19 stage takes no --arm"
PF_ARM=""
[[ -z $PF_DUMP ]] || pf_die "--dump is for RAD runs"
pf_check_gpus "$PF_GPUS" 4
pf_probe_epochs
LABEL=hrnet-rs19-ours

variant=${HRNET_RS19_RECIPE:-paul-shared-20260923}
case "$variant" in
  paul-shared-20260923)
    lr=1e-4 epochs=150 mscale_wt=0.1
    source_note="hrnet/train_rs19.yml in the hyperparameter files Paul shared on 2026-09-23 (Drive folder 'hyperparameters', copy at /data/izadia1/checkpoints/paul-hyperparameters-drive with SHA256SUMS)"
    ;;
  ckpt-0.7385)
    lr=5e-4 epochs=300 mscale_wt=0.05
    source_note="pauls3/semantic-segmentation scripts/train_rs19.yml @ 8c2a170 (= 'command' stored in rs19_cityscapes_ep98_miou_0.7385.pth)"
    ;;
  git-head-9fbd50f)
    lr=1e-4 epochs=150 mscale_wt=0.1
    source_note="pauls3/semantic-segmentation scripts/train_rs19.yml @ 9fbd50f (git HEAD; not the 0.7385 recipe)"
    ;;
  *) pf_die "HRNET_RS19_RECIPE must be paul-shared-20260923, ckpt-0.7385 or git-head-9fbd50f" ;;
esac
[[ -n ${PF_PROBE:-} ]] && epochs=$PF_PROBE

pf_require_file "$PF_NVIDIA_MAPCITY"
pf_require_file "$PF_HRNET_IMAGENET"
[[ -d $PF_RS19_ROOT/train_images && -f $PF_RS19_ROOT/rs19-config.json && -f $PF_RS19_ROOT/manifest.json ]] \
  || pf_die "RailSem19 split missing or incomplete (no manifest.json) at $PF_RS19_ROOT"
pf_fresh_run_dir
pf_export_paths
export PAUL_RS19_ROOT=$PF_RS19_ROOT

# Validation on the 850 RailSem19 test images at 3 scales costs ~10-15 min per epoch. Training
# is unchanged by val_freq; only how often the best checkpoint is evaluated (epochs 0, 5, ...).
val_freq=${HRNET_RS19_VAL_FREQ:-5}
[[ $val_freq =~ ^[1-9][0-9]*$ ]] || pf_die "HRNET_RS19_VAL_FREQ must be a positive integer"
pf_torchrun 4 hrnet
cmd=("${PF_TORCHRUN[@]}"
  --dataset railsem19 --cv 0 --syncbn --apex --fp16 --gblur --brt_aug
  --crop_size "1080,1920" --bs_trn 1 --poly_exp 2 --lr "$lr" --rmi_loss
  --max_epoch "$epochs" --n_scales "0.5,1.0,2.0" --supervised_mscale_loss_wt "$mscale_wt"
  --snapshot "$PF_NVIDIA_MAPCITY" --arch ocrnet.HRNet_Mscale
  --val_freq "$val_freq" --result_dir "$PF_RUN_DIR/train")

deviations=(
  "Apex replaced by native AMP (fp16 autocast + GradScaler) and torch DDP/SyncBN (September compat port, patch P0)"
  "launched with torch.distributed.run (one process per GPU) instead of torch.distributed.launch via runx"
  "pretrained ImageNet backbone loaded at model build is the timm hrnet_w48 conversion; every backbone tensor is then overwritten by the snapshot (see train/init-coverage.json)"
  "snapshot loaded by P2 shape-matched loader (fails on any unexpected skip) instead of forgiving_state_restore"
  "RailSem19 6800/850/850 split rebuilt from pauls3/rail_segmentation scripts/ai_server_splits; Paul's 2022 split files are assumed to be those lists"
  "ours: P3 best-mud not applicable (no mud class in RailSem19); P4/P5/P6 do not change the training math"
)
[[ $variant == paul-shared-20260923 ]] && deviations+=("recipe paul-shared-20260923 (lr 1e-4, 150 epochs, weight 0.1) is what Paul shared for this work, not the recipe stored in his 0.7385 checkpoint (lr 5e-4, 300 epochs, weight 0.05)")
[[ $variant == git-head-9fbd50f ]] && deviations+=("recipe variant git-head-9fbd50f is not the one that produced Paul's 0.7385 checkpoint")
[[ $val_freq != 1 ]] && deviations+=("validation every $val_freq epochs instead of every epoch (Paul's val_freq 1): training is identical; the RS19 checkpoint handed to the RAD stage is the best of epochs 0, $val_freq, ... (decision 2026-10-05, saves ~1 day)")
[[ -n ${PF_PROBE:-} ]] && deviations+=("TIMING PROBE: max_epoch=$PF_PROBE (poly LR schedule differs); not a result")

prov=(--chain "map_city|nvidia|init|$PF_NVIDIA_MAPCITY"
      --chain "rs19|ours|this-run|"
      --weights "build-time-imagenet|$PF_HRNET_IMAGENET"
      --data-root "$PF_RS19_ROOT"
      --extra "recipe_variant=$variant")
for d in "${PF_P0_DEVIATIONS[@]}" "$PF_P0_RMI_DEVIATION" "${deviations[@]}"; do prov+=(--deviation "$d"); done

pf_launch hrnet rs19 "$LABEL" "$source_note" "${prov[@]}" -- "${cmd[@]}"
