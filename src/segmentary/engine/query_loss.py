"""Native Hungarian set-prediction objective for semantic mask classification.

The engine receives one semantic index map and derives one binary target mask
for each present canonical class.  It never asks a third-party model to compute
its private loss: matching, ignore handling, inactive-class masking, reduction,
and auxiliary decoder supervision are all explicit Segmentary contracts.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn.functional as F
from scipy.optimize import linear_sum_assignment
from torch import Tensor, nn

from ..config import QueryLossSpec
from ..models.outputs import QueryOutput, QueryPrediction, SegmentationOutput


def _graph_zero(tensor: Tensor) -> Tensor:
    """Return an exact graph-connected zero without reading tensor values."""
    return tensor[:0].sum()


def _validate_prediction_tensors(prediction: QueryPrediction, *, where: str) -> None:
    if (
        not prediction.class_logits.is_floating_point()
        or not prediction.mask_logits.is_floating_point()
    ):
        raise TypeError(f"{where} class_logits and mask_logits must use floating dtypes")
    if prediction.class_logits.device != prediction.mask_logits.device:
        raise ValueError(f"{where} class_logits and mask_logits must share one device")
    if not bool(torch.isfinite(prediction.class_logits).all()) or not bool(
        torch.isfinite(prediction.mask_logits).all()
    ):
        raise FloatingPointError(f"{where} contains non-finite class or mask logits")


@dataclass(frozen=True)
class SemanticMaskTarget:
    """One image's set target plus the pixels on which masks are supervised."""

    class_ids: Tensor  # (M,), canonical class ids
    masks: Tensor  # (M, H, W), float binary masks
    valid: Tensor  # (H, W), false exactly at ignore_index

    def __post_init__(self) -> None:
        if self.class_ids.ndim != 1:
            raise ValueError("semantic mask target class_ids must be one-dimensional")
        if self.masks.ndim != 3 or self.masks.shape[0] != self.class_ids.numel():
            raise ValueError("semantic mask target masks must have shape (M,H,W)")
        if self.valid.ndim != 2 or self.masks.shape[-2:] != self.valid.shape:
            raise ValueError("semantic mask target valid mask must match mask spatial size")
        if self.class_ids.dtype != torch.long:
            raise ValueError("semantic mask target class_ids must use torch.long")
        if self.valid.dtype != torch.bool:
            raise ValueError("semantic mask target valid mask must use torch.bool")
        if not self.masks.is_floating_point():
            raise ValueError("semantic mask target masks must use a floating dtype")
        if not (self.class_ids.device == self.masks.device == self.valid.device):
            raise ValueError("semantic mask target tensors must share one device")
        if bool((self.class_ids < 0).any()):
            raise ValueError("semantic mask target class_ids cannot be negative")
        if self.class_ids.numel() > 1 and not bool(
            (self.class_ids[1:] > self.class_ids[:-1]).all()
        ):
            raise ValueError("semantic mask target class_ids must be unique and sorted")
        if not bool(torch.isfinite(self.masks).all()) or bool(
            ((self.masks != 0) & (self.masks != 1)).any()
        ):
            raise ValueError("semantic mask target masks must contain only finite 0/1 values")


def _active_rows(
    active: Tensor | None,
    batch_size: int,
    num_classes: int,
    device: torch.device,
) -> Tensor:
    if active is not None and not isinstance(active, Tensor):
        raise TypeError(f"active mask must be a Tensor or None, got {type(active).__name__}")
    if active is None:
        rows = torch.ones((batch_size, num_classes), dtype=torch.bool, device=device)
    elif active.ndim == 1:
        if active.shape != (num_classes,):
            raise ValueError(
                f"active mask {tuple(active.shape)} does not match {num_classes} classes"
            )
        rows = active.to(device=device, dtype=torch.bool).view(1, -1).expand(batch_size, -1)
    elif active.ndim == 2:
        if active.shape != (batch_size, num_classes):
            raise ValueError(
                f"per-sample active mask {tuple(active.shape)} does not match batch "
                f"({batch_size}, {num_classes})"
            )
        rows = active.to(device=device, dtype=torch.bool)
    else:
        raise ValueError(f"active mask must be 1-D (C,) or 2-D (N,C), got {active.ndim}-D")
    if not bool(rows.any(dim=1).all()):
        raise ValueError("active mask excludes every canonical class for a sample")
    return rows


