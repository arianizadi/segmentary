"""Composable semantic-segmentation objectives with strict mask semantics.

The module consumes raw logits; activation is an objective decision, never a
model-side layer. Every term runs in float32 under mixed precision, excludes
``ignore_index`` exactly, and respects the per-sample active-class mask used by
mixed-dataset curricula. All-ignore crops return a graph-connected zero.

Implementations are small formulations from the cited papers and PyTorch
primitives. They do not depend on or copy an external segmentation framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import torch
import torch.nn.functional as F
from torch import Tensor, nn

if TYPE_CHECKING:
    from ..config import LossSpec, LossTermSpec

AuxKind = Literal["none", "lovasz", "dice"]


def _graph_zero(tensor: Tensor) -> Tensor:
    """Return an exact graph-connected zero without reading tensor values."""
    return tensor[:0].sum()


@dataclass
class LossConfig:
    """Runtime objective config.

    ``terms`` is the canonical API. The legacy fields preserve old Python call
    sites and are migrated to the same typed term dataclasses during
    construction.
    """

    task: Literal["multiclass", "binary", "multilabel"] = "multiclass"
    activation: Literal["auto", "softmax", "sigmoid"] = "auto"
    terms: list[LossTermSpec] = field(default_factory=list)
    aux: AuxKind = "none"
    aux_weight: float = 0.0
    ce_weight: float = 1.0
    label_smoothing: float = 0.0
    class_weights: list[float] | None = None

    def __post_init__(self) -> None:
        # Import lazily so config.py remains the single validation definition
        # without creating an import cycle at module import time.
        from ..config import ConfigError, LossSpec

        try:
            spec = LossSpec(
                task=self.task,
                activation=self.activation,
                terms=self.terms,
                aux=self.aux,
                aux_weight=self.aux_weight,
                ce_weight=self.ce_weight,
                label_smoothing=self.label_smoothing,
                class_weights=self.class_weights,
            )
        except ConfigError as exc:
            raise ValueError(str(exc)) from exc
        self.terms = spec.resolved_terms()

    @classmethod
    def from_spec(cls, spec: LossSpec) -> LossConfig:
        return cls(task=spec.task, activation=spec.activation, terms=spec.resolved_terms())


def mask_inactive(logits: Tensor, active: Tensor | None) -> Tensor:
    """Drive classes a sample cannot label to the finite dtype floor.

    ``active`` may be ``(C,)`` or ``(N, C)``. Inactive multiclass logits are
    removed from softmax competition. Sigmoid objectives also apply the mask to
    their unreduced element losses so those channels receive zero gradient.
    """
    if active is None:
        return logits
    n, c = logits.shape[:2]
    if active.ndim == 1:
        if active.shape != (c,):
            raise ValueError(f"active mask {tuple(active.shape)} does not match {c} classes")
        view = active.view(1, c, 1, 1)
    elif active.ndim == 2:
        if active.shape != (n, c):
            raise ValueError(
                f"per-sample active mask {tuple(active.shape)} does not match batch ({n}, {c})"
            )
        view = active.view(n, c, 1, 1)
    else:
        raise ValueError(f"active mask must be 1-D (C,) or 2-D (N, C), got {active.ndim}-D")
    if not bool(active.bool().any(dim=-1).all()):
        raise ValueError("active mask excludes every class; the loss would be undefined")
    return logits.masked_fill(
        ~view.to(device=logits.device, dtype=torch.bool), torch.finfo(logits.dtype).min
    )


def _active_view(active: Tensor | None, n: int, c: int, device: torch.device) -> Tensor:
    if active is None:
        return torch.ones((n, c, 1, 1), dtype=torch.bool, device=device)
    if active.ndim == 1:
        return active.to(device=device, dtype=torch.bool).view(1, c, 1, 1).expand(n, -1, -1, -1)
    return active.to(device=device, dtype=torch.bool).view(n, c, 1, 1)


def lovasz_grad(gt_sorted: Tensor) -> Tensor:
    """Gradient of the Lovasz extension of Jaccard (Berman et al., 2018)."""
    p = gt_sorted.numel()
    gts = gt_sorted.sum()
    intersection = gts - gt_sorted.cumsum(0)
    union = gts + (1 - gt_sorted).cumsum(0)
    jaccard = 1.0 - intersection / union.clamp(min=1e-12)
    if p > 1:
        jaccard = torch.cat((jaccard[:1], jaccard[1:] - jaccard[:-1]))
    return jaccard


def lovasz_softmax(
    probs: Tensor,
    target: Tensor,
    present_only: bool = True,
    class_ids: list[int] | None = None,
) -> Tensor:
    """Lovasz-Softmax over flattened, valid multiclass pixels."""
    if probs.numel() == 0:
        return probs.sum() * 0.0
    losses = []
    for class_id in class_ids if class_ids is not None else range(probs.shape[1]):
        fg = (target == class_id).to(probs.dtype)
        if present_only and not bool(fg.any()):
            continue
        errors = (fg - probs[:, class_id]).abs()
        errors_sorted, perm = torch.sort(errors, descending=True)
        losses.append(torch.dot(errors_sorted, lovasz_grad(fg[perm])))
    return torch.stack(losses).mean() if losses else probs.sum() * 0.0


def soft_dice(
    probs: Tensor,
    target: Tensor,
    num_classes: int,
    eps: float = 1.0,
    *,
    present_only: bool = True,
    include_background: bool = True,
) -> Tensor:
    """Macro soft Dice over flattened, valid multiclass pixels."""
    if probs.numel() == 0:
        return probs.sum() * 0.0
    onehot = F.one_hot(target, num_classes).to(probs.dtype)
    selected = torch.ones(num_classes, dtype=torch.bool, device=probs.device)
    if not include_background:
        selected[0] = False
    if present_only:
        selected &= onehot.sum(0) > 0
    if not bool(selected.any()):
        return probs.sum() * 0.0
    inter = (probs * onehot).sum(0)
    denom = probs.sum(0) + onehot.sum(0)
    return 1.0 - ((2.0 * inter + eps) / (denom + eps))[selected].mean()


def _multiclass_vectors(
    probs: Tensor, target: Tensor, valid: Tensor, num_classes: int
) -> tuple[Tensor, Tensor]:
    flat_valid = valid.reshape(-1)
    flat_probs = probs.permute(0, 2, 3, 1).reshape(-1, num_classes)[flat_valid]
    flat_target = target.reshape(-1)[flat_valid]
    return flat_probs, flat_target


def _cross_entropy_pixels(
    logits: Tensor,
    target: Tensor,
    valid: Tensor,
    active_view: Tensor,
    *,
    label_smoothing: float,
    class_weights: list[float] | None,
) -> tuple[Tensor, Tensor]:
    """Return valid per-pixel CE and its weighted-mean denominator.

    PyTorch's built-in label smoothing distributes mass over every channel.
    That is wrong for mixed-taxonomy batches because inactive channels have
    deliberately been removed from the softmax. Here smoothing mass is spread
    only across the classes active for each sample.
    """
    safe_target = target.masked_fill(~valid, 0)
    log_probs = F.log_softmax(logits, dim=1)
    target_log_prob = log_probs.gather(1, safe_target.unsqueeze(1)).squeeze(1)
    weights = (
        torch.tensor(class_weights, dtype=logits.dtype, device=logits.device)
        if class_weights is not None
        else None
    )
    target_weight = (
        weights[safe_target] if weights is not None else torch.ones_like(target_log_prob)
    )
    raw = -target_log_prob * target_weight
    if label_smoothing:
        class_mask = active_view.expand_as(logits).to(logits.dtype)
        if weights is not None:
            class_mask = class_mask * weights.view(1, -1, 1, 1)
        active_count = active_view.sum(1).to(logits.dtype)
        smooth = -(log_probs * class_mask).sum(1) / active_count
        raw = (1.0 - label_smoothing) * raw + label_smoothing * smooth
    denominator = target_weight[valid].sum() if weights is not None else valid.sum()
    if not bool(denominator > 0):
        raise ValueError(
            "cross-entropy class weights are zero for every valid target in this batch"
        )
    return raw[valid], denominator.to(logits.dtype)


def _multiclass_onehot(
    target: Tensor, valid: Tensor, num_classes: int, dtype: torch.dtype
) -> Tensor:
    safe = target.masked_fill(~valid, 0)
    return F.one_hot(safe, num_classes).permute(0, 3, 1, 2).to(dtype) * valid.unsqueeze(1)


def _sigmoid_target(target: Tensor, logits: Tensor, ignore_index: int) -> tuple[Tensor, Tensor]:
    """Normalize binary/multilabel targets to ``(N,C,H,W)`` and valid pixels."""
    n, c, h, w = logits.shape
    if target.ndim == 3:
        if c != 1 or target.shape != (n, h, w):
            raise ValueError(
                "binary index targets shaped (N,H,W) require exactly one output channel"
            )
        valid = target != ignore_index
        if bool(((target[valid] != 0) & (target[valid] != 1)).any()):
            raise ValueError("binary targets must contain only 0, 1, or ignore_index")
        dense = target.masked_fill(~valid, 0).unsqueeze(1).to(logits.dtype)
        return dense, valid.unsqueeze(1)
    if target.ndim != 4 or target.shape != logits.shape:
        raise ValueError(
            f"multilabel target must match logits {tuple(logits.shape)}, got {tuple(target.shape)}"
        )
    valid = target != ignore_index
    if bool(((target[valid] != 0) & (target[valid] != 1)).any()):
        raise ValueError("multilabel targets must contain only 0, 1, or ignore_index")
    return target.masked_fill(~valid, 0).to(logits.dtype), valid


def _selected_channels(num_classes: int, include_background: bool) -> list[int]:
    return list(range(0 if include_background else 1, num_classes))


def _soft_boundary(values: Tensor, width: int) -> Tensor:
    kernel = 2 * width + 1
    return (F.max_pool2d(values, kernel, stride=1, padding=width) - values).clamp(0.0, 1.0)


def _truncated_distance_to_foreground(mask: Tensor, max_distance: int) -> Tensor:
    """City-block distance transform using only max-pooling primitives."""
    reached = mask > 0.5
    distance = torch.zeros_like(mask)
    frontier = reached
    for step in range(1, max_distance + 1):
        expanded = F.max_pool2d(frontier.to(mask.dtype), 3, stride=1, padding=1) > 0.5
        newly_reached = expanded & ~reached
        distance = torch.where(newly_reached, torch.full_like(distance, float(step)), distance)
        reached |= expanded
        frontier = expanded
    return torch.where(reached, distance, torch.full_like(distance, float(max_distance)))


class SegmentationLoss(nn.Module):
    """Evaluate a validated weighted list of dense segmentation objectives.

    ``teacher_logits`` is required only when ``kl_distillation`` is configured.
    The teacher must already use the same channel order and spatial resolution;
    Segmentary deliberately does not guess class or resolution mappings.
    """

    def __init__(self, cfg: LossConfig, num_classes: int, ignore_index: int = 255) -> None:
        super().__init__()
        if num_classes < 1:
            raise ValueError(f"num_classes must be positive, got {num_classes}")
        if cfg.task == "binary" and num_classes != 1:
            raise ValueError("task='binary' requires a one-channel model output")
        if cfg.task == "multiclass" and num_classes < 2:
            raise ValueError("task='multiclass' requires at least two classes")
        self.cfg = cfg
        self.num_classes = num_classes
        self.ignore_index = ignore_index
        for term in cfg.terms:
            for name in ("class_weights", "pos_weights"):
                weights = getattr(term, name, None)
                if weights is not None and len(weights) != num_classes:
                    raise ValueError(
                        f"{term.kind}.{name} has {len(weights)} entries, expected {num_classes}"
                    )
            alpha = getattr(term, "alpha", None)
            if term.kind == "focal" and isinstance(alpha, list) and len(alpha) != num_classes:
                raise ValueError(f"focal.alpha has {len(alpha)} entries, expected {num_classes}")

    def forward(
        self,
        logits: Tensor,
        target: Tensor,
        active: Tensor | None = None,
        *,
        teacher_logits: Tensor | None = None,
    ) -> tuple[Tensor, dict[str, Tensor]]:
        if logits.ndim != 4:
            raise ValueError(f"logits must be (N,C,H,W), got {tuple(logits.shape)}")
        if logits.shape[1] != self.num_classes:
            raise ValueError(f"expected {self.num_classes} logits, got {logits.shape[1]}")
        if target.shape[0] != logits.shape[0] or target.shape[-2:] != logits.shape[-2:]:
            raise ValueError(
                f"logits {tuple(logits.shape)} and target {tuple(target.shape)} disagree; "
                "upsample logits to label resolution before the loss"
            )
        if not bool(torch.isfinite(logits).all()):
            raise FloatingPointError("segmentation loss received non-finite logits")
        if self.cfg.task == "multiclass" and (
            target.dtype == torch.bool or target.is_floating_point() or target.is_complex()
        ):
            raise ValueError("multiclass targets must use an integer class-index dtype")
        original_logits = logits
        if logits.dtype not in (torch.float32, torch.float64):
            logits = logits.float()
        active_view = _active_view(active, logits.shape[0], logits.shape[1], logits.device)
        if self.cfg.task == "multiclass":
            masked_logits = mask_inactive(logits, active)
            target = target.long()
            valid = target != self.ignore_index
            if bool(valid.any()):
                if bool(((target[valid] < 0) | (target[valid] >= self.num_classes)).any()):
                    raise ValueError(
                        f"multiclass targets must be in [0, {self.num_classes - 1}] or "
                        f"ignore_index={self.ignore_index}"
                    )
                sample_index = torch.arange(target.shape[0], device=target.device)[:, None, None]
                supervised = active_view[:, :, 0, 0][
                    sample_index, target.clamp(0, self.num_classes - 1)
                ]
                if bool((valid & ~supervised).any()):
                    raise ValueError("target contains a class marked inactive for that sample")
            probs = masked_logits.softmax(dim=1)
            dense_target = None
            element_valid = valid.unsqueeze(1) & active_view
        else:
            mask_inactive(logits, active)  # validates mask shape and non-empty samples
            masked_logits = logits
            dense_target, element_valid = _sigmoid_target(target, logits, self.ignore_index)
            element_valid &= active_view
            valid = element_valid.any(dim=1)
            probs = logits.sigmoid()

        if any(term.kind == "kl_distillation" for term in self.cfg.terms):
            if teacher_logits is None:
                raise ValueError(
                    "kl_distillation is configured but teacher_logits was not provided"
                )
            if teacher_logits.shape != logits.shape:
                raise ValueError(
                    f"teacher_logits must exactly match student logits {tuple(logits.shape)}, "
                    f"got {tuple(teacher_logits.shape)}"
                )
            if not teacher_logits.is_floating_point():
                raise ValueError("teacher_logits must use a floating dtype")
            if not bool(torch.isfinite(teacher_logits).all()):
                raise FloatingPointError("teacher_logits contains non-finite values")

        if not bool(valid.any()):
            zero = _graph_zero(original_logits)
            components = {term.kind: zero.detach() for term in self.cfg.terms}
            components.update(total=zero.detach(), empty_crop=zero.detach() + 1)
            return zero, components

        components: dict[str, Tensor] = {}
        total = _graph_zero(original_logits)
        for term in self.cfg.terms:
            value = self._term(
                term,
                masked_logits,
                probs,
                target,
                dense_target,
                valid,
                element_valid,
                active_view,
                teacher_logits,
            )
            if not bool(torch.isfinite(value).all()):
                raise FloatingPointError(
                    f"loss term {term.kind!r} produced a non-finite value; "
                    "check logits, targets, and objective hyperparameters"
                )
            components[term.kind] = value.detach()
            total = total + term.weight * value
        if not bool(torch.isfinite(total).all()):
            raise FloatingPointError("weighted loss total is non-finite")
        components["total"] = total.detach()
        return total, components

    def _term(
        self,
        term: LossTermSpec,
        logits: Tensor,
        probs: Tensor,
        target: Tensor,
        dense_target: Tensor | None,
        valid: Tensor,
        element_valid: Tensor,
        active_view: Tensor,
        teacher_logits: Tensor | None,
    ) -> Tensor:
        if term.kind == "cross_entropy":
            pixels, denominator = _cross_entropy_pixels(
                logits,
                target,
                valid,
                active_view,
                label_smoothing=term.label_smoothing,
                class_weights=term.class_weights,
            )
            return pixels.sum() / denominator.clamp_min(1e-12)

        if term.kind == "binary_cross_entropy":
            assert dense_target is not None
            pos_weight = (
                torch.tensor(term.pos_weights, dtype=logits.dtype, device=logits.device).view(
                    1, -1, 1, 1
                )
                if term.pos_weights is not None
                else None
            )
            raw = F.binary_cross_entropy_with_logits(
                logits, dense_target, pos_weight=pos_weight, reduction="none"
            )
            return raw[element_valid].mean()

        if term.kind == "ohem_cross_entropy":
            raw, _ = _cross_entropy_pixels(
                logits,
                target,
                valid,
                active_view,
                label_smoothing=term.label_smoothing,
                class_weights=term.class_weights,
            )
            keep = min(raw.numel(), max(term.min_kept, int(raw.numel() * term.fraction)))
            if term.probability_threshold is not None:
                flat_target = target[valid]
                true_prob = (
                    probs.permute(0, 2, 3, 1)[valid].gather(1, flat_target.unsqueeze(1)).squeeze(1)
                )
                hard = raw[true_prob < term.probability_threshold]
                if hard.numel() >= keep:
                    return hard.mean()
            return raw.topk(keep, largest=True).values.mean()

        if term.kind == "focal":
            if self.cfg.task == "multiclass":
                flat_probs, flat_target = _multiclass_vectors(
                    probs, target, valid, self.num_classes
                )
                pt = flat_probs.gather(1, flat_target[:, None]).squeeze(1).clamp_min(1e-7)
                alpha = 1.0
                if isinstance(term.alpha, (int, float)):
                    alpha = float(term.alpha)
                elif isinstance(term.alpha, list):
                    alpha = torch.tensor(term.alpha, dtype=pt.dtype, device=pt.device)[flat_target]
                return (-(1.0 - pt).pow(term.gamma) * pt.log() * alpha).mean()
            assert dense_target is not None
            bce = F.binary_cross_entropy_with_logits(logits, dense_target, reduction="none")
            pt = torch.where(dense_target > 0.5, probs, 1.0 - probs)
            alpha_factor: Tensor | float = 1.0
            if isinstance(term.alpha, (int, float)):
                alpha_factor = torch.where(
                    dense_target > 0.5,
                    torch.full_like(probs, float(term.alpha)),
                    torch.full_like(probs, 1.0 - float(term.alpha)),
                )
            elif isinstance(term.alpha, list):
                alpha_factor = torch.tensor(
                    term.alpha, dtype=logits.dtype, device=logits.device
                ).view(1, -1, 1, 1)
            return (bce * (1.0 - pt).pow(term.gamma) * alpha_factor)[element_valid].mean()

        if self.cfg.task == "multiclass":
            dense_target = _multiclass_onehot(target, valid, self.num_classes, probs.dtype)
        assert dense_target is not None

        selected = (active_view.expand_as(probs) & element_valid).clone()
        channel_start = 0 if getattr(term, "include_background", True) else 1
        if channel_start:
            selected[:, 0] = False
        reduce_dims = (0, 2, 3)
        present = (dense_target * selected).sum(reduce_dims) > 0
        channel_mask = active_view[:, :, 0, 0].any(0)
        if getattr(term, "present_only", False):
            channel_mask &= present
        if channel_start:
            channel_mask[0] = False
        if not bool(channel_mask.any()):
            return _graph_zero(logits)

        if term.kind in ("dice", "jaccard", "tversky"):
            pred = probs * selected
            truth = dense_target * selected
            tp = (pred * truth).sum(reduce_dims)
            fp = (pred * (1.0 - truth)).sum(reduce_dims)
            fn = ((1.0 - pred) * truth * selected).sum(reduce_dims)
            if term.kind == "dice":
                score = (2.0 * tp + term.smooth) / (2.0 * tp + fp + fn + term.smooth)
            elif term.kind == "jaccard":
                score = (tp + term.smooth) / (tp + fp + fn + term.smooth)
            else:
                score = (tp + term.smooth) / (tp + term.alpha * fp + term.beta * fn + term.smooth)
            return 1.0 - score[channel_mask].mean()

        if term.kind == "lovasz":
            losses = []
            for c in torch.where(channel_mask)[0].tolist():
                pixel_mask = selected[:, c]
                fg = dense_target[:, c][pixel_mask]
                error = (fg - probs[:, c][pixel_mask]).abs()
                error_sorted, perm = torch.sort(error, descending=True)
                losses.append(torch.dot(error_sorted, lovasz_grad(fg[perm])))
            return torch.stack(losses).mean()

        if term.kind == "boundary":
            boundary_valid = element_valid.to(probs.dtype)
            # Stop ignored/inactive values from entering neighboring max-pool
            # windows before masking the output. Otherwise an ignored pixel can
            # still receive gradient through an adjacent valid contour.
            boundary_input = probs * boundary_valid
            pred_boundary = _soft_boundary(boundary_input, term.width) * boundary_valid
            target_boundary = _soft_boundary(dense_target, term.width) * boundary_valid
            inter = (pred_boundary * target_boundary).sum(reduce_dims)
            denom = pred_boundary.sum(reduce_dims) + target_boundary.sum(reduce_dims)
            score = (2.0 * inter + term.smooth) / (denom + term.smooth)
            return 1.0 - score[channel_mask].mean()

        if term.kind == "hausdorff":
            # Distance maps are target-derived constants. Weighting squared
            # prediction error by distance to both masks is the differentiable
            # distance-transform surrogate of Karimi & Salcudean (2019).
            selection_float = selected.to(probs.dtype)
            truth = dense_target.detach() * selection_float
            pred_mask = (probs.detach() > 0.5).to(probs.dtype) * selection_float
            truth_dt = _truncated_distance_to_foreground(truth, term.max_distance)
            pred_dt = _truncated_distance_to_foreground(pred_mask, term.max_distance)
            weights = truth_dt.pow(term.power) + pred_dt.pow(term.power)
            error = (probs - truth).square() * weights * selected
            per_channel = error.sum(reduce_dims) / selected.sum(reduce_dims).clamp_min(1)
            return per_channel[channel_mask].mean()

        if term.kind == "kl_distillation":
            assert teacher_logits is not None
            teacher = teacher_logits.detach() if term.detach_teacher else teacher_logits
            if teacher.dtype not in (torch.float32, torch.float64):
                teacher = teacher.float()
            temperature = term.temperature
            if self.cfg.task == "multiclass":
                teacher = teacher.masked_fill(~active_view, torch.finfo(teacher.dtype).min)
                raw = F.kl_div(
                    F.log_softmax(logits / temperature, dim=1),
                    F.softmax(teacher / temperature, dim=1),
                    reduction="none",
                ).sum(1)
                return raw[valid].mean() * temperature**2
            student_prob = torch.sigmoid(logits / temperature).clamp(1e-7, 1 - 1e-7)
            teacher_prob = torch.sigmoid(teacher / temperature).clamp(1e-7, 1 - 1e-7)
            raw = teacher_prob * (teacher_prob.log() - student_prob.log()) + (1 - teacher_prob) * (
                (1 - teacher_prob).log() - (1 - student_prob).log()
            )
            return raw[element_valid].mean() * temperature**2

        raise AssertionError(f"unhandled validated loss term {term.kind!r}")
