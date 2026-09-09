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
            await pilot.press("q")

    try:
        asyncio.run(exercise())
    finally:
        writer.close()
