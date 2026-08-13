"""A read-only, human-friendly dashboard for queued Segmentary campaigns.

The dashboard deliberately observes files that training already writes.  It
never imports a model, opens a checkpoint, reserves a GPU, or signals a trainer.
That makes it safe to start beside an in-progress multi-GPU campaign::

    segmentary-progress runs/my_campaign

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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
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
    try:
        return [path for path in run_dir.rglob("events.out.tfevents*") if path.is_file()]
    except OSError:
        return []


def _stage_dir(event_path: Path) -> Path:
    # Current: <stage>/tensorboard/events.out.tfevents...
    # Legacy:  <stage>/lightning_logs/version_N/events.out.tfevents...
    if event_path.parent.name == "tensorboard":
        return event_path.parent.parent
    if event_path.parent.parent.name == "lightning_logs":
        return event_path.parent.parent.parent
    return event_path.parent


def _read_total_steps(stage_dir: Path) -> int | None:
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


def _load_event_scalars(event_paths: list[Path]) -> dict[str, list[ScalarPoint]]:
    """Merge scalar summaries across rollovers/resumes of one active stage."""
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    result: dict[str, list[ScalarPoint]] = {}
    for event_path in event_paths:
        accumulator = EventAccumulator(str(event_path), size_guidance={"scalars": 0})
        accumulator.Reload()
        available = set(accumulator.Tags().get("scalars", []))
        for tag in HEADLINE_TAGS:
            if tag not in available:
                continue
            result.setdefault(tag, []).extend(
                ScalarPoint(int(item.step), float(item.value), float(item.wall_time))
                for item in accumulator.Scalars(tag)
            )
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


def _local_time(value: datetime | None, timezone: tzinfo) -> str:
    return "—" if value is None else value.astimezone(timezone).strftime("%a %I:%M %p %Z")


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
    record, _ = _read_json(path)
    metrics = record.get("metrics") if record else None
    value = metrics.get("miou") if isinstance(metrics, dict) else None
    return float(value) if isinstance(value, int | float) and math.isfinite(value) else None


def _queue_text(jobs: list[dict[str, Any]]) -> Text:
    text = Text()
    for index, job in enumerate(jobs):
        if index:
            text.append("  →  ", style="dim")
        status = job.get("status")
        model = job.get("model")
        protocol = job.get("protocol", job.get("curriculum", "?"))
        slug = (
            f"{model} / {protocol} s{job.get('seed', '?')}"
            if model
            else f"{protocol} s{job.get('seed', '?')}"
        )
        if status in COMPLETED_STATUSES:
            text.append("✓ ", style="bold green")
            text.append(slug, style="green")
        elif status in ACTIVE_STATUSES:
            text.append("▶ ", style="bold cyan")
            text.append(slug, style="bold white")
        elif status in FAILED_STATUSES:
            text.append("✗ ", style="bold red")
            text.append(slug, style="red")
        else:
            text.append("○ ", style="dim")
            text.append(slug, style="dim")
    return text


def _tmux_alive(session: str) -> bool | None:
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


def _gpu_rows(indices: set[int] | None = None) -> list[tuple[int, float, float, float, int]]:
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
            index = int(raw[0])
            if indices is not None and index not in indices:
                continue
            rows.append((index, float(raw[1]), float(raw[2]), float(raw[3]), int(raw[4])))
        except (ValueError, IndexError):
            continue
    return rows


def _lane_panel(snapshot: LaneSnapshot, timezone: tzinfo, tmux_prefix: str | None) -> Panel:
    jobs = _job_records(snapshot.record)
    total_jobs = len(jobs)
    failed = any(job.get("status") in FAILED_STATUSES for job in jobs) or bool(
        snapshot.record.get("failure")
    )
    recorded_session = snapshot.record.get("tmux_session")
    session = (
        recorded_session
        if isinstance(recorded_session, str) and recorded_session
        else f"{tmux_prefix}-{snapshot.lane}"
        if tmux_prefix
        else snapshot.lane
    )
    alive = _tmux_alive(session)
    health = (
        "FAILED"
        if failed
        else "RUNNING"
        if snapshot.active_job
        else snapshot.record.get("status", "—")
    )
    health_style = "bold red" if failed else "bold green"

    header = Table.grid(expand=True)
    header.add_column(ratio=3)
    header.add_column(justify="right", ratio=2)
    tmux = "tmux unknown" if alive is None else "tmux alive" if alive else "tmux missing"
    header.add_row(
        Text.assemble(
            (f"● {health}", health_style), f"   GPUs {snapshot.record.get('gpu_visibility', '—')}"
        ),
        f"{snapshot.completed}/{total_jobs} jobs complete   •   {tmux}",
    )

    content: list[Any] = [header, Text(), _queue_text(jobs)]
    active = snapshot.active_job
    if active is not None:
        content.append(Text())
        phase = str(active.get("status", "active")).upper()
        content.append(
            Text.assemble(
                (f"{phase}  ", "bold cyan"),
                (
                    (
                        f"{active.get('model')} / "
                        f"{active.get('protocol', active.get('curriculum'))}  "
                        f"seed {active.get('seed')}"
                        if active.get("model")
                        else f"{active.get('curriculum')}  seed {active.get('seed')}"
                    ),
                    "bold white",
                ),
                f"   elapsed {_format_duration(_elapsed(active))}",
            )
        )
        if snapshot.stage is not None:
            stage = snapshot.stage
            step = stage.step or 0
            total = stage.total_steps or 0
            percent = 100 * step / total if total else 0
            progress = Table.grid(expand=True, padding=(0, 1))
            progress.add_column(width=24)
            progress.add_column(ratio=1)
            progress.add_column(width=47, justify="right")
            progress.add_row(
                f"{stage.name} • iterations",
                ProgressBar(total=max(total, 1), completed=step, width=None),
                f"{step:,} / {total:,}  •  {percent:5.1f}%  •  "
                f"{_format_duration(stage.eta_seconds)} left",
            )
            content.extend([Text(), progress])

            metrics = Table.grid(expand=True, padding=(0, 2))
            for _ in range(7):
                metrics.add_column(justify="center")
            rate = f"{stage.rate:.2f} it/s" if stage.rate else "estimating…"
            metrics.add_row(
                f"loss\n[bold]{_metric(stage, 'train/loss')}[/]",
                f"learning rate\n[bold]{_metric(stage, 'train/lr', scientific=True)}[/]",
                f"val mIoU\n[bold green]{_metric(stage, 'val/miou', percent=True)}[/]",
                f"val mean acc\n[bold]{_metric(stage, 'val/macc', percent=True)}[/]",
                f"pixel accuracy\n[bold]{_metric(stage, 'val/pixel_acc', percent=True)}[/]",
                f"boundary F1\n[bold]{_metric(stage, 'val/boundary_f1', percent=True)}[/]",
                f"throughput\n[bold]{rate}[/]",
            )
            val_point = stage.scalars.get("val/miou")
            freshness = Text(
                f"Live scalar step {step:,}; validation through step "
                f"{val_point.step + 1:,}.  "
                f"Last scalar {_local_time(stage.last_update, timezone)}."
                if val_point
                else f"Live scalar step {step:,}; waiting for the first validation.",
                style="dim",
            )
            content.extend([metrics, Align.center(freshness)])

    completed_results = []
    for job in jobs:
        if job.get("status") not in COMPLETED_STATUSES:
            continue
        value = _result_miou(job)
        if value is not None:
            completed_results.append(
                f"{job.get('model')} / {job.get('protocol')} s{job.get('seed')} {100 * value:.2f}%"
                if job.get("model")
                else f"{job.get('curriculum')} s{job.get('seed')} {100 * value:.2f}%"
            )
    if completed_results:
        content.extend(
            [Text(), Text("Validated mIoU: " + "  •  ".join(completed_results), style="dim")]
        )

    lane_finish = datetime.now(UTC) + timedelta(seconds=snapshot.lane_eta_seconds or 0)
    eta_text = (
        f"Expected lane finish: {_local_time(lane_finish, timezone)} "
        f"({_format_duration(snapshot.lane_eta_seconds)} remaining)"
        if snapshot.lane_eta_seconds is not None
        else "Expected lane finish: estimating from completed jobs…"
    )
    content.extend([Text(), Text(eta_text, style="bold magenta")])
    return Panel(Group(*content), title=f" Lane {snapshot.lane.upper()} ", border_style="cyan")


def _elapsed(job: dict[str, Any]) -> float | None:
    started = _parse_datetime(job.get("started_at"))
    return None if started is None else max(0, (datetime.now(UTC) - started).total_seconds())


def render_dashboard(
    campaign: Path,
    snapshots: list[LaneSnapshot],
    timezone: tzinfo,
    tmux_prefix: str | None,
    show_gpus: bool,
) -> Group:
    now = datetime.now(UTC)
    total_jobs = sum(len(_job_records(item.record)) for item in snapshots)
    completed = sum(item.completed for item in snapshots)
    campaign_eta = (
        max(item.lane_eta_seconds for item in snapshots if item.lane_eta_seconds is not None)
        if snapshots and all(item.lane_eta_seconds is not None for item in snapshots)
        else None
    )
    finish = now + timedelta(seconds=campaign_eta or 0)
    title = Text.assemble(
        ("SEGMENTARY  ", "bold cyan"),
        ("LIVE TRAINING", "bold white"),
        f"   {campaign.name}",
    )
    summary = Table.grid(expand=True)
    summary.add_column(justify="left")
    summary.add_column(justify="center")
    summary.add_column(justify="right")
    summary.add_row(
        title,
        f"[bold]{completed}/{total_jobs}[/] jobs complete",
        (
            f"expected finish [bold magenta]{_local_time(finish, timezone)}[/]"
            if campaign_eta is not None
            else "expected finish estimating…"
        ),
    )
    renderables: list[Any] = [
        Panel(summary, subtitle=_local_time(now, timezone), border_style="blue")
    ]
    renderables.extend(_lane_panel(item, timezone, tmux_prefix) for item in snapshots)

    if show_gpus:
        configured: set[int] = set()
        for item in snapshots:
            for raw in str(item.record.get("gpu_visibility", "")).split(","):
                if raw.strip().isdigit():
                    configured.add(int(raw))
        rows = _gpu_rows(configured or None)
        if rows:
            table = Table(expand=True, box=None, padding=(0, 2))
            table.add_column("GPU", style="bold")
            table.add_column("util", justify="right")
            table.add_column("memory", justify="right")
            table.add_column("temp", justify="right")
            table.add_column("state")
            for index, util, used, total, temp in rows:
                state = "● training" if util >= 10 else "○ between phases"
                style = "green" if temp < 80 else "red"
                table.add_row(
                    str(index),
                    f"{util:.0f}%",
                    f"{used / 1024:.1f}/{total / 1024:.1f} GiB",
                    f"{temp}°C",
                    Text(state, style=style),
                )
            renderables.append(Panel(table, title=" GPU health ", border_style="green"))

    warnings = [warning for item in snapshots for warning in item.warnings]
    failures = [str(item.record.get("failure")) for item in snapshots if item.record.get("failure")]
    if warnings or failures:
        renderables.append(
            Panel("\n".join([*failures, *warnings]), title=" Attention ", border_style="yellow")
        )
    renderables.append(
        Align.center(
            Text(
                "Read-only view • refreshes from TensorBoard/status files • Ctrl-C exits only the dashboard",
                style="dim",
            )
        )
    )
    return Group(*renderables)


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise argparse.ArgumentTypeError(f"unknown IANA timezone: {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Open a read-only Rich dashboard over a queued Segmentary campaign. "
            "It observes status and TensorBoard files without loading models or "
            "affecting training."
        )
    )
    parser.add_argument("campaign", type=Path, help="campaign directory with lane_*_status.json")
    parser.add_argument("--once", action="store_true", help="print one snapshot and exit")
    parser.add_argument(
        "--refresh", type=float, default=10.0, help="live refresh interval (seconds)"
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
    if args.refresh < 1:
        print("segmentary-progress: --refresh must be at least 1 second", file=sys.stderr)
        return 2
    console = Console()

    def snapshot() -> Group:
        lanes = inspect_campaign(campaign)
        if not lanes:
            return Group(
                Panel(
                    f"No readable lane_*_status.json files under\n{campaign}",
                    title=" Segmentary progress ",
                    border_style="yellow",
                )
            )
        return render_dashboard(
            campaign,
            lanes,
            args.timezone,
            args.tmux_prefix,
            not args.no_gpus,
        )

    if args.once:
        console.print(snapshot())
        return 0
    try:
        with Live(snapshot(), console=console, refresh_per_second=4, screen=True) as live:
            while True:
                time.sleep(args.refresh)
                live.update(snapshot(), refresh=True)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
