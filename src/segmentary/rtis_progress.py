"""Live RTIS controller: observe existing state and TensorBoard telemetry only."""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Header, Sparkline, Static


def duration(value):
    if value is None or not math.isfinite(value):
        return "—"
    seconds = max(0, int(value))
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return f"{h:02}:{m:02}:{s:02}"


def number(value, fmt=".3f"):
    return format(value, fmt) if value is not None and math.isfinite(value) else "—"


class Telemetry:
    def __init__(self, root):
        self.root = root
        self.readers = {}

    def read(self):
        rows, errors = [], []
        for path in sorted((self.root / "state").glob("*.json")):
            try:
                state = json.loads(path.read_text())
                state["scalars"] = {}
                state["loss_history"] = []
                if state["status"] not in ("queued", "completed"):
                    run = (
                        self.root
                        / "future-runs"
                        / (state["name"] + "_seed" + state["name"].rsplit("--seed-", 1)[-1])
                        / "rtis"
                    )
                    events = sorted(
                        run.rglob("events.out.tfevents.*"), key=lambda p: p.stat().st_mtime
                    )
                    if events:
                        event = events[-1]
                        key = str(event)
                        signature = (event.stat().st_size, event.stat().st_mtime_ns)
                        cached = self.readers.get(key)
                        if cached is None:
                            cached = (EventAccumulator(key, size_guidance={"scalars": 256}), None)
                        acc, previous = cached
                        if previous != signature:
                            acc.Reload()
                        self.readers[key] = (acc, signature)
                        for tag in acc.Tags()["scalars"]:
                            points = acc.Scalars(tag)
                            if points:
                                state["scalars"][tag] = points[-1]
                                if tag == "train/loss":
                                    state["loss_history"] = [
                                        p.value for p in points if math.isfinite(p.value)
                                    ]
                rows.append(state)
            except (OSError, ValueError, KeyError) as exc:
                errors.append(f"{path.name}: {exc}")
        active_names = {
            row["name"] + "_seed" + row["name"].rsplit("--seed-", 1)[-1]
            for row in rows
            if row["status"] not in ("queued", "completed")
        }
        self.readers = {k: v for k, v in self.readers.items() if any(n in k for n in active_names)}
        gpus = {}
        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=3,
            )
            for line in output.splitlines():
                index, util, used, total, temp = (v.strip() for v in line.split(","))
                gpus[int(index)] = (
                    f"{util}% · {float(used) / 1024:.1f}/{float(total) / 1024:.0f}G · {temp}°"
                )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(f"GPU telemetry unavailable: {exc}")
        return rows, gpus, errors


def value(row, tag):
    point = row["scalars"].get(tag)
    return point.value if point is not None else None


