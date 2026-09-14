"""Canonical RTIS launchers share the medical campaign's optional monitor."""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys

import pytest
from scripts import launch_rtis_full_campaign as full
from scripts import run_rtis_campaign as pilot


@pytest.mark.parametrize("opt_out", [False, True])
def test_rtis_pilot_launch_uses_shared_dashboard(tmp_path, monkeypatch, opt_out):
    calls = []
    monkeypatch.setattr(pilot, "verify_frozen", lambda *a: None)
    monkeypatch.setattr(pilot.subprocess, "check_output", lambda *a, **k: "")
    monkeypatch.setattr(
        pilot.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "")
    )
    monkeypatch.setattr(
        "segmentary.campaign_dashboard.ensure_dashboard", lambda *a: calls.append(a)
    )
    pilot.launch(tmp_path, tmp_path / "repo", tmp_path / "publisher", [0], dashboard=not opt_out)
    assert len(calls) == int(not opt_out)
    if calls:
        assert calls[0] == (tmp_path, tmp_path / "repo", sys.executable)


@pytest.mark.parametrize("opt_out", [False, True])
def test_rtis_pilot_cli_preserves_monitor_opt_out(tmp_path, monkeypatch, opt_out):
    flags = []
    monkeypatch.setattr(pilot, "launch", lambda *a, **k: flags.append(k["dashboard"]))
    arguments = ["runner", "launch", "--campaign", str(tmp_path)]
    if opt_out:
        arguments.append("--no-dashboard")
    monkeypatch.setattr(sys, "argv", arguments)
    pilot.main()
    assert flags == [not opt_out]


@pytest.mark.parametrize("opt_out", [False, True])
def test_rtis_full_launcher_uses_shared_dashboard_after_preflight(tmp_path, monkeypatch, opt_out):
    root, old = tmp_path / "new", tmp_path / "old"
    root.mkdir()
    old.mkdir()
    (old / "STOP").touch()
    (root / "STOP_LAUNCHER").touch()  # Exercise setup without starting workers.
    (root / "launch-validation.json").write_text(json.dumps({"passed": True, "code_sha": "code"}))
    calls = []
    monkeypatch.setattr(full.runtime, "verify_frozen", lambda *a: None)
    monkeypatch.setattr(full.runtime, "git", lambda *a: "code")
    monkeypatch.setattr(full.runtime, "lock", lambda *a: contextlib.nullcontext(True))
    monkeypatch.setattr(
        "segmentary.campaign_dashboard.ensure_dashboard", lambda *a, **k: calls.append((a, k))
    )
    arguments = [
        "launcher",
        "--campaign",
        str(root),
        "--previous-campaign",
        str(old),
        "--checkout",
        str(tmp_path / "publisher"),
    ]
    if opt_out:
        arguments.append("--no-dashboard")
    monkeypatch.setattr(sys, "argv", arguments)
    full.main()
    assert len(calls) == int(not opt_out)
    if calls:
        assert calls[0][0][0] == root
        assert calls[0][1] == {"session": "rtis-fullstats-controller"}
