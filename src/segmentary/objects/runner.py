"""Explicit single-device training, native-resolution evaluation and COCO prediction export."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader

from ..models.factory import build_model
from ..models.tuning import apply_tuning
from ..utils.provenance import git_sha
from ..utils.seed import seed_everything
from .checkpoint_model import model_spec, restore_model
from .config import ObjectConfig, ObjectDataConfig
from .data import (
    ObjectDataset,
    ObjectTarget,
    _categories,
    collate_objects,
    preprocess_image,
    resize_image_tensor,
)
from .loss import ObjectQueryLoss
from .metrics import InstanceMetrics, PanopticMetrics
from .prediction import postprocess


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def dataset(config: ObjectConfig, data: ObjectDataConfig, *, training=False, categories=None):
    return ObjectDataset(
        images=Path(data.images),
        annotations=Path(data.annotations),
        task=config.task,
        panoptic_masks=Path(data.panoptic_masks) if data.panoptic_masks else None,
        image_size=(config.image_size[0], config.image_size[1]) if training else None,
        categories=categories,
    )


def check_split_overlap(
    config: ObjectConfig, training: ObjectDataset, validation: ObjectDataset
) -> None:
    if config.allow_train_val_overlap:
        return
    train_hashes = {file_digest(training.image_root / row["file_name"]) for row in training.images}
    if any(
        file_digest(validation.image_root / row["file_name"]) in train_hashes
        for row in validation.images
    ):
        raise ValueError(
            "Train and validation contain identical image files; use separate splits. For an explicit memorization check only, set allow_train_val_overlap: true"
        )


def make_model(config: ObjectConfig, num_classes: int):
    model = build_model(config.model, num_classes)
    if not model.supports_query_objective:
        raise ValueError("This model returns semantic logits only; choose an EoMT/query model")
    return apply_tuning(model, config.model).to(config.device)


def target_to(target: ObjectTarget, device: str) -> ObjectTarget:
    return ObjectTarget(
        class_ids=target.class_ids.to(device),
        masks=target.masks.to(device),
        valid=target.valid.to(device),
        iscrowd=target.iscrowd.to(device),
        image_id=target.image_id,
        original_size=target.original_size,
    )


def query_output(model, images):
    output = model.forward_output(images)
    if output.query is None:
        raise ValueError("Object segmentation requires raw query class and mask logits")
    return output.query


@torch.inference_mode()
def evaluate(model, config: ObjectConfig, data: ObjectDataset) -> dict:
    """Resize only model input; match predictions and targets at native resolution."""
    was_training = model.training
    model.eval()
    metrics = (
        InstanceMetrics(data.num_classes, data.thing_ids)
        if config.task == "instance"
        else PanopticMetrics(data.num_classes, data.thing_ids)
    )
    started = time.monotonic()
    try:
        for index in range(len(data)):
            sample = data[index]
            target = sample["target"]
            images = resize_image_tensor(
                sample["image"], (config.image_size[0], config.image_size[1])
            )[None].to(config.device)
            raw = query_output(model, images).primary
            predictions = postprocess(
                raw,
                task=config.task,
                thing_ids=data.thing_ids,
                sizes=[target.original_size],
                score_threshold=config.score_threshold,
                mask_threshold=config.mask_threshold,
                overlap_threshold=config.overlap_threshold,
            )
            metrics.update(predictions[0], target)
        result = metrics.compute()
        result["wall_clock_s"] = time.monotonic() - started
        return result
    finally:
        model.train(was_training)


def provenance(config: ObjectConfig, train: ObjectDataset, val: ObjectDataset) -> dict:
    sha, dirty = git_sha(Path(__file__).resolve().parents[3])
    return {
        "config": asdict(config),
        "config_sha256": hashlib.sha256(
            json.dumps(asdict(config), sort_keys=True).encode()
        ).hexdigest(),
        "git_sha": sha,
        "git_dirty": dirty,
        "model_native_size": None,
        "torch": str(torch.__version__),
        "categories": train.categories,
        "annotations_sha256": {
            "train": hashlib.sha256(Path(config.train.annotations).read_bytes()).hexdigest(),
            "val": hashlib.sha256(Path(config.val.annotations).read_bytes()).hexdigest(),
        },
        "train_images": len(train),
        "val_images": len(val),
        "protocol": "single-device float32 AdamW; fixed resize; no augmentation, EMA, TTA or sliding windows; native-resolution validation",
    }


def train(config: ObjectConfig) -> dict:
    """Start a new isolated run; existing output directories are never overwritten."""
    seed_everything(config.seed)
    train_data = dataset(config, config.train, training=True)
    val_data = dataset(config, config.val, categories=train_data.categories)
    check_split_overlap(config, train_data, val_data)
    # Fail before model construction if any annotation is invalid.
    for data in (train_data, val_data):
        for _ in data:
            pass
    out = Path(config.output)
    out.mkdir(parents=True, exist_ok=False)
    record = provenance(config, train_data, val_data)
    write_json(out / "config.json", record)
    model = make_model(config, train_data.num_classes)
    architecture = model_spec(model)
    record["model_native_size"] = getattr(model, "native_size", None)
    write_json(out / "config.json", record)
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=config.lr,
        weight_decay=config.weight_decay,
    )
    criterion = ObjectQueryLoss(train_data.num_classes, num_points=config.num_points)
    loader = DataLoader(
        train_data,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=0,
        collate_fn=collate_objects,
        generator=torch.Generator().manual_seed(config.seed),
    )
    iterator = iter(loader)
    best, best_step = -1.0, 0
    history: list[dict] = []
    started = time.monotonic()
    if str(config.device).startswith("cuda"):
        torch.cuda.reset_peak_memory_stats(config.device)
    for step in range(1, config.max_steps + 1):
        try:
            images, targets, _ = next(iterator)
        except StopIteration:
            iterator = iter(loader)
            images, targets, _ = next(iterator)
        model.train()
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(
            query_output(model, images.to(config.device)),
            [target_to(t, config.device) for t in targets],
        )
        if not torch.isfinite(loss):
            raise FloatingPointError(f"Non-finite object loss at step {step}")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
        optimizer.step()
        entry: dict = {"step": step, "loss": float(loss.detach())}
        if step % config.val_every == 0 or step == config.max_steps:
            entry["validation"] = evaluate(model, config, val_data)
            score = entry["validation"]["map" if config.task == "instance" else "pq"]
            checkpoint = {
                "schema": "segmentary-objects-v1",
                "architecture": architecture,
                "task": config.task,
                "categories": train_data.categories,
                "config": asdict(config),
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "step": step,
            }
            if score is not None and score > best:
                best, best_step = score, step
                _save_checkpoint(out / "best.pt", checkpoint)
            _save_checkpoint(out / "last.pt", checkpoint)
        history.append(entry)
        write_json(out / "history.json", history)
    result = {
        **record,
        "status": "completed",
        "steps": config.max_steps,
        "selection_metric": "mask_AP" if config.task == "instance" else "PQ",
        "best_metric": best if best_step else None,
        "best_step": best_step or None,
        "wall_clock_s": time.monotonic() - started,
        "history": history,
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(config.device)
        if str(config.device).startswith("cuda")
        else None,
    }
    write_json(out / "results.json", result)
    return result


def _save_checkpoint(path: Path, checkpoint: dict) -> None:
    temporary = path.with_suffix(".tmp")
    torch.save(checkpoint, temporary)
    temporary.replace(path)


def load_checkpoint(config: ObjectConfig, path: Path, categories: list[dict] | None = None):
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint.get("schema") != "segmentary-objects-v1" or checkpoint.get("task") != config.task:
        raise ValueError("Checkpoint does not match this object segmentation task/schema")
    saved_categories = _categories(checkpoint.get("categories"), config.task)
    if categories is not None and saved_categories != categories:
        raise ValueError("Checkpoint category mapping differs from the dataset")
    if checkpoint["config"]["model"] != asdict(config.model):
        raise ValueError("Checkpoint model configuration differs")
    model = restore_model(checkpoint["architecture"], config.model, len(saved_categories)).to(
        config.device
    )
    cast(Any, model).object_categories = saved_categories
    model.load_state_dict(checkpoint["model"], strict=True)
    return model


@torch.inference_mode()
def predict(config: ObjectConfig, checkpoint: Path, images: Path, output: Path) -> dict:
    """Export native-size panoptic RGB IDs + metadata, or COCO instance RLE masks."""
    model = load_checkpoint(config, checkpoint)
    categories = model.object_categories
    thing_ids = {i for i, category in enumerate(categories) if category["isthing"]}
    model.eval()
    images, output = images.resolve(), output.resolve()
    if output.is_relative_to(images) or images.is_relative_to(output):
        raise ValueError("Prediction output must be separate from the input image tree")
    paths = sorted(p for p in images.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not paths:
        raise ValueError("No images found")
    output.mkdir(parents=True, exist_ok=False)
    records = []
    image_records = []
    for image_id, path in enumerate(paths, 1):
        with Image.open(path) as image:
            width, height = image.size
            tensor = preprocess_image(image, (config.image_size[0], config.image_size[1]))[None]
        image_records.append(
            {
                "id": image_id,
                "file_name": str(path.relative_to(images)),
                "width": width,
                "height": height,
                "sha256": file_digest(path),
            }
        )
        result = postprocess(
            query_output(model, tensor.to(config.device)).primary,
            task=config.task,
            thing_ids=thing_ids,
            sizes=[(height, width)],
            score_threshold=config.score_threshold,
            mask_threshold=config.mask_threshold,
            overlap_threshold=config.overlap_threshold,
        )[0]
        if config.task == "panoptic":
            ids = result["segmentation"].cpu().numpy().astype(np.uint32)
            rgb_ids = np.stack([ids % 256, ids // 256 % 256, ids // 65536 % 256], axis=-1).astype(
                np.uint8
            )
            filename = f"{image_id:08d}.png"
            Image.fromarray(rgb_ids).save(output / filename)
            segments = [
                {
                    **s,
                    "category_id": categories[s["category_id"]]["id"],
                    "area": int((ids == s["id"]).sum()),
                    "iscrowd": 0,
                }
                for s in result["segments_info"]
            ]
            records.append({"image_id": image_id, "file_name": filename, "segments_info": segments})
        else:
            from pycocotools import mask as mask_utils

            for mask, label, score in zip(
                result["masks"], result["class_ids"], result["scores"], strict=True
            ):
                rle = mask_utils.encode(np.asfortranarray(mask.cpu().numpy().astype(np.uint8)))
                rle["counts"] = rle["counts"].decode("ascii")
                records.append(
                    {
                        "image_id": image_id,
                        "category_id": categories[int(label)]["id"],
                        "score": float(score),
                        "segmentation": rle,
                    }
                )
    manifest = {
        "task": config.task,
        "categories": categories,
        "images": image_records,
        "annotations": records,
        "checkpoint_sha256": file_digest(checkpoint),
        "inference_config": asdict(config),
    }
    write_json(output / "predictions.json", manifest)
    if config.task == "instance":
        write_json(output / "instances.json", records)
    return manifest
