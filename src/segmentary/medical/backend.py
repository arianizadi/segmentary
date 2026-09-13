"""Isolated, version-bound orchestration of the optional nnU-Net 2.8.1 backend.

The public functions return JSON-serializable records. ``dry_run=True`` validates
inputs and returns a proposed action without creating files or starting a child.
Only development cases enter nnU-Net's raw/planning directories. As in standard
nnU-Net, planning uses train + validation; this is not train-only fold planning.

Official interfaces were checked against the 2.8.1 wheel: ``get_trainer_from_args``,
``plan_and_preprocess_entry``, and ``nnUNetPredictor``. This module delegates the
network, preprocessing, augmentation, optimizer, losses, and training loop to
that release. It adds experiment guards and atomic checkpoint/RNG sidecars.
Resume recovers at the saved epoch; it does not reproduce discarded prefetched
batches or an interrupted epoch bit for bit.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NNUNET_VERSION = "2.8.1"
_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class NNUNetConfig:
    """Frozen recipe. Runtime overrides are explicitly non-baseline experiments."""

    workspace: str
    backend_python: str | None = None
    dataset_id: int = 707
    dataset_name: str = "Pancreas"
    resenc: str = "L"
    configuration: str = "3d_fullres"
    fold: int = 0
    gpu: str = "0"
    seed: int = 0
    workers: int = 2
    nnunet_version: str = NNUNET_VERSION
    deterministic: bool = False
    purpose: str = "baseline"
    num_epochs: int | None = None
    num_iterations_per_epoch: int | None = None
    num_val_iterations_per_epoch: int | None = None
    save_probabilities: bool = False
    use_mirroring: bool = False
    tile_step_size: float = 0.5

    def __post_init__(self):
        for name in ("dataset_id", "fold", "seed", "workers"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer, not a boolean or float")
        for name in ("deterministic", "save_probabilities", "use_mirroring"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        object.__setattr__(self, "workspace", str(Path(self.workspace).expanduser().resolve()))
        if self.backend_python is not None and not isinstance(self.backend_python, str):
            raise ValueError("backend_python must be an interpreter path string")
        object.__setattr__(
            self,
            "backend_python",
            str(Path(self.backend_python or sys.executable).expanduser().absolute()),
        )
        if isinstance(self.gpu, bool) or not re.fullmatch(r"[0-9]+", str(self.gpu)):
            raise ValueError("gpu must identify one numeric device")
        object.__setattr__(self, "gpu", str(int(self.gpu)))
        if not 1 <= self.dataset_id <= 999 or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*", self.dataset_name
        ):
            raise ValueError("Use dataset_id 1..999 and an alphanumeric dataset_name")
        if self.resenc not in {"M", "L", "XL"} or self.configuration not in {"3d_fullres", "2d"}:
            raise ValueError("Supported recipes are ResEnc M/L/XL, 3d_fullres or 2d")
        if self.fold != 0:
            raise ValueError(
                "This explicit train/val split is fold 0; use separate workspaces for other splits"
            )
        if not re.fullmatch(r"[0-9]+", self.gpu) or self.workers < 1 or not 0 <= self.seed < 2**32:
            raise ValueError("Specify one numeric GPU, positive workers, and a uint32 seed")
        if self.nnunet_version != NNUNET_VERSION:
            raise ValueError(f"This adapter is verified for nnunetv2=={NNUNET_VERSION} only")
        if self.purpose not in {"baseline", "smoke", "overfit"}:
            raise ValueError("purpose must be baseline, smoke, or overfit")
        overrides = [
            self.num_epochs,
            self.num_iterations_per_epoch,
            self.num_val_iterations_per_epoch,
        ]
        if any(
            x is not None and (not isinstance(x, int) or isinstance(x, bool) or x < 1)
            for x in overrides
        ):
            raise ValueError("Runtime overrides must be positive integers")
        if self.purpose == "baseline" and any(x is not None for x in overrides):
            raise ValueError("Runtime overrides require purpose=smoke or overfit")
        if (
            isinstance(self.tile_step_size, bool)
            or not isinstance(self.tile_step_size, (int, float))
            or not 0 < self.tile_step_size <= 1
        ):
            raise ValueError("tile_step_size must be in (0, 1]")

    @property
    def dataset(self) -> str:
        return f"Dataset{self.dataset_id:03d}_{self.dataset_name}"

    @property
    def plans(self) -> str:
        return f"nnUNetResEncUNet{self.resenc}Plans"

    @property
    def root(self) -> Path:
        return Path(self.workspace)

    @property
    def preprocessed(self) -> Path:
        return self.root / "nnUNet_preprocessed" / self.dataset

    @property
    def model_folder(self) -> Path:
        return (
            self.root
            / "nnUNet_results"
            / self.dataset
            / f"nnUNetTrainer__{self.plans}__{self.configuration}"
        )

    @property
    def fold_folder(self) -> Path:
        return self.model_folder / "fold_0"


def _sha(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _atomic_json(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("x") as f:
            json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _check_hash(path: str | Path, expected: str):
    if not expected or _sha(path) != expected:
        raise ValueError(f"Content hash changed or missing: {path}")


def _code_identity() -> dict:
    return {p.name: _sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))}


def _documents(manifest_path: str | Path, splits_path: str | Path) -> tuple[dict, dict]:
    from segmentary.medical.data import load_manifest, validate_splits

    # Loading manifest metadata must not open held-out image or label payloads.
    manifest = load_manifest(manifest_path, verify_files=False)
    splits = _json(Path(splits_path))
    validate_splits(manifest, splits)
    if not manifest.get("audit", {}).get("passed"):
        raise ValueError("An audited manifest with audit.passed=true is required")
    if manifest["ontology"] != {"background": 0, "pancreas": 1, "mass": 2}:
        raise ValueError("This backend requires the explicit background/pancreas/mass ontology")
    if not splits["train"] or not splits["val"]:
        raise ValueError("Nonempty train and validation groups are required")
    for case in manifest["cases"]:
        if not _CASE_ID.fullmatch(case["case_id"]):
            raise ValueError(f"Unsafe case identifier: {case['case_id']}")
    return manifest, splits


def prepare_dataset(
    manifest_path: str | Path,
    splits_path: str | Path,
    config: NNUNetConfig,
    *,
    dry_run: bool = False,
) -> dict:
    """Create a fresh isolated nnU-Net dataset; source files are read-only symlinks.

    Validation contributes to the dataset fingerprint/planner, matching ordinary
    nnU-Net development-set preprocessing. Test data is absent from this layout.
    No overwrite/automatic reuse is allowed, including after partial preparation.
    """
    manifest_path, splits_path = Path(manifest_path).resolve(), Path(splits_path).resolve()
    manifest, splits = _documents(manifest_path, splits_path)
    if config.root.exists() and any(config.root.iterdir()):
        raise FileExistsError(f"Use an empty workspace: {config.root}")
    lookup = {c["case_id"]: c for c in manifest["cases"]}
    development = [lookup[x] for x in splits["train"] + splits["val"]]
    for case in development:
        if case["annotation_status"] != "labeled" or not case.get("label"):
            raise ValueError(
                "Joint pancreas/mass training requires fully labeled development cases"
            )
        for key in ("image", "label"):
            if not str(case[key]).endswith(".nii.gz"):
                raise ValueError("The nnU-Net adapter currently stages .nii.gz files only")
            _check_hash(case[key], case[f"{key}_sha256"])
    binding = {
        "schema_version": 1,
        "config": dataclasses.asdict(config),
        "manifest_path": str(manifest_path),
        "splits_path": str(splits_path),
        "manifest_sha256": _sha(manifest_path),
        "splits_sha256": _sha(splits_path),
        "manifest_fingerprint": manifest["fingerprint"],
        "split_fingerprint": splits["fingerprint"],
        "ontology": manifest["ontology"],
        "code": _code_identity(),
        "planning_scope": "train_and_val_only",
        "development_cases": [c["case_id"] for c in development],
        "held_out_cases": list(splits["test"]),
    }
    result = {
        "action": "prepare",
        "dry_run": dry_run,
        "workspace": config.workspace,
        "train_cases": len(splits["train"]),
        "val_cases": len(splits["val"]),
        "test_cases_excluded": len(splits["test"]),
        "identity": _digest(binding),
    }
    if dry_run:
        return result
    config.root.mkdir(parents=True, exist_ok=True)
    raw = config.root / "nnUNet_raw" / config.dataset
    for directory in (
        raw / "imagesTr",
        raw / "labelsTr",
        config.preprocessed,
        config.root / "nnUNet_results",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    for case in development:
        (raw / "imagesTr" / f"{case['case_id']}_0000.nii.gz").symlink_to(
            Path(case["image"]).resolve()
        )
        (raw / "labelsTr" / f"{case['case_id']}.nii.gz").symlink_to(Path(case["label"]).resolve())
    _atomic_json(
        raw / "dataset.json",
        {
            "channel_names": {"0": "CT"},
            "labels": manifest["ontology"],
            "numTraining": len(development),
            "file_ending": ".nii.gz",
            "overwrite_image_reader_writer": "NibabelIO",
        },
    )
    _atomic_json(
        config.preprocessed / "splits_final.json",
        [{"train": splits["train"], "val": splits["val"]}],
    )
    _atomic_json(config.root / "binding.json", binding)
    _atomic_json(config.root / "resolved-config.json", dataclasses.asdict(config))
    _atomic_json(config.root / "preparation.json", result)
    return result


def _binding(config: NNUNetConfig, *, verify_development: bool = True) -> dict:
    binding = _json(config.root / "binding.json")
    if binding["config"] != dataclasses.asdict(config) or binding["code"] != _code_identity():
        raise ValueError(
            "Configuration or backend source changed; create a new experiment workspace"
        )
    _check_hash(binding["manifest_path"], binding["manifest_sha256"])
    _check_hash(binding["splits_path"], binding["splits_sha256"])
    if verify_development:
        manifest, splits = _documents(binding["manifest_path"], binding["splits_path"])
        expected = [{"train": splits["train"], "val": splits["val"]}]
        if json.loads((config.preprocessed / "splits_final.json").read_text()) != expected:
            raise ValueError("nnU-Net development split changed")
        raw = config.root / "nnUNet_raw" / config.dataset
        if {p.name for p in (raw / "imagesTr").iterdir()} != {
            f"{x}_0000.nii.gz" for x in binding["development_cases"]
        }:
            raise ValueError("Raw image membership changed (possible held-out contamination)")
        if {p.name for p in (raw / "labelsTr").iterdir()} != {
            f"{x}.nii.gz" for x in binding["development_cases"]
        }:
            raise ValueError("Raw label membership changed")
        for case in manifest["cases"]:
            if case["case_id"] in binding["development_cases"]:
                _check_hash(
                    raw / "imagesTr" / f"{case['case_id']}_0000.nii.gz", case["image_sha256"]
                )
                _check_hash(raw / "labelsTr" / f"{case['case_id']}.nii.gz", case["label_sha256"])
        expected_json = {
            "channel_names": {"0": "CT"},
            "labels": binding["ontology"],
            "numTraining": len(binding["development_cases"]),
            "file_ending": ".nii.gz",
            "overwrite_image_reader_writer": "NibabelIO",
        }
        if _json(raw / "dataset.json") != expected_json:
            raise ValueError("Raw dataset ontology or modality configuration changed")
    return binding


def _runtime(config: NNUNetConfig) -> dict:
    """Probe the worker interpreter, independently of the RGB harness environment.

    nnU-Net's dynamic-network-architectures dependency constrains packages
    differently from Segmentary's RGB stack. Only lightweight medical modules
    cross that interpreter boundary through PYTHONPATH.
    """
    code = (
        "import importlib.metadata as m,json,sys; "
        "packages=dict(sorted((d.metadata['Name'],d.version) for d in m.distributions() if 'Name' in d.metadata)); "
        "print(json.dumps({'python':sys.version,'executable':sys.executable,'packages':packages}))"
    )
    completed = subprocess.run(
        [str(config.backend_python), "-c", code],
        env=_environment(config),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Cannot inspect backend interpreter: {completed.stderr.strip()}")
    try:
        runtime = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Backend interpreter did not return runtime metadata") from exc
    installed = runtime["packages"].get("nnunetv2")
    if installed != NNUNET_VERSION:
        raise RuntimeError(
            f"Expected nnunetv2=={NNUNET_VERSION} in {config.backend_python}, found {installed}; use a separate nnU-Net environment"
        )
    return runtime


@contextlib.contextmanager
def _lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Resource is already in use: {path}") from exc
        try:
            yield handle.fileno()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _gpu_lock(config: NNUNetConfig) -> Path:
    root = Path(
        os.environ.get(
            "SEGMENTARY_MEDICAL_LOCK_DIR",
            str(Path(tempfile.gettempdir()) / f"segmentary-medical-{os.getuid()}"),
        )
    )
    return root / f"gpu-{config.gpu}.lock"


def _environment(config: NNUNetConfig, *, action: str | None = None) -> dict[str, str]:
    """Zero workers selects synchronous augmentation only in the training stage.

    nnU-Net 2.8.1 also uses nnUNet_n_proc_DA as the planner's Torch thread count,
    where zero is invalid. Planning, prediction and metadata probes use positive
    worker counts. The trainer explicitly supports zero augmentation workers.
    """
    env = dict(os.environ)
    inherited_devices = env.get("CUDA_VISIBLE_DEVICES")
    if inherited_devices is not None:
        tokens = [value.strip() for value in inherited_devices.split(",")]
        if not all(re.fullmatch(r"[0-9]+", value) for value in tokens):
            raise ValueError(
                "Inherited CUDA_VISIBLE_DEVICES is disabled or uses unsupported UUID/MIG identifiers"
            )
        if config.gpu not in {str(int(value)) for value in tokens}:
            raise ValueError("Requested GPU is outside inherited CUDA_VISIBLE_DEVICES")
    env.update(
        {
            name: str(config.root / name)
            for name in ("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results")
        }
    )
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": config.gpu,
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
            "PYTHONHASHSEED": str(config.seed),
            "nnUNet_n_proc_DA": "0"
            if action == "train" and config.deterministic
            else str(config.workers),
            "nnUNet_compile": "false",
            "OMP_NUM_THREADS": str(config.workers),
            "MKL_NUM_THREADS": str(config.workers),
            "PYTHONUNBUFFERED": "1",
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
            "HF_HUB_OFFLINE": "1",
            "WANDB_MODE": "disabled",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            "PYTHONNOUSERSITE": "1",
        }
    )
    return env


def _stop_child(process):
    if process is None or process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def _run(config: NNUNetConfig, action: str, payload: dict, *, gpu: bool = False) -> dict:
    """Synchronous child lifecycle. Terminal outcomes are persisted even on failure."""
    runtime = _runtime(config)
    identity = _digest({"binding": _binding(config, verify_development=False), "runtime": runtime})
    action_id = f"{action}-{time.time_ns()}"
    directory = config.root / "stages" / action_id
    with contextlib.ExitStack() as stack:
        lock_fds = [stack.enter_context(_lock(config.root / ".stage.lock"))]
        if gpu:
            lock_fds.append(stack.enter_context(_lock(_gpu_lock(config))))
        directory.mkdir(parents=True)
        request = {
            "config": dataclasses.asdict(config),
            "action": action,
            "payload": payload,
            "identity": identity,
        }
        _atomic_json(directory / "request.json", request)
        _atomic_json(directory / "runtime.json", runtime)
        argv = [
            str(config.backend_python),
            "-m",
            "segmentary.medical.backend",
            "_worker",
            str(directory / "request.json"),
        ]
        state: dict[str, Any] = {
            "action": action,
            "action_id": action_id,
            "status": "starting",
            "started_at": time.time(),
            "argv": argv,
            "identity": identity,
            "log": str(directory / "subprocess.log"),
        }
        state_path = config.root / "active-stage.json"
        _atomic_json(state_path, state)
        process = None
        previous_sigterm = None
        if threading.current_thread() is threading.main_thread():
            previous_sigterm = signal.getsignal(signal.SIGTERM)

            def terminate_parent(_signum, _frame):
                raise KeyboardInterrupt("Termination requested")

            signal.signal(signal.SIGTERM, terminate_parent)
        try:
            with (directory / "subprocess.log").open("wb") as log:
                process = subprocess.Popen(
                    argv,
                    env=_environment(config, action=action),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    pass_fds=tuple(lock_fds),
                )
                state.update(status="running", pid=process.pid)
                _atomic_json(state_path, state)
                returncode = process.wait()
            state.update(returncode=returncode, status="completed" if returncode == 0 else "failed")
            if returncode in (-signal.SIGTERM, -signal.SIGINT, 130, 143):
                state["status"] = "cancelled"
            if returncode:
                raise RuntimeError(
                    f"{action} {state['status']} (exit {returncode}); see {state['log']}"
                )
        except KeyboardInterrupt:
            _stop_child(process)
            state["status"] = "cancelled"
            raise
        except BaseException as exc:
            _stop_child(process)
            if state["status"] not in {"failed", "cancelled"}:
                state["status"] = "failed"
            state["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if previous_sigterm is not None:
                signal.signal(signal.SIGTERM, previous_sigterm)
            state["finished_at"] = time.time()
            state["wall_seconds"] = state["finished_at"] - state["started_at"]
            state["allocated_gpu_hours"] = state["wall_seconds"] / 3600 if gpu else 0
            _atomic_json(state_path, state)
            _atomic_json(directory / "outcome.json", state)
    return state


def cancel(config: NNUNetConfig) -> dict:
    """Terminate this workspace's live worker process group, with PID reuse checks."""
    state = _json(config.root / "active-stage.json")
    if state["status"] != "running":
        raise ValueError("There is no running stage to cancel")
    pid = state["pid"]
    proc = Path(f"/proc/{pid}/cmdline")
    if not proc.exists():
        raise RuntimeError("Safe cancellation requires a live Linux /proc process record")
    cmdline = proc.read_bytes().split(b"\0")
    if state["argv"][-1].encode() not in cmdline or os.getpgid(pid) != pid:
        raise RuntimeError("Process identity changed; refusing to signal a reused PID")
    os.killpg(pid, signal.SIGTERM)
    return {"status": "cancellation_requested", "pid": pid, "action": state["action"]}


