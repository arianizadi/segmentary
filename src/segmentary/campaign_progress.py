"""Shared read-only campaign UI; adapters supply telemetry and metric meaning.

The same table, status filters, run selection, responsive curves and refresh
lifecycle are used by medical and RTIS campaigns. This module has no trainer API.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import Counter
from datetime import datetime
from typing import ClassVar

from rich.table import Table
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Sparkline, Static

from segmentary.training_curve import TrainingCurve

COMPLETED = {"completed", "succeeded", "reused", "prepared"}
FAILED = {"failed", "interrupted", "invalid_report"}


def duration(value):
    if value is None or not math.isfinite(value):
        return "—"
    seconds = max(0, int(value))
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return f"{h:02}:{m:02}:{s:02}"


def number(value, fmt=".3f"):
    return format(value, fmt) if value is not None and math.isfinite(value) else "—"


def value(row, tag):
    point = row["scalars"].get(tag)
    return point.value if point is not None else None


def visible(row, selection):
    status = row["status"]
    return (
        selection == "all"
        or (selection == "active" and status not in (COMPLETED | FAILED | {"queued"}))
        or (selection == "completed" and status in COMPLETED)
        or (selection == "queued" and status == "queued")
        or (selection == "failed" and status in FAILED)
    )


def row_order(row):
    status = row["status"]
    group = 0 if status in FAILED else 2 if status in COMPLETED else 3 if status == "queued" else 1
    gpu = row.get("gpu")
    return group, int(gpu) if gpu is not None and str(gpu).isdigit() else 999, row["name"]


class CurveGrid(Grid):
    def on_resize(self, event):
        columns = 1 if event.size.width < 96 else 2
        if self.styles.grid_size_columns != columns:
            self.styles.grid_size_columns = columns
            self.styles.height = 63 if columns == 1 else 31


class CampaignProgress(App, inherit_bindings=False):  # type: ignore[call-arg]
    TITLE = "SEGMENTARY  /  Training progress"
    CSS = """
    Screen { background: #0c1422; }
    Header { background: #17263c; }
    #summary { height: 3; padding: 1 2; background: #17263c; color: #66e3c4; }
    #backend-summary { height: auto; max-height: 4; padding: 0 2; color: #aac4e6; }
    #failures { height: auto; max-height: 7; overflow-y: auto; color: #ffb4b4; background: #351c2b; padding: 0 2; }
    #jobs { height: 1fr; min-height: 7; margin: 1 1 0 1; }
    #detail { height: 6; padding: 1 2; background: #17263c; }
    #curve { height: 4; padding: 0 2; }
    #curve-label { width: 18; content-align: left middle; color: #66e3c4; }
    Sparkline { width: 1fr; color: #66e3c4; }
    #note { height: 3; padding: 0 2; color: #97abc7; }
    #focus-view { display: none; height: 1fr; padding: 1 2; }
    #focus-summary { height: auto; min-height: 4; margin-bottom: 1; }
    #charts { grid-size: 2; grid-rows: 15; height: 31; grid-gutter: 1; }
    TrainingCurve { height: 15; border: round #294461; padding: 0 1; }
    #all-metrics { height: auto; margin-top: 1; }
    Footer { background: #17263c; }
    """
    BINDINGS: ClassVar = [
        ("escape", "overview", "Overview"),
        ("r", "refresh", "Refresh"),
        ("a", "filter('all')", "All"),
        ("t", "filter('active')", "Active"),
        ("c", "filter('completed')", "Complete"),
        ("q", "filter('queued')", "Queued"),
        ("f", "filter('failed')", "Issues"),
        ("shift+right", "scroll_table_right", "Scroll →"),
        ("shift+left", "scroll_table_left", "Scroll ←"),
    ]

    def __init__(self, root, telemetry, profile, *, refresh=None):
        super().__init__()
        self.root = root
        self.telemetry = telemetry
        self.profile = profile
        self.refresh_seconds = max(profile.refresh_seconds, refresh or 0)
        self.rows = {}
        self.busy = False
        self.detail_key = None
        self.selection = "all"
        self.errors = []
        self.last_success = None
        self.read_failure = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Reading live telemetry…", id="summary")
        yield Static("", id="backend-summary", markup=False)
        yield Static("", id="failures", markup=False)
        yield DataTable(id="jobs", cursor_type="row", zebra_stripes=True)
        yield Static("Select a run for details", id="detail", markup=False)
        with Horizontal(id="curve"):
            yield Static("TRAIN LOSS", id="curve-label")
            yield Sparkline([], id="loss")
        with VerticalScroll(id="focus-view"):
            yield Static("", id="focus-summary", markup=False)
            with CurveGrid(id="charts"):
                for title, tag, percent in self.profile.charts:
                    yield TrainingCurve(title, tag, percent=percent)
            yield Static("", id="all-metrics")
        yield Static("", id="note", markup=False)
        yield Footer()

    async def on_mount(self):
        self.sub_title = self.profile.label + " / " + self.root.name
        table = self.query_one(DataTable)
        for title, width in self.profile.columns:
            table.add_column(title, width=width)
        self.set_interval(self.refresh_seconds, self.action_refresh)
        await self.action_refresh()
        self.adjust_overview()
        table.focus()

    def on_resize(self, event):
        self.adjust_overview()

    def adjust_overview(self):
        if not self.query("#detail"):
            return
        compact = self.size.height < 36
        self.query_one("#detail").styles.height = 3 if compact else 6
        self.query_one("#backend-summary").styles.max_height = 2 if compact else 4
        self.query_one("#curve").display = not compact and self.detail_key is None

    async def action_refresh(self):
        if self.busy:
            return
        self.busy = True
        try:
            rows, gpus, errors = await asyncio.to_thread(self.telemetry.read, self.detail_key)
            self.rows = {row["name"]: row for row in rows}
            self.errors = errors
            self.last_success = time.time()
            self.read_failure = None
            for row in rows:
                try:
                    end = (
                        datetime.fromisoformat(row["finished_at"]).timestamp()
                        if row.get("finished_at")
                        else self.last_success
                    )
                    row["elapsed"] = end - datetime.fromisoformat(row["started_at"]).timestamp()
                except (KeyError, ValueError, TypeError):
                    row["elapsed"] = None
                row["gpu_text"] = (
                    "run completed" if row["status"] in COMPLETED else gpus.get(row.get("gpu"), "—")
                )
            self.redraw_rows()
        except Exception as exc:
            age = duration(time.time() - self.last_success) if self.last_success else "never"
            self.read_failure = f"LIVE READ FAILED · {type(exc).__name__}: {exc}\nDisplayed snapshot is stale; last successful read {age} ago. Training is untouched."
            self.render_notice()
        finally:
            self.busy = False

    def redraw_rows(self):
        rows = list(self.rows.values())
        counts = Counter(row["status"] for row in rows)
        complete = sum(counts[key] for key in COMPLETED)
        self.query_one("#summary", Static).update(
            f"{complete}/{len(rows)} COMPLETE    "
            + "    ".join(
                f"{count} {status.upper()}"
                for status, count in counts.items()
                if status not in COMPLETED
            )
            + f"    VIEW: {self.selection.upper()}"
        )
        self.query_one("#backend-summary", Static).update(getattr(self.telemetry, "summary", ""))
        failures = [
            f"{row['status'].upper()} · {row['name']}\n  {row.get('failure_detail') or row.get('error') or 'Inspect the preserved run log'}"
            for row in rows
            if row["status"] in FAILED
        ]
        self.query_one("#failures", Static).update("\n".join(failures))
        self.query_one("#failures").display = bool(failures) and self.detail_key is None
        table = self.query_one(DataTable)
        selected = table.cursor_row
        key = (
            table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            if table.row_count
            else None
        )
        table.clear()
        for row in sorted(rows, key=row_order):
            if visible(row, self.selection):
                table.add_row(*self.profile.cells(row, time.time()), key=row["name"])
        if table.row_count:
            table.move_cursor(
                row=table.get_row_index(key)
                if key in table.rows
                else min(selected, table.row_count - 1)
            )
            self.show_detail(
                str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
            )
        else:
            self.query_one("#detail", Static).update(
                f"No {self.selection} runs. " + str(dict(counts))
            )
            self.query_one(Sparkline).data = []
        self.render_notice()
        self.update_focus()

    def render_notice(self):
        self.query_one("#note", Static).update(
            self.read_failure or (" | ".join(self.errors) if self.errors else self.profile.note)
        )

    def action_filter(self, selection):
        self.selection = selection
        self.action_overview()
        self.redraw_rows()

    def action_scroll_table_right(self):
        self.query_one(DataTable).scroll_right(animate=False)

    def action_scroll_table_left(self):
        self.query_one(DataTable).scroll_left(animate=False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        self.detail_key = str(event.row_key.value)
        for selector in ("#jobs", "#detail", "#curve", "#summary", "#failures", "#backend-summary"):
            self.query_one(selector).display = False
        self.query_one("#focus-view").display = True
        self.query_one("#focus-view").focus()
        self.update_focus()

    def action_overview(self):
        self.detail_key = None
        self.query_one("#focus-view").display = False
        for selector in ("#jobs", "#detail", "#curve", "#summary", "#backend-summary"):
            self.query_one(selector).display = True
        self.query_one("#failures").display = any(
            row["status"] in FAILED for row in self.rows.values()
        )
        self.query_one(DataTable).focus()
        self.adjust_overview()

    def update_focus(self):
        row = self.rows.get(self.detail_key)
        if row is None:
            return
        self.query_one("#focus-summary", Static).update(self.profile.detail(row, focus=True))
        for chart in self.query(TrainingCurve):
            chart.points = row.get("history", {}).get(chart.tag, [])
            chart.refresh()
        table = Table(title="Recorded metrics · latest sample per metric", expand=True)
        for title in ("Metric", "Value", "Step", "Age"):
            table.add_column(title)
        for tag, point in sorted(row["scalars"].items()):
            table.add_row(
                tag,
                number(point.value, self.profile.metric_format(tag)),
                str(point.step + 1),
                duration(time.time() - point.wall_time),
            )
        self.query_one("#all-metrics", Static).update(table)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        self.show_detail(str(event.row_key.value))

    def show_detail(self, key):
        row = self.rows.get(key)
        if row is None or not self.query("#detail"):
            return
        self.query_one("#detail", Static).update(self.profile.detail(row, focus=False))
        self.query_one(Sparkline).data = row.get("loss_history", [])


def render_once(rows, gpus, errors, profile, summary=""):
    """Use the same columns and adapter semantics for noninteractive checks."""
    table = Table(title=f"SEGMENTARY / {profile.label} · {summary}", expand=True)
    for title, _ in profile.columns:
        table.add_column(title)
    for row in sorted(rows, key=row_order):
        row["gpu_text"] = gpus.get(row.get("gpu"), "—")
        table.add_row(*profile.cells(row, time.time()))
    return table, " | ".join(errors) if errors else profile.note
