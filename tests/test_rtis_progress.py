"""Controller values and interactive lifecycle with recorded telemetry."""

import asyncio
from pathlib import Path

from tensorboard.compat.proto.event_pb2 import Event
from tensorboard.compat.proto.summary_pb2 import Summary
from tensorboard.summary.writer.event_file_writer import EventFileWriter

from segmentary.rtis_progress import DataTable, RTISProgress, Telemetry, value


def test_controller_reads_iterations_and_refreshes(tmp_path, monkeypatch):
    import json

    name = "model--rtis_only--seed-1"
    (tmp_path / "state").mkdir()
    (tmp_path / "state/job.json").write_text(
        json.dumps(
            {
                "name": name,
                "status": "training",
                "gpu": 0,
                "started_at": "2026-09-09T17:00:00+00:00",
            }
        )
    )
    log = tmp_path / "future-runs" / (name + "_seed1") / "rtis"
    writer = EventFileWriter(str(log))
    writer.add_event(
        Event(
            wall_time=1,
            step=49,
            summary=Summary(
                value=[
                    Summary.Value(tag="train/iteration", simple_value=50),
                    Summary.Value(tag="train/progress", simple_value=0.0125),
                    Summary.Value(tag="train/loss", simple_value=1.25),
                ]
            ),
        )
    )
    writer.flush()
    monkeypatch.setattr(
        "segmentary.rtis_progress.subprocess.check_output", lambda *a, **k: "0, 95, 1024, 49152, 50"
    )
    telemetry = Telemetry(tmp_path)
    rows, _, errors = telemetry.read()
    assert not errors
    assert value(rows[0], "train/iteration") == 50

    async def exercise():
        app = RTISProgress(Path(tmp_path))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert app.query_one(DataTable).get_row_at(0)[3] == "50/4,000"
            await pilot.press("enter")
            assert app.detail_key == name
            assert app.query_one("#focus-view").display
            assert not app.query_one(DataTable).display
            writer.add_event(
                Event(
                    wall_time=2,
                    step=99,
                    summary=Summary(
                        value=[
                            Summary.Value(tag="train/iteration", simple_value=100),
                            Summary.Value(tag="train/progress", simple_value=0.025),
                        ]
                    ),
                )
            )
            writer.flush()
            await app.action_refresh()
            await pilot.pause()
            assert app.query_one(DataTable).get_row_at(0)[3] == "100/4,000"
            assert app.detail_key == name
            from segmentary.training_curve import TrainingCurve

            assert app.query_one(TrainingCurve).points[-1].value == 1.25
            await pilot.resize_terminal(80, 30)
            await pilot.pause()
            assert app.query_one("#charts").styles.grid_size_columns == 1
            await pilot.resize_terminal(140, 40)
            await pilot.pause()
            assert app.query_one("#charts").styles.grid_size_columns == 2
            state_path = tmp_path / "state/job.json"
            state = json.loads(state_path.read_text())
            state["status"] = "completed"
            state_path.write_text(json.dumps(state))
            await app.action_refresh()
            assert app.detail_key == name
            assert app.query_one(TrainingCurve).points[-1].value == 1.25
            await pilot.press("escape")
            assert app.detail_key is None
            assert app.query_one(DataTable).display
            await pilot.press("q")
            await pilot.pause()
            assert app.is_running
            await pilot.press("ctrl+q")
            assert app.is_running

    try:
        asyncio.run(exercise())
    finally:
        writer.close()


def test_failure_overview_shows_actual_exception(tmp_path):
    import json

    from segmentary.rtis_progress import failure_detail

    (tmp_path / "logs").mkdir()
    state = {
        "name": "model--rtis_only--seed-0",
        "status": "failed",
        "collection_phase": "diagnostics",
        "error": "Process exited 1; see log",
    }
    (tmp_path / "logs" / (state["name"] + ".log")).write_text(
        "Traceback...\nRuntimeError: Split coverage mismatch: expected 205 images, got 204\n"
    )
    assert "expected 205 images, got 204" in failure_detail(tmp_path, state)
    (tmp_path / "state").mkdir()
    (tmp_path / "state/job.json").write_text(json.dumps(state))

    async def exercise():
        app = RTISProgress(tmp_path)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert app.query_one("#failures").display
            assert "expected 205 images, got 204" in str(app.query_one("#failures").render())
            await pilot.press("enter")
            assert not app.query_one("#failures").display
            await pilot.press("escape")
            assert app.query_one("#failures").display

    asyncio.run(exercise())
