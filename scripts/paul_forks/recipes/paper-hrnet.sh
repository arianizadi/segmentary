#!/usr/bin/env bash
# paper-hrnet: RAD stage of Paul's HRNet-OCR-Mscale (paper: Map->City->RS19, 67.1 test mIoU).
#
#   paper-hrnet.sh --rs19 paul --arm <arm> --gpus 2,3,4,5 --run-dir <dir> [--dry-run]
#       label paper-hrnet__rs19-paul__arm-<arm>: NVIDIA Map->City -> Paul RS19 0.7385 -> RAD
#   paper-hrnet.sh --rs19 ours --rs19-ckpt <ckpt from an hrnet-rs19-ours run> --arm <arm> ...
#       label paper-hrnet__rs19-ours__arm-<arm>: NVIDIA Map->City -> our RS19 -> RAD
#   paper-hrnet.sh --rs19 none --arm <arm> ...
#       label paper-hrnet__mapcity-direct__arm-<arm>: NVIDIA Map->City -> RAD (no RS19 stage;
#       Paul shared no script for this chain, so his shared RAD settings are used)
#   paper-hrnet.sh --dump val|test --checkpoint <run>/train/<ckpt>.pth --arm <arm> \
#       --gpus <one GPU> --run-dir <finished RAD run> [--scales single|native]
#       P4 prediction dump (single = n_scales 1.0, primary; native = 0.5,1.0,2.0 as eval_rr22.yml)
#
# <arm> is paul, fixed-stratified or fixed-grouped (adapter $PAUL_FORK_RUN_ROOT/adapters/<arm>).
# Recipe (HRNET_RAD_RECIPE): paul-shared-20260923 (default) = hrnet/train_rtisrail22.yml Paul
# shared: lr 7e-5, 1000 epochs, n_scales 0.5,1.0,1.5, mscale weight 0.05. train_2 = the
# 'command' stored in rr22_rs19_city_miou_0.8964.pth (lr 1e-4, 500 epochs); train_1 = lr 1e-4,
# 500 epochs, weight 0.1, n_scales 0.5,1.0,2.0. A non-default recipe appends
# __recipe-<variant> to the label (--rs19 paul|ours only). Shared: poly 2, crop 1080x1920,
# bs_trn 1 x 4 GPUs, RMI, fp16, syncbn, gblur, brt_aug. See recipes.md.
set -euo pipefail
PF_SCRIPT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")
# shellcheck source=_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
pf_usage() { sed -n '2,21p' "$PF_SCRIPT"; }

pf_parse_common "$@"
pf_check_arm
export PAUL_ADAPTER_ROOT=${PAUL_FORK_ADAPTERS:-$PF_RUN_ROOT/adapters}/$PF_ARM
[[ -f $PAUL_ADAPTER_ROOT/classes.json && -d $PAUL_ADAPTER_ROOT/trainVal_images ]] \
  || pf_die "adapter for arm $PF_ARM missing at $PAUL_ADAPTER_ROOT"
pf_check_adapter "$PAUL_ADAPTER_ROOT" "$PF_ARM"
pf_require_file "$PF_HRNET_IMAGENET"

if [[ -n $PF_DUMP ]]; then
  pf_dump hrnet
  case "$PF_DUMP_SCALES" in
    single) scales=1.0 ;;
    native) scales=0.5,1.0,2.0 ;;
    *) pf_die "--scales must be single or native" ;;
  esac
  export PAUL_HRNET_IMAGENET_CKPT=$PF_HRNET_IMAGENET
  pf_torchrun 1 hrnet
  cmd=("${PF_TORCHRUN[@]}" --dataset rtisrail22 --cv 0 --syncbn --apex --fp16 --eval "$PF_DUMP"
       --n_scales "$scales" --snapshot "$PF_DUMP_CKPT" --arch ocrnet.HRNet_Mscale
       --result_dir "$PF_DUMP_DIR/log" --dump_preds "$PF_DUMP_DIR/pred")
  pf_launch hrnet dump "$PF_DUMP_LABEL" "eval-only P4 dump (scripts/eval_rr22.yml settings, n_scales $scales)" \
    --chain "rad|ours|dumped|$PF_DUMP_CKPT" --base-provenance "$PF_RUN_DIR/provenance.json" --data-root "$PAUL_ADAPTER_ROOT" \
    --extra "split=$PF_DUMP" --extra "scales=$scales" -- "${cmd[@]}"
  exit 0
fi

pf_check_gpus "$PF_GPUS" 4
pf_probe_epochs
case "$PF_RS19" in
  paul)
    [[ -z $PF_RS19_CKPT ]] || pf_die "--rs19 paul uses the staged 0.7385 checkpoint; drop --rs19-ckpt"
    rs19_ckpt=$PF_PAUL_HRNET_RS19
    rs19_owner=paul
    ;;
  ours)
    [[ -n $PF_RS19_CKPT ]] || pf_die "--rs19 ours needs --rs19-ckpt <checkpoint of an hrnet-rs19-ours run>"
    rs19_prov=$(pf_check_rs19_ours "$PF_RS19_CKPT" hrnet-rs19-ours)
    rs19_ckpt=$PF_RS19_CKPT
    rs19_owner=ours
    ;;
  none)
    [[ -z $PF_RS19_CKPT ]] || pf_die "--rs19 none starts from NVIDIA Map->City; drop --rs19-ckpt"
    rs19_ckpt=""
    ;;
  *) pf_die "--rs19 must be paul, ours or none" ;;
