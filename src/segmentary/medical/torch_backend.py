"""Isolated scratch CT training, native validation, and bound same-run resume.

One worker owns one GPU; independent recipes/seeds can use different cards. This
backend intentionally uses a declared common AdamW recipe, not each paper's full
training system. nnU-Net retains its separate official trainer and environment.
"""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .backend import _atomic_json, _check_hash, _digest, _documents, _json, _lock, _sha, _stop_child
from .torch_config import TorchConfig


def _config_record(config: TorchConfig) -> dict:
    return json.loads(json.dumps(dataclasses.asdict(config)))


def _code() -> dict:
    root = Path(__file__).parent
    return {str(p.relative_to(root)): _sha(p) for p in sorted(root.rglob("*.py"))}


def _environment(config: TorchConfig) -> dict[str, str]:
    env = dict(os.environ)
    inherited = env.get("CUDA_VISIBLE_DEVICES")
    if config.gpu != "cpu" and inherited is not None and config.gpu not in inherited.split(","):
        raise ValueError("Requested GPU is outside inherited CUDA_VISIBLE_DEVICES")
    env.update(
        CUDA_VISIBLE_DEVICES="" if config.gpu == "cpu" else config.gpu,
        CUDA_DEVICE_ORDER="PCI_BUS_ID",
        HF_HUB_OFFLINE="1",
        WANDB_MODE="disabled",
        PYTHONHASHSEED=str(config.seed),
        PYTHONNOUSERSITE="1",
        PYTHONUNBUFFERED="1",
        OMP_NUM_THREADS=str(config.workers),
        MKL_NUM_THREADS=str(config.workers),
        CUBLAS_WORKSPACE_CONFIG=":4096:8",
        PYTHONPATH=str(Path(__file__).resolve().parents[2]),
    )
    return env


