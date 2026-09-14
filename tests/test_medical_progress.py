"""Shared medical progress UI must observe training without inventing metrics."""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from textual.widgets import DataTable

from segmentary.campaign_progress import CampaignProgress, visible
from segmentary.medical_progress import (
    MedicalProgress,
    MedicalTelemetry,
    parse_nnunet,
    score_display,
)
from segmentary.progress import detect_backend, main
from segmentary.rtis_progress import RTISProgress
from segmentary.training_curve import TrainingCurve


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def medical(tmp_path, monkeypatch):
    monkeypatch.setattr("segmentary.medical_progress.alive", lambda *args: True)
    now = time.time()
    splits = tmp_path / "splits.json"
    write(
        splits,
        {"train": ["train-case"], "val": ["case-one", "case-two"], "test": ["reserved-case"]},
    )
    spec = {
        "schema_version": 1,
        "campaign_id": "medical-test",
        "source_commit": "frozen-source",
        "manifest": str(tmp_path / "never-read-manifest.json"),
        "splits": str(splits),
        "gpus": ["0", "1"],
        "runs": [],
        "protocol": {
            "nnunet": {"expected_default_epochs": 1000, "expected_default_updates_per_epoch": 250}
        },
    }
    for index, (name, status, backend) in enumerate(
        (
            ("active", "running", "torch"),
            ("finished", "completed", "torch"),
            ("waiting", "queued", "torch"),
            ("nnunet", "running", "nnunet"),
        )
    ):
        workspace = tmp_path / "runs" / name
        config = tmp_path / "recipes" / f"{name}.json"
        write(
            config,
            {
                "backend": backend,
                "model": name,
                "workspace": str(workspace),
                "epochs": 2,
                "steps_per_epoch": 100,
                "initialization": "scratch",
            },
        )
        spec["runs"].append({"id": name, "model": name, "backend": backend, "config": str(config)})
        write(
            tmp_path / "state/runs" / f"{name}.json",
            {
                "id": name,
                "status": status,
                "stage": "train" if status == "running" else None,
                "workspace": str(workspace),
                "config": str(config),
                "gpu": str(index),
                "started_at": "2026-09-14T00:00:00+00:00",
                "updated_at": "2026-09-14T00:00:00+00:00",
                "cli_pid": 123,
            },
        )
        if name == "active":
            write(
                workspace / "metrics/epoch-00001.json",
                {
                    "epoch": 1,
                    "step": 100,
                    "loss": 1.4,
                    "learning_rate": 0.001,
                    "validation": {
                        "space": "native_full_volume",
                        "mean_mass_dice": 0.3,
                        "mean_pancreas_dice": 0.8,
                        "cases": [{"case_id": "case-one"}, {"case_id": "case-two"}],
                    },
                },
            )
            write(
                workspace / "progress.json",
                {"phase": "train", "step": 150, "loss": 1.0, "updated_at": now},
            )
        if name == "nnunet":
            path = workspace / "nnUNet_results/fold_0/training_log_test.txt"
            path.parent.mkdir(parents=True)
            path.write_text(
                "Epoch 0\ntrain_loss -0.5\nPseudo dice [np.float32(0.71), np.float32(0.42)]\nEpoch time: 160.5 s\nEpoch 1\n"
            )
    write(tmp_path / "campaign.json", spec)
    write(tmp_path / "state/status.json", {"status": "running", "pid": 123, "updated_at": now})
    write(tmp_path / "state/publisher-status.json", {"last_success": now})
    return tmp_path


def test_telemetry_uses_complete_native_metrics_and_keeps_pseudo_separate(medical):
    telemetry = MedicalTelemetry(medical, show_gpus=False)
    rows, gpus, errors = telemetry.read()
    assert not errors and not gpus
    assert len(rows) == 4
    by_name = {row["name"]: row for row in rows}
    assert score_display(by_name["active"]) == (0.3, 0.8, "native", 100, "2/2")
    assert by_name["active"]["step"] == 150
    assert score_display(by_name["waiting"]) == (None, None, "pending", None, "—")
    assert score_display(by_name["nnunet"]) == (None, None, "pending", None, "—")
    assert by_name["nnunet"]["scalars"]["pseudo/mass_dice"].value == 0.42
    assert not by_name["nnunet"]["history"].get("val/mass_dice")
    assert by_name["nnunet"]["progress_text"] == "1/1000 ep"
    assert "PATCH" in telemetry.summary
    assert "case-one" not in str(rows)


