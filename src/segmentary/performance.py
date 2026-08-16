"""Measure one model's deployment cost under the Segmentary benchmark contract.

This is deliberately a model-only benchmark: it excludes image decoding,
normalisation, data loading, sliding-window stitching, and post-processing.
Every campaign model is measured through its public ``model(image)`` forward at
batch one, 1024x1024, with PyTorch BF16 autocast on an NVIDIA L40S.  CUDA events
provide device-side latency after a fixed warmup, while synchronized allocator
statistics provide peak inference memory.

The output is a strict, immutable ``performance.json`` evidence record. It is
model-level data measured exactly once from the model's RailSem19-only 21-class
recorded endpoint (raw for running-stat BatchNorm, EMA otherwise) and linked to
its three quality protocols. The public forward
includes any model-internal query-to-dense semantic collapse; external image
I/O, preprocessing, sliding-window stitching, argmax, and metrics are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickletools
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .config import ExperimentConfig, config_hash, from_dict, load_yaml, to_dict
from .eval import load_configured_checkpoint
from .models.factory import build_model
from .taxonomy import load_space
from .utils.provenance import collect_env, discover_git_root, git_sha, peak_vram, reset_peak_vram
from .utils.results import load_results
from .utils.seed import seed_everything

SCHEMA_VERSION = 1


class PerformanceError(RuntimeError):
    """The standardized deployment benchmark contract was not satisfied."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def latency_summary(latencies_ms: list[float]) -> dict[str, Any]:
    """Return strict timing statistics and retain every device-side sample."""
    if not latencies_ms or any(
        isinstance(value, bool) or not math.isfinite(value) or value <= 0 for value in latencies_ms
    ):
        raise PerformanceError("latency samples must be non-empty, finite, and positive")
    values = np.asarray(latencies_ms, dtype=np.float64)
    mean_ms = float(statistics.fmean(latencies_ms))
    return {
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "mean_ms": mean_ms,
        "minimum_ms": float(values.min()),
        "maximum_ms": float(values.max()),
        "fps": 1000.0 / mean_ms,
        "raw_ms": latencies_ms,
        "percentile_method": "numpy linear interpolation",
    }


def measure_cuda_forward(
    model: torch.nn.Module,
    image: torch.Tensor,
    *,
    warmup: int,
    iterations: int,
    expected_channels: int | None = None,
) -> tuple[dict[str, Any], int]:
    """Measure public-forward BF16 latency and allocator peak reserved memory.

    The CUDA context is not counted. After an untimed correctness preflight and
    warmup, the output reference is released, the stream is synchronized, and
    peak statistics are reset. The measured high-water mark therefore reflects
    steady-state cached/resident allocator memory without a duplicate preflight
    output.
    """
    if image.device.type != "cuda" or image.ndim != 4 or image.shape[0] != 1:
        raise PerformanceError("performance input must be a batch-one CUDA NCHW tensor")
    if warmup < 1 or iterations < 1:
        raise PerformanceError("warmup and measured iteration counts must be positive")
    device = image.device
    torch.cuda.synchronize(device)

    def forward() -> torch.Tensor:
        with torch.autocast("cuda", dtype=torch.bfloat16):
            output = model(image)
        if not isinstance(output, torch.Tensor) or output.ndim != 4 or output.shape[0] != 1:
            raise PerformanceError("public model forward must return one dense NCHW logits tensor")
        if output.shape[-2:] != image.shape[-2:]:
            raise PerformanceError(
                f"public forward output shape {tuple(output.shape)} does not preserve "
                f"input spatial shape {tuple(image.shape)}"
            )
        if expected_channels is not None and output.shape[1] != expected_channels:
            raise PerformanceError(
                f"public forward output has {output.shape[1]} channels; expected "
                f"the RailSem19 space's {expected_channels}"
            )
        return output

    latencies: list[float] = []
    with torch.inference_mode():
        # Correctness checks are a separate synchronized preflight.  A tensor
        # reduction inside the CUDA-event region would contaminate every sample.
        preflight = forward()
        if not bool(torch.isfinite(preflight).all()):
            raise PerformanceError("public model forward produced non-finite logits")
        for _ in range(warmup):
            forward()
        torch.cuda.synchronize(device)
        del preflight
        torch.cuda.synchronize(device)
        reset_peak_vram()
        for _ in range(iterations):
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            forward()
            end.record()
            end.synchronize()
            latencies.append(float(start.elapsed_time(end)))
    torch.cuda.synchronize(device)
    return latency_summary(latencies), int(peak_vram().get(f"cuda:{device.index or 0}", 0))


def physical_visibility_token() -> str:
    """Return the one physical GPU token backing logical ``cuda:0``."""
    raw = os.environ.get("CUDA_VISIBLE_DEVICES")
    tokens = [item.strip() for item in raw.split(",")] if isinstance(raw, str) else []
    if len(tokens) != 1 or not tokens[0]:
        raise PerformanceError(
            "standardized performance benchmark requires exactly one CUDA_VISIBLE_DEVICES token"
        )
    return tokens[0]


