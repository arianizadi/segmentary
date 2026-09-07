"""Mask AP and panoptic quality, accumulated independently of semantic mIoU.

Protocols follow the official COCO all-area mask evaluator and panoptic API:
https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/cocoeval.py
https://github.com/cocodataset/panopticapi/blob/master/panopticapi/evaluation.py

AP uses .50:.05:.95 IoU, 101-point interpolated precision, and the 100 highest
scores per image/category. Crowd matching uses intersection / detection area
and permits repeated matches. No area-stratified AP or box AP is reported.
Pixel validity is an explicit extension: masks are clipped to valid pixels,
and detections entirely outside valid pixels are ignored. Standard COCO inputs
have all pixels valid. PQ uses strict IoU > .5, subtracts void overlap from the
union, and ignores unmatched predictions >50% covered by void/same-class crowd.

All numbers are fractions. Classes without evaluation support report None.
These accumulators are single-process; callers must combine predictions before
updating rather than averaging per-image or per-worker AP/PQ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import torch
from torch import Tensor


class _Target(Protocol):
    class_ids: Tensor
    masks: Tensor
    valid: Tensor
    iscrowd: Tensor
    image_id: int


def _class_set(num_classes: int, thing_ids: set[int] | None) -> set[int]:
    if type(num_classes) is not int or num_classes < 1:
        raise ValueError("num_classes must be a positive integer")
    if thing_ids is None:
        return set(range(num_classes))
    if not isinstance(thing_ids, (set, frozenset)) or any(
        type(value) is not int or not 0 <= value < num_classes for value in thing_ids
    ):
        raise ValueError("thing_ids must contain valid contiguous class IDs")
    return set(thing_ids)


def _cpu_tensor(value: Any, name: str, ndim: int, dtype: torch.dtype) -> Tensor:
    if not isinstance(value, Tensor) or value.ndim != ndim or value.dtype != dtype:
        raise ValueError(f"{name} must be a {ndim}-dimensional {dtype} tensor")
    return value.detach().cpu()


def _target_arrays(target: _Target, num_classes: int) -> tuple[Tensor, Tensor, Tensor, Tensor]:
    labels = _cpu_tensor(target.class_ids, "target class_ids", 1, torch.long)
    masks = _cpu_tensor(target.masks, "target masks", 3, torch.bool)
    valid = _cpu_tensor(target.valid, "target valid", 2, torch.bool)
    crowd = _cpu_tensor(target.iscrowd, "target iscrowd", 1, torch.bool)
    if len(labels) != len(masks) or len(crowd) != len(labels) or masks.shape[1:] != valid.shape:
        raise ValueError("target masks, classes, crowd and validity dimensions disagree")
    if not valid.numel() or ((labels < 0) | (labels >= num_classes)).any():
        raise ValueError("target dimensions or class IDs are invalid")
    masks = masks & valid
    if len(masks) and not masks.flatten(1).any(1).all():
        raise ValueError("target contains an empty object in valid pixels")
    return labels, masks, valid, crowd


def _instance_arrays(
    prediction: dict[str, Any], size: torch.Size, num_classes: int
) -> tuple[Tensor, Tensor, Tensor]:
    masks = _cpu_tensor(prediction.get("masks"), "prediction masks", 3, torch.bool)
    labels = _cpu_tensor(prediction.get("class_ids"), "prediction class_ids", 1, torch.long)
    scores = prediction.get("scores")
    if not isinstance(scores, Tensor) or scores.ndim != 1 or not scores.is_floating_point():
        raise ValueError("prediction scores must be a one-dimensional float tensor")
    scores = scores.detach().cpu().double()
    if len(labels) != len(masks) or len(labels) != len(scores) or masks.shape[1:] != size:
        raise ValueError("prediction masks, classes, scores or target dimensions disagree")
    if (
        ((labels < 0) | (labels >= num_classes)).any()
        or not torch.isfinite(scores).all()
        or ((scores < 0) | (scores > 1)).any()
    ):
        raise ValueError("prediction class IDs or confidence scores are invalid")
    if len(masks) and not masks.flatten(1).any(1).all():
        raise ValueError("prediction contains an empty mask")
    return labels, masks, scores


@dataclass
class _Detections:
    scores: np.ndarray
    matches: np.ndarray
    ignored: np.ndarray


class InstanceMetrics:
    """Streaming COCO all-area mask AP; only score/match vectors are retained."""

    thresholds = np.linspace(0.5, 0.95, 10)

    def __init__(self, num_classes: int, thing_ids: set[int] | None = None) -> None:
        self.thing_ids = _class_set(num_classes, thing_ids)
        self.num_classes = num_classes
        self.reset()

    def reset(self) -> None:
        self._detections: dict[int, list[_Detections]] = {value: [] for value in self.thing_ids}
        self._support = {value: 0 for value in self.thing_ids}
        self._images: set[int] = set()

    def update(self, prediction: dict[str, Any], target: _Target) -> None:
        if target.image_id in self._images:
            raise ValueError(f"image {target.image_id!r} was already evaluated")
        gt_labels, gt_masks, valid, crowd = _target_arrays(target, self.num_classes)
        labels, masks, scores = _instance_arrays(prediction, valid.shape, self.num_classes)
        if any(int(label) not in self.thing_ids for label in labels):
            raise ValueError("instance predictions must contain thing classes only")
        masks = masks & valid
        pending: dict[int, tuple[int, _Detections]] = {}
        for category in sorted(self.thing_ids):
            gt_keep = gt_labels == category
            gt = gt_masks[gt_keep]
            gt_crowd = crowd[gt_keep]
            # Non-crowd objects always take matching priority over crowd regions.
            gt_order = gt_crowd.to(torch.int64).argsort(stable=True)
            gt, gt_crowd = gt[gt_order], gt_crowd[gt_order]
            pred_keep = labels == category
            order = scores[pred_keep].argsort(descending=True, stable=True)[:100]
            pred, confidence = masks[pred_keep][order], scores[pred_keep][order]
            area = pred.flatten(1).sum(1).numpy().astype(np.float64)
            gt_area = gt.flatten(1).sum(1).numpy().astype(np.float64)
            intersections = np.zeros((len(pred), len(gt)), dtype=np.float64)
            # Work one mask at a time to avoid a D x G x H x W allocation.
            for index, region in enumerate(pred):
                intersections[index] = (gt & region).flatten(1).sum(1).numpy()
            denominator = area[:, None] + gt_area[None, :] - intersections
            crowd_array = gt_crowd.numpy()
            denominator[:, crowd_array] = area[:, None]
            ious = np.divide(
                intersections,
                denominator,
                out=np.zeros_like(intersections),
                where=denominator > 0,
            )
            matches = np.zeros((10, len(pred)), dtype=bool)
            ignored = np.broadcast_to(area == 0, matches.shape).copy()
            for threshold_index, threshold in enumerate(self.thresholds):
                gt_matched = np.zeros(len(gt), dtype=bool)
                for detection in range(len(pred)):
                    best, minimum = -1, float(threshold)
                    for truth in range(len(gt)):
                        if gt_matched[truth] and not crowd_array[truth]:
                            continue
                        if best >= 0 and not crowd_array[best] and crowd_array[truth]:
                            break
                        if ious[detection, truth] < minimum:
                            continue
                        best, minimum = truth, ious[detection, truth]
                    if best >= 0:
                        matches[threshold_index, detection] = True
                        ignored[threshold_index, detection] = crowd_array[best]
                        gt_matched[best] = True
            pending[category] = (
                int((~gt_crowd).sum()),
                _Detections(confidence.numpy(), matches, ignored),
            )
        for category, (support, detections) in pending.items():
            self._support[category] += support
            self._detections[category].append(detections)
        self._images.add(target.image_id)

    def compute(self) -> dict[str, Any]:
        per_class: dict[str, Any] = {}
        aps, recalls = [], []
        for category in sorted(self.thing_ids):
            support = self._support[category]
            if support == 0:
                per_class[str(category)] = {
                    "map": None,
                    "map_50": None,
                    "map_75": None,
                    "mar_100": None,
                    "support": 0,
                }
                continue
            detections = self._detections[category]
            scores = np.concatenate([item.scores for item in detections])
            order = np.argsort(-scores, kind="stable")
            matched = np.concatenate([item.matches for item in detections], axis=1)[:, order]
            ignored = np.concatenate([item.ignored for item in detections], axis=1)[:, order]
            true_positive = np.cumsum(matched & ~ignored, axis=1, dtype=np.float64)
            false_positive = np.cumsum(~matched & ~ignored, axis=1, dtype=np.float64)
            recall = true_positive / support
            precision = np.divide(
                true_positive,
                true_positive + false_positive,
                out=np.zeros_like(true_positive),
                where=(true_positive + false_positive) > 0,
            )
            interpolated = np.zeros((10, 101), dtype=np.float64)
            maximum_recall = np.zeros(10, dtype=np.float64)
            for threshold in range(10):
                if len(order) == 0:
                    continue
                envelope = np.maximum.accumulate(precision[threshold, ::-1])[::-1]
                indices = np.searchsorted(recall[threshold], np.linspace(0, 1, 101), side="left")
                available = indices < len(order)
                interpolated[threshold, available] = envelope[indices[available]]
                maximum_recall[threshold] = recall[threshold, -1]
            class_ap = interpolated.mean(1)
            aps.append(class_ap)
            recalls.append(maximum_recall)
            per_class[str(category)] = {
                "map": float(class_ap.mean()),
                "map_50": float(class_ap[0]),
                "map_75": float(class_ap[5]),
                "mar_100": float(maximum_recall.mean()),
                "support": support,
            }
        return {
            "map": float(np.mean(aps)) if aps else None,
            "map_50": float(np.mean([item[0] for item in aps])) if aps else None,
            "map_75": float(np.mean([item[5] for item in aps])) if aps else None,
            "mar_100": float(np.mean(recalls)) if recalls else None,
            "per_class": per_class,
            "images": len(self._images),
            "protocol": {
                "name": "COCO mask AP, all areas",
                "iou_thresholds": [round(float(value), 2) for value in self.thresholds],
                "recall_points": 101,
                "max_detections_per_image_per_category": 100,
                "pixel_validity": "clip masks; ignore detections entirely outside valid pixels",
                "score_units": "fraction",
            },
        }


class PanopticMetrics:
    """Streaming PQ, SQ and RQ, including thing/stuff groups and class counts."""

    def __init__(self, num_classes: int, thing_ids: set[int]) -> None:
        self.thing_ids = _class_set(num_classes, thing_ids)
        self.num_classes = num_classes
        self.reset()

    def reset(self) -> None:
        self._counts = np.zeros((self.num_classes, 3), dtype=np.int64)  # TP, FP, FN
        self._iou = np.zeros(self.num_classes, dtype=np.float64)
        self._images: set[int] = set()

    def update(self, prediction: dict[str, Any], target: _Target) -> None:
        if target.image_id in self._images:
            raise ValueError(f"image {target.image_id!r} was already evaluated")
        labels, masks, valid, crowd = _target_arrays(target, self.num_classes)
        segmentation = _cpu_tensor(prediction.get("segmentation"), "segmentation", 2, torch.long)
        if segmentation.shape != valid.shape or (segmentation < 0).any():
            raise ValueError("panoptic segmentation shape or segment IDs are invalid")
        segments = prediction.get("segments_info")
        if not isinstance(segments, list):
            raise ValueError("panoptic prediction requires segments_info")
        pred_info: dict[int, int] = {}
        stuff_seen: set[int] = set()
        for segment in segments:
            if not isinstance(segment, dict):
                raise ValueError("segments_info entries must be dictionaries")
            segment_id, category = segment.get("id"), segment.get("category_id")
            if (
                type(segment_id) is not int
                or segment_id <= 0
                or segment_id in pred_info
                or type(category) is not int
                or not 0 <= category < self.num_classes
            ):
                raise ValueError(
                    "segment IDs must be unique positive integers with valid categories"
                )
            if segment.get("isthing") not in (category in self.thing_ids,):
                raise ValueError("segment isthing disagrees with the category definition")
            if category not in self.thing_ids:
                if category in stuff_seen:
                    raise ValueError("panoptic stuff of one category must be merged")
                stuff_seen.add(category)
            pred_info[segment_id] = category
        actual = set(segmentation.unique().tolist()) - {0}
        if actual != set(pred_info):
            raise ValueError("panoptic pixels and segments_info must have identical segment IDs")
        if len(masks) and (masks.sum(0) > 1).any():
            raise ValueError("panoptic ground-truth objects must not overlap")
        for category in set(labels.tolist()) - self.thing_ids:
            if int(((labels == category) & ~crowd).sum()) > 1:
                raise ValueError("panoptic ground-truth stuff of one category must be merged")

        # Unassigned pixels and explicitly invalid pixels are both panoptic void.
        void = ~masks.any(0)
        counts = np.zeros_like(self._counts)
        iou_sums = np.zeros_like(self._iou)
        matched_gt: set[int] = set()
        matched_pred: set[int] = set()
        for segment_id, category in pred_info.items():
            region = segmentation == segment_id
            area = int(region.sum())
            void_overlap = int((region & void).sum())
            for truth in range(len(masks)):
                if bool(crowd[truth]) or int(labels[truth]) != category:
                    continue
                intersection = int((region & masks[truth]).sum())
                union = area + int(masks[truth].sum()) - intersection - void_overlap
                iou = intersection / union if union else 0.0
                if iou > 0.5:
                    if truth in matched_gt or segment_id in matched_pred:
                        raise ValueError("panoptic matching must be one-to-one")
                    counts[category, 0] += 1
                    iou_sums[category] += iou
                    matched_gt.add(truth)
                    matched_pred.add(segment_id)
            if segment_id not in matched_pred:
                crowd_regions = masks[(labels == category) & crowd].any(0)
                ignored_area = int((region & (void | crowd_regions)).sum())
                if ignored_area / area <= 0.5:
                    counts[category, 1] += 1
        for truth, category in enumerate(labels.tolist()):
            if truth not in matched_gt and not bool(crowd[truth]):
                counts[category, 2] += 1
        self._counts += counts
        self._iou += iou_sums
        self._images.add(target.image_id)

    def compute(self) -> dict[str, Any]:
        per_class: dict[str, Any] = {}
        for category in range(self.num_classes):
            tp, fp, fn = (int(value) for value in self._counts[category])
            denominator = tp + 0.5 * fp + 0.5 * fn
            per_class[str(category)] = {
                "pq": float(self._iou[category] / denominator) if denominator else None,
                "sq": float(self._iou[category] / tp) if tp else (0.0 if denominator else None),
                "rq": tp / denominator if denominator else None,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "sum_iou": float(self._iou[category]),
                "isthing": category in self.thing_ids,
            }

        def aggregate(categories: set[int]) -> dict[str, Any]:
            included = [
                per_class[str(cat)] for cat in sorted(categories) if self._counts[cat].any()
            ]
            return {
                **{
                    metric: float(np.mean([item[metric] for item in included]))
                    if included
                    else None
                    for metric in ("pq", "sq", "rq")
                },
                "classes": len(included),
            }

        return {
            **aggregate(set(range(self.num_classes))),
            "things": aggregate(self.thing_ids),
            "stuff": aggregate(set(range(self.num_classes)) - self.thing_ids),
            "per_class": per_class,
            "images": len(self._images),
            "protocol": {
                "name": "COCO panoptic quality",
                "matching_iou": ">0.5",
                "ignore_unmatched_prediction": ">50% void or same-category crowd",
                "score_units": "fraction",
            },
        }
