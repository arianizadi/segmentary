"""Best-effort, read-only dashboard launch shared by campaign schedulers."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import sys
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
