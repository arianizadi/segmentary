"""The live dashboard remains read-only, useful, and robust to partial state."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from rich.console import Console

from segmentary import progress


def _job(
    campaign: Path,
    curriculum: str,
    seed: int,
    status: str,
    started: datetime | None = None,
    finished: datetime | None = None,
) -> dict:
    run_dir = campaign / f"{curriculum}_seed{seed}"
    return {
        "curriculum": curriculum,
        "seed": seed,
        "status": status,
        "run_dir": str(run_dir),
        "common_results": str(run_dir / "common_railsem19" / "results.json"),
        "started_at": started.isoformat() if started else None,
        "finished_at": finished.isoformat() if finished else None,
        "failure": None,
    }


def _write_status(campaign: Path, lane: str, jobs: list[dict]) -> None:
    campaign.mkdir(parents=True, exist_ok=True)
    (campaign / f"lane_{lane}_status.json").write_text(
        json.dumps(
            {
                "lane": lane,
                "status": "running",
                "gpu_visibility": "0,1,2,3" if lane == "a" else "4,5,6,7",
                "failure": None,
                "tmux_session": f"recorded-{lane}",
                "jobs": jobs,
            }
        ),
        encoding="utf-8",
    )


def _write_stage(
    run_dir: Path,
    name: str = "railsem19",
    iters: int = 40_000,
    *,
    package_tag: str = "segmentary",
) -> Path:
    version = run_dir / name / "lightning_logs" / "version_0"
    version.mkdir(parents=True)
    event = version / "events.out.tfevents.fixture"
    event.touch()
    (version / "hparams.yaml").write_text(
        f"train_cfg: !!python/object:{package_tag}.config.TrainConfig\n  iters: {iters}\n",
        encoding="utf-8",
    )
    return event


def _write_current_tensorboard_stage(
    run_dir: Path,
    name: str = "railsem19",
    iters: int = 40_000,
) -> Path:
    log_dir = run_dir / name / "tensorboard"
    log_dir.mkdir(parents=True)
    event = log_dir / "events.out.tfevents.fixture"
    event.touch()
    (log_dir / "hparams.yaml").write_text(
        f"train_cfg: !!python/object:segmentary.config.TrainConfig\n  iters: {iters}\n",
        encoding="utf-8",
    )
    return event


def test_read_total_steps_accepts_pre_rename_lightning_hparams(tmp_path: Path) -> None:
    legacy_package = "rail" + "yard"
    event = _write_stage(tmp_path / "run", iters=123, package_tag=legacy_package)
    assert progress._read_total_steps(progress._stage_dir(event)) == 123


def test_read_total_steps_accepts_stable_tensorboard_directory(tmp_path: Path) -> None:
    event = _write_current_tensorboard_stage(tmp_path / "run", iters=456)
    stage = progress._stage_dir(event)
    assert stage == tmp_path / "run" / "railsem19"
    assert progress._read_total_steps(stage) == 456


def test_inspect_campaign_uses_live_scalars_without_loading_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    now = datetime(2026, 8, 12, 20, tzinfo=UTC)
    complete = _job(
        campaign,
        "rs_only",
        0,
        "succeeded",
        now - timedelta(hours=4),
        now - timedelta(minutes=30),
    )
    active = _job(campaign, "rs_only", 1, "training", now - timedelta(hours=1))
    pending = _job(campaign, "rs_only", 2, "pending")
    _write_status(campaign, "a", [complete, active, pending])
    _write_stage(Path(active["run_dir"]))

    points = [
        progress.ScalarPoint(7_999, 0.7, now.timestamp() - 1_400),
        progress.ScalarPoint(11_999, 0.4, now.timestamp() - 100),
    ]
    monkeypatch.setattr(
        progress,
        "_load_event_scalars",
        lambda _path: {
            "train/loss": points,
            "train/lr": [progress.ScalarPoint(11_999, 4e-5, now.timestamp() - 100)],
            "val/miou": [progress.ScalarPoint(11_999, 0.681, now.timestamp() - 120)],
            "val/boundary_f1": [progress.ScalarPoint(11_999, 0.757, now.timestamp() - 120)],
        },
    )

    snapshots = progress.inspect_campaign(campaign, now=now)
    assert len(snapshots) == 1
    lane = snapshots[0]
    assert lane.completed == 1
    assert lane.active_job is active or lane.active_job == active
    assert lane.stage is not None
    assert lane.stage.name == "railsem19"
    assert lane.stage.step == 12_000
    assert lane.stage.total_steps == 40_000
    assert lane.stage.rate == pytest.approx(4_000 / 1_300)
    assert lane.stage.eta_seconds == pytest.approx(28_000 / lane.stage.rate)
    assert lane.lane_eta_seconds is not None
    assert not lane.warnings


def test_render_is_plain_language_and_labels_validation_cadence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "pretty_campaign"
    now = datetime.now(UTC)
    complete = _job(
        campaign,
        "cs_only",
        0,
        "succeeded",
        now - timedelta(hours=3),
        now - timedelta(minutes=10),
    )
    result = Path(complete["common_results"])
    result.parent.mkdir(parents=True)
    result.write_text(json.dumps({"metrics": {"miou": 0.2975}}), encoding="utf-8")
    active = _job(campaign, "rs_only", 1, "training", now - timedelta(hours=1))
    _write_status(campaign, "a", [complete, active])
    _write_stage(Path(active["run_dir"]))
    monkeypatch.setattr(
        progress,
        "_load_event_scalars",
        lambda _path: {
            "train/loss": [
                progress.ScalarPoint(7_999, 0.5, now.timestamp() - 1_400),
                progress.ScalarPoint(11_999, 0.4, now.timestamp() - 100),
            ],
            "train/lr": [progress.ScalarPoint(11_999, 4e-5, now.timestamp() - 100)],
            "val/miou": [progress.ScalarPoint(7_999, 0.681, now.timestamp() - 500)],
            "val/macc": [progress.ScalarPoint(7_999, 0.809, now.timestamp() - 500)],
            "val/pixel_acc": [progress.ScalarPoint(7_999, 0.891, now.timestamp() - 500)],
            "val/boundary_f1": [progress.ScalarPoint(7_999, 0.757, now.timestamp() - 500)],
        },
    )
    monkeypatch.setattr(progress, "_tmux_alive", lambda *_args: True)
    monkeypatch.setattr(progress, "_gpu_rows", lambda *_args: [])
    snapshots = progress.inspect_campaign(campaign, now=now)
    output = io.StringIO()
    console = Console(file=output, width=140, color_system=None)
    console.print(
        progress.render_dashboard(
            campaign, snapshots, ZoneInfo("America/Los_Angeles"), "segmentary-m5", False
        )
    )
    shown = output.getvalue()
    assert "SEGMENTARY" in shown
    assert "pretty_campaign" in shown
    assert "12,000/40,000" in shown
    assert "VAL mIoU" in shown
    assert "68.10% @8,000" in shown
    assert "Validated mIoU: cs_only s0 29.75%" in shown
    assert "expected finish" in shown
    assert "read-only view" in shown


def test_render_labels_tensorboard_validation_step_zero_as_first_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TensorBoard uses zero-based step labels; the dashboard uses human counts."""
    monkeypatch.setattr(progress, "_tmux_alive", lambda *_args: None)
    stage = progress.StageSnapshot(
        name="cityscapes",
        path=tmp_path,
        step=1,
        total_steps=10,
        scalars={
            "val/miou": progress.ScalarPoint(
                step=0,
                value=0.25,
                wall_time=datetime.now(UTC).timestamp(),
            )
        },
    )
    job = _job(tmp_path, "cs_only", 0, "training", datetime.now(UTC))
    snapshot = progress.LaneSnapshot(
        lane="a",
        record={"lane": "a", "status": "running", "jobs": [job]},
        active_job=job,
        stage=stage,
        completed=0,
        lane_eta_seconds=None,
        warnings=[],
    )
    output = io.StringIO()
    Console(file=output, width=140, color_system=None).print(
        progress.render_dashboard(
            tmp_path,
            [snapshot],
            ZoneInfo("UTC"),
            "segmentary-m5",
            False,
        )
    )
    assert "25.00% @1" in output.getvalue()


