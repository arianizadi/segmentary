"""Numerical AP/PQ proofs cover identity, ranking, crowds and panoptic void."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import torch

from segmentary.objects.metrics import InstanceMetrics, PanopticMetrics


def _target(masks, labels=None, crowd=None, valid=None, image_id=1):
    masks = torch.as_tensor(masks, dtype=torch.bool)
    return SimpleNamespace(
        masks=masks,
        class_ids=torch.tensor(
            labels if labels is not None else [0] * len(masks), dtype=torch.long
        ),
        iscrowd=torch.tensor(crowd if crowd is not None else [False] * len(masks)),
        valid=torch.as_tensor(valid, dtype=torch.bool)
        if valid is not None
        else torch.ones(masks.shape[1:], dtype=torch.bool),
        image_id=image_id,
    )


def _pred(masks, labels=None, scores=None):
    masks = torch.as_tensor(masks, dtype=torch.bool)
    return {
        "masks": masks,
        "class_ids": torch.tensor(
            labels if labels is not None else [0] * len(masks), dtype=torch.long
        ),
        "scores": torch.tensor(scores if scores is not None else [0.9] * len(masks)),
    }


def _panoptic(segmentation, categories, things=None):
    things = {0} if things is None else things
    return {
        "segmentation": torch.tensor(segmentation, dtype=torch.long),
        "segments_info": [
            {"id": index + 1, "category_id": category, "isthing": category in things}
            for index, category in enumerate(categories)
        ],
    }


def test_two_identical_class_instances_score_perfectly_with_distinct_identity() -> None:
    masks = [[[1, 0], [0, 0]], [[0, 1], [0, 0]]]
    metric = InstanceMetrics(2, {0})
    metric.update(_pred(masks), _target(masks))
    result = metric.compute()
    assert result["map"] == pytest.approx(1.0)
    assert result["map_50"] == pytest.approx(1.0)
    assert result["map_75"] == pytest.approx(1.0)
    assert result["mar_100"] == pytest.approx(1.0)
    assert result["per_class"]["0"]["support"] == 2


def test_ranked_false_positive_and_missing_object_have_verifiable_101_point_ap() -> None:
    # FP first, then one TP, with a second GT missed: precision=.5, recall=.5.
    # 51 of 101 recall samples receive .5, the remaining 50 receive zero.
    truth = [[[1, 0, 0]], [[0, 1, 0]]]
    prediction = [[[0, 0, 1]], [[1, 0, 0]]]
    metric = InstanceMetrics(1)
    metric.update(_pred(prediction, scores=[0.99, 0.9]), _target(truth))
    assert metric.compute()["map"] == pytest.approx(0.5 * 51 / 101)
    assert metric.compute()["mar_100"] == pytest.approx(0.5)


def test_ap_thresholds_and_duplicate_detection_matching() -> None:
    # IoU .6 is accepted at .50/.55/.60, and rejected at seven later thresholds.
    metric = InstanceMetrics(1)
    metric.update(_pred([[[1, 1, 1, 0, 0]]]), _target([[[1, 1, 1, 1, 1]]]))
    assert metric.compute()["map"] == pytest.approx(0.3)
    assert metric.compute()["map_50"] == pytest.approx(1.0)
    assert metric.compute()["map_75"] == 0
    # The duplicated highest-score mask cannot satisfy two same-class GT objects.
    metric.reset()
    metric.update(_pred([[[1, 0]], [[1, 0]]]), _target([[[1, 0]], [[0, 1]]]))
    assert metric.compute()["mar_100"] == 0.5


def test_instance_crowd_can_absorb_multiple_predictions_without_false_positives() -> None:
    metric = InstanceMetrics(1)
    metric.update(
        _pred([[[0, 1, 0]], [[0, 0, 1]], [[1, 0, 0]]], scores=[0.99, 0.98, 0.9]),
        _target([[[1, 0, 0]], [[0, 1, 1]]], crowd=[False, True]),
    )
    assert metric.compute()["map"] == 1.0
    assert metric.compute()["per_class"]["0"]["support"] == 1


def test_instance_invalid_pixels_are_excluded_and_no_support_is_null() -> None:
    metric = InstanceMetrics(2)
    metric.update(
        _pred([[[0, 1]], [[1, 1]]], scores=[0.99, 0.9]),
        _target([[[1, 0]]], valid=[[True, False]]),
    )
    result = metric.compute()
    assert result["map"] == 1.0
    assert result["per_class"]["1"]["map"] is None
    metric.reset()
    assert metric.compute()["map"] is None


def test_instance_global_ranking_not_mean_of_image_aps_and_max100() -> None:
    metric = InstanceMetrics(1)
    metric.update(_pred([[[0, 1]]], scores=[0.99]), _target([[[1, 0]]], image_id=1))
    metric.update(_pred([[[1, 0]]], scores=[0.8]), _target([[[1, 0]]], image_id=2))
    assert metric.compute()["map"] == pytest.approx(0.5 * 51 / 101)
    metric.reset()
    metric.update(
        _pred([[[0, 1]]] * 100 + [[[1, 0]]], scores=[0.9] * 100 + [0.8]),
        _target([[[1, 0]]]),
    )
    assert metric.compute()["map"] == 0


def test_panoptic_perfect_things_stuff_and_missing_group() -> None:
    metric = PanopticMetrics(3, {0})
    metric.update(
        _panoptic([[1, 2], [3, 3]], [0, 0, 1]),
        _target([[[1, 0], [0, 0]], [[0, 1], [0, 0]], [[0, 0], [1, 1]]], [0, 0, 1]),
    )
    result = metric.compute()
    assert result["pq"] == result["sq"] == result["rq"] == 1
    assert result["things"]["pq"] == result["stuff"]["pq"] == 1
    assert result["per_class"]["0"]["tp"] == 2
    assert result["per_class"]["2"]["pq"] is None


def test_panoptic_merged_things_fail_strict_half_overlap_and_count_false_negatives() -> None:
    metric = PanopticMetrics(1, {0})
    metric.update(_panoptic([[1, 1]], [0]), _target([[[1, 0]], [[0, 1]]]))
    result = metric.compute()
    assert result["pq"] == 0
    assert result["per_class"]["0"]["tp"] == 0
    assert result["per_class"]["0"]["fp"] == 1
    assert result["per_class"]["0"]["fn"] == 2


def test_panoptic_void_excluded_from_union_and_majority_void_prediction_ignored() -> None:
    metric = PanopticMetrics(1, {0})
    metric.update(
        _panoptic([[1, 1, 2, 2]], [0, 0]),
        _target([[[1, 0, 0, 0]]], valid=[[True, False, False, False]]),
    )
    result = metric.compute()
    assert result["pq"] == 1
    assert result["per_class"]["0"]["fp"] == 0


def test_panoptic_same_category_crowd_ignored_other_category_is_false_positive() -> None:
    target = _target([[[1, 0, 0]], [[0, 1, 1]]], crowd=[False, True])
    metric = PanopticMetrics(2, {0, 1})
    metric.update(_panoptic([[1, 2, 2]], [0, 0], {0, 1}), target)
    assert metric.compute()["pq"] == 1
    metric.reset()
    metric.update(_panoptic([[1, 2, 2]], [0, 1], {0, 1}), target)
    result = metric.compute()
    assert result["pq"] == 0.5
    assert result["per_class"]["1"]["fp"] == 1


def test_panoptic_false_positive_false_negative_formula() -> None:
    metric = PanopticMetrics(1, {0})
    # One true positive (IoU .75), one false positive and one missed GT.
    metric.update(
        _panoptic([[1, 1, 1, 2, 0]], [0, 0]),
        _target([[[1, 1, 1, 1, 0]], [[0, 0, 0, 0, 1]]]),
    )
    result = metric.compute()
    assert result["sq"] == 0.75
    assert result["rq"] == 0.5
    assert result["pq"] == 0.375


@pytest.mark.parametrize("kind", ["instance", "panoptic"])
def test_duplicate_images_are_rejected_and_reset_is_available(kind: str) -> None:
    metric = InstanceMetrics(1) if kind == "instance" else PanopticMetrics(1, {0})
    prediction = _pred([[[1]]]) if kind == "instance" else _panoptic([[1]], [0])
    target = _target([[[1]]])
    metric.update(prediction, target)
    with pytest.raises(ValueError, match="already evaluated"):
        metric.update(prediction, target)
    metric.reset()
    metric.update(prediction, target)
    assert metric.compute()["images"] == 1


def test_panoptic_rejects_overlapping_truth_unknown_segments_and_separate_stuff() -> None:
    metric = PanopticMetrics(2, {0})
    with pytest.raises(ValueError, match="overlap"):
        metric.update(_panoptic([[1]], [0]), _target([[[1]], [[1]]]))
    with pytest.raises(ValueError, match="identical segment IDs"):
        metric.update(_panoptic([[2]], [0]), _target([[[1]]]))
    with pytest.raises(ValueError, match=r"stuff.*merged"):
        metric.update(_panoptic([[1, 2]], [1, 1]), _target([[[1, 1]]], [1]))


def test_invalid_prediction_inputs_are_rejected_before_accumulating() -> None:
    metric = InstanceMetrics(1)
    with pytest.raises(ValueError, match="scores are invalid"):
        metric.update(_pred([[[1]]], scores=[float("nan")]), _target([[[1]]]))
    assert metric.compute()["images"] == 0


@pytest.mark.parametrize("seed", [7, 23, 41])
def test_mask_ap_matches_official_cocoeval_with_multiple_classes_and_crowds(seed: int) -> None:
    from pycocotools import mask as mask_utils
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval

    rng = np.random.default_rng(seed)
    metric = InstanceMetrics(3)
    annotations, detections = [], []
    images = [{"id": image_id, "height": 4, "width": 8} for image_id in range(1, 4)]
    for image in images:
        gt_masks = np.zeros((4, 4, 8), dtype=bool)
        gt_masks[0, :2, :3] = True
        gt_masks[1, 2:, :3] = True
        gt_masks[2, :2, 3:6] = True
        gt_masks[3, :, 6:] = True
        labels, crowds = [0, 0, 1, 0], [False, False, False, True]
        pred_masks = [*gt_masks]
        pred_labels = [0, 0, 1, 0]
        for _ in range(12):
            base = int(rng.integers(4))
            noisy = gt_masks[base] ^ (rng.random((4, 8)) < 0.15)
            pred_masks.append(noisy)
            pred_labels.append(labels[base] if rng.random() > 0.2 else 2)
        scores = rng.uniform(0.05, 0.99, len(pred_masks)).tolist()
        metric.update(
            _pred(np.array(pred_masks), pred_labels, scores),
            _target(gt_masks, labels, crowds, image_id=image["id"]),
        )
        for mask, label, crowd in zip(gt_masks, labels, crowds, strict=True):
            rle = mask_utils.encode(np.asfortranarray(mask.astype(np.uint8)))
            annotations.append(
                {
                    "id": len(annotations) + 1,
                    "image_id": image["id"],
                    "category_id": label,
                    "segmentation": rle,
                    "area": float(mask_utils.area(rle)),
                    "bbox": mask_utils.toBbox(rle).tolist(),
                    "iscrowd": int(crowd),
                }
            )
        for mask, label, score in zip(pred_masks, pred_labels, scores, strict=True):
            detections.append(
                {
                    "image_id": image["id"],
                    "category_id": label,
                    "score": score,
                    "segmentation": mask_utils.encode(np.asfortranarray(mask.astype(np.uint8))),
                }
            )
    truth = COCO()
    truth.dataset = {
        "images": images,
        "annotations": annotations,
        "categories": [{"id": category, "name": str(category)} for category in range(3)],
        "info": {},
    }
    truth.createIndex()
    evaluator = COCOeval(truth, truth.loadRes(detections), "segm")
    evaluator.evaluate()
    evaluator.accumulate()
    evaluator.summarize()
    result = metric.compute()
    assert result["map"] == pytest.approx(evaluator.stats[0], abs=1e-12)
    assert result["map_50"] == pytest.approx(evaluator.stats[1], abs=1e-12)
    assert result["map_75"] == pytest.approx(evaluator.stats[2], abs=1e-12)
    assert result["mar_100"] == pytest.approx(evaluator.stats[8], abs=1e-12)
