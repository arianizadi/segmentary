"""Export one validation scene for pixel-level comparison in an external viewer.

This command deliberately reuses Segmentary's evaluation data path and inference
functions.  The exported ground truth is therefore in the canonical taxonomy and
the prediction is produced by the same native-resolution whole/sliding protocol as
``segmentary-eval``.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import torch
from PIL import Image

from .config import DataConfig, config_hash, deep_merge, load_experiment, to_dict
from .data.loaders import aug_from_spec, build_dataset, input_normalization, load_data_mapping
from .data.transforms import build_eval_transform
from .engine.inference import InferenceConfig, inference, prediction_from_inference
from .eval import load_configured_checkpoint
from .models.factory import build_model
from .tasks import validate_canonical_active, validate_task_configuration, validate_task_space
from .taxonomy import LabelSpace, load_space
from .train import parse_override
from .utils.provenance import discover_git_root, git_sha
from .utils.seed import seed_everything

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RESERVED_NAMES = {"config", "gt", "input", "scene"}
_INPUT_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_PROTOCOL_FIELDS = (
    "native_resolution",
    "configured_inference",
    "execution",
    "window",
    "stride",
    "tta",
    "task",
    "threshold",
    "autocast",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            os.fchmod(fh.fileno(), 0o644)
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _png_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    Image.fromarray(array).save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON from existing {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"existing {path} must contain a JSON object")
    return value


def _write_identical_or_new(path: Path, payload: bytes, *, description: str) -> None:
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise FileExistsError(
                f"{path} already exists with different {description}; choose another output root"
            )
        return
    _atomic_bytes(path, payload)


def _input_candidates(scene_dir: Path) -> list[Path]:
    if not scene_dir.is_dir():
        return []
    return sorted(
        path
        for path in scene_dir.iterdir()
        if path.is_file()
        and path.stem.lower() == "input"
        and path.suffix.lower() in _INPUT_SUFFIXES
    )


def _manifest_artifact(
    scene_doc: dict[str, Any], kind: str, scene_dir: Path, expected_path: Path
) -> None:
    artifacts = scene_doc.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get(kind), dict):
        raise ValueError(f"{scene_dir / 'scene.json'} has no artifacts.{kind} object")
    record = artifacts[kind]
    if record.get("file") != expected_path.name:
        raise ValueError(
            f"{scene_dir / 'scene.json'} records artifacts.{kind}.file="
            f"{record.get('file')!r}, but the artifact is {expected_path.name!r}"
        )
    expected_sha = record.get("sha256")
    if not isinstance(expected_sha, str) or expected_sha != _sha256_file(expected_path):
        raise ValueError(
            f"{scene_dir / 'scene.json'} artifacts.{kind} SHA-256 does not match "
            f"{expected_path.name}"
        )


def _validate_existing_scene(
    scene_dir: Path,
    data: DataConfig,
    split: str,
    space: LabelSpace,
    *,
    canonical_root: bool,
) -> None:
    manifest = scene_dir / "scene.json"
    inputs = _input_candidates(scene_dir)
    gt_path = scene_dir / "gt.png"
    prediction_pngs = [
        path for path in scene_dir.glob("*.png") if path.name != "gt.png" and path not in inputs
    ]
    looks_like_scene = bool(inputs or gt_path.exists() or prediction_pngs)
    if not manifest.exists():
        if looks_like_scene:
            if canonical_root:
                raise ValueError(
                    f"{scene_dir} is an incomplete Segmentary scene: canonical artifacts exist "
                    "but scene.json was never committed. Remove this scene directory and retry; "
                    "a manifest-free partial export cannot be resumed safely."
                )
            raise ValueError(
                f"{scene_dir} looks like a legacy comparison scene but has no compatible "
                "Segmentary scene.json. Use a new empty canonical export root; do not mix "
                "canonical predictions with legacy native-ID artifacts."
            )
        return
    scene_doc = _read_json(manifest)
    expected_identity = {
        "schema_version": 1,
        "dataset": data.name,
        "split": split,
        "taxonomy": space.name,
    }
    for field, expected in expected_identity.items():
        if scene_doc.get(field) != expected:
            raise ValueError(
                f"existing {manifest} has {field}={scene_doc.get(field)!r}, expected {expected!r}"
            )
    if not isinstance(scene_doc.get("frame_key"), str) or not scene_doc["frame_key"]:
        raise ValueError(f"existing {manifest} has no non-empty frame_key")
    predictions = scene_doc.get("predictions")
    if not isinstance(predictions, dict):
        raise ValueError(f"existing {manifest} has no predictions object")
    if len(inputs) != 1:
        raise ValueError(
            f"{scene_dir} must contain exactly one input image named input.jpg/jpeg/png/webp; "
            f"found {[path.name for path in inputs]}"
        )
    if not gt_path.is_file():
        raise ValueError(f"existing {manifest} references a scene without gt.png")
    _manifest_artifact(scene_doc, "input", scene_dir, inputs[0])
    _manifest_artifact(scene_doc, "ground_truth", scene_dir, gt_path)
    recorded_prediction_files: set[Path] = set()
    for name, record in predictions.items():
        if not isinstance(name, str) or not isinstance(record, dict):
            raise ValueError(f"existing {manifest} contains a malformed prediction record")
        filename = record.get("file")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError(
                f"existing prediction {name!r} in {manifest} has unsafe file {filename!r}"
            )
        prediction_path = scene_dir / filename
        if prediction_path.suffix.lower() != ".png" or not prediction_path.is_file():
            raise ValueError(
                f"existing prediction {name!r} in {manifest} has no PNG artifact {filename!r}"
            )
        if record.get("sha256") != _sha256_file(prediction_path):
            raise ValueError(
                f"existing prediction {name!r} SHA-256 does not match {prediction_path.name}"
            )
        recorded_prediction_files.add(prediction_path)
    if set(prediction_pngs) != recorded_prediction_files:
        raise ValueError(
            f"{scene_dir} prediction PNGs and {manifest.name} records differ; "
            f"files={sorted(path.name for path in prediction_pngs)}, "
            f"records={sorted(path.name for path in recorded_prediction_files)}"
        )


def _validate_output_root(
    output_root: Path,
    data: DataConfig,
    split: str,
    space: LabelSpace,
    expected_config: dict[str, Any],
) -> None:
    if not output_root.exists():
        return
    if not output_root.is_dir():
        raise ValueError(f"comparison output root is not a directory: {output_root}")
    legacy_configs = [
        path for path in output_root.iterdir() if path.name.lower() == "rs19-config.json"
    ]
    if legacy_configs:
        raise ValueError(
            f"{legacy_configs[0]} is a legacy RailSem native-ID class config. Export into a "
            "new empty canonical root; canonical rail_union ids diverge from native ids."
        )
    config_path = output_root / "config.json"
    canonical_root = False
    if config_path.exists():
        existing_config = _read_json(config_path)
        if existing_config != expected_config:
            raise ValueError(
                f"existing {config_path} differs from this canonical dataset/taxonomy config; "
                "use a separate empty output root"
            )
        canonical_root = True
    for child in sorted(path for path in output_root.iterdir() if path.is_dir()):
        _validate_existing_scene(child, data, split, space, canonical_root=canonical_root)


def _resolve_input_artifact(scene_dir: Path, raw_image: np.ndarray) -> tuple[Path, bytes | None]:
    candidates = _input_candidates(scene_dir)
    if len(candidates) > 1:
        raise ValueError(
            f"{scene_dir} contains conflicting input images {[path.name for path in candidates]}; "
            "keep exactly one input.jpg/jpeg/png/webp"
        )
    if not candidates:
        return scene_dir / "input.png", _png_bytes(raw_image)
    input_path = candidates[0]
    try:
        with Image.open(input_path) as image:
            existing = np.asarray(image.convert("RGB"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot decode existing input image {input_path}: {exc}") from exc
    if existing.shape != raw_image.shape or not np.array_equal(existing, raw_image):
        raise ValueError(
            f"existing {input_path} does not decode to the selected frame's exact RGB pixels"
        )
    return input_path, None


def _enforce_protocol_compatibility(
    predictions: dict[str, Any], protocol: dict[str, Any], scene_path: Path
) -> None:
    for name, record in predictions.items():
        if not isinstance(record, dict) or not isinstance(record.get("protocol"), dict):
            raise ValueError(f"existing prediction {name!r} in {scene_path} has no protocol object")
        existing = record["protocol"]
        mismatches = [field for field in _PROTOCOL_FIELDS if existing.get(field) != protocol[field]]
        if mismatches:
            raise ValueError(
                f"prediction {name!r} in {scene_path} uses a different comparison protocol "
                f"for {mismatches}. Use a separate output root for protocol variants."
            )


def _validate_mask(mask: np.ndarray, space: LabelSpace, *, name: str, allow_ignore: bool) -> None:
    if mask.ndim != 2:
        raise ValueError(f"{name} must be a two-dimensional index mask, got {mask.shape}")
    observed = np.unique(mask)
    valid = (observed >= 0) & (observed < space.num_classes)
    if allow_ignore:
        valid |= observed == space.ignore_index
    if not bool(valid.all()):
        bad = observed[~valid].tolist()
        raise ValueError(
            f"{name} contains ids outside canonical classes 0..{space.num_classes - 1}"
            f"{' plus ignore ' + str(space.ignore_index) if allow_ignore else ''}: {bad[:10]}"
        )


def _select_sample(dataset: Any, frame_key: str | None, frame_index: int | None) -> int:
    if frame_key is not None:
        matches = [index for index, sample in enumerate(dataset.samples) if sample.key == frame_key]
        if not matches:
            raise KeyError(
                f"frame key {frame_key!r} is not present in {dataset.name!r} split "
                f"{dataset.split!r} ({len(dataset)} samples)"
            )
        if len(matches) != 1:
            raise ValueError(
                f"frame key {frame_key!r} occurs {len(matches)} times; keys must be unique"
            )
        return matches[0]
    assert frame_index is not None
    if not 0 <= frame_index < len(dataset):
        raise IndexError(
            f"frame index {frame_index} is outside 0..{len(dataset) - 1} for "
            f"{dataset.name!r} split {dataset.split!r}"
        )
    return frame_index


def _resolve_device(requested: str) -> torch.device:
    try:
        device = torch.device(requested)
    except (RuntimeError, ValueError) as exc:
        raise ValueError(f"invalid --device {requested!r}: {exc}") from exc
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(f"--device {requested!r} requested CUDA, but CUDA is unavailable")
    if device.type == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError(f"--device {requested!r} requested MPS, but MPS is unavailable")
    return device


def _taxonomy_document(
    space: LabelSpace, active_ids: tuple[int, ...], data: DataConfig
) -> dict[str, Any]:
    active = set(active_ids)
    return {
        "schema_version": 1,
        "dataset": {
            "name": data.name,
            "mapping": data.mapping or data.name,
            "variant": data.variant,
        },
        "taxonomy": {
            "name": space.name,
            "description": space.description,
            "ignore_index": space.ignore_index,
            "thin_class_ids": list(space.thin_classes),
            "classes": [
                {
                    "id": item.id,
                    "name": item.name,
                    "color": list(item.color),
                    "evaluate": item.id in active,
                }
                for item in space.classes
            ],
        },
    }


def _data_from_args(args: argparse.Namespace, cfg: Any) -> tuple[DataConfig, str]:
    if args.stage is None:
        stage = cfg.stages[-1]
    else:
        matches = [candidate for candidate in cfg.stages if candidate.name == args.stage]
        if not matches:
            raise ValueError(
                f"unknown stage {args.stage!r}; configured stages are "
                f"{[candidate.name for candidate in cfg.stages]}"
            )
        stage = matches[0]

    if args.dataset is None:
        return stage.data[0], args.split or stage.data[0].val_split

    if args.root is None:
        raise ValueError("--dataset requires --root")
    return (
        DataConfig(
            name=args.dataset,
            root=args.root,
            loader=args.loader,
            mapping=args.mapping,
            loader_options=args.loader_options,
            variant=args.variant,
            split_file=args.split_file,
            val_split=args.split or "val",
        ),
        args.split or "val",
    )


def export_scene(args: argparse.Namespace) -> Path:
    overrides: dict[str, Any] = {}
    for item in args.set:
        overrides = deep_merge(overrides, parse_override(item))
    cfg = load_experiment(args.configs, overrides=overrides)
    validate_task_configuration(cfg)
    seed_everything(cfg.train.seed)

    if cfg.loss.task not in ("multiclass", "binary"):
        raise ValueError(
            f"scene export supports multiclass and binary tasks, not {cfg.loss.task!r}"
        )
    task = cast(Literal["multiclass", "binary"], cfg.loss.task)
    space = load_space(cfg.taxonomy_root, cfg.space)
    validate_task_space(task, space)
    data, split = _data_from_args(args, cfg)
    mapping = load_data_mapping(data, space, cfg.taxonomy_root)
    active = torch.from_numpy(mapping.active_mask())
    if task == "binary":
        validate_canonical_active(
            active,
            task,
            where=f"scene-export dataset {data.name!r} active mask",
        )
    taxonomy_doc = _taxonomy_document(space, mapping.active_ids, data)
    output_root = args.out.resolve()
    _validate_output_root(output_root, data, split, space, taxonomy_doc)
    device = _resolve_device(args.device)

    model = build_model(cfg.model, space.num_classes)
    model = load_configured_checkpoint(model, cfg, args.ckpt, args.ema)
    model = model.to(device).eval()
    normalization = input_normalization(model)
    transform = build_eval_transform(aug_from_spec(cfg.aug, model))
    dataset = build_dataset(data, space, cfg.taxonomy_root, split, transform)
    sample_index = _select_sample(dataset, args.frame_key, args.frame_index)
    sample = dataset.samples[sample_index]
    item = dataset[sample_index]

    key = item.get("key")
    if key != sample.key:
        raise ValueError(
            f"dataset returned key {key!r} at index {sample_index}, expected {sample.key!r}"
        )
    image = item.get("image")
    target = item.get("mask")
    if not isinstance(image, torch.Tensor) or image.ndim != 3 or image.shape[0] != 3:
        raise ValueError(
            f"dataset returned image {type(image).__name__} with shape "
            f"{getattr(image, 'shape', None)}, expected (3,H,W) tensor"
        )
    if not isinstance(target, torch.Tensor) or target.ndim != 2:
        raise ValueError(
            f"dataset returned mask {type(target).__name__} with shape "
            f"{getattr(target, 'shape', None)}, expected (H,W) tensor"
        )

    raw_image = dataset.load_image(sample.image)
    if raw_image.ndim != 3 or raw_image.shape[2] != 3:
        raise ValueError(
            f"{sample.image}: decoded input shape must be (H,W,3), got {raw_image.shape}"
        )
    height, width = raw_image.shape[:2]
    if tuple(image.shape[1:]) != (height, width) or tuple(target.shape) != (height, width):
        raise ValueError(
            f"evaluation preprocessing changed native dimensions for {sample.key}: raw "
            f"{(height, width)}, image {tuple(image.shape[1:])}, mask {tuple(target.shape)}"
        )

    infer_cfg = InferenceConfig(
        sliding_window=cfg.eval.sliding_window,
        window=(int(cfg.eval.window[0]), int(cfg.eval.window[1])),
        stride=(int(cfg.eval.stride[0]), int(cfg.eval.stride[1])),
        scales=(1.0,),
        flip=False,
        task=task,
        threshold=cfg.eval.threshold,
    )
    with torch.no_grad():
        batch = image.unsqueeze(0).to(device)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
            scores = inference(model, batch, space.num_classes, infer_cfg)
        prediction = prediction_from_inference(scores.float(), infer_cfg)

    if tuple(prediction.shape) != (1, height, width):
        raise ValueError(
            f"prediction shape {tuple(prediction.shape)} does not match input {(1, height, width)}"
        )
    gt = target.detach().cpu().numpy()
    pred = prediction[0].detach().cpu().numpy()
    _validate_mask(gt, space, name="canonical ground truth", allow_ignore=True)
    _validate_mask(pred, space, name="prediction", allow_ignore=False)
    gt_u8 = gt.astype(np.uint8, copy=False)
    pred_u8 = pred.astype(np.uint8, copy=False)

    scene_slug = (
        sample.key
        if _NAME.fullmatch(sample.key) and sample.key not in {".", ".."}
        else f"frame-{hashlib.sha256(sample.key.encode('utf-8')).hexdigest()[:16]}"
    )
    scene_dir = output_root / scene_slug
    config_path = output_root / "config.json"
    input_path, input_payload = _resolve_input_artifact(scene_dir, raw_image)
    gt_path = scene_dir / "gt.png"
    prediction_path = scene_dir / f"{args.name}.png"
    scene_path = scene_dir / "scene.json"

    _write_identical_or_new(
        config_path, _json_bytes(taxonomy_doc), description="canonical taxonomy"
    )
    if input_payload is not None:
        _atomic_bytes(input_path, input_payload)
    _write_identical_or_new(gt_path, _png_bytes(gt_u8), description="canonical ground truth")

    identity = {
        "schema_version": 1,
        "frame_key": sample.key,
        "dataset": data.name,
        "split": split,
        "taxonomy": space.name,
    }
    scene_doc: dict[str, Any]
    if scene_path.exists():
        scene_doc = _read_json(scene_path)
        for field, expected in identity.items():
            if scene_doc.get(field) != expected:
                raise ValueError(
                    f"existing {scene_path} has {field}={scene_doc.get(field)!r}, "
                    f"expected {expected!r}"
                )
        predictions = scene_doc.get("predictions")
        if not isinstance(predictions, dict):
            raise ValueError(f"existing {scene_path} has no predictions object")
    else:
        scene_doc = {
            **identity,
            "frame_index": sample_index,
            "artifacts": {
                "input": {"file": input_path.name, "sha256": _sha256_file(input_path)},
                "ground_truth": {"file": gt_path.name, "sha256": _sha256_file(gt_path)},
            },
            "predictions": {},
        }
        predictions = scene_doc["predictions"]

    if prediction_path.exists() and not args.replace:
        raise FileExistsError(
            f"{prediction_path} already exists; use --replace only when intentionally replacing "
            "that named prediction"
        )
    protocol = {
        "native_resolution": [height, width],
        "configured_inference": "sliding_window" if infer_cfg.sliding_window else "whole_image",
        "execution": (
            "sliding_window"
            if infer_cfg.sliding_window
            and height >= infer_cfg.window[0]
            and width >= infer_cfg.window[1]
            else ("whole_image_fallback" if infer_cfg.sliding_window else "whole_image")
        ),
        "window": list(infer_cfg.window) if infer_cfg.sliding_window else None,
        "stride": list(infer_cfg.stride) if infer_cfg.sliding_window else None,
        "tta": False,
        "task": infer_cfg.task,
        "threshold": infer_cfg.threshold if infer_cfg.task == "binary" else None,
        "input_normalization": normalization,
        "autocast": "bfloat16" if device.type == "cuda" else None,
    }
    _enforce_protocol_compatibility(predictions, protocol, scene_path)

    resolved_config = to_dict(cfg)
    repo_root = discover_git_root([*args.configs, Path.cwd()]) or Path.cwd()
    sha, dirty = git_sha(repo_root)
    prediction_payload = _png_bytes(pred_u8)
    prediction_record = {
        "name": args.name,
        "file": prediction_path.name,
        "sha256": hashlib.sha256(prediction_payload).hexdigest(),
        "weights": "ema" if args.ema else "raw",
        "checkpoint": {
            "file": args.ckpt.name,
            "sha256": _sha256_file(args.ckpt),
        },
        "config": {
            "hash": config_hash(resolved_config),
            "sha256": _sha256_json(resolved_config),
            "sources": [{"file": path.name, "sha256": _sha256_file(path)} for path in args.configs],
        },
        "segmentary": {"git_sha": sha, "git_dirty": dirty},
        "protocol": protocol,
    }

    _atomic_bytes(prediction_path, prediction_payload)
    predictions[args.name] = prediction_record
    _atomic_bytes(scene_path, _json_bytes(scene_doc))
    return scene_dir


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("configs", nargs="+", type=Path, help="YAML configs, merged left to right")
    parser.add_argument("--ckpt", required=True, type=Path)
    parser.add_argument("--name", required=True, help="safe prediction filename/display name")
    parser.add_argument("--out", required=True, type=Path, help="comparison artifact root")
    parser.add_argument("--ema", action="store_true", help="load EMA shadow weights")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--stage", default=None, help="configured stage to inspect; default: last")
    parser.add_argument("--dataset", default=None, help="override dataset identity")
    parser.add_argument("--root", default=None, help="dataset root; required with --dataset")
    parser.add_argument("--split", default=None, help="default: configured validation split")
    parser.add_argument("--split-file", default=None)
    parser.add_argument("--mapping", default=None, help="taxonomy mapping stem")
    parser.add_argument("--variant", default=None, help="taxonomy mapping variant")
    parser.add_argument("--loader", default=None, help="built-in id or package.module:DatasetClass")
    parser.add_argument(
        "--loader-options",
        default="{}",
        metavar="JSON",
        help="loader-specific JSON object",
    )
    frame = parser.add_mutually_exclusive_group(required=True)
    frame.add_argument("--frame-key", default=None)
    frame.add_argument("--frame-index", type=int, default=None, help="zero-based split index")
    parser.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE", help="repeatable config override"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="explicitly replace an existing prediction with the same --name",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not _NAME.fullmatch(args.name) or args.name.lower() in _RESERVED_NAMES:
        parser.error(
            "--name must use letters, numbers, dots, underscores, or hyphens; "
            "input, gt, scene, and config are reserved"
        )
    if args.frame_index is not None and args.frame_index < 0:
        parser.error("--frame-index cannot be negative")
    try:
        args.loader_options = json.loads(args.loader_options)
    except json.JSONDecodeError as exc:
        parser.error(f"--loader-options must be valid JSON: {exc}")
    if not isinstance(args.loader_options, dict):
        parser.error("--loader-options must decode to a JSON object")
    if args.dataset is None and any(
        value is not None
        for value in (args.root, args.split_file, args.mapping, args.variant, args.loader)
    ):
        parser.error(
            "--root/--split-file/--mapping/--variant/--loader require --dataset; "
            "use --stage for configured data"
        )
    if args.dataset is None and args.loader_options:
        parser.error("--loader-options requires --dataset")
    for path in [*args.configs, args.ckpt]:
        if not path.is_file():
            parser.error(f"file not found: {path}")

    try:
        scene_dir = export_scene(args)
    except (ArithmeticError, IndexError, KeyError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"segmentary-scene: error: {exc}\n")
    print(f"wrote comparison scene {scene_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