def test_partial_tensorboard_file_is_a_warning_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    active = _job(campaign, "rs_only", 1, "training", datetime.now(UTC))
    _write_status(campaign, "a", [active])
    _write_stage(Path(active["run_dir"]))
    monkeypatch.setattr(
        progress,
        "_load_event_scalars",
        lambda _path: (_ for _ in ()).throw(ValueError("partial record")),
    )
    snapshot = progress.inspect_campaign(campaign)[0]
    assert snapshot.stage is not None
    assert snapshot.stage.step is None
    assert any("refresh deferred" in warning for warning in snapshot.warnings)


@pytest.mark.parametrize(
    "status",
    ["benchmarking", "performance_failed", "performance_artifact_failed"],
)
def test_performance_statuses_are_visible(status: str) -> None:
    assert (status in progress.ACTIVE_STATUSES) is (status == "benchmarking")
    assert (status in progress.FAILED_STATUSES) is (status != "benchmarking")


def test_lane_panel_uses_recorded_tmux_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(progress, "_tmux_alive", lambda session: seen.append(session) or True)
    snapshot = progress.LaneSnapshot(
        lane="gpu9",
        record={
            "lane": "gpu9",
            "tmux_session": "segmentary-cityrail-gpu9",
            "status": "running",
            "jobs": [],
        },
        active_job=None,
        stage=None,
        completed=0,
        lane_eta_seconds=None,
        warnings=[],
    )
    progress._lane_cells(
        snapshot,
        "wrong-prefix",
        {},
        datetime.now(UTC),
        {"job": 32, "queue": 11, "miou": 14},
    )
    assert seen == ["segmentary-cityrail-gpu9"]


