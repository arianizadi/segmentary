"""AdamW parameter groups with layer-wise LR decay, plus the poly/warmup schedule.

Two decisions live here that the rest of the trainer depends on:

1. Which learning rate each parameter gets. Depths come from
   ``engine.layer_depth``; this file turns them into per-group LRs via
   ``lr = backbone_lr * llrd ** (max_depth - depth)``.

2. What weight decay may touch. Decaying biases, norm scales, position
   embeddings or cls tokens shrinks parameters that have no scale-invariance
   argument for being shrunk, and reliably costs a fraction of a point of mIoU.

The head is treated as the deepest layer with an explicit multiplier: it is
randomly initialised, so it needs the full learning rate no matter how
aggressive ``llrd`` is on the encoder.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import torch
from torch import nn
from torch.optim.lr_scheduler import LambdaLR

from ..config import OptimConfig
from .layer_depth import DEFAULT_HEAD_PATTERNS, assign_layer_id, discover_layout, is_head

__all__ = [
    "DEFAULT_HEAD_PATTERNS",
    "NO_DECAY_PATTERNS",
    "assign_layer_id",
    "build_optimizer",
    "build_param_groups",
    "build_scheduler",
    "describe_param_groups",
    "poly_lr_lambda",
]

# Substrings that force weight_decay=0 even when the tensor is multi-dimensional
# (a 2-D relative-position table is still an embedding, not a weight matrix).
NO_DECAY_PATTERNS: tuple[str, ...] = (
    "bias",
    "norm",
    "bn",
    "pos_embed",
    "position_embed",
    "positional_embed",
    "cls_token",
    "class_token",
    "register_token",
    "mask_token",
    "gamma",
    "layer_scale",
)


def _no_decay(name: str, param: torch.Tensor) -> bool:
    if param.ndim <= 1:
        return True
    return any(pattern in name.lower() for pattern in NO_DECAY_PATTERNS)


def build_param_groups(
    model: nn.Module, cfg: OptimConfig, head_patterns: Sequence[str]
) -> list[dict]:
    """Group trainable parameters by (depth, decay) with layer-wise decayed LRs.

    Head parameters -- those whose name contains any of ``head_patterns`` -- get
    ``backbone_lr * head_lr_mult`` and no layer decay. Everything else gets
    ``backbone_lr * llrd ** (max_depth - depth)``. Parameters with
    ``requires_grad=False`` are dropped, so frozen encoders and LoRA base weights
    never reach the optimiser state.
    """
    if not head_patterns:
        raise ValueError(
            "head_patterns is empty; the randomly initialised head would be trained at the "
            "backbone LR and the run would underfit it"
        )
    layout = discover_layout(model, head_patterns)
    if layout.num_layers == 0 and cfg.llrd != 1.0:
        # A ResNet/HRNet trunk has no numbered block list to read, so every
        # backbone tensor lands at depth 0 and llrd degenerates into a blanket
        # multiplier on backbone_lr -- a plausible-looking run at the wrong LR.
        raise ValueError(
            f"llrd={cfg.llrd} was requested but no transformer blocks could be found in "
            f"{type(model).__name__}; layer-wise decay would silently scale the whole "
            f"backbone by llrd instead. Set llrd=1.0 and use backbone_lr directly."
        )
    buckets: dict[tuple[int, bool], dict] = {}

    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        head = is_head(name, head_patterns)
        depth = assign_layer_id(
            name, layout.num_layers, head_patterns, stage_blocks=layout.stage_blocks
        )
        decay = not _no_decay(name, param)
        key = (depth, decay)
        group = buckets.get(key)
        if group is None:
            scale = cfg.llrd ** (layout.max_depth - depth)
            lr = cfg.backbone_lr * scale * (cfg.head_lr_mult if head else 1.0)
            group = {
                "params": [],
                "param_names": [],
                "lr": lr,
                "weight_decay": cfg.weight_decay if decay else 0.0,
                "layer_id": depth,
                "is_head": head,
                "name": f"{'head' if head else f'layer{depth}'}.{'decay' if decay else 'no_decay'}",
            }
            buckets[key] = group
        group["params"].append(param)
        group["param_names"].append(name)

    if not buckets:
        raise ValueError(
            "no trainable parameters found; every parameter has requires_grad=False, so "
            "the optimiser would have nothing to update"
        )
    return [buckets[key] for key in sorted(buckets)]


def build_optimizer(
    model: nn.Module, cfg: OptimConfig, head_patterns: Sequence[str]
) -> torch.optim.AdamW:
    """AdamW over ``build_param_groups(model, cfg, head_patterns)``."""
    groups = build_param_groups(model, cfg, head_patterns)
    # Per-group lr/weight_decay override these defaults; they only matter for
    # groups added later (e.g. by a callback) and for optimizer.defaults logging.
    return torch.optim.AdamW(
        groups, lr=cfg.backbone_lr, betas=cfg.betas, weight_decay=cfg.weight_decay
    )


def poly_lr_lambda(cfg: OptimConfig, total_iters: int) -> Callable[[int], float]:
    """Multiplicative LR factor per iteration: linear warmup, then poly decay.

    The returned factor is applied to each group's own base LR, so layer-wise
    decay and the head multiplier survive the schedule unchanged.
    """
    if total_iters < 1:
        raise ValueError(f"total_iters must be >= 1, got {total_iters}")
    if cfg.warmup_iters < 0:
        raise ValueError(f"warmup_iters must be >= 0, got {cfg.warmup_iters}")
    if cfg.warmup_iters >= total_iters:
        raise ValueError(
            f"warmup_iters={cfg.warmup_iters} >= total_iters={total_iters}; the run would "
            f"end before the LR ever reaches its peak"
        )
    if not 0.0 <= cfg.min_lr_ratio <= 1.0:
        raise ValueError(f"min_lr_ratio must be in [0, 1], got {cfg.min_lr_ratio}")
    if not 0.0 <= cfg.warmup_ratio <= 1.0:
        raise ValueError(f"warmup_ratio must be in [0, 1], got {cfg.warmup_ratio}")

    warmup = cfg.warmup_iters
    ratio = cfg.warmup_ratio
    power = cfg.poly_power
    floor = cfg.min_lr_ratio

    def factor(it: int) -> float:
        if it < 0:
            raise ValueError(f"iteration must be >= 0, got {it}")
        if warmup > 0 and it < warmup:
            return ratio + (1.0 - ratio) * (it / warmup)
        progress = (it - warmup) / max(1, total_iters - warmup)
        return max((1.0 - progress) ** power, floor)

    return factor


def build_scheduler(
    optimizer: torch.optim.Optimizer, cfg: OptimConfig, total_iters: int
) -> LambdaLR:
    """Per-iteration LambdaLR wrapping ``poly_lr_lambda``. Step it every optimiser step."""
    return LambdaLR(optimizer, lr_lambda=poly_lr_lambda(cfg, total_iters))


def describe_param_groups(groups: list[dict]) -> str:
    """One compact block for the run log: group count, LR range, decay split."""
    if not groups:
        raise ValueError("no parameter groups to describe")
    lrs = [float(g["lr"]) for g in groups]
    decayed = [g for g in groups if float(g["weight_decay"]) > 0.0]
    plain = [g for g in groups if float(g["weight_decay"]) == 0.0]
    head = [g for g in groups if g.get("is_head")]

    def _count(subset: list[dict]) -> tuple[int, int]:
        tensors = sum(len(g["params"]) for g in subset)
        elements = sum(int(p.numel()) for g in subset for p in g["params"])
        return tensors, elements

    lines = [
        f"{len(groups)} param groups | lr {min(lrs):.3e} .. {max(lrs):.3e} "
        f"| depths {min(int(g['layer_id']) for g in groups)}..{max(int(g['layer_id']) for g in groups)}",
    ]
    for label, subset in (("decay", decayed), ("no_decay", plain), ("head", head)):
        tensors, elements = _count(subset)
        lines.append(f"  {label:<8} {tensors:>4} tensors, {elements / 1e6:8.2f}M params")
    return "\n".join(lines)
