#!/usr/bin/env python
"""Milestone 3: overfit 8 images with no augmentation until mIoU > 0.95.

If this does not converge, something is wrong with the data path, the label
mapping, the loss, or the model wiring -- and no amount of GPU-hours will fix it.
It is the single cheapest check that catches the majority of pipeline bugs.

Deliberately a plain single-GPU loop rather than a Lightning run: fewer moving
parts means a failure here points at the pipeline, not at the trainer.

    segmentary-overfit base.yaml model.yaml experiment.yaml
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Literal, cast

import torch

from .config import ExperimentConfig, deep_merge, from_dict, load_yaml
from .curriculum import validate_training_contract
from .data.loaders import aug_from_spec, build_dataset, load_data_mapping
from .data.mixed import collate
from .data.transforms import build_overfit_transform
from .engine.inference import InferenceConfig, inference, prediction_from_inference
from .engine.losses import LossConfig, SegmentationLoss
from .engine.metrics import ConfusionMatrix
from .engine.module import dense_training_objective
from .engine.optim import build_optimizer
from .engine.query_loss import QuerySegmentationLoss, query_training_objective
from .models.factory import build_model
from .models.tuning import apply_tuning
from .tasks import validate_canonical_active, validate_task_space
from .taxonomy import load_space
from .utils.seed import seed_everything, seed_transforms


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("configs", nargs="+", type=Path)
    ap.add_argument("--images", type=int, default=8)
    ap.add_argument("--iters", type=int, default=400)
    ap.add_argument("--target", type=float, default=0.95)
    ap.add_argument("--lr", type=float, default=6e-4, help="high on purpose: we WANT overfitting")
    ap.add_argument("--crop", type=int, nargs=2, default=(512, 512))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda:0")
    args = ap.parse_args(argv)
    if args.images < 1 or args.iters < 1:
        ap.error("--images and --iters must be at least 1")
    if not 0.0 < args.target <= 1.0:
        ap.error("--target must be in (0, 1]")
    if args.lr <= 0.0:
        ap.error("--lr must be positive")
    if any(size < 1 for size in args.crop):
        ap.error("--crop dimensions must be positive")

    merged: dict = {}
    for p in args.configs:
        merged = deep_merge(merged, load_yaml(p))
    cfg = from_dict(ExperimentConfig, merged)
    validate_training_contract(cfg)
    seed_everything(args.seed)

    space = load_space(cfg.taxonomy_root, cfg.space)
    validate_task_space(cfg.loss.task, space)
    data = cfg.stages[0].data[0]
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model = apply_tuning(build_model(cfg.model, space.num_classes), cfg.model).to(device)
    if cfg.loss.query is not None and not getattr(model, "supports_query_objective", False):
        raise ValueError(
            f"loss.query requires raw QueryOutput, but {type(model).__name__} is a dense model"
        )
    aug = aug_from_spec(cfg.aug, model)
    aug.crop = tuple(args.crop)

    dataset = build_dataset(
        data, space, cfg.taxonomy_root, data.train_split, build_overfit_transform(aug)
    )
    seed_transforms(dataset, args.seed)
    dataset.samples = dataset.samples[: args.images]
    mapping = load_data_mapping(data, space, cfg.taxonomy_root)
    active = torch.from_numpy(mapping.active_mask())
    if cfg.loss.task == "binary":
        validate_canonical_active(
            active,
            cfg.loss.task,
            where=f"overfit dataset {data.name!r} active mask",
        )

    batch = collate([dataset[i] for i in range(len(dataset))])
    images = batch["image"].to(device)
    masks = batch["mask"].to(device)
    active_dev = active.to(device)

    print(
        f"overfitting {len(dataset)} {data.name} images at {tuple(args.crop)}, "
        f"space={space.name}, model={cfg.model.arch}, device={device}"
    )
    present = sorted(set(masks.unique().tolist()) - {space.ignore_index})
    print(
        f"classes present in these {len(dataset)} images: "
        f"{[space.classes[c].name for c in present]}"
    )
    print(f"ignore fraction: {100 * float((masks == space.ignore_index).float().mean()):.1f}%")

    loss_fn = (
        QuerySegmentationLoss(cfg.loss.query, space.num_classes, space.ignore_index)
        if cfg.loss.query is not None
        else SegmentationLoss(
            LossConfig.from_spec(cfg.loss),
            int(getattr(model, "output_channels", space.num_classes)),
            space.ignore_index,
        )
    ).to(device)

    opt_cfg = type(cfg.optim)(
        **{
            **vars(cfg.optim),
            "backbone_lr": args.lr,
            "warmup_iters": 10,
            "llrd": 1.0,
            "weight_decay": 0.0,
        }
    )
    head_patterns = tuple(model.head_patterns()) if hasattr(model, "head_patterns") else ("head",)
    optimizer = build_optimizer(model, opt_cfg, head_patterns)

    model.train()
    t0 = time.time()
    best = 0.0
    for step in range(1, args.iters + 1):
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
            # Branch rather than select a function object: each objective
            # accepts only its own loss type.
            if isinstance(loss_fn, QuerySegmentationLoss):
                loss, _ = query_training_objective(model, loss_fn, images, masks, active=active_dev)
            else:
                loss, _ = dense_training_objective(model, loss_fn, images, masks, active=active_dev)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        if step % 20 == 0 or step == args.iters:
            model.eval()
            with (
                torch.no_grad(),
                torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"),
            ):
                if cfg.loss.task not in ("multiclass", "binary"):
                    raise SystemExit(
                        f"overfit check supports multiclass and binary, not {cfg.loss.task!r}"
                    )
                infer_cfg = InferenceConfig(
                    sliding_window=False,
                    task=cast(Literal["multiclass", "binary"], cfg.loss.task),
                    threshold=cfg.eval.threshold,
                )
                scores = inference(model, images, space.num_classes, infer_cfg)
                pred = prediction_from_inference(scores.float(), infer_cfg)
            cm = ConfusionMatrix(
                space.num_classes, space.ignore_index, active=active_dev, device=device
            )
            cm.update(pred, masks)
            miou = cm.compute().miou
            best = max(best, miou)
            print(
                f"  step {step:>4}  loss {loss.detach().item():.4f}  mIoU {miou:.4f}"
                f"  ({time.time() - t0:.0f}s)"
            )
            model.train()
            if miou > args.target:
                print(
                    f"\nPASS: reached mIoU {miou:.4f} > {args.target} at step {step} "
                    f"in {time.time() - t0:.0f}s"
                )
                return 0

    print(
        f"\nFAIL: best mIoU {best:.4f} after {args.iters} steps, target {args.target}.\n"
        f"The pipeline cannot memorise {len(dataset)} images, so the bug is upstream of\n"
        f"training. Check, in order: verify_dataset.py overlays (alignment/palette),\n"
        f"the taxonomy mapping for this dataset, that logits are upsampled to label\n"
        f"resolution, and that the head is actually receiving gradient."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
