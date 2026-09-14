import json
import subprocess

import pytest

from segmentary import campaign_dashboard as dashboard


def medical(root, status="completed", runs=None):
    state = root / "state"
    state.mkdir(exist_ok=True)
    (state / "campaign-binding.json").write_text(
        json.dumps({"spec": {"campaign_id": "c", "runs": [{"id": "a"}, {"id": "b"}]}})
    )
    (state / "status.json").write_text(
        json.dumps(
            {
                "campaign_id": "c",
                "status": status,
                "runs": runs
                if runs is not None
                else [{"id": "a", "status": "completed"}, {"id": "b", "status": "completed"}],
            }
        )
    )


@pytest.mark.parametrize("status", ["running", "failed", "interrupted", "prepared"])
def test_medical_non_success_stays_open(tmp_path, status):
    medical(tmp_path, status)
    assert not dashboard.campaign_completed(tmp_path)


def test_medical_requires_every_declared_job_and_readable_state(tmp_path):
    medical(tmp_path)
    assert dashboard.campaign_completed(tmp_path)
    assert dashboard.campaign_completed(tmp_path / "state")
    medical(tmp_path, runs=[{"id": "a", "status": "completed"}])
    assert not dashboard.campaign_completed(tmp_path)
    (tmp_path / "state/status.json").write_text("{")
    assert not dashboard.campaign_completed(tmp_path)


def test_rtis_waits_for_all_planned_jobs_including_collection(tmp_path):
    (tmp_path / "plan.json").write_text(json.dumps({"jobs": [{"name": "a"}, {"name": "b"}]}))
    (tmp_path / "state").mkdir()
    (tmp_path / "state/a.json").write_text('{"status":"completed"}')
    assert not dashboard.campaign_completed(tmp_path)
    for status in ["queued", "training", "evaluating", "collecting", "failed"]:
        (tmp_path / "state/b.json").write_text(json.dumps({"status": status}))
        assert not dashboard.campaign_completed(tmp_path)
    (tmp_path / "state/b.json").write_text('{"status":"completed"}')
    assert dashboard.campaign_completed(tmp_path)


def test_cleanup_preserves_user_panes_and_repurposed_panes(tmp_path, monkeypatch):
    medical(tmp_path)
    monkeypatch.setattr(dashboard, "_owns", lambda *args: True)
    calls = []

    def tmux(*args, check=True):
        calls.append(args)
        output = ""
        if args[0] == "list-panes":
            output = "%1\n%2\n%3\n%4\n"
        else:
            pane = args[args.index("-t") + 1]
            if args[-1] == "@segmentary_cleanup_root":
                output = str(tmp_path) if pane != "%3" else ""
            elif args[-1] == "@segmentary_cleanup_command":
                output = "watch gpu" if pane == "%2" else "dashboard"
            elif args[-1] == "#{pane_start_command}":
                output = (
                    "user shell" if pane == "%4" else "watch gpu" if pane == "%2" else "dashboard"
                )
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr(dashboard, "_tmux", tmux)
    assert dashboard.cleanup_dashboard(tmp_path, "view") == ["%1", "%2"]
    assert [c for c in calls if c[0].startswith("kill")] == [
        ("kill-pane", "-t", "%1"),
        ("kill-pane", "-t", "%2"),
    ]
    monkeypatch.setattr(dashboard, "_owns", lambda *args: False)
    assert dashboard.cleanup_dashboard(tmp_path, "view") == []


def test_empty_campaign_is_not_complete(tmp_path):
    assert not dashboard.campaign_completed(tmp_path)
    (tmp_path / "plan.json").write_text('{"jobs":[]}')
    assert not dashboard.campaign_completed(tmp_path)
