"""Real-Git contracts for publishing reports separately from frozen training."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = importlib.util.spec_from_file_location(
    "medical_publisher", ROOT / "scripts/publish_medical_campaign.py"
)
assert MODULE and MODULE.loader
publisher = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(publisher)


@pytest.fixture
def repository(tmp_path, monkeypatch):
    git = publisher.git
    remote, author, checkout = [tmp_path / name for name in ("origin.git", "author", "publisher")]
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(author))
    git(author, "checkout", "-b", "main")
    git(author, "config", "user.name", "Test")
    git(author, "config", "user.email", "test@example.invalid")
    (author / "README.md").write_text("Original source\n")
    git(author, "add", ".")
    git(author, "commit", "-m", "Initial")
    git(author, "push", "origin", "main")
    git(tmp_path, "clone", "--branch", "main", str(remote), str(checkout))
    git(checkout, "config", "user.name", "Test")
    git(checkout, "config", "user.email", "test@example.invalid")
    campaign = tmp_path / "campaign.json"
    publisher.write_json(
        campaign, {"source_root": str(author), "campaign_id": "example", "runs": [{"id": "one"}]}
    )
    state = tmp_path / "state"
    publisher.write_json(state / "runs/one.json", {"status": "running"})
    snapshot = {"generated_at": "old", "status_counts": {"running": 1}, "runs": [{"live_step": 2}]}
    monkeypatch.setattr(publisher.reports, "collect", lambda *args: snapshot)
    monkeypatch.setattr(publisher.reports, "render", lambda data: {"README.md": json.dumps(data)})
    return campaign, state, checkout, author, snapshot


def test_publish_is_scoped_unchanged_snapshot_does_not_commit_and_final_exits(repository):
    campaign, state, checkout, author, snapshot = repository
    first = publisher.publish_once(campaign, state, checkout, "docs/results/pancreas")
    assert first["meaningful_change"] and not first["terminal"]
    snapshot["generated_at"] = "later"
    second = publisher.publish_once(campaign, state, checkout, "docs/results/pancreas")
    assert second["commit"] == first["commit"]
    assert not second["meaningful_change"]
    publisher.git(author, "pull", "--ff-only", "origin", "main")
    (author / "README.md").write_text("Other researcher changed source\n")
    publisher.git(author, "commit", "-am", "Source improvement")
    publisher.git(author, "push", "origin", "main")
    snapshot["runs"][0]["live_step"] = 3
    publisher.write_json(state / "runs/one.json", {"status": "completed"})
    last = publisher.publish_once(campaign, state, checkout, "docs/results/pancreas")
    assert last["terminal"]
    assert (checkout / "README.md").read_text() == "Other researcher changed source\n"
    assert publisher.git(checkout, "rev-parse", "HEAD") == publisher.git(
        checkout, "rev-parse", "origin/main"
    )


def test_unrelated_dirty_files_and_frozen_checkout_are_preserved(repository):
    campaign, state, checkout, author, _ = repository
    (checkout / "README.md").write_text("Uncommitted user change")
    with pytest.raises(RuntimeError, match="unrelated edits"):
        publisher.publish_once(campaign, state, checkout, "docs/results/pancreas")
    assert (checkout / "README.md").read_text() == "Uncommitted user change"
    with pytest.raises(ValueError, match="separate checkout"):
        publisher.publish_once(campaign, state, author, "docs/results/pancreas")


@pytest.mark.parametrize(
    "relative", ["../elsewhere", "/tmp/elsewhere", "docs/results/../../source", ".git/data", "docs"]
)
def test_report_path_cannot_escape_checkout(tmp_path, relative):
    with pytest.raises(ValueError):
        publisher.report_path(tmp_path, relative)


def test_symlink_escape_rejected(tmp_path):
    checkout = tmp_path / "checkout"
    (checkout / "docs/results").mkdir(parents=True)
    (checkout / "docs/results/pancreas").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        publisher.report_path(checkout, "docs/results/pancreas")


def test_failed_push_is_bounded_and_unpublished_commit_recovers(repository, monkeypatch):
    campaign, state, checkout, _, _ = repository
    original = publisher.git
    attempts = []

    def broken(repo, *args):
        if args[0] == "push":
            attempts.append(args)
            raise RuntimeError("Simulated network outage")
        return original(repo, *args)

    monkeypatch.setattr(publisher, "git", broken)
    with pytest.raises(RuntimeError, match="network outage"):
        publisher.publish_once(campaign, state, checkout, "docs/results/pancreas")
    assert len(attempts) == 2
    assert original(checkout, "rev-list", "origin/main..HEAD")
    monkeypatch.setattr(publisher, "git", original)
    result = publisher.publish_once(campaign, state, checkout, "docs/results/pancreas")
    assert result["commit"] == original(checkout, "rev-parse", "origin/main")


def test_unrelated_unpublished_commit_is_not_pushed(repository):
    campaign, state, checkout, _, _ = repository
    (checkout / "README.md").write_text("Local source change")
    publisher.git(checkout, "commit", "-am", "Unrelated source work")
    with pytest.raises(RuntimeError, match="Unpublished commits"):
        publisher.publish_once(campaign, state, checkout, "docs/results/pancreas")
    assert (checkout / "README.md").read_text() == "Local source change"


def test_push_race_rebases_only_generated_commit_once(repository, monkeypatch):
    campaign, state, checkout, author, _ = repository
    original = publisher.git
    pushed = []

    def racing(repo, *args):
        if repo == checkout and args[0] == "push":
            pushed.append(args)
            if len(pushed) == 1:
                (author / "README.md").write_text("Concurrent source commit")
                original(author, "commit", "-am", "Concurrent author edit")
                original(author, "push", "origin", "main")
        return original(repo, *args)

    monkeypatch.setattr(publisher, "git", racing)
    publisher.publish_once(campaign, state, checkout, "docs/results/pancreas")
    assert len(pushed) == 2
    assert (checkout / "README.md").read_text() == "Concurrent source commit"
    assert original(checkout, "rev-parse", "HEAD") == original(checkout, "rev-parse", "origin/main")


def test_completion_during_publication_requires_another_final_snapshot(repository, monkeypatch):
    campaign, state, checkout, _, _ = repository
    original = publisher.reports.render

    def completing(snapshot):
        publisher.write_json(state / "runs/one.json", {"status": "completed"})
        return original(snapshot)

    monkeypatch.setattr(publisher.reports, "render", completing)
    result = publisher.publish_once(campaign, state, checkout, "docs/results/pancreas")
    assert not result["terminal"]
