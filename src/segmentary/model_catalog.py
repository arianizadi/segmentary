"""Inspect shipped model recipes and admission-test a fully composed model.

``segmentary-models list`` reads the same typed model YAMLs users train with.
``segmentary-models probe`` merges a normal experiment config, builds the exact
first-stage model, and exercises Segmentary's real objective and optimizer on
synthetic tensors.  A probe is compatibility evidence, never an accuracy
benchmark.
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import json
import math
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import torch
from torch import Tensor, nn

from .config import (
    ExperimentConfig,
    ModelConfig,
    config_hash,
    deep_merge,
    from_dict,
    load_yaml,
    replace,
    to_dict,
)
from .curriculum import apply_freeze, prepare_stage_model, validate_training_contract
from .data.loaders import input_normalization
from .engine.losses import LossConfig, SegmentationLoss
from .engine.module import dense_training_objective
from .engine.optim import build_optimizer, describe_param_groups
from .engine.query_loss import QuerySegmentationLoss, query_training_objective
from .models.factory import build_model
from .models.native import NativeDenseSegmenter
from .models.outputs import QueryOutput, SegmentationOutput
from .models.tuning import count_trainable
from .tasks import output_channels as task_output_channels
from .tasks import validate_task_space
from .taxonomy import load_space
from .utils.provenance import collect_env, discover_git_root, git_sha, peak_vram, reset_peak_vram
from .utils.seed import seed_everything

_SCHEMA_VERSION = 1
_DEFAULT_SHAPES = ((64, 96), (65, 97))


class ModelProbeError(RuntimeError):
    """A model cannot satisfy the declared probe contract."""


@dataclass(frozen=True)
class ProbeOptions:
    """Validated execution controls for :func:`probe_configs`."""

    shapes: tuple[tuple[int, int], ...] = _DEFAULT_SHAPES
    batch_size: int = 1
    steps: int = 2
    device: str = "cpu"
    precision: Literal["auto", "fp32", "bf16"] = "auto"
    seed: int = 0

    def __post_init__(self) -> None:
        if len(self.shapes) < 2:
            raise ValueError("a model probe requires at least two input shapes")
        if len(set(self.shapes)) != len(self.shapes):
            raise ValueError(f"probe shapes must be distinct, got {self.shapes}")
        for shape in self.shapes:
            if len(shape) != 2 or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 1
                for value in shape
            ):
                raise ValueError(f"probe shapes must be positive (H, W) pairs, got {shape}")
            if shape[0] == shape[1]:
                raise ValueError(
                    f"probe shape {shape} is square; use non-square shapes to expose accidental "
                    "height/width assumptions"
                )
        if isinstance(self.batch_size, bool) or self.batch_size < 1:
            raise ValueError("probe batch_size must be at least 1")
        if isinstance(self.steps, bool) or self.steps < 1:
            raise ValueError("probe steps must be at least 1")
        if not isinstance(self.device, str) or not self.device.strip():
            raise ValueError("probe device must be a non-empty torch device string")
        if self.precision not in ("auto", "fp32", "bf16"):
            raise ValueError("probe precision must be auto, fp32, or bf16")


def _parse_shape(value: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("shape must use HxW, for example 257x385")
    try:
        shape = (int(parts[0]), int(parts[1]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("shape dimensions must be integers") from exc
    if any(item < 1 for item in shape):
        raise argparse.ArgumentTypeError("shape dimensions must be positive")
    if shape[0] == shape[1]:
        raise argparse.ArgumentTypeError("probe shapes must be non-square")
    return shape


def _parse_override(item: str) -> dict[str, Any]:
    if "=" not in item:
        raise ValueError(f"--set expects key=value, got {item!r}")
    key, raw = item.split("=", 1)
    if not key or any(not part for part in key.split(".")):
        raise ValueError(f"--set has an invalid dotted key: {key!r}")
    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    result: Any = value
    for part in reversed(key.split(".")):
        result = {part: result}
    return result


def load_probe_config(
    paths: Sequence[Path | str], overrides: Sequence[str] = ()
) -> ExperimentConfig:
    """Load a normal left-to-right composed experiment without touching data."""

    if not paths:
        raise ValueError("probe needs at least one config path")
    merged: dict[str, Any] = {}
    for path in paths:
        merged = deep_merge(merged, load_yaml(path))
    for item in overrides:
        merged = deep_merge(merged, _parse_override(item))
    return from_dict(ExperimentConfig, merged)


def _catalog_candidates() -> tuple[Path, ...]:
    source_root = Path(__file__).resolve().parents[2]
    candidates = (
        Path.cwd() / "configs" / "models",
        source_root / "configs" / "models",
        Path(sys.prefix) / "share" / "segmentary" / "configs" / "models",
    )
    # Preserve precedence while avoiding a confusing repeated search path.
    return tuple(dict.fromkeys(path.resolve() for path in candidates))


def resolve_catalog_dir(explicit: Path | str | None = None) -> Path:
    """Locate the source-checkout or wheel-installed model recipe directory."""

    candidates = (Path(explicit).expanduser().resolve(),) if explicit else _catalog_candidates()
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        f"could not locate a Segmentary model catalog; searched {searched}. "
        "Pass --config-dir explicitly when recipes live elsewhere."
    )


def _model_summary(name: str, recipe_path: str, model: ModelConfig) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "name": name,
        "path": recipe_path,
        "arch": model.arch,
        "tuning": model.tuning,
        "checkpoint": model.checkpoint,
    }
    if model.arch == "native":
        native = model.native
        assert native is not None
        summary["composition"] = {
            "task": native.task,
            "backbone": {
                "kind": native.backbone.kind,
                "name": native.backbone.name,
                "weights": native.backbone.weights,
                "out_indices": list(native.backbone.out_indices),
            },
            "neck": native.neck.kind,
            "head": native.head.kind,
            "auxiliary_heads": [
                {"name": item.name, "kind": item.head.kind, "loss_weight": item.loss_weight}
                for item in native.auxiliary_heads
            ],
        }
    elif model.arch == "smp":
        summary["composition"] = {
            "decoder": model.smp_arch,
            "encoder": model.encoder_name,
            "encoder_weights": model.encoder_weights,
        }
    else:
        summary["composition"] = None
    return summary


def list_catalog(config_dir: Path | str | None = None) -> dict[str, Any]:
    """Parse every shipped recipe through ``ModelConfig`` and return JSON-ready rows."""

    root = resolve_catalog_dir(config_dir)
    recipes: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.yaml")):
        raw = load_yaml(path)
        if "model" not in raw:
            raise ValueError(f"catalog recipe {path} has no top-level model mapping")
        model = from_dict(ModelConfig, raw["model"], f"{path}.model")
        recipes.append(_model_summary(path.stem, path.relative_to(root).as_posix(), model))
    if not recipes:
        raise ValueError(f"model catalog {root} contains no YAML recipes")
    return {
        "schema_version": _SCHEMA_VERSION,
        "command": "list",
        "catalog_dir": _portable_catalog_id(root),
        "recipe_count": len(recipes),
        "recipes": recipes,
    }


def _portable_catalog_id(root: Path) -> str:
    """Identify a catalog without embedding a user or cluster filesystem path."""

    if tuple(root.parts[-4:]) == ("share", "segmentary", "configs", "models"):
        return "share/segmentary/configs/models"
    if tuple(root.parts[-2:]) == ("configs", "models"):
        return "configs/models"
    return root.name


def _validate_normalization(model: nn.Module) -> dict[str, Any]:
    normalization = input_normalization(model)
    for field in ("mean", "std"):
        raw = normalization.get(field)
        if not isinstance(raw, list) or len(raw) != 3:
            raise ModelProbeError(
                f"model preprocessing {field} must contain exactly three values, got {raw!r}"
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in raw
        ):
            raise ModelProbeError(f"model preprocessing {field} is not finite: {raw!r}")
    if any(float(value) <= 0.0 for value in normalization["std"]):
        raise ModelProbeError(
            f"model preprocessing standard deviations must be positive: {normalization['std']!r}"
        )
    if normalization.get("channel_order") not in ("rgb", "bgr"):
        raise ModelProbeError(
            "model preprocessing channel_order must be exactly 'rgb' or 'bgr', got "
            f"{normalization.get('channel_order')!r}"
        )
    source = normalization.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ModelProbeError("model preprocessing has no recordable normalization source")
    return normalization


def _feature_rows(specs: Iterable[Any]) -> list[dict[str, Any]]:
    return [
        {"name": item.name, "channels": int(item.channels), "reduction": int(item.reduction)}
        for item in specs
    ]


def _native_description(model: nn.Module) -> dict[str, Any] | None:
    if not isinstance(model, NativeDenseSegmenter):
        return None
    backbone_cfg = getattr(model.backbone, "pretrained_cfg", {})
    provenance = {
        key: backbone_cfg[key]
        for key in ("architecture", "tag", "url", "hf_hub_id")
        if key in backbone_cfg and isinstance(backbone_cfg[key], (str, int, float, bool))
    }
    return {
        "backbone": {
            "class": type(model.backbone).__name__,
            "name": getattr(model.backbone, "name", None),
            "pretrained": getattr(model.backbone, "pretrained", None),
            "out_indices": list(getattr(model.backbone, "out_indices", ())),
            "features": _feature_rows(model.backbone.output_specs),
            "pretrained_source": provenance,
        },
        "neck": {
            "class": type(model.neck).__name__,
            "features": _feature_rows(model.neck.output_specs),
        },
        "head": {
            "class": type(model.head).__name__,
            "in_indices": list(model.head.in_indices),
            "selected_features": _feature_rows(model.head.selected_specs),
        },
        "auxiliary_heads": [
            {
                "name": name,
                "class": type(head).__name__,
                "loss_weight": model._auxiliary_weights[name],
                "in_indices": list(head.in_indices),
                "selected_features": _feature_rows(head.selected_specs),
            }
            for name, head in model.auxiliary_heads.items()
        ],
        "parameter_tensors_by_component": model.validate_parameter_partition(),
    }


def _resolve_device(requested: str) -> torch.device:
    try:
        device = torch.device(requested)
    except (RuntimeError, ValueError) as exc:
        raise ModelProbeError(f"invalid torch device {requested!r}: {exc}") from exc
    if device.type == "cuda":
        if not torch.cuda.is_available():
            raise ModelProbeError(
                f"device {requested!r} requested CUDA, but torch.cuda.is_available() is false"
            )
        index = torch.cuda.current_device() if device.index is None else device.index
        if index < 0 or index >= torch.cuda.device_count():
            raise ModelProbeError(
                f"device {requested!r} selects CUDA index {index}, but only "
                f"{torch.cuda.device_count()} device(s) are visible"
            )
        return torch.device("cuda", index)
    if device.type == "mps" and not torch.backends.mps.is_available():
        raise ModelProbeError("MPS was requested but is not available")
    if device.type not in ("cpu", "cuda", "mps"):
        raise ModelProbeError(f"unsupported probe device type {device.type!r}")
    return device


def _resolve_precision(
    requested: Literal["auto", "fp32", "bf16"], device: torch.device
) -> Literal["fp32", "bf16"]:
    precision: Literal["fp32", "bf16"] = (
        "bf16" if requested == "auto" and device.type == "cuda" else "fp32"
    )
    if requested != "auto":
        precision = requested
    if precision == "bf16":
        if device.type != "cuda":
            raise ModelProbeError("BF16 probe execution currently requires CUDA")
        if not torch.cuda.is_bf16_supported():
            raise ModelProbeError(f"device {device} does not report BF16 support")
    return precision


def _autocast(device: torch.device, precision: str):
    if precision == "bf16":
        return torch.autocast(device_type="cuda", dtype=torch.bfloat16)
    return contextlib.nullcontext()


def _tensor_stats(tensor: Tensor) -> dict[str, Any]:
    value = tensor.detach().float()
    return {
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype).removeprefix("torch."),
        "finite": bool(torch.isfinite(value).all()),
        "min": float(value.min()),
        "max": float(value.max()),
        "mean": float(value.mean()),
    }


def _dense_forward(model: nn.Module, image: Tensor) -> Tensor:
    forward_output = getattr(model, "forward_output", None)
    raw = forward_output(image) if callable(forward_output) else model(image)
    if isinstance(raw, Tensor):
        logits = raw
    elif isinstance(raw, SegmentationOutput):
        if raw.query is not None or raw.dense_logits is None:
            raise ModelProbeError(
                f"{type(model).__name__} emitted raw query predictions. The dense model probe "
                "will not invent a collapse for an unadvertised output contract. Configure "
                "loss.query or implement a reviewed public dense-collapse contract."
            )
        logits = raw.dense_logits
    else:
        raise ModelProbeError(
            f"{type(model).__name__}.forward_output returned {type(raw).__name__}, expected "
            "Tensor or SegmentationOutput"
        )
    if logits.ndim != 4:
        raise ModelProbeError(f"model emitted non-NCHW logits {tuple(logits.shape)}")
    if not bool(torch.isfinite(logits.float()).all()):
        raise ModelProbeError("model emitted non-finite logits")
    return logits


def _query_forward(model: nn.Module, image: Tensor, num_classes: int) -> QueryOutput:
    """Return a finite raw query contract without collapsing it to dense scores."""

    forward_output = getattr(model, "forward_output", None)
    if not callable(forward_output):
        raise ModelProbeError(
            f"{type(model).__name__} has no forward_output, but loss.query requires raw QueryOutput"
        )
    raw = forward_output(image)
    if not isinstance(raw, SegmentationOutput) or raw.query is None:
        kind = type(raw).__name__
        raise ModelProbeError(
            f"{type(model).__name__}.forward_output returned {kind} without raw query "
            "predictions, but loss.query is configured"
        )
    for layer_index, prediction in enumerate((raw.query.primary, *raw.query.auxiliary)):
        if prediction.class_logits.shape[0] != image.shape[0]:
            raise ModelProbeError(
                f"query layer {layer_index} batch {prediction.class_logits.shape[0]} does not "
                f"match input batch {image.shape[0]}"
            )
        if prediction.class_logits.shape[-1] != num_classes + 1:
            raise ModelProbeError(
                f"query layer {layer_index} has {prediction.class_logits.shape[-1]} class "
                f"columns; expected {num_classes + 1} including no-object"
            )
        for name, tensor in (
            ("class_logits", prediction.class_logits),
            ("mask_logits", prediction.mask_logits),
        ):
            if not bool(torch.isfinite(tensor.float()).all()):
                raise ModelProbeError(f"query layer {layer_index} emitted non-finite {name}")
    return raw.query


def _public_dense_forward(model: nn.Module, image: Tensor) -> Tensor:
    """Validate the stable evaluation contract of a query-output model."""

    logits = model(image)
    if not isinstance(logits, Tensor) or logits.ndim != 4:
        kind = tuple(logits.shape) if isinstance(logits, Tensor) else type(logits).__name__
        raise ModelProbeError(f"public model forward must return NCHW logits, got {kind}")
    if not bool(torch.isfinite(logits.float()).all()):
        raise ModelProbeError("public model forward emitted non-finite dense logits")
    return logits


def _query_stats(output: QueryOutput) -> dict[str, Any]:
    return {
        "primary": {
            "class_logits": _tensor_stats(output.primary.class_logits),
            "mask_logits": _tensor_stats(output.primary.mask_logits),
        },
        "auxiliary_layers": [
            {
                "class_logits": _tensor_stats(item.class_logits),
                "mask_logits": _tensor_stats(item.mask_logits),
            }
            for item in output.auxiliary
        ],
    }


def _tracked_parameters(model: nn.Module) -> dict[str, Tensor]:
    trainable = {name: value for name, value in model.named_parameters() if value.requires_grad}
    classifier = {name: value for name, value in trainable.items() if "classifier" in name.lower()}
    if classifier:
        return classifier
    patterns = tuple(model.head_patterns()) if hasattr(model, "head_patterns") else ()
    head = {
        name: value
        for name, value in trainable.items()
        if any(pattern.strip(".") in name for pattern in patterns)
    }
    if not head:
        raise ModelProbeError(
            f"{type(model).__name__} exposes no trainable classifier or head parameters to "
            "verify after the optimizer step"
        )
    return head


def _gradient_audit(model: nn.Module) -> dict[str, Any]:
    trainable = [
        (name, parameter) for name, parameter in model.named_parameters() if parameter.requires_grad
    ]
    missing = [name for name, parameter in trainable if parameter.grad is None]
    nonfinite = [
        name
        for name, parameter in trainable
        if parameter.grad is not None and not bool(torch.isfinite(parameter.grad).all())
    ]
    if missing:
        raise ModelProbeError(
            f"{len(missing)} trainable parameter tensor(s) received no gradient; first: "
            f"{missing[:8]}. Freeze an exact audited inactive path or fix the forward graph."
        )
    if nonfinite:
        raise ModelProbeError(
            f"{len(nonfinite)} trainable parameter tensor(s) received non-finite gradients; "
            f"first: {nonfinite[:8]}"
        )
    return {
        "trainable_tensors": len(trainable),
        "gradient_tensors": len(trainable) - len(missing),
        "all_present": not missing,
        "all_finite": not nonfinite,
    }


def _optimizer_description(optimizer: torch.optim.Optimizer) -> dict[str, Any]:
    return {
        "class": type(optimizer).__name__,
        "summary": describe_param_groups(optimizer.param_groups),
        "groups": [
            {
                "name": group.get("name"),
                "lr": float(group["lr"]),
                "weight_decay": float(group["weight_decay"]),
                "layer_id": int(group["layer_id"]),
                "is_head": bool(group.get("is_head")),
                "parameter_tensors": len(group["params"]),
                "parameters": sum(int(parameter.numel()) for parameter in group["params"]),
            }
            for group in optimizer.param_groups
        ],
    }


def _write_json(path: Path | str, record: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)


def _record_path(path: Path, root: Path | None) -> str:
    """Prefer repository-relative provenance without inventing a common root."""

    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return str(path)


def probe_configs(
    config_paths: Sequence[Path | str],
    *,
    options: ProbeOptions = ProbeOptions(),
    overrides: Sequence[str] = (),
) -> dict[str, Any]:
    """Build and train-step the first stage of one composed experiment.

    Dataset roots are intentionally never opened.  The taxonomy is loaded to
    derive the real class count and ignore index; everything after that uses
    synthetic normalized tensors and labels.
    """

    started = time.time()
    paths = [Path(path) for path in config_paths]
    cfg = load_probe_config(paths, overrides)
    validate_training_contract(cfg)
    stage = cfg.stages[0]
    if stage.init_from != "pretrained":
        raise ModelProbeError(
            f"first stage {stage.name!r} uses init_from={stage.init_from!r}. The model probe "
            "does not ignore or partially load curriculum checkpoints; use a first-stage "
            "pretrained recipe or run the checkpoint-aware training/evaluation path."
        )
    device = _resolve_device(options.device)
    precision = _resolve_precision(options.precision, device)
    seed_everything(options.seed)
    space = load_space(cfg.taxonomy_root, cfg.space)
    validate_task_space(cfg.loss.task, space)
    expected_output_channels = task_output_channels(cfg.loss.task, space.num_classes)

    model = build_model(cfg.model, space.num_classes)
    declared_output_channels = int(getattr(model, "output_channels", expected_output_channels))
    if declared_output_channels != expected_output_channels:
        raise ModelProbeError(
            f"task={cfg.loss.task!r} with {space.num_classes} canonical classes requires "
            f"{expected_output_channels} model output channel(s), but "
            f"{type(model).__name__} declares {declared_output_channels}"
        )
    query_objective = cfg.loss.query is not None
    if query_objective and not getattr(model, "supports_query_objective", False):
        raise ModelProbeError(
            f"loss.query requires raw QueryOutput, but {type(model).__name__} is a dense model"
        )
    supports_query = bool(getattr(model, "supports_query_objective", False))
    supports_dense = bool(getattr(model, "supports_dense_ce", True))
    dense_query_ablation = not query_objective and not supports_dense and supports_query
    if not query_objective and not supports_dense and not supports_query:
        raise ModelProbeError(
            f"{type(model).__name__} advertises neither dense-objective nor raw-query training "
            "support, so the probe cannot select a production objective"
        )
    model.train()
    model = prepare_stage_model(model, cfg, None, stage.reset_head)
    frozen_tensors = apply_freeze(model, stage.freeze)
    normalization = _validate_normalization(model)
    trainable, total = count_trainable(model)
    if trainable < 1:
        raise ModelProbeError("the composed first-stage model has no trainable parameters")
    native = _native_description(model)

    model = model.to(device)
    if cfg.loss.query is not None:
        loss_fn: SegmentationLoss | QuerySegmentationLoss = QuerySegmentationLoss(
            cfg.loss.query, space.num_classes, space.ignore_index
        ).to(device)
        objective = query_training_objective
        objective_name = "segmentary.engine.query_loss.query_training_objective"
        objective_kind = "query"
    else:
        loss_fn = SegmentationLoss(
            LossConfig.from_spec(cfg.loss), expected_output_channels, space.ignore_index
        ).to(device)
        objective = dense_training_objective
        objective_name = "segmentary.engine.module.dense_training_objective"
        objective_kind = "dense"
    train_iters = stage.iters or cfg.train.iters
    optim_cfg = replace(
        cfg.optim,
        backbone_lr=cfg.optim.backbone_lr * stage.lr_scale,
        warmup_iters=min(cfg.optim.warmup_iters, max(1, train_iters // 10)),
    )
    head_patterns = tuple(model.head_patterns()) if hasattr(model, "head_patterns") else ()
    optimizer = build_optimizer(model, optim_cfg, head_patterns)
    tracked = _tracked_parameters(model)
    tracked_before = {name: parameter.detach().cpu().clone() for name, parameter in tracked.items()}

    if device.type == "cuda":
        torch.cuda.set_device(device)
        reset_peak_vram()

    shape_checks: list[dict[str, Any]] = []
    model.eval()
    for height, width in options.shapes:
        image = torch.randn(options.batch_size, 3, height, width, device=device)
        try:
            with torch.no_grad(), _autocast(device, precision):
                if query_objective:
                    query = _query_forward(model, image, space.num_classes)
                    logits = _public_dense_forward(model, image)
                elif dense_query_ablation:
                    query = None
                    logits = _public_dense_forward(model, image)
                else:
                    query = None
                    logits = _dense_forward(model, image)
        except Exception as exc:
            if isinstance(exc, ModelProbeError):
                raise
            raise ModelProbeError(
                f"model rejected probe shape {height}x{width}: {exc}. It may require a fixed "
                "input size or a larger minimum crop; record that constraint instead of "
                "assuming arbitrary-resolution support."
            ) from exc
        expected = (options.batch_size, expected_output_channels, height, width)
        if tuple(logits.shape) != expected:
            raise ModelProbeError(
                f"shape {height}x{width} produced logits {tuple(logits.shape)}, expected {expected}"
            )
        shape_check = {"input": list(image.shape), "output": _tensor_stats(logits)}
        if query is not None:
            shape_check["query_output"] = _query_stats(query)
        shape_checks.append(shape_check)
        del image, logits, query

    step_checks: list[dict[str, Any]] = []
    model.train()
    for step in range(options.steps):
        height, width = options.shapes[step % len(options.shapes)]
        image = torch.randn(options.batch_size, 3, height, width, device=device)
        target = torch.randint(
            0,
            space.num_classes,
            (options.batch_size, height, width),
            device=device,
            dtype=torch.long,
        )
        active = torch.ones(space.num_classes, device=device, dtype=torch.bool)
        optimizer.zero_grad(set_to_none=True)
        try:
            with _autocast(device, precision):
                loss, parts = objective(model, loss_fn, image, target, active=active)
            if not bool(torch.isfinite(loss.detach()).all()):
                raise ModelProbeError(f"optimizer step {step + 1} produced non-finite loss")
            loss.backward()
            gradient_check = _gradient_audit(model)
            if optim_cfg.grad_clip is not None:
                grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), optim_cfg.grad_clip)
                if not bool(torch.isfinite(grad_norm).all()):
                    raise ModelProbeError(
                        f"optimizer step {step + 1} produced non-finite global gradient norm"
                    )
            else:
                grad_norm = None
            optimizer.step()
        except Exception as exc:
            if isinstance(exc, ModelProbeError):
                raise
            raise ModelProbeError(
                f"production objective/optimizer failed at shape {height}x{width}, "
                f"step {step + 1}: {exc}"
            ) from exc
        step_checks.append(
            {
                "step": step + 1,
                "shape": [height, width],
                "loss": float(loss.detach()),
                "loss_components": {name: float(value) for name, value in parts.items()},
                "grad_norm_before_clip": float(grad_norm) if grad_norm is not None else None,
                "gradients": gradient_check,
            }
        )
        del image, target, active, loss, parts

    changed = [
        name
        for name, parameter in tracked.items()
        if not torch.equal(tracked_before[name], parameter.detach().cpu())
    ]
    if not changed:
        raise ModelProbeError(
            f"AdamW completed {options.steps} step(s), but none of the {len(tracked)} tracked "
            "classifier/head tensors changed"
        )

    root = discover_git_root([*paths, Path.cwd()])
    sha, dirty = git_sha(root) if root is not None else ("unknown", True)
    environment = collect_env()
    environment["input_normalization"] = normalization
    finished = time.time()
    record: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "command": "probe",
        "status": "passed",
        "started_unix_s": started,
        "finished_unix_s": finished,
        "wall_clock_s": finished - started,
        "config_files": [_record_path(path, root) for path in paths],
        "config_hash": config_hash(cfg),
        "git": {"sha": sha, "dirty": dirty},
        "experiment": {
            "name": cfg.name,
            "space": cfg.space,
            "task": cfg.loss.task,
            "num_classes": space.num_classes,
            "output_channels": expected_output_channels,
            "ignore_index": space.ignore_index,
            "first_stage": stage.name,
            "model": to_dict(cfg.model),
            "loss": to_dict(cfg.loss),
            "optimizer": to_dict(optim_cfg),
        },
        "model": {
            "arch": cfg.model.arch,
            "class": type(model).__name__,
            "total_parameters": total,
            "trainable_parameters": trainable,
            "frozen_by_stage_tensors": frozen_tensors,
            "audited_inactive_parameter_paths": list(cfg.model.inactive_parameter_paths),
            "head_patterns": list(head_patterns),
            "tracked_update_kind": "classifier"
            if all("classifier" in name.lower() for name in tracked)
            else "head",
            "tracked_tensors": sorted(tracked),
            "changed_tracked_tensors": sorted(changed),
            "native_components": native,
        },
        "protocol": {
            "synthetic_data": True,
            "quality_benchmark": False,
            "shapes": [list(shape) for shape in options.shapes],
            "batch_size": options.batch_size,
            "optimizer_steps": options.steps,
            "precision": precision,
            "device": str(device),
            "seed": options.seed,
            "objective_kind": objective_kind,
            "objective": objective_name,
            "objective_contract": (
                "native_query"
                if query_objective
                else "experimental_dense_query_collapse"
                if dense_query_ablation
                else "dense"
            ),
            "dense_query_ablation": dense_query_ablation,
        },
        "shape_checks": shape_checks,
        "step_checks": step_checks,
        "optimizer": _optimizer_description(optimizer),
        "checks": {
            "typed_config_loaded": True,
            "normalization_valid": True,
            "all_shapes_forwarded": True,
            "all_logits_finite": True,
            "production_objective_backward": True,
            "all_trainable_gradients_present": True,
            "all_trainable_gradients_finite": True,
            "optimizer_stepped": True,
            "classifier_or_head_changed": True,
        },
        "environment": environment,
        "peak_vram_bytes": peak_vram() if device.type == "cuda" else {},
        "interpretation": (
            "Compatibility smoke for the explicitly selected experimental dense-collapse "
            "query-model ablation only; it is not native query training and synthetic inputs "
            "and labels cannot measure mIoU, quality, convergence, latency, throughput, or "
            "production memory."
            if dense_query_ablation
            else "Compatibility smoke only: synthetic inputs and labels cannot measure mIoU, "
            "quality, convergence, latency, throughput, or production memory."
        ),
    }
    return record


def _print_catalog(record: dict[str, Any]) -> None:
    print(f"model catalog: {record['catalog_dir']} ({record['recipe_count']} recipes)")
    for recipe in record["recipes"]:
        composition = recipe["composition"]
        if recipe["arch"] == "native":
            detail = (
                f"{composition['backbone']['name']} -> {composition['neck']} -> "
                f"{composition['head']}"
            )
        elif recipe["arch"] == "smp":
            detail = f"{composition['encoder']} -> {composition['decoder']}"
        else:
            detail = recipe["checkpoint"] or recipe["arch"]
        print(f"  {recipe['name']:<48} {recipe['arch']:<12} {detail}")


def _print_probe(record: dict[str, Any]) -> None:
    model = record["model"]
    protocol = record["protocol"]
    print(
        f"PASS {model['arch']} / {model['class']}: "
        f"{model['trainable_parameters']:,}/{model['total_parameters']:,} trainable parameters"
    )
    print(
        f"  shapes: {', '.join('x'.join(map(str, shape)) for shape in protocol['shapes'])}; "
        f"{protocol['optimizer_steps']} {protocol['precision']} step(s) on {protocol['device']}"
    )
    print(f"  normalization: {record['environment']['input_normalization']}")
    print(
        f"  changed {len(model['changed_tracked_tensors'])}/"
        f"{len(model['tracked_tensors'])} tracked {model['tracked_update_kind']} tensors"
    )
    if protocol["dense_query_ablation"]:
        print(
            "  WARNING: experimental dense-collapse query-model ablation, not native query training"
        )
    print("  compatibility smoke only; this is not an accuracy or speed benchmark")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="segmentary-models",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    listing = subcommands.add_parser("list", help="list and type-check model recipe YAMLs")
    listing.add_argument("--config-dir", type=Path, default=None)
    listing.add_argument("--json", action="store_true", help="print one JSON document")
    listing.add_argument("--output", type=Path, help="also write the JSON record atomically")

    probe = subcommands.add_parser(
        "probe", help="construct and optimizer-smoke a composed experiment model"
    )
    probe.add_argument("configs", nargs="+", type=Path, help="YAMLs merged left to right")
    probe.add_argument(
        "--shape",
        action="append",
        type=_parse_shape,
        default=[],
        metavar="HxW",
        help="non-square probe shape; repeat at least twice (default: 64x96, 65x97)",
    )
    probe.add_argument("--batch-size", type=int, default=1)
    probe.add_argument("--steps", type=int, default=2, help="optimizer steps; shapes alternate")
    probe.add_argument("--device", default="cpu", help="exact torch device; never falls back")
    probe.add_argument("--precision", choices=("auto", "fp32", "bf16"), default="auto")
    probe.add_argument("--seed", type=int, default=0)
    probe.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE", help="typed dotted override"
    )
    probe.add_argument("--json", action="store_true", help="print one JSON document")
    probe.add_argument("--output", type=Path, help="also write the JSON evidence atomically")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            record = list_catalog(args.config_dir)
        else:
            shapes = tuple(args.shape) if args.shape else _DEFAULT_SHAPES
            options = ProbeOptions(
                shapes=shapes,
                batch_size=args.batch_size,
                steps=args.steps,
                device=args.device,
                precision=args.precision,
                seed=args.seed,
            )
            record = probe_configs(args.configs, options=options, overrides=args.set)
        if args.output is not None:
            _write_json(args.output, record)
        if args.json:
            print(json.dumps(record, indent=2, sort_keys=True))
        elif args.command == "list":
            _print_catalog(record)
        else:
            _print_probe(record)
        return 0
    except Exception as exc:
        failure = {
            "schema_version": _SCHEMA_VERSION,
            "command": args.command,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        if args.output is not None:
            _write_json(args.output, failure)
        if args.json:
            print(json.dumps(failure, indent=2, sort_keys=True))
        else:
            print(f"segmentary-models {args.command}: ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        gc.collect()
        if torch.cuda.is_available() and torch.cuda.is_initialized():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    raise SystemExit(main())