def _runtime(config: TorchConfig) -> dict:
    code = "import importlib.metadata as m,json,sys; print(json.dumps({'python':sys.version,'executable':sys.executable,'packages':dict(sorted((d.metadata['Name'],d.version) for d in m.distributions() if 'Name' in d.metadata))}))"
    completed = subprocess.run(
        [config.backend_python, "-c", code],
        env=_environment(config),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(completed.stdout)


def prepare_dataset(
    manifest_path: str | Path,
    splits_path: str | Path,
    config: TorchConfig,
    *,
    dry_run: bool = False,
) -> dict:
    from .model_registry import model_metadata

    metadata = model_metadata(config.model)
    expected = 3 if config.mode == "3d" else 2
    if metadata["dimensions"] != expected:
        raise ValueError("Architecture dimensionality and CT mode differ")
    allowed = set(
        metadata.get(
            "allowed_options", metadata.get("default_options", metadata.get("options", {}))
        )
    )
    unknown = set(config.model_options) - allowed
    if unknown:
        raise ValueError(f"Unsupported model options: {sorted(unknown)}")
    if config.batch_size < metadata.get("training_batch_minimum", 1):
        raise ValueError("Batch size is below this architecture's training minimum")
    for name, value in config.model_options.items():
        choices = metadata.get("options", {}).get(name, {}).get("choices")
        if choices is not None and value not in choices:
            raise ValueError(f"Unsupported {name}: {value}")
    manifest_path, splits_path = Path(manifest_path).resolve(), Path(splits_path).resolve()
    manifest, splits = _documents(manifest_path, splits_path)
    development = set(splits["train"] + splits["val"])
    for case in manifest["cases"]:
        if case["case_id"] in development:
            if case["annotation_status"] != "labeled" or not case.get("label"):
                raise ValueError("Training and validation require full pancreas/mass labels")
            for key in ("image", "label"):
                _check_hash(case[key], case[f"{key}_sha256"])
    if config.root.exists() and any(config.root.iterdir()):
        raise FileExistsError("Use an empty experiment workspace")
    record = {
        "schema_version": 1,
        "run_id": uuid.uuid4().hex,
        "config": _config_record(config),
        "code": _code(),
        "runtime": _runtime(config),
        "manifest_path": str(manifest_path),
        "splits_path": str(splits_path),
        "manifest_sha256": _sha(manifest_path),
        "splits_sha256": _sha(splits_path),
        "manifest_fingerprint": manifest["fingerprint"],
        "split_fingerprint": splits["fingerprint"],
        "architecture": metadata,
        "initialization": "scratch",
        "preprocessing_fit_scope": "none_fixed_recipe",
        "checkpoint_selection": "maximum validation mean per-case mass Dice; empty/empty=1",
        "purpose": config.purpose,
    }
    result = {
        "action": "prepare",
        "dry_run": dry_run,
        "model": config.model,
        "train_cases": len(splits["train"]),
        "val_cases": len(splits["val"]),
        "test_cases_excluded": len(splits["test"]),
    }
    if not dry_run:
        _atomic_json(config.root / "binding.json", record)
        _atomic_json(config.root / "resolved-config.json", _config_record(config))
    return result


def _binding(config: TorchConfig, *, verify_development: bool = False) -> dict:
    record = _json(config.root / "binding.json")
    if record["config"] != _config_record(config) or record["code"] != _code():
        raise ValueError("Configuration or source changed; create a new experiment")
    if record["runtime"] != _runtime(config):
        raise ValueError("Runtime changed; create a new experiment")
    for key in ("manifest", "splits"):
        _check_hash(record[f"{key}_path"], record[f"{key}_sha256"])
    if verify_development:
        manifest, splits = _documents(record["manifest_path"], record["splits_path"])
        for case in manifest["cases"]:
            if case["case_id"] in splits["train"] + splits["val"]:
                for key in ("image", "label"):
                    _check_hash(case[key], case[f"{key}_sha256"])
    return record


def _run(config: TorchConfig, action: str, payload: dict, *, gpu: bool) -> dict:
    binding = _binding(config)
    directory = config.root / "stages" / f"{action}-{time.time_ns()}"
    with contextlib.ExitStack() as stack:
        fds = [stack.enter_context(_lock(config.root / ".stage.lock"))]
        if gpu and config.gpu != "cpu":
            lockroot = Path(
                os.environ.get(
                    "SEGMENTARY_MEDICAL_LOCK_DIR",
                    str(Path(tempfile.gettempdir()) / f"segmentary-medical-{os.getuid()}"),
                )
            )
            fds.append(stack.enter_context(_lock(lockroot / f"gpu-{config.gpu}.lock")))
        directory.mkdir(parents=True)
        request = directory / "request.json"
        _atomic_json(
            request,
            {
                "config": _config_record(config),
                "action": action,
                "payload": payload,
                "identity": _digest(binding),
            },
        )
        argv = [
            config.backend_python,
            "-m",
            "segmentary.medical.torch_backend",
            "_worker",
            str(request),
        ]
        state: dict[str, Any] = {
            "action": action,
            "status": "starting",
            "argv": argv,
            "started_at": time.time(),
            "log": str(directory / "subprocess.log"),
        }
        statepath = config.root / "active-stage.json"
        _atomic_json(statepath, state)
        process = None
        previous = None
        if threading.current_thread() is threading.main_thread():
            previous = signal.getsignal(signal.SIGTERM)

            def interrupted(_sig: int, _frame: Any) -> None:
                raise KeyboardInterrupt("Stage termination requested")

            signal.signal(signal.SIGTERM, interrupted)
        try:
            with Path(state["log"]).open("wb") as log:
                process = subprocess.Popen(
                    argv,
                    env=_environment(config),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    pass_fds=tuple(fds),
                )
                state.update(status="running", pid=process.pid)
                _atomic_json(statepath, state)
                code = process.wait()
            state.update(
                returncode=code,
                status="completed"
                if code == 0
                else "cancelled"
                if code in (-2, -15, 130, 143)
                else "failed",
            )
            if code:
                raise RuntimeError(f"{action} {state['status']}; see {state['log']}")
        except BaseException as exc:
            _stop_child(process)
            state.update(
                status="cancelled"
                if isinstance(exc, KeyboardInterrupt)
                else state["status"]
                if state["status"] == "cancelled"
                else "failed",
                error=str(exc),
            )
            raise
        finally:
            if previous is not None:
                signal.signal(signal.SIGTERM, previous)
            state["wall_seconds"] = time.time() - state["started_at"]
            state["allocated_gpu_hours"] = (
                state["wall_seconds"] / 3600 if gpu and config.gpu != "cpu" else 0
            )
            _atomic_json(statepath, state)
            _atomic_json(directory / "outcome.json", state)
    return state


def cancel(config: TorchConfig) -> dict:
    state = _json(config.root / "active-stage.json")
    if state["status"] != "running":
        raise ValueError("There is no running worker")
    pid = state["pid"]
    proc = Path(f"/proc/{pid}/cmdline")
    if (
        not proc.exists()
        or state["argv"][-1].encode() not in proc.read_bytes().split(b"\0")
        or os.getpgid(pid) != pid
    ):
        raise RuntimeError("Worker identity changed; refusing cancellation")
    os.killpg(pid, signal.SIGTERM)
    return {"status": "cancellation_requested", "pid": pid}


def _plan(config: TorchConfig) -> dict:
    binding = _binding(config)
    plan = _json(config.root / "plan-binding.json")
    if plan["identity"] != _digest(binding):
        raise ValueError("Preprocessing identity changed")
    if plan.get("cache_format") == "shared_npy":
        from .torch_cache import cache_file_records

        _, splits = _documents(binding["manifest_path"], binding["splits_path"])
        if set(plan["cases"]) != set(splits["train"]):
            raise ValueError("Training cache membership changed")
        for record in plan["cases"].values():
            if cache_file_records(record) != record["files"]:
                raise ValueError("Training cache content changed")
        return plan
    files = {p.name: _sha(p) for p in (config.root / "cache").iterdir() if p.is_file()}
    if plan["files"] != files:
        raise ValueError("Training cache content or membership changed")
    return plan


def plan_and_preprocess(config: TorchConfig, *, dry_run: bool = False) -> dict:
    _binding(config, verify_development=True)
    if (config.root / "cache").exists() or (config.root / "plan-binding.json").exists():
        raise FileExistsError("Preprocessing is immutable; use a fresh workspace")
    if dry_run:
        return {
            "action": "preprocess",
            "dry_run": True,
            "scope": "train_only",
            "fitted_statistics": False,
        }
    return _run(config, "preprocess", {}, gpu=False)


def _checkpoint(config: TorchConfig, name: str) -> Path:
    if name not in {"checkpoint_latest.pth", "checkpoint_best.pth", "checkpoint_final.pth"}:
        raise ValueError("Only checkpoints from this scratch-origin run are accepted")
    index = _json(config.root / "checkpoint-index.json")
    if index["identity"] != _digest(_binding(config)) or index["initialization"] != "scratch":
        raise ValueError("Checkpoint provenance mismatch")
    if name not in index["files"]:
        raise ValueError("Requested checkpoint has not been created")
    item = index["files"][name]
    if Path(item["path"]).name != item["path"]:
        raise ValueError("Checkpoint path escapes its experiment")
    path = config.root / "checkpoints" / item["path"]
    _check_hash(path, item["sha256"])
    return path


def train(
    config: TorchConfig,
    *,
    resume: bool = False,
    resume_checkpoint: str | None = None,
    dry_run: bool = False,
) -> dict:
    _plan(config)
    _binding(config, verify_development=True)
    if not resume and (
        (config.root / "scratch-origin.json").exists() or (config.root / "checkpoints").exists()
    ):
        raise FileExistsError("Existing training state requires explicit resume")
    if resume_checkpoint is not None and not resume:
        raise ValueError("A checkpoint is only valid with explicit resume")
    name = resume_checkpoint or "checkpoint_latest.pth"
    if resume:
        _checkpoint(config, name)
    if dry_run:
        return {
            "action": "resume" if resume else "train",
            "dry_run": True,
            "initialization": "scratch",
        }
    return _run(config, "train", {"resume": resume, "checkpoint": name}, gpu=True)


def predict(
    config: TorchConfig,
    *,
    partition: str = "val",
    final_test: bool = False,
    checkpoint: str = "checkpoint_best.pth",
    dry_run: bool = False,
) -> dict:
    if partition not in {"train", "val", "test", "unlabeled"} or final_test != (
        partition == "test"
    ):
        raise ValueError("Test prediction requires explicit --final-test; use it only for test")
    _plan(config)
    _checkpoint(config, checkpoint)
    output = config.root / "predictions" / partition
    if output.exists():
        raise FileExistsError("Predictions are immutable; choose a fresh experiment")
    if dry_run:
        return {"action": "predict", "dry_run": True, "partition": partition, "output": str(output)}
    return _run(config, "predict", {"partition": partition, "checkpoint": checkpoint}, gpu=True)


def _seed(config: TorchConfig) -> None:
    import numpy as np
    import torch

    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.cuda.manual_seed_all(config.seed)
    torch.set_num_threads(config.workers)
    torch.use_deterministic_algorithms(config.deterministic)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = config.deterministic


def _state_hash(model: Any) -> str:
    import hashlib

    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        digest.update(name.encode())
        digest.update(str(tensor.dtype).encode())
        digest.update(str(tuple(tensor.shape)).encode())
        digest.update(
            tensor.detach()
            .cpu()
            .contiguous()
            .reshape(-1)
            .view(__import__("torch").uint8)
            .numpy()
            .tobytes()
        )
    return digest.hexdigest()


def _save_checkpoint(config: TorchConfig, state: dict, names: list[str]) -> None:
    import torch

    directory = config.root / "checkpoints"
    directory.mkdir(exist_ok=True)
    indexpath = config.root / "checkpoint-index.json"
    index = (
        _json(indexpath)
        if indexpath.exists()
        else {"identity": state["identity"], "initialization": "scratch", "files": {}}
    )
    generation = directory / f"generation-{uuid.uuid4().hex}.pth"
    with generation.open("xb") as stream:
        torch.save(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    item = {"path": generation.name, "sha256": _sha(generation)}
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    for name in names:
        index["files"][name] = item
    # Until this pointer commits, every previously indexed generation remains intact.
    _atomic_json(indexpath, index)
    fd = os.open(config.root, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    keep = {record["path"] for record in index["files"].values()}
    for old in directory.glob("generation-*.pth"):
        if old.name not in keep:
            old.unlink()


def _validation(model: Any, cases: list[dict], config: TorchConfig, device: Any) -> dict:
    import nibabel as nib
    import numpy as np

    from .torch_data import predict_case

    scores: list[dict[str, Any]] = []
    for case in cases:
        _atomic_json(
            config.root / "progress.json",
            {
                "phase": "validation",
                "updated_at": time.time(),
                "completed_cases": len(scores),
                "total_cases": len(cases),
            },
        )
        prediction = predict_case(model, case, config, device)
        label_image: Any = nib.load(case["label"])
        truth = np.asarray(label_image.dataobj)
        pred, target = prediction == 2, truth == 2
        denominator = int(pred.sum()) + int(target.sum())
        organ_pred, organ_target = prediction > 0, truth > 0
        organ_denominator = int(organ_pred.sum()) + int(organ_target.sum())
        scores.append(
            {
                "case_id": case["case_id"],
                "mass_dice": 2 * int((pred & target).sum()) / denominator if denominator else 1.0,
                "pancreas_dice": 2 * int((organ_pred & organ_target).sum()) / organ_denominator
                if organ_denominator
                else 1.0,
                "mass_present": bool(target.any()),
                "predicted_mass_voxels": int(pred.sum()),
            }
        )
    return {
        "mean_mass_dice": float(np.mean([x["mass_dice"] for x in scores])),
        "mean_pancreas_dice": float(np.mean([x["pancreas_dice"] for x in scores])),
        "cases": scores,
        "space": "native_full_volume",
    }


def _train_worker(config: TorchConfig, payload: dict, binding: dict) -> None:
    import numpy as np
    import torch

    from .model_registry import build_model
    from .torch_batches import BatchStream
    from .torch_data import training_loss
    from .torch_numerics import clip_grad_norm_

    _seed(config)
    device = torch.device("cpu" if config.gpu == "cpu" else "cuda:0")
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    if config.precision == "bf16" and not torch.cuda.is_bf16_supported():
        raise RuntimeError("Requested GPU does not support bf16")
    model = build_model(
        config.model,
        in_channels=config.context_slices,
        patch_size=config.patch_size,
        model_options=config.model_options,
    ).to(device)
    origin = {
        "initialization": "scratch",
        "initial_state_sha256": _state_hash(model),
        "identity": _digest(binding),
        "parameters": sum(p.numel() for p in model.parameters()),
        "external_weight_loads": 0,
    }
    if not payload["resume"]:
        _atomic_json(config.root / "scratch-origin.json", origin)
    elif _json(config.root / "scratch-origin.json") != origin:
        raise ValueError("Random initialization differs from this run's recorded origin")
    groups = [
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
            "weight_decay": 0.0,
        },
    ]
    optimizer = torch.optim.AdamW(groups, lr=config.learning_rate)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda step: max(0.0, 1 - step / (config.epochs * config.steps_per_epoch)) ** 0.9
    )
    scaler = torch.amp.GradScaler("cuda", enabled=config.precision == "fp16")
    rng = np.random.default_rng(config.seed)
    epoch, step, best = 0, 0, -1.0
    if payload["resume"]:
        state = torch.load(
            _checkpoint(config, payload["checkpoint"]), map_location="cpu", weights_only=False
        )
        if state["identity"] != _digest(binding) or state["origin"] != origin:
            raise ValueError("Checkpoint identity mismatch")
        model.load_state_dict(state["model"], strict=True)
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        scaler.load_state_dict(state["scaler"])
        random.setstate(state["python_rng"])
        np.random.set_state(state["numpy_rng"])
        rng.bit_generator.state = state["sampling_rng"]
        torch.set_rng_state(state["torch_rng"])
        if device.type == "cuda":
            torch.cuda.set_rng_state_all(state["cuda_rng"])
        epoch, step, best = state["epoch"], state["step"], state["best"]
    manifest, splits = _documents(binding["manifest_path"], binding["splits_path"])
    lookup = {c["case_id"]: c for c in manifest["cases"]}

    plan = _json(config.root / "plan-binding.json") if config.cache_root is not None else {}

    # Five mmap files per case must fit hosts with a 1024 descriptor soft limit.
    # The OS page cache still shares volume pages between independent workers.
    @functools.lru_cache(maxsize=64 if config.cache_root else 2)
    def cached(case_id: str) -> dict:
        if plan.get("cache_format") == "shared_npy":
            from .torch_cache import load_cached_case

            return load_cached_case(plan["cases"][case_id], verify=False)
        with np.load(config.root / "cache" / f"{case_id}.npz", allow_pickle=False) as file:
            return {name: file[name] for name in file.files}

    def checkpoint_state() -> dict:
        return {
            "identity": _digest(binding),
            "origin": origin,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "scaler": scaler.state_dict(),
            "python_rng": random.getstate(),
            "numpy_rng": np.random.get_state(),
            "sampling_rng": rng.bit_generator.state,
            "torch_rng": torch.get_rng_state(),
            "cuda_rng": torch.cuda.get_rng_state_all() if device.type == "cuda" else [],
            "epoch": epoch,
            "step": step,
            "best": best,
        }

    if not payload["resume"]:
        _save_checkpoint(config, checkpoint_state(), ["checkpoint_latest.pth"])
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    with BatchStream(config, splits["train"], cached, rng, device) as batches:
        started = time.monotonic()
        for current in range(epoch, config.epochs):
            epoch_started = time.monotonic()
            model.train()
            losses = []
            for _ in range(config.steps_per_epoch):
                images, labels = next(batches)
                optimizer.zero_grad(set_to_none=True)
                dtype = torch.bfloat16 if config.precision == "bf16" else torch.float16
                with torch.autocast(
                    device_type=device.type, dtype=dtype, enabled=config.precision != "fp32"
                ):
                    loss = training_loss(model, images, labels)
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite training loss")
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                clip_grad_norm_(model.parameters(), config.gradient_clip)
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
                step += 1
                losses.append(float(loss.detach()))
                if step % config.progress_interval == 0 or len(losses) == 1:
                    _atomic_json(
                        config.root / "progress.json",
                        {
                            "phase": "train",
                            "updated_at": time.time(),
                            "epoch": current + 1,
                            "step": step,
                            "target_steps": config.epochs * config.steps_per_epoch,
                            "loss": losses[-1],
                            "epoch_mean_loss": float(np.mean(losses)),
                            "learning_rate": scheduler.get_last_lr()[0],
                            "optimizer_steps_per_second": len(losses)
                            / (time.monotonic() - epoch_started),
                        },
                    )
            epoch = current + 1
            train_seconds = time.monotonic() - epoch_started
            validate = (
                epoch == 1 or epoch % config.validation_interval == 0 or epoch == config.epochs
            )
            validation = (
                _validation(model, [lookup[c] for c in splits["val"]], config, device)
                if validate
                else None
            )
            validation_seconds = time.monotonic() - epoch_started - train_seconds
            improved = validation is not None and validation["mean_mass_dice"] > best
            if validation is not None:
                best = max(best, validation["mean_mass_dice"])
            metrics = {
                "epoch": epoch,
                "step": step,
                "loss": float(np.mean(losses)),
                "learning_rate": scheduler.get_last_lr()[0],
                "validation": validation,
                "best_mass_dice": best,
                "wall_seconds": time.monotonic() - started,
                "epoch_training_seconds": train_seconds,
                "epoch_validation_seconds": validation_seconds,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated()
                if device.type == "cuda"
                else 0,
                "peak_reserved_bytes": torch.cuda.max_memory_reserved()
                if device.type == "cuda"
                else 0,
            }
            _atomic_json(config.root / "metrics" / f"epoch-{epoch:05d}.json", metrics)
            names = ["checkpoint_latest.pth"]
            if improved:
                names.append("checkpoint_best.pth")
            if epoch == config.epochs:
                names.append("checkpoint_final.pth")
            _save_checkpoint(config, checkpoint_state(), names)
            print(json.dumps(metrics), flush=True)
    _atomic_json(
        config.root / "training-result.json",
        {
            "completed": True,
            "epochs": epoch,
            "steps": step,
            "best_mass_dice": best,
            "identity": _digest(binding),
            "initialization": "scratch",
            "purpose": config.purpose,
        },
    )


def _worker(request_path: Path) -> None:
    import numpy as np
    import torch

    from .model_registry import build_model
    from .torch_data import predict_case, preprocess_case

    request = _json(request_path)
    config = TorchConfig(**request["config"])
    binding = _binding(config)
    if request["identity"] != _digest(binding):
        raise ValueError("Worker identity changed")
    manifest, splits = _documents(binding["manifest_path"], binding["splits_path"])
    lookup = {c["case_id"]: c for c in manifest["cases"]}
    if request["action"] == "preprocess":
        directory = config.root / "cache"
        directory.mkdir()
        records = {}
        for case_id in splits["train"]:
            case = lookup[case_id]
            for key in ("image", "label"):
                _check_hash(case[key], case[f"{key}_sha256"])
            if config.cache_root is not None:
                from .torch_cache import build_cached_case

                records[case_id] = build_cached_case(case, config, config.cache_root)
            else:
                data = preprocess_case(case, config, with_label=True)
                np.savez_compressed(directory / f"{case_id}.npz", **data)
            _atomic_json(
                config.root / "progress.json",
                {
                    "phase": "preprocess",
                    "updated_at": time.time(),
                    "completed_cases": splits["train"].index(case_id) + 1,
                    "total_cases": len(splits["train"]),
                },
            )
        _atomic_json(
            config.root / "plan-binding.json",
            {
                "identity": _digest(binding),
                "files": {p.name: _sha(p) for p in directory.iterdir()},
                **({"cache_format": "shared_npy", "cases": records} if config.cache_root else {}),
                "preprocessing": "fixed HU window and RAS spacing; train cache only",
            },
        )
    elif request["action"] == "train":
        _plan(config)
        _train_worker(config, request["payload"], binding)
    elif request["action"] == "predict":
        _seed(config)
        payload = request["payload"]
        device = torch.device("cpu" if config.gpu == "cpu" else "cuda:0")
        model = build_model(
            config.model,
            in_channels=config.context_slices,
            patch_size=config.patch_size,
            model_options=config.model_options,
        ).to(device)
        checkpoint = _checkpoint(config, payload["checkpoint"])
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        if state["identity"] != _digest(binding) or state["origin"] != _json(
            config.root / "scratch-origin.json"
        ):
            raise ValueError("Checkpoint identity mismatch")
        model.load_state_dict(state["model"], strict=True)
        ids = (
            splits[payload["partition"]]
            if payload["partition"] != "unlabeled"
            else [c["case_id"] for c in manifest["cases"] if c["annotation_status"] == "unlabeled"]
        )
        if not ids:
            raise ValueError("Prediction partition is empty")
        output = config.root / "predictions" / payload["partition"]
        output.mkdir(parents=True)
        statuses = []
        for case_id in ids:
            case = lookup[case_id]
            start = time.monotonic()
            try:
                _check_hash(case["image"], case["image_sha256"])
                predict_case(model, case, config, device, output=output / f"{case_id}.nii.gz")
                statuses.append(
                    {
                        "case_id": case_id,
                        "status": "completed",
                        "wall_seconds": time.monotonic() - start,
                    }
                )
            except Exception as exc:
                statuses.append({"case_id": case_id, "status": "failed", "error": str(exc)})
            _atomic_json(
                output / "prediction-status.json",
                {
                    "cases": statuses,
                    "identity": _digest(binding),
                    "checkpoint_sha256": _sha(checkpoint),
                    "partition": payload["partition"],
                },
            )
        if any(x["status"] != "completed" for x in statuses):
            raise RuntimeError("Some predictions failed; inspect prediction-status.json")
    else:
        raise ValueError("Unknown worker action")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "_worker":
        raise SystemExit("This module is an internal stage worker")
    _worker(Path(sys.argv[2]))
