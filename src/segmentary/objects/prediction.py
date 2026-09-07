"""Decode query masks without collapsing distinct objects into semantic classes."""

from __future__ import annotations

import math
from typing import Any

import torch
from torch.nn import functional as F

from segmentary.models.outputs import QueryPrediction


def _threshold(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and between 0 and 1")


@torch.no_grad()
def postprocess(
    prediction: QueryPrediction,
    task: str,
    thing_ids: set[int],
    sizes: list[tuple[int, int]],
    score_threshold: float = 0.5,
    mask_threshold: float = 0.5,
    overlap_threshold: float = 0.8,
) -> list[dict[str, Any]]:
    """Return original-size instance masks or a disjoint panoptic segmentation.

    Classes are contiguous training IDs; the final classifier column means no
    object. An instance keeps one query's identity, including disconnected mask
    regions. Its score is class probability times mean foreground probability.
    Panoptic pixels are assigned by class-probability-weighted mask confidence;
    queries retaining too little of their original foreground are discarded.
    Stuff queries of one class are merged, while thing queries remain separate.
    Segment ID zero is void, independent of category ID zero.
    """
    if not isinstance(prediction, QueryPrediction):
        raise TypeError("object postprocessing requires a QueryPrediction")
    if task not in {"instance", "panoptic"}:
        raise ValueError("task must be 'instance' or 'panoptic'")
    for name, value in (
        ("score_threshold", score_threshold),
        ("mask_threshold", mask_threshold),
        ("overlap_threshold", overlap_threshold),
    ):
        _threshold(name, value)
    classes = prediction.class_logits.shape[-1] - 1
    if not isinstance(thing_ids, (set, frozenset)) or any(
        type(value) is not int or not 0 <= value < classes for value in thing_ids
    ):
        raise ValueError("thing_ids must contain valid contiguous class IDs")
    if len(sizes) != prediction.class_logits.shape[0] or any(
        len(size) != 2 or any(type(value) is not int or value < 1 for value in size)
        for size in sizes
    ):
        raise ValueError("sizes must provide positive (height, width) for every batch item")
    if prediction.class_logits.device != prediction.mask_logits.device:
        raise ValueError("class and mask logits must be on the same device")
    for logits in (prediction.class_logits, prediction.mask_logits):
        if not logits.is_floating_point() or not torch.isfinite(logits).all():
            raise ValueError("query logits must be finite floating point tensors")

    confidence, labels = prediction.class_logits.float().softmax(-1).max(-1)
    outputs: list[dict[str, Any]] = []
    for batch, size in enumerate(sizes):
        keep = (labels[batch] != classes) & (confidence[batch] >= score_threshold)
        if task == "instance":
            keep &= torch.tensor(
                [int(label) in thing_ids for label in labels[batch]],
                device=keep.device,
                dtype=torch.bool,
            )
        class_ids = labels[batch, keep]
        scores = confidence[batch, keep]
        if not keep.any():
            masks = torch.empty((0, *size), dtype=torch.bool, device=keep.device)
            probabilities = torch.empty((0, *size), device=keep.device)
        else:
            probabilities = F.interpolate(
                prediction.mask_logits[batch, keep, None].float(),
                size=size,
                mode="bilinear",
                align_corners=False,
            )[:, 0].sigmoid()
            masks = probabilities >= mask_threshold

        if task == "instance":
            area = masks.flatten(1).sum(1)
            scores = scores * (probabilities * masks).flatten(1).sum(1) / area.clamp_min(1)
            keep_nonempty = area > 0
            order = scores[keep_nonempty].argsort(descending=True, stable=True)
            outputs.append(
                {
                    "masks": masks[keep_nonempty][order],
                    "class_ids": class_ids[keep_nonempty][order],
                    "scores": scores[keep_nonempty][order],
                }
            )
            continue

        segmentation = torch.zeros(size, dtype=torch.long, device=keep.device)
        segments: list[dict[str, Any]] = []
        stuff: dict[int, int] = {}
        if len(scores):
            # argmax resolves exact ties by original query order, deterministically.
            assignment = (scores[:, None, None] * probabilities).argmax(0)
            for query, (category, score) in enumerate(zip(class_ids, scores, strict=True)):
                foreground = masks[query]
                region = (assignment == query) & foreground
                region_area, original_area = int(region.sum()), int(foreground.sum())
                if (
                    not region_area
                    or not original_area
                    or region_area / original_area < overlap_threshold
                ):
                    continue
                category_id = int(category)
                isthing = category_id in thing_ids
                if not isthing and category_id in stuff:
                    segment_id = stuff[category_id]
                    segmentation[region] = segment_id
                    # Max confidence describes the merged stuff class, not another instance.
                    segments[segment_id - 1]["score"] = max(
                        segments[segment_id - 1]["score"], float(score)
                    )
                    continue
                segment_id = len(segments) + 1
                segmentation[region] = segment_id
                segments.append(
                    {
                        "id": segment_id,
                        "category_id": category_id,
                        "isthing": isthing,
                        "score": float(score),
                    }
                )
                if not isthing:
                    stuff[category_id] = segment_id
        outputs.append({"segmentation": segmentation, "segments_info": segments})
    return outputs
