#!/usr/bin/env python3
"""Measure verified scratch checkpoints with a fixed batch-one GPU protocol.

Each model runs in a fresh process with its recorded interpreter and source.
The shared medical GPU lock and an idle-device check precede any CUDA work.
Only public dense model.forward is timed: clinical preprocessing, transfers,
sliding windows, external softmax, reconstruction, metrics and export are absent.
The output is patch throughput, never clinical examinations per second.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def summarize_latency(samples: list[float]) -> dict[str, float]:
    if not samples or any(not math.isfinite(value) or value <= 0 for value in samples):
        raise ValueError("CUDA latency samples must be finite and positive")
    ordered = sorted(samples)

    def percentile(fraction: float) -> float:
        position = fraction * (len(ordered) - 1)
        low = math.floor(position)
        high = math.ceil(position)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)

    return {
        "mean": statistics.mean(samples),
        "p50": percentile(0.5),
        "p95": percentile(0.95),
        "min": min(samples),
        "max": max(samples),
    }


def occupied_gpu_processes(gpu: str, gpu_inventory: str, process_inventory: str) -> list[int]:
    """Resolve physical index to UUID; reject malformed telemetry, not just busy GPUs."""
    lookup = {}
    for line in gpu_inventory.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 2 or not fields[0].isdigit() or not fields[1].startswith("GPU-"):
            raise ValueError("Malformed GPU identity inventory")
        lookup[fields[0]] = fields[1]
    if gpu not in lookup:
        raise ValueError("Requested physical GPU is absent")
    occupants = []
    for line in process_inventory.splitlines():
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 2 or not fields[0].startswith("GPU-") or not fields[1].isdigit():
            raise ValueError("Malformed GPU process inventory")
        if fields[0] == lookup[gpu]:
            occupants.append(int(fields[1]))
    return occupants


def check_idle(gpu: str) -> None:
    inventory = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader,nounits"],
        text=True,
        timeout=15,
    )
    processes = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader,nounits"],
        text=True,
        timeout=15,
    )
    occupants = occupied_gpu_processes(gpu, inventory, processes)
    if occupants:
        raise RuntimeError(f"GPU {gpu} has active CUDA processes {occupants}; no benchmark started")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def check_runtime(expected: dict, actual: dict | None = None) -> None:
    if actual is None:
        import importlib.metadata

        actual = {
            "python": sys.version,
            "executable": sys.executable,
            "packages": dict(
                sorted(
                    (distribution.metadata["Name"], distribution.version)
                    for distribution in importlib.metadata.distributions()
                    if "Name" in distribution.metadata
                )
            ),
        }
    expected, actual = dict(expected), dict(actual)
    for runtime in (expected, actual):
        runtime["executable"] = str(Path(runtime["executable"]).resolve())
    if actual != expected:
        raise ValueError("Benchmark is not executing in the recorded Python/package runtime")


def load_verified_checkpoint(backend: Any, config: Any) -> tuple[dict, str]:
    """Deserialize exactly the bytes checked, including for older frozen sources."""
    if hasattr(backend, "_load_checkpoint"):
        return backend._load_checkpoint(config, "checkpoint_best.pth")
    import hashlib
    import io

    import torch

    # Older frozen campaigns lack the new bytes-bound loader; their ordinary
    # provenance guard still runs before this additional exact-buffer check.
    path = backend._checkpoint(config, "checkpoint_best.pth")
    index = read_json(config.root / "checkpoint-index.json")
    expected = index["files"]["checkpoint_best.pth"]
    if path.name != expected["path"]:
        raise ValueError("Best checkpoint pointer changed while capturing benchmark input")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected["sha256"]:
        raise ValueError("Checkpoint bytes differ from their recorded SHA-256")
    state = torch.load(io.BytesIO(data), map_location="cpu", weights_only=False)
    if not isinstance(state, dict):
        raise ValueError("Checkpoint payload is not a state mapping")
    return state, digest


@contextlib.contextmanager
def quiescent_workspace(workspace: Path) -> Iterator[None]:
    """Support both old and new source snapshots without mutating their locks."""
    import fcntl

    path = workspace / ".stage.lock"
    if not path.is_file():
        raise ValueError("Workspace has no existing stage lock")
    with path.open("rb") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Workspace has an active stage; no benchmark started") from exc
        try:
            active = workspace / "active-stage.json"
            if active.exists() and read_json(active).get("status") in {"running", "starting"}:
                raise RuntimeError("Workspace records an unfinished stage; no benchmark started")
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def select_runs(spec: dict, run_ids: list[str]) -> list[dict]:
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Repeated benchmark run ids are not allowed")
    wanted = set(run_ids)
    runs = [
        run
        for run in spec["runs"]
        if run.get("backend") == "torch" and (not wanted or run["id"] in wanted)
    ]
    if not runs or wanted - {run["id"] for run in runs}:
        raise ValueError("Benchmark only known Torch run ids; nnU-Net uses a separate protocol")
    return runs


def run_worker(spec: dict, run: dict, gpu: str) -> dict:
    source = Path(spec["source_root"]).resolve()
    sys.path.insert(0, str(source / "src"))
    from segmentary.medical import torch_backend as backend
    from segmentary.medical.backend import _atomic_json, _digest, _json, _lock, _sha
    from segmentary.medical.torch_config import TorchConfig

    if Path(backend.__file__).resolve().parents[3] != source:
        raise ValueError("Benchmark imported a different source tree")
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, timeout=15
    ).strip()
    if revision != spec["source_commit"]:
        raise ValueError("Benchmark source revision differs from the campaign")
    workspace = Path(run["workspace"]).resolve()
    config = TorchConfig(**_json(workspace / "resolved-config.json"))
    if config.root != workspace or config.backend_python != sys.executable:
        raise ValueError("Benchmark must use the original workspace and recorded interpreter")
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    if inherited is not None and gpu not in inherited.split(","):
        raise ValueError("Benchmark GPU exceeds inherited CUDA_VISIBLE_DEVICES")
    if config.gpu == "cpu":
        raise ValueError("Standard inference benchmark requires a recorded GPU experiment")
    output_path = workspace / "standard-inference.json"
    if output_path.exists():
        raise FileExistsError(
            "Standard benchmark artifact already exists; preserve it and use a separate workspace"
        )
    lock_root = Path(
        os.environ.get(
            "SEGMENTARY_MEDICAL_LOCK_DIR",
            str(Path(tempfile.gettempdir()) / f"segmentary-medical-{os.getuid()}"),
        )
    )
    # _binding/_checkpoint run before narrowing CUDA visibility: their runtime
    # probe must retain the original model's recorded physical GPU setting.
    with quiescent_workspace(workspace):
        binding = backend._binding(config)
        check_runtime(binding["runtime"])
        origin = _json(workspace / "scratch-origin.json")
        if origin.get("initialization") != "scratch" or origin.get("external_weight_loads") != 0:
            raise ValueError(
                "Only this experiment's verified scratch checkpoint can be benchmarked"
            )
        with _lock(lock_root / f"gpu-{gpu}.lock"):
            check_idle(gpu)
            state, checkpoint_sha = load_verified_checkpoint(backend, config)
            if state.get("identity") != _digest(binding) or state.get("origin") != origin:
                raise ValueError("Loaded checkpoint identity or scratch origin differs")
            import torch

            if torch.cuda.is_initialized():
                raise RuntimeError("CUDA was initialized before binding the benchmark GPU")
            os.environ["CUDA_VISIBLE_DEVICES"] = gpu
            os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["PYTHONNOUSERSITE"] = "1"
            os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
            from segmentary.medical.model_registry import build_model

            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is unavailable")
            backend._seed(config)
            device = torch.device("cuda:0")
            model = build_model(
                config.model,
                in_channels=config.context_slices,
                patch_size=config.patch_size,
                model_options=config.model_options,
            )
            model.load_state_dict(state["model"], strict=True)
            del state
            parameters = sum(parameter.numel() for parameter in model.parameters())
            weight_bytes = sum(
                value.numel() * value.element_size() for value in model.state_dict().values()
            )
            model = model.to(device).eval()
            generator = torch.Generator(device=device).manual_seed(config.seed)
            inputs = torch.rand(
                (1, config.context_slices, *config.patch_size),
                generator=generator,
                dtype=torch.float32,
                device=device,
            )
            autocast_dtype = torch.bfloat16 if config.precision == "bf16" else torch.float16
            samples = []
            with (
                torch.inference_mode(),
                torch.autocast("cuda", dtype=autocast_dtype, enabled=config.precision != "fp32"),
            ):
                for _ in range(10):
                    output = model(inputs)
                torch.cuda.synchronize()
                if tuple(output.shape) != (1, 3, *config.patch_size) or not bool(
                    torch.isfinite(output).all()
                ):
                    raise ValueError("Public forward returned invalid dense logits")
                del output
                torch.cuda.reset_peak_memory_stats()
                start, finish = (
                    torch.cuda.Event(enable_timing=True),
                    torch.cuda.Event(enable_timing=True),
                )
                for _ in range(50):
                    start.record()
                    output = model(inputs)
                    finish.record()
                    finish.synchronize()
                    samples.append(float(start.elapsed_time(finish)))
                    del output
            latency = summarize_latency(samples)
            result = {
                "schema_version": 1,
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "status": "completed",
                "input_scope": "synthetic_model_only",
                "model": config.model,
                "batch_size": 1,
                "patch_size": list(config.patch_size),
                "context_slices": config.context_slices,
                "precision": config.precision,
                "warmup_iterations": 10,
                "measured_iterations": 50,
                "sample_latencies_ms": samples,
                "latency_ms": latency,
                "patches_per_second": 1000.0 / latency["mean"],
                "parameters": parameters,
                "model_weight_bytes": weight_bytes,
                "model_weight_bytes_scope": "state_dict parameters and buffers, excluding optimizer",
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                "checkpoint_sha256": checkpoint_sha,
                "config_fingerprint": _digest(binding["config"]),
                "code_fingerprint": _digest(binding["code"]),
                "runtime_fingerprint": _digest(binding["runtime"]),
                "gpu_name": torch.cuda.get_device_name(device),
                "physical_gpu": gpu,
                "source_commit": spec["source_commit"],
                "binding_identity": _digest(binding),
                "benchmark_script_sha256": _sha(Path(__file__)),
                "torch_version": torch.__version__,
                "timing_scope": "CUDA events around public dense forward including query-mask collapse; excludes input allocation/transfers, external softmax, tiling, preprocessing, reconstruction, metrics and export",
                "memory_scope": "peak after warmup with model and batch-one input resident; reserved includes warm allocator blocks",
                "input_distribution": "seeded uniform float32 [0,1), autocast follows frozen inference precision",
                "limitations": "One GPU and synthetic fixed patch; not examinations/s, deployment latency, accuracy or end-to-end CT performance",
            }
            _atomic_json(output_path, result)
            return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign", type=Path, required=True, help="Campaign directory containing campaign.json"
    )
    parser.add_argument(
        "--gpu", required=True, help="Idle physical GPU index; original configs are unchanged"
    )
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--worker-run-id", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.gpu.isdigit() or str(int(args.gpu)) != args.gpu:
        raise ValueError("GPU must be a canonical physical numeric index")
    spec = read_json(args.campaign.resolve() / "campaign.json")
    runs = select_runs(spec, [args.worker_run_id] if args.worker_run_id else args.run_id)
    if args.worker_run_id:
        result = run_worker(spec, runs[0], args.gpu)
        print(
            json.dumps(
                {
                    "model": result["model"],
                    "latency_ms": result["latency_ms"],
                    "patches_per_second": result["patches_per_second"],
                }
            ),
            flush=True,
        )
        return 0
    for run in runs:
        config = read_json(Path(run["workspace"]) / "resolved-config.json")
        command = [
            config["backend_python"],
            str(Path(__file__).resolve()),
            "--campaign",
            str(args.campaign.resolve()),
            "--gpu",
            args.gpu,
            "--worker-run-id",
            run["id"],
        ]
        result = subprocess.run(command, check=False, timeout=900)
        if result.returncode:
            raise RuntimeError(
                f"Benchmark failed for {run['id']}; earlier completed artifacts remain"
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Medical inference benchmark: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
