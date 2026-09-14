"""Best-effort, read-only dashboard launch shared by campaign schedulers."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

_ROOT_ENV = "SEGMENTARY_DASHBOARD_ROOT"


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")[:100] or "campaign"


def dashboard_session(root: Path) -> str:
    """Use the full resolved path to distinguish campaigns with the same basename."""
    root = root.resolve()
    digest = hashlib.sha256(os.fsencode(root)).hexdigest()[:10]
    return f"{_safe_name(root.name)}-controller-{digest}"


def _tmux(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["tmux", *arguments], capture_output=True, text=True, check=check, timeout=5
    )


def _exists(session: str) -> bool:
    return _tmux("has-session", "-t", f"={session}", check=False).returncode == 0


def _owns(session: str, root: Path) -> bool:
    result = _tmux("show-environment", "-t", f"={session}", _ROOT_ENV, check=False)
    return result.returncode == 0 and result.stdout.strip() == f"{_ROOT_ENV}={root}"


def ensure_dashboard(
    root: Path,
    repo: Path,
    python: str | Path,
    *,
    session: str | None = None,
) -> str | None:
    """Create or reuse this campaign's dashboard; never signal a training process.

    Existing sessions belong to us only when their environment records this exact
    campaign root. A requested name occupied by an unrelated or legacy session
    gets a deterministic path suffix; that session and its windows stay untouched.
    Missing tmux, dashboard dependencies, and other startup failures only produce
    diagnostics, so monitoring cannot prevent authorized training from starting.
    """
    log: Path | None = None
    try:
        root, repo = root.resolve(), repo.resolve()
        log = root / "service-logs" / "dashboard.log"
        if not root.is_dir():
            raise ValueError(f"Campaign directory does not exist: {root}")
        name = _safe_name(session) if session is not None else dashboard_session(root)
        exists = _exists(name)
        if exists and not _owns(name, root):
            digest = hashlib.sha256(os.fsencode(root)).hexdigest()[:10]
            name = f"{name}-{digest}"
            exists = _exists(name)
            if exists and not _owns(name, root):
                raise RuntimeError(f"Dashboard session name is already owned: {name}")

        windows = (
            _tmux("list-windows", "-t", f"={name}", "-F", "#{window_name}").stdout.splitlines()
            if exists
            else []
        )
        dead_pane = None
        if "training" in windows:
            panes = _tmux(
                "list-panes", "-t", f"={name}:training", "-F", "#{pane_id}\t#{pane_dead}"
            ).stdout.splitlines()
            # Do not reinterpret user-added/split panes as the dashboard. tmux's
            # respawn without -k also refuses a pane that became live meanwhile.
            if len(panes) == 1:
                pane, dead = panes[0].split("\t")
                if dead == "1":
                    dead_pane = pane
        created_windows = []
        if "training" not in windows or dead_pane is not None:
            environment = dict(os.environ)
            source_path = str(repo / "src")
            if environment.get("PYTHONPATH"):
                source_path += os.pathsep + environment["PYTHONPATH"]
            environment["PYTHONPATH"] = source_path
            # Validate UI dependencies in the requested interpreter, which may be
            # different from a model backend's isolated training interpreter.
            subprocess.run(
                [
                    str(python),
                    "-c",
                    "import textual; import tensorboard; from segmentary.progress import main",
                ],
                cwd=repo,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
            )
            log.parent.mkdir(parents=True, exist_ok=True)
            command = (
                f"cd {shlex.quote(str(repo))} && "
                f"PYTHONPATH={shlex.quote(source_path)} "
                + shlex.join([str(python), "-m", "segmentary.progress", str(root)])
                # Textual renders to stderr. Both streams must stay attached to
                # the tmux PTY; only a separate exit-status line goes to the log.
                + "; segmentary_dashboard_status=$?; "
                + 'if [ "$segmentary_dashboard_status" -ne 0 ]; then '
                + "printf '%s\\n' "
                + '"Dashboard exited with status $segmentary_dashboard_status; '
                + 'inspect the tmux training pane for details" '
                + f">> {shlex.quote(str(log))}; fi; "
                + 'exit "$segmentary_dashboard_status"'
            )
            if not exists:
                created = _tmux(
                    "new-session",
                    "-d",
                    "-s",
                    name,
                    "-n",
                    "training",
                    "-e",
                    f"{_ROOT_ENV}={root}",
                    command,
                    check=False,
                )
                if created.returncode:
                    # Another launcher can win the atomic tmux session creation.
                    if not (_exists(name) and _owns(name, root)):
                        raise RuntimeError(created.stderr.strip() or "tmux session creation failed")
                    return name
            elif dead_pane is not None:
                _tmux("respawn-pane", "-t", dead_pane, command)
            else:
                _tmux("new-window", "-d", "-t", f"={name}", "-n", "training", command)
            created_windows.append("training")
            _tmux("set-window-option", "-t", f"={name}:training", "remain-on-exit", "on")
        if "gpu-monitor" not in windows:
            _tmux(
                "new-window",
                "-d",
                "-t",
                f"={name}",
                "-n",
                "gpu-monitor",
                "watch -n 2 nvidia-smi",
            )
            created_windows.append("gpu-monitor")
        for window in created_windows:
            pane = _tmux(
                "display-message", "-p", "-t", f"={name}:{window}", "#{pane_id}"
            ).stdout.strip()
            if pane:
                register_cleanup_pane(name, root, pane)
        start_cleanup(root, repo, python, name)
        print(
            f"Campaign dashboard: tmux attach -t {shlex.quote(name)}; errors: {log}",
            file=sys.stderr,
        )
        return name
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        if log is not None:
            try:
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("a") as stream:
                    stream.write(f"Dashboard startup failed: {detail.strip()}\n")
            except OSError:
                pass  # The stderr diagnostic remains available if logging fails.
        print(
            f"Campaign dashboard unavailable; training continues: {detail.strip()}", file=sys.stderr
        )
        return None


def campaign_completed(root: Path) -> bool:
    """Fail closed on missing, partial, failed, or still-collecting evidence."""
    try:
        state = root if (root / "campaign-binding.json").is_file() else root / "state"
        if (state / "campaign-binding.json").is_file():
            status = json.loads((state / "status.json").read_text())
            binding = json.loads((state / "campaign-binding.json").read_text())
            # The status is published only after prediction/evaluation finishes.
            runs = status["runs"]
            return (
                bool(runs)
                and status["status"] == "completed"
                and all(run["status"] == "completed" for run in runs)
                and {run["id"] for run in runs} == {run["id"] for run in binding["spec"]["runs"]}
                and status["campaign_id"] == binding["spec"]["campaign_id"]
            )
        plan = json.loads((root / "plan.json").read_text())
        jobs = plan["jobs"]
        return bool(jobs) and all(
            json.loads((root / "state" / f"{job['name']}.json").read_text())["status"]
            == "completed"
            for job in jobs
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def register_cleanup_pane(session: str, root: Path, pane: str) -> None:
    """Tag only a pane we created, recording its command to detect repurposing."""
    if not _owns(session, root):
        raise RuntimeError("Cannot register a pane in an unrelated dashboard")
    command = _tmux("display-message", "-p", "-t", pane, "#{pane_start_command}").stdout.strip()
    _tmux("set-option", "-p", "-t", pane, "@segmentary_cleanup_root", str(root))
    _tmux("set-option", "-p", "-t", pane, "@segmentary_cleanup_command", command)


def cleanup_dashboard(root: Path, session: str) -> list[str]:
    """Remove registered view panes only; user-added windows/splits survive."""
    if not campaign_completed(root) or not _owns(session, root):
        return []
    panes = _tmux("list-panes", "-s", "-t", f"={session}", "-F", "#{pane_id}").stdout.splitlines()
    removed = []
    for pane in panes:
        owner = _tmux(
            "show-options", "-p", "-v", "-t", pane, "@segmentary_cleanup_root", check=False
        )
        saved = _tmux(
            "show-options", "-p", "-v", "-t", pane, "@segmentary_cleanup_command", check=False
        )
        current = _tmux("display-message", "-p", "-t", pane, "#{pane_start_command}", check=False)
        if (
            owner.returncode
            or saved.returncode
            or current.returncode
            or owner.stdout.strip() != str(root)
            or not saved.stdout.strip()
            or saved.stdout.strip() != current.stdout.strip()
        ):
            continue
        # Never kill the session: it may contain user-added windows or panes.
        if not campaign_completed(root):
            break
        if _tmux("kill-pane", "-t", pane, check=False).returncode == 0:
            removed.append(pane)
    return removed


def start_cleanup(root: Path, repo: Path, python: str | Path, session: str) -> None:
    log = root / "service-logs" / "dashboard-cleanup.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, PYTHONPATH=str(repo / "src"))
    with log.open("a") as stream:
        subprocess.Popen(
            [str(python), "-m", "segmentary.campaign_dashboard", str(root), session],
            cwd=repo,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean up owned dashboard panes after successful completion"
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("session")
    args = parser.parse_args()
    root = args.root.resolve()
    lock = root / "service-logs" / f"dashboard-cleanup-{_safe_name(args.session)}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        while _exists(args.session) and _owns(args.session, root):
            try:
                if campaign_completed(root):
                    print(
                        f"Campaign completed; removed dashboard panes: {cleanup_dashboard(root, args.session)}",
                        flush=True,
                    )
                    return
            except (OSError, subprocess.SubprocessError) as error:
                print(f"Cleanup deferred: {error}", flush=True)
            time.sleep(30)


if __name__ == "__main__":
    main()
