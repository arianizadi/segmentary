"""Live RTIS controller: observe existing state and TensorBoard telemetry only."""

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

from segmentary.campaign_progress import CampaignProgress, duration, number, value
from segmentary.campaign_progress import DataTable as DataTable


def failure_detail(root, state):
    detail = str(state.get("error") or "No error message recorded")
    path = root / "logs" / (state["name"] + ".log")
    if path.is_file():
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 16384))
            tail = stream.read().decode("utf-8", errors="replace")
        lines = [
            line.strip()
            for line in tail.splitlines()
            if re.match(r"^[\w.]+(?:Error|Exception):", line.strip())
        ]
        if lines:
            detail = lines[-1]
    phase = state.get("collection_phase", "job")
    return f"{phase}: {detail}"


class Telemetry:
    def __init__(self, root):
        self.root = root
        self.readers = {}
        self.show_gpus = True

    def read(self, selected=None):
        rows, errors = [], []
        for path in sorted((self.root / "state").glob("*.json")):
            try:
                state = json.loads(path.read_text())
                if state["status"] == "failed":
                    state["failure_detail"] = failure_detail(self.root, state)
                state["scalars"] = {}
                state["loss_history"] = []
                state["history"] = {}
                if state["status"] not in ("queued", "completed") or state["name"] == selected:
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
                                state["history"][tag] = sorted(
                                    [p for p in points if math.isfinite(p.value)],
                                    key=lambda p: p.step,
                                )
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
            if row["status"] not in ("queued", "completed") or row["name"] == selected
        }
        self.readers = {k: v for k, v in self.readers.items() if any(n in k for n in active_names)}
        gpus = {}
        try:
            if not self.show_gpus:
                return rows, gpus, errors
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


class RTISProfile:
    label = "RTIS"
    refresh_seconds = 3
    columns: ClassVar = [
        ("GPU", 3),
        ("Model / protocol", 30),
        ("Phase", 10),
        ("Iterations", 11),
        ("Progress", 15),
        ("opt/s", 6),
        ("Train ETA*", 9),
        ("Loss", 6),
        ("Age", 8),
    ]
    charts: ClassVar = [
        ("TRAINING LOSS", "train/loss", False),
        ("VALIDATION mIoU", "val/miou", True),
        ("MUD-PUMPING IoU", "val_iou/mud-pumping", True),
        ("OPTIMIZER STEPS / SECOND", "train/optimizer_steps_per_sec", False),
    ]
    note = "Ctrl+b then d: detach · Enter: details · Esc: overview · A/T/C/Q/F: status filters\n*Training ETA excludes final evaluation/profiling. Rates are run averages."

    def metric_format(self, tag):
        return ".2%" if tag.startswith(("val/", "val_iou/")) else ".5g"

    def cells(self, row, now):
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
        training = row["status"] == "training"
        short = row["name"].split("--")
        protocol = (
            {
                "rtis_only": "RTIS",
                "cityscapes_to_rtis": "CS→RTIS",
                "railsem19_to_rtis": "RS→RTIS",
                "cityscapes_to_railsem19_to_rtis": "CS→RS→RTIS",
            }.get(short[1], short[1])
            if len(short) > 1
            else "RTIS"
        )
        return (
            str(row.get("gpu", "—")),
            Text(short[0] + " / " + protocol, overflow="ellipsis", no_wrap=True),
            Text(
                row["status"],
                style="red" if row["status"] == "failed" else "cyan" if training else "yellow",
            ),
            f"{int(iteration):,}/{total:,}" if total else "—",
            Text(bar, style="#66e3c4"),
            number(value(row, "train/optimizer_steps_per_sec")) if training else "—",
            duration(value(row, "train/eta_seconds")) if training else "—",
            number(value(row, "train/loss")),
            Text(duration(age), style="yellow" if age is not None and age > 180 else "dim"),
        )

    def detail(self, row, *, focus=False):
        val = row["scalars"].get("val/miou")
        return (
            row["name"]
            + "\n"
            + f"{row['status'].upper()} · Step {number(value(row, 'train/iteration'), '.0f')} · Progress {number(value(row, 'train/progress'), '.1%')} · Elapsed {duration(row.get('elapsed'))} · GPU {row.get('gpu_text', '—')}\n"
            + f"Val mIoU {number(value(row, 'val/miou'), '.2%')} · Mud IoU {number(value(row, 'val_iou/mud-pumping'), '.2%')} · Last validation step {val.step + 1 if val else '—'} · Learning rate {number(value(row, 'train/lr'), '.3g')}\n"
            + f"Training ETA {duration(value(row, 'train/eta_seconds')) if row['status'] == 'training' else '—'} · Images/s {number(value(row, 'train/examples_per_sec'), '.1f')}"
            + (
                "\n" + str(row.get("failure_detail") or row.get("error"))
                if row.get("error")
                else ""
            )
        )


class RTISProgress(CampaignProgress):
    """Compatibility name backed by the shared campaign UI."""

    def __init__(self, root, *, refresh=None, show_gpus=True):
        super().__init__(root, Telemetry(root), RTISProfile(), refresh=refresh)
        self.telemetry.show_gpus = show_gpus


def run(root):
    RTISProgress(root).run()


def ensure_controller(root, repo, python, session="rtis-fullstats-controller"):
    """Compatibility wrapper around the shared automatic dashboard launcher."""
    from segmentary.campaign_dashboard import ensure_dashboard

    return ensure_dashboard(root, repo, python, session=session)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    if not (args.campaign / "state").is_dir():
        parser.error("campaign must contain a state directory")
    run(args.campaign.resolve())
