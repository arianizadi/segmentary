"""Object identity, COCO rasterization, void and category mapping contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from PIL import Image

from segmentary.objects.data import (
    ObjectDataset,
    collate_objects,
    decode_instance_mask,
    preprocess_image,
    resize_image_tensor,
)


def _write_split(tmp_path: Path, document: dict[str, Any]) -> tuple[Path, Path]:
    images = tmp_path / "images"
    images.mkdir(exist_ok=True)
    for record in document["images"]:
        destination = images / record["file_name"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (record["width"], record["height"]), (255, 0, 0)).save(destination)
    annotations = tmp_path / "annotations.json"
    annotations.write_text(json.dumps(document))
    return images, annotations


def _instance_document() -> dict[str, Any]:
    return {
        "images": [{"id": 7, "file_name": "sequence/frame.png", "height": 4, "width": 4}],
        "categories": [{"id": 20, "name": "animal"}, {"id": 3, "name": "vehicle"}],
        "annotations": [
            {
                "id": 1,
                "image_id": 7,
                "category_id": 20,
                "segmentation": {"size": [4, 4], "counts": [0, 2, 2, 2, 10]},
            },
            {
                "id": 2,
                "image_id": 7,
                "category_id": 20,
                "segmentation": {"size": [4, 4], "counts": [10, 2, 2, 2]},
            },
            {
                "id": 3,
                "image_id": 7,
                "category_id": 3,
                "iscrowd": 1,
                "segmentation": {"size": [4, 4], "counts": [2, 2, 2, 2, 8]},
            },
        ],
    }


def test_instance_preserves_distinct_objects_crowds_and_category_mapping(tmp_path: Path) -> None:
    images, annotations = _write_split(tmp_path, _instance_document())
    dataset = ObjectDataset(images, annotations, "instance")
    sample = dataset[0]
    target = sample["target"]
    assert dataset.num_classes == 2
    assert dataset.category_id_to_class_id == {3: 0, 20: 1}
    assert dataset.class_id_to_category_id == {0: 3, 1: 20}
    assert dataset.thing_ids == {0, 1}
    assert [category["name"] for category in dataset.categories] == ["vehicle", "animal"]
    assert sample["key"] == "sequence/frame.png"
    assert target.class_ids.tolist() == [1, 1, 0]
    assert target.iscrowd.tolist() == [False, False, True]
    assert target.original_size == (4, 4)
    assert target.image_id == 7
    assert target.masks.dtype == torch.bool
    assert target.valid.all()  # Crowds are retained; the loss excludes them separately.
    assert target.masks[0, :2, :2].all() and target.masks[0].sum() == 4
    assert target.masks[1, 2:, 2:].all() and target.masks[1].sum() == 4
    assert not (target.masks[0] & target.masks[1]).any()
    assert target.to("cpu").class_ids.tolist() == [1, 1, 0]
    expected_rgb = (
        torch.tensor([1.0, 0.0, 0.0]) - torch.tensor([0.485, 0.456, 0.406])
    ) / torch.tensor([0.229, 0.224, 0.225])
    torch.testing.assert_close(sample["image"][:, 0, 0], expected_rgb)


def test_coco_polygons_keep_disconnected_components_and_rle_matches_reference() -> None:
    mask_api = pytest.importorskip("pycocotools.mask")
    polygons = [[0, 0, 2, 0, 2, 2, 0, 2], [2, 2, 4, 2, 4, 4, 2, 4]]
    expected = np.array([[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 1, 1], [0, 0, 1, 1]], dtype=np.bool_)
    assert np.array_equal(decode_instance_mask(polygons, 4, 4), expected)
    # Official COCO encoding exercises signed differences between alternating runs.
    rng = np.random.default_rng(41)
    for height, width in ((4, 4), (11, 17), (63, 29)):
        mask = rng.integers(0, 2, size=(height, width), dtype=np.uint8)
        encoded = mask_api.encode(np.asfortranarray(mask))
        encoded["counts"] = encoded["counts"].decode("ascii")
        np.testing.assert_array_equal(decode_instance_mask(encoded, height, width), mask)


def _panoptic_document() -> tuple[dict[str, Any], np.ndarray]:
    ids = np.array(
        [[65793, 65793, 2, 2], [65793, 65793, 2, 2], [9, 9, 9, 9], [10, 10, 300, 0]],
        dtype=np.uint32,
    )
    document = {
        "images": [{"id": 8, "file_name": "frame.png", "height": 4, "width": 4}],
        "categories": [
            {"id": 7, "name": "person", "isthing": 1},
            {"id": 3, "name": "sky", "isthing": 0},
        ],
        "annotations": [
            {
                "image_id": 8,
                "file_name": "segments.png",
                "segments_info": [
                    {"id": 65793, "category_id": 7, "area": 4},
                    {"id": 2, "category_id": 7, "area": 4},
                    {"id": 9, "category_id": 3, "area": 4},
                    {"id": 10, "category_id": 3, "area": 2},
                    {"id": 300, "category_id": 7, "area": 1, "iscrowd": 1},
                ],
            }
        ],
    }
    return document, ids


def _save_panoptic(tmp_path: Path, ids: np.ndarray) -> Path:
    masks = tmp_path / "panoptic"
    masks.mkdir(exist_ok=True)
    rgb = np.stack([ids % 256, (ids // 256) % 256, ids // 256**2], axis=-1).astype(np.uint8)
    Image.fromarray(rgb).save(masks / "segments.png")
    return masks


def test_panoptic_rgb_ids_things_stuff_void_crowd_and_resize(tmp_path: Path) -> None:
    document, ids = _panoptic_document()
    images, annotations = _write_split(tmp_path, document)
    masks = _save_panoptic(tmp_path, ids)
    dataset = ObjectDataset(images, annotations, "panoptic", masks, image_size=(8, 12))
    target = dataset[0]["target"]
    assert dataset.thing_ids == {1}
    assert target.original_size == (4, 4)
    assert target.masks.shape == (4, 8, 12)
    assert target.class_ids.tolist() == [1, 1, 0, 1]
    assert target.iscrowd.tolist() == [False, False, False, True]
    assert target.masks.flatten(1).sum(1).tolist() == [24, 24, 36, 6]
    assert target.valid.sum() == 90
    assert not target.valid[-2:, -3:].any()
    assert target.valid[-2:, -6:-3].all()  # Same-class crowd is not generic void.
    assert not (target.masks.sum(0) > 1).any()
    assert dataset[0]["image"].shape == (3, 8, 12)


def test_empty_instance_images_remain_negative_samples_and_collate(tmp_path: Path) -> None:
    document = _instance_document()
    document["images"].append({"id": 9, "file_name": "negative.png", "height": 4, "width": 4})
    images, annotations = _write_split(tmp_path, document)
    dataset = ObjectDataset(images, annotations, "instance")
    negative = dataset[1]
    assert negative["target"].masks.shape == (0, 4, 4)
    assert negative["target"].class_ids.numel() == 0
    assert negative["target"].valid.all()
    batch, targets, keys = collate_objects([dataset[0], negative])
    assert batch.shape == (2, 3, 4, 4)
    assert len(targets) == 2
    assert keys == ["sequence/frame.png", "negative.png"]
    with pytest.raises(ValueError, match="sizes differ"):
        collate_objects([negative, {**negative, "image": torch.zeros(3, 3, 4)}])


def test_all_void_panoptic_image_has_no_fabricated_background(tmp_path: Path) -> None:
    document, ids = _panoptic_document()
    document["annotations"][0]["segments_info"] = []
    images, annotations = _write_split(tmp_path, document)
    masks = _save_panoptic(tmp_path, np.zeros_like(ids))
    dataset = ObjectDataset(images, annotations, "panoptic", masks)
    target = dataset[0]["target"]
    assert target.masks.shape == (0, 4, 4)
    assert target.class_ids.numel() == 0
    assert not target.valid.any()


def test_split_category_metadata_must_agree_with_training(tmp_path: Path) -> None:
    images, annotations = _write_split(tmp_path, _instance_document())
    dataset = ObjectDataset(images, annotations, "instance")
    train_categories = copy.deepcopy(dataset.categories)
    train_categories.append({"id": 99, "name": "extra thing", "isthing": 1})
    split = ObjectDataset(images, annotations, "instance", categories=train_categories)
    assert split.num_classes == 3
    assert split[0]["target"].class_ids.tolist() == [1, 1, 0]
    train_categories[0]["name"] = "wrong meaning"
    with pytest.raises(ValueError, match="disagrees"):
        ObjectDataset(images, annotations, "instance", categories=train_categories)


@pytest.mark.parametrize(
    ("segmentation", "message"),
    [
        ({"size": [2, 2], "counts": [16]}, "RLE size"),
        ({"size": [4, 4], "counts": [15]}, "pixel count"),
        ({"size": [4, 4], "counts": [0, -1, 17]}, "RLE run"),
        ({"size": [4, 4], "counts": "P"}, "Truncated"),
        ({"size": [4, 4], "counts": "!"}, "Invalid compressed"),
        ([[0, 0, 1, 1]], "three x/y"),
        ([[0, 0, 1, 0, 0, float("nan")]], "finite"),
    ],
)
def test_malformed_instance_masks_fail_before_native_decode(
    segmentation: Any, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        decode_instance_mask(segmentation, 4, 4)


@pytest.mark.parametrize("problem", ["undeclared", "missing", "area", "dimensions", "mode"])
def test_bad_panoptic_masks_are_rejected(tmp_path: Path, problem: str) -> None:
    document, ids = _panoptic_document()
    if problem == "undeclared":
        ids[3, 3] = 44
    elif problem == "missing":
        ids[ids == 65793] = 0
    elif problem == "area":
        document["annotations"][0]["segments_info"][0]["area"] = 99
    elif problem == "dimensions":
        ids = ids[:2]
    images, annotations = _write_split(tmp_path, document)
    masks = _save_panoptic(tmp_path, ids)
    if problem == "mode":
        Image.new("L", (4, 4)).save(masks / "segments.png")
    dataset = ObjectDataset(images, annotations, "panoptic", masks)
    with pytest.raises(ValueError):
        dataset[0]


@pytest.mark.parametrize("problem", ["image_id", "category_id", "annotation_id", "iscrowd"])
def test_bad_annotation_metadata_is_rejected(tmp_path: Path, problem: str) -> None:
    document = _instance_document()
    if problem == "image_id":
        document["annotations"][0]["image_id"] = 999
    elif problem == "category_id":
        document["annotations"][0]["category_id"] = 999
    elif problem == "annotation_id":
        document["annotations"][1]["id"] = 1
    elif problem == "iscrowd":
        document["annotations"][0]["iscrowd"] = "false"
    images, annotations = _write_split(tmp_path, document)
    with pytest.raises(ValueError):
        ObjectDataset(images, annotations, "instance")


def test_path_escape_and_metadata_dimension_mismatch_are_rejected(tmp_path: Path) -> None:
    document = _instance_document()
    images, annotations = _write_split(tmp_path, document)
    document["images"][0]["file_name"] = "../outside.png"
    annotations.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="inside its root"):
        ObjectDataset(images, annotations, "instance")
    document = _instance_document()
    document["images"][0]["width"] = 5
    annotations.write_text(json.dumps(document))
    dataset = ObjectDataset(images, annotations, "instance")
    with pytest.raises(ValueError, match="dimensions differ"):
        dataset[0]


def test_resize_must_not_silently_erase_instances(tmp_path: Path) -> None:
    images, annotations = _write_split(tmp_path, _instance_document())
    dataset = ObjectDataset(images, annotations, "instance", image_size=(1, 1))
    with pytest.raises(ValueError, match="erased an annotated segment"):
        dataset[0]


@pytest.mark.parametrize("problem", ["no_isthing", "duplicate_id", "crowd_stuff", "no_annotation"])
def test_panoptic_metadata_contracts(tmp_path: Path, problem: str) -> None:
    document, ids = _panoptic_document()
    if problem == "no_isthing":
        del document["categories"][0]["isthing"]
    elif problem == "duplicate_id":
        document["annotations"][0]["segments_info"][1]["id"] = 65793
    elif problem == "crowd_stuff":
        document["annotations"][0]["segments_info"][2]["iscrowd"] = 1
    elif problem == "no_annotation":
        document["annotations"] = []
    images, annotations = _write_split(tmp_path, document)
    masks = _save_panoptic(tmp_path, ids)
    with pytest.raises(ValueError):
        ObjectDataset(images, annotations, "panoptic", masks)


def test_instance_stuff_categories_fail_instead_of_becoming_objects(tmp_path: Path) -> None:
    document = _instance_document()
    document["categories"][0]["isthing"] = 0
    images, annotations = _write_split(tmp_path, document)
    with pytest.raises(ValueError, match="only thing"):
        ObjectDataset(images, annotations, "instance")


@pytest.mark.parametrize("size", [(7, 9), (23, 31), (11, 17)])
def test_training_and_inference_image_preprocessing_are_identical(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    document = _instance_document()
    document["images"][0].update(height=11, width=17)
    document["annotations"] = []
    images, annotations = _write_split(tmp_path, document)
    # Texture reveals both uint8 rounding and antialiasing differences that a
    # constant-color fixture would miss in PIL versus torch resize pipelines.
    pixels = np.random.default_rng(21).integers(0, 256, (11, 17, 3), dtype=np.uint8)
    image = Image.fromarray(pixels)
    image.save(images / "sequence/frame.png")
    native = ObjectDataset(images, annotations, "instance")[0]["image"]
    training = ObjectDataset(images, annotations, "instance", image_size=size)[0]["image"]
    inference = resize_image_tensor(native, size)
    torch.testing.assert_close(training, inference, rtol=0, atol=0)
    torch.testing.assert_close(training, preprocess_image(image, size), rtol=0, atol=0)
    assert training.shape == (3, *size)