def test_missing_campaign_and_bad_refresh_fail_cleanly(tmp_path: Path, capsys) -> None:
    assert progress.main([str(tmp_path / "missing"), "--once"]) == 2
    assert "campaign directory not found" in capsys.readouterr().err

    campaign = tmp_path / "campaign"
    campaign.mkdir()
    assert progress.main([str(campaign), "--once", "--refresh", "0"]) == 2
    assert (
        f"--refresh must be at least {progress.MINIMUM_REFRESH} seconds" in capsys.readouterr().err
    )


def test_eta_is_withheld_until_every_remaining_curriculum_has_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    now = datetime.now(UTC)
    completed = _job(
        campaign,
        "rs_only",
        0,
        "succeeded",
        now - timedelta(hours=4),
        now - timedelta(minutes=30),
    )
    active = _job(campaign, "rs_only", 1, "training", now - timedelta(hours=1))
    unknown = _job(campaign, "never_completed", 0, "pending")
    _write_status(campaign, "a", [completed, active, unknown])
    _write_stage(Path(active["run_dir"]))
    monkeypatch.setattr(
        progress,
        "_load_event_scalars",
        lambda _paths: {
            "train/loss": [
                progress.ScalarPoint(0, 1.0, now.timestamp() - 100),
                progress.ScalarPoint(100, 0.9, now.timestamp()),
            ]
        },
    )
    assert progress.inspect_campaign(campaign, now=now)[0].lane_eta_seconds is None


def test_campaign_eta_is_withheld_when_any_lane_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(progress, "_tmux_alive", lambda *_args: None)
    known = progress.LaneSnapshot(
        lane="a",
        record={"lane": "a", "status": "running", "jobs": []},
        active_job=None,
        stage=None,
        completed=0,
        lane_eta_seconds=600,
        warnings=[],
    )
    unknown = progress.LaneSnapshot(
        lane="b",
        record={"lane": "b", "status": "running", "jobs": []},
        active_job=None,
        stage=None,
        completed=0,
        lane_eta_seconds=None,
        warnings=[],
    )
    output = io.StringIO()
    Console(file=output, width=120, color_system=None).print(
        progress.render_dashboard(
            tmp_path, [known, unknown], ZoneInfo("UTC"), "segmentary-m5", False
        )
    )
    assert "expected finish estimating" in output.getvalue()


@pytest.mark.parametrize("payload", ["{broken", json.dumps({"jobs": None})])
def test_malformed_status_is_visible_instead_of_crashing(tmp_path: Path, payload: str) -> None:
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "lane_a_status.json").write_text(payload, encoding="utf-8")
    snapshots = progress.inspect_campaign(campaign)
    assert len(snapshots) == 1
    assert snapshots[0].warnings
    assert snapshots[0].completed == 0


def test_missing_run_dir_does_not_scan_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    active = _job(campaign, "rs_only", 1, "training", datetime.now(UTC))
    active["run_dir"] = ""
    _write_status(campaign, "a", [active])
    monkeypatch.setattr(
        progress,
        "_event_files",
        lambda _path: pytest.fail("empty run_dir scanned the working directory"),
    )
    snapshot = progress.inspect_campaign(campaign)[0]
    assert snapshot.stage is None
    assert any("missing non-empty run_dir" in warning for warning in snapshot.warnings)
