"""Evaluate a checkpoint under the fixed protocol.

    python -m segmentary.eval configs/base.yaml configs/models/segformer_b2.yaml \
        configs/curricula/cs_rs.yaml --ckpt runs/cs_rs_seed0/railsem19/best.ckpt

For the post-run RailSem19 sweep, evaluate every checkpoint on the same common
split and pass that training run's seed explicitly, for example ``--seed 1
--dataset railsem19 --root /data/.../railsem19 --split-file
splits/railsem19_seed0.json --out .../common_railsem19_seed1/results.json``. The seed
override is applied before hashing, so each RunRecord contains the matching
seed, config, and hash; supply a distinct ``--out`` path for each run.

The protocol is identical to what training's validation loop uses -- native
resolution, sliding window, same metrics -- so an eval.py number and a training
val number are directly comparable. TTA is opt-in via --tta and is reported as a
separate variant, never as the headline.

--dataset lets you score a checkpoint on a dataset it was not trained on, which
is how the zero-shot domain-gap numbers are produced.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal, cast

import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from .checkpoints import checkpoint_uses_lora, read_checkpoint
from .config import (
    DataConfig,
    ExperimentConfig,
    config_hash,
    deep_merge,
    from_dict,
    load_yaml,
    to_dict,
)
from .data.loaders import aug_from_spec, build_dataset, input_normalization, load_data_mapping
from .data.mixed import collate
from .data.transforms import build_eval_transform
from .engine.boundary import BoundaryConfig, BoundaryF1
from .engine.ema import EMA_CHECKPOINT_KEY, EmaConfig, ModelEma
from .engine.inference import InferenceConfig, inference, prediction_from_inference
from .engine.metrics import ConfusionMatrix
from .models.factory import build_model
from .models.tuning import apply_tuning
from .models.wrappers import SegmentationModel
from .tasks import (
    validate_canonical_active,
    validate_task_configuration,
    validate_task_space,
)
from .taxonomy import load_space
from .train import parse_override
from .utils.provenance import collect_env, discover_git_root, git_sha, peak_vram
from .utils.results import RunRecord, RunTimer, write_results
from .utils.seed import seed_everything


def load_checkpoint(
    model: torch.nn.Module,
    ckpt: Path,
    use_ema: bool,
    *,
    checkpoint_state: dict | None = None,
) -> None:
    state = read_checkpoint(ckpt) if checkpoint_state is None else checkpoint_state
    if use_ema:
        if EMA_CHECKPOINT_KEY not in state:
            raise ValueError(
                f"{ckpt} contains no EMA weights but --ema was requested. Drop --ema or "
                f"use a checkpoint that explicitly saved its EMA shadow weights."
            )
        ema = ModelEma(model, EmaConfig())
        try:
            ema.load_state_dict(state[EMA_CHECKPOINT_KEY])
            ema.copy_to(model)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"{ckpt} contains invalid EMA state: {exc}") from exc
        return

    sd = state.get("state_dict", state)
    if isinstance(sd, dict):
        sd = {k[len("model.") :]: v for k, v in sd.items() if k.startswith("model.")} or sd
    else:
        raise RuntimeError(f"{ckpt} has no dictionary state_dict")
    missing, unexpected = model.load_state_dict(sd, strict=False)
    if missing or unexpected:
        raise RuntimeError(
            f"{ckpt} does not exactly match this model: {len(missing)} missing "
            f"(first {missing[:5]}), {len(unexpected)} unexpected "
            f"(first {unexpected[:5]})"
        )


def load_configured_checkpoint(
    model: SegmentationModel,
    cfg: ExperimentConfig,
    ckpt: Path,
    use_ema: bool,
) -> SegmentationModel:
    """Match a raw or PEFT-shaped checkpoint before exact loading."""
    state = read_checkpoint(ckpt)
    adapted = checkpoint_uses_lora(state)
    if cfg.model.tuning == "lora" and adapted:
        model = apply_tuning(model, cfg.model)
    load_checkpoint(model, ckpt, use_ema, checkpoint_state=state)
    if cfg.model.tuning == "lora" and not adapted:
        model = apply_tuning(model, cfg.model)
    return model


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("configs", nargs="+", type=Path)
    ap.add_argument("--ckpt", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=None, help="override train.seed for this record")
    ap.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="dotted config override, repeatable",
    )
    ap.add_argument("--dataset", default=None, help="override which dataset to score on")
    ap.add_argument(
        "--loader",
        default=None,
        help="dataset loader id (for example folder) or package.module:DatasetClass",
    )
    ap.add_argument("--mapping", default=None, help="taxonomy mapping stem; defaults to dataset")
    ap.add_argument(
        "--loader-options",
        default="{}",
        metavar="JSON",
        help="loader-specific JSON object, for example '{\"recursive\": false}'",
    )
    ap.add_argument("--root", default=None, help="dataset root when --dataset is given")
    ap.add_argument("--split-file", default=None)
    ap.add_argument(
        "--split",
        default=None,
        help="split to score (default: the configured val_split, or 'val' with --dataset)",
    )
    ap.add_argument("--variant", default=None)
    ap.add_argument("--stage", default=None, help="which stage's data to use (default: last)")
    ap.add_argument("--tta", action="store_true", help="multi-scale + flip; a reported variant")
    ap.add_argument("--scales", type=float, nargs="+", default=[0.75, 1.0, 1.25, 1.5])
    ap.add_argument("--ema", action="store_true", help="score the EMA weights")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="evaluation loader workers; 0 loads in-process (default: eval.num_workers)",
    )
    args = ap.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        ap.error("--limit must be at least 1")
    if args.num_workers is not None and args.num_workers < 0:
        ap.error("--num-workers cannot be negative")
    try:
        loader_options = json.loads(args.loader_options)
    except json.JSONDecodeError as exc:
        ap.error(f"--loader-options must be valid JSON: {exc}")
    if not isinstance(loader_options, dict):
        ap.error("--loader-options must decode to a JSON object")
    if args.dataset is None and (
        args.root is not None
        or args.loader is not None
        or args.mapping is not None
        or args.variant is not None
        or args.split_file is not None
        or loader_options
    ):
        ap.error(
            "--root/--loader/--mapping/--variant/--split-file/--loader-options require "
            "--dataset; use --stage to evaluate configured data"
        )

    merged: dict = {}
    for p in args.configs:
        merged = deep_merge(merged, load_yaml(p))
    for item in args.set:
        merged = deep_merge(merged, parse_override(item))
    if args.seed is not None:
        merged = deep_merge(merged, {"train": {"seed": args.seed}})
    cfg = from_dict(ExperimentConfig, merged)
    validate_task_configuration(cfg)
    seed_everything(cfg.train.seed)

    space = load_space(cfg.taxonomy_root, cfg.space)
    validate_task_space(cfg.loss.task, space)
    if args.stage is None:
        stage = cfg.stages[-1]
    else:
        matches = [s for s in cfg.stages if s.name == args.stage]
        if not matches:
            raise SystemExit(
                f"unknown stage {args.stage!r}; configured stages are "
                f"{[s.name for s in cfg.stages]}"
            )
        stage = matches[0]

    if args.dataset:
        if not args.root:
            raise SystemExit("--dataset requires --root")
        split = args.split or "val"
        data = DataConfig(
            name=args.dataset,
            root=args.root,
            loader=args.loader,
            mapping=args.mapping,
            loader_options=loader_options,
            variant=args.variant,
            split_file=args.split_file,
            val_split=split,
            limit=args.limit,
        )
    else:
        data = stage.data[0]
        split = args.split or data.val_split
        if args.limit is not None:
            data = DataConfig(**{**to_dict(data), "limit": args.limit})

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model = build_model(cfg.model, space.num_classes)
    model = load_configured_checkpoint(model, cfg, args.ckpt, args.ema)
    model = model.to(device).eval()

    transform = build_eval_transform(aug_from_spec(cfg.aug, model))
    mapping = load_data_mapping(data, space, cfg.taxonomy_root)
    active = torch.from_numpy(mapping.active_mask())
    if cfg.loss.task == "binary":
        validate_canonical_active(
            active,
            cfg.loss.task,
            where=f"evaluation dataset {data.name!r} active mask",
        )
    dataset = build_dataset(data, space, cfg.taxonomy_root, split, transform)

    # InferenceConfig would reject anything else in __post_init__; checking here
    # names the command that cannot serve the task instead of the dataclass.
    if cfg.loss.task not in ("multiclass", "binary"):
        raise SystemExit(
            f"segmentary-eval supports multiclass and binary tasks, not {cfg.loss.task!r}"
        )
    task = cast(Literal["multiclass", "binary"], cfg.loss.task)

    infer_cfg = InferenceConfig(
        sliding_window=cfg.eval.sliding_window,
        window=(int(cfg.eval.window[0]), int(cfg.eval.window[1])),
        stride=(int(cfg.eval.stride[0]), int(cfg.eval.stride[1])),
        scales=tuple(args.scales) if args.tta else (1.0,),
        flip=bool(args.tta),
        task=task,
        threshold=cfg.eval.threshold,
    )

    cm = ConfusionMatrix(
        space.num_classes, space.ignore_index, active=active.to(device), device=device
    )
    bf1 = BoundaryF1(
        space.num_classes,
        space.ignore_index,
        cfg=BoundaryConfig(tolerance_frac=cfg.eval.boundary_tolerance_frac),
        active=active.to(device),
        device=device,
    )

    num_workers = cfg.eval.num_workers if args.num_workers is None else args.num_workers
    # dict[str, Any]: these are DataLoader keyword arguments with several
    # different parameter types, and a narrower inferred value type fails every
    # one of them when the mapping is unpacked.
    loader_kwargs: dict[str, Any] = {
        "batch_size": cfg.eval.batch_size,
        "shuffle": False,
        "num_workers": num_workers,
        "collate_fn": collate,
        "pin_memory": True,
    }
    if num_workers > 0:
        # The evaluator constructs CUDA models and metrics before its loader is
        # iterated. Linux's default ``fork`` can inherit a locked CUDA or
        # threaded-library runtime at that point. ``spawn`` gives standalone
        # evaluation fresh workers. Custom datasets used this way must be
        # picklable; set workers to zero for in-process loading when they are not.
        loader_kwargs["multiprocessing_context"] = "spawn"
    loader = DataLoader(dataset, **loader_kwargs)

    print(f"evaluating {args.ckpt}")
    print(f"  dataset : {dataset.describe()}  split={split}")
    print(
        f"  weights : {'EMA' if args.ema else 'raw'}   TTA: {'on ' + str(args.scales) if args.tta else 'off'}"
    )
    print(
        f"  protocol: {'sliding window ' + str(infer_cfg.window) + ' stride ' + str(infer_cfg.stride) if infer_cfg.sliding_window else 'whole image'}"
    )
    if infer_cfg.task == "binary":
        print(f"  prediction: sigmoid class-1 threshold {infer_cfg.threshold:.6g}")

    with RunTimer() as timer, torch.no_grad():
        for batch in tqdm(loader, desc="eval"):
            image = batch["image"].to(device, non_blocking=True)
            target = batch["mask"].to(device, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits = inference(model, image, space.num_classes, infer_cfg)
            pred = prediction_from_inference(logits.float(), infer_cfg)
            cm.update(pred, target)
            bf1.update(pred, target)

    if timer.started_at is None:
        raise RuntimeError("run timer recorded no start time; evaluation never ran")
    result = cm.compute()
    metrics = result.as_dict(list(space.names))
    metrics["boundary"] = bf1.compute().as_dict(list(space.names))
    if cfg.eval.save_confusion:
        metrics["confusion"] = result.confusion.tolist()

    print(
        f"\nmIoU {result.miou:.4f} | mAcc {result.macc:.4f} | pixel acc {result.pixel_accuracy:.4f}"
    )
    print(f"{'class':<16} {'IoU':>8} {'support':>14}")
    for cid, name in enumerate(space.names):
        iou = result.iou[cid]
        shown = "  n/a" if torch.isnan(iou) else f"{float(iou):.4f}"
        print(f"{name:<16} {shown:>8} {int(result.support[cid]):>14,}")

    provenance_root = discover_git_root([*args.configs, Path.cwd()]) or Path.cwd()
    sha, dirty = git_sha(provenance_root)
    record_config = to_dict(cfg)
    record_config["evaluation"] = {
        "data": to_dict(data),
        "split": split,
        "num_workers": num_workers,
        "weights": "ema" if args.ema else "raw",
        "tta": {
            "enabled": bool(args.tta),
            "scales": list(infer_cfg.scales),
            "flip": bool(infer_cfg.flip),
        },
        "prediction": {
            "task": infer_cfg.task,
            "activation": "sigmoid" if infer_cfg.task == "binary" else "softmax",
            "threshold": infer_cfg.threshold if infer_cfg.task == "binary" else None,
        },
    }
    record_env = collect_env()
    record_env["input_normalization"] = input_normalization(model)
    out = args.out or (
        args.ckpt.parent / f"eval_{data.name}_{split}{'_tta' if args.tta else ''}" / "results.json"
    )
    write_results(
        out,
        RunRecord(
            name=cfg.name,
            stage=f"eval:{data.name}:{split}",
            config_hash=config_hash(record_config),
            git_sha=sha,
            git_dirty=dirty,
            seed=cfg.train.seed,
            started_at=timer.started_at,
            finished_at=timer.finished_at,
            wall_clock_s=timer.wall_clock_s,
            peak_vram_bytes=peak_vram(),
            metrics=metrics,
            config=record_config,
            env=record_env,
            dataset_sizes={"eval": len(dataset)},
            notes=f"checkpoint={args.ckpt} ema={args.ema} tta={args.tta}",
        ),
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
