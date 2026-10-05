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

from segmentary.gpu_policy import GpuInspectionError, GpuPolicyError, assert_pid_on_uuid

# Telemetry ticks are 5 s apart; a child whose placement cannot be verified for
# this many consecutive ticks (~2 min of nvidia-smi/ps outage) is terminated.
MAX_UNVERIFIED_CHECKS = 24


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
    expected_gpu_uuid: str | None = None,
    max_unverified_checks: int = MAX_UNVERIFIED_CHECKS,
) -> None:
    """Count startup, execution and shutdown; retain failed/incomplete attempts.

    With ``expected_gpu_uuid`` the child's process tree is checked against
    ``nvidia-smi`` on every telemetry tick and terminated on the first context
    *observed* on any other GPU; the violation is recorded and raised. A tick on
    which ``nvidia-smi``/``ps`` themselves fail is not a violation: it is
    appended to ``policy_check_errors`` and the child keeps running, but after
    ``max_unverified_checks`` consecutive unverified ticks the child is
    terminated and the attempt fails closed.
    """
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
        "gpu_uuid": expected_gpu_uuid,
        "telemetry_interval_seconds": 5,
        "telemetry": [],
        "telemetry_errors": [],
        "policy_check_errors": [],
    }
    _write(path, record)
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=subprocess.STDOUT)
    record["pid"] = process.pid
    _write(path, record)
    violation: GpuPolicyError | None = None
    unverified = 0
    try:
        while process.poll() is None:
            if expected_gpu_uuid is not None:
                try:
                    assert_pid_on_uuid(process.pid, expected_gpu_uuid)
                    unverified = 0
                except GpuInspectionError as error:
                    unverified += 1
                    record["policy_check_errors"].append(str(error))
                    if unverified >= max(1, int(max_unverified_checks)):
                        violation = GpuPolicyError(
                            f"GPU placement of pid {process.pid} could not be verified for "
                            f"{unverified} consecutive checks; last error: {error}"
                        )
                except GpuPolicyError as error:
                    violation = error
                if violation is not None:
                    record["gpu_policy_violation"] = str(violation)
                    _write(path, record)
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    break
            try:
                values = (
                    subprocess.check_output(
                        [
                            "nvidia-smi",
                            f"--id={expected_gpu_uuid or env['CUDA_VISIBLE_DEVICES']}",
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
    if violation is not None:
        raise violation
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command)
