#!/usr/bin/env python3
"""Bounded real-image GPU forward/backward validation; random tiny models, not accuracy benchmarks."""

from __future__ import annotations

import argparse
import gc
import json
import time
from pathlib import Path
from typing import Any, cast

import torch
from transformers import (
    DetrConfig,
    EomtConfig,
    EomtDinov3Config,
    EomtDinov3ForUniversalSegmentation,
    EomtForUniversalSegmentation,
    Mask2FormerConfig,
    Mask2FormerForUniversalSegmentation,
    MaskFormerConfig,
    MaskFormerForInstanceSegmentation,
    SwinConfig,
)

from segmentary.models.mask_classification import MaskClassWrapper
from segmentary.objects.checkpoint_model import model_spec
from segmentary.objects.continuation import rng_state
from segmentary.objects.data import ObjectDataset, resize_image_tensor
from segmentary.objects.loss import ObjectQueryLoss
from segmentary.objects.model_factory import wrap_object_model
from segmentary.objects.runner import _save_checkpoint, file_digest, query_output, write_json
from segmentary.utils.seed import seed_everything

FAMILIES = ("eomt_large", "eomt_dinov3_large", "maskformer_swin_tiny", "mask2former_swin_tiny")


def tiny_architecture(arch: str, classes: int, queries: int, size: tuple[int, int]):
    """Explicit small architecture configurations; never downloads weights or remote code."""
    config: Any
    model: Any
    if arch.startswith("eomt"):
        dino = arch == "eomt_dinov3_large"
        config_type = cast(Any, EomtDinov3Config if dino else EomtConfig)
        model_type = cast(
            Any, EomtDinov3ForUniversalSegmentation if dino else EomtForUniversalSegmentation
        )
        config = config_type(
            hidden_size=32,
            num_hidden_layers=2,
            num_attention_heads=4,
            image_size=min(size),
            patch_size=16,
            num_blocks=1,
            num_upscale_blocks=1,
            num_queries=queries,
            num_register_tokens=0,
            num_labels=classes,
            intermediate_size=64,
        )
        return MaskClassWrapper(
            model_type(config),
            classes,
            backbone_paths=("embeddings", "layers"),
            head_paths=("class_predictor", "mask_head", "query"),
            native_size=(min(size), min(size)),
        )
    backbone = cast(Any, SwinConfig)(
        embed_dim=32,
        depths=[1, 1, 1, 1],
        num_heads=[1, 2, 4, 8],
        window_size=2,
        out_indices=[1, 2, 3, 4],
        drop_path_rate=0,
    )
    if arch == "mask2former_swin_tiny":
        config = cast(Any, Mask2FormerConfig)(
            backbone_config=backbone,
            feature_size=32,
            mask_feature_size=32,
            hidden_dim=32,
            encoder_feedforward_dim=64,
            encoder_layers=1,
            decoder_layers=2,
            num_attention_heads=4,
            dim_feedforward=64,
            num_queries=queries,
            num_labels=classes,
        )
        model = Mask2FormerForUniversalSegmentation(config)
    elif arch == "maskformer_swin_tiny":
        config = cast(Any, MaskFormerConfig)(
            backbone_config=backbone,
            decoder_config=DetrConfig(
                d_model=32,
                decoder_layers=2,
                decoder_attention_heads=4,
                decoder_ffn_dim=64,
                num_queries=queries,
            ),
            fpn_feature_size=32,
            mask_feature_size=32,
            num_labels=classes,
            use_auxiliary_loss=True,
        )
        model = MaskFormerForInstanceSegmentation(config)
    else:
        raise ValueError(f"Unknown family: {arch}")
    return wrap_object_model(model, arch, classes)


