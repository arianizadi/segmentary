"""Turn a completed smoke campaign into the main campaign's launch-validation.json.

The smoke campaign must have run the same frozen code on a subset of the main
campaign's allowed GPUs, with every job completed and its collection verified
on an allowed GPU. A live nvidia-smi reading must show none of the current
user's compute processes on a forbidden GPU. Only then is the record written,
and scripts/launch_rtis_full_campaign.py requires it to match both the code
revision and the frozen GPU policy.
"""

from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_rtis_campaign as runtime

from segmentary import gpu_policy


def process_owner(pid):
    try:
        return subprocess.check_output(["ps", "-o", "user=", "-p", str(pid)], text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def own_processes_on_forbidden(policy, user=None):
    """``[(pid, uuid)]`` of the current user's contexts on forbidden GPUs."""
    user = getpass.getuser() if user is None else user
    forbidden = gpu_policy.forbidden_uuids(policy)
    return [
        (pid, uuid)
        for pid, uuid in gpu_policy.compute_apps()
        if gpu_policy.normalize_uuid(uuid) in forbidden and process_owner(pid) == user
    ]


def validate(root, smoke_root):
    main = runtime.read(root / "campaign.json")
    smoke = runtime.read(smoke_root / "campaign.json")
    if smoke.get("smoke") is not True:
        raise RuntimeError("Smoke campaign.json must have smoke: true")
    if main.get("smoke") is True:
        raise RuntimeError("The main campaign must not itself be a smoke campaign")
    if smoke.get("code_sha") != main.get("code_sha"):
        raise RuntimeError("Smoke campaign ran a different code revision than the main campaign")
    policy = gpu_policy.load(main)
    smoke_policy = gpu_policy.load(smoke)
    if gpu_policy.policy_sha256(policy) != main.get("gpu_policy_sha256"):
        raise RuntimeError("Main campaign gpu_policy hash mismatch")
    allowed = gpu_policy.allowed_uuids(policy)
    if not gpu_policy.allowed_uuids(smoke_policy) <= allowed or not set(
        gpu_policy.allowed_indices(smoke_policy)
    ) <= set(gpu_policy.allowed_indices(policy)):
        raise RuntimeError("Smoke campaign allowlist is not a subset of the main allowlist")
    states = [runtime.read(p) for p in sorted((smoke_root / "state").glob("*.json"))]
    if not states:
        raise RuntimeError("Smoke campaign has no job states")
    for state in states:
        name = state.get("name", "?")
        if state.get("status") != "completed":
            raise RuntimeError(f"Smoke job {name} is {state.get('status')!r}, not completed")
        if state.get("collection", {}).get("verified") is not True:
            raise RuntimeError(f"Smoke job {name} has no verified collection")
        uuid = state.get("gpu_uuid")
        if not uuid or gpu_policy.normalize_uuid(uuid) not in allowed:
            raise RuntimeError(f"Smoke job {name} ran on GPU {uuid!r}, outside the allowlist")
    gpu_policy.verify_inventory(policy)
    offenders = own_processes_on_forbidden(policy)
    if offenders:
        raise RuntimeError(f"Current user has compute processes on forbidden GPUs: {offenders}")
    return {
        "passed": True,
        "code_sha": main["code_sha"],
        "gpu_policy_sha256": main["gpu_policy_sha256"],
        "smoke_campaign": str(smoke_root),
        "smoke_jobs": [s["name"] for s in states],
        "smoke_gpu_uuids": sorted({s["gpu_uuid"] for s in states}),
        "forbidden_gpu_uuids_checked": sorted(e["uuid"] for e in policy.get("forbidden", [])),
        "checked_at": runtime.now(),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--smoke-campaign", type=Path, required=True)
    args = ap.parse_args()
    root, smoke_root = args.campaign.resolve(), args.smoke_campaign.resolve()
    target = root / "launch-validation.json"
    try:
        record = validate(root, smoke_root)
    except Exception as error:
        runtime.write(
            target,
            {
                "passed": False,
                "smoke_campaign": str(smoke_root),
                "error": str(error),
                "checked_at": runtime.now(),
            },
        )
        raise
    runtime.write(target, record)
    print(f"PASS: {len(record['smoke_jobs'])} smoke jobs; wrote {target}", flush=True)


if __name__ == "__main__":
    main()
