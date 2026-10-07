"""Freeze a campaign's GPU allowlist and enforce it at every process boundary.

The policy is recorded once at campaign initialisation from the live
``nvidia-smi`` inventory (index, UUID and PCI bus id of every GPU on the host,
split into allowed and forbidden entries). Launchers iterate only the allowed
entries, workers refuse to start unless their own environment is pinned to one
allowed GPU, children re-check the pinning before touching CUDA, and the parent
polls ``nvidia-smi`` so a child that lands on a forbidden GPU is killed.

Only the standard library is imported at module import time; torch is imported
lazily by the functions that need it so orchestration parents never initialise
CUDA. Nothing here can be disabled by an environment variable or flag: when
``SEGMENTARY_GPU_POLICY`` is absent the process is simply not part of a campaign.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import time
import warnings
from pathlib import Path
from typing import Any

POLICY_ENV = "SEGMENTARY_GPU_POLICY"
ASSIGNED_ENV = "SEGMENTARY_ASSIGNED_GPU"
FORBIDDEN_ENV = "SEGMENTARY_FORBIDDEN_GPUS"
# Physical (PCI_BUS_ID-ordered) indices that belong to other users on the shared
# host. The environment variable can only add indices; nothing removes these.
DEFAULT_FORBIDDEN_GPUS = frozenset({0, 1})
DEVICE_ORDER = "PCI_BUS_ID"
SCHEMA_VERSION = 1
INVENTORY_ATTEMPTS = 3
INVENTORY_RETRY_SECONDS = 5.0


class GpuPolicyError(RuntimeError):
    """A GPU outside the frozen allowlist would be, or was, used."""


class GpuInspectionError(GpuPolicyError):
    """``nvidia-smi``/``ps`` could not be consulted, so placement is unverified.

    It is a ``GpuPolicyError`` so every caller that does not handle it still
    fails closed; callers that poll may treat it as transient and keep a
    running child alive while the tool is unavailable for a bounded time.
    """


def parse_gpus(text: str) -> tuple[int, ...]:
    """Parse ``"2,3,4"`` into distinct non-negative indices; refuse anything else."""
    tokens = [item.strip() for item in str(text).split(",")]
    if not tokens or any(not token.isdigit() for token in tokens):
        raise GpuPolicyError(f"GPU list must be comma-separated non-negative integers: {text!r}")
    values = tuple(int(token) for token in tokens)
    if len(set(values)) != len(values):
        raise GpuPolicyError(f"GPU list contains duplicates: {text!r}")
    return values


def forbidden_gpus(environ=None) -> frozenset[int]:
    """``DEFAULT_FORBIDDEN_GPUS`` plus any indices listed in ``SEGMENTARY_FORBIDDEN_GPUS``.

    The variable can only extend the set; a malformed value fails closed.
    """
    environ = os.environ if environ is None else environ
    extra = str(environ.get(FORBIDDEN_ENV, "")).strip()
    return DEFAULT_FORBIDDEN_GPUS | (frozenset(parse_gpus(extra)) if extra else frozenset())


def refuse_forbidden(gpus, environ=None) -> None:
    """Refuse to schedule or expose any physical GPU index in the forbidden set."""
    forbidden = forbidden_gpus(environ)
    requested = []
    for gpu in gpus:
        text = str(gpu).strip()
        if isinstance(gpu, bool) or not text.isdigit():
            raise GpuPolicyError(f"GPU must be a physical numeric index, got {gpu!r}")
        requested.append(int(text))
    blocked = sorted(set(requested) & forbidden)
    if blocked:
        raise GpuPolicyError(
            f"GPU(s) {blocked} are forbidden on this host (forbidden set {sorted(forbidden)}); "
            "choose other GPUs"
        )


def hostname() -> str:
    return socket.gethostname()


def inventory(attempts: int = INVENTORY_ATTEMPTS) -> list[dict[str, Any]]:
    """Every GPU on this host as ``{"index", "uuid", "pci_bus_id"}`` from nvidia-smi.

    A slow or hiccupping ``nvidia-smi`` is retried a few times with a pause so a
    transient tool failure does not look like a policy violation; after the
    last attempt a ``GpuInspectionError`` is raised and the caller fails closed.
    """
    output = None
    for attempt in range(1, max(1, int(attempts)) + 1):
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=index,uuid,pci.bus_id", "--format=csv,noheader"],
                text=True,
                timeout=20,
            )
            break
        except (OSError, subprocess.SubprocessError) as error:
            if attempt >= attempts:
                raise GpuInspectionError(
                    f"Could not read the GPU inventory after {attempt} attempt(s): {error}"
                ) from error
            time.sleep(INVENTORY_RETRY_SECONDS)
    assert output is not None
    rows = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = [item.strip() for item in line.split(",")]
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1] or not parts[2]:
            raise GpuPolicyError(f"Unexpected nvidia-smi inventory row: {line!r}")
        rows.append({"index": int(parts[0]), "uuid": parts[1], "pci_bus_id": parts[2]})
    if not rows:
        raise GpuPolicyError("nvidia-smi reported no GPUs")
    if len({row["index"] for row in rows}) != len(rows):
        raise GpuPolicyError("nvidia-smi reported duplicate GPU indices")
    return rows


def freeze(allowed, inventory: list[dict[str, Any]], hostname: str) -> dict[str, Any]:
    """Record the allowed entries and every other GPU as forbidden."""
    allowed = tuple(int(index) for index in allowed)
    if not allowed or len(set(allowed)) != len(allowed):
        raise GpuPolicyError("Allowlist must be a non-empty list of distinct GPU indices")
    by_index = {int(row["index"]): row for row in inventory}
    missing = [index for index in allowed if index not in by_index]
    if missing:
        raise GpuPolicyError(f"Allowed GPU(s) {missing} are not in the host inventory")
    # CUDA_VISIBLE_DEVICES=<index> under PCI_BUS_ID order means "the index-th GPU in
    # PCI order"; that only names the nvidia-smi index when the two orders agree.
    pci_order = [row["index"] for row in sorted(inventory, key=lambda row: row["pci_bus_id"])]
    if pci_order != sorted(by_index):
        raise GpuPolicyError(f"nvidia-smi index order differs from PCI bus order: {pci_order}")

    def entry(index):
        row = by_index[index]
        return {"index": index, "uuid": str(row["uuid"]), "pci_bus_id": str(row["pci_bus_id"])}

    return {
        "schema_version": SCHEMA_VERSION,
        "hostname": hostname,
        "device_order": DEVICE_ORDER,
        "allowed": [entry(index) for index in sorted(allowed)],
        "forbidden": [entry(index) for index in sorted(by_index) if index not in allowed],
        "host_gpu_count": len(by_index),
    }


def policy_sha256(policy: dict[str, Any]) -> str:
    canonical = json.dumps(policy, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def load(campaign) -> dict[str, Any]:
    """Return ``campaign["gpu_policy"]`` from a campaign dict or a campaign.json path."""
    if not isinstance(campaign, dict):
        try:
            campaign = json.loads(Path(campaign).read_text())
        except (OSError, ValueError) as error:
            raise GpuPolicyError(f"Cannot read campaign policy {campaign}: {error}") from error
    policy = campaign.get("gpu_policy")
    if not isinstance(policy, dict) or not policy.get("allowed"):
        raise GpuPolicyError("Campaign has no frozen gpu_policy; refusing to use any GPU")
    if policy.get("device_order") != DEVICE_ORDER:
        raise GpuPolicyError(f"gpu_policy device_order must be {DEVICE_ORDER}")
    return policy


def allowed_indices(policy: dict[str, Any]) -> tuple[int, ...]:
    return tuple(int(entry["index"]) for entry in policy["allowed"])


def allowed_uuids(policy: dict[str, Any]) -> set[str]:
    return {normalize_uuid(entry["uuid"]) for entry in policy["allowed"]}


def forbidden_uuids(policy: dict[str, Any]) -> set[str]:
    return {normalize_uuid(entry["uuid"]) for entry in policy.get("forbidden", [])}


def require_allowed(policy: dict[str, Any], gpu) -> dict[str, Any]:
    if not isinstance(gpu, int) or isinstance(gpu, bool):
        raise GpuPolicyError(f"GPU index must be an int, got {gpu!r}")
    for entry in policy["allowed"]:
        if int(entry["index"]) == gpu:
            return entry
    raise GpuPolicyError(
        f"GPU {gpu} is not in the campaign allowlist {list(allowed_indices(policy))}"
    )


def normalize_uuid(value: str) -> str:
    """nvidia-smi prints ``GPU-<hex>``; torch's device properties may omit the prefix."""
    text = str(value).strip().lower()
    for prefix in ("gpu-", "mig-"):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def verify_inventory(policy: dict[str, Any], live=None, host=None) -> None:
    """Every frozen entry must still be the same card at the same index and PCI slot."""
    live = inventory() if live is None else live
    host = hostname() if host is None else host
    if host != policy["hostname"]:
        raise GpuPolicyError(f"GPU policy was frozen on {policy['hostname']!r}, not {host!r}")
    by_index = {int(row["index"]): row for row in live}
    if len(by_index) != policy["host_gpu_count"]:
        raise GpuPolicyError(
            f"Host now has {len(by_index)} GPUs; policy froze {policy['host_gpu_count']}"
        )
    for kind in ("allowed", "forbidden"):
        for entry in policy.get(kind, []):
            row = by_index.get(int(entry["index"]))
            if row is None:
                raise GpuPolicyError(f"GPU {entry['index']} ({kind}) is no longer present")
            if normalize_uuid(row["uuid"]) != normalize_uuid(entry["uuid"]):
                raise GpuPolicyError(
                    f"GPU {entry['index']} ({kind}) UUID changed: frozen {entry['uuid']}, live {row['uuid']}"
                )
            if str(row["pci_bus_id"]) != str(entry["pci_bus_id"]):
                raise GpuPolicyError(
                    f"GPU {entry['index']} ({kind}) moved: frozen PCI {entry['pci_bus_id']}, live {row['pci_bus_id']}"
                )


