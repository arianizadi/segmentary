"""Query decoding preserves identity and makes explicit panoptic void/stuff IDs."""

from __future__ import annotations

import pytest
import torch

from segmentary.models.outputs import QueryPrediction
from segmentary.objects.prediction import postprocess


def _queries() -> QueryPrediction:
    # Two things of class zero, two separated stuff masks of class one, no-object.
    masks = torch.full((1, 5, 2, 6), -10.0)
    masks[0, 0, 0, :2] = 10
    masks[0, 1, 0, 2:4] = 10
    masks[0, 2, 1, :3] = 10
    masks[0, 3, 1, 3:] = 10
    masks[0, 4] = 10
    classes = torch.tensor(
        [[[10.0, -10, -10], [9, -10, -10], [-10, 10, -10], [-10, 9, -10], [-10, -10, 10]]]
    )
    return QueryPrediction(classes, masks)


def test_instance_keeps_two_same_class_objects_and_excludes_stuff_no_object() -> None:
    result = postprocess(_queries(), "instance", {0}, [(2, 6)])[0]
    assert result["class_ids"].tolist() == [0, 0]
    assert result["masks"].shape == (2, 2, 6)
    assert result["masks"].sum((1, 2)).tolist() == [2, 2]
    assert not (result["masks"][0] & result["masks"][1]).any()
    assert (result["scores"] > 0.99).all()


def test_panoptic_merges_stuff_but_preserves_two_things_and_void() -> None:
    result = postprocess(_queries(), "panoptic", {0}, [(2, 6)])[0]
    assert result["segmentation"].tolist() == [[1, 1, 2, 2, 0, 0], [3, 3, 3, 3, 3, 3]]
    assert [item["category_id"] for item in result["segments_info"]] == [0, 0, 1]
    assert [item["isthing"] for item in result["segments_info"]] == [True, True, False]


def test_panoptic_conflict_assignment_and_overlap_rejection_are_deterministic() -> None:
    query = QueryPrediction(torch.tensor([[[8.0, -8], [8.0, -8]]]), torch.ones(1, 2, 3, 3) * 8)
    first = postprocess(query, "panoptic", {0}, [(3, 3)])[0]
    second = postprocess(query, "panoptic", {0}, [(3, 3)])[0]
    assert len(first["segments_info"]) == 1
    assert torch.equal(first["segmentation"], torch.ones(3, 3, dtype=torch.long))
    assert torch.equal(first["segmentation"], second["segmentation"])
    # Instance segmentation permits overlap; identities must never silently merge.
    assert len(postprocess(query, "instance", {0}, [(3, 3)])[0]["masks"]) == 2


@pytest.mark.parametrize("task", ["instance", "panoptic"])
def test_no_object_and_empty_foreground_have_explicit_empty_outputs(task: str) -> None:
    query = QueryPrediction(torch.tensor([[[-4.0, 4]]]), torch.ones(1, 1, 2, 2))
    result = postprocess(query, task, {0}, [(4, 6)])[0]
    if task == "instance":
        assert result["masks"].shape == (0, 4, 6)
    else:
        assert result["segmentation"].shape == (4, 6)
        assert result["segmentation"].sum() == 0
        assert result["segments_info"] == []
    query = QueryPrediction(torch.tensor([[[4.0, -4]]]), torch.ones(1, 1, 2, 2) * -8)
    result = postprocess(query, task, {0}, [(4, 6)])[0]
    assert len(result["masks"] if task == "instance" else result["segments_info"]) == 0


def test_resizing_batch_and_quality_scores() -> None:
    query = QueryPrediction(torch.tensor([[[4.0, -4]], [[4.0, -4]]]), torch.ones(2, 1, 2, 2))
    result = postprocess(query, "instance", {0}, [(6, 4), (8, 2)])
    assert result[0]["masks"].shape == (1, 6, 4)
    assert result[1]["masks"].shape == (1, 8, 2)
    expected = torch.tensor([4.0, -4]).softmax(0)[0] * torch.tensor(1.0).sigmoid()
    assert float(result[0]["scores"][0]) == pytest.approx(float(expected))


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"task": "semantic"}, "task"),
        ({"thing_ids": {2}}, "thing_ids"),
        ({"sizes": [(0, 2)]}, "sizes"),
        ({"sizes": []}, "sizes"),
        ({"score_threshold": float("nan")}, "score_threshold"),
        ({"mask_threshold": -0.1}, "mask_threshold"),
        ({"overlap_threshold": 1.1}, "overlap_threshold"),
    ],
)
def test_bad_configuration_is_rejected(kwargs: dict, match: str) -> None:
    args = {"task": "instance", "thing_ids": {0}, "sizes": [(2, 6)]} | kwargs
    with pytest.raises(ValueError, match=match):
        postprocess(_queries(), **args)


def test_nonfinite_logits_are_rejected() -> None:
    query = _queries()
    query.mask_logits[0, 0, 0, 0] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        postprocess(query, "instance", {0}, [(2, 6)])