def positive(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for split in ("train", "val"):
        parser.add_argument(f"--{split}-images", type=Path, required=True)
        parser.add_argument(f"--{split}-annotations", type=Path, required=True)
        parser.add_argument(f"--{split}-panoptic-masks", type=Path)
    parser.add_argument("--task", choices=("instance", "panoptic"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument(
        "--memory-fraction",
        type=float,
        default=0.15,
        help="CUDA allocator fraction cap; does not reserve free memory",
    )
    parser.add_argument("--allow-cpu", action="store_true", help="Local harness testing only")
    parser.add_argument("--models", nargs="+", choices=FAMILIES, default=list(FAMILIES))
    parser.add_argument("--steps", type=positive, default=2)
    parser.add_argument("--limit", type=positive, default=2)
    parser.add_argument("--height", type=positive, default=256)
    parser.add_argument("--width", type=positive, default=512)
    parser.add_argument("--accumulation", type=positive, default=2)
    parser.add_argument(
        "--precision", choices=("float32", "float16", "bfloat16"), default="float32"
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    device = torch.device(args.device)
    if device.type != "cuda" and not args.allow_cpu:
        parser.error("GPU validation requires CUDA; --allow-cpu is only for testing the harness")
    if args.precision == "float16" and device.type != "cuda":
        parser.error("float16 requires CUDA")
    if args.height % 32 or args.width % 32:
        parser.error("Input height and width must be divisible by 32")
    if not 0 < args.memory_fraction <= 1:
        parser.error("memory-fraction must be in (0,1]")
    if device.type == "cuda":
        torch.cuda.set_per_process_memory_fraction(args.memory_fraction, device)
    training = ObjectDataset(
        args.train_images, args.train_annotations, args.task, args.train_panoptic_masks
    )
    validation = ObjectDataset(
        args.val_images,
        args.val_annotations,
        args.task,
        args.val_panoptic_masks,
        categories=training.categories,
    )
    train_samples = [training[i] for i in range(min(args.limit, len(training)))]
    val_samples = [validation[i] for i in range(min(args.limit, len(validation)))]
    train_digests = {file_digest(training.image_root / row["file_name"]) for row in training.images}
    if any(
        file_digest(validation.image_root / row["file_name"]) in train_digests
        for row in validation.images
    ):
        raise ValueError("Real-data smoke requires disjoint train and validation images")
    queries = max(16, max(int(sample["target"].class_ids.numel()) for sample in train_samples) + 8)
    content_hashes = {}
    for split, source, samples in (
        ("train", training, train_samples),
        ("val", validation, val_samples),
    ):
        chosen = {sample["target"].image_id for sample in samples}
        hashes = {
            "images": {
                row["file_name"]: file_digest(source.image_root / row["file_name"])
                for row in source.images
                if row["id"] in chosen
            }
        }
        if source.panoptic_root:
            document = json.loads(source.annotation_path.read_text())
            hashes["panoptic_masks"] = {
                row["file_name"]: file_digest(source.panoptic_root / row["file_name"])
                for row in document["annotations"]
                if row["image_id"] in chosen
            }
        content_hashes[split] = hashes
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    size = (args.height, args.width)
    metadata = {
        "purpose": "real-data GPU execution smoke; random tiny architectures; not benchmark accuracy",
        "arguments": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
        "categories": training.categories,
        "content_sha256": content_hashes,
        "torch": str(torch.__version__),
        "device_name": torch.cuda.get_device_name(device)
        if device.type == "cuda"
        else "CPU harness test",
        "annotation_sha256": {
            split: file_digest(getattr(args, f"{split}_annotations")) for split in ("train", "val")
        },
        "image_ids": {
            "train": [sample["target"].image_id for sample in train_samples],
            "val": [sample["target"].image_id for sample in val_samples],
        },
        "target_protocol": "Native-resolution masks unchanged; only RGB model input resized",
        "num_queries": queries,
        "results": results,
    }
    for arch in args.models:
        seed_everything(args.seed)
        model = tiny_architecture(arch, training.num_classes, queries, size).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
        criterion = ObjectQueryLoss(training.num_classes, num_points=256)
        scaler = torch.amp.GradScaler("cuda", enabled=args.precision == "float16")
        dtype = torch.float16 if args.precision == "float16" else torch.bfloat16
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(device)
            torch.cuda.synchronize(device)
        started = time.monotonic()
        losses, completed, attempts = [], 0, 0
        model.train()
        while completed < args.steps:
            attempts += 1
            if attempts > args.steps + 20:
                raise FloatingPointError("Too many FP16 overflow attempts")
            optimizer.zero_grad(set_to_none=True)
            step_loss = 0.0
            for micro in range(args.accumulation):
                sample = train_samples[
                    ((attempts - 1) * args.accumulation + micro) % len(train_samples)
                ]
                image = resize_image_tensor(sample["image"], size)[None].to(device)
                target = sample["target"].to(device)
                with torch.autocast(device.type, dtype=dtype, enabled=args.precision != "float32"):
                    loss = criterion(query_output(model, image), [target]) / args.accumulation
                if not torch.isfinite(loss):
                    raise FloatingPointError(f"Non-finite {arch} loss")
                scaler.scale(loss).backward()
                step_loss += float(loss.detach())
            scaler.unscale_(optimizer)
            norm = torch.nn.utils.clip_grad_norm_(
                model.parameters(), 1.0, error_if_nonfinite=not scaler.is_enabled()
            )
            scale = scaler.get_scale()
            scaler.step(optimizer)
            scaler.update()
            if scaler.is_enabled() and scaler.get_scale() < scale:
                continue
            if not torch.isfinite(norm) or norm <= 0:
                raise FloatingPointError(f"Invalid {arch} gradient norm")
            completed += 1
            losses.append({"step": completed, "loss": step_loss, "gradient_norm": float(norm)})
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        wall = time.monotonic() - started
        model.eval()
        with torch.inference_mode():
            for sample in val_samples:
                raw = query_output(
                    model, resize_image_tensor(sample["image"], size)[None].to(device)
                ).primary
                if (
                    not torch.isfinite(raw.class_logits).all()
                    or not torch.isfinite(raw.mask_logits).all()
                ):
                    raise FloatingPointError(f"Non-finite held-out {arch} predictions")
        checkpoint = args.output / f"{arch}.pt"
        _save_checkpoint(
            checkpoint,
            {
                "schema": "segmentary-object-gpu-smoke-v1",
                "architecture": model_spec(model),
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scaler": scaler.state_dict(),
                "rng": rng_state(),
                "steps": completed,
            },
        )
        results.append(
            {
                "family": arch,
                "initialization": "random tiny configuration",
                "status": "passed",
                "architecture": model_spec(model),
                "losses": losses,
                "optimizer_steps": completed,
                "attempts": attempts,
                "train_wall_clock_s": wall,
                "validation_forward_finite": True,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(device)
                if device.type == "cuda"
                else None,
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(device)
                if device.type == "cuda"
                else None,
                "checkpoint": checkpoint.name,
                "checkpoint_sha256": file_digest(checkpoint),
            }
        )
        write_json(args.output / "results.json", metadata)
        print(json.dumps({"family": arch, "status": "passed", "steps": completed}), flush=True)
        del model, optimizer, criterion, scaler, loss, raw, image, target
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()
    return metadata


if __name__ == "__main__":
    main()