def child_env(base, policy: dict[str, Any], gpu: int, campaign_json) -> dict[str, str]:
    """Environment for a process that may touch exactly the one allowed GPU ``gpu``."""
    require_allowed(policy, gpu)
    campaign_json = Path(campaign_json)
    if campaign_json.name != "campaign.json":
        raise GpuPolicyError(f"Policy path must be a campaign.json: {campaign_json}")
    return {
        **dict(base),
        "CUDA_DEVICE_ORDER": DEVICE_ORDER,
        "CUDA_VISIBLE_DEVICES": str(gpu),
        POLICY_ENV: str(campaign_json),
        ASSIGNED_ENV: str(gpu),
    }


def shell_prefix(policy: dict[str, Any], gpu: int) -> list[str]:
    """``env`` words that pin a tmux command, which never inherits the launcher's env."""
    require_allowed(policy, gpu)
    return ["env", f"CUDA_DEVICE_ORDER={DEVICE_ORDER}", f"CUDA_VISIBLE_DEVICES={gpu}"]


def no_gpu_prefix() -> list[str]:
    """``env`` words for sessions that must never see a GPU (publisher, dashboard)."""
    return ["env", "CUDA_VISIBLE_DEVICES="]


def assert_env(policy: dict[str, Any], gpu: int, environ=None) -> dict[str, Any]:
    """The process may see exactly its one allowed GPU, addressed in PCI order."""
    environ = os.environ if environ is None else environ
    entry = require_allowed(policy, gpu)
    raw = environ.get("CUDA_VISIBLE_DEVICES")
    tokens = [item.strip() for item in raw.split(",")] if isinstance(raw, str) else []
    if tokens != [str(gpu)]:
        raise GpuPolicyError(
            f"CUDA_VISIBLE_DEVICES must be exactly {gpu!r} for GPU {gpu} ({entry['uuid']}), got {raw!r}"
        )
    if environ.get("CUDA_DEVICE_ORDER") != DEVICE_ORDER:
        raise GpuPolicyError(
            f"CUDA_DEVICE_ORDER must be {DEVICE_ORDER} for GPU {gpu}, got {environ.get('CUDA_DEVICE_ORDER')!r}"
        )
    assigned = environ.get(ASSIGNED_ENV)
    if assigned is not None and assigned != str(gpu):
        raise GpuPolicyError(f"{ASSIGNED_ENV}={assigned!r} disagrees with GPU {gpu}")
    return entry


