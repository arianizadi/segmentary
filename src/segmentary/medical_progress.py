"""Medical telemetry adapter for Segmentary's shared read-only campaign UI.

Reads the existing validated report collector, progress JSON and nnU-Net text
logs. Never loads images, masks, models or checkpoints, and never imports torch.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import math
import re
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from rich.text import Text

from segmentary.campaign_progress import CampaignProgress, duration, number, value
from segmentary.progress import ScalarPoint


def locations(root):
    root = Path(root).resolve()
    state = root if (root / "campaign-binding.json").is_file() else root / "state"
    binding = state / "campaign-binding.json"
    if binding.is_file():
        document = json.loads(binding.read_text())
        spec = document.get("spec_path")
        if spec:
            return Path(spec), state
        candidate = state.parent / "campaign.json"
        return (candidate if candidate.is_file() else binding), state
    return root / "campaign.json", state


class JsonCache:
    """Epoch files are immutable; avoid decoding the whole history every refresh."""

    def __init__(self):
        self.entries = {}

    def read(self, path):
        path = Path(path)
        if not path.is_file():
            return {}
        stat = path.stat()
        signature = stat.st_ino, stat.st_size, stat.st_mtime_ns
        cached = self.entries.get(path)
        if cached and cached[0] == signature:
            return cached[1]
        value = json.loads(
            path.read_text(),
            parse_constant=lambda text: (_ for _ in ()).throw(
                ValueError(f"Nonfinite JSON: {text}")
            ),
        )
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        self.entries[path] = signature, value
        while len(self.entries) > 8192:
            self.entries.pop(next(iter(self.entries)))
        return value


def alive(pid, expected_start=None):
    """Linux PID identity check; no signals are sent, including signal zero."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[0] != "Z" and (expected_start is None or fields[19] == str(expected_start))
    except (OSError, IndexError):
        return False


def stamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def tail(path, limit=2 * 1024 * 1024):
    with Path(path).open("rb") as stream:
        stream.seek(max(0, Path(path).stat().st_size - limit))
        return stream.read().decode("utf-8", errors="replace")


def parse_nnunet(text):
    """Count an epoch only once its completion/timing line was recorded."""
    current = None
    completed = {}
    errors = []
    for line in text.splitlines():
        match = re.search(r"(?:^|:\s)Epoch (\d+)\s*$", line)
        if match:
            current = {"epoch": int(match[1]) + 1}
            continue
        if current is None:
            continue
        match = re.search(r"train_loss\s+([-+\deE.]+)", line)
        if match:
            loss = float(match[1])
            if math.isfinite(loss):
                current["loss"] = loss
        match = re.search(r"Pseudo dice\s+(\[.*\])", line)
        if match:
            payload = re.sub(r"(?:np\.)?float(?:16|32|64)\(([^)]+)\)", r"\1", match[1])
            try:
                scores = ast.literal_eval(payload)
                if len(scores) != 2 or any(
                    type(item) not in (int, float) or not math.isfinite(item) or not 0 <= item <= 1
                    for item in scores
                ):
                    raise ValueError("invalid pseudo Dice")
                current["pancreas_pseudo"], current["mass_pseudo"] = scores
            except (ValueError, SyntaxError, TypeError):
                errors.append("nnU-Net recorded invalid patch pseudo-Dice; values withheld")
        match = re.search(r"Epoch time:\s+([\d.]+)\s+s", line)
        if match:
            current["seconds"] = float(match[1])
            completed[current["epoch"]] = dict(current)
    return {
        "current_epoch": current["epoch"] if current else None,
        "epochs": [completed[key] for key in sorted(completed)],
        "errors": errors,
    }


def add_point(row, tag, val, step, when):
    if val is None or not isinstance(val, (int, float)) or not math.isfinite(val):
        return
    point = ScalarPoint(max(0, int(step) - 1), float(val), when)
    row["scalars"][tag] = point
    row["history"].setdefault(tag, []).append(point)


