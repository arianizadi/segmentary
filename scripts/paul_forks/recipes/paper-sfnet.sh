#!/usr/bin/env bash
# paper-sfnet: RAD stage of Paul's SFNet-R18 (paper: Map->City->RS19, 61.0 test mIoU).
#
#   paper-sfnet.sh --rs19 ours --rs19-ckpt <ckpt from a sfnet-rs19-ours run> --arm <arm> \
#       --gpus 2,3,4,5 --run-dir <dir> [--dry-run]
#       label paper-sfnet__rs19-ours__arm-<arm>: public Map->City -> our RS19 -> RAD
#   paper-sfnet.sh --rs19 paul --rs19-ckpt <Paul's railsem19_sfnet_resnet18_mean-iu_0.75268.pth> ...
#       label paper-sfnet__rs19-paul__arm-<arm> (RESERVED: refused by write_provenance.py until
#       Paul sends that checkpoint and its sha256 is pinned as ("paul", "rs19", "sfnet") in
#       write_provenance.PINS and as ("paper-sfnet", "rs19-paul") in score_predictions.PINNED)
#   paper-sfnet.sh --rs19 none --arm <arm> --gpus 2,3 --run-dir <dir>
#       label paper-sfnet__mapcity-direct__arm-<arm>: public Map->City -> RAD (no RS19 stage),
#       Paul's shared sfnet/train_rs19_rtisrail22_sfnet_res18.sh (lr 0.0025, 700 epochs)
#   paper-sfnet.sh --dump val|test --checkpoint <run>/ckpt/.../<ckpt>.pth --arm <arm> \
#       --gpus <one GPU> --run-dir <finished RAD run>
#       P4 prediction dump: whole image, single scale (SFNet's own test setting)
#
# Recipe (SFNET_RAD_RECIPE): paul-shared-20260923 (default) = sfnet/train_rtisrail22_sfnet_res18.sh
# from the hyperparameters Paul shared, lr 0.002; train_2 = SFSegNets-2 @ fcc42b6, lr 0.001
# (label gets __recipe-train_2). --rs19 none takes the default only.
# Shared: poly 1.0, repoly 1.5, rescale 1.0, 1000 epochs, crop 1080,
# class-uniform 0.5 tile 1080 (max_cu_epoch default 100000), OHEM, SGD, color_aug 0.25,
# gblur+bblur, wt_bound 1.0, syncbn, --apex (DDP, FP32). Paul: 4 GPUs x bs_mult 8 (global 32);
# --gpus with 2 GPUs runs 2 x 16 (global 32, plan 2B) and is recorded as a deviation.
set -euo pipefail
PF_SCRIPT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")
# shellcheck source=_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
pf_usage() { sed -n '2,24p' "$PF_SCRIPT"; }

pf_parse_common "$@"
pf_check_arm
export PAUL_ADAPTER_ROOT=${PAUL_FORK_ADAPTERS:-$PF_RUN_ROOT/adapters}/$PF_ARM
[[ -f $PAUL_ADAPTER_ROOT/classes.json && -d $PAUL_ADAPTER_ROOT/trainVal_images ]] \
  || pf_die "adapter for arm $PF_ARM missing at $PAUL_ADAPTER_ROOT"
pf_check_adapter "$PAUL_ADAPTER_ROOT" "$PF_ARM"
pf_require_file "$PF_SFNET_IMAGENET"

