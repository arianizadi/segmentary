"""Canonical RTIS launchers share the medical campaign's optional monitor."""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys

import pytest
from scripts import launch_rtis_full_campaign as full
from scripts import run_rtis_campaign as pilot

from helpers_gpu_policy import make_policy, patch_live, uuid_of, write_campaign
from segmentary import gpu_policy


@pytest.mark.parametrize("opt_out", [False, True])
def test_rtis_pilot_launch_uses_shared_dashboard(tmp_path, monkeypatch, opt_out):
    calls = []
    campaign = write_campaign(tmp_path)
    monkeypatch.setattr(pilot, "verify_frozen", lambda *a: campaign)
    patch_live(monkeypatch)
    monkeypatch.setattr(
        pilot.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "")
    )
    monkeypatch.setattr(
        "segmentary.campaign_dashboard.ensure_dashboard", lambda *a: calls.append(a)
    )
    pilot.launch(tmp_path, tmp_path / "repo", tmp_path / "publisher", [2], dashboard=not opt_out)
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


def _full_fixture(tmp_path, monkeypatch, *, jobs=("a", "b"), smoke=False, compute_apps=()):
    root = tmp_path / "new"
    campaign = write_campaign(root, jobs=jobs, smoke=smoke, dataset="rad_9_24_2026-paul")
    if not smoke:
        (root / "launch-validation.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "code_sha": "code",
                    "gpu_policy_sha256": campaign["gpu_policy_sha256"],
                }
            )
        )
    monkeypatch.setattr(full.runtime, "verify_frozen", lambda *a: campaign)
    monkeypatch.setattr(full.runtime, "git", lambda *a: "code")
    patch_live(monkeypatch, compute_apps)
    sessions = {}
    monkeypatch.setattr(full, "session_exists", lambda name: name in sessions)
    monkeypatch.setattr(
        full.subprocess,
        "run",
        lambda a, **k: sessions.__setitem__(a[4], a[5]) or subprocess.CompletedProcess(a, 0),
    )
    monkeypatch.setattr(full.time, "sleep", lambda s: (root / "STOP_LAUNCHER").touch())
    monkeypatch.setattr("segmentary.campaign_dashboard.ensure_dashboard", lambda *a, **k: None)
    return root, campaign, sessions


def _run(root, *extra):
    sys.argv = ["launcher", "--campaign", str(root), "--no-dashboard", *extra]
    full.main()


@pytest.mark.parametrize("opt_out", [False, True])
def test_rtis_full_launcher_uses_shared_dashboard_after_preflight(tmp_path, monkeypatch, opt_out):
    root, _, _ = _full_fixture(tmp_path, monkeypatch)
    (root / "STOP_LAUNCHER").touch()  # Exercise setup without starting workers.
    calls = []
    monkeypatch.setattr(
        "segmentary.campaign_dashboard.ensure_dashboard", lambda *a, **k: calls.append((a, k))
    )
    arguments = ["launcher", "--campaign", str(root)]
    if opt_out:
        arguments.append("--no-dashboard")
    monkeypatch.setattr(sys, "argv", arguments)
    full.main()
    assert len(calls) == int(not opt_out)
    if calls:
        assert calls[0][0][0] == root
        assert calls[0][1] == {"session": "rtis-fullstats-controller"}


def test_full_launcher_starts_pinned_workers_only_on_allowed_idle_gpus(tmp_path, monkeypatch):
    # GPU 0 busy with someone else's work must not matter; GPU 4 busy must be skipped.
    root, _, sessions = _full_fixture(
        tmp_path, monkeypatch, compute_apps=[(1, uuid_of(0)), (2, uuid_of(4))]
    )
    _run(root, "--hf-home", str(tmp_path / "hf"))
    names = sorted(sessions)
    assert names == [f"rtis-new-gpu-{g}" for g in (2, 3, 5, 6, 7, 8, 9)]
    for name, shell in sessions.items():
        gpu = name.rsplit("-", 1)[1]
        assert f"&& env CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES={gpu} " in shell
        assert f"HF_HOME={tmp_path / 'hf'}" in shell
        assert f"--gpu {gpu} " in shell
    assert not any(name.endswith("publisher") for name in sessions)
    status = full.runtime.read(root / "launcher-status.json")
    assert status["allowed_gpus"] == list(range(2, 10))
    assert status["publisher_started"] is False


