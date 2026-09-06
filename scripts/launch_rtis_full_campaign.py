"""Fill idle GPUs with verified full-statistics jobs and hand off publication."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_rtis_campaign as runtime


def session_exists(name):
    return (
        subprocess.run(
            ["tmux", "has-session", "-t", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def start_session(name, command, repo, log):
    shell = (
        f"cd {shlex.quote(str(repo))} && PYTHONPATH={shlex.quote(str(repo / 'src'))} "
        + shlex.join(command)
        + f" >> {shlex.quote(str(log))} 2>&1"
    )
    subprocess.run(["tmux", "new-session", "-d", "-s", name, shell], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--previous-campaign", type=Path, required=True)
    ap.add_argument("--checkout", type=Path, required=True)
    args = ap.parse_args()
    root = args.campaign.resolve()
    old = args.previous_campaign.resolve()
    repo = Path(__file__).resolve().parents[1]
    runtime.verify_frozen(root, repo)
    if not (old / "STOP").is_file():
        raise RuntimeError("Previous campaign must be draining before launch")
    preflight = runtime.read(root / "launch-validation.json")
    if preflight.get("passed") is not True or preflight.get("code_sha") != runtime.git(
        repo, "rev-parse", "HEAD"
    ):
        raise RuntimeError("Verified GPU collection preflight is required before launch")
    old_publisher = f"rtis-{old.name}-publisher"
    new_publisher = f"rtis-{root.name}-publisher"
    logs = root / "service-logs"
    logs.mkdir(exist_ok=True)
    with runtime.lock(root / "locks/launcher.lock") as acquired:
        if not acquired:
            raise RuntimeError("Launcher already running")
        while not (root / "STOP_LAUNCHER").exists():
            runtime.verify_frozen(root, repo)
            states = [runtime.read(p) for p in (root / "state").glob("*.json")]
            if any(s["status"] == "queued" for s in states) and not (root / "STOP").exists():
                busy = set(
                    subprocess.check_output(
                        ["nvidia-smi", "--query-compute-apps=gpu_uuid", "--format=csv,noheader"],
                        text=True,
                    )
                    .strip()
                    .splitlines()
                )
                for line in subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"], text=True
                ).splitlines():
                    index, uuid = [v.strip() for v in line.split(",")]
                    session = f"rtis-{root.name}-gpu-{index}"
                    if uuid in busy or session_exists(session):
                        continue
                    # The old STOP marker prevents new claims after this lock releases.
                    with runtime.lock(old / "locks" / f"gpu-{index}.lock") as free:
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
                                index,
                            ],
                            repo,
                            logs / f"gpu-{index}.log",
                        )
            old_states = [runtime.read(p) for p in (old / "state").glob("*.json")]
            if not any(s["status"] in ("training", "evaluating", "collecting") for s in old_states):
                (old / "STOP_PUBLISHER").write_text(
                    "Archive the drained pilot and hand off to full-statistics campaign\n"
                )
                if not session_exists(old_publisher) and not session_exists(new_publisher):
                    campaign = runtime.read(root / "campaign.json")
                    campaign["previous_report_commit"] = runtime.read(
                        old / "publisher-status.json"
                    )["commit"]
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
                            str(args.checkout),
                        ],
                        repo,
                        logs / "publisher.log",
                    )
            runtime.write(
                root / "launcher-status.json",
                {
                    "at": runtime.now(),
                    "queued": sum(s["status"] == "queued" for s in states),
                    "publisher_started": session_exists(new_publisher),
                    "previous_active": sum(
                        s["status"] in ("training", "evaluating", "collecting") for s in old_states
                    ),
                    "policy": "Start only on an idle GPU after the old worker lock releases; preserve previous report commit",
                },
            )
            time.sleep(30)


if __name__ == "__main__":
    main()