def semantic_targets_from_dense(
    target: Tensor,
    *,
    num_classes: int,
    ignore_index: int,
    active: Tensor | None = None,
) -> tuple[SemanticMaskTarget, ...]:
    """Convert ``(N,H,W)`` labels into one mask per present active class.

    Classes are sorted by canonical id, making matching inputs reproducible.
    An inactive labelled pixel is an error rather than silently becoming void.
    """
    if not isinstance(target, Tensor):
        raise TypeError(f"query targets must be a Tensor, got {type(target).__name__}")
    if target.ndim != 3:
        raise ValueError(f"query targets must have shape (N,H,W), got {tuple(target.shape)}")
    if target.shape[0] < 1 or target.shape[1] < 1 or target.shape[2] < 1:
        raise ValueError("query targets cannot have an empty batch or spatial dimension")
    if target.dtype == torch.bool or target.is_floating_point() or target.is_complex():
        raise ValueError("query targets must use an integer class-index dtype")

    target = target.long()
    rows = _active_rows(active, target.shape[0], num_classes, target.device)
    converted: list[SemanticMaskTarget] = []
    for sample_index in range(target.shape[0]):
        labels = target[sample_index]
        valid = labels != ignore_index
        valid_labels = labels[valid]
        if valid_labels.numel():
            if bool(((valid_labels < 0) | (valid_labels >= num_classes)).any()):
                raise ValueError(
                    f"query targets must be in [0, {num_classes - 1}] or "
                    f"ignore_index={ignore_index}"
                )
            if not bool(rows[sample_index, valid_labels].all()):
                raise ValueError("target contains a class marked inactive for that sample")
            class_ids = torch.unique(valid_labels, sorted=True)
            masks = torch.stack([(labels == class_id) & valid for class_id in class_ids], dim=0).to(
                torch.float32
            )
        else:
            class_ids = torch.empty(0, dtype=torch.long, device=target.device)
            masks = torch.empty(
                (0, labels.shape[0], labels.shape[1]),
                dtype=torch.float32,
                device=target.device,
            )
        converted.append(SemanticMaskTarget(class_ids=class_ids, masks=masks, valid=valid))
    return tuple(converted)


