#!/usr/bin/env python3
"""Read-only, bytes-bound access to a completed campaign's scratch checkpoint.

Historical guards execute in the historical source and interpreter. Diagnostics
then use their own explicitly recorded source, never rewriting a training binding
or weakening ordinary same-run resume guards. Call before initializing CUDA.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import io
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from benchmark_medical_inference import check_runtime, load_verified_checkpoint


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def _selected(campaign: Path, run_id: str) -> tuple[dict, dict]:
    spec = _read(campaign / "campaign.json")
    runs = [run for run in spec["runs"] if run["id"] == run_id]
    if len(runs) != 1 or runs[0].get("backend") != "torch":
        raise ValueError("Select exactly one existing Torch campaign run")
    return spec, runs[0]


@contextlib.contextmanager
def readonly_workspace(workspace: Path) -> Iterator[None]:
    """Concurrent diagnostic readers exclude every ordinary exclusive writer."""
    path = workspace / ".stage.lock"
    if not path.is_file():
        raise ValueError("Historical workspace has no existing stage lock")
    with path.open("rb") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Historical workspace has an active writer") from exc
        try:
            active = workspace / "active-stage.json"
            if active.exists() and _read(active).get("status") in {"running", "starting"}:
                raise RuntimeError("Historical workspace records an unfinished stage")
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _verify_original(campaign: Path, run_id: str) -> dict:
    """Subprocess entry: import only the original frozen medical source."""
    spec, run = _selected(campaign, run_id)
    source = Path(spec["source_root"]).resolve()
    sys.path.insert(0, str(source / "src"))
    from segmentary.medical import torch_backend as backend
    from segmentary.medical.backend import _digest
    from segmentary.medical.torch_config import TorchConfig

    if Path(backend.__file__).resolve().parents[3] != source:
        raise ValueError("Historical verification imported an unexpected source")
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, timeout=15
    ).strip()
    if revision != spec["source_commit"]:
        raise ValueError("Historical source revision differs from the campaign")
    workspace = Path(run["workspace"]).resolve()
    if _read(workspace / "training-result.json").get("completed") is not True:
        raise ValueError("Historical training has not completed")
    config = TorchConfig(**_read(workspace / "resolved-config.json"))
    if (
        config.root != workspace
        or Path(config.backend_python).resolve() != Path(sys.executable).resolve()
    ):
        raise ValueError("Historical workspace or interpreter differs")
    binding = backend._binding(config)
    check_runtime(binding["runtime"])
    origin = _read(workspace / "scratch-origin.json")
    if origin.get("initialization") != "scratch" or origin.get("external_weight_loads") != 0:
        raise ValueError("Diagnostic checkpoint must have a verified scratch origin")
    state, digest = load_verified_checkpoint(backend, config)
    if state.get("identity") != _digest(binding) or state.get("origin") != origin:
        raise ValueError("Historical checkpoint identity or scratch origin differs")
    index = _read(workspace / "checkpoint-index.json")
    item = index["files"]["checkpoint_best.pth"]
    path = workspace / "checkpoints" / item["path"]
    if item["sha256"] != digest or path.resolve().parent != (workspace / "checkpoints").resolve():
        raise ValueError("Historical checkpoint index changed or escaped its directory")
    return {
        "config": binding["config"],
        "binding": binding,
        "origin": origin,
        "checkpoint_sha256": digest,
        "checkpoint_path": str(path),
        "training_source_root": str(source),
        "training_source_commit": revision,
        "verification": {
            "protocol": "original_source_binding_runtime_and_scratch_guards_then_sha256_bound_bytes",
            "binding_identity": _digest(binding),
            "checkpoint_epoch": state.get("epoch"),
            "checkpoint_global_step": state.get("step", state.get("global_step")),
            "checkpoint_selection": "original_checkpoint_best.pth",
            "campaign_sha256": sha256(campaign / "campaign.json"),
            "helper_sha256": sha256(Path(__file__)),
        },
    }


@contextlib.contextmanager
def verified_historical_checkpoint(campaign: Path, run_id: str) -> Iterator[dict[str, Any]]:
    """Yield verified config/binding/origin/state while holding the original lock.

    The caller owns the GPU lock and may only narrow CUDA visibility afterwards.
    No file in the original workspace is created or changed by this helper.
    """
    import torch

    if torch.cuda.is_initialized():
        raise RuntimeError("Verify the historical checkpoint before initializing CUDA")
    campaign = campaign.resolve()
    _spec, run = _selected(campaign, run_id)
    workspace = Path(run["workspace"]).resolve()
    config = _read(workspace / "resolved-config.json")
    if Path(config["backend_python"]).resolve() != Path(sys.executable).resolve():
        raise ValueError("Run the diagnostic with the historical interpreter")
    with readonly_workspace(workspace):
        guarded = [
            campaign / "campaign.json",
            *[
                workspace / name
                for name in (
                    "resolved-config.json",
                    "binding.json",
                    "scratch-origin.json",
                    "checkpoint-index.json",
                    "training-result.json",
                )
            ],
        ]
        before = {str(path): sha256(path) for path in guarded}
        env = dict(os.environ, HF_HUB_OFFLINE="1", PYTHONNOUSERSITE="1")
        completed = subprocess.run(
            [
                config["backend_python"],
                str(Path(__file__).resolve()),
                "--verify-original",
                str(campaign),
                run_id,
            ],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        receipt = json.loads(completed.stdout)
        check_runtime(receipt["binding"]["runtime"])
        if receipt["config"] != config:
            raise ValueError("Historical config changed during diagnostic verification")
        data = Path(receipt["checkpoint_path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != receipt["checkpoint_sha256"]:
            raise ValueError("Checkpoint bytes changed after original-source verification")
        state = torch.load(io.BytesIO(data), map_location="cpu", weights_only=False)
        del data
        if (
            not isinstance(state, dict)
            or state.get("identity") != receipt["verification"]["binding_identity"]
            or state.get("origin") != receipt["origin"]
        ):
            raise ValueError("Diagnostic checkpoint payload identity differs")
        for kind in ("manifest", "splits"):
            path = Path(receipt["binding"][f"{kind}_path"])
            expected = receipt["binding"][f"{kind}_sha256"]
            if sha256(path) != expected:
                raise ValueError(f"Historical {kind} changed")
            before[str(path)] = expected
        medical_source = Path(receipt["training_source_root"]) / "src/segmentary/medical"
        for relative, expected in receipt["binding"]["code"].items():
            path = medical_source / relative
            if sha256(path) != expected:
                raise ValueError("Historical source changed after original verification")
            before[str(path)] = expected
        before[receipt["checkpoint_path"]] = receipt["checkpoint_sha256"]
        try:
            yield {**receipt, "state": state}
        finally:
            if any(sha256(Path(path)) != digest for path, digest in before.items()):
                raise ValueError("An original input changed during the read-only diagnostic")


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--verify-original":
        raise SystemExit("Internal original-source verifier")
    print(json.dumps(_verify_original(Path(sys.argv[2]).resolve(), sys.argv[3])))