def checkpoint_global_step(path: Path) -> int | None:
    """Read Lightning's scalar step without unpickling executable checkpoint objects."""
    try:
        with zipfile.ZipFile(path) as archive:
            payload_name = next(name for name in archive.namelist() if name.endswith("/data.pkl"))
            payload = archive.read(payload_name)
    except (OSError, KeyError, StopIteration, zipfile.BadZipFile):
        return None
    found_key = False
    try:
        for opcode, argument, _ in pickletools.genops(payload):
            if argument == "global_step":
                found_key = True
            elif (
                found_key
                and opcode.name in {"INT", "BININT", "BININT1", "BININT2", "LONG"}
                and isinstance(argument, int)
                and not isinstance(argument, bool)
            ):
                return argument
    except ValueError:
        return None
    return None


def _gpu_uuid(physical_token: str) -> str | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--id={physical_token}",
                "--query-gpu=uuid",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip() if completed.returncode == 0 else ""
    return value or None


def benchmark_uses_ema(result: dict[str, Any], *, explicit_ema: bool, auto_weights: bool) -> bool:
    """Resolve the benchmark endpoint without reinterpreting evaluation policy.

    ``--auto-weights`` means "benchmark the exact endpoint reported by the
    quality evaluation."  Inferring again from the constructed model can drift
    from that immutable record, especially when a model contains BatchNorm but
    its accepted evaluation explicitly used EMA parameters.
    """
    if not auto_weights:
        return explicit_ema
    config = result.get("config")
    evaluation = config.get("evaluation") if isinstance(config, dict) else None
    weights = evaluation.get("weights") if isinstance(evaluation, dict) else None
    if weights not in {"raw", "ema"}:
        raise PerformanceError(
            "--auto-weights requires config.evaluation.weights to be exactly 'raw' or 'ema'"
        )
    return weights == "ema"


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    if not args.config.is_file():
        raise PerformanceError(f"config does not exist: {args.config}")
    if not args.ckpt.is_file() or args.ckpt.stat().st_size == 0:
        raise PerformanceError(f"checkpoint is missing or empty: {args.ckpt}")
    if not args.result.is_file() or args.result.stat().st_size == 0:
        raise PerformanceError(f"evaluation result is missing or empty: {args.result}")
    actual_checkpoint_step = checkpoint_global_step(args.ckpt)
    if actual_checkpoint_step != args.checkpoint_global_step:
        raise PerformanceError(
            f"checkpoint global_step {actual_checkpoint_step!r} != expected "
            f"{args.checkpoint_global_step}"
        )
    result = load_results(args.result).to_dict()
    result_checks = {
        "git_sha": (result.get("git_sha"), args.expected_result_git_sha),
        "git_dirty": (result.get("git_dirty"), False),
        "seed": (result.get("seed"), args.expected_seed),
        "stage": (result.get("stage"), args.expected_result_stage),
    }
    wrong_result = [
        f"{name}={actual!r}, expected {wanted!r}"
        for name, (actual, wanted) in result_checks.items()
        if actual != wanted
    ]
    if wrong_result:
        raise PerformanceError("evaluation result provenance mismatch: " + "; ".join(wrong_result))
    if not torch.cuda.is_available():
        raise PerformanceError("standardized performance measurement requires CUDA")
    device = torch.device(args.device)
    if device.type != "cuda":
        raise PerformanceError("standardized performance measurement requires a CUDA device")
    torch.cuda.set_device(device)
    if device.index not in (None, 0):
        raise PerformanceError(
            "single-GPU standardized benchmark must address its isolated device as cuda:0"
        )
    physical_gpu = physical_visibility_token()
    gpu_uuid = _gpu_uuid(physical_gpu)
    if not gpu_uuid:
        raise PerformanceError(
            f"could not resolve a non-empty GPU UUID for CUDA_VISIBLE_DEVICES={physical_gpu}"
        )
    properties = torch.cuda.get_device_properties(device)
    gpu_name = str(properties.name)
    if args.required_gpu_name not in gpu_name:
        raise PerformanceError(
            f"GPU {gpu_name!r} does not satisfy required model {args.required_gpu_name!r}"
        )

    raw = load_yaml(args.config)
    cfg = from_dict(ExperimentConfig, raw)
    seed_everything(cfg.train.seed)
    root = discover_git_root([args.config, Path.cwd()]) or Path.cwd()
    source_sha, source_dirty = git_sha(root)
    if source_dirty:
        raise PerformanceError("performance benchmark source worktree is dirty")
    if source_sha != args.expected_git_sha:
        raise PerformanceError(
            f"performance benchmark source SHA {source_sha} != expected {args.expected_git_sha}"
        )

    space = load_space(cfg.taxonomy_root, cfg.space)
    model = build_model(cfg.model, space.num_classes)
    use_ema = benchmark_uses_ema(
        result,
        explicit_ema=bool(args.ema),
        auto_weights=bool(args.auto_weights),
    )
    model = load_configured_checkpoint(model, cfg, args.ckpt, use_ema)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    trainable_parameter_count = sum(
        parameter.numel() for parameter in model.parameters() if parameter.requires_grad
    )
    resident_parameter_bytes = sum(
        parameter.numel() * parameter.element_size() for parameter in model.parameters()
    )
    parameter_dtype_counts: dict[str, int] = {}
    for parameter in model.parameters():
        name = str(parameter.dtype).removeprefix("torch.")
        parameter_dtype_counts[name] = parameter_dtype_counts.get(name, 0) + parameter.numel()
    model = model.to(device).eval()
    image = torch.zeros(
        (1, 3, args.height, args.width), dtype=torch.float32, device=device
    ).contiguous()
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    wall_started = time.perf_counter()
    timing, peak_bytes = measure_cuda_forward(
        model,
        image,
        warmup=args.warmup,
        iterations=args.iterations,
        expected_channels=space.num_classes,
    )
    benchmark_wall_clock_s = time.perf_counter() - wall_started
    checkpoint_bytes = args.ckpt.stat().st_size
    now = datetime.now(UTC).isoformat(timespec="seconds")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "model_id": args.model_id,
        "measured_at": now,
        "status": "complete",
        "benchmark_scope": "model_level_railsem19_proxy",
        "applies_to": list(args.applies_to),
        "source": {
            "campaign_git_sha": source_sha,
            "git_dirty": source_dirty,
            "config_hash": config_hash(to_dict(cfg)),
            "resolved_config": str(args.config),
            "config_sha256": _sha256(args.config),
            "checkpoint_sha256": _sha256(args.ckpt),
            "checkpoint_global_step": args.checkpoint_global_step,
            "checkpoint_bytes": checkpoint_bytes,
            "checkpoint_kind": "resume checkpoint with optimizer and EMA state",
            "weights": "ema" if use_ema else "raw",
            "measured_checkpoint_job_id": args.measured_job_id,
            "result_sha256": _sha256(args.result),
            "result_git_sha": result["git_sha"],
            "result_stage": result["stage"],
            "result_seed": result["seed"],
        },
        "hardware": {
            "gpu_name": gpu_name,
            "gpu_uuid": gpu_uuid,
            "logical_device": "cuda:0",
            "physical_visibility_token": physical_gpu,
            "compute_capability": [properties.major, properties.minor],
            "total_memory_bytes": int(properties.total_memory),
        },
        "model": {
            "parameter_count": parameter_count,
            "trainable_parameter_count": trainable_parameter_count,
            "resident_parameter_bytes": resident_parameter_bytes,
            "parameter_dtype_counts": parameter_dtype_counts,
        },
        "contract": {
            "backend": "pytorch",
            "precision": "bf16_autocast",
            "batch_size": 1,
            "input_shape_nchw": [1, 3, args.height, args.width],
            "warmup_iterations": args.warmup,
            "measured_iterations": args.iterations,
            "timing": "per-forward CUDA events with end-event synchronization",
            "includes_preprocessing": False,
            "includes_data_loader": False,
            "includes_sliding_window": False,
            "input_resident_on_gpu": True,
            "model_only": True,
            "entrypoint": "public model(image) dense-logits forward",
        },
        "measurements": {
            "latency": timing,
            "peak_reserved_bytes": peak_bytes,
            "memory_kind": "pytorch_cuda_allocator_peak_reserved_excluding_context",
            "benchmark_wall_clock_s": benchmark_wall_clock_s,
        },
        "started_at": started_at,
        "finished_at": now,
        "environment": collect_env(),
    }
    _atomic_json(args.out, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="fully resolved campaign config")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--measured-job-id", required=True)
    parser.add_argument("--applies-to", required=True, nargs="+")
    parser.add_argument("--ckpt", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--expected-result-git-sha", required=True)
    parser.add_argument("--expected-result-stage", required=True)
    parser.add_argument("--expected-seed", required=True, type=int)
    parser.add_argument("--checkpoint-global-step", required=True, type=int)
    weights = parser.add_mutually_exclusive_group()
    weights.add_argument("--ema", action="store_true")
    weights.add_argument("--auto-weights", action="store_true")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--required-gpu-name", default="NVIDIA L40S")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.height < 1 or args.width < 1:
        parser.error("input height and width must be positive")
    if args.warmup < 1 or args.iterations < 1:
        parser.error("warmup and iterations must be positive")
    try:
        payload = run_benchmark(args)
    except (OSError, RuntimeError, ValueError, PerformanceError) as exc:
        print(f"performance benchmark error: {exc}", file=sys.stderr)
        return 2
    measurements = payload["measurements"]
    print(
        f"wrote {args.out}: {measurements['latency']['fps']:.2f} FPS, "
        f"p95 {measurements['latency']['p95_ms']:.2f} ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