def _deterministic_points(valid: Tensor, count: int | None) -> Tensor:
    indices = torch.nonzero(valid.reshape(-1), as_tuple=False).flatten()
    if count is None or indices.numel() <= count:
        return indices
    if count == 1:
        return indices[indices.numel() // 2].view(1)
    # Evenly cover the ordered valid-pixel population, including both ends.
    positions = torch.div(
        torch.arange(count, device=indices.device) * (indices.numel() - 1),
        count - 1,
        rounding_mode="floor",
    )
    return indices[positions]


def _resize_masks(mask_logits: Tensor, size: tuple[int, ...]) -> Tensor:
    """Resize to a spatial (H, W); callers pass a tensor ``.shape`` directly."""
    if tuple(mask_logits.shape[-2:]) == tuple(size):
        return mask_logits
    return F.interpolate(
        mask_logits.unsqueeze(1), size=size, mode="bilinear", align_corners=False
    ).squeeze(1)


def _pairwise_mask_costs(
    prediction: Tensor,
    target: Tensor,
    valid: Tensor,
    *,
    num_points: int | None,
    dice_smooth: float,
) -> tuple[Tensor, Tensor]:
    """Return memory-bounded sigmoid BCE and soft-Dice matrices of shape Q x M."""
    points = _deterministic_points(valid, num_points)
    if points.numel() == 0:
        if target.shape[0] != 0:
            raise ValueError("non-empty mask targets have no supervised pixels")
        empty = prediction.new_empty((prediction.shape[0], 0))
        return empty, empty
    pred = prediction.flatten(1)[:, points]
    truth = target.flatten(1)[:, points].to(dtype=pred.dtype)
    # BCE(x,t) = softplus(x) - x*t.  This QxM form avoids materialising QxMxP.
    bce = F.softplus(pred).mean(dim=1, keepdim=True) - pred @ truth.transpose(0, 1) / float(
        points.numel()
    )
    probs = pred.sigmoid()
    intersection = probs @ truth.transpose(0, 1)
    denominator = probs.sum(dim=1, keepdim=True) + truth.sum(dim=1).unsqueeze(0)
    dice = 1.0 - (2.0 * intersection + dice_smooth) / (denominator + dice_smooth)
    return bce, dice


def hungarian_match(
    prediction: QueryPrediction,
    targets: tuple[SemanticMaskTarget, ...],
    active: Tensor | None,
    spec: QueryLossSpec,
    *,
    num_classes: int,
) -> tuple[tuple[Tensor, Tensor], ...]:
    """Deterministically assign queries to targets with SciPy's exact solver."""
    _validate_prediction_tensors(prediction, where="query matching prediction")
    n, q, columns = prediction.class_logits.shape
    if columns != num_classes + 1:
        raise ValueError(
            f"query class logits have {columns} columns; expected {num_classes + 1} "
            "canonical classes plus no-object"
        )
    if len(targets) != n:
        raise ValueError(f"received {len(targets)} query targets for batch size {n}")
    rows = _active_rows(active, n, num_classes, prediction.class_logits.device)
    assignments: list[tuple[Tensor, Tensor]] = []
    with torch.autocast(device_type=prediction.class_logits.device.type, enabled=False):
        class_logits = prediction.class_logits.detach().float()
        mask_logits = prediction.mask_logits.detach().float()
        for sample_index, target in enumerate(targets):
            m = target.class_ids.numel()
            if m == 0:
                empty = torch.empty(0, dtype=torch.long, device=class_logits.device)
                assignments.append((empty, empty))
                continue
            if m > q:
                raise ValueError(
                    f"sample {sample_index} has {m} present classes but only {q} queries; "
                    "Hungarian matching cannot supervise every target"
                )
            if bool((target.class_ids >= num_classes).any()):
                raise ValueError(
                    f"sample {sample_index} query target contains a class outside "
                    f"[0, {num_classes - 1}]"
                )
            if not bool(rows[sample_index, target.class_ids].all()):
                raise ValueError(f"sample {sample_index} query target contains an inactive class")
            allowed = torch.cat(
                (rows[sample_index], torch.ones(1, dtype=torch.bool, device=rows.device))
            )
            masked = class_logits[sample_index].masked_fill(
                ~allowed.unsqueeze(0), torch.finfo(class_logits.dtype).min
            )
            class_cost = -masked.log_softmax(dim=-1)[:, target.class_ids]
            resized_masks = _resize_masks(mask_logits[sample_index], target.valid.shape)
            bce_cost, dice_cost = _pairwise_mask_costs(
                resized_masks.detach(),
                target.masks,
                target.valid,
                num_points=spec.matching_num_points,
                dice_smooth=spec.dice_smooth,
            )
            cost = (
                spec.match_class_cost * class_cost
                + spec.match_mask_bce_cost * bce_cost
                + spec.match_dice_cost * dice_cost
            )
            if not bool(torch.isfinite(cost).all()):
                raise FloatingPointError("Hungarian matching cost contains non-finite values")
            query_indices, target_indices = linear_sum_assignment(
                cost.detach().to(device="cpu", dtype=torch.float64).numpy()
            )
            assignments.append(
                (
                    torch.as_tensor(query_indices, dtype=torch.long, device=class_logits.device),
                    torch.as_tensor(target_indices, dtype=torch.long, device=class_logits.device),
                )
            )
    return tuple(assignments)


class QuerySegmentationLoss(nn.Module):
    """Hungarian class/BCE/Dice objective over raw query predictions."""

    def __init__(self, spec: QueryLossSpec, num_classes: int, ignore_index: int = 255) -> None:
        super().__init__()
        if num_classes < 2:
            raise ValueError("query multiclass segmentation requires at least two classes")
        self.spec = spec
        self.num_classes = num_classes
        self.ignore_index = ignore_index

    def forward(
        self,
        output: QueryOutput,
        target: Tensor,
        active: Tensor | None = None,
    ) -> tuple[Tensor, dict[str, Tensor]]:
        if not isinstance(output, QueryOutput):
            raise TypeError(f"query loss requires QueryOutput, got {type(output).__name__}")
        if not isinstance(target, Tensor):
            raise TypeError(f"query target must be a Tensor, got {type(target).__name__}")
        if active is not None and not isinstance(active, Tensor):
            raise TypeError(f"active mask must be a Tensor or None, got {type(active).__name__}")
        if target.device != output.primary.class_logits.device:
            raise ValueError(
                f"query target is on {target.device}, but predictions are on "
                f"{output.primary.class_logits.device}"
            )
        if active is not None and active.device != target.device:
            raise ValueError(
                f"active mask is on {active.device}, but query target is on {target.device}"
            )
        targets = semantic_targets_from_dense(
            target,
            num_classes=self.num_classes,
            ignore_index=self.ignore_index,
            active=active,
        )
        predictions = (output.primary, *output.auxiliary)
        self._validate_predictions(predictions, target.shape[0])

        # Void-only crops have no semantic supervision.  In particular, do not
        # teach every query to be no-object based solely on padding/ignore pixels.
        if not any(bool(item.valid.any()) for item in targets):
            zero = sum(
                (
                    _graph_zero(prediction.class_logits) + _graph_zero(prediction.mask_logits)
                    for prediction in predictions
                ),
                output.primary.class_logits.new_zeros(()),
            )
            return zero, {"total": zero.detach(), "empty_crop": zero.detach() + 1}

        total, primary_parts = self._prediction_loss(output.primary, targets, active)
        parts = {name: value.detach() for name, value in primary_parts.items()}
        if self.spec.auxiliary_layer_weight > 0.0:
            for layer_index, prediction in enumerate(output.auxiliary):
                layer_total, layer_parts = self._prediction_loss(prediction, targets, active)
                weighted = self.spec.auxiliary_layer_weight * layer_total
                total = total + weighted
                for name, value in layer_parts.items():
                    parts[f"aux/{layer_index}/{name}"] = value.detach()
                parts[f"aux/{layer_index}/weighted_loss"] = weighted.detach()
        if not bool(torch.isfinite(total).all()):
            raise FloatingPointError("weighted query loss total is non-finite")
        parts["total"] = total.detach()
        return total, parts

    def _validate_predictions(
        self, predictions: tuple[QueryPrediction, ...], batch_size: int
    ) -> None:
        expected_device = predictions[0].class_logits.device
        for layer_index, prediction in enumerate(predictions):
            if prediction.class_logits.device != expected_device:
                raise ValueError(
                    f"query layer {layer_index} is on {prediction.class_logits.device}; "
                    f"expected {expected_device}"
                )
            _validate_prediction_tensors(prediction, where=f"query layer {layer_index}")
            if prediction.class_logits.shape[0] != batch_size:
                raise ValueError(
                    f"query layer {layer_index} batch size {prediction.class_logits.shape[0]} "
                    f"does not match target batch size {batch_size}"
                )
            if prediction.class_logits.shape[-1] != self.num_classes + 1:
                raise ValueError(
                    f"query layer {layer_index} has {prediction.class_logits.shape[-1]} class "
                    f"columns; expected {self.num_classes + 1} including no-object"
                )

    def _prediction_loss(
        self,
        prediction: QueryPrediction,
        targets: tuple[SemanticMaskTarget, ...],
        active: Tensor | None,
    ) -> tuple[Tensor, dict[str, Tensor]]:
        assignments = hungarian_match(
            prediction,
            targets,
            active,
            self.spec,
            num_classes=self.num_classes,
        )
        rows = _active_rows(
            active,
            prediction.class_logits.shape[0],
            self.num_classes,
            prediction.class_logits.device,
        )
        class_losses: list[Tensor] = []
        bce_losses: list[Tensor] = []
        dice_losses: list[Tensor] = []
        with torch.autocast(device_type=prediction.class_logits.device.type, enabled=False):
            class_logits = prediction.class_logits.float()
            mask_logits = prediction.mask_logits.float()
            for sample_index, (target, assignment) in enumerate(
                zip(targets, assignments, strict=True)
            ):
                if not bool(target.valid.any()):
                    continue
                query_indices, target_indices = assignment
                allowed = torch.cat(
                    (rows[sample_index], torch.ones(1, dtype=torch.bool, device=rows.device))
                )
                masked_class_logits = class_logits[sample_index].masked_fill(
                    ~allowed.unsqueeze(0), torch.finfo(class_logits.dtype).min
                )
                class_target = torch.full(
                    (masked_class_logits.shape[0],),
                    self.num_classes,
                    dtype=torch.long,
                    device=masked_class_logits.device,
                )
                if query_indices.numel():
                    class_target[query_indices] = target.class_ids[target_indices]
                class_weights = torch.ones(
                    self.num_classes + 1,
                    dtype=masked_class_logits.dtype,
                    device=masked_class_logits.device,
                )
                class_weights[-1] = self.spec.no_object_coefficient
                class_losses.append(
                    F.cross_entropy(masked_class_logits, class_target, weight=class_weights)
                )

                if query_indices.numel():
                    # Bilinear interpolation treats every query plane
                    # independently. Select the matched queries first so a
                    # typical 15-mask target does not materialize all 200 EoMT
                    # query masks at full label resolution.
                    pred_masks = _resize_masks(
                        mask_logits[sample_index][query_indices], target.valid.shape
                    )[:, target.valid]
                    truth_masks = target.masks[target_indices][:, target.valid].to(
                        dtype=pred_masks.dtype
                    )
                    bce_losses.append(F.binary_cross_entropy_with_logits(pred_masks, truth_masks))
                    probabilities = pred_masks.sigmoid()
                    intersection = (probabilities * truth_masks).sum(dim=1)
                    denominator = probabilities.sum(dim=1) + truth_masks.sum(dim=1)
                    dice_losses.append(
                        (
                            1.0
                            - (2.0 * intersection + self.spec.dice_smooth)
                            / (denominator + self.spec.dice_smooth)
                        ).mean()
                    )

        graph_zero = _graph_zero(prediction.class_logits) + _graph_zero(prediction.mask_logits)
        class_loss = torch.stack(class_losses).mean() if class_losses else graph_zero
        bce_loss = torch.stack(bce_losses).mean() if bce_losses else graph_zero
        dice_loss = torch.stack(dice_losses).mean() if dice_losses else graph_zero
        total = (
            self.spec.classification_weight * class_loss
            + self.spec.mask_bce_weight * bce_loss
            + self.spec.dice_weight * dice_loss
        )
        components = {
            "classification": class_loss,
            "mask_bce": bce_loss,
            "dice": dice_loss,
        }
        return total, components


def query_training_objective(
    model: nn.Module,
    loss_fn: QuerySegmentationLoss,
    pixel_values: Tensor,
    target: Tensor,
    active: Tensor | None = None,
) -> tuple[Tensor, dict[str, Tensor]]:
    """Run the rich model path and reject dense/query objective mismatches."""
    forward_output = getattr(model, "forward_output", None)
    if not callable(forward_output):
        raise TypeError(
            f"{type(model).__name__} has no forward_output; a query objective requires raw "
            "QueryOutput rather than collapsed dense logits"
        )
    raw_output = forward_output(pixel_values)
    if not isinstance(raw_output, SegmentationOutput):
        raise TypeError(
            f"{type(model).__name__} training forward returned {type(raw_output).__name__}; "
            "expected SegmentationOutput containing raw query predictions"
        )
    if raw_output.query is None:
        raise ValueError(
            f"{type(model).__name__} returned dense predictions, but the configured objective "
            "is Hungarian query matching"
        )
    return loss_fn(raw_output.query, target, active=active)