if [[ -n $PF_DUMP ]]; then
  pf_dump sfnet
  [[ $PF_DUMP_SCALES == single ]] || pf_die "SFNet dumps are single-scale only"
  export PAUL_SFNET_R18_IMAGENET_CKPT=$PF_SFNET_IMAGENET
  pf_torchrun 1 sfnet
  cmd=("${PF_TORCHRUN[@]}" --dataset rtisrail22 --cv 0 --arch network.sfnet_resnet.DeepR18_SF_deeply
       --class_uniform_pct 0 --bs_mult_val 1 --snapshot "$PF_DUMP_CKPT"
       --dump_preds "$PF_DUMP_DIR/pred" --dump_split "$PF_DUMP"
       --exp dump --ckpt "$PF_DUMP_DIR/log" --tb_path "$PF_DUMP_DIR/log")
  pf_launch sfnet dump "$PF_DUMP_LABEL" "eval-only P4 dump (whole image, single scale)" \
    --chain "rad|ours|dumped|$PF_DUMP_CKPT" --base-provenance "$PF_RUN_DIR/provenance.json" --data-root "$PAUL_ADAPTER_ROOT" \
    --extra "split=$PF_DUMP" --extra "scales=1.0" -- "${cmd[@]}"
  exit 0
fi

pf_check_gpus "$PF_GPUS" 2 4
pf_probe_epochs
case "$PF_RS19" in
  ours)
    [[ -n $PF_RS19_CKPT ]] || pf_die "--rs19-ckpt is required"
    rs19_prov=$(pf_check_rs19_ours "$PF_RS19_CKPT" sfnet-rs19-ours)
    rs19_owner=ours
    ;;
  paul)
    [[ -n $PF_RS19_CKPT ]] || pf_die "--rs19-ckpt is required"
    rs19_prov=""
    rs19_owner=paul
    ;;
  none)
    [[ -z $PF_RS19_CKPT ]] || pf_die "--rs19 none starts from the public Map->City checkpoint; drop --rs19-ckpt"
    rs19_prov=""
    ;;
  *) pf_die "--rs19 must be ours, paul or none" ;;
esac
pf_require_file "$PF_SFNET_MAPCITY"
bs_mult=$((32 / PF_NGPU))
variant=${SFNET_RAD_RECIPE:-$PF_DEFAULT_RECIPE}
shared_dir="in the hyperparameter files Paul shared on 2026-09-23 (Drive folder 'hyperparameters', copy at /data/izadia1/checkpoints/paul-hyperparameters-drive with SHA256SUMS)"
# The public Map->City checkpoint has a 32/64-wide stem; SFSegNets builds a 64/128 deep stem,
# so these 22 tensors keep the ImageNet deep-stem init (as in sfnet-rs19-ours.sh).
stem_skip='layer0.*,layer1.0.conv1.weight,layer1.0.downsample.*'
skip_args=()
if [[ $PF_RS19 == none ]]; then
  chain=mapcity-direct head_from=Cityscapes
  [[ $variant == "$PF_DEFAULT_RECIPE" ]] \
    || pf_die "--rs19 none (mapcity-direct) runs Paul's shared settings only; unset SFNET_RAD_RECIPE"
  snapshot=$PF_SFNET_MAPCITY
  skip_args=(--allow_skip "$stem_skip")
  lr=0.0025 epochs=700
  source_note="sfnet/train_rs19_rtisrail22_sfnet_res18.sh $shared_dir"
else
  chain=rs19-$PF_RS19 head_from=RS19
  pf_require_file "$PF_RS19_CKPT"
  snapshot=$PF_RS19_CKPT
  epochs=1000
  case "$variant" in
    paul-shared-20260923) lr=0.002
      source_note="sfnet/train_rtisrail22_sfnet_res18.sh $shared_dir" ;;
    train_2) lr=0.001
      source_note="pauls3/SFSegNets-2 scripts/rtisrail/train_rtisrail22_sfnet_res18.sh @ fcc42b6 (train_2)" ;;
    *) pf_die "SFNET_RAD_RECIPE must be paul-shared-20260923 or train_2" ;;
  esac
fi
pf_rad_label "paper-sfnet__$chain" "$variant"
[[ -n ${PF_PROBE:-} ]] && epochs=$PF_PROBE

