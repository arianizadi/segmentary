"""Shared monitoring startup never disturbs workers or an unrelated tmux session."""

from __future__ import annotations

import subprocess

import pytest

from segmentary import campaign_dashboard as dashboard


class Tmux:
    def __init__(self):
        self.sessions = {}
        self.calls = []
        self.dead = False

    def __call__(self, *arguments, check=True):
        self.calls.append(arguments)
        action = arguments[0]
        output, code = "", 0
        target = arguments[arguments.index("-t") + 1].lstrip("=") if "-t" in arguments else None
        session = self.sessions.get(target)
        if action == "has-session":
            code = 0 if target in self.sessions else 1
        elif action == "show-environment":
            output = f"SEGMENTARY_DASHBOARD_ROOT={session['root']}\n"
        elif action == "list-windows":
            output = "\n".join(session["windows"])
        elif action == "list-panes":
            output = f"%10\t{int(self.dead)}\n"
        elif action == "new-session":
            name = arguments[arguments.index("-s") + 1]
            root = arguments[arguments.index("-e") + 1].split("=", 1)[1]
            self.sessions[name] = {"root": root, "windows": ["training"]}
        elif action == "new-window":
            session["windows"].append(arguments[arguments.index("-n") + 1])
        elif action == "respawn-pane":
            assert target == "%10"
            assert "-k" not in arguments
            assert self.dead
            self.dead = False
        return subprocess.CompletedProcess(arguments, code, output, "")


@pytest.fixture
def tmux(monkeypatch):
    fake = Tmux()
    monkeypatch.setattr(dashboard, "_tmux", fake)
    monkeypatch.setattr(
        dashboard.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "")
    )
    return fake


def test_dashboard_is_idempotent_uses_shared_entrypoint_and_quotes_paths(tmp_path, tmux):
    root = tmp_path / "campaign $(touch unintended)"
    root.mkdir()
    session = dashboard.ensure_dashboard(root, tmp_path, "/some python", session="my.dashboard")
    assert session == "my-dashboard"
    assert (
        dashboard.ensure_dashboard(root, tmp_path, "/some python", session="my.dashboard")
        == session
    )
    starts = [call for call in tmux.calls if call[0] == "new-session"]
    assert len(starts) == 1
    assert "segmentary.progress" in starts[0][-1]
    ui_command, exit_logger = starts[0][-1].split("; segmentary_dashboard_status=$?", 1)
    assert ">" not in ui_command  # Textual requires stderr and stdout on the PTY.
    assert "2>" not in exit_logger
    assert "Dashboard exited with status" in exit_logger
    assert "'/some python'" in starts[0][-1]
    assert f"'{root}'" in starts[0][-1]
    assert not [call for call in tmux.calls if "kill" in call[0] or call[0] == "respawn-pane"]
    assert tmux.sessions[session]["windows"] == ["training", "gpu-monitor"]


def test_existing_foreign_session_is_untouched_and_collision_name_is_stable(tmp_path, tmux):
    tmux.sessions["controller"] = {"root": "/other-campaign", "windows": ["training"]}
    first = dashboard.ensure_dashboard(tmp_path, tmp_path, "python", session="controller")
    second = dashboard.ensure_dashboard(tmp_path, tmp_path, "python", session="controller")
    assert first == second
    assert first.startswith("controller-")
    assert tmux.sessions["controller"] == {"root": "/other-campaign", "windows": ["training"]}
    for call in tmux.calls:
        if "=controller" in call:
            assert call[0] in {"has-session", "show-environment"}


def test_root_hash_distinguishes_same_basename_and_sanitizes_name(tmp_path):
    one = dashboard.dashboard_session(tmp_path / "one" / "same: name")
    two = dashboard.dashboard_session(tmp_path / "two" / "same: name")
    assert one != two
    assert one.startswith("same-name-controller-")
    assert one == dashboard.dashboard_session(tmp_path / "one" / "same: name")


def test_missing_tmux_is_nonfatal_and_reports_problem(tmp_path, monkeypatch, capsys):
    def missing(*args, **kwargs):
        raise FileNotFoundError("tmux was not found")

    monkeypatch.setattr(dashboard, "_tmux", missing)
    assert dashboard.ensure_dashboard(tmp_path, tmp_path, "python") is None
    assert "training continues: tmux was not found" in capsys.readouterr().err
    assert "tmux was not found" in (tmp_path / "service-logs/dashboard.log").read_text()


def test_missing_dashboard_dependencies_are_nonfatal_and_show_stderr(
    tmp_path, tmux, monkeypatch, capsys
):
    def missing(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args, stderr="ModuleNotFoundError: textual")

    monkeypatch.setattr(dashboard.subprocess, "run", missing)
    assert dashboard.ensure_dashboard(tmp_path, tmp_path, "python") is None
    assert "ModuleNotFoundError: textual" in capsys.readouterr().err
    assert not [call for call in tmux.calls if call[0] == "new-session"]


def test_only_owned_dead_dashboard_pane_is_restarted(tmp_path, tmux):
    session = dashboard.ensure_dashboard(tmp_path, tmp_path, "python")
    tmux.dead = True
    assert dashboard.ensure_dashboard(tmp_path, tmp_path, "python") == session
    restarts = [call for call in tmux.calls if call[0] == "respawn-pane"]
    assert len(restarts) == 1
    assert restarts[0][1:3] == ("-t", "%10")
    assert "-k" not in restarts[0]
    assert not tmux.dead
    dashboard.ensure_dashboard(tmp_path, tmp_path, "python")
    assert len([call for call in tmux.calls if call[0] == "respawn-pane"]) == 1