def score_display(row):
    """Incomplete native evaluations and patch scores never enter Dice columns."""
    evaluation = row.get("evaluation", {})
    if row["status"] == "completed" and evaluation.get("complete_coverage"):
        coverage = evaluation["coverage"]
        return (
            evaluation["mass"]["dice"],
            evaluation["pancreas"]["dice"],
            "final",
            None,
            f"{coverage['valid_prediction_cases']}/{coverage['eligible_cases']}",
        )
    latest = row.get("latest_validation")
    if latest:
        return (
            latest["mass_dice"],
            latest["pancreas_dice"],
            "native",
            latest["step"],
            f"{latest['validation_cases']}/{row['expected_cases']}",
        )
    return None, None, "pending", None, "—"


class MedicalTelemetry:
    def __init__(self, root, *, show_gpus=True, reporter=None):
        self.root = Path(root)
        self.campaign, self.state = locations(root)
        self.cache = JsonCache()
        self.show_gpus = show_gpus
        self.summary = ""
        if reporter is None:
            spec = self.read_record(self.campaign)
            local = Path(__file__).resolve().parents[2] / "scripts/report_medical_campaign.py"
            source = (
                local
                if local.is_file()
                else Path(spec["source_root"]) / "scripts/report_medical_campaign.py"
            )
            module = importlib.util.spec_from_file_location(
                "segmentary_dashboard_medical_report", source
            )
            if module is None or module.loader is None:
                raise RuntimeError("Medical report collector unavailable")
            reporter = importlib.util.module_from_spec(module)
            module.loader.exec_module(reporter)
        self.reporter = reporter
        self.reporter._read = self.read_record

    def read_record(self, path):
        document = self.cache.read(path)
        if Path(path) == self.campaign and "spec" in document:
            return document["spec"]
        return document

    def read(self, selected=None):
        now = time.time()
        snapshot = self.reporter.collect(self.campaign, self.state, now=now)
        spec = self.read_record(self.campaign)
        errors, rows, pseudo = [], [], []
        for original in snapshot["runs"]:
            row = dict(original)
            row.update(
                name=row["id"],
                scalars={},
                history={},
                loss_history=[],
                expected_cases=snapshot["split_counts"]["val"],
            )
            state = self.cache.read(self.state / "runs" / f"{row['id']}.json")
            workspace = Path(state.get("workspace", self.root / "missing"))
            progress = self.cache.read(workspace / "progress.json")
            row["gpu"] = int(row["gpu"]) if row.get("gpu") is not None else None
            row["error"] = state.get("error")
            training = row["status"] == "running" and row.get("stage") == "train"
            row["phase"] = (
                (progress.get("phase", "train") if training else row.get("stage"))
                if row["status"] == "running"
                else row["status"]
            )
            row["sample_time"] = stamp(progress.get("updated_at")) if training else None
            row["health"] = (
                "alive"
                if alive(state.get("cli_pid"), state.get("cli_process_start"))
                else "PID absent"
                if row["status"] == "running"
                else "—"
            )
            if row["status"] == "running" and row["health"] != "alive":
                errors.append(
                    f"{row['model']}: recorded worker PID is absent; controller may be changing stages"
                )
            for curve in row.get("curves", []):
                step = curve["step"]
                when = workspace / "metrics" / f"epoch-{curve['epoch']:05d}.json"
                metric_time = (
                    when.stat().st_mtime if when.is_file() else stamp(row.get("last_update")) or now
                )
                for field, tag in (
                    ("loss", "train/loss"),
                    ("learning_rate", "train/lr"),
                    ("mass_dice", "val/mass_dice"),
                    ("pancreas_dice", "val/pancreas_dice"),
                ):
                    add_point(row, tag, curve.get(field), step, metric_time)
            step = (
                row.get("live_step")
                if row.get("live_step") is not None
                else row.get("completed_steps", 0)
            )
            row["step"] = step
            when = row["sample_time"] or stamp(row.get("last_update")) or now
            for tag, val in (
                ("train/iteration", step),
                ("train/loss", progress.get("loss")),
                ("train/lr", progress.get("learning_rate")),
                ("train/optimizer_steps_per_sec", progress.get("optimizer_steps_per_second")),
            ):
                add_point(row, tag, val, step, when)
            budget = row.get("budget_steps")
            if budget:
                add_point(row, "train/progress", step / budget, step, when)
                started = stamp(state.get("updated_at"))
                if started and row.get("stage") == "train" and step > 0:
                    add_point(
                        row,
                        "train/eta_seconds",
                        (budget - step) * max(0, now - started) / step,
                        step,
                        now,
                    )
            row["progress_text"] = f"{step:,}/{budget:,}" if budget else "—"
            if progress.get("phase") == "validation" and training:
                row["progress_text"] = (
                    f"val {progress.get('completed_cases', 0)}/{progress.get('total_cases', '?')}"
                )
            if row.get("backend") == "nnunet":
                logs = sorted(
                    workspace.glob("nnUNet_results/**/training_log_*.txt"),
                    key=lambda path: path.stat().st_mtime,
                )
                protocol = spec.get("protocol", {}).get("nnunet", {})
                epochs = row.get("recipe", {}).get("num_epochs") or protocol.get(
                    "expected_default_epochs"
                )
                updates = row.get("recipe", {}).get("num_iterations_per_epoch") or protocol.get(
                    "expected_default_updates_per_epoch"
                )
                if logs:
                    parsed = parse_nnunet(tail(logs[-1]))
                    row["nnunet"] = parsed
                    errors.extend(parsed["errors"])
                    nn_epochs = parsed["epochs"]
                    if nn_epochs:
                        latest = nn_epochs[-1]
                        row["progress_text"] = f"{latest['epoch']}/{epochs or '?'} ep"
                        row["sample_time"] = logs[-1].stat().st_mtime
                        for metric in nn_epochs:
                            nn_step = metric["epoch"] * (updates or 1)
                            for field, tag in (
                                ("loss", "train/loss"),
                                ("mass_pseudo", "pseudo/mass_dice"),
                                ("pancreas_pseudo", "pseudo/pancreas_class_dice"),
                            ):
                                add_point(row, tag, metric.get(field), nn_step, row["sample_time"])
                        nn_step = latest["epoch"] * (updates or 1)
                        if epochs:
                            add_point(row, "train/iteration", nn_step, nn_step, row["sample_time"])
                            add_point(
                                row,
                                "train/progress",
                                latest["epoch"] / epochs,
                                nn_step,
                                row["sample_time"],
                            )
                            remaining = (epochs - latest["epoch"]) * statistics.median(
                                item["seconds"] for item in nn_epochs[-10:]
                            )
                            add_point(
                                row, "train/eta_seconds", remaining, nn_step, row["sample_time"]
                            )
                        pseudo.append(
                            f"nnU-Net PATCH pseudo-Dice only · epoch {latest['epoch']}: mass {number(latest.get('mass_pseudo'))} / pancreas CLASS {number(latest.get('pancreas_pseudo'))}; separate from full-volume scores"
                        )
            row["loss_history"] = [point.value for point in row["history"].get("train/loss", [])]
            rows.append(row)
        controller = self.cache.read(self.state / "status.json")
        controller_alive = alive(controller.get("pid"), controller.get("process_start"))
        controller_time = stamp(controller.get("updated_at"))
        publisher = self.cache.read(self.state / "publisher-status.json")
        publisher_time = stamp(publisher.get("last_success"))
        controller_label = (
            "alive"
            if controller_alive
            else "PID ABSENT"
            if controller.get("status") == "running"
            else controller.get("status", "unverified")
        )
        if controller.get("status") == "running" and (
            not controller_alive or controller_time is None or now - controller_time > 60
        ):
            errors.append(
                "Controller process or heartbeat needs inspection; dashboard does not restart workers"
            )
        if publisher_time is not None and now - publisher_time > 2100:
            errors.append("Report publication is older than 35 minutes")
        self.summary = (
            f"Controller {controller_label} · heartbeat {duration(now - controller_time) if controller_time else '—'} ago · reports {duration(now - publisher_time) if publisher_time else 'unverified'} ago · source {str(snapshot.get('source_commit', ''))[:8]}\n"
            + "\n".join(pseudo)
        )
        gpus = {}
        if self.show_gpus:
            try:
                result = subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                    timeout=3,
                )
                for line in result.splitlines():
                    index, util, used, total, temperature = [
                        part.strip() for part in line.split(",")
                    ]
                    gpus[int(index)] = (
                        f"{util}% · {float(used) / 1024:.1f}/{float(total) / 1024:.0f}G · {temperature}°"
                    )
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append(f"GPU telemetry unavailable: {exc}")
        return rows, gpus, errors


