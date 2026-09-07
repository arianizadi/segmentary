"""Reproducible object-task evaluation pages and linked comparison indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

from ..utils.provenance import git_sha
from .config import ObjectConfig, load_config
from .data import ObjectDataset, resize_image_tensor
from .metrics import InstanceMetrics, PanopticMetrics
from .prediction import postprocess
from .runner import dataset, file_digest, load_checkpoint, query_output, write_json


def _percent(value: Any) -> str:
    return "—" if value is None else f"{100 * value:.2f}"


def _number(value: Any) -> str:
    return "—" if value is None else f"{value:.2f}"


def _text(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _sync(device: str) -> None:
    if torch.device(device).type == "cuda":
        torch.cuda.synchronize(device)
    elif torch.device(device).type == "mps":
        torch.mps.synchronize()


def _cpu(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.detach().cpu() if isinstance(value, torch.Tensor) else value
        for key, value in result.items()
    }


def _timing(values: list[float]) -> dict[str, Any]:
    return {
        "images": len(values),
        "total_s": sum(values),
        "fps": len(values) / sum(values),
        "mean_ms": 1000 * float(np.mean(values)),
        "median_ms": 1000 * float(np.median(values)),
        "p95_ms": 1000 * float(np.percentile(values, 95)),
        "per_image_s": values,
    }


def _fingerprint(data: ObjectDataset) -> dict[str, Any]:
    files = {"annotations": file_digest(data.annotation_path)}
    for row in data.images:
        files["image/" + row["file_name"]] = file_digest(data.image_root / row["file_name"])
    if data.panoptic_root is not None:
        document = json.loads(data.annotation_path.read_text())
        for row in document["annotations"]:
            files["mask/" + row["file_name"]] = file_digest(data.panoptic_root / row["file_name"])
    return {
        "sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
        "files_sha256": files,
    }


def _export(
    result: dict, image_id: int, categories: list[dict], task: str, output: Path
) -> list[dict]:
    if task == "panoptic":
        ids = result["segmentation"].numpy().astype(np.uint32)
        if ids.max(initial=0) >= 2**24:
            raise ValueError("Panoptic segment IDs must fit RGB encoding")
        rgb = np.stack([ids % 256, ids // 256 % 256, ids // 65536 % 256], axis=-1).astype(np.uint8)
        filename = f"{image_id}.png"
        Image.fromarray(rgb).save(output / filename)
        segments = [
            {
                **s,
                "category_id": categories[s["category_id"]]["id"],
                "area": int((ids == s["id"]).sum()),
                "iscrowd": 0,
            }
            for s in result["segments_info"]
        ]
        return [{"image_id": image_id, "file_name": filename, "segments_info": segments}]
    from pycocotools import mask as mask_utils

    rows = []
    for mask, label, score in zip(
        result["masks"], result["class_ids"], result["scores"], strict=True
    ):
        rle = mask_utils.encode(np.asfortranarray(mask.numpy().astype(np.uint8)))
        rle["counts"] = rle["counts"].decode("ascii")
        rows.append(
            {
                "image_id": image_id,
                "category_id": categories[int(label)]["id"],
                "score": float(score),
                "segmentation": rle,
            }
        )
    return rows


def markdown(report: dict) -> str:
    task, metrics = report["task"], report["metrics"]
    names = (
        [("map", "Mask AP"), ("map_50", "AP50"), ("map_75", "AP75"), ("mar_100", "AR100")]
        if task == "instance"
        else [("pq", "PQ"), ("sq", "SQ"), ("rq", "RQ")]
    )
    lines = [
        f"# {_text(report['name'])}",
        "",
        f"{task.title()} segmentation; {metrics['images']} validation images. Scores are percentages.",
        "",
        "| " + " | ".join(name for _, name in names) + " |",
        "| " + " | ".join("---:" for _ in names) + " |",
        "| " + " | ".join(_percent(metrics.get(key)) for key, _ in names) + " |",
        "",
        "## Per-class results",
        "",
        "| Class | Kind | "
        + " | ".join(name for _, name in names)
        + (" | GT objects |" if task == "instance" else " | TP | FP | FN |"),
        "| --- | --- | "
        + " | ".join("---:" for _ in names)
        + (" | ---: |" if task == "instance" else " | ---: | ---: | ---: |"),
    ]
    for index, category in enumerate(report["categories"]):
        row = metrics["per_class"].get(str(index), {})
        extra = (
            str(row.get("support", "—"))
            if task == "instance"
            else " | ".join(str(row.get(key, "—")) for key in ("tp", "fp", "fn"))
        )
        lines.append(
            f"| {_text(category['name'])} | {'thing' if category['isthing'] else 'stuff'} | "
            + " | ".join(_percent(row.get(key)) for key, _ in names)
            + " | "
            + extra
            + " |"
        )
    if task == "panoptic":
        lines += [
            "",
            "| Group | PQ | SQ | RQ | Evaluated classes |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for group in ("things", "stuff"):
            row = metrics[group]
            lines.append(
                f"| {group} | {_percent(row['pq'])} | {_percent(row['sq'])} | {_percent(row['rq'])} | {row['classes']} |"
            )
    resources = report["resources"]
    lines += [
        "",
        "## Speed and memory",
        "",
        "| Measurement | FPS | Mean ms | Median ms | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in ("model_only", "end_to_end"):
        row = resources[name]
        lines.append(
            f"| {name.replace('_', ' ')} | "
            + " | ".join(_number(row[key]) for key in ("fps", "mean_ms", "median_ms", "p95_ms"))
            + " |"
        )
    for key, label in (
        ("peak_allocated_bytes", "Peak allocated VRAM (GiB)"),
        ("peak_reserved_bytes", "Peak reserved VRAM (GiB)"),
    ):
        value = resources.get(key)
        lines += ["", f"{label}: {_number(value / 2**30 if value is not None else None)}."]
    lines += [
        "",
        _text(resources["protocol"]),
        "",
        f"Hardware: {_text(resources['hardware'])}. GPU exclusivity was not enforced; concurrent jobs can affect speed and available memory. VRAM is this process's PyTorch allocator peak, including loaded model weights, not total device usage or training VRAM.",
        "",
        "## Provenance",
        "",
        f"- Checkpoint SHA256: `{report['provenance']['checkpoint_sha256']}`",
        f"- Checkpoint step: {report['provenance'].get('checkpoint_step') if report['provenance'].get('checkpoint_step') is not None else '—'}",
        f"- Dataset fingerprint: `{report['dataset']['sha256']}`",
        f"- Architecture: `{_text(report['config']['model']['arch'])}`",
        f"- Initializer configuration: `{_text(json.dumps(report['config']['model'], sort_keys=True))}`",
        f"- Evaluation code: `{report['provenance']['git_sha']}`; dirty: {report['provenance']['git_dirty']}",
        "",
        "Full resolved configuration, embedded checkpoint architecture, category mapping, thresholds, seed, package versions, hardware, per-image timings and input file hashes: [report.json](report.json). Exported native predictions: [predictions.json](predictions/predictions.json).",
        "",
        "## Reference evaluator",
        "",
    ]
    reference = report.get("reference")
    lines += [
        f"{'PASS' if reference['passed'] else 'FAIL'}: {_text(reference['implementation'])}; absolute tolerance {reference['tolerance']}. Details are recorded in report.json."
        if reference
        else "Not requested; reference equivalence has not been established for this report.",
        "",
    ]
    return "\n".join(lines)


@torch.inference_mode()
def run_report(
    config: ObjectConfig,
    checkpoint: Path,
    out: Path,
    *,
    reference: bool = False,
    warmup: int = 3,
    name: str | None = None,
) -> dict:
    if warmup < 1:
        raise ValueError("warmup must be positive")
    for source in (Path(config.val.images), Path(config.val.annotations).parent, checkpoint.parent):
        if out.resolve() == source.resolve() or source.resolve().is_relative_to(out.resolve()):
            raise ValueError("Report output cannot contain input data or checkpoint paths")
    if out.exists():
        raise FileExistsError(out)
    for image_tree in (config.val.images, config.val.panoptic_masks):
        if image_tree and out.resolve().is_relative_to(Path(image_tree).resolve()):
            raise ValueError("Report output must be outside evaluation image/mask trees")
    checkpoint_sha256 = file_digest(checkpoint)
    model = load_checkpoint(config, checkpoint).eval()
    data = dataset(config, config.val, categories=model.object_categories)
    if not len(data):
        raise ValueError("Evaluation dataset must contain images")
    # This metadata is safe-loaded independently; initializer paths are descriptive,
    # not proof of which external bytes were used before checkpoint creation.
    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    checkpoint_metadata = {
        key: saved.get(key)
        for key in ("architecture", "step", "schema", "task", "config", "data_fingerprint")
    }
    del saved
    if file_digest(checkpoint) != checkpoint_sha256:
        raise ValueError("Checkpoint changed while loading; use an immutable checkpoint copy")
    out.mkdir(parents=True, exist_ok=False)
    predictions_dir = out / "predictions"
    predictions_dir.mkdir()
    device_type = torch.device(config.device).type
    warm = data[0]
    warm_image = resize_image_tensor(warm["image"], (config.image_size[0], config.image_size[1]))[
        None
    ].to(config.device)
    for _ in range(warmup):
        query_output(model, warm_image)
    _sync(config.device)
    del warm, warm_image
    if device_type == "cuda":
        torch.cuda.reset_peak_memory_stats(config.device)
    metric = (
        InstanceMetrics(data.num_classes, data.thing_ids)
        if config.task == "instance"
        else PanopticMetrics(data.num_classes, data.thing_ids)
    )
    model_times, total_times, annotations, image_rows = [], [], [], []
    for index, image_row in enumerate(data.images):
        _sync(config.device)
        start = time.perf_counter()
        sample = data[index]
        target = sample["target"]
        tensor = resize_image_tensor(sample["image"], (config.image_size[0], config.image_size[1]))[
            None
        ].to(config.device)
        _sync(config.device)
        model_start = time.perf_counter()
        raw = query_output(model, tensor).primary
        _sync(config.device)
        model_times.append(time.perf_counter() - model_start)
        result = _cpu(
            postprocess(
                raw,
                task=config.task,
                thing_ids=data.thing_ids,
                sizes=[target.original_size],
                score_threshold=config.score_threshold,
                mask_threshold=config.mask_threshold,
                overlap_threshold=config.overlap_threshold,
            )[0]
        )
        _sync(config.device)
        total_times.append(time.perf_counter() - start)
        metric.update(result, target)
        annotations.extend(
            _export(result, target.image_id, data.categories, config.task, predictions_dir)
        )
        image_rows.append(
            {**image_row, "sha256": file_digest(data.image_root / image_row["file_name"])}
        )
        del raw, result, tensor, sample, target
    metrics = metric.compute()
    if file_digest(checkpoint) != checkpoint_sha256:
        raise ValueError("Checkpoint changed during evaluation; report was not published")
    write_json(
        predictions_dir / "predictions.json",
        {
            "task": config.task,
            "categories": data.categories,
            "images": image_rows,
            "annotations": annotations,
            "checkpoint_sha256": checkpoint_sha256,
        },
    )
    if config.task == "instance":
        write_json(predictions_dir / "instances.json", annotations)
    sha, dirty = git_sha(Path(__file__).resolve().parents[3])
    versions: dict[str, str | None] = {}
    for package in ("torch", "torchvision", "transformers", "numpy", "pycocotools", "panopticapi"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    hardware: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "device": config.device,
        "torch_threads": torch.get_num_threads(),
        "cuda_runtime": torch.version.cuda,
    }
    if device_type == "cuda":
        properties = torch.cuda.get_device_properties(config.device)
        free, total = torch.cuda.mem_get_info(config.device)
        hardware.update(
            gpu=properties.name,
            gpu_total_bytes=total,
            gpu_free_bytes_at_end=free,
            compute_capability=[properties.major, properties.minor],
        )
    report = {
        "schema": "segmentary-object-report-v1",
        "name": name or f"{config.model.arch} {config.task}",
        "task": config.task,
        "metrics": metrics,
        "categories": data.categories,
        "config": asdict(config),
        "dataset": _fingerprint(data),
        "provenance": {
            "checkpoint_path": str(checkpoint.resolve()),
            "checkpoint_sha256": checkpoint_sha256,
            "checkpoint_step": checkpoint_metadata["step"],
            "checkpoint_metadata": checkpoint_metadata,
            "initializer_provenance_note": "Initializer configuration is recorded; external initializer file hashes are not guaranteed by older checkpoints.",
            "git_sha": sha,
            "git_dirty": dirty,
            "packages": versions,
        },
        "resources": {
            "model_only": _timing(model_times),
            "end_to_end": _timing(total_times),
            "warmup_forwards": warmup,
            "hardware": hardware,
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(config.device)
            if device_type == "cuda"
            else None,
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(config.device)
            if device_type == "cuda"
            else None,
            "protocol": f"Batch size 1; float32 evaluation; input {config.image_size}; {warmup} untimed model warmup forwards; synchronized CUDA/MPS timing. Model-only excludes resize and transfer. End-to-end includes image/target decoding, normalization, resize, transfer, forward, native-size postprocessing and CPU prediction transfer; excludes metric calculation, hashing and prediction export. File caches are not flushed.",
        },
        "reference": None,
    }
    if reference:
        from .reference import compare_reference

        report["reference"] = compare_reference(data, predictions_dir)
    if file_digest(checkpoint) != checkpoint_sha256:
        raise ValueError("Checkpoint changed before report publication")
    write_json(out / "report.json", report)
    (out / "README.md").write_text(markdown(report))
    return report


def comparison(paths: list[Path], output: Path) -> None:
    """Group by task and exact evaluation-data bytes; link each full report page."""
    groups: dict[tuple[str, str], list[tuple[Path, dict]]] = {}
    for path in paths:
        report = json.loads(path.read_text())
        if report.get("schema") != "segmentary-object-report-v1":
            raise ValueError(f"Unsupported report schema: {path}")
        groups.setdefault((report["task"], report["dataset"]["sha256"]), []).append((path, report))
    lines = [
        "# Object segmentation model comparison",
        "",
        "Scores are percentages. Rows are grouped by task and exact dataset fingerprint; each model links to its full report. Input size, thresholds and hardware are recorded on the model pages. Review those settings before interpreting speed or accuracy differences.",
        "",
    ]
    for (task, fingerprint), rows in sorted(groups.items()):
        keys = ("map", "map_50", "map_75") if task == "instance" else ("pq", "sq", "rq")
        names = ("Mask AP", "AP50", "AP75") if task == "instance" else ("PQ", "SQ", "RQ")
        lines += [
            f"## {task.title()} — dataset `{fingerprint}`",
            "",
            "| Model | "
            + " | ".join(names)
            + " | Model FPS | End-to-end FPS | Peak allocated GiB |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for path, report in rows:
            link = (
                Path(os.path.relpath(path.parent / "README.md", output.parent))
                .as_posix()
                .replace(" ", "%20")
            )
            resources = report["resources"]
            peak = resources.get("peak_allocated_bytes")
            lines.append(
                f"| [{_text(report['name'])}]({link}) | "
                + " | ".join(_percent(report["metrics"].get(key)) for key in keys)
                + f" | {_number(resources['model_only']['fps'])} | {_number(resources['end_to_end']['fps'])} | {_number(peak / 2**30 if peak is not None else None)} |"
            )
        lines.append("")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, nargs="?")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--name")
    parser.add_argument("--compare", nargs="+", type=Path, metavar="REPORT_JSON")
    args = parser.parse_args()
    if args.compare:
        if args.config or args.checkpoint or args.reference:
            parser.error("--compare does not accept config/checkpoint/reference")
        comparison(args.compare, args.out)
    else:
        if not args.config or not args.checkpoint:
            parser.error("Evaluation requires config and --checkpoint")
        report = run_report(
            load_config(args.config),
            args.checkpoint,
            args.out,
            reference=args.reference,
            warmup=args.warmup,
            name=args.name,
        )
        print(args.out / "README.md")
        if report["reference"] and not report["reference"]["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