class RTISProgress(App):
    TITLE = "SEGMENTARY  /  Training controller"
    CSS = """
    Screen { background: #0c1422; }
    Header { background: #17263c; }
    #summary { height: 3; padding: 1 2; background: #17263c; color: #66e3c4; }
    #jobs { height: 1fr; min-height: 7; margin: 1 1 0 1; }
    #detail { height: 6; padding: 1 2; background: #17263c; }
    #curve { height: 4; padding: 0 2; }
    #curve-label { width: 18; content-align: left middle; color: #66e3c4; }
    Sparkline { width: 1fr; color: #66e3c4; }
    #note { height: 3; padding: 0 2; color: #97abc7; }
    Footer { background: #17263c; }
    """
    BINDINGS: ClassVar = [("q", "quit", "Close viewer"), ("r", "refresh", "Refresh")]

    def __init__(self, root):
        super().__init__()
        self.root = root
        self.telemetry = Telemetry(root)
        self.rows = {}
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Reading live telemetry…", id="summary")
        yield DataTable(id="jobs", cursor_type="row", zebra_stripes=True)
        yield Static("Select a run for details", id="detail", markup=False)
        with Horizontal(id="curve"):
            yield Static("TRAIN LOSS", id="curve-label")
            yield Sparkline([], id="loss")
        yield Static("", id="note", markup=False)
        yield Footer()

    async def on_mount(self):
        self.sub_title = self.root.parent.name + " / " + self.root.name
        table = self.query_one(DataTable)
        for title, width in [
            ("GPU", 3),
            ("Model / protocol", 30),
            ("Phase", 10),
            ("Iterations", 11),
            ("Progress", 15),
            ("opt/s", 6),
            ("Train ETA*", 9),
            ("Loss", 6),
            ("Age", 8),
        ]:
            table.add_column(title, width=width)
        self.set_interval(3, self.action_refresh)
        await self.action_refresh()
        self.query_one(DataTable).focus()

    async def action_refresh(self):
        if self.busy:
            return
        self.busy = True
        try:
            rows, gpus, errors = await asyncio.to_thread(self.telemetry.read)
            self.rows = {r["name"]: r for r in rows}
            counts = Counter(r["status"] for r in rows)
            self.query_one("#summary", Static).update(
                f"{counts['completed']}/{len(rows)} COMPLETE    "
                + "    ".join(f"{v} {k.upper()}" for k, v in counts.items() if k != "completed")
            )
            table = self.query_one(DataTable)
            selected = table.cursor_row
            table.clear()
            now = time.time()
            for row in sorted(rows, key=lambda r: (r.get("gpu", 999), r["name"])):
                if row["status"] in ("queued", "completed"):
                    continue
                scalar = row["scalars"].get("train/iteration")
                iteration = scalar.value if scalar else None
                progress = value(row, "train/progress")
                total = round(iteration / progress) if iteration is not None and progress else None
                bar = (
                    "—"
                    if progress is None
                    else "━" * round(min(1, max(0, progress)) * 10)
                    + "─" * (10 - round(min(1, max(0, progress)) * 10))
                    + f" {progress:.0%}"
                )
                age = now - scalar.wall_time if scalar else None
                try:
                    elapsed = now - datetime.fromisoformat(row["started_at"]).timestamp()
                except (KeyError, ValueError):
                    elapsed = None
                training = row["status"] == "training"
                row["elapsed"] = elapsed
                row["gpu_text"] = gpus.get(row.get("gpu"), "—")
                short = row["name"].split("--")
                protocol = {
                    "rtis_only": "RTIS",
                    "cityscapes_to_rtis": "CS→RTIS",
                    "railsem19_to_rtis": "RS→RTIS",
                    "cityscapes_to_railsem19_to_rtis": "CS→RS→RTIS",
                }.get(short[1], short[1])
                table.add_row(
                    str(row.get("gpu", "—")),
                    Text(short[0] + " / " + protocol, overflow="ellipsis", no_wrap=True),
                    Text(row["status"], style="cyan" if training else "yellow"),
                    f"{int(iteration):,}/{total:,}" if total else "—",
                    Text(bar, style="#66e3c4"),
                    number(value(row, "train/optimizer_steps_per_sec")) if training else "—",
                    duration(value(row, "train/eta_seconds")) if training else "—",
                    number(value(row, "train/loss")),
                    Text(duration(age), style="yellow" if age is not None and age > 180 else "dim"),
                    key=row["name"],
                )
            if table.row_count:
                table.move_cursor(row=min(selected, table.row_count - 1))
                self.show_detail(
                    str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
                )
            else:
                self.query_one("#detail", Static).update("No active runs. " + str(dict(counts)))
                self.query_one(Sparkline).data = []
            note = (
                " | ".join(errors)
                if errors
                else (
                    "Refresh 3s · Metrics emitted every 50 optimizer steps · Arrow keys select / scroll columns\n"
                    "*Training ETA to step limit; early stopping may shorten it. Final evaluation/profiling adds time. Rates are run averages."
                )
            )
            self.query_one("#note", Static).update(note)
        finally:
            self.busy = False

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        self.show_detail(str(event.row_key.value))

    def show_detail(self, key):
        row = self.rows.get(key)
        if row is None or not self.query("#detail"):
            return
        val = row["scalars"].get("val/miou")
        self.query_one("#detail", Static).update(
            row["name"]
            + "\n"
            + f"Elapsed {duration(row.get('elapsed'))}   Images/s {number(value(row, 'train/examples_per_sec'), '.1f')}   GPU {row.get('gpu_text', '—')}\n"
            + f"Val mIoU {number(value(row, 'val/miou'), '.2%')}   Mud IoU {number(value(row, 'val_iou/mud-pumping'), '.2%')}   "
            + f"Learning rate {number(value(row, 'train/lr'), '.3g')}   "
            + f"Last validation: step {val.step + 1 if val else '—'}   "
            + f"Pixel accuracy {number(value(row, 'val/pixel_acc'), '.2%')}   "
            + f"Boundary F1 {number(value(row, 'val/boundary_f1'), '.3f')}"
            + ("\n" + str(row["error"]) if row.get("error") else "")
        )
        self.query_one(Sparkline).data = row["loss_history"]


def run(root):
    RTISProgress(root).run()


def ensure_controller(root, repo, python, session="rtis-fullstats-controller"):
    """Start the standard controller alongside a campaign, without signaling workers."""
    import shlex

    command = f"cd {shlex.quote(str(repo))} && PYTHONPATH=src " + shlex.join(
        [str(python), "-m", "segmentary.rtis_progress", str(root)]
    )
    exists = (
        subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode == 0
    )
    if not exists:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, "-n", "training", command], check=True
        )
        subprocess.run(
            [
                "tmux",
                "new-window",
                "-d",
                "-t",
                session,
                "-n",
                "gpu-monitor",
                "watch -n 2 nvidia-smi",
            ],
            check=True,
        )
    else:
        windows = subprocess.check_output(
            ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"], text=True
        ).splitlines()
        if "training" not in windows:
            subprocess.run(
                ["tmux", "new-window", "-d", "-t", session, "-n", "training", command], check=True
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    if not (args.campaign / "state").is_dir():
        parser.error("campaign must contain a state directory")
    run(args.campaign.resolve())