def test_full_launcher_requires_matching_preflight_unless_smoke(tmp_path, monkeypatch):
    root, _, sessions = _full_fixture(tmp_path, monkeypatch)
    (root / "launch-validation.json").write_text(
        json.dumps({"passed": True, "code_sha": "code", "gpu_policy_sha256": "stale"})
    )
    with pytest.raises(RuntimeError, match="does not match"):
        _run(root)
    (root / "launch-validation.json").unlink()
    with pytest.raises(RuntimeError, match="validate_rtis_launch"):
        _run(root)
    assert sessions == {}
    root, _, sessions = _full_fixture(tmp_path / "smoke", monkeypatch, smoke=True)
    _run(root)
    assert len(sessions) == 8


def test_full_launcher_takes_over_only_released_previous_gpu_locks(tmp_path, monkeypatch):
    root, _, sessions = _full_fixture(tmp_path, monkeypatch)
    old = tmp_path / "old"
    write_campaign(old, jobs=["x"])
    (old / "state/x.json").write_text(json.dumps({"name": "x", "status": "training"}))
    held = {3, 4}
    original = full.runtime.lock

    def lock(path):
        if path.parent == old / "locks" and path.stem.removeprefix("gpu-") in map(str, held):
            return contextlib.nullcontext(False)
        return original(path)

    monkeypatch.setattr(full.runtime, "lock", lock)
    _run(root, "--previous-campaign", str(old))  # no STOP file in the previous campaign
    assert sorted(sessions) == [f"rtis-new-gpu-{g}" for g in (2, 5, 6, 7, 8, 9)]
    assert not (old / "STOP_PUBLISHER").exists()
    assert full.runtime.read(root / "launcher-status.json")["previous_active"] == 1


def test_full_launcher_refuses_to_chain_while_previous_launcher_runs(tmp_path, monkeypatch):
    """Two launchers could double-book an allowed GPU; the old one must be gone or stopped."""
    root, _, sessions = _full_fixture(tmp_path, monkeypatch)
    old = tmp_path / "old"
    write_campaign(old, jobs=["x"])
    original = full.runtime.lock

    def lock(path):
        if path == old / "locks" / "launcher.lock":
            return contextlib.nullcontext(False)
        return original(path)

    monkeypatch.setattr(full.runtime, "lock", lock)
    with pytest.raises(RuntimeError, match="still running"):
        _run(root, "--previous-campaign", str(old))
    assert sessions == {}
    (old / "STOP").touch()  # A stopped previous launcher starts nothing, so chaining is safe.
    _run(root, "--previous-campaign", str(old))
    assert len(sessions) == 8


def test_full_launcher_restarts_worker_for_orphaned_active_job(tmp_path, monkeypatch):
    """A dead worker session with a job still training must be resumed, not spin forever."""
    root, _, sessions = _full_fixture(tmp_path, monkeypatch, jobs=["a", "b"])
    (root / "state/a.json").write_text(json.dumps({"name": "a", "status": "training", "gpu": 4}))
    (root / "state/b.json").write_text(json.dumps({"name": "b", "status": "completed"}))
    _run(root)
    assert list(sessions) == ["rtis-new-gpu-2"]  # exactly one worker for the one orphan
    status = full.runtime.read(root / "launcher-status.json")
    assert status["orphaned_active"] == ["a"] and status["queued"] == 0
    assert "finished" not in status
    sessions.clear()
    sessions["rtis-new-gpu-4"] = "alive"
    (root / "STOP_LAUNCHER").unlink()
    _run(root)
    assert list(sessions) == ["rtis-new-gpu-4"]  # the live worker's job is not an orphan


def test_full_launcher_hands_off_publisher_only_when_previous_is_drained(tmp_path, monkeypatch):
    root, _, sessions = _full_fixture(tmp_path, monkeypatch)
    old = tmp_path / "old"
    write_campaign(old, jobs=["x", "y"])
    # A worker between jobs: nothing active, but a queued job it will pick up next.
    (old / "state/x.json").write_text(json.dumps({"name": "x", "status": "completed"}))
    _run(root, "--previous-campaign", str(old), "--checkout", str(tmp_path / "pub"))
    assert not (old / "STOP_PUBLISHER").exists()
    assert not any(name.endswith("publisher") for name in sessions)
    (old / "STOP").touch()  # Queued old jobs can no longer start: drained.
    (root / "STOP_LAUNCHER").unlink()
    _run(root, "--previous-campaign", str(old), "--checkout", str(tmp_path / "pub"))
    assert (old / "STOP_PUBLISHER").exists()
    publisher = sessions["rtis-new-publisher"]
    assert "--report-dir docs/results/rad_9_24_2026-paul/live" in publisher


