"""Paper retries preserve checkpoints and disclose interrupted compute accounting."""

import os
import subprocess

import pytest
from scripts import run_rtis_campaign as runtime
from scripts import run_rtis_full_campaign as full

from helpers_gpu_policy import write_campaign


@pytest.fixture
def stopped_job(tmp_path):
    config = tmp_path / "job.yaml"
    config.write_text("frozen config and seed")
    job = {"name": "job", "config": str(config), "config_sha256": runtime.digest(config), "seed": 1}
    campaign = write_campaign(tmp_path, jobs=["job"], research_protocol={"seeds": [0, 1, 2]})
    runtime.write(
        tmp_path / "state/job.json",
        {"name": "job", "status": "training", "config_sha256": job["config_sha256"]},
    )
    runtime.write(
        tmp_path / "job-attempts/job/0000.json",
        {
            "status": "running",
            "started_at": "2026-01-01T10:00:00+00:00",
            "config_sha256": job["config_sha256"],
            "seed": 1,
        },
    )
    runtime.write(
        tmp_path / "attempts/job/0000-training.json",
        {
            "phase": "training",
            "status": "running",
            "started_at": "2026-01-01T10:00:02+00:00",
            "telemetry": [{"elapsed_seconds": 7.25}],
        },
    )
    return tmp_path, job, campaign


def test_host_interruption_resumes_same_identity_with_observed_lower_bound(stopped_job):
    root, job, campaign = stopped_job
    assert full.recover_paper_job(root, job, campaign)
    state = runtime.read(root / "state/job.json")
    assert state["status"] == "queued"
    assert state["failure"] == full.paper_failure(
        job, 1, "infrastructure", "Interrupted infrastructure attempt"
    )
    worker = runtime.read(root / "job-attempts/job/0000.json")
    phase = runtime.read(root / "attempts/job/0000-training.json")
    assert worker["wall_clock_s"] == worker["duration_lower_bound_s"] == 9.25
    assert phase["wall_clock_s"] == phase["duration_lower_bound_s"] == 7.25
    assert worker["accounting_complete"] is False
    assert worker["missing_tail_seconds"] is None
    assert worker["failure"]["retryable"] is True
    assert full.recover_paper_job(root, job, campaign) is False


def test_recovery_does_not_claim_an_active_job(stopped_job):
    root, job, campaign = stopped_job
    with runtime.lock(root / "locks/job.lock") as claimed:
        assert claimed
        assert full.recover_paper_job(root, job, campaign) is False
    record = runtime.read(root / "job-attempts/job/0000.json")
    record["pid"] = os.getpid()
    runtime.write(root / "job-attempts/job/0000.json", record)
    with pytest.raises(RuntimeError, match="live attempt owner"):
        full.recover_paper_job(root, job, campaign)
    assert runtime.read(root / "job-attempts/job/0000.json")["status"] == "running"


@pytest.mark.parametrize("damage", ["config", "seed"])
def test_recovery_rejects_changed_config_or_seed(stopped_job, damage):
    root, job, campaign = stopped_job
    if damage == "config":
        (root / "job.yaml").write_text("changed")
    else:
        record = runtime.read(root / "job-attempts/job/0000.json")
        record["seed"] = 2
        runtime.write(root / "job-attempts/job/0000.json", record)
    with pytest.raises(RuntimeError, match="frozen run"):
        full.recover_paper_job(root, job, campaign)


def test_infrastructure_retry_budget_is_three_total_attempts(stopped_job):
    root, job, campaign = stopped_job
    for index in range(3):
        runtime.write(
            root / "job-attempts/job" / f"{index:04d}.json",
            {
                "status": "failed",
                "started_at": "2026-01-01T10:00:00+00:00",
                "wall_clock_s": 10,
                "config_sha256": job["config_sha256"],
                "seed": 1,
            },
        )
    state = runtime.read(root / "state/job.json")
    state.update(
        status="failed", failure=full.paper_failure(job, 3, "infrastructure", "host interruption")
    )
    runtime.write(root / "state/job.json", state)
    assert full.recover_paper_job(root, job, campaign) is False
    assert runtime.read(root / "state/job.json")["failure"]["retryable"] is False


