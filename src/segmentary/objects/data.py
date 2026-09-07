"""COCO object targets, deliberately separate from semantic label-map datasets.

Instance masks may overlap and repeated class IDs are never collapsed. Panoptic
PNG IDs identify segments, not classes: zero is void, and ``segments_info`` maps
each nonzero ID to its category. Image sizes are always written as (height, width).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from torch import Tensor
from torch.nn import functional as F
from torch.utils.data import Dataset


@dataclass
class ObjectTarget:
    class_ids: Tensor
    masks: Tensor
    valid: Tensor
    iscrowd: Tensor
    image_id: int
    original_size: tuple[int, int]

    def to(self, device: torch.device | str) -> ObjectTarget:
        return ObjectTarget(
            self.class_ids.to(device),
            self.masks.to(device),
            self.valid.to(device),
            self.iscrowd.to(device),
            self.image_id,
            self.original_size,
        )


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, got {value!r}")
    return value


def resize_image_tensor(image: Tensor, size: tuple[int, int] | None) -> Tensor:
    """Resize normalized RGB CHW data identically in training and inference.

    Images use antialiased bilinear sampling; this helper is never for masks or
    segment IDs. Normalization happens at native resolution before this step.
    """
    if image.ndim != 3 or image.shape[0] != 3 or not image.is_floating_point():
        raise ValueError("Expected a floating-point normalized RGB image with shape (3, H, W)")
    if size is None:
        return image
    if len(size) != 2:
        raise ValueError("Image size must be (height, width)")
    size = (
        _integer(size[0], "image height", minimum=1),
        _integer(size[1], "image width", minimum=1),
    )
    if image.shape[-2:] == size:
        return image
    return F.interpolate(
        image.unsqueeze(0), size=size, mode="bilinear", align_corners=False, antialias=True
    )[0]


def preprocess_image(image: Image.Image, size: tuple[int, int] | None = None) -> Tensor:
    """Convert a PIL image to RGB, apply ImageNet normalization, then resize."""
    image_array = np.asarray(image.convert("RGB"), dtype=np.float32).copy() / 255.0
    tensor = torch.from_numpy(image_array).permute(2, 0, 1)
    mean = tensor.new_tensor([0.485, 0.456, 0.406])[:, None, None]
    std = tensor.new_tensor([0.229, 0.224, 0.225])[:, None, None]
    return resize_image_tensor((tensor - mean) / std, size)


def _flag(value: Any, name: str) -> int:
    if not isinstance(value, (int, bool)) or value not in (0, 1):
        raise ValueError(f"{name} must be 0 or 1, got {value!r}")
    return int(value)


def _records(value: Any, name: str, *, nonempty: bool = False) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{name} must be a list of objects")
    if nonempty and not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _safe_file(root: Path, name: Any) -> Path:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError(f"Invalid dataset file_name: {name!r}")
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Dataset file_name must remain inside its root: {name!r}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Dataset file escapes its root: {name!r}")
    if not path.is_file():
        raise FileNotFoundError(f"Dataset file does not exist: {path}")
    return path


def _categories(records: Any, task: str) -> list[dict[str, Any]]:
    result = []
    seen: set[int] = set()
    for record in _records(records, "categories", nonempty=True):
        category = dict(record)
        category_id = _integer(category.get("id"), "category id")
        if category_id in seen:
            raise ValueError(f"Duplicate category id: {category_id}")
        seen.add(category_id)
        if not isinstance(category.get("name"), str) or not category["name"].strip():
            raise ValueError(f"Category {category_id} needs a nonempty name")
        if task == "panoptic" and "isthing" not in category:
            raise ValueError(f"Panoptic category {category_id} must declare isthing")
        category["isthing"] = _flag(category.get("isthing", 1), "isthing")
        if task == "instance" and not category["isthing"]:
            raise ValueError("Instance datasets must contain only thing categories")
        result.append(category)
    return sorted(result, key=lambda category: category["id"])


def _rle_counts(counts: Any, pixels: int) -> list[int]:
    """Decode COCO's signed, delta-coded base-32 runs before allocating masks.

    Checking the total is essential: malformed lengths must never reach a native
    decoder that assumes its caller has supplied exactly height * width pixels.
    """
    if isinstance(counts, list):
        runs = [_integer(value, "RLE run") for value in counts]
    elif isinstance(counts, str):
        runs = []
        position = 0
        while position < len(counts):
            value = 0
            shift = 0
            while True:
                if position >= len(counts):
                    raise ValueError("Truncated compressed RLE")
                code = ord(counts[position]) - 48
                position += 1
                if not 0 <= code <= 63 or shift > 60:
                    raise ValueError("Invalid compressed RLE")
                value |= (code & 31) << shift
                shift += 5
                if not code & 32:
                    if code & 16:
                        value -= 1 << shift
                    break
            if len(runs) > 2:
                value += runs[-2]
            if value < 0 or value > pixels:
                raise ValueError("Compressed RLE run is outside image bounds")
            runs.append(value)
    else:
        raise ValueError("RLE counts must be a list of lengths or a compressed string")
    if not runs or sum(runs) != pixels:
        raise ValueError("RLE run lengths must sum to the image pixel count")
    return runs


def decode_instance_mask(segmentation: Any, height: int, width: int) -> np.ndarray:
    """Decode COCO polygons or compressed/uncompressed RLE to a Boolean mask."""
    _integer(height, "mask height", minimum=1)
    _integer(width, "mask width", minimum=1)
    if isinstance(segmentation, dict):
        size = segmentation.get("size")
        if (
            not isinstance(size, list)
            or len(size) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in size)
            or size != [height, width]
        ):
            raise ValueError(f"RLE size {size!r} does not match image {(height, width)}")
        runs = _rle_counts(segmentation.get("counts"), height * width)
        flat = np.zeros(height * width, dtype=np.bool_)
        start = 0
        for index, run in enumerate(runs):
            if index % 2:
                flat[start : start + run] = True
            start += run
        return flat.reshape((height, width), order="F")
    if not isinstance(segmentation, list) or not segmentation:
        raise ValueError("Instance segmentation must be nonempty COCO polygons or RLE")
    for polygon in segmentation:
        if not isinstance(polygon, list) or len(polygon) < 6 or len(polygon) % 2:
            raise ValueError("Each COCO polygon needs at least three x/y coordinate pairs")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in polygon
        ):
            raise ValueError("Polygon coordinates must be finite numbers")
    try:
        from pycocotools import mask as mask_api
    except ImportError as error:
        raise ImportError(
            "COCO polygon decoding needs pycocotools; install segmentary[objects]"
        ) from error
    encoded = mask_api.frPyObjects(segmentation, height, width)
    return np.asarray(mask_api.decode(mask_api.merge(encoded)), dtype=np.bool_)


class ObjectDataset(Dataset[dict[str, Any]]):
    """Load a COCO instance or panoptic split with an explicit category mapping.

    ``categories`` can carry the training category metadata into another split;
    local category IDs, names and thing/stuff flags must agree. Contiguous model
    IDs follow sorted original category IDs, never annotation or file order.
    Panoptic stuff segments of the same class are merged, whereas thing objects
    remain separate even when they share a class. Crowd masks remain in targets
    for evaluation. ``valid`` marks every nonvoid pixel, including crowds;
    training excludes crowds separately using ``iscrowd``. Instance background
    pixels remain valid negatives.
    """

    def __init__(
        self,
        images: Path,
        annotations: Path,
        task: str,
        panoptic_masks: Path | None = None,
        image_size: tuple[int, int] | None = None,
        categories: list[dict[str, Any]] | None = None,
    ) -> None:
        if task not in ("instance", "panoptic"):
            raise ValueError("ObjectDataset task must be 'instance' or 'panoptic'")
        self.task = task
        self.image_root = Path(images).resolve()
        self.annotation_path = Path(annotations).resolve()
        self.panoptic_root = Path(panoptic_masks).resolve() if panoptic_masks is not None else None
        if not self.image_root.is_dir():
            raise FileNotFoundError(f"Image root does not exist: {self.image_root}")
        if task == "panoptic" and (self.panoptic_root is None or not self.panoptic_root.is_dir()):
            raise ValueError("Panoptic datasets require an existing panoptic_masks directory")
        if task == "instance" and panoptic_masks is not None:
            raise ValueError("panoptic_masks is only valid for panoptic datasets")
        if image_size is not None:
            if len(image_size) != 2:
                raise ValueError("image_size must be (height, width)")
            image_size = (
                _integer(image_size[0], "image height", minimum=1),
                _integer(image_size[1], "image width", minimum=1),
            )
        self.image_size = image_size
        document = json.loads(self.annotation_path.read_text())
        if not isinstance(document, dict):
            raise ValueError("COCO annotations must be a JSON object")
        local_categories = _categories(document.get("categories"), task)
        self.categories = (
            _categories(categories, task) if categories is not None else local_categories
        )
        canonical = {category["id"]: category for category in self.categories}
        for category in local_categories:
            expected = canonical.get(category["id"])
            if expected is None or any(
                category[key] != expected[key] for key in ("name", "isthing")
            ):
                raise ValueError(f"Split category disagrees with training categories: {category!r}")
        self.category_id_to_class_id = {
            category["id"]: index for index, category in enumerate(self.categories)
        }
        self.class_id_to_category_id = {
            index: category["id"] for index, category in enumerate(self.categories)
        }
        self.num_classes = len(self.categories)
        self.thing_ids = {
            index for index, category in enumerate(self.categories) if category["isthing"]
        }
        self.images = _records(document.get("images"), "images", nonempty=True)
        self._by_image: dict[int, list[dict[str, Any]]] = {}
        filenames: set[str] = set()
        for record in self.images:
            image_id = _integer(record.get("id"), "image id")
            if image_id in self._by_image:
                raise ValueError(f"Duplicate image id: {image_id}")
            _integer(record.get("height"), "image height", minimum=1)
            _integer(record.get("width"), "image width", minimum=1)
            _safe_file(self.image_root, record.get("file_name"))
            if record["file_name"] in filenames:
                raise ValueError(f"Duplicate image file_name: {record['file_name']!r}")
            filenames.add(record["file_name"])
            self._by_image[image_id] = []
        annotation_ids: set[int] = set()
        local_ids = {category["id"] for category in local_categories}
        for annotation in _records(document.get("annotations"), "annotations"):
            image_id = _integer(annotation.get("image_id"), "annotation image_id")
            if image_id not in self._by_image:
                raise ValueError(f"Annotation references unknown image_id: {image_id}")
            if task == "instance":
                annotation_id = _integer(annotation.get("id"), "annotation id")
                if annotation_id in annotation_ids:
                    raise ValueError(f"Duplicate annotation id: {annotation_id}")
                annotation_ids.add(annotation_id)
                segments = [annotation]
            else:
                if self._by_image[image_id]:
                    raise ValueError(f"Multiple panoptic annotations for image {image_id}")
                assert self.panoptic_root is not None
                _safe_file(self.panoptic_root, annotation.get("file_name"))
                segments = _records(annotation.get("segments_info"), "segments_info")
            segment_ids: set[int] = set()
            for segment in segments:
                category_id = _integer(segment.get("category_id"), "category_id")
                if category_id not in local_ids:
                    raise ValueError(f"Annotation references undeclared category_id: {category_id}")
                crowd = _flag(segment.get("iscrowd", 0), "iscrowd")
                if task == "panoptic":
                    segment_id = _integer(segment.get("id"), "panoptic segment id", minimum=1)
                    if segment_id >= 256**3 or segment_id in segment_ids:
                        raise ValueError(f"Invalid or duplicate panoptic segment id: {segment_id}")
                    segment_ids.add(segment_id)
                    if crowd and not canonical[category_id]["isthing"]:
                        raise ValueError("Panoptic stuff segments cannot be crowds")
                elif "segmentation" not in segment:
                    raise ValueError("Instance annotation requires segmentation, not only a box")
            self._by_image[image_id].append(annotation)
        if task == "panoptic" and any(not records for records in self._by_image.values()):
            raise ValueError(
                "Every panoptic image needs one annotation (including all-void images)"
            )

    def __len__(self) -> int:
        return len(self.images)

    def _masks(
        self, record: dict[str, Any]
    ) -> tuple[list[int], list[np.ndarray], list[bool], np.ndarray]:
        height, width = record["height"], record["width"]
        annotations = self._by_image[record["id"]]
        class_ids: list[int] = []
        masks: list[np.ndarray] = []
        crowds: list[bool] = []
        if self.task == "instance":
            valid = np.ones((height, width), dtype=np.bool_)
            for annotation in annotations:
                mask = decode_instance_mask(annotation["segmentation"], height, width)
                if not mask.any():
                    raise ValueError(f"Instance annotation {annotation['id']} has an empty mask")
                class_ids.append(self.category_id_to_class_id[annotation["category_id"]])
                masks.append(mask)
                crowds.append(bool(annotation.get("iscrowd", 0)))
        else:
            assert self.panoptic_root is not None
            annotation = annotations[0]
            with Image.open(_safe_file(self.panoptic_root, annotation["file_name"])) as png:
                if png.format != "PNG" or png.mode != "RGB":
                    raise ValueError("Panoptic masks must be RGB PNGs encoding 24-bit segment IDs")
                if png.size != (width, height):
                    raise ValueError("Panoptic PNG dimensions differ from image metadata")
                rgb = np.asarray(png, dtype=np.uint32)
            ids = rgb[:, :, 0] + 256 * rgb[:, :, 1] + 256**2 * rgb[:, :, 2]
            present = set(np.unique(ids).tolist()) - {0}
            declared = {segment["id"] for segment in annotation["segments_info"]}
            if present != declared:
                raise ValueError(
                    f"Panoptic PNG IDs disagree with segments_info: "
                    f"undeclared={sorted(present - declared)}, missing={sorted(declared - present)}"
                )
            valid = ids != 0
            stuff_index: dict[int, int] = {}
            for segment in annotation["segments_info"]:
                class_id = self.category_id_to_class_id[segment["category_id"]]
                mask = ids == segment["id"]
                if "area" in segment:
                    area = _integer(segment["area"], "panoptic segment area", minimum=1)
                    if area != int(mask.sum()):
                        raise ValueError(
                            f"Panoptic segment {segment['id']} area disagrees with PNG"
                        )
                if class_id in stuff_index:
                    masks[stuff_index[class_id]] |= mask
                    continue
                if class_id not in self.thing_ids:
                    stuff_index[class_id] = len(masks)
                class_ids.append(class_id)
                masks.append(mask)
                crowds.append(bool(segment.get("iscrowd", 0)))
        return class_ids, masks, crowds, valid

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.images[index]
        original_size = (record["height"], record["width"])
        with Image.open(_safe_file(self.image_root, record["file_name"])) as source:
            if source.size != (original_size[1], original_size[0]):
                raise ValueError(f"Image dimensions differ from metadata: {record['file_name']}")
            image = source.convert("RGB")
        class_ids, masks, crowds, valid = self._masks(record)
        size = self.image_size or original_size
        if size != original_size:
            pil_size = (size[1], size[0])
            masks = [
                np.asarray(Image.fromarray(mask).resize(pil_size, Image.Resampling.NEAREST)).copy()
                for mask in masks
            ]
            valid = np.asarray(
                Image.fromarray(valid).resize(pil_size, Image.Resampling.NEAREST)
            ).copy()
            if any(not mask.any() for mask in masks):
                raise ValueError(
                    f"Resizing {record['file_name']} to {size} erased an annotated segment; "
                    "use a larger image_size or native resolution"
                )
        image_tensor = preprocess_image(image, size)
        mask_array = np.stack(masks) if masks else np.zeros((0, *size), dtype=np.bool_)
        target = ObjectTarget(
            class_ids=torch.tensor(class_ids, dtype=torch.long),
            masks=torch.from_numpy(np.ascontiguousarray(mask_array)),
            valid=torch.from_numpy(np.ascontiguousarray(valid)),
            iscrowd=torch.tensor(crowds, dtype=torch.bool),
            image_id=record["id"],
            original_size=original_size,
        )
        return {"image": image_tensor, "target": target, "key": record["file_name"]}


def collate_objects(samples: list[dict[str, Any]]) -> tuple[Tensor, list[ObjectTarget], list[str]]:
    """Stack equally sized images while preserving variable object counts."""
    if not samples:
        raise ValueError("Cannot collate an empty object batch")
    shapes = {tuple(sample["image"].shape) for sample in samples}
    if len(shapes) != 1:
        raise ValueError(
            "Object batch image sizes differ; configure image_size or use batch_size=1"
        )
    return (
        torch.stack([sample["image"] for sample in samples]),
        [sample["target"] for sample in samples],
        [sample["key"] for sample in samples],
    )