def test_changed_metric_invalidates_cache_and_bad_coverage_withholds_scores(medical):
    telemetry = MedicalTelemetry(medical, show_gpus=False)
    telemetry.read()
    path = medical / "runs/active/metrics/epoch-00001.json"
    metric = json.loads(path.read_text())
    metric["validation"]["cases"].pop()
    write(path, metric)
    rows, _, _ = telemetry.read()
    row = next(row for row in rows if row["name"] == "active")
    assert row["status"] == "invalid_report"
    assert score_display(row)[:2] == (None, None)


def test_final_scores_require_complete_evaluation_and_label_different_basis():
    row = {
        "status": "completed",
        "latest_validation": {
            "mass_dice": 0.3,
            "pancreas_dice": 0.8,
            "step": 100,
            "validation_cases": 42,
        },
        "expected_cases": 42,
        "evaluation": {
            "complete_coverage": False,
            "mass": {"dice": 0.9},
            "pancreas": {"dice": 0.95},
            "coverage": {"valid_prediction_cases": 41, "eligible_cases": 42},
        },
    }
    assert score_display(row) == (0.3, 0.8, "native", 100, "42/42")
    row["evaluation"]["complete_coverage"] = True
    row["evaluation"]["coverage"]["valid_prediction_cases"] = 42
    assert score_display(row) == (0.9, 0.95, "final", None, "42/42")


def test_no_partial_nnunet_epoch_or_invalid_pseudo_is_presented_as_complete():
    text = "Epoch 4\nPseudo dice [np.float32(0.7), np.float32(0.3)]\n"
    assert parse_nnunet(text)["epochs"] == []
    parsed = parse_nnunet(
        text
        + "Epoch time: 12.5 s\nEpoch 5\nPseudo dice [np.float32(nan), np.float32(0.4)]\nEpoch time: 13 s\n"
    )
    assert parsed["epochs"][0]["epoch"] == 5
    assert parsed["epochs"][0]["mass_pseudo"] == 0.3
    assert "mass_pseudo" not in parsed["epochs"][1]
    assert parsed["errors"]


def test_medical_binding_only_state_directory_supported_before_workers_start(medical):
    spec = json.loads((medical / "campaign.json").read_text())
    state = medical / "arbitrary-controller-state"
    write(state / "campaign-binding.json", {"schema_version": 1, "spec": spec})
    (medical / "campaign.json").unlink()
    assert detect_backend(state) == "medical"
    rows, _, _ = MedicalTelemetry(state, show_gpus=False).read()
    assert len(rows) == 4
    assert all(row["status"] == "queued" for row in rows)


@pytest.mark.parametrize("size", [(80, 24), (160, 50)])
def test_shared_medical_ui_lists_all_filters_focus_and_scrolling(medical, size):
    async def exercise():
        app = MedicalProgress(medical, show_gpus=False)
        assert isinstance(app, CampaignProgress)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            table = app.query_one(DataTable)
            assert table.row_count == 4
            assert app.query_one("#note").region.bottom <= size[1]
            assert table.region.height >= 7
            active = table.get_row("active")
            assert active[4:9] == ["0.300", "0.800", "native", "100", "2/2"]
            await pilot.press("t")
            assert table.row_count == 2
            await pilot.press("c")
            assert table.row_count == 1
            await pilot.press("q")
            assert table.row_count == 1
            await pilot.press("a")
            assert table.row_count == 4
            if size[0] == 80:
                await pilot.press("shift+right")
                await pilot.pause()
                assert table.scroll_x > 0
            table.move_cursor(row=table.get_row_index("active"))
            await pilot.press("enter")
            assert app.detail_key == "active"
            assert app.query_one("#focus-view").display
            mass = next(chart for chart in app.query(TrainingCurve) if chart.tag == "val/mass_dice")
            assert mass.points[-1].value == 0.3
            assert app.query_one("#charts").styles.grid_size_columns == (1 if size[0] == 80 else 2)
            await pilot.press("escape")
            assert app.query_one(DataTable).display
            await app.action_refresh()
            assert table.row_count == 4

    asyncio.run(exercise())


