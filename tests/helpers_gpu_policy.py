"""Fake ten-GPU host shared by the RTIS GPU-policy tests (no GPU, no nvidia-smi)."""

from __future__ import annotations

import json
from pathlib import Path

from segmentary import gpu_policy

HOST = "fake-host"
INVENTORY = [
    {
        "index": index,
        "uuid": f"GPU-{index:08x}-0000-0000-0000-00000000000{index}",
        "pci_bus_id": f"00000000:{0x10 + index:02X}:00.0",
    }
    for index in range(10)
]
ALLOWED = tuple(range(2, 10))


def uuid_of(index: int) -> str:
    return INVENTORY[index]["uuid"]


def make_policy(allowed=ALLOWED) -> dict:
    return gpu_policy.freeze(allowed, INVENTORY, HOST)


def make_campaign(allowed=ALLOWED, **extra) -> dict:
    policy = make_policy(allowed)
    return {
        "code_sha": "code",
        "plan_sha256": "plan",
        "gpu_policy": policy,
        "gpu_policy_sha256": gpu_policy.policy_sha256(policy),
        **extra,
    }


def write_campaign(root: Path, allowed=ALLOWED, jobs=(), **extra) -> dict:
    """campaign.json plus a matching plan.json and queued states."""
    root.mkdir(parents=True, exist_ok=True)
    campaign = make_campaign(allowed, **extra)
    plan = {
        "gpu_allowlist": sorted(allowed),
        "jobs": [{"name": name} for name in jobs],
        "smoke": bool(extra.get("smoke")),
    }
    (root / "plan.json").write_text(json.dumps(plan))
    campaign["plan_sha256"] = gpu_policy.hashlib.sha256(
        (root / "plan.json").read_bytes()
    ).hexdigest()
    (root / "campaign.json").write_text(json.dumps(campaign))
    for name in jobs:
        (root / "state").mkdir(exist_ok=True)
        (root / "state" / f"{name}.json").write_text(json.dumps({"name": name, "status": "queued"}))
    return campaign


def patch_live(monkeypatch, compute_apps=()) -> None:
    """Make the fake host the live one and keep torch/NVML out of the picture."""
    monkeypatch.setattr(gpu_policy, "inventory", lambda: INVENTORY)
    monkeypatch.setattr(gpu_policy, "hostname", lambda: HOST)
    monkeypatch.setattr(gpu_policy, "nvml_uuids", lambda: None)
    monkeypatch.setattr(gpu_policy, "compute_apps", lambda: list(compute_apps))


def pinned_env(gpu: int, campaign_json: Path | None = None, **base) -> dict:
    env = {
        **base,
        "CUDA_DEVICE_ORDER": gpu_policy.DEVICE_ORDER,
        "CUDA_VISIBLE_DEVICES": str(gpu),
    }
    if campaign_json is not None:
        env[gpu_policy.POLICY_ENV] = str(campaign_json)
        env[gpu_policy.ASSIGNED_ENV] = str(gpu)
    return env
