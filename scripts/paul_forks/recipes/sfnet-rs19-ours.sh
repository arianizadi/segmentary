#!/usr/bin/env bash
# sfnet-rs19-ours: OUR RailSem19 stage of Paul's SFNet-R18 chain.
#   public SFNet Map->City (resnet18 + map, 79.9) -> RailSem19 (this run, ours)
#
#   sfnet-rs19-ours.sh --gpus 2,3,4,5 --run-dir <dir> [--dry-run]
#
# Recipe: pauls3/SFSegNets-1 @ 25f315e scripts/train_railsem19_sfnet_res18.sh, every flag
# ported verbatim to SFSegNets-2 @ 0bb9e59 (all 27 flags exist in its argparse): lr 0.0025,
# poly 1.0 (repoly 1.5, rescale 1.0), 400 epochs, crop 1080, class-uniform 0.5 tile 1080,
# OHEM, SGD, color_aug 0.25, gblur+bblur, wt_bound 1.0, syncbn, --apex (DDP; FP32, no --fp16).
# Global batch 32 = bs_mult 8 x 4 GPUs (Paul); 2 GPUs x 16 or 8 x 4 keep 32 and are recorded
# as deviations. Trains on trainVal_images (7650 = train+val), selects on val_images (850).
set -euo pipefail
PF_SCRIPT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")
# shellcheck source=_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
pf_usage() { sed -n '2,14p' "$PF_SCRIPT"; }

pf_parse_common "$@"
[[ -z $PF_ARM || $PF_ARM == none ]] || pf_die "the RailSem19 stage takes no --arm"
PF_ARM=""
[[ -z $PF_DUMP ]] || pf_die "--dump is for RAD runs"
pf_check_gpus "$PF_GPUS" 2 4 8
pf_probe_epochs
LABEL=sfnet-rs19-ours
bs_mult=$((32 / PF_NGPU))
epochs=400
[[ -n ${PF_PROBE:-} ]] && epochs=$PF_PROBE

pf_require_file "$PF_SFNET_MAPCITY"
pf_require_file "$PF_SFNET_IMAGENET"
[[ -d $PF_RS19_ROOT/trainVal_images && -f $PF_RS19_ROOT/rs19-config.json && -f $PF_RS19_ROOT/manifest.json ]] \
  || pf_die "RailSem19 split missing or incomplete (no manifest.json) at $PF_RS19_ROOT"
pf_fresh_run_dir
pf_export_paths
export PAUL_RS19_ROOT=$PF_RS19_ROOT

# The public Map->City checkpoint has a 32/64-wide stem; SFSegNets (1 and 2) build a 64/128
# deep stem, so these 22 tensors keep the ImageNet deep-stem weights. Paul's forgiving loader
# skipped the same tensors silently (resnet_d.py is identical at 25f315e and 0bb9e59).
stem_skip='layer0.*,layer1.0.conv1.weight,layer1.0.downsample.*'

pf_torchrun "$PF_NGPU" sfnet
cmd=("${PF_TORCHRUN[@]}"
  --dataset railsem19 --cv 0 --arch network.sfnet_resnet.DeepR18_SF_deeply
  --class_uniform_pct 0.5 --class_uniform_tile 1080 --lr 0.0025 --lr_schedule poly
  --poly_exp 1.0 --repoly 1.5 --rescale 1.0 --syncbn --sgd --ohem --crop_size 1080
  --scale_min 0.5 --scale_max 2.0 --color_aug 0.25 --gblur --bblur --max_epoch "$epochs"
  --wt_bound 1.0 --bs_mult "$bs_mult" --apex --exp "$LABEL"
  --ckpt "$PF_RUN_DIR/ckpt" --tb_path "$PF_RUN_DIR/tb"
  --snapshot "$PF_SFNET_MAPCITY" --allow_skip "$stem_skip")

deviations=(
  "code: SFSegNets-2 @ 0bb9e59 instead of SFSegNets-1 @ 25f315e; AlignedModule calls grid_sample(align_corners=True) in 0bb9e59 vs the torch default (False) in 25f315e; ResNet/loss/optimizer/sampler code identical"
  "Apex DDP/SyncBN replaced by torch DDP/SyncBN (September compat port, patch P0); FP32 as in Paul's script"
  "launched with torch.distributed.run instead of torch.distributed.launch"
  "snapshot loaded by P2 shape-matched loader; the 22 stem tensors that do not fit are allowed explicitly via --allow_skip and keep ImageNet deep-stem init (same outcome as Paul's forgiving loader)"
  "RailSem19 trainVal/val/test rebuilt from pauls3/rail_segmentation scripts/ai_server_splits (6800+850 / 850 / 850)"
)
[[ $PF_NGPU -ne 4 ]] && deviations+=("layout ${PF_NGPU} GPUs x bs_mult ${bs_mult} instead of Paul's 4 x 8 (global batch 32 kept; per-GPU SyncBN batch differs)")
[[ -n ${PF_PROBE:-} ]] && deviations+=("TIMING PROBE: max_epoch=$PF_PROBE (poly LR schedule differs); not a result")

prov=(--chain "map_city|public-sfnet-authors|init|$PF_SFNET_MAPCITY"
      --chain "rs19|ours|this-run|"
      --weights "build-time-imagenet-deep-stem|$PF_SFNET_IMAGENET"
      --data-root "$PF_RS19_ROOT"
      --extra "allow_skip=$stem_skip")
for d in "${PF_P0_DEVIATIONS[@]}" "${deviations[@]}"; do prov+=(--deviation "$d"); done

pf_launch sfnet rs19 "$LABEL" "pauls3/SFSegNets-1 @ 25f315e scripts/train_railsem19_sfnet_res18.sh" \
  "${prov[@]}" -- "${cmd[@]}"