class MedicalProfile:
    label = "Medical CT"
    refresh_seconds = 10
    columns: ClassVar = [
        ("GPU", 3),
        ("Model", 21),
        ("Phase", 11),
        ("Updates / phase", 14),
        ("Mass Dice", 9),
        ("Pancreas", 9),
        ("Scores", 7),
        ("Val step", 8),
        ("Scans", 7),
        ("Train ETA*", 10),
        ("Loss", 8),
        ("Age", 8),
    ]
    charts: ClassVar = [
        ("TRAINING LOSS", "train/loss", False),
        ("FULL-VOLUME MASS DICE", "val/mass_dice", True),
        ("FULL-VOLUME PANCREAS DICE", "val/pancreas_dice", True),
        ("OPTIMIZER STEPS / SECOND", "train/optimizer_steps_per_sec", False),
    ]
    note = (
        "Enter curves · A/T/C/Q/F filters · Shift+←/→ scroll · Ctrl+b then d detach\n"
        "Native: both-empty=1. Final: reference-positive means. — unavailable.\n"
        "*Train ETA excludes final evaluation. Different budgets; no ranking."
    )

    def metric_format(self, tag):
        return ".3f" if "dice" in tag else ".5g"

    def cells(self, row, now):
        mass, pancreas, kind, step, coverage = score_display(row)
        status = row["status"]
        phase = row.get("phase") or status
        age = now - row["sample_time"] if row.get("sample_time") and status == "running" else None
        return (
            str(row["gpu"]) if row.get("gpu") is not None and status == "running" else "—",
            Text(row["model"], overflow="ellipsis", no_wrap=True),
            Text(
                phase,
                style="red"
                if status in {"failed", "invalid_report", "interrupted"}
                else "cyan"
                if status == "running"
                else "green"
                if status == "completed"
                else "dim",
            ),
            row.get("progress_text", "—"),
            number(mass),
            number(pancreas),
            kind,
            f"{step:,}" if step is not None else "best" if kind == "final" else "—",
            coverage,
            duration(value(row, "train/eta_seconds"))
            if status == "running" and row.get("stage") == "train"
            else "—",
            number(value(row, "train/loss")),
            Text(duration(age), style="yellow" if age and age > 180 else "dim"),
        )

    def detail(self, row, *, focus=False):
        mass, pancreas, kind, step, coverage = score_display(row)
        result = f"{row['model']} · {row['status'].upper()} · {row.get('progress_text', '—')} · worker {row.get('health', '—')}\nGPU {row.get('gpu', '—')}: {row.get('gpu_text', '—')} · Loss {number(value(row, 'train/loss'))} · LR {number(value(row, 'train/lr'), '.3g')}\n{kind.upper()} mass Dice {number(mass)} / pancreas Dice {number(pancreas)} · validation step {step if step is not None else 'selected best' if kind == 'final' else '—'} · coverage {coverage} scans"
        if row.get("backend") == "nnunet":
            result += f"\nPATCH PSEUDO only: mass {number(value(row, 'pseudo/mass_dice'))} / pancreas CLASS {number(value(row, 'pseudo/pancreas_class_dice'))}. Patch scores stay outside native Dice charts; final checkpoint scores appear in the table."
        if kind == "final":
            result += "\nFinal evaluator uses reference-positive means; native training validation uses both-empty=1."
        if row.get("error"):
            result += "\n" + str(row["error"])
        return result


class MedicalProgress(CampaignProgress):
    def __init__(self, root, *, refresh=None, show_gpus=True, telemetry=None):
        super().__init__(
            root,
            telemetry or MedicalTelemetry(root, show_gpus=show_gpus),
            MedicalProfile(),
            refresh=refresh,
        )
