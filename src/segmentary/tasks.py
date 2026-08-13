"""Semantic-task contracts shared by training, inference, and evaluation.

Segmentary's taxonomy always describes canonical semantic classes. A binary
model is deliberately different from a two-channel multiclass model: it emits
one raw class-1 (positive) logit and reconstructs canonical ids 0/1 with a
sigmoid threshold. Keeping that conversion in one module prevents individual
callers from accidentally applying ``argmax`` to a one-channel tensor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import torch
from torch import Tensor

if TYPE_CHECKING:
    from .config import ExperimentConfig, LossTask
    from .taxonomy import LabelSpace

RunnableTask = Literal["multiclass", "binary"]


def validate_task_configuration(cfg: ExperimentConfig) -> RunnableTask:
    """Reject unsupported or contradictory model/objective task selections."""
    task = cfg.loss.task
    if task == "multilabel":
        raise ValueError(
            "loss.task='multilabel' has objective-level primitives but no standard "
            "dataset, inference, or evaluation contract yet; use multiclass or binary"
        )

    native = cfg.model.native if cfg.model.arch == "native" else None
    if native is not None and native.task != task:
        raise ValueError(
            f"model.native.task={native.task!r} does not match loss.task={task!r}; "
            "model output channels and target semantics must describe the same task"
        )
    if task == "binary" and cfg.model.arch != "native":
        raise ValueError(
            f"loss.task='binary' currently requires model.arch='native', got "
            f"{cfg.model.arch!r}; other wrappers still implement multiclass outputs only"
        )
    if cfg.model.arch == "native" and native is None:
        raise ValueError("arch='native' requires model.native")
    return task


def output_channels(task: LossTask | str, canonical_classes: int) -> int:
    """Map canonical taxonomy size to the model's dense output-channel count."""
    if task == "multiclass":
        if canonical_classes < 2:
            raise ValueError(
                f"multiclass segmentation needs at least two canonical classes, got "
                f"{canonical_classes}"
            )
        return canonical_classes
    if task == "binary":
        if canonical_classes != 2:
            raise ValueError(
                "binary segmentation requires exactly two canonical classes "
                f"(id 0 negative, id 1 positive), got {canonical_classes}"
            )
        return 1
    raise ValueError(
        f"task={task!r} has no end-to-end dense output contract; multilabel is not "
        "implemented by the standard data/evaluation pipeline"
    )


def validate_task_space(task: LossTask | str, space: LabelSpace) -> None:
    """Validate the canonical taxonomy semantics required by a runnable task."""
    expected_channels = output_channels(task, space.num_classes)
    if task == "binary":
        ids = tuple(item.id for item in space.classes)
        if ids != (0, 1):
            raise ValueError(
                "binary taxonomy must contain exactly canonical ids (0, 1), where id 1 "
                f"is the positive sigmoid/threshold class; got ids={ids}"
            )
        if expected_channels != 1:  # Defensive: output_channels owns this invariant.
            raise AssertionError("binary output channel contract drifted")


def validate_canonical_active(
    active: Tensor,
    task: LossTask | str,
    *,
    batch_size: int | None = None,
    where: str = "dataset active mask",
) -> None:
    """Validate canonical active-class supervision for the selected task.

    Binary negative/positive supervision cannot safely mask either class: with
    only one sigmoid channel, an unlabeled positive class is indistinguishable
    from a supervised negative. Every sample must therefore supervise both
    canonical ids before its active mask is collapsed to the one-logit loss.
    """
    if task == "multiclass":
        return
    if task != "binary":
        raise ValueError(f"{where}: task={task!r} has no active-mask conversion")
    if not isinstance(active, Tensor):
        raise TypeError(f"{where} must be a torch.Tensor, got {type(active).__name__}")
    if active.dtype != torch.bool:
        raise ValueError(f"{where} must use boolean canonical-class flags")
    if active.ndim == 1:
        if active.shape != (2,):
            raise ValueError(f"{where} must have canonical shape (2,), got {tuple(active.shape)}")
        rows = active.view(1, 2)
    elif active.ndim == 2:
        if batch_size is None:
            batch_size = int(active.shape[0])
        if active.shape != (batch_size, 2):
            raise ValueError(
                f"{where} must have per-sample canonical shape ({batch_size}, 2), got "
                f"{tuple(active.shape)}"
            )
        rows = active
    else:
        raise ValueError(f"{where} must be canonical (2,) or per-sample (N,2), got {active.ndim}-D")
    incomplete = ~rows.all(dim=1)
    if bool(incomplete.any()):
        indices = incomplete.nonzero(as_tuple=False).flatten().tolist()
        raise ValueError(
            f"{where}: binary segmentation requires both canonical classes to be "
            f"supervised for every sample; incomplete sample rows={indices[:8]}"
        )


def active_for_loss(
    active: Tensor | None,
    task: LossTask | str,
    *,
    batch_size: int,
) -> Tensor | None:
    """Convert canonical dataset active masks to model-output active channels."""
    if task == "multiclass":
        return active
    if task != "binary":
        raise ValueError(f"task={task!r} has no end-to-end active-mask conversion")
    if active is None:
        raise ValueError(
            "binary training requires the dataset's canonical active mask; refusing to "
            "assume that both the negative and positive classes are supervised"
        )
    validate_canonical_active(active, task, batch_size=batch_size)
    if active.ndim == 1:
        return torch.ones((1,), dtype=torch.bool, device=active.device)
    return torch.ones((batch_size, 1), dtype=torch.bool, device=active.device)


__all__ = [
    "RunnableTask",
    "active_for_loss",
    "output_channels",
    "validate_canonical_active",
    "validate_task_configuration",
    "validate_task_space",
]