esac
[[ -z $rs19_ckpt ]] || pf_require_file "$rs19_ckpt"
pf_require_file "$PF_NVIDIA_MAPCITY"

variant=${HRNET_RAD_RECIPE:-$PF_DEFAULT_RECIPE}
if [[ $PF_RS19 == none ]]; then
  chain=mapcity-direct head_from=Cityscapes
  [[ $variant == "$PF_DEFAULT_RECIPE" ]] \
    || pf_die "--rs19 none (mapcity-direct) runs Paul's shared settings only; unset HRNET_RAD_RECIPE"
  snapshot=$PF_NVIDIA_MAPCITY
else
  chain=rs19-$PF_RS19 head_from=RS19
  snapshot=$rs19_ckpt
fi
case "$variant" in
  paul-shared-20260923) lr=7e-5 epochs=1000 mscale_wt=0.05 scales=0.5,1.0,1.5
    source_note="hrnet/train_rtisrail22.yml in the hyperparameter files Paul shared on 2026-09-23 (Drive folder 'hyperparameters', copy at /data/izadia1/checkpoints/paul-hyperparameters-drive with SHA256SUMS)" ;;
  train_2) lr=1e-4 epochs=500 mscale_wt=0.05 scales=0.5,1.0,1.5
    source_note="pauls3/semantic-segmentation scripts/train_rtisrail22.yml @ d90f254 (train_2; = 'command' stored in rr22_rs19_city_miou_0.8964.pth)" ;;
  train_1) lr=1e-4 epochs=500 mscale_wt=0.1 scales=0.5,1.0,2.0
    source_note="pauls3/semantic-segmentation scripts/train_rtisrail22.yml @ 0cc4a7e (train_1 settings; NOT the 0.8964 recipe)" ;;
  *) pf_die "HRNET_RAD_RECIPE must be paul-shared-20260923, train_2 or train_1" ;;
esac
pf_rad_label "paper-hrnet__$chain" "$variant"
[[ -n ${PF_PROBE:-} ]] && epochs=$PF_PROBE

pf_fresh_run_dir
pf_export_paths
pf_torchrun 4 hrnet
cmd=("${PF_TORCHRUN[@]}"
  --dataset rtisrail22 --cv 0 --syncbn --apex --fp16 --gblur --brt_aug
  --crop_size "1080,1920" --bs_trn 1 --poly_exp 2 --lr "$lr" --rmi_loss
  --max_epoch "$epochs" --n_scales "$scales" --supervised_mscale_loss_wt "$mscale_wt"
  --snapshot "$snapshot" --arch ocrnet.HRNet_Mscale
  --result_dir "$PF_RUN_DIR/train")

deviations=(
  "data: RAD 9/24 arm '$PF_ARM' (21 classes incl. mud-pumping=13 and standing-water=20) instead of Paul's 2022 RAD v7 (19 classes); trainVal_ holds TRAIN ONLY (Paul's trainVal also contained val), val_ is our held-out val"
  "19-class $head_from head re-initialised for 21 classes (P2: only ocr.cls_head and ocr.aux_head.2 skipped; see train/init-coverage.json)"
  "Apex replaced by native AMP and torch DDP/SyncBN (September compat port, patch P0); torch.distributed.run instead of torch.distributed.launch"
  "September sampler fix kept: validation covers every val image exactly once; confusion matrices all-reduced as int64"
  "extra checkpoint best_mud_epoch_N.pth selected on val IoU of class 13 (P3); Paul's best-by-mIoU checkpoint is still written"
  "in-training validation uses the recipe's n_scales; scoring uses P4 single-scale dumps scored by Segmentary eval.py"
)
[[ $variant == paul-shared-20260923 ]] && deviations+=("recipe paul-shared-20260923 (lr 7e-5, 1000 epochs) is what Paul shared for this work, not the recipe stored in his 0.8964 checkpoint (train_2: lr 1e-4, 500 epochs)")
[[ $chain == mapcity-direct ]] && deviations+=("chain mapcity-direct: NVIDIA Map->City snapshot fine-tuned on RAD directly, skipping RailSem19. Paul shared no script for this chain; the settings are his shared hrnet/train_rtisrail22.yml (written for RS19 -> RAD) with only --snapshot changed")
[[ $variant == train_1 ]] && deviations+=("recipe variant train_1 is not the one that produced Paul's 0.8964 checkpoint")
[[ -n ${PF_PROBE:-} ]] && deviations+=("TIMING PROBE: max_epoch=$PF_PROBE (poly LR schedule differs); not a result")

if [[ $chain == mapcity-direct ]]; then
  prov=(--chain "map_city|nvidia|init|$PF_NVIDIA_MAPCITY")
else
  prov=(--chain "map_city|nvidia|ancestor|$PF_NVIDIA_MAPCITY"
        --chain "rs19|$rs19_owner|init|$rs19_ckpt")
fi
prov+=(--chain "rad|ours|this-run|"
      --weights "build-time-imagenet|$PF_HRNET_IMAGENET"
      --data-root "$PAUL_ADAPTER_ROOT"
      --extra "recipe_variant=$variant")
[[ $PF_RS19 == ours ]] && prov+=(--extra "rs19_run_provenance=$rs19_prov")
for d in "${PF_P0_DEVIATIONS[@]}" "$PF_P0_RMI_DEVIATION" "${deviations[@]}"; do prov+=(--deviation "$d"); done

pf_launch hrnet rad "$LABEL" "$source_note" "${prov[@]}" -- "${cmd[@]}"
