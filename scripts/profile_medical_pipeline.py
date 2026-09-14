#!/usr/bin/env python3
"""Profile scratch CT training on audited training examinations only.

Example (output must not already exist; no resumable training run is created):
  python scripts/profile_medical_pipeline.py --config model.json \
      --manifest task07.json --splits split.json --output /data/profile/unet --trace

The diagnostic deliberately synchronizes CUDA around stages. Its stage timings
and profiler overhead are not uninstrumented campaign throughput. Full-volume
inference uses a training examination, never validation/test patients for tuning.
Generated output contains numerical diagnostics and optionally a Chrome trace;
temporary CT arrays, predictions and diagnostic weights are not published.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import functools
import importlib.metadata
import json
import os
import platform
import random
import resource
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from segmentary.medical.backend import _atomic_json, _lock
from segmentary.medical.cli import _config
from segmentary.medical.data import load_manifest, validate_splits
from segmentary.medical.geometry import sha256_file
from segmentary.medical.model_registry import build_model
from segmentary.medical.torch_cache import build_cached_case, load_cached_case
from segmentary.medical.torch_config import TorchConfig
from segmentary.medical.torch_data import predict_case, preprocess_case, sample_patch, training_loss
from segmentary.medical.torch_numerics import clip_grad_norm_


def _statistics(values: list[float]) -> dict:
    return {
        "count": len(values),
        "mean_seconds": float(np.mean(values)),
        "p50_seconds": float(np.percentile(values, 50)),
        "p95_seconds": float(np.percentile(values, 95)),
        "min_seconds": min(values),
        "max_seconds": max(values),
    }


def _system() -> dict:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    result: dict[str, Any] = {
        "max_rss_bytes": usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
        "major_page_faults": usage.ru_majflt,
        "minor_page_faults": usage.ru_minflt,
        "voluntary_context_switches": usage.ru_nvcsw,
        "involuntary_context_switches": usage.ru_nivcsw,
        "file_descriptor_limit": list(resource.getrlimit(resource.RLIMIT_NOFILE)),
        "child_user_cpu_seconds": children.ru_utime,
        "child_system_cpu_seconds": children.ru_stime,
    }
    for key, file in (
        ("process_io", "/proc/self/io"),
        ("pressure_cpu", "/proc/pressure/cpu"),
        ("pressure_io", "/proc/pressure/io"),
        ("pressure_memory", "/proc/pressure/memory"),
    ):
        try:
            result[key] = Path(file).read_text().strip()
        except OSError:
            result[key] = None
    status = Path("/proc/self/status")
    if status.exists():
        result["process_status"] = {
            key: value.strip()
            for line in status.read_text().splitlines()
            if ":" in line
            for key, value in [line.split(":", 1)]
            if key in {"Threads", "VmPeak", "VmRSS", "VmHWM", "FDSize"}
        }
    return result


def _timed(function: Callable[[], Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    result = function()
    return result, time.perf_counter() - started


def _select_cases(manifest: dict, splits: dict) -> list[dict]:
    validate_splits(manifest, splits)
    lookup = {case["case_id"]: case for case in manifest["cases"]}
    ordered = sorted(
        (lookup[key] for key in splits["train"]),
        key=lambda case: (int(np.prod(case["shape"])), case["case_id"]),
    )
    if not ordered:
        raise ValueError("Profiling requires a nonempty validated training partition")
    result = []
    for index in dict.fromkeys((0, len(ordered) // 2, len(ordered) - 1)):
        case = ordered[index]
        if case["annotation_status"] != "labeled" or case.get("label") is None:
            raise ValueError("Profiling requires fully annotated training examinations")
        for key in ("image", "label"):
            if sha256_file(Path(case[key])) != case[f"{key}_sha256"]:
                raise ValueError(f"Training source {key} no longer matches its audited hash")
        result.append(case)
    return result


def _legacy_sample(data: dict, config: TorchConfig, rng: np.random.Generator) -> tuple:
    """Frozen previous algorithm for measured whole-volume-copy comparison."""
    if _legacy_sampler_inapplicable_reason(config) is not None:
        raise ValueError("Historical sampler comparison is not applicable to this recipe")
    assert config.foreground_probability is not None
    image, label = data["image"], data["label"]
    center = [int(rng.integers(size)) for size in label.shape]
    if rng.random() < config.foreground_probability:
        classes = [c for c in (1, 2) if np.any(label == c)]
        if classes:
            locations = np.argwhere(label == rng.choice(classes))
            center = locations[int(rng.integers(len(locations)))].tolist()
    if config.mode == "3d":
        image = image[None]
    else:
        offsets = np.arange(config.context_slices) - config.context_slices // 2
        image = image[np.clip(center[0] + offsets, 0, image.shape[0] - 1)]
        label = label[center[0]]
        center = center[1:]
    padding = [
        (max(0, (p - n) // 2), max(0, p - n - (p - n) // 2))
        for n, p in zip(label.shape, config.patch_size, strict=True)
    ]
    image = np.pad(image, [(0, 0), *padding])
    label = np.pad(label, padding)
    starts = [
        max(0, min(c + pad[0] - p // 2, n - p))
        for c, pad, p, n in zip(center, padding, config.patch_size, label.shape, strict=True)
    ]
    region = tuple(
        slice(start, start + p) for start, p in zip(starts, config.patch_size, strict=True)
    )
    image, label = image[(slice(None), *region)], label[region]
    if config.augment:
        for axis in range(label.ndim):
            if rng.random() < 0.5:
                image, label = np.flip(image, axis + 1), np.flip(label, axis)
    return image.copy(), label.astype(np.int64).copy()


def _legacy_sampler_inapplicable_reason(config: TorchConfig) -> str | None:
    if config.foreground_probability is None:
        return "Explicit center distribution differs from the historical foreground sampler"
    if config.rotation_probability or config.intensity_scale_probability:
        return "Enabled rotation/intensity augmentation is absent from the historical sampler"
    return None


def _data_profile(
    case: dict, config: TorchConfig, root: Path, iterations: int
) -> tuple[dict, dict]:
    raw, preprocess_seconds = _timed(lambda: preprocess_case(case, config, with_label=True))
    legacy_path = root / f"{case['case_id']}.npz"
    _, save_seconds = _timed(lambda: np.savez_compressed(legacy_path, **raw))
    npz_bytes = legacy_path.stat().st_size
    record, shared_seconds = _timed(lambda: build_cached_case(case, config, root / "shared"))
    mapped, verified_load_seconds = _timed(lambda: load_cached_case(record))
    load_timings: dict[str, list[float]] = {"legacy_npz": [], "mapped_npy": []}
    legacy_reason = _legacy_sampler_inapplicable_reason(config)
    sample_timings: dict[str, list[float]] = {"current_raw": [], "optimized": []}
    if legacy_reason is None:
        sample_timings["legacy"] = []
    for iteration in range(iterations):
        started = time.perf_counter()
        with np.load(legacy_path, allow_pickle=False) as archive:
            loaded = {key: archive[key] for key in archive.files}
        load_timings["legacy_npz"].append(time.perf_counter() - started)
        del loaded
        loaded, elapsed = _timed(lambda: load_cached_case(record, verify=False))
        load_timings["mapped_npy"].append(elapsed)
        del loaded
        expected_rng = np.random.default_rng(config.seed + iteration)
        actual_rng = np.random.default_rng(config.seed + iteration)
        expected, elapsed = _timed(functools.partial(sample_patch, raw, config, expected_rng))
        sample_timings["current_raw"].append(elapsed)
        actual, elapsed = _timed(functools.partial(sample_patch, mapped, config, actual_rng))
        sample_timings["optimized"].append(elapsed)
        for left, right in zip(expected, actual, strict=True):
            np.testing.assert_array_equal(left, right)
        if expected_rng.bit_generator.state != actual_rng.bit_generator.state:
            raise ValueError("Cached current-recipe sampling changed random-state consumption")
        if legacy_reason is None:
            legacy_rng = np.random.default_rng(config.seed + iteration)
            historical, elapsed = _timed(functools.partial(_legacy_sample, raw, config, legacy_rng))
            sample_timings["legacy"].append(elapsed)
            for left, right in zip(historical, actual, strict=True):
                np.testing.assert_array_equal(left, right)
            if legacy_rng.bit_generator.state != actual_rng.bit_generator.state:
                raise ValueError("Current recipe changed historical sampling RNG consumption")
    legacy_path.unlink()
    return {
        "case_id": case["case_id"],
        "native_shape_xyz": case["shape"],
        "processed_shape_zyx": list(raw["image"].shape),
        "source_sha256": {key: case[f"{key}_sha256"] for key in ("image", "label")},
        "preprocess_seconds": preprocess_seconds,
        "npz_compress_write_seconds": save_seconds,
        "npz_bytes": npz_bytes,
        "shared_build_including_second_preprocess_and_hashes_seconds": shared_seconds,
        "npy_bytes": sum(path.stat().st_size for path in Path(record["path"]).glob("*.npy")),
        "verified_mmap_load_seconds": verified_load_seconds,
        "shared_cache_fingerprint": record["fingerprint"],
        "load": {key: _statistics(value) for key, value in load_timings.items()},
        "sample": {key: _statistics(value) for key, value in sample_timings.items()},
        "bitwise_samples_and_rng_equal": True,
        "sample_parity_reference": "current recipe on raw arrays versus mapped NPY arrays",
        "legacy_sampler_comparison": {
            "applicable": legacy_reason is None,
            "reason": legacy_reason,
            "bitwise_samples_and_rng_equal": True if legacy_reason is None else None,
        },
        "raw_sampling_policy": "Current sampler may retain foreground coordinates in the case dictionary after its first sample",
        "disk_cache_policy": "OS page cache was not dropped; no sudo; repeated warm reads",
        "mmap_policy": "mapping time excludes lazy page faults; sampled patch time includes access",
    }, mapped


def _model_profile(
    case: dict, data: dict, config: TorchConfig, output: Path, trace: bool, skip_inference: bool
) -> dict:
    device = torch.device("cpu" if config.gpu == "cpu" else "cuda:0")
    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.set_num_threads(config.workers)
    torch.use_deterministic_algorithms(config.deterministic)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = config.deterministic
    if device.type == "cuda":
        torch.cuda.manual_seed_all(config.seed)
        torch.cuda.reset_peak_memory_stats(device)
    model = build_model(
        config.model,
        in_channels=config.context_slices,
        patch_size=config.patch_size,
        model_options=config.model_options,
    ).to(device)
    optimizer = torch.optim.AdamW(
        [
            {
                "params": [
                    p
                    for p in model.parameters()
                    if p.requires_grad and not getattr(p, "_no_weight_decay", False)
                ],
                "weight_decay": config.weight_decay,
            },
            {
                "params": [
                    p
                    for p in model.parameters()
                    if p.requires_grad and getattr(p, "_no_weight_decay", False)
                ],
                "weight_decay": 0,
            },
        ],
        lr=config.learning_rate,
    )
    scaler = torch.amp.GradScaler("cuda", enabled=config.precision == "fp16")
    rng = np.random.default_rng(config.seed)
    timings: dict[str, list[float]] = {
        key: []
        for key in ("sample", "host_to_device", "forward", "backward", "optimizer", "whole_step")
    }
    losses = []

    def sync() -> None:
        if device.type == "cuda":
            torch.cuda.synchronize(device)

    def stage(name: str, function: Callable[[], Any], record: bool) -> Any:
        sync()
        started = time.perf_counter()
        with torch.profiler.record_function(f"medical::{name}"):
            result = function()
            sync()
        if record:
            timings[name].append(time.perf_counter() - started)
        return result

    def step(record: bool) -> None:
        started = time.perf_counter()
        patches = stage(
            "sample",
            lambda: [sample_patch(data, config, rng) for _ in range(config.batch_size)],
            record,
        )
        images, labels = stage(
            "host_to_device",
            lambda: (
                torch.from_numpy(np.stack([item[0] for item in patches])).to(device),
                torch.from_numpy(np.stack([item[1] for item in patches])).to(device),
            ),
            record,
        )
        optimizer.zero_grad(set_to_none=True)

        def forward() -> torch.Tensor:
            dtype = torch.bfloat16 if config.precision == "bf16" else torch.float16
            with torch.autocast(
                device_type=device.type, dtype=dtype, enabled=config.precision != "fp32"
            ):
                loss = training_loss(model, images, labels, config)
            if not torch.isfinite(loss):
                raise ValueError("Non-finite diagnostic training loss")
            return loss

        loss = stage("forward", forward, record)
        stage("backward", lambda: scaler.scale(loss).backward(), record)

        def update() -> None:
            scaler.unscale_(optimizer)
            clip_grad_norm_(model.parameters(), config.gradient_clip)
            scaler.step(optimizer)
            scaler.update()

        stage("optimizer", update, record)
        if record:
            timings["whole_step"].append(time.perf_counter() - started)
            losses.append(float(loss.detach()))

    for _ in range(3):
        step(False)
    activities = [torch.profiler.ProfilerActivity.CPU]
    if device.type == "cuda":
        activities.append(torch.profiler.ProfilerActivity.CUDA)
    profiler = (
        torch.profiler.profile(
            activities=activities, record_shapes=True, profile_memory=True, acc_events=True
        )
        if trace
        else None
    )
    with profiler if profiler is not None else contextlib.nullcontext():
        for _ in range(5):
            step(True)
            if profiler is not None:
                profiler.step()
    result: dict[str, Any] = {
        "warmup_steps": 3,
        "measured_steps": 5,
        "parameters": sum(p.numel() for p in model.parameters()),
        "losses": losses,
        "timings": {key: _statistics(value) for key, value in timings.items()},
        "cuda_synchronized_per_stage": True,
        "profiler_enabled": trace,
        "learning_rate_policy": "diagnostic constant AdamW learning rate; not a resumable campaign run",
        "initialization": "scratch; no external weights",
    }
    if profiler is not None:
        profiler.export_chrome_trace(str(output / "trace.json"))
        events = profiler.key_averages()
        # Include both host and device bottlenecks: sorting only by host time
        # can hide long CUDA kernels whose launches are cheap on the CPU.
        selected_events = {
            event.key: event
            for attribute in ("self_cpu_time_total", "self_device_time_total")
            for event in sorted(events, key=lambda item: getattr(item, attribute), reverse=True)[
                :60
            ]
        }
        result["operators"] = [
            {
                "name": event.key,
                "count": event.count,
                "self_cpu_time_us": event.self_cpu_time_total,
                "self_device_time_us": event.self_device_time_total,
                "self_cpu_memory_bytes": event.self_cpu_memory_usage,
                "self_device_memory_bytes": event.self_device_memory_usage,
            }
            for event in selected_events.values()
        ]
    with tempfile.TemporaryDirectory(prefix="checkpoint-profile-", dir=output) as directory:
        path = Path(directory) / "diagnostic.pth"
        sync()
        _, elapsed = _timed(
            lambda: torch.save(
                {
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "scaler": scaler.state_dict(),
                },
                path,
            )
        )
        result["checkpoint_serialization"] = {
            "seconds": elapsed,
            "bytes": path.stat().st_size,
            "retained": False,
            "storage": "temporary directory; serialization only, no fsync/atomic-index cost",
        }
    if skip_inference:
        result["native_inference"] = {"status": "explicitly_skipped"}
    else:
        image_only = {"case_id": case["case_id"], "image": case["image"]}
        baseline_config = dataclasses.replace(config, inference_batch_size=1)
        sync()
        baseline, first_seconds = _timed(
            lambda: predict_case(model, image_only, baseline_config, device)
        )
        sync()
        batched, batch_seconds = _timed(lambda: predict_case(model, image_only, config, device))
        sync()
        if baseline.shape != tuple(case["shape"]) or batched.shape != baseline.shape:
            raise ValueError("Diagnostic inference did not preserve the complete native volume")
        result["native_inference"] = {
            "case_id": case["case_id"],
            "partition": "train",
            "batch_1_seconds": first_seconds,
            "configured_batch_size": config.inference_batch_size,
            "configured_batch_seconds": batch_seconds,
            "argmax_disagreement_voxels": int(np.count_nonzero(baseline != batched)),
            "native_voxels": int(baseline.size),
            "labels_opened_for_inference": False,
            "note": "Argmax differences may expose batch-dependent floating-point behavior; no quality score is computed",
        }
    if device.type == "cuda":
        result["peak_allocated_cuda_bytes"] = torch.cuda.max_memory_allocated(device)
        result["peak_reserved_cuda_bytes"] = torch.cuda.max_memory_reserved(device)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "manifest", "splits", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--trace", action="store_true")
    parser.add_argument(
        "--skip-inference",
        action="store_true",
        help="Explicitly omit the potentially long full-volume diagnostic",
    )
    args = parser.parse_args()
    if not 1 <= args.iterations <= 20:
        parser.error("--iterations must be between 1 and 20")
    config = _config(args.config)
    if not isinstance(config, TorchConfig):
        raise ValueError("This profiler requires a scratch torch medical recipe")
    torch.set_num_threads(config.workers)
    if config.gpu != "cpu":
        inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
        if inherited is not None and config.gpu not in inherited.split(","):
            raise ValueError("Configured GPU is outside inherited CUDA visibility")
        os.environ["CUDA_VISIBLE_DEVICES"] = config.gpu
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    packages: dict[str, str | None] = {}
    for name in (
        "torch",
        "torchvision",
        "numpy",
        "scipy",
        "nibabel",
        "monai",
        "mamba-ssm",
        "transformers",
        "timm",
        "segmentation-models-pytorch",
        "einops",
        "ml-collections",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    git_head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    git_status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    summary: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "created_at": datetime.now(UTC).isoformat(),
        "purpose": "training-partition pipeline performance diagnostic; not model quality evidence",
        "config": {**dataclasses.asdict(config), "workspace": str(config.workspace)},
        "source_sha256": {
            str(path.relative_to(root)): sha256_file(path)
            for path in sorted((root / "src" / "segmentary" / "medical").rglob("*.py"))
        },
        "profiler_source_sha256": sha256_file(Path(__file__)),
        "git_commit": git_head.stdout.strip() if git_head.returncode == 0 else None,
        "git_dirty": bool(git_status.stdout.strip()) if git_status.returncode == 0 else None,
        "manifest_sha256": sha256_file(args.manifest),
        "splits_sha256": sha256_file(args.splits),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "packages": packages,
            "torch_cuda_build": torch.version.cuda,
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "cpu_threads": config.workers,
            "torch_threads": torch.get_num_threads(),
            "torch_interop_threads": torch.get_num_interop_threads(),
            "thread_environment": {
                key: os.environ.get(key)
                for key in (
                    "OMP_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                )
            },
        },
        "system_before": _system(),
        "data": [],
    }
    _atomic_json(args.output / "summary.json", summary)
    try:
        manifest = load_manifest(args.manifest, verify_files=False)
        splits = json.loads(args.splits.read_text())
        cases = _select_cases(manifest, splits)
        summary["manifest_fingerprint"] = manifest["fingerprint"]
        summary["splits_fingerprint"] = splits["fingerprint"]
        summary["case_selection"] = (
            "Smallest, median and largest native voxel counts in the training partition, ties by case_id"
        )
        with tempfile.TemporaryDirectory(prefix="data-profile-", dir=args.output) as directory:
            selected_data = None
            for case in cases:
                record, mapped = _data_profile(case, config, Path(directory), args.iterations)
                summary["data"].append(record)
                if selected_data is None:
                    selected_data = mapped
                _atomic_json(args.output / "summary.json", summary)
            lockroot = Path(
                os.environ.get(
                    "SEGMENTARY_MEDICAL_LOCK_DIR", f"/tmp/segmentary-medical-{os.getuid()}"
                )
            )
            lock = (
                _lock(lockroot / f"gpu-{config.gpu}.lock")
                if config.gpu != "cpu"
                else contextlib.nullcontext()
            )
            with lock:
                if config.gpu != "cpu":
                    properties = torch.cuda.get_device_properties(0)
                    summary["environment"]["gpu"] = {
                        "name": properties.name,
                        "total_memory_bytes": properties.total_memory,
                        "capability": [properties.major, properties.minor],
                    }
                assert selected_data is not None
                summary["model"] = _model_profile(
                    cases[0], selected_data, config, args.output, args.trace, args.skip_inference
                )
        summary["status"] = "completed"
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["traceback"] = traceback.format_exc()
        raise
    finally:
        summary["system_after"] = _system()
        summary["finished_at"] = datetime.now(UTC).isoformat()
        _atomic_json(args.output / "summary.json", summary)
    print(json.dumps({"status": summary["status"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