def nvml_uuids() -> list[str] | None:
    """NVML-ordered UUIDs without creating a CUDA context; None when unavailable."""
    try:
        import torch
    except ImportError:
        return None
    reader = getattr(getattr(torch, "cuda", None), "_raw_device_uuid_nvml", None)
    if reader is None:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            values = reader()
    except Exception:
        return None
    return [str(value) for value in values] if values else None


def torch_visible_uuid() -> tuple[int, str]:
    """``(device_count, uuid of cuda:0)`` as seen by torch; initialises CUDA."""
    import torch

    if not torch.cuda.is_available():
        raise GpuPolicyError("CUDA is not available to this process under a GPU policy")
    count = int(torch.cuda.device_count())
    if count != 1:
        raise GpuPolicyError(
            f"Exactly one GPU must be visible under a GPU policy, torch sees {count}"
        )
    properties = torch.cuda.get_device_properties(0)
    uuid = getattr(properties, "uuid", None)
    if uuid is None:
        raise GpuPolicyError("torch cannot report the device UUID; refusing to run under a policy")
    return count, normalize_uuid(str(uuid))


def enforce_from_env(*, init_cuda: bool, environ=None) -> dict[str, Any] | None:
    """Fail closed when ``SEGMENTARY_GPU_POLICY`` names a campaign; no-op otherwise."""
    environ = os.environ if environ is None else environ
    policy_path = environ.get(POLICY_ENV)
    if not policy_path:
        return None
    policy = load(policy_path)
    assigned = environ.get(ASSIGNED_ENV)
    if assigned is None or not assigned.isdigit():
        raise GpuPolicyError(f"{ASSIGNED_ENV} must name the assigned GPU index, got {assigned!r}")
    gpu = int(assigned)
    entry = assert_env(policy, gpu, environ)
    verify_inventory(policy)
    expected = normalize_uuid(entry["uuid"])
    evidence = {"index": gpu, "uuid": entry["uuid"], "verified_by": "nvidia-smi"}
    nvml = nvml_uuids()
    if nvml is not None:
        if gpu >= len(nvml) or normalize_uuid(nvml[gpu]) != expected:
            raise GpuPolicyError(
                f"NVML reports {nvml[gpu] if gpu < len(nvml) else None!r} at index {gpu}, policy expects {entry['uuid']}"
            )
        evidence["verified_by"] = "nvml"
    if init_cuda:
        _, actual = torch_visible_uuid()
        if actual != expected:
            raise GpuPolicyError(
                f"torch is on GPU {actual!r} but GPU {gpu} ({entry['uuid']}) was assigned"
            )
        evidence["verified_by"] = "torch"
    return evidence


