"""Fill the campaign's allowed GPUs with verified full-statistics jobs.

Workers start only on GPUs in the campaign's frozen allowlist. With
``--previous-campaign`` the previous launcher must be stopped (its ``STOP`` file
exists) or provably gone (its ``locks/launcher.lock`` can be taken; it is then
held for this launcher's lifetime so it cannot come back and double-book a GPU),
and a GPU is taken over only once that campaign's worker has released its
``locks/gpu-N.lock`` (a worker holds it for its whole life, including between
jobs, so this proves the worker exited). With ``--checkout`` the publisher is
handed off once the previous campaign has nothing active and nothing queued;
without it no publisher is ever started. A worker whose tmux session died while
its job was active is restarted so the job resumes. The launcher exits once no
job is queued and none is active.
"""

from __future__ import annotations

import argparse
import contextlib
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_rtis_campaign as runtime

from segmentary import gpu_policy

ACTIVE = ("training", "evaluating", "collecting")
RESULTS_ROOT = Path("docs/results")


def session_exists(name):
    return (
        subprocess.run(
            ["tmux", "has-session", "-t", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def start_session(name, command, repo, log, prefix, extra_env=None):
    """tmux never inherits the launcher's environment, so pin it in the command."""
    words = [*prefix, f"PYTHONPATH={repo / 'src'}"]
    words += [f"{key}={value}" for key, value in (extra_env or {}).items()]
    shell = (
        f"cd {shlex.quote(str(repo))} && "
        + shlex.join([*words, *command])
        + f" >> {shlex.quote(str(log))} 2>&1"
    )
    subprocess.run(["tmux", "new-session", "-d", "-s", name, shell], check=True)


def require_preflight(root, repo, campaign):
    """A smoke-validated launch record must match this code and this allowlist."""
    if campaign.get("smoke") is True:
        return None
    try:
        preflight = runtime.read(root / "launch-validation.json")
    except FileNotFoundError as error:
        raise RuntimeError(
            "Verified GPU collection preflight is required before launch; run scripts/validate_rtis_launch.py"
        ) from error
    if (
        preflight.get("passed") is not True
        or preflight.get("code_sha") != runtime.git(repo, "rev-parse", "HEAD")
        or preflight.get("gpu_policy_sha256") != campaign.get("gpu_policy_sha256")
    ):
        raise RuntimeError(
            "launch-validation.json does not match this code revision and GPU policy"
        )
    return preflight


def report_dir_for(campaign, requested=None):
    """Each campaign publishes under docs/results/<dataset>/live unless told otherwise."""
    report = (
        Path(requested) if requested is not None else RESULTS_ROOT / campaign["dataset"] / "live"
    )
    if report.is_absolute() or ".." in report.parts or not report.is_relative_to(RESULTS_ROOT):
        raise RuntimeError(f"--report-dir must be a relative path inside {RESULTS_ROOT}: {report}")
    return report


def states(root):
    return [runtime.read(p) for p in sorted((root / "state").glob("*.json"))]


def worker_session(root, gpu):
    return f"rtis-{root.name}-gpu-{gpu}"


def orphaned_active(root, current):
    """Active jobs whose worker session is gone; a restarted worker resumes them."""
    return [
        s["name"]
        for s in current
        if s["status"] in ACTIVE and not session_exists(worker_session(root, s.get("gpu")))
    ]


def previous_drained(old):
    """Nothing active, and nothing queued that the old campaign could still start."""
    stopped = (old / "STOP").exists()
    return not any(
        s["status"] in ACTIVE or (s["status"] == "queued" and not stopped) for s in states(old)
    )


def handoff_publisher(root, old, checkout, repo, logs, report):
    """Start our publisher once the previous campaign has nothing active or queued."""
    new_publisher = f"rtis-{root.name}-publisher"
    if old is not None:
        if not previous_drained(old):
            return
        (old / "STOP_PUBLISHER").write_text(
            "Archive the drained campaign and hand off to the next campaign\n"
        )
        if session_exists(f"rtis-{old.name}-publisher"):
            return
    if session_exists(new_publisher):
        return
    if old is not None:
        # Read-modify-write keeps every frozen field, including gpu_policy.
        campaign = runtime.read(root / "campaign.json")
        status = old / "publisher-status.json"
        if status.exists():
            campaign["previous_report_commit"] = runtime.read(status).get("commit")
        campaign["previous_campaign"] = str(old)
        runtime.write(root / "campaign.json", campaign)
    start_session(
        new_publisher,
        [
            sys.executable,
            "-u",
            str(repo / "scripts/publish_rtis_results.py"),
            "--campaign",
            str(root),
            "--checkout",
            str(checkout),
            "--report-dir",
            str(report),
        ],
        repo,
        logs / "publisher.log",
        gpu_policy.no_gpu_prefix(),
    )


def previous_launcher_gate(old):
    """Hold the previous launcher's lock unless that campaign is already stopped."""
    if old is None or (old / "STOP").exists():
        return contextlib.nullcontext(True)
    return runtime.lock(old / "locks" / "launcher.lock")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument(
        "--previous-campaign",
        type=Path,
        help="take over each GPU only after this campaign's worker released its lock",
    )
    ap.add_argument(
        "--checkout", type=Path, help="publisher checkout; without it no publisher starts"
    )
    ap.add_argument(
        "--report-dir",
        type=Path,
        help="publisher target relative to the checkout (default docs/results/<dataset>/live)",
    )
    ap.add_argument(
        "--hf-home", type=Path, help="HF_HOME for worker sessions (tmux does not inherit it)"
    )
    ap.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Do not start the shared tmux progress dashboard",
    )
    args = ap.parse_args()
    root = args.campaign.resolve()
    old = args.previous_campaign.resolve() if args.previous_campaign else None
    checkout = args.checkout.resolve() if args.checkout else None
    repo = Path(__file__).resolve().parents[1]
    campaign = runtime.verify_frozen(root, repo)
    policy = gpu_policy.load(campaign)
    require_preflight(root, repo, campaign)
    if old is not None and not (old / "campaign.json").is_file():
        raise RuntimeError(f"Previous campaign is not initialized: {old}")
    if checkout is not None and checkout == repo:
        raise RuntimeError("A separate publisher checkout is required")
    report = report_dir_for(campaign, args.report_dir) if checkout is not None else None
    extra_env = {"HF_HOME": str(args.hf_home.resolve())} if args.hf_home else None
    logs = root / "service-logs"
    logs.mkdir(exist_ok=True)
    with runtime.lock(root / "locks/launcher.lock") as acquired:
        if not acquired:
            raise RuntimeError("Launcher already running")
        with previous_launcher_gate(old) as previous_stopped:
            if not previous_stopped:
                raise RuntimeError(
                    f"The launcher of {old} is still running and could start workers on "
                    "GPUs this campaign takes over; write its STOP file (and let it exit "
                    "via STOP_LAUNCHER) before chaining"
                )
            if not args.no_dashboard:
                sys.path.insert(0, str(repo / "src"))
                from segmentary.campaign_dashboard import ensure_dashboard

                ensure_dashboard(root, repo, sys.executable, session="rtis-fullstats-controller")
            while not (root / "STOP_LAUNCHER").exists():
                status = {
                    "at": runtime.now(),
                    "allowed_gpus": list(gpu_policy.allowed_indices(policy)),
                    "policy": "Start only an allowed, idle GPU after the previous worker lock releases; restart a worker whose session died with an active job; never start a publisher without --checkout",
                }
                try:
                    runtime.verify_frozen(root, repo)
                    current = states(root)
                    queued = sum(s["status"] == "queued" for s in current)
                    active = sum(s["status"] in ACTIVE for s in current)
                    orphaned = orphaned_active(root, current)
                    status.update(queued=queued, active=active, orphaned_active=orphaned)
                    # With nothing queued only the orphaned jobs need a worker each.
                    slots = None if queued else len(orphaned)
                    if (queued or orphaned) and not (root / "STOP").exists():
                        busy = {
                            gpu_policy.normalize_uuid(uuid) for _, uuid in gpu_policy.compute_apps()
                        }
                        for entry in policy["allowed"]:
                            if slots is not None and slots <= 0:
                                break
                            index = int(entry["index"])
                            session = worker_session(root, index)
                            if gpu_policy.normalize_uuid(entry["uuid"]) in busy or session_exists(
                                session
                            ):
                                continue
                            # The previous worker holds its GPU lock until it exits, also
                            # between jobs; acquiring it proves that GPU is free of it.
                            gate = (
                                runtime.lock(old / "locks" / f"gpu-{index}.lock")
                                if old is not None
                                else contextlib.nullcontext(True)
                            )
                            with gate as free:
                                if not free:
                                    continue
                                start_session(
                                    session,
                                    [
                                        sys.executable,
                                        "-u",
                                        str(repo / "scripts/run_rtis_full_campaign.py"),
                                        "--campaign",
                                        str(root),
                                        "--gpu",
                                        str(index),
                                    ],
                                    repo,
                                    logs / f"gpu-{index}.log",
                                    gpu_policy.shell_prefix(policy, index),
                                    extra_env,
                                )
                                if slots is not None:
                                    slots -= 1
                    if checkout is not None:
                        handoff_publisher(root, old, checkout, repo, logs, report)
                except gpu_policy.GpuInspectionError as error:
                    # nvidia-smi is unavailable: start nothing this pass, keep the
                    # running workers, and try again. Any other policy error is fatal.
                    status["inspection_error"] = str(error)
                    runtime.write(root / "launcher-status.json", status)
                    time.sleep(30)
                    continue
                status["publisher_started"] = session_exists(f"rtis-{root.name}-publisher")
                if old is not None:
                    status["previous_active"] = sum(s["status"] in ACTIVE for s in states(old))
                if not queued and not active:
                    status["finished"] = True
                    runtime.write(root / "launcher-status.json", status)
                    return
                runtime.write(root / "launcher-status.json", status)
                time.sleep(30)


if __name__ == "__main__":
    main()