def test_unified_entrypoint_uses_shared_adapter_once_and_no_gpu(medical, capsys, monkeypatch):
    monkeypatch.setattr(
        "segmentary.medical_progress.subprocess.check_output",
        lambda *a, **k: pytest.fail("--no-gpus was ignored"),
    )
    assert main([str(medical), "--once", "--no-gpus"]) == 0
    text = capsys.readouterr().out
    assert "Medical CT" in text
    assert "pending" in text
    assert "0.300" in text
    assert "case-one" not in text


def test_both_adapters_share_the_same_ui_and_status_filters():
    assert issubclass(RTISProgress, CampaignProgress)
    assert issubclass(MedicalProgress, CampaignProgress)
    for status in ("running", "training", "completed", "queued", "failed", "invalid_report"):
        assert visible({"status": status}, "all")
    assert visible({"status": "invalid_report"}, "failed")
    assert not visible({"status": "completed"}, "active")


def test_read_failure_stays_visible_through_filters_until_success(medical):
    from textual.widgets import Static

    async def exercise():
        app = MedicalProgress(medical, show_gpus=False)
        reader = app.telemetry.read
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()

            def failing(*args):
                raise OSError("simulated unavailable state")

            app.telemetry.read = failing
            await app.action_refresh()
            assert app.read_failure
            await pilot.press("t")
            assert "snapshot is stale" in str(app.query_one("#note", Static).render())
            await pilot.press("enter")
            assert "snapshot is stale" in str(app.query_one("#note", Static).render())
            app.telemetry.read = reader
            await app.action_refresh()
            assert app.read_failure is None
            assert "snapshot is stale" not in str(app.query_one("#note", Static).render())

    asyncio.run(exercise())


@pytest.mark.parametrize("size", [(80, 24), (160, 50)])
def test_shared_rtis_ui_has_same_filters_and_responsive_focus(tmp_path, size):
    from segmentary.progress import ScalarPoint

    point = ScalarPoint(49, 50, time.time())
    row = {
        "name": "unet--rtis_only--seed-0",
        "status": "training",
        "gpu": 0,
        "scalars": {
            "train/iteration": point,
            "train/progress": ScalarPoint(49, 0.1, point.wall_time),
        },
        "history": {},
        "loss_history": [],
    }

    async def exercise():
        app = RTISProgress(tmp_path, show_gpus=False)
        app.telemetry.read = lambda *args: ([dict(row)], {}, [])
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.query_one(DataTable).row_count == 1
            assert app.query_one("#note").region.bottom <= size[1]
            await pilot.press("q")
            assert app.query_one(DataTable).row_count == 0
            await pilot.press("a")
            assert app.query_one(DataTable).get_row_at(0)[3] == "50/500"
            await pilot.press("enter")
            assert app.detail_key == row["name"]
            assert app.query_one("#focus-view").display
            assert app.query_one("#charts").styles.grid_size_columns == (1 if size[0] == 80 else 2)
            await pilot.press("escape")
            assert app.query_one(DataTable).display

    asyncio.run(exercise())


@pytest.mark.parametrize("stage", ["predict", "evaluate"])
def test_post_training_stage_ignores_stale_validation_progress(medical, stage):
    state = medical / "state/runs/active.json"
    record = json.loads(state.read_text())
    record["stage"] = stage
    write(state, record)
    write(
        medical / "runs/active/progress.json",
        {
            "phase": "validation",
            "completed_cases": 1,
            "total_cases": 2,
            "updated_at": time.time() - 1000,
        },
    )
    rows, _, _ = MedicalTelemetry(medical, show_gpus=False).read()
    row = next(row for row in rows if row["name"] == "active")
    assert row["phase"] == stage
    assert not row["progress_text"].startswith("val")
    assert row["sample_time"] is None


def test_checkpoint_progress_is_distinct_from_training(medical):
    write(
        medical / "runs/active/progress.json",
        {
            "phase": "checkpoint",
            "step": 150,
            "target_steps": 200,
            "updated_at": time.time(),
        },
    )
    rows, _, _ = MedicalTelemetry(medical, show_gpus=False).read()
    active = next(row for row in rows if row["name"] == "active")
    assert active["phase"] == "checkpoint"
    assert active["progress_text"] == "save @150"
