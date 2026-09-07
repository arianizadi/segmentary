"""Hungarian instance/panoptic loss without collapsing objects into classes.

Each non-crowd object or stuff region is a separate matching target. In
particular, two objects with the same category require two different queries.
This objective is independent of the semantic training engine and its config.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from scipy.optimize import linear_sum_assignment
from torch import Tensor, nn

from ..engine.query_loss import (
    _deterministic_points,
    _graph_zero,
    _pairwise_mask_costs,
    _resize_masks,
    _validate_prediction_tensors,
)
from ..models.outputs import QueryOutput, QueryPrediction
from .data import ObjectTarget


@dataclass(frozen=True)
class _MatchTarget:
    class_ids: Tensor
    masks: Tensor
    valid: Tensor


class ObjectQueryLoss(nn.Module):
    """Match queries to individual annotated segments and supervise their masks.

    ``num_points`` samples pixels for Hungarian matching only; one positive
    anchor per segment is also included so small objects are not all sampled
    as background. Matching interpolates only those points, avoiding a full
    resolution allocation for every query. Matched-mask BCE and Dice supervise
    every valid pixel. Set ``num_points=None`` for full-resolution matching.
    Unmatched queries learn the final no-object class. Crowd/void pixels do not
    contribute mask loss, and fully ignored images contribute no loss at all.
    Auxiliary decoder layers are independently matched and added with
    ``auxiliary_weight``. Input targets must already be on the model's device.
    """

    def __init__(
        self,
        num_classes: int,
        *,
        class_weight: float = 2.0,
        mask_weight: float = 5.0,
        dice_weight: float = 5.0,
        no_object_weight: float = 0.1,
        num_points: int | None = 1024,
        auxiliary_weight: float = 1.0,
    ) -> None:
        super().__init__()
        if isinstance(num_classes, bool) or not isinstance(num_classes, int) or num_classes < 1:
            raise ValueError("num_classes must be a positive integer")
        for name, value in (
            ("class_weight", class_weight),
            ("mask_weight", mask_weight),
            ("dice_weight", dice_weight),
            ("auxiliary_weight", auxiliary_weight),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if class_weight + mask_weight + dice_weight <= 0:
            raise ValueError("at least one matching/loss weight must be positive")
        if not math.isfinite(no_object_weight) or no_object_weight <= 0:
            raise ValueError("no_object_weight must be finite and positive")
        if num_points is not None and (
            isinstance(num_points, bool) or not isinstance(num_points, int) or num_points < 1
        ):
            raise ValueError("num_points must be a positive integer or None")
        self.num_classes = num_classes
        self.class_weight = class_weight
        self.mask_weight = mask_weight
        self.dice_weight = dice_weight
        self.no_object_weight = no_object_weight
        self.num_points = num_points
        self.auxiliary_weight = auxiliary_weight

    def forward(self, output: QueryOutput, targets: Sequence[ObjectTarget]) -> Tensor:
        if not isinstance(output, QueryOutput):
            raise TypeError("object query loss requires QueryOutput")
        if not isinstance(targets, (list, tuple)):
            raise TypeError("object targets must be a list or tuple of ObjectTarget values")
        predictions = (output.primary, *output.auxiliary)
        device = output.primary.class_logits.device
        batch_size = output.primary.class_logits.shape[0]
        if len(targets) != batch_size:
            raise ValueError(f"received {len(targets)} targets for batch size {batch_size}")
        for index, prediction in enumerate(predictions):
            _validate_prediction_tensors(prediction, where=f"object query layer {index}")
            if prediction.class_logits.device != device:
                raise ValueError("all object query layers must share one device")
            if prediction.class_logits.shape[-1] != self.num_classes + 1:
                raise ValueError(
                    f"object query logits need {self.num_classes + 1} class columns "
                    "including no-object"
                )
        prepared = tuple(self._prepare_target(target, device) for target in targets)
        query_count = output.primary.class_logits.shape[1]
        for index, target in enumerate(prepared):
            if target.class_ids.numel() > query_count:
                raise ValueError(
                    f"sample {index} has {target.class_ids.numel()} non-crowd segments "
                    f"but only {query_count} queries; every segment needs a separate query"
                )
        if not any(bool(target.valid.any()) for target in prepared):
            return sum(
                (
                    _graph_zero(prediction.class_logits) + _graph_zero(prediction.mask_logits)
                    for prediction in predictions
                ),
                output.primary.class_logits.new_zeros(()),
            )
        loss = self._prediction_loss(output.primary, prepared)
        if self.auxiliary_weight:
            for prediction in output.auxiliary:
                loss = loss + self.auxiliary_weight * self._prediction_loss(prediction, prepared)
        if not bool(torch.isfinite(loss)):
            raise FloatingPointError("object query loss is non-finite")
        return loss

    def _prepare_target(self, target: ObjectTarget, device: torch.device) -> _MatchTarget:
        if not isinstance(target, ObjectTarget):
            raise TypeError("object targets must contain ObjectTarget values")
        classes, masks, valid, crowd = (
            target.class_ids,
            target.masks,
            target.valid,
            target.iscrowd,
        )
        if classes.ndim != 1 or classes.dtype != torch.long:
            raise ValueError("target class_ids must be one-dimensional torch.long")
        if masks.ndim != 3 or masks.shape[0] != classes.numel():
            raise ValueError("target masks must have shape (M,H,W)")
        if valid.ndim != 2 or valid.dtype != torch.bool or valid.shape != masks.shape[-2:]:
            raise ValueError("target valid must be bool with the masks' spatial shape")
        if valid.numel() == 0:
            raise ValueError("target masks cannot have an empty spatial dimension")
        if crowd.dtype != torch.bool or crowd.shape != classes.shape:
            raise ValueError("target iscrowd must be bool with shape (M,)")
        if any(tensor.device != device for tensor in (classes, masks, valid, crowd)):
            raise ValueError("object target tensors and predictions must share one device")
        if bool(((classes < 0) | (classes >= self.num_classes)).any()):
            raise ValueError(f"target class IDs must be in [0, {self.num_classes - 1}]")
        if not bool(torch.isfinite(masks).all()) or bool(((masks != 0) & (masks != 1)).any()):
            raise ValueError("target masks must contain finite binary 0/1 values")
        # Dataset readers already exclude crowds, but enforce the contract for
        # callers constructing targets directly as well. Do not mutate inputs.
        if bool(crowd.any()):
            valid = valid & ~masks[crowd].bool().any(dim=0)
        retained = ~crowd & (masks.bool() & valid.unsqueeze(0)).flatten(1).any(dim=1)
        return _MatchTarget(classes[retained], masks[retained], valid)

    def _match(
        self, class_logits: Tensor, masks: Tensor, target: _MatchTarget
    ) -> tuple[Tensor, Tensor]:
        with torch.no_grad():
            class_cost = -class_logits.log_softmax(dim=-1)[:, target.class_ids]
            if self.num_points is None:
                sampled_masks = _resize_masks(masks, target.valid.shape)
                sampled_truth = target.masks
                sampled_valid = target.valid
            else:
                points = _deterministic_points(target.valid, self.num_points)
                anchors = torch.stack(
                    [
                        (mask * target.valid).to(torch.float32).flatten().argmax()
                        for mask in target.masks
                    ]
                )
                points = torch.unique(torch.cat((points, anchors)), sorted=True)
                height, width = target.valid.shape
                x = ((points % width).float() + 0.5) * (2 / width) - 1
                y = (torch.div(points, width, rounding_mode="floor").float() + 0.5) * (
                    2 / height
                ) - 1
                grid = torch.stack((x, y), dim=-1).view(1, 1, -1, 2)
                sampled_masks = F.grid_sample(
                    masks.unsqueeze(0),
                    grid,
                    mode="bilinear",
                    padding_mode="border",
                    align_corners=False,
                ).squeeze(0)
                sampled_truth = target.masks.flatten(1)[:, points].unsqueeze(1)
                sampled_valid = torch.ones(
                    (1, points.numel()), device=points.device, dtype=torch.bool
                )
            bce_cost, dice_cost = _pairwise_mask_costs(
                sampled_masks,
                sampled_truth,
                sampled_valid,
                num_points=None,
                dice_smooth=1.0,
            )
            cost = (
                self.class_weight * class_cost
                + self.mask_weight * bce_cost
                + self.dice_weight * dice_cost
            )
            if not bool(torch.isfinite(cost).all()):
                raise FloatingPointError("object Hungarian matching cost is non-finite")
            queries, objects = linear_sum_assignment(
                cost.to(device="cpu", dtype=torch.float64).numpy()
            )
        return (
            torch.as_tensor(queries, device=class_logits.device, dtype=torch.long),
            torch.as_tensor(objects, device=class_logits.device, dtype=torch.long),
        )

    def _prediction_loss(
        self, prediction: QueryPrediction, targets: tuple[_MatchTarget, ...]
    ) -> Tensor:
        zero = _graph_zero(prediction.class_logits) + _graph_zero(prediction.mask_logits)
        class_losses: list[Tensor] = []
        mask_losses: list[Tensor] = []
        dice_losses: list[Tensor] = []
        with torch.autocast(device_type=prediction.class_logits.device.type, enabled=False):
            all_classes = prediction.class_logits.float()
            all_masks = prediction.mask_logits.float()
            class_weights = all_classes.new_ones(self.num_classes + 1)
            class_weights[-1] = self.no_object_weight
            for index, target in enumerate(targets):
                if not bool(target.valid.any()):
                    continue
                classes = all_classes[index]
                class_target = torch.full(
                    (classes.shape[0],), self.num_classes, device=classes.device, dtype=torch.long
                )
                if target.class_ids.numel():
                    # Matching uses no autograd; resize only assigned masks on
                    # the gradient path, bounding full-resolution graph memory.
                    queries, objects = self._match(
                        classes.detach(), all_masks[index].detach(), target
                    )
                    class_target[queries] = target.class_ids[objects]
                    masks = _resize_masks(all_masks[index][queries], target.valid.shape)[
                        :, target.valid
                    ]
                    truth = target.masks[objects][:, target.valid].to(masks.dtype)
                    mask_losses.append(F.binary_cross_entropy_with_logits(masks, truth))
                    probabilities = masks.sigmoid()
                    intersection = (probabilities * truth).sum(dim=1)
                    denominator = probabilities.sum(dim=1) + truth.sum(dim=1)
                    dice_losses.append((1 - (2 * intersection + 1) / (denominator + 1)).mean())
                class_losses.append(F.cross_entropy(classes, class_target, weight=class_weights))
        classification = torch.stack(class_losses).mean() if class_losses else zero
        mask = torch.stack(mask_losses).mean() if mask_losses else zero
        dice = torch.stack(dice_losses).mean() if dice_losses else zero
        return (
            self.class_weight * classification + self.mask_weight * mask + self.dice_weight * dice
        )