def test_nonfinite_loss_is_terminal_and_legacy_recovery_stays_opt_in(stopped_job):
    root, job, campaign = stopped_job
    state = runtime.read(root / "state/job.json")
    state.update(
        status="failed",
        failure=full.paper_failure(job, 1, "nonfinite_training_loss", "NONFINITE_TRAINING_LOSS"),
    )
    runtime.write(root / "state/job.json", state)
    assert full.recover_paper_job(root, job, campaign) is False
    assert full.recover_paper_job(root, job, {}) is False


def test_completed_paper_can_disclose_unknown_compute_tail(stopped_job, monkeypatch):
    root, job, campaign = stopped_job

    def collect(*args):
        runtime.write(
            root / "state/job.json",
            {"name": "job", "status": "collecting", "collection": {"resources": {}}},
        )

    monkeypatch.setattr(full, "collect_job", collect)
    full.run_job(root, root, job, 2, campaign)
    state = runtime.read(root / "state/job.json")
    resources = state["collection"]["resources"]
    assert state["status"] == "completed"
    assert resources["whole_run_accounting_complete"] is False
    assert resources["reserved_gpu_wall_seconds_is_lower_bound"] is True
    assert resources["unknown_missing_tail_seconds"] is None
    assert resources["total_reserved_gpu_wall_seconds"] >= 9.25
    assert len(state["failure_history"]) == 1


@pytest.mark.parametrize("nonfinite", [False, True])
def test_worker_failure_classification_keeps_frozen_identity(stopped_job, monkeypatch, nonfinite):
    root, job, campaign = stopped_job
    # Start with no earlier attempt, so the current failure is attempt one.
    (root / "job-attempts/job/0000.json").unlink()
    (root / "attempts/job/0000-training.json").unlink()
    (root / "logs").mkdir()

    def collect(*args):
        if nonfinite:
            (root / "logs/job.log").write_text("NONFINITE_TRAINING_LOSS")
        raise subprocess.CalledProcessError(1 if nonfinite else -9, ["train"])

    monkeypatch.setattr(full, "collect_job", collect)
    with pytest.raises(subprocess.CalledProcessError):
        full.run_job(root, root, job, 2, campaign)
    state = runtime.read(root / "state/job.json")
    failure = state["failure"]
    assert failure["kind"] == ("nonfinite_training_loss" if nonfinite else "infrastructure")
    assert failure["retryable"] is (not nonfinite)
    assert failure["config_sha256"] == job["config_sha256"]
    assert failure["seed"] == 1
    assert failure["attempt"] == 1
    assert state["failure_history"] == [failure]


def test_collection_accepts_explicit_paper_lower_bounds_only():
    state = {"checkpoints": {"best": {"sha256": "best"}}}
    diagnostics = {
        "test_evaluated": False,
        "standalone_confusion_exact_match": True,
        "results": {
            key: {}
            for key in ("best-auto-train", "best-auto-val", "best-alternate-val", "final-auto-val")
        },
    }
    performance = {
        "status": "complete",
        "source": {"checkpoint_sha256": "best"},
        "model": {"parameter_count": 1},
        "measurements": {"latency": {"fps": 1}, "peak_reserved_bytes": 1},
    }
    attempts = [
        {"phase": phase, "status": "completed", "wall_clock_s": 1}
        for phase in ("training", "diagnostics", "performance")
    ]
    attempts.append(
        {
            "phase": "training",
            "status": "interrupted",
            "wall_clock_s": 0,
            "duration_lower_bound_s": 0,
            "accounting_complete": False,
            "wall_clock_s_is_lower_bound": True,
            "missing_tail_seconds": None,
        }
    )
    with pytest.raises(RuntimeError, match="lower bound"):
        full.validate_collection(state, diagnostics, performance, attempts)
    full.validate_collection(
        state, diagnostics, performance, attempts, allow_interrupted_accounting=True
    )
    attempts[-1]["wall_clock_s_is_lower_bound"] = False
    with pytest.raises(RuntimeError, match="lower bound"):
        full.validate_collection(
            state, diagnostics, performance, attempts, allow_interrupted_accounting=True
        )