def compute_apps() -> list[tuple[int, str]]:
    """``(pid, gpu_uuid)`` for every compute process nvidia-smi reports."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid,gpu_uuid", "--format=csv,noheader"],
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise GpuInspectionError(f"Could not list GPU compute processes: {error}") from error
    rows = []
    for line in output.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) >= 2 and parts[0].isdigit():
            rows.append((int(parts[0]), parts[1]))
    return rows


def descendant_pids(pid: int) -> set[int]:
    """``pid`` plus every transitive child (dataloader workers, DDP ranks)."""
    try:
        output = subprocess.check_output(["ps", "-A", "-o", "pid=,ppid="], text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as error:
        raise GpuInspectionError(f"Could not list processes: {error}") from error
    children: dict[int, list[int]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    tree, pending = {int(pid)}, [int(pid)]
    while pending:
        for child in children.get(pending.pop(), []):
            if child not in tree:
                tree.add(child)
                pending.append(child)
    return tree


def assert_pid_on_uuid(pid: int, uuid: str) -> None:
    """The pid and its descendants may hold contexts only on the expected GPU.

    Raises ``GpuPolicyError`` on an observed foreign context and the
    ``GpuInspectionError`` subclass when the process tables could not be read.
    """
    expected = normalize_uuid(uuid)
    tree = descendant_pids(pid)
    for process, actual in compute_apps():
        if process in tree and normalize_uuid(actual) != expected:
            raise GpuPolicyError(
                f"Process {process} (tree of {pid}) has a context on GPU {actual}, not {uuid}"
            )
