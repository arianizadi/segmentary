"""Explicit, audited scratch-run continuation in a fresh experiment workspace.

This is a migration, not an exception to the normal source/configuration guards.
Original checkpoint bytes and parent provenance are retained; new checkpoint
generations change only their binding identity and the corresponding origin
identity. Optimizer, scheduler, scaler, model and every recorded RNG value are
verified unchanged. Preprocessing must run normally in the new workspace before
training resumes. No old cache is silently relabeled as a new implementation.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import importlib.metadata
import math
import os
import shutil
import struct
import sys
import tempfile
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from .backend import _atomic_json, _check_hash, _digest, _documents, _json, _lock, _sha
from .torch_config import TorchConfig

_ALIASES = {"checkpoint_best.pth", "checkpoint_latest.pth", "checkpoint_final.pth"}
# Membership alone does not authorize an edit. The reviewed policy must identify
# the exact old/new complete source trees and every individual changed file.
_REVIEWABLE_FILES = {
    "torch_backend.py",
    "torch_data.py",
    "torch_geometry.py",
    "geometry.py",
    "cli.py",
    "torch_inference_cache.py",
    "continuation.py",
    "pants.py",
    "data.py",
}
_REQUIRED_STATE = {
    "identity",
    "origin",
    "model",
    "optimizer",
    "scheduler",
    "scaler",
    "python_rng",
    "numpy_rng",
    "sampling_rng",
    "torch_rng",
    "cuda_rng",
    "epoch",
    "step",
    "best",
}


def code_hashes(root: str | Path) -> dict[str, str]:
    """Hash the same complete medical Python tree as the bound Torch backend."""
    root = Path(root).resolve()
    if not (root / "torch_backend.py").is_file():
        raise ValueError("source_code_root must be the medical Python source directory")
    result = {}
    for path in sorted(root.rglob("*.py")):
        if path.is_symlink():
            raise ValueError("Source snapshots must not contain symbolic Python links")
        result[str(path.relative_to(root))] = _sha(path)
    return result


def _function_ast(root: Path, name: str) -> str:
    tree = ast.parse((root / "torch_data.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise ValueError(f"Protected training function missing: {name}")


def _verify_policy(policy: dict, old: dict, source_root: Path, target_root: Path) -> dict:
    if policy.get("schema_version") != 1 or policy.get("purpose") != "performance-only":
        raise ValueError("An explicit performance-only continuation policy is required")
    source, target = code_hashes(source_root), code_hashes(target_root)
    if source != old["code"] or policy.get("source_code") != source:
        raise ValueError("Original source snapshot differs from the recorded binding/policy")
    if policy.get("target_code") != target:
        raise ValueError("Target source differs from the reviewed continuation policy")
    changed = {
        name for name in source.keys() | target.keys() if source.get(name) != target.get(name)
    }
    allowed = policy.get("allowed_changed_files")
    if not isinstance(allowed, list) or set(allowed) != changed or len(allowed) != len(changed):
        raise ValueError("Policy must enumerate exactly every changed source file")
    if not changed <= _REVIEWABLE_FILES:
        raise ValueError(
            f"Protected model/training source changed: {sorted(changed - _REVIEWABLE_FILES)}"
        )
    for name in ("dice_ce", "training_loss", "sample_patch", "context_image"):
        if _function_ast(source_root, name) != _function_ast(target_root, name):
            raise ValueError(f"Training objective or sampling changed: {name}")
    if not isinstance(policy.get("review"), str) or not policy["review"].strip():
        raise ValueError("Policy must describe the reviewed performance-only changes")
    evidence = policy.get("verification_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Policy requires hashed numerical/provenance verification evidence")
    for record in evidence:
        if not isinstance(record, dict) or not record.get("description"):
            raise ValueError("Verification evidence requires a description")
        _check_hash(record["path"], record["sha256"])
    return {"source": source, "target": target, "changed": sorted(changed)}


def state_digest(value: Any) -> str:
    """Canonical value digest for full dense Torch/NumPy checkpoint state.

    Unlike a pickle-byte hash, this is insensitive to storage identities while
    distinguishing tensor dtype/shape/value, tuple/list and scalar types. It is
    used only after the trusted parent file has passed its recorded SHA-256.
    """
    import numpy as np
    import torch

    digest = hashlib.sha256()

    def chunk(tag: bytes, data: bytes) -> None:
        digest.update(tag + struct.pack(">Q", len(data)) + data)

    def visit(item: Any) -> None:
        if isinstance(item, torch.Tensor):
            if item.layout != torch.strided or item.is_quantized:
                raise ValueError("Continuation supports dense nonquantized checkpoint tensors")
            chunk(b"tensor", str(item.dtype).encode())
            visit(tuple(item.shape))
            chunk(
                b"values",
                item.detach().cpu().contiguous().reshape(-1).view(torch.uint8).numpy().tobytes(),
            )
        elif isinstance(item, np.ndarray):
            if item.dtype.hasobject:
                raise ValueError("Object arrays are not accepted in checkpoint state")
            chunk(b"array", item.dtype.str.encode())
            visit(item.shape)
            chunk(b"values", item.tobytes(order="C"))
        elif isinstance(item, np.generic):
            chunk(b"numpy_scalar", item.dtype.str.encode() + item.tobytes())
        elif isinstance(item, Mapping):
            chunk(b"mapping", str(len(item)).encode())
            for key in sorted(item, key=state_digest):
                visit(key)
                visit(item[key])
        elif isinstance(item, (tuple, list)):
            chunk(b"tuple" if isinstance(item, tuple) else b"list", str(len(item)).encode())
            for child in item:
                visit(child)
        elif item is None:
            chunk(b"none", b"")
        elif type(item) is bool:
            chunk(b"bool", bytes([item]))
        elif type(item) is int:
            chunk(b"int", str(item).encode())
        elif type(item) is float:
            chunk(b"float", struct.pack(">d", item))
        elif isinstance(item, str):
            chunk(b"str", item.encode())
        elif isinstance(item, bytes):
            chunk(b"bytes", item)
        else:
            raise ValueError(f"Unsupported checkpoint state type: {type(item).__name__}")

    visit(value)
    return digest.hexdigest()


@contextlib.contextmanager
def _quiescent_source(root: Path) -> Iterator[None]:
    import fcntl

    path = root / ".stage.lock"
    if not path.is_file():
        raise ValueError("Source has no stage lock; cannot establish a safe checkpoint boundary")
    # Existing file, read-only: never creates or modifies the source workspace.
    with path.open("rb") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Source stage is active; stop cleanly before continuation") from exc
        try:
            active = root / "active-stage.json"
            if active.exists() and _json(active).get("status") in {"running", "starting"}:
                raise RuntimeError("Source records an unfinished active stage; reconcile it first")
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _source_records(source: Path, config: TorchConfig) -> tuple[dict, dict, dict, dict]:
    from .torch_backend import _config_record, _runtime

    binding = _json(source / "binding.json")
    old_config = dict(binding["config"])
    if old_config.get("workspace") != str(source):
        raise ValueError("Source workspace does not match its recorded binding")
    if _json(source / "resolved-config.json") != old_config:
        raise ValueError("Original resolved configuration differs from its binding")
    target_config = _config_record(config)
    old_config["workspace"] = config.workspace
    if old_config != target_config:
        raise ValueError("Only workspace may differ; recipe, devices and interpreter must match")
    if binding.get("initialization") != "scratch" or config.initialization != "scratch":
        raise ValueError("Continuation requires a scratch-origin experiment")
    if binding.get("runtime") != _runtime(config):
        raise ValueError("Continuation cannot change the Python/package runtime")
    expected_runtime = dict(binding["runtime"])
    executing_runtime = _executing_runtime()
    for runtime in (expected_runtime, executing_runtime):
        runtime["executable"] = str(Path(runtime["executable"]).resolve())
    if executing_runtime != expected_runtime:
        raise ValueError(
            "Continuation must execute in the recorded Python/package runtime; "
            "invoke this command with the configured backend_python"
        )
    for name in ("manifest", "splits"):
        _check_hash(binding[f"{name}_path"], binding[f"{name}_sha256"])
    manifest, splits = _documents(binding["manifest_path"], binding["splits_path"])
    if (
        manifest["fingerprint"] != binding["manifest_fingerprint"]
        or splits["fingerprint"] != binding["split_fingerprint"]
    ):
        raise ValueError("Dataset or split fingerprint changed")
    for case in manifest["cases"]:
        if case["case_id"] in set(splits["train"] + splits["val"]):
            for name in ("image", "label"):
                _check_hash(case[name], case[f"{name}_sha256"])
    identity = _digest(binding)
    origin = _json(source / "scratch-origin.json")
    if (
        origin.get("identity") != identity
        or origin.get("initialization") != "scratch"
        or origin.get("external_weight_loads") != 0
    ):
        raise ValueError("Parent scratch origin is invalid")
    if not origin.get("initial_state_sha256") or not isinstance(origin.get("parameters"), int):
        raise ValueError("Parent scratch origin is incomplete")
    index = _json(source / "checkpoint-index.json")
    if index.get("identity") != identity or index.get("initialization") != "scratch":
        raise ValueError("Parent checkpoint index provenance differs")
    if not index.get("files") or set(index["files"]) - _ALIASES:
        raise ValueError("Parent checkpoint aliases are invalid")
    for item in index["files"].values():
        relative = item.get("path", "")
        if (
            not relative.startswith("generation-")
            or Path(relative).name != relative
            or not relative.endswith(".pth")
        ):
            raise ValueError("Checkpoint is not an immutable in-workspace generation")
        path = source / "checkpoints" / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("Checkpoint generation must be an ordinary file")
    result = (
        _json(source / "training-result.json") if (source / "training-result.json").exists() else {}
    )
    if result and (result.get("identity") != identity or result.get("initialization") != "scratch"):
        raise ValueError("Parent training result provenance differs")
    return binding, origin, index, result


def _executing_runtime() -> dict:
    """Inspect this process, which actually decodes and rewrites checkpoints."""
    return {
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


def _verify_state(state: dict, binding: dict, origin: dict) -> None:
    if not isinstance(state, dict) or not state.keys() >= _REQUIRED_STATE:
        raise ValueError(
            "Checkpoint is missing complete model/optimizer/scheduler/scaler/RNG state"
        )
    if state["identity"] != _digest(binding) or state["origin"] != origin:
        raise ValueError("Parent checkpoint state identity differs")
    epoch, step = state["epoch"], state["step"]
    config = binding["config"]
    if (
        type(epoch) is not int
        or type(step) is not int
        or not 0 <= epoch <= config["epochs"]
        or step != epoch * config["steps_per_epoch"]
    ):
        raise ValueError("Checkpoint is not a consistent saved epoch boundary")
    if (
        not isinstance(state["best"], (float, int))
        or not math.isfinite(state["best"])
        or not -1 <= state["best"] <= 1
    ):
        raise ValueError("Checkpoint best validation score is invalid")


def _verify_aliases(index: dict, generations: dict, completed: dict, config: TorchConfig) -> None:
    """Require the alias relationships published atomically by the trainer."""
    aliases = index["files"]
    if "checkpoint_latest.pth" not in aliases:
        raise ValueError("Parent checkpoint index is missing its latest generation")
    latest_record = aliases["checkpoint_latest.pth"]
    latest = generations[latest_record["path"]]
    if any(item["epoch"] > latest["epoch"] for item in generations.values()):
        raise ValueError("An indexed checkpoint is newer than the latest generation")
    best_record = aliases.get("checkpoint_best.pth")
    if best_record is None:
        if latest["epoch"] != 0 or latest["best"] != -1:
            raise ValueError("A validated latest checkpoint requires its selected best alias")
    elif latest["best"] < 0 or generations[best_record["path"]]["best"] != latest["best"]:
        raise ValueError("Best checkpoint score disagrees with the latest selected best score")
    if any(item["best"] > latest["best"] for item in generations.values()):
        raise ValueError("An indexed checkpoint has a higher best score than latest")
    final_record = aliases.get("checkpoint_final.pth")
    if final_record is not None and (
        final_record != latest_record or latest["epoch"] != config.epochs
    ):
        raise ValueError("Final and latest aliases must select the same completed generation")
    if completed.get("completed") and (
        final_record is None or completed.get("best_mass_dice") != latest["best"]
    ):
        raise ValueError("Parent completion record disagrees with its selected best score/final")


def _verify_captured_artifacts(source: Path, hashes: dict[str, str | None]) -> None:
    for name, expected in hashes.items():
        if expected is None:
            if (source / name).exists():
                raise ValueError("Source metadata appeared during continuation capture")
        else:
            _check_hash(source / name, expected)


def create_continuation(
    source_workspace: str | Path,
    config: TorchConfig,
    *,
    source_code_root: str | Path,
    policy: dict | str | Path,
    action: str = "predict",
    dry_run: bool = False,
) -> dict:
    """Publish a new bound run after exact-source, data and state verification.

    ``action='predict'`` requires completed parent training and preserves its
    selected best checkpoint without further optimizer updates. ``'resume'``
    requires an unfinished latest epoch and preserves all indexed aliases.
    Both modes retain every old checkpoint generation byte for audit. A dry run
    performs the same checks, including trusted checkpoint decoding, but writes
    nothing. Run this under the recorded backend interpreter. Checkpoints are
    decoded on CPU and no model is instantiated or CUDA workload launched.
    """
    import torch

    from .torch_backend import _config_record

    source, target = Path(source_workspace).resolve(), config.root
    if action not in {"predict", "resume"}:
        raise ValueError("Continuation action must be predict or resume")
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("Continuation requires a separate, non-nested workspace")
    if target.exists():
        raise FileExistsError("Continuation target must not exist")
    policy = _json(Path(policy)) if isinstance(policy, (str, Path)) else policy
    if not isinstance(policy, dict):
        raise ValueError("Continuation policy must be a JSON object")
    source_root, target_root = Path(source_code_root).resolve(), Path(__file__).parent.resolve()
    with _quiescent_source(source):
        artifact_names = (
            "binding.json",
            "resolved-config.json",
            "scratch-origin.json",
            "checkpoint-index.json",
            "training-result.json",
        )
        captured_artifacts = {
            name: (source / name).read_bytes() if (source / name).exists() else None
            for name in artifact_names
        }
        artifact_hashes = {
            name: hashlib.sha256(data).hexdigest() if data is not None else None
            for name, data in captured_artifacts.items()
        }
        old, origin, index, completed = _source_records(source, config)
        reviewed = _verify_policy(policy, old, source_root, target_root)
        if action == "predict" and not completed.get("completed"):
            raise ValueError("Prediction continuation requires a completed parent training result")
        if action == "resume" and completed.get("completed"):
            raise ValueError("Training is already complete; use prediction continuation")
        required_alias = "checkpoint_best.pth" if action == "predict" else "checkpoint_latest.pth"
        if required_alias not in index["files"]:
            raise ValueError(f"Required parent checkpoint is absent: {required_alias}")
        generations = {}
        for alias, record in index["files"].items():
            name = record["path"]
            if name not in generations:
                path = source / "checkpoints" / name
                _check_hash(path, record["sha256"])
                state = torch.load(path, map_location="cpu", weights_only=False)
                _verify_state(state, old, origin)
                preserved = {k: v for k, v in state.items() if k not in {"identity", "origin"}}
                generations[name] = {
                    "sha256": record["sha256"],
                    "state_digest": state_digest(preserved),
                    "epoch": state["epoch"],
                    "step": state["step"],
                    "best": state["best"],
                    "aliases": [],
                }
                del state, preserved
            if generations[name]["sha256"] != record["sha256"]:
                raise ValueError("Aliases disagree about the same checkpoint generation")
            generations[name]["aliases"].append(alias)
        _verify_aliases(index, generations, completed, config)
        selected = generations[index["files"][required_alias]["path"]]
        if action == "resume" and selected["epoch"] >= config.epochs:
            raise ValueError("Latest checkpoint already reached its budget; do not retrain")
        if action == "predict":
            if (
                completed.get("epochs") != config.epochs
                or completed.get("steps") != config.epochs * config.steps_per_epoch
            ):
                raise ValueError(
                    "Parent completion record disagrees with the fixed training budget"
                )
            final = index["files"].get("checkpoint_final.pth")
            if not final or generations[final["path"]]["epoch"] != config.epochs:
                raise ValueError("Completed training requires a final checkpoint at its budget")
        parent = {
            "workspace": str(source),
            "binding_sha256": artifact_hashes["binding.json"],
            "binding_identity": _digest(old),
            "code_digest": _digest(old["code"]),
            "origin_sha256": artifact_hashes["scratch-origin.json"],
            "checkpoint_index_sha256": artifact_hashes["checkpoint-index.json"],
            "artifact_sha256": artifact_hashes,
            "policy_digest": _digest(policy),
            "action": action,
        }
        binding = copy.deepcopy(old)
        binding.update(
            run_id=uuid.uuid4().hex, config=_config_record(config), code=reviewed["target"]
        )
        binding["continuation_lineage"] = [*old.get("continuation_lineage", []), parent]
        identity = _digest(binding)
        new_origin = {**origin, "identity": identity}
        report = {
            "schema_version": 1,
            "action": action,
            "dry_run": dry_run,
            "parent": parent,
            "target_workspace": str(target),
            "target_identity": identity,
            "changed_files": reviewed["changed"],
            "checkpoint": required_alias,
            "resume_epoch": selected["epoch"],
            "resume_step": selected["step"],
            "generations": generations,
            "preprocessing_required_before_execution": True,
            "training_state_fields_preserved": sorted(_REQUIRED_STATE - {"identity", "origin"}),
            "validation_schedule_unchanged": True,
        }
        _verify_captured_artifacts(source, artifact_hashes)
        if dry_run:
            return report
        target.parent.mkdir(parents=True, exist_ok=True)
        with _lock(target.parent / f".{target.name}.continuation.lock"):
            if target.exists():
                raise FileExistsError("Continuation target appeared during verification")
            stage = Path(
                tempfile.mkdtemp(prefix=f".{target.name}.continuation-", dir=target.parent)
            )
            try:
                provenance = stage / "continuation-parent"
                provenance.mkdir()
                for name, data in captured_artifacts.items():
                    if data is not None:
                        with (provenance / name).open("xb") as stream:
                            stream.write(data)
                            stream.flush()
                            os.fsync(stream.fileno())
                _atomic_json(provenance / "policy.json", policy)
                _atomic_json(stage / "binding.json", binding)
                _atomic_json(stage / "resolved-config.json", _config_record(config))
                _atomic_json(stage / "scratch-origin.json", new_origin)
                new_index: dict[str, Any] = {
                    "identity": identity,
                    "initialization": "scratch",
                    "files": {},
                }
                (stage / "checkpoints").mkdir()
                for name, info in generations.items():
                    original = provenance / name
                    shutil.copyfile(source / "checkpoints" / name, original)
                    _check_hash(original, info["sha256"])
                    with original.open("rb") as stream:
                        os.fsync(stream.fileno())
                    state = torch.load(original, map_location="cpu", weights_only=False)
                    state.update(identity=identity, origin=new_origin)
                    generation = stage / "checkpoints" / f"generation-{uuid.uuid4().hex}.pth"
                    with generation.open("xb") as stream:
                        torch.save(state, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                    del state
                    reloaded = torch.load(generation, map_location="cpu", weights_only=False)
                    unchanged = state_digest(
                        {k: v for k, v in reloaded.items() if k not in {"identity", "origin"}}
                    )
                    if (
                        unchanged != info["state_digest"]
                        or reloaded["origin"] != new_origin
                        or reloaded["identity"] != identity
                    ):
                        raise ValueError("Continuation altered preserved checkpoint state")
                    del reloaded
                    item = {"path": generation.name, "sha256": _sha(generation)}
                    for alias in info["aliases"]:
                        new_index["files"][alias] = item
                _atomic_json(stage / "checkpoint-index.json", new_index)
                if completed:
                    _atomic_json(
                        stage / "training-result.json", {**completed, "identity": identity}
                    )
                _atomic_json(stage / "continuation.json", report)
                # Verify source/index/snapshot again before publication. An
                # atomic rename exposes either no target or the complete run.
                _verify_captured_artifacts(source, artifact_hashes)
                if (
                    code_hashes(source_root) != reviewed["source"]
                    or code_hashes(target_root) != reviewed["target"]
                ):
                    raise ValueError("Source changed during continuation capture")
                for directory in (provenance, stage / "checkpoints", stage):
                    descriptor = os.open(directory, os.O_RDONLY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                os.rename(stage, target)
                descriptor = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        return report