def _plan_binding(config: NNUNetConfig) -> dict:
    record = _json(config.root / "plan-binding.json")
    if record["binding_digest"] != _digest(_binding(config)):
        raise ValueError("Prepared data/configuration identity changed")
    if record["runtime"] != _runtime(config):
        raise ValueError("Environment changed since planning; use a new experiment")
    for relative, expected in record["files"].items():
        _check_hash(config.preprocessed / relative, expected)
    actual = {
        str(p.relative_to(config.preprocessed))
        for p in config.preprocessed.rglob("*")
        if p.is_file()
    }
    if actual != set(record["files"]):
        raise ValueError("Preprocessing cache membership changed")
    return record


def plan_and_preprocess(config: NNUNetConfig, *, dry_run: bool = False) -> dict:
    binding = _binding(config)
    if (config.root / "plan-binding.json").exists():
        raise FileExistsError("Planning is frozen; use a new workspace for a new plan")
    result = {
        "action": "plan",
        "dry_run": dry_run,
        "planner": f"nnUNetPlannerResEnc{config.resenc}",
        "plans": config.plans,
        "configuration": config.configuration,
        "planning_scope": "train_and_val_only",
        "test_cases_excluded": len(binding["held_out_cases"]),
    }
    if dry_run:
        return result
    # Refuse stale partial caches; never let nnU-Net reuse an unbound fingerprint.
    if set(p.name for p in config.preprocessed.iterdir()) != {"splits_final.json"}:
        raise FileExistsError("Unbound preprocessing outputs exist; create a fresh workspace")
    state = _run(config, "plan", {})
    plan = _json(config.preprocessed / f"{config.plans}.json")
    if config.configuration not in plan["configurations"]:
        raise ValueError("Requested configuration was not produced by the planner")
    files = {
        str(p.relative_to(config.preprocessed)): _sha(p)
        for p in sorted(config.preprocessed.rglob("*"))
        if p.is_file()
    }
    _atomic_json(
        config.root / "plan-binding.json",
        {"binding_digest": _digest(binding), "runtime": _runtime(config), "files": files},
    )
    return {**result, "stage": state, "plan_sha256": files[f"{config.plans}.json"]}