def test_full_launcher_report_dir_is_per_dataset_and_inside_results(tmp_path, monkeypatch):
    root, campaign, sessions = _full_fixture(tmp_path, monkeypatch)
    assert full.report_dir_for(campaign) == full.Path("docs/results/rad_9_24_2026-paul/live")
    assert full.report_dir_for(campaign, "docs/results/other/live") == full.Path(
        "docs/results/other/live"
    )
    for bad in ("/abs/docs/results/x", "docs/results/../x", "docs/other"):
        with pytest.raises(RuntimeError, match="report-dir"):
            full.report_dir_for(campaign, bad)
    _run(root, "--checkout", str(tmp_path / "pub"), "--report-dir", "docs/results/custom/live")
    assert "--report-dir docs/results/custom/live" in sessions["rtis-new-publisher"]


def test_full_launcher_survives_transient_inspection_failure_without_starting_workers(
    tmp_path, monkeypatch
):
    root, _, sessions = _full_fixture(tmp_path, monkeypatch)

    def down():
        raise gpu_policy.GpuInspectionError("Could not list GPU compute processes: timeout")

    monkeypatch.setattr(gpu_policy, "compute_apps", down)
    _run(root)
    assert sessions == {}
    status = full.runtime.read(root / "launcher-status.json")
    assert "timeout" in status["inspection_error"]
    assert "finished" not in status
    # Any other policy error is still fatal.
    monkeypatch.setattr(
        full.runtime,
        "verify_frozen",
        lambda *a: (_ for _ in ()).throw(gpu_policy.GpuPolicyError("x")),
    )
    (root / "STOP_LAUNCHER").unlink()
    with pytest.raises(gpu_policy.GpuPolicyError):
        _run(root)


def test_full_launcher_publisher_only_with_checkout_and_keeps_policy(tmp_path, monkeypatch):
    root, campaign, sessions = _full_fixture(tmp_path, monkeypatch)
    old = tmp_path / "old"
    write_campaign(old, jobs=["x"])
    (old / "state/x.json").write_text(json.dumps({"name": "x", "status": "completed"}))
    full.runtime.write(old / "publisher-status.json", {"commit": "abc"})
    _run(root, "--previous-campaign", str(old))
    assert not (old / "STOP_PUBLISHER").exists()
    assert not any(name.endswith("publisher") for name in sessions)
    (root / "STOP_LAUNCHER").unlink()
    _run(root, "--previous-campaign", str(old), "--checkout", str(tmp_path / "pub"))
    assert (old / "STOP_PUBLISHER").exists()
    publisher = sessions["rtis-new-publisher"]
    assert "&& env CUDA_VISIBLE_DEVICES= " in publisher
    assert "--checkout " + str(tmp_path / "pub") in publisher
    rewritten = full.runtime.read(root / "campaign.json")
    assert rewritten["gpu_policy"] == campaign["gpu_policy"]
    assert rewritten["gpu_policy_sha256"] == campaign["gpu_policy_sha256"]
    assert rewritten["previous_report_commit"] == "abc"
    assert rewritten["previous_campaign"] == str(old)


def test_full_launcher_exits_when_nothing_is_queued_or_active(tmp_path, monkeypatch):
    root, _, sessions = _full_fixture(tmp_path, monkeypatch, jobs=["a"])
    (root / "state/a.json").write_text(json.dumps({"name": "a", "status": "completed"}))
    monkeypatch.setattr(full.time, "sleep", lambda s: pytest.fail("must exit without sleeping"))
    _run(root)
    assert sessions == {}
    assert full.runtime.read(root / "launcher-status.json")["finished"] is True


def test_full_launcher_never_iterates_outside_policy(tmp_path, monkeypatch):
    root, campaign, sessions = _full_fixture(tmp_path, monkeypatch)
    campaign["gpu_policy"] = make_policy([7])
    campaign["gpu_policy_sha256"] = gpu_policy.policy_sha256(campaign["gpu_policy"])
    (root / "launch-validation.json").write_text(
        json.dumps(
            {"passed": True, "code_sha": "code", "gpu_policy_sha256": campaign["gpu_policy_sha256"]}
        )
    )
    _run(root)
    assert list(sessions) == ["rtis-new-gpu-7"]
