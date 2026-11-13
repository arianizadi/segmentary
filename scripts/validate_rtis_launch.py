"""Turn a completed smoke campaign into the main campaign's launch-validation.json.

The smoke campaign must have run the same frozen code on a subset of the main
campaign's allowed GPUs, with every job completed and its collection verified
on an allowed GPU. A live nvidia-smi reading must show none of this main/smoke campaign's
compute processes on a forbidden GPU; unrelated user workloads are not blocked. Only then is the record written,
and scripts/launch_rtis_full_campaign.py requires it to match both the code
revision and the frozen GPU policy.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shlex
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


def process_context(pid):
    """Inspect only attribution fields; never return arbitrary environment secrets."""
    try:
        output = subprocess.check_output(
            ["ps", "-o", "ppid=,args=", "-p", str(pid)], text=True, timeout=10
        ).strip()
        parent, command = output.split(None, 1)
        if not parent.isdigit() or not command:
            raise ValueError("Missing process attribution fields")
        proc = Path("/proc") / str(pid)
        cwd = os.readlink(proc / "cwd")
        # Read the environment to select this one policy key, never log other keys.
        raw = (proc / "environ").read_bytes()
        policy = next(
            (
                item.split(b"=", 1)[1].decode(errors="replace")
                for item in raw.split(b"\0")
                if item.startswith(b"SEGMENTARY_GPU_POLICY=")
            ),
            None,
        )
        return {"ppid": int(parent), "command": command, "cwd": cwd, "policy": policy}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise gpu_policy.GpuInspectionError(
            f"Cannot attribute forbidden-GPU process {pid} to a campaign"
        ) from error


def contains_scope_path(text, scopes):
    """Match whole path boundaries; /campaign-a must not match /campaign-ab."""
    return any(
        re.search(r"(?<![A-Za-z0-9_./-])" + re.escape(str(scope)) + r"(?=$|[/\s\"'=:,])", str(text))
        for scope in scopes
    )


def campaign_processes_on_forbidden(policy, roots, user=None):
    """Block scoped contexts and fail closed when a same-user context is ambiguous.

    A context is scoped if its command, cwd, explicit GPU-policy path, or any
    same-user ancestor identifies the main campaign, its smoke campaign, or the
    frozen tools checkout. Explicit foreign policy paths/project commands are
    sufficient unrelated-workload evidence only after the ancestry is checked.
    """
    user = getpass.getuser() if user is None else user
    scopes = [Path(root).resolve() for root in roots]
    forbidden = gpu_policy.forbidden_uuids(policy)
    offenders = []
    for pid, uuid in gpu_policy.compute_apps():
        if gpu_policy.normalize_uuid(uuid) not in forbidden:
            continue
        owner = process_owner(pid)
        if owner is None:
            raise gpu_policy.GpuInspectionError(f"Cannot identify forbidden-GPU process {pid}")
        if owner != user:
            continue
        current, seen, scoped, foreign = pid, set(), False, False
        while current > 1:
            if current in seen or len(seen) >= 64:
                raise gpu_policy.GpuInspectionError(f"Ambiguous process ancestry for {pid}")
            seen.add(current)
            context = process_context(current)
            fields = [context["command"], context["cwd"], context.get("policy") or ""]
            if any(contains_scope_path(value, scopes) for value in fields):
                scoped = True
                break
            if current == pid:
                policy_path = context.get("policy")
                try:
                    tokens = shlex.split(context["command"])
                except ValueError as error:
                    raise gpu_policy.GpuInspectionError(
                        f"Unreadable process command for {pid}"
                    ) from error
                # An explicit alternate campaign or project entrypoint/interpreter
                # provides affirmative attribution, unlike a generic python process.
                foreign = bool(policy_path and Path(policy_path).is_absolute()) or any(
                    token.startswith("/")
                    and ("/projects/" in token or "/.venv/" in token or token.endswith(".py"))
                    for token in tokens
                )
            parent = context["ppid"]
            if parent <= 1:
                break
            parent_owner = process_owner(parent)
            if parent_owner is None:
                raise gpu_policy.GpuInspectionError(f"Cannot inspect process ancestor of {pid}")
            if parent_owner != user:
                break
            current = parent
        if scoped:
            offenders.append((pid, uuid))
        elif not foreign:
            raise gpu_policy.GpuInspectionError(
                f"Cannot rule out campaign ownership of forbidden-GPU process {pid}"
            )
    return offenders


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
    offenders = campaign_processes_on_forbidden(
        policy, [root, smoke_root, Path(__file__).resolve().parents[1]]
    )
    if offenders:
        raise RuntimeError(f"Campaign has compute processes on forbidden GPUs: {offenders}")
    return {
        "passed": True,
        "code_sha": main["code_sha"],
        "gpu_policy_sha256": main["gpu_policy_sha256"],
        "smoke_campaign": str(smoke_root),
        "smoke_jobs": [s["name"] for s in states],
        "smoke_gpu_uuids": sorted({s["gpu_uuid"] for s in states}),
        "forbidden_gpu_uuids_checked": sorted(e["uuid"] for e in policy.get("forbidden", [])),
        "forbidden_process_scope": [
            str(root),
            str(smoke_root),
            str(Path(__file__).resolve().parents[1]),
        ],
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