def _checkpoint(config: NNUNetConfig, name: str) -> dict:
    if name not in {"checkpoint_latest.pth", "checkpoint_best.pth", "checkpoint_final.pth"}:
        raise ValueError("Select a named checkpoint created by this experiment")
    index = _json(config.root / "checkpoint-index.json")
    if name not in index:
        raise ValueError(
            f"No bound checkpoint exists: {name}; resume never falls back to a fresh run"
        )
    item = index[name]
    identity = _digest(
        {"binding": _binding(config, verify_development=False), "runtime": _runtime(config)}
    )
    if item["identity"] != identity:
        raise ValueError("Checkpoint belongs to different data, code, or environment")
    _check_hash(config.fold_folder / name, item["sha256"])
    _check_hash(config.fold_folder / f"{name}.rng.pt", item["rng_sha256"])
    return item


def train(
    config: NNUNetConfig,
    *,
    resume: bool = False,
    resume_checkpoint: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Train one direct GPU job, or explicitly recover an identity-bound checkpoint."""
    _plan_binding(config)
    checkpoint = None
    if resume:
        if resume_checkpoint is None:
            index_path = config.root / "checkpoint-index.json"
            if not index_path.exists():
                raise ValueError(
                    "No checkpoint index exists; resume cannot start a fresh training run"
                )
            index = _json(index_path)
            candidates = [
                n
                for n in ("checkpoint_final.pth", "checkpoint_latest.pth", "checkpoint_best.pth")
                if n in index and (config.fold_folder / n).exists()
            ]
            if not candidates:
                raise ValueError("No recovery checkpoint exists")
            resume_checkpoint = max(
                candidates, key=lambda n: (index[n]["epoch"], index[n]["saved_at"])
            )
        checkpoint = _checkpoint(config, resume_checkpoint)
    elif resume_checkpoint is not None:
        raise ValueError("resume_checkpoint requires resume=True")
    elif config.fold_folder.exists():
        raise FileExistsError("Training output exists; explicitly resume or use a new workspace")
    result = {
        "action": "train",
        "dry_run": dry_run,
        "gpu": config.gpu,
        "resume": resume,
        "resume_checkpoint": resume_checkpoint,
        "checkpoint_sha256": checkpoint["sha256"] if checkpoint else None,
        "purpose": config.purpose,
        "resume_granularity": "saved_epoch_not_bitwise_mid_epoch",
        "deterministic": config.deterministic,
        "augmentation_workers": 0 if config.deterministic else config.workers,
    }
    if dry_run:
        return result
    state = _run(config, "train", {"resume_checkpoint": resume_checkpoint}, gpu=True)
    _checkpoint(config, "checkpoint_final.pth")
    return {**result, "stage": state}


def validate_prediction_geometry(image: str | Path, prediction: str | Path) -> dict:
    """Check a native-space output using image geometry only, never annotations."""
    import nibabel as nib
    import numpy as np

    src: Any = nib.load(str(image))
    pred: Any = nib.load(str(prediction))
    if (
        len(src.shape) != 3
        or pred.shape != src.shape
        or not np.allclose(pred.affine, src.affine, atol=1e-4, rtol=0)
    ):
        raise ValueError(f"Prediction does not match native CT geometry: {prediction}")
    values = np.asanyarray(pred.dataobj)
    if not np.isfinite(values).all() or not np.isin(values, (0, 1, 2)).all():
        raise ValueError(f"Prediction contains invalid class values: {prediction}")
    return {"shape": list(pred.shape), "affine": pred.affine.tolist(), "sha256": _sha(prediction)}


def _finalize_native_prediction(image: str | Path, prediction: str | Path) -> dict:
    """Restore verified spatial header metadata dropped by nnU-Net's NibabelIO.

    First verify the predicted voxel grid and affine. Never repair a geometric
    mismatch by replacing its affine. Only a validated output receives source
    units and coded spatial forms, and the change is recorded with both hashes.
    """
    import nibabel as nib
    import numpy as np

    before = validate_prediction_geometry(image, prediction)
    source: Any = nib.load(str(image))
    predicted: Any = nib.load(str(prediction))
    units = source.header.get_xyzt_units()
    if units[0] != "mm":
        raise ValueError("Native CT must explicitly declare millimeter spatial units")
    labels = np.asanyarray(predicted.dataobj)
    header = predicted.header.copy()
    header.set_xyzt_units(*units)
    restored = nib.Nifti1Image(labels, source.affine, header)
    for form in ("qform", "sform"):
        matrix, code = getattr(source, f"get_{form}")(coded=True)
        getattr(restored, f"set_{form}")(matrix, code=int(code))
    destination = Path(prediction)
    temporary = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}.nii.gz")
    try:
        nib.save(restored, temporary)
        validated = validate_prediction_geometry(image, temporary)
        checked_volume: Any = nib.load(temporary)
        if not np.array_equal(np.asanyarray(checked_volume.dataobj), labels):
            raise ValueError("Spatial-header restoration unexpectedly changed predicted labels")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        **validated,
        "backend_output_sha256": before["sha256"],
        "header_action": "copied_source_spatial_units_and_coded_forms_after_affine_validation",
    }


def predict(
    config: NNUNetConfig,
    *,
    partition: str = "val",
    final_test: bool = False,
    checkpoint: str = "checkpoint_best.pth",
    dry_run: bool = False,
) -> dict:
    """Image-only inference. Test requires an explicit, separately invoked flag.

    Output completion is subject to native image geometry validation. Test use is
    recorded durably. Repeated testing does not authorize changing model choices.
    """
    if partition not in {"train", "val", "test", "unlabeled"} or final_test != (
        partition == "test"
    ):
        raise ValueError(
            "Use train/val/unlabeled, or explicitly partition=test and final_test=True"
        )
    binding = _binding(config, verify_development=False)
    checkpoint_item = _checkpoint(config, checkpoint)
    manifest = _json(Path(binding["manifest_path"]))
    splits = _json(Path(binding["splits_path"]))
    lookup = {c["case_id"]: c for c in manifest["cases"]}
    identifiers = (
        splits[partition]
        if partition != "unlabeled"
        else [c["case_id"] for c in manifest["cases"] if c["annotation_status"] == "unlabeled"]
    )
    cases = [
        {"case_id": x, "image": lookup[x]["image"], "image_sha256": lookup[x]["image_sha256"]}
        for x in identifiers
    ]
    if not cases:
        raise ValueError(f"No {partition} images were declared")
    for case in cases:
        _check_hash(case["image"], case["image_sha256"])
    # Predictor loads plans.json and dataset.json from the trained model folder.
    plan_record = _json(config.root / "plan-binding.json")
    for model_name, original_name in (
        ("plans.json", f"{config.plans}.json"),
        ("dataset.json", "dataset.json"),
    ):
        original = config.preprocessed / original_name
        _check_hash(original, plan_record["files"][original_name])
        if _json(config.model_folder / model_name) != _json(original):
            raise ValueError(f"Trained model metadata changed: {model_name}")
    output = config.root / "predictions" / f"{partition}-{time.time_ns()}"
    result = {
        "action": "predict",
        "partition": partition,
        "final_test": final_test,
        "dry_run": dry_run,
        "output": str(output),
        "cases": len(cases),
        "checkpoint_sha256": checkpoint_item["sha256"],
    }
    if dry_run:
        return result
    payload = {
        "cases": cases,
        "output": str(output),
        "checkpoint": checkpoint,
        "partition": partition,
    }
    state = _run(config, "predict", payload, gpu=True)
    expected = {f"{c['case_id']}.nii.gz" for c in cases}
    if {p.name for p in output.glob("*.nii.gz")} != expected:
        raise ValueError("Prediction coverage is incomplete or includes unexpected cases")
    checks = {
        c["case_id"]: validate_prediction_geometry(c["image"], output / f"{c['case_id']}.nii.gz")
        for c in cases
    }
    _atomic_json(output / "geometry-validation.json", checks)
    _atomic_json(
        output / "prediction-record.json", {**result, "stage": state, "status": "validated"}
    )
    return {**result, "stage": state, "status": "validated"}


def _seed_runtime(config: NNUNetConfig):
    import random

    import numpy as np
    import torch

    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.cuda.manual_seed_all(config.seed)
    torch.backends.cudnn.benchmark = not config.deterministic
    torch.backends.cudnn.deterministic = config.deterministic
    torch.use_deterministic_algorithms(config.deterministic)


def _train_worker(config: NNUNetConfig, payload: dict, identity: str):
    import random

    import numpy as np
    import torch
    from nnunetv2.run.run_training import get_trainer_from_args

    # Match the official CUDA training CLI's Torch thread limits. The separate
    # nnUNet_n_proc_DA=0 switch controls synchronous augmentation, not Torch.
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    _seed_runtime(config)
    trainer = get_trainer_from_args(
        config.dataset,
        config.configuration,
        config.fold,
        trainer_name="nnUNetTrainer",
        plans_identifier=config.plans,
        continue_training=payload["resume_checkpoint"] is not None,
        device=torch.device("cuda", 0),
    )
    for name in ("num_epochs", "num_iterations_per_epoch", "num_val_iterations_per_epoch"):
        value = getattr(config, name)
        if value is not None:
            setattr(trainer, name, value)
    original_save = trainer.save_checkpoint

    def save_checkpoint(filename: str):
        destination = Path(filename)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        rng_path = destination.with_name(destination.name + ".rng.pt")
        rng_tmp = rng_path.with_name(f".{rng_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            original_save(str(temporary))
            torch.save(
                {
                    "python": random.getstate(),
                    "numpy": np.random.get_state(),
                    "torch_cpu": torch.get_rng_state(),
                    "torch_cuda": torch.cuda.get_rng_state_all(),
                    "scheduler": trainer.lr_scheduler.state_dict(),
                },
                rng_tmp,
            )
            os.replace(temporary, destination)
            os.replace(rng_tmp, rng_path)
            index_path = config.root / "checkpoint-index.json"
            index = _json(index_path) if index_path.exists() else {}
            index[destination.name] = {
                "sha256": _sha(destination),
                "rng_sha256": _sha(rng_path),
                "identity": identity,
                "epoch": trainer.current_epoch + 1,
                "saved_at": time.time(),
            }
            _atomic_json(index_path, index)
        finally:
            temporary.unlink(missing_ok=True)
            rng_tmp.unlink(missing_ok=True)

    trainer.save_checkpoint = save_checkpoint
    resume = payload["resume_checkpoint"]
    if resume is not None:
        _checkpoint(config, resume)
        trainer.load_checkpoint(str(config.fold_folder / resume))
        rng = torch.load(
            config.fold_folder / f"{resume}.rng.pt", map_location="cpu", weights_only=False
        )
        random.setstate(rng["python"])
        np.random.set_state(rng["numpy"])
        torch.set_rng_state(rng["torch_cpu"])
        torch.cuda.set_rng_state_all(rng["torch_cuda"])
        trainer.lr_scheduler.load_state_dict(rng["scheduler"])
    original_step = trainer.train_step

    def train_step(batch):
        result = original_step(batch)
        if not np.isfinite(result["loss"]).all():
            raise FloatingPointError(
                "Non-finite training loss; stopping without changing the recipe"
            )
        return result

    trainer.train_step = train_step
    _atomic_json(
        config.root / "trainer-settings.json",
        {
            "purpose": config.purpose,
            "trainer": "nnUNetTrainer",
            "num_epochs": trainer.num_epochs,
            "num_iterations_per_epoch": trainer.num_iterations_per_epoch,
            "num_val_iterations_per_epoch": trainer.num_val_iterations_per_epoch,
            "initial_lr": trainer.initial_lr,
            "weight_decay": trainer.weight_decay,
            "oversample_foreground_percent": trainer.oversample_foreground_percent,
            "checkpoint_selection": "official_ema_foreground_dice",
            "seed": config.seed,
            "deterministic": config.deterministic,
            "reproducibility": "strict_deterministic_algorithms"
            if config.deterministic
            else "seeded_initialization_with_upstream_nondeterministic_cuda_and_augmentation",
            "resume_granularity": "saved_epoch_no_bitwise_prefetch_or_mid_epoch_guarantee",
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu_name": torch.cuda.get_device_name(0),
        },
    )
    torch.cuda.reset_peak_memory_stats(0)
    telemetry: dict[str, Any] = {
        "status": "running",
        "training_seconds": None,
        "validation_seconds": None,
        "peak_allocated_gpu_bytes": None,
        "peak_reserved_gpu_bytes": None,
    }
    training_started = time.monotonic()
    try:
        trainer.run_training()
        telemetry["status"] = "training_complete"
    except BaseException as exc:
        telemetry["status"] = "training_failed"
        if (
            config.deterministic
            and isinstance(exc, RuntimeError)
            and "deterministic" in str(exc).lower()
        ):
            raise RuntimeError(
                "Strict deterministic execution failed because a required backend kernel has no "
                "deterministic implementation. This experiment was stopped without changing its "
                "recipe. To use standard nnU-Net GPU execution, explicitly set deterministic=false "
                "in a new experiment workspace. Original error: " + str(exc)
            ) from exc
        raise
    finally:
        telemetry["training_seconds"] = time.monotonic() - training_started
        telemetry["peak_allocated_gpu_bytes"] = torch.cuda.max_memory_allocated(0)
        telemetry["peak_reserved_gpu_bytes"] = torch.cuda.max_memory_reserved(0)
        _atomic_json(config.root / "training-telemetry.json", telemetry)
    # Keep full-volume export separate from patch-level checkpoint selection.
    # The official perform_actual_validation hardcodes mirror TTA and its own
    # process count; invoke the official predictor with our frozen settings.
    _checkpoint(config, "checkpoint_best.pth")
    _checkpoint(config, "checkpoint_final.pth")
    binding = _binding(config, verify_development=False)
    manifest = _json(Path(binding["manifest_path"]))
    splits = _json(Path(binding["splits_path"]))
    lookup = {c["case_id"]: c for c in manifest["cases"]}
    # Free training state before constructing an independent inference network.
    original_save = original_step = trainer = None
    import gc

    gc.collect()
    torch.cuda.empty_cache()
    validation_output = config.fold_folder / f"validation-{time.time_ns()}"
    validation_started = time.monotonic()
    try:
        _predict_worker(
            config,
            {
                "cases": [{"case_id": x, "image": lookup[x]["image"]} for x in splits["val"]],
                "checkpoint": "checkpoint_best.pth",
                "output": str(validation_output),
            },
        )
        telemetry["status"] = "completed"
    except BaseException:
        telemetry["status"] = "validation_failed"
        raise
    finally:
        telemetry["validation_seconds"] = time.monotonic() - validation_started
        _atomic_json(config.root / "training-telemetry.json", telemetry)
    _atomic_json(
        config.root / "training-validation.json",
        {
            "output": str(validation_output),
            "cases": splits["val"],
            "selection": "official_ema_foreground_dice",
            "use_mirroring": config.use_mirroring,
            "metrics": "Run the separate medical evaluator; patch Dice is not full-volume Dice",
        },
    )


def _predict_worker(config: NNUNetConfig, payload: dict):
    import torch
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

    # This also runs after training inside the same worker process.
    os.environ["nnUNet_n_proc_DA"] = str(config.workers)  # noqa: SIM112 - upstream variable name
    _seed_runtime(config)
    output = Path(payload["output"])
    output.mkdir(parents=True, exist_ok=False)
    predictor = nnUNetPredictor(
        tile_step_size=config.tile_step_size,
        use_gaussian=True,
        use_mirroring=config.use_mirroring,
        device=torch.device("cuda", 0),
    )
    # Predictor enables benchmarking in its constructor; restore the frozen setting.
    torch.backends.cudnn.benchmark = not config.deterministic
    predictor.initialize_from_trained_model_folder(
        str(config.model_folder), use_folds=(0,), checkpoint_name=payload["checkpoint"]
    )
    predictor.predict_from_files(
        [[c["image"]] for c in payload["cases"]],
        [str(output / c["case_id"]) for c in payload["cases"]],
        save_probabilities=config.save_probabilities,
        overwrite=False,
        num_processes_preprocessing=config.workers,
        num_processes_segmentation_export=config.workers,
    )
    expected = {f"{c['case_id']}.nii.gz" for c in payload["cases"]}
    if {p.name for p in output.glob("*.nii.gz")} != expected:
        raise ValueError("Prediction coverage is incomplete or contains unexpected cases")
    native_checks = {
        case["case_id"]: _finalize_native_prediction(
            case["image"], output / f"{case['case_id']}.nii.gz"
        )
        for case in payload["cases"]
    }
    _atomic_json(output / "native-spatial-metadata.json", native_checks)


def _worker(request_path: str):
    request = _json(Path(request_path))
    config = NNUNetConfig(**request["config"])
    if (
        _digest(
            {"binding": _binding(config, verify_development=False), "runtime": _runtime(config)}
        )
        != request["identity"]
    ):
        raise ValueError("Worker code/configuration/environment changed after launch")
    action, payload = request["action"], request["payload"]
    if action == "plan":
        from nnunetv2.experiment_planning.plan_and_preprocess_entrypoints import (
            plan_and_preprocess_entry,
        )

        sys.argv = [
            "nnUNetv2_plan_and_preprocess",
            "-d",
            str(config.dataset_id),
            "-pl",
            f"nnUNetPlannerResEnc{config.resenc}",
            "-c",
            config.configuration,
            "-npfp",
            str(config.workers),
            "-np",
            str(config.workers),
            "--verify_dataset_integrity",
        ]
        plan_and_preprocess_entry()
    elif action == "train":
        _train_worker(config, payload, request["identity"])
    elif action == "predict":
        _predict_worker(config, payload)
    else:
        raise ValueError(f"Unknown worker action: {action}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "_worker":
        raise SystemExit("Use segmentary-medical; this module is an internal subprocess worker")
    _worker(sys.argv[2])