pf_fresh_run_dir
pf_export_paths
pf_torchrun "$PF_NGPU" sfnet
cmd=("${PF_TORCHRUN[@]}"
  --dataset rtisrail22 --cv 0 --arch network.sfnet_resnet.DeepR18_SF_deeply
  --class_uniform_pct 0.5 --class_uniform_tile 1080 --lr "$lr" --lr_schedule poly
  --poly_exp 1.0 --repoly 1.5 --rescale 1.0 --syncbn --sgd --ohem --crop_size 1080
  --scale_min 0.5 --scale_max 2.0 --color_aug 0.25 --gblur --bblur --max_epoch "$epochs"
  --wt_bound 1.0 --bs_mult "$bs_mult" --apex --exp "$LABEL"
  --ckpt "$PF_RUN_DIR/ckpt" --tb_path "$PF_RUN_DIR/tb"
  --snapshot "$snapshot" ${skip_args[@]+"${skip_args[@]}"})

deviations=(
  "data: RAD 9/24 arm '$PF_ARM' (21 classes incl. mud-pumping=13 and standing-water=20) instead of Paul's 2022 RAD v6/v7 (19 classes); trainVal_ holds TRAIN ONLY (Paul's trainVal also contained val), val_ is our held-out val"
  "19-class $head_from head re-initialised for 21 classes (P2: head.conv_last.1 skipped; see ckpt/.../init-coverage.json)"
  "Apex DDP/SyncBN replaced by torch DDP/SyncBN (September compat port, patch P0); FP32 as in Paul's script; torch.distributed.run instead of torch.distributed.launch"
  "September sampler fix kept: validation covers every val image exactly once; confusion matrices all-reduced as int64"
  "extra checkpoint best_mud_epoch_N.pth selected on val IoU of class 13 (P3); Paul's best-by-mIoU checkpoint is still written"
  "recipe $variant: $source_note; provenance of Paul's paper SFNet number (0.88745) among train_0/1/2 is not established"
)
[[ $chain == mapcity-direct ]] && deviations+=(
  "chain mapcity-direct: public Map->City snapshot fine-tuned on RAD directly, skipping RailSem19, with Paul's shared sfnet/train_rs19_rtisrail22_sfnet_res18.sh (its file name, --exp and EXP_DIR mention rs19, but its --snapshot is pretrained_cityscapes_mapillary_rs18_miou-0.799.pth; we follow --snapshot)"
  "snapshot loaded by P2 shape-matched loader; the 22 stem tensors that do not fit are allowed explicitly via --allow_skip and keep ImageNet deep-stem init (same outcome as Paul's forgiving loader)"
)
[[ $PF_NGPU -ne 4 ]] && deviations+=("layout ${PF_NGPU} GPUs x bs_mult ${bs_mult} instead of Paul's 4 x 8 (global batch 32 kept; per-GPU SyncBN batch differs)")
[[ -n ${PF_PROBE:-} ]] && deviations+=("TIMING PROBE: max_epoch=$PF_PROBE (poly LR schedule differs); not a result")

if [[ $chain == mapcity-direct ]]; then
  prov=(--chain "map_city|public-sfnet-authors|init|$PF_SFNET_MAPCITY" --extra "allow_skip=$stem_skip")
else
  prov=(--chain "map_city|public-sfnet-authors|ancestor|$PF_SFNET_MAPCITY"
        --chain "rs19|$rs19_owner|init|$PF_RS19_CKPT")
fi
prov+=(--chain "rad|ours|this-run|"
      --weights "build-time-imagenet-deep-stem|$PF_SFNET_IMAGENET"
      --data-root "$PAUL_ADAPTER_ROOT")
prov+=(--extra "recipe_variant=$variant")
[[ -n $rs19_prov ]] && prov+=(--extra "rs19_run_provenance=$rs19_prov")
for d in "${PF_P0_DEVIATIONS[@]}" "${deviations[@]}"; do prov+=(--deviation "$d"); done

pf_launch sfnet rad "$LABEL" "$source_note" "${prov[@]}" -- "${cmd[@]}"
