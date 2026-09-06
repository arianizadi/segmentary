"""Durable subprocess timing and sampled device telemetry for campaign phases."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any


def _write(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run_recorded(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stdout: IO[str],
    records: Path,
    phase: str,
) -> None:
    """Count startup, execution and shutdown; retain failed/incomplete attempts."""
    records.mkdir(parents=True, exist_ok=True)
    path = records / f"{len(list(records.glob('*.json'))):04d}-{phase}.json"
    start = time.monotonic()
    record: dict[str, Any] = {
        "phase": phase,
        "command": command,
        "cwd": str(cwd),
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "physical_gpu": env["CUDA_VISIBLE_DEVICES"],
        "telemetry_interval_seconds": 5,
        "telemetry": [],
        "telemetry_errors": [],
    }
    _write(path, record)
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=subprocess.STDOUT)
    record["pid"] = process.pid
    _write(path, record)
    try:
        while process.poll() is None:
            try:
                values = (
                    subprocess.check_output(
                        [
                            "nvidia-smi",
                            f"--id={env['CUDA_VISIBLE_DEVICES']}",
                            "--query-gpu=memory.used,utilization.gpu,power.draw,temperature.gpu",
                            "--format=csv,noheader,nounits",
                        ],
                        text=True,
                        timeout=3,
                    )
                    .strip()
                    .split(",")
                )
                sample: dict[str, Any] = {"elapsed_seconds": time.monotonic() - start}
                for key, value in zip(
                    [
                        "device_used_mib",
                        "gpu_utilization_percent",
                        "board_power_w",
                        "temperature_c",
                    ],
                    values,
                    strict=True,
                ):
                    try:
                        sample[key] = float(value.strip())
                    except ValueError:
                        sample[key] = None
                record["telemetry"].append(sample)
                _write(path, record)
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                record["telemetry_errors"].append(str(error))
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=5)
    finally:
        record.update(
            status="completed"
            if process.poll() == 0
            else "failed"
            if process.poll() is not None
            else "incomplete",
            returncode=process.poll(),
            finished_at=datetime.now(UTC).isoformat(),
            wall_clock_s=time.monotonic() - start,
        )
        _write(path, record)
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command)
