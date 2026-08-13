"""A read-only, single-screen dashboard for queued Segmentary campaigns.

The dashboard deliberately observes files that training already writes.  It
never imports a model, opens a checkpoint, reserves a GPU, or signals a trainer.
That makes it safe to start beside an in-progress multi-GPU campaign::

    segmentary-progress runs/my_campaign

Every lane is one row, so a ten-GPU campaign fits in one window without
scrolling.  The view refreshes once a second; the columns that can only move
when training logs a scalar are paired with an AGE column that ticks every
second, so a still frame is always distinguishable from a stalled lane.

Press Ctrl-C to leave the dashboard; training continues unchanged.
Use ``--once`` for a plain snapshot suitable for logs or remote status checks.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rich.align import Align
from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


@dataclass(frozen=True)
class ScalarPoint:
    step: int
    value: float
    wall_time: float


@dataclass
class StageSnapshot:
    name: str
    path: Path
    step: int | None = None
    total_steps: int | None = None
    rate: float | None = None
    eta_seconds: float | None = None
    last_update: datetime | None = None
    scalars: dict[str, ScalarPoint] = field(default_factory=dict)


@dataclass
class LaneSnapshot:
    lane: str
    record: dict[str, Any]
    active_job: dict[str, Any] | None
    stage: StageSnapshot | None
    completed: int
    lane_eta_seconds: float | None
    warnings: list[str]


HEADLINE_TAGS = (
    "train/loss",
    "train/ce",
    "train/lovasz",
    "train/lr",
    "train/optimizer_steps_per_sec",
    "train/examples_per_sec",
    "train/eta_seconds",
    "val/miou",
    "val/macc",
    "val/pixel_acc",
    "val/boundary_f1",
    "val/thin_miou",
)
ACTIVE_STATUSES = {"training", "evaluating", "benchmarking"}
COMPLETED_STATUSES = {"succeeded", "reused"}
FAILED_STATUSES = {
    "train_failed",
    "train_artifact_failed",
    "eval_failed",
    "eval_artifact_failed",
    "performance_failed",
    "performance_artifact_failed",
    "checkpoint_missing",
    "provenance_failed",
}

# A one-second refresh must not re-read the campaign from scratch every tick.
# Event files only grow when training logs (every 50 optimizer steps, so roughly
# once a minute per lane), and nvidia-smi/tmux answers stay true for seconds, so
# each source is re-read only when it can actually have changed.
_EVENT_SCAN_TTL = 5.0
_TMUX_TTL = 15.0
_GPU_TTL = 4.0
_TOTAL_STEPS_TTL = 60.0
_CACHE_ENTRIES = 4096

_ttl_cache: dict[Any, tuple[float, Any]] = {}
_signature_cache: dict[Any, tuple[Any, Any]] = {}


def _prune(cache: dict[Any, Any]) -> None:
    # Long campaigns retire stages and jobs; drop the oldest keys rather than
    # letting a days-long dashboard grow without bound.
    while len(cache) > _CACHE_ENTRIES:
        cache.pop(next(iter(cache)))


def _cached(key: Any, ttl: float, produce: Callable[[], Any]) -> Any:
    """Return a recent value for ``key``, recomputing only after ``ttl`` seconds."""
    now = time.monotonic()
    hit = _ttl_cache.get(key)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]
    value = produce()
    _ttl_cache[key] = (now, value)
    _prune(_ttl_cache)
    return value


def _signature(path: Path) -> tuple[float, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime, stat.st_size)


def _cached_by_file(key: Any, path: Path, produce: Callable[[], Any]) -> Any:
    """Return a cached value that is reused until ``path`` changes on disk."""
    signature = _signature(path)
    hit = _signature_cache.get(key)
    if hit is not None and hit[0] == signature:
        return hit[1]
    value = produce()
    _signature_cache[key] = (signature, value)
    _prune(_signature_cache)
    return value


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"missing {path.name}"
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"cannot read {path.name}: {exc}"
    if not isinstance(value, dict):
        return None, f"{path.name} is not a JSON object"
    return value, None


def _event_files(run_dir: Path) -> list[Path]:
    def scan() -> list[Path]:
        try:
            return [path for path in run_dir.rglob("events.out.tfevents*") if path.is_file()]
        except OSError:
            return []

    return _cached(("events", run_dir), _EVENT_SCAN_TTL, scan)


def _stage_dir(event_path: Path) -> Path:
    # Current: <stage>/tensorboard/events.out.tfevents...
    # Legacy:  <stage>/lightning_logs/version_N/events.out.tfevents...
    if event_path.parent.name == "tensorboard":
        return event_path.parent.parent
    if event_path.parent.parent.name == "lightning_logs":
        return event_path.parent.parent.parent
    return event_path.parent


def _read_total_steps(stage_dir: Path) -> int | None:
    def read() -> int | None:
        candidates = sorted(
            [
                *stage_dir.glob("tensorboard/hparams.yaml"),
                *stage_dir.glob("lightning_logs/version_*/hparams.yaml"),
            ],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            match = re.search(r"(?m)^\s+iters:\s*(\d+)\s*$", text)
            if match:
                return int(match.group(1))
        return None

    # The iteration budget is fixed for the life of a stage, so a short TTL is
    # enough to notice a newly written hparams.yaml without re-reading it 1x/s.
    return _cached(("total_steps", stage_dir), _TOTAL_STEPS_TTL, read)


def _load_event_scalars(event_paths: list[Path]) -> dict[str, list[ScalarPoint]]:
    """Merge scalar summaries across rollovers/resumes of one active stage."""
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    def parse(event_path: Path) -> dict[str, list[ScalarPoint]]:
        accumulator = EventAccumulator(str(event_path), size_guidance={"scalars": 0})
        accumulator.Reload()
        available = set(accumulator.Tags().get("scalars", []))
        return {
            tag: [
                ScalarPoint(int(item.step), float(item.value), float(item.wall_time))
                for item in accumulator.Scalars(tag)
            ]
            for tag in HEADLINE_TAGS
            if tag in available
        }

    result: dict[str, list[ScalarPoint]] = {}
    for event_path in event_paths:
        # Re-parsing a growing event file is the single most expensive thing the
        # dashboard does, and the file only changes when training logs.
        parsed = _cached_by_file(
            ("scalars", event_path), event_path, lambda event_path=event_path: parse(event_path)
        )
        for tag, points in parsed.items():
            result.setdefault(tag, []).extend(points)
    for tag, points in result.items():
        # A resumed logger can repeat the last step. The most recently written
        # scalar is the authoritative value for that step.
        by_step = {point.step: point for point in sorted(points, key=lambda item: item.wall_time)}
        result[tag] = sorted(by_step.values(), key=lambda item: item.step)
    return result


def _measured_rate(points: list[ScalarPoint]) -> float | None:
    """Estimate effective optimizer-step throughput, including recent validation pauses."""
    if len(points) < 2:
        return None
    # A roughly 4k-step window smooths logging jitter while adapting when a new
    # stage or host has meaningfully different throughput.
    latest = points[-1]
    earliest = points[0]
    for point in reversed(points[:-1]):
        earliest = point
        if latest.step - point.step >= 4_000:
            break
    elapsed = latest.wall_time - earliest.wall_time
    steps = latest.step - earliest.step
    if elapsed <= 0 or steps <= 0:
        return None
    return steps / elapsed


def inspect_stage(run_dir: Path, warnings: list[str]) -> StageSnapshot | None:
    events = _event_files(run_dir)
    if not events:
        return None
    event_path = max(events, key=lambda path: path.stat().st_mtime)
    stage_dir = _stage_dir(event_path)
    snapshot = StageSnapshot(
        name=stage_dir.name,
        path=stage_dir,
        total_steps=_read_total_steps(stage_dir),
    )
    try:
        stage_events = sorted(path for path in events if _stage_dir(path) == stage_dir)
        series = _load_event_scalars(stage_events)
    except Exception as exc:  # a partial final event is recoverable on the next refresh
        warnings.append(f"{run_dir.name}: TensorBoard refresh deferred ({exc})")
        return snapshot

    snapshot.scalars = {tag: points[-1] for tag, points in series.items() if points}
    training = series.get("train/loss", [])
    if training:
        latest = training[-1]
        snapshot.step = latest.step + 1
        snapshot.rate = _measured_rate(training)
        snapshot.last_update = datetime.fromtimestamp(latest.wall_time, tz=UTC)
    elif snapshot.scalars:
        latest = max(snapshot.scalars.values(), key=lambda point: point.wall_time)
        snapshot.step = latest.step + 1
        snapshot.last_update = datetime.fromtimestamp(latest.wall_time, tz=UTC)
    if snapshot.step is not None and snapshot.total_steps is not None:
        snapshot.step = min(snapshot.step, snapshot.total_steps)
        if snapshot.rate and snapshot.rate > 0:
            snapshot.eta_seconds = max(0, snapshot.total_steps - snapshot.step) / snapshot.rate
    return snapshot


def _duration_seconds(started: Any, finished: Any) -> float | None:
    start = _parse_datetime(started)
    end = _parse_datetime(finished)
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds()


def _observed_job_durations(records: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for record in records:
        for job in _job_records(record):
            if not isinstance(job, dict) or job.get("status") != "succeeded":
                continue
            duration = _duration_seconds(job.get("started_at"), job.get("finished_at"))
            curriculum = job.get("curriculum")
            if duration is not None and isinstance(curriculum, str):
                values.setdefault(curriculum, []).append(duration)
    return {name: statistics.median(durations) for name, durations in values.items()}


def _remaining_lane_seconds(
    record: dict[str, Any],
    stage: StageSnapshot | None,
    observed: dict[str, float],
    now: datetime,
) -> float | None:
    if record.get("failure") or any(
        job.get("status") in FAILED_STATUSES for job in _job_records(record)
    ):
        return None
    remaining = 0.0
    unfinished = False
    for job in _job_records(record):
        status = job.get("status")
        if status in COMPLETED_STATUSES or status in FAILED_STATUSES:
            continue
        unfinished = True
        typical = observed.get(job.get("curriculum"))
        # A partial sum would be a dangerously optimistic lane ETA. Until every
        # remaining curriculum has a completed analogue, say "estimating".
        if typical is None:
            return None
        if status in ACTIVE_STATUSES:
            started = _parse_datetime(job.get("started_at"))
            by_history = (
                max(0.0, typical - (now - started).total_seconds())
                if started is not None
                else typical
            )
            by_stage = stage.eta_seconds if stage is not None else None
            remaining += max(value for value in (by_history, by_stage) if value is not None)
        elif status == "pending":
            remaining += typical
        else:
            return None
    return remaining if unfinished else 0.0


def _job_records(record: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = record.get("jobs", [])
    if not isinstance(jobs, list):
        return []
    return [job for job in jobs if isinstance(job, dict)]


def inspect_campaign(campaign: Path, now: datetime | None = None) -> list[LaneSnapshot]:
    now = now or datetime.now(UTC)
    loaded: list[tuple[str, dict[str, Any], list[str]]] = []
    status_paths = sorted(campaign.glob("lane_*_status.json"))
    for path in status_paths:
        warnings: list[str] = []
        record, problem = _read_json(path)
        if problem:
            warnings.append(problem)
        if record is None:
            record = {
                "lane": path.stem.removeprefix("lane_").removesuffix("_status"),
                "status": "unreadable",
                "jobs": [],
                "failure": None,
            }
        lane = str(record.get("lane") or path.stem.removeprefix("lane_").removesuffix("_status"))
        if not isinstance(record.get("jobs", []), list):
            warnings.append(f"{path.name}: jobs must be a JSON list")
        loaded.append((lane, record, warnings))
    records = [record for _, record, _ in loaded]
    observed = _observed_job_durations(records)
    snapshots: list[LaneSnapshot] = []
    for lane, record, warnings in loaded:
        jobs = _job_records(record)
        active = next((job for job in jobs if job.get("status") in ACTIVE_STATUSES), None)
        stage = None
        if active is not None and active.get("status") == "training":
            raw_run_dir = active.get("run_dir")
            if isinstance(raw_run_dir, str) and raw_run_dir.strip():
                run_dir = Path(raw_run_dir)
                stage = inspect_stage(run_dir, warnings)
            else:
                warnings.append(
                    f"{active.get('curriculum', 'active job')}: missing non-empty run_dir"
                )
        if (
            stage is not None
            and stage.last_update is not None
            and now - stage.last_update > timedelta(minutes=15)
        ):
            warnings.append(
                f"lane {lane}: no new training scalar for "
                f"{_format_duration((now - stage.last_update).total_seconds())}"
            )
        snapshots.append(
            LaneSnapshot(
                lane=lane,
                record=record,
                active_job=active,
                stage=stage,
                completed=sum(job.get("status") in COMPLETED_STATUSES for job in jobs),
                lane_eta_seconds=_remaining_lane_seconds(record, stage, observed, now),
                warnings=warnings,
            )
        )
    return snapshots


def _format_duration(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "estimating…"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _format_short_duration(seconds: float | None) -> str:
    """Compact ``2h04``/``31m``/``18s`` form for narrow columns."""
    if seconds is None or not math.isfinite(seconds):
        return "—"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{rest:02d}"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}"


def _local_time(value: datetime | None, timezone: tzinfo) -> str:
    return "—" if value is None else value.astimezone(timezone).strftime("%a %I:%M %p %Z")


def _clock(value: datetime, timezone: tzinfo) -> str:
    return value.astimezone(timezone).strftime("%I:%M:%S %p")


def _metric(
    stage: StageSnapshot | None,
    tag: str,
    *,
    percent: bool = False,
    scientific: bool = False,
) -> str:
    point = stage.scalars.get(tag) if stage else None
    if point is None:
        return "—"
    value = point.value * 100 if percent else point.value
    if percent:
        return f"{value:.2f}%"
    return f"{value:.2e}" if scientific else f"{value:.4f}"


def _result_miou(job: dict[str, Any]) -> float | None:
    path = Path(str(job.get("common_results", "")))

    def read() -> float | None:
        record, _ = _read_json(path)
        metrics = record.get("metrics") if record else None
        value = metrics.get("miou") if isinstance(metrics, dict) else None
        return float(value) if isinstance(value, int | float) and math.isfinite(value) else None

    # A finished job's results.json never changes again, and a campaign
    # accumulates hundreds of them.
    return _cached_by_file(("result", path), path, read)


def _truncate(value: str, width: int) -> str:
    return value if len(value) <= width else value[: max(1, width - 1)] + "…"


def _job_label(job: dict[str, Any]) -> str:
    protocol = job.get("protocol", job.get("curriculum", "?"))
    model = job.get("model")
    seed = job.get("seed", "?")
    return f"{model} / {protocol} s{seed}" if model else f"{protocol} s{seed}"


def _queue_text(jobs: list[dict[str, Any]], width: int) -> Text:
    """One glyph per job: the whole lane plan at a glance, in a fixed column."""
    text = Text()
    shown = jobs[:width] if len(jobs) > width else jobs
    for job in shown:
        status = job.get("status")
        if status in COMPLETED_STATUSES:
            text.append("✓", style="green")
        elif status in ACTIVE_STATUSES:
            text.append("▶", style="bold cyan")
        elif status in FAILED_STATUSES:
            text.append("✗", style="bold red")
        else:
            text.append("·", style="grey42")
    if len(jobs) > len(shown):
        text.append(f"+{len(jobs) - len(shown)}", style="dim")
    return text


def _tmux_alive(session: str) -> bool | None:
    def probe() -> bool | None:
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", session],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.returncode == 0

    # Forking one tmux per lane per second would cost more than the dashboard.
    return _cached(("tmux", session), _TMUX_TTL, probe)


def _gpu_rows(indices: set[int] | None = None) -> list[tuple[int, float, float, float, int]]:
    def query() -> list[tuple[int, float, float, float, int]]:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        if result.returncode != 0:
            return []
        rows = []
        for line in result.stdout.splitlines():
            try:
                raw = [part.strip() for part in line.split(",")]
                rows.append(
                    (
                        int(raw[0]),
                        float(raw[1]),
                        float(raw[2]),
                        float(raw[3]),
                        int(raw[4]),
                    )
                )
            except (ValueError, IndexError):
                continue
        return rows

    # nvidia-smi on a saturated host can take a noticeable moment; one call
    # serves every lane in the frame, and stays valid for a few frames.
    rows = _cached(("gpus",), _GPU_TTL, query)
    return [row for row in rows if indices is None or row[0] in indices]


def _lane_session(snapshot: LaneSnapshot, tmux_prefix: str | None) -> str:
    recorded = snapshot.record.get("tmux_session")
    if isinstance(recorded, str) and recorded:
        return recorded
    return f"{tmux_prefix}-{snapshot.lane}" if tmux_prefix else snapshot.lane


def _lane_gpus(snapshot: LaneSnapshot) -> list[int]:
    return [
        int(raw.strip())
        for raw in str(snapshot.record.get("gpu_visibility", "")).split(",")
        if raw.strip().isdigit()
    ]


def _health(snapshot: LaneSnapshot, alive: bool | None) -> Text:
    jobs = _job_records(snapshot.record)
    failed = any(job.get("status") in FAILED_STATUSES for job in jobs) or bool(
        snapshot.record.get("failure")
    )
    if failed:
        return Text("✗ failed", style="bold red")
    if snapshot.active_job is not None:
        if alive is False:
            # A lane that claims to be running with no tmux session behind it is
            # the one state worth shouting about.
            return Text("⚠ no tmux", style="bold red")
        status = str(snapshot.active_job.get("status", "active"))
        label = {"training": "training", "evaluating": "eval", "benchmarking": "bench"}.get(
            status, status
        )
        return Text(f"● {label}", style="bold green" if status == "training" else "bold cyan")
    if jobs and all(job.get("status") in COMPLETED_STATUSES for job in jobs):
        return Text("✓ done", style="green")
    return Text(f"○ {snapshot.record.get('status', 'idle')}", style="dim")


def _age_text(stage: StageSnapshot | None, now: datetime) -> Text:
    """Seconds since the last logged scalar — the one cell that moves every tick."""
    if stage is None or stage.last_update is None:
        return Text("—", style="dim")
    seconds = max(0.0, (now - stage.last_update).total_seconds())
    if seconds < 300:
        style = "green"
    elif seconds < 900:
        style = "yellow"
    else:
        style = "bold red"
    return Text(_format_short_duration(seconds), style=style)


def _miou_text(stage: StageSnapshot | None, width: int) -> Text:
    point = stage.scalars.get("val/miou") if stage else None
    if point is None:
        return Text("—", style="dim")
    text = Text(f"{100 * point.value:.2f}%", style="bold green")
    # Validation lags training, so the step the number came from is part of the
    # number: without it a stale mIoU reads as a live one.
    suffix = f" @{point.step + 1:,}"
    if len(text.plain) + len(suffix) <= width:
        text.append(suffix, style="dim")
    return text


def _gpu_text(snapshot: LaneSnapshot, rows: dict[int, tuple[float, float, float, int]]) -> Text:
    measured = [rows[index] for index in _lane_gpus(snapshot) if index in rows]
    if not measured:
        return Text("—", style="dim")
    util = sum(item[0] for item in measured) / len(measured)
    used = sum(item[1] for item in measured) / 1024
    temp = max(item[3] for item in measured)
    style = "red" if temp >= 80 else "green" if util >= 10 else "yellow"
    return Text(f"{util:3.0f}% {used:4.1f}G {temp}°", style=style)


@dataclass(frozen=True)
class _Column:
    key: str
    header: str
    width: int | None = None
    justify: str = "left"
    # 0 is always kept; higher numbers are dropped first as the window narrows.
    priority: int = 0


_BAR_MIN_WIDTH = 10
_COLUMNS: tuple[_Column, ...] = (
    _Column("lane", "LANE", width=5),
    _Column("state", "", width=10),
    _Column("job", "CURRENT JOB", width=32),
    _Column("queue", "QUEUE", width=11, priority=3),
    _Column("bar", "PROGRESS"),
    _Column("step", "ITERATIONS", width=19, justify="right"),
    _Column("loss", "LOSS", width=7, justify="right", priority=2),
    _Column("miou", "VAL mIoU", width=14, justify="right", priority=1),
    _Column("rate", "it/s", width=5, justify="right", priority=2),
    _Column("eta", "LEFT", width=7, justify="right"),
    _Column("gpu", "GPU", width=14, justify="right", priority=4),
    _Column("age", "AGE", width=5, justify="right"),
)
_JOB_MIN_WIDTH = 14


def _plan_columns(available: int) -> list[_Column]:
    """Choose the widest column set that fits, dropping the least useful first."""

    def required(columns: Iterable[_Column]) -> int:
        columns = list(columns)
        return sum(column.width or _BAR_MIN_WIDTH for column in columns) + 2 * len(columns)

    columns = list(_COLUMNS)
    for group in sorted({column.priority for column in _COLUMNS if column.priority}, reverse=True):
        if required(columns) <= available:
            break
        columns = [column for column in columns if column.priority != group]
    overflow = required(columns) - available
    if overflow > 0:
        # Model names are long but recognisable from their prefix, so the job
        # column is the last thing to give ground.
        job = next(column for column in columns if column.key == "job")
        shrunk = max(_JOB_MIN_WIDTH, (job.width or _JOB_MIN_WIDTH) - overflow)
        columns = [
            _Column(job.key, job.header, shrunk, job.justify, job.priority)
            if column.key == "job"
            else column
            for column in columns
        ]
    return columns


def _lane_cells(
    snapshot: LaneSnapshot,
    tmux_prefix: str | None,
    gpus: dict[int, tuple[float, float, float, int]],
    now: datetime,
    widths: dict[str, int],
) -> dict[str, Any]:
    alive = _tmux_alive(_lane_session(snapshot, tmux_prefix))
    jobs = _job_records(snapshot.record)
    stage = snapshot.stage
    active = snapshot.active_job

    if active is not None:
        job_text = Text(_truncate(_job_label(active), widths["job"]), style="white")
    elif jobs and all(job.get("status") in COMPLETED_STATUSES for job in jobs):
        job_text = Text("lane complete", style="dim green")
    else:
        job_text = Text("—", style="dim")

    step = stage.step if stage and stage.step is not None else None
    total = stage.total_steps if stage and stage.total_steps else None
    if step is not None and total:
        bar: Any = ProgressBar(
            total=total,
            completed=step,
            complete_style="cyan",
            finished_style="green",
            style="grey27",
        )
        step_text = Text.assemble(
            (f"{step:>7,}", "white"),
            ("/", "dim"),
            (f"{total:,}", "dim"),
            (f" {100 * step / total:3.0f}%", "bold cyan"),
        )
    else:
        bar = Align.center(
            Text("waiting for first scalar" if active is not None else "—", style="dim")
        )
        step_text = Text("—", style="dim")

    return {
        "lane": Text(snapshot.lane.upper(), style="bold"),
        "state": _health(snapshot, alive),
        "job": job_text,
        "queue": _queue_text(jobs, widths.get("queue", 11)),
        "bar": bar,
        "step": step_text,
        "loss": Text(_metric(stage, "train/loss"), style="white" if stage else "dim"),
        "miou": _miou_text(stage, widths.get("miou", 14)),
        "rate": Text(
            f"{stage.rate:.2f}" if stage and stage.rate else "—",
            style="white" if stage and stage.rate else "dim",
        ),
        "eta": Text(
            _format_short_duration(stage.eta_seconds) if stage else "—",
            style="magenta" if stage and stage.eta_seconds else "dim",
        ),
        "gpu": _gpu_text(snapshot, gpus),
        "age": _age_text(stage, now),
    }


def _lane_table(
    snapshots: list[LaneSnapshot],
    tmux_prefix: str | None,
    show_gpus: bool,
    width: int,
    now: datetime,
) -> Table:
    columns = _plan_columns(width)
    widths = {column.key: column.width or _BAR_MIN_WIDTH for column in columns}
    gpus: dict[int, tuple[float, float, float, int]] = {}
    if show_gpus and any(column.key == "gpu" for column in columns):
        configured = {index for item in snapshots for index in _lane_gpus(item)}
        gpus = {row[0]: row[1:] for row in _gpu_rows(configured or None)}

    table = Table(
        box=None,
        expand=True,
        pad_edge=False,
        padding=(0, 1),
        header_style="bold grey58",
    )
    for column in columns:
        table.add_column(
            column.header,
            width=column.width,
            ratio=1 if column.width is None else None,
            justify=column.justify,
            no_wrap=True,
            overflow="ellipsis",
        )
    for snapshot in snapshots:
        cells = _lane_cells(snapshot, tmux_prefix, gpus, now, widths)
        table.add_row(*(cells[column.key] for column in columns))
    return table


def _campaign_header(
    campaign: Path,
    snapshots: list[LaneSnapshot],
    timezone: tzinfo,
    now: datetime,
    tick: int,
) -> Table:
    total_jobs = sum(len(_job_records(item.record)) for item in snapshots)
    completed = sum(item.completed for item in snapshots)
    running = sum(1 for item in snapshots if item.active_job is not None)
    campaign_eta = (
        max(item.lane_eta_seconds for item in snapshots if item.lane_eta_seconds is not None)
        if snapshots and all(item.lane_eta_seconds is not None for item in snapshots)
        else None
    )
    header = Table.grid(expand=True)
    header.add_column(justify="left", ratio=2)
    header.add_column(justify="center", ratio=2)
    header.add_column(justify="right", ratio=3)
    header.add_row(
        Text.assemble(
            ("SEGMENTARY ", "bold cyan"),
            # The spinner advances on every frame, so the view is visibly alive
            # even while the training numbers wait on the next logged scalar.
            (_SPINNER[tick % len(_SPINNER)], "bold green"),
            (f"  {campaign.name}", "white"),
        ),
        Text.assemble(
            (f"{completed}", "bold"),
            (f"/{total_jobs} jobs", "grey58"),
            (f"   {running}/{len(snapshots)} lanes running", "grey58"),
        ),
        Text.assemble(
            (
                f"expected finish {_local_time(now + timedelta(seconds=campaign_eta), timezone)}"
                if campaign_eta is not None
                else "expected finish estimating…",
                "magenta" if campaign_eta is not None else "dim",
            ),
            ("   ", ""),
            (_clock(now, timezone), "bold white"),
        ),
    )
    return header


def _results_line(snapshots: list[LaneSnapshot], width: int) -> Text | None:
    results: list[tuple[float, str]] = []
    for snapshot in snapshots:
        for job in _job_records(snapshot.record):
            if job.get("status") not in COMPLETED_STATUSES:
                continue
            value = _result_miou(job)
            if value is not None:
                results.append((value, f"{_job_label(job)} {100 * value:.2f}%"))
    if not results:
        return None
    results.sort(key=lambda item: item[0], reverse=True)
    text = Text("Validated mIoU: ", style="grey58")
    used = len(text.plain)
    for index, (_, label) in enumerate(results):
        addition = ("  •  " if index else "") + label
        if used + len(addition) > width - 8:
            text.append(f"  (+{len(results) - index} more)", style="dim")
            break
        text.append(addition, style="green")
        used += len(addition)
    return text


def _attention_lines(snapshots: list[LaneSnapshot], budget: int) -> list[str]:
    messages = [
        str(item.record.get("failure")) for item in snapshots if item.record.get("failure")
    ] + [warning for item in snapshots for warning in item.warnings]
    shown = messages[:budget]
    if len(messages) > len(shown):
        shown.append(f"…and {len(messages) - len(shown)} more")
    return shown


def _attention_panel(lines: list[str]) -> Panel:
    return Panel(
        "\n".join(lines),
        title=" attention ",
        title_align="left",
        border_style="yellow",
        padding=(0, 1),
    )


_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_LEGEND = (
    "● training   ✓ done   · pending   ✗ failed      "
    "AGE = time since the last logged scalar (training logs every 50 steps)      "
    "read-only view • Ctrl-C closes the dashboard, not training"
)


class Dashboard:
    """A one-screen campaign view that adapts to the terminal it is printed to."""

    def __init__(
        self,
        campaign: Path,
        snapshots: list[LaneSnapshot],
        timezone: tzinfo,
        tmux_prefix: str | None,
        show_gpus: bool,
        *,
        tick: int = 0,
        limit_height: bool = False,
    ) -> None:
        self.campaign = campaign
        self.snapshots = snapshots
        self.timezone = timezone
        self.tmux_prefix = tmux_prefix
        self.show_gpus = show_gpus
        self.tick = tick
        self.limit_height = limit_height

    def _visible_lanes(self, height: int, extra_lines: int) -> tuple[list[LaneSnapshot], int]:
        if not self.limit_height:
            return self.snapshots, 0
        # header + rule + column header + legend + one line of slack, plus
        # whatever the attention panel and the results line need.
        budget = height - (5 + extra_lines)
        if budget >= len(self.snapshots):
            return self.snapshots, 0
        budget = max(1, budget - 1)  # room for the "hidden lanes" note

        def needs_attention(item: LaneSnapshot) -> bool:
            return bool(
                item.active_job is not None
                or item.warnings
                or item.record.get("failure")
                or any(job.get("status") in FAILED_STATUSES for job in _job_records(item.record))
            )

        # Lanes that need attention keep their seat, but the survivors are
        # re-sorted into lane order so a given lane never moves between frames.
        ranked = sorted(
            range(len(self.snapshots)),
            key=lambda index: (not needs_attention(self.snapshots[index]), index),
        )
        kept = sorted(ranked[:budget])
        return [self.snapshots[index] for index in kept], len(self.snapshots) - len(kept)

    def _renderables(self, width: int, height: int) -> Iterator[Any]:
        now = datetime.now(UTC)
        if not self.snapshots:
            yield Panel(
                f"No readable lane_*_status.json files under\n{self.campaign}",
                title=" segmentary progress ",
                border_style="yellow",
            )
            return

        attention = _attention_lines(self.snapshots, budget=3)
        results = _results_line(self.snapshots, width)
        extra = (len(attention) + 2 if attention else 0) + (0 if results is None else 1)
        lanes, hidden = self._visible_lanes(height, extra)

        yield _campaign_header(self.campaign, self.snapshots, self.timezone, now, self.tick)
        yield Rule(style="grey30")
        yield _lane_table(lanes, self.tmux_prefix, self.show_gpus, width, now)
        if hidden:
            yield Text(
                f"  …{hidden} idle lane(s) hidden — the window is too short to show them",
                style="dim",
            )
        if results is not None:
            yield results
        if attention:
            yield _attention_panel(attention)
        yield Align.center(Text(_LEGEND, style="dim"))

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield from self._renderables(options.max_width, console.size.height)


def render_dashboard(
    campaign: Path,
    snapshots: list[LaneSnapshot],
    timezone: tzinfo,
    tmux_prefix: str | None,
    show_gpus: bool,
    *,
    tick: int = 0,
    limit_height: bool = False,
) -> Dashboard:
    return Dashboard(
        campaign,
        snapshots,
        timezone,
        tmux_prefix,
        show_gpus,
        tick=tick,
        limit_height=limit_height,
    )


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise argparse.ArgumentTypeError(f"unknown IANA timezone: {value}") from exc


MINIMUM_REFRESH = 0.25


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Open a read-only Rich dashboard over a queued Segmentary campaign. "
            "Every lane is one row, so the whole campaign fits in one window. "
            "It observes status and TensorBoard files without loading models or "
            "affecting training."
        )
    )
    parser.add_argument("campaign", type=Path, help="campaign directory with lane_*_status.json")
    parser.add_argument("--once", action="store_true", help="print one snapshot and exit")
    parser.add_argument(
        "--refresh", type=float, default=1.0, help="live refresh interval in seconds (default: 1)"
    )
    parser.add_argument(
        "--timezone",
        type=_timezone,
        default=datetime.now().astimezone().tzinfo or UTC,
        metavar="AREA/CITY",
        help="display timezone (default: local timezone)",
    )
    parser.add_argument("--no-gpus", action="store_true", help="do not call nvidia-smi")
    parser.add_argument(
        "--tmux-prefix",
        default=None,
        help="fallback session prefix when old lane status lacks tmux_session",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    campaign = args.campaign.expanduser().resolve()
    if not campaign.is_dir():
        print(f"segmentary-progress: campaign directory not found: {campaign}", file=sys.stderr)
        return 2
    if args.refresh < MINIMUM_REFRESH:
        print(
            f"segmentary-progress: --refresh must be at least {MINIMUM_REFRESH} seconds",
            file=sys.stderr,
        )
        return 2
    console = Console()

    def snapshot(tick: int, *, limit_height: bool) -> Dashboard:
        return render_dashboard(
            campaign,
            inspect_campaign(campaign),
            args.timezone,
            args.tmux_prefix,
            not args.no_gpus,
            tick=tick,
            limit_height=limit_height,
        )

    if args.once:
        console.print(snapshot(0, limit_height=False))
        return 0
    try:
        with Live(
            snapshot(0, limit_height=True),
            console=console,
            refresh_per_second=4,
            screen=True,
            transient=False,
        ) as live:
            tick = 0
            while True:
                time.sleep(args.refresh)
                tick += 1
                live.update(snapshot(tick, limit_height=True), refresh=True)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
