#!/usr/bin/env python3
"""Run one fail-closed lane of the Milestone 5 curriculum matrix.

The two lanes are intentionally balanced and fixed.  Run them with disjoint
four-GPU visibility sets and distinct master ports, for example::

    python scripts/run_m5_lane.py --lane a --campaign runs/m5_2026-08-12 \
        --expected-sha <full-sha> --gpus 0,1,2,3 --master-port 29501 \
        --railsem19-root /datasets/railsem19
    python scripts/run_m5_lane.py --lane b --campaign runs/m5_2026-08-12 \
        --expected-sha <full-sha> --gpus 4,5,6,7 --master-port 29502 \
        --railsem19-root /datasets/railsem19

Every job is provenance-gated immediately before launch.  Training failures do
not block independent jobs, but a changed checkout or output collision stops the
lane so an unattended sweep cannot silently mix code or overwrite a result.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

REPO_ROOT = Path(__file__).resolve().parents[1]
MASTER_ADDR = "127.0.0.1"
RAILSEM19_SPLIT_FILE = "splits/railsem19_seed0.json"
RAILSEM19_SPLIT = "val"
ENV_DISPLAY_ORDER = (
    "PL_GLOBAL_SEED",
    "CUDA_VISIBLE_DEVICES",
    "HF_HOME",
    "PYTHONPATH",
    "MASTER_ADDR",
    "MASTER_PORT",
)


@dataclass(frozen=True)
class Job:
    curriculum: str
    seed: int
    final_stage: str

    @property
    def slug(self) -> str:
        return f"{self.curriculum}_seed{self.seed}"


LANE_QUEUES: dict[str, tuple[Job, ...]] = {
    "a": (
        Job("cs_only", 0, "cityscapes"),
        Job("joint_cs_rs", 1, "joint"),
        Job("cs_rs", 2, "railsem19"),
        Job("rs_only", 1, "railsem19"),
        Job("cs_only", 2, "cityscapes"),
        Job("cs_rs", 0, "railsem19"),
    ),
    "b": (
        Job("rs_only", 0, "railsem19"),
        Job("cs_rs", 1, "railsem19"),
        Job("joint_cs_rs", 2, "joint"),
        Job("cs_only", 1, "cityscapes"),
        Job("rs_only", 2, "railsem19"),
        Job("joint_cs_rs", 0, "joint"),
    ),
}


class ProvenanceError(RuntimeError):
    """A condition that must stop the lane rather than skip one job."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _full_sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise argparse.ArgumentTypeError("expected a full 40-character hexadecimal git SHA")
    return value.lower()


def _gpu_visibility(value: str) -> str:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4 or len(set(parts)) != 4 or any(not part.isdecimal() for part in parts):
        raise argparse.ArgumentTypeError(
            "GPU visibility must contain exactly four distinct non-negative indices"
        )
    return ",".join(parts)


def _master_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("master port must be an integer") from exc
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("master port must be between 1024 and 65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--lane", required=True, choices=sorted(LANE_QUEUES))
    parser.add_argument(
        "--campaign",
        "--output-root",
        dest="campaign",
        required=True,
        type=Path,
        help="shared output_root for both lanes (use an ignored run path or a path outside the repo)",
    )
    parser.add_argument("--expected-sha", required=True, type=_full_sha)
    parser.add_argument(
        "--gpus",
        "--cuda-visible-devices",
        dest="gpus",
        required=True,
        type=_gpu_visibility,
    )
    parser.add_argument(
        "--master-port",
        required=True,
        type=_master_port,
        help="DDP port for this lane; concurrent lanes must use different ports",
    )
    parser.add_argument(
        "--railsem19-root",
        type=Path,
        default=os.environ.get("SEGMENTARY_RAILSEM19"),
        help="RailSem19 root for the common evaluation (or set SEGMENTARY_RAILSEM19)",
    )
    parser.add_argument(
        "--railsem19-split-file",
        default=RAILSEM19_SPLIT_FILE,
        help="committed RailSem19 split JSON passed to the common evaluation",
    )
    parser.add_argument(
        "--hf-home",
        type=Path,
        default=os.environ.get("HF_HOME"),
        help="optional Hugging Face cache root (otherwise inherit the environment/default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run read-only provenance checks and print every exact command",
    )
    return parser


def run_dir(campaign: Path, job: Job) -> Path:
    return campaign / job.slug


def checkpoint_path(campaign: Path, job: Job) -> Path:
    return run_dir(campaign, job) / job.final_stage / "last.ckpt"


def training_results_path(campaign: Path, job: Job) -> Path:
    return run_dir(campaign, job) / job.final_stage / "results.json"


def common_results_path(campaign: Path, job: Job) -> Path:
    return run_dir(campaign, job) / "common_railsem19" / "results.json"


def _config_paths(job: Job) -> list[str]:
    return [
        "configs/base.yaml",
        "configs/models/segformer_b2.yaml",
        f"configs/curricula/{job.curriculum}.yaml",
    ]


def _config_overrides(campaign: Path) -> list[str]:
    return [
        "--set",
        "train.devices=4",
        "--set",
        "train.batch_size=4",
        "--set",
        "train.accum=1",
        "--set",
        f"output_root={campaign}",
    ]


def train_command(campaign: Path, job: Job) -> list[str]:
    return [
        sys.executable,
        "-m",
        "segmentary.train",
        *_config_paths(job),
        "--seed",
        str(job.seed),
        *_config_overrides(campaign),
    ]


def eval_command(
    campaign: Path,
    job: Job,
    railsem19_root: Path,
    railsem19_split_file: str = RAILSEM19_SPLIT_FILE,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "segmentary.eval",
        *_config_paths(job),
        "--ckpt",
        str(checkpoint_path(campaign, job)),
        "--auto-weights",
        "--seed",
        str(job.seed),
        *_config_overrides(campaign),
        "--dataset",
        "railsem19",
        "--root",
        str(railsem19_root),
        "--split-file",
        railsem19_split_file,
        "--split",
        RAILSEM19_SPLIT,
        "--out",
        str(common_results_path(campaign, job)),
        "--device",
        "cuda:0",
    ]


def job_environment(
    job: Job,
    gpu_visibility: str,
    master_port: int,
    hf_home: Path | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PL_GLOBAL_SEED": str(job.seed),
            "CUDA_VISIBLE_DEVICES": gpu_visibility,
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "MASTER_ADDR": MASTER_ADDR,
            "MASTER_PORT": str(master_port),
        }
    )
    if hf_home is not None:
        env["HF_HOME"] = str(hf_home.expanduser().resolve())
    return env


def format_invocation(command: Sequence[str], env: dict[str, str]) -> str:
    assignments = " ".join(
        f"{key}={shlex.quote(env[key])}" for key in ENV_DISPLAY_ORDER if key in env
    )
    return f"{assignments} {shlex.join(command)}"


def _git(arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ProvenanceError(f"git {' '.join(arguments)} failed: {detail or completed.returncode}")
    return completed.stdout.strip()


def check_source_provenance(expected_sha: str) -> str:
    """Validate that the checkout still has exactly the expected clean source."""
    actual_sha = _git(["rev-parse", "--verify", "HEAD"]).lower()
    if actual_sha != expected_sha.lower():
        raise ProvenanceError(f"HEAD is {actual_sha}, expected {expected_sha.lower()}")

    # Standard porcelain status includes tracked, staged, and untracked files,
    # while intentionally omitting ignored paths such as runs/.
    dirty = _git(["status", "--porcelain=v1", "--untracked-files=all"])
    if dirty:
        raise ProvenanceError(f"worktree is dirty:\n{dirty}")
    return actual_sha


def check_provenance(expected_sha: str, target_run_dir: Path) -> str:
    """Validate source provenance and the one-job output collision."""
    actual_sha = check_source_provenance(expected_sha)

    # Path.exists() is false for a broken symlink, which is still a collision.
    if target_run_dir.exists() or target_run_dir.is_symlink():
        raise ProvenanceError(f"target run directory already exists: {target_run_dir}")
    return actual_sha


def validate_result_record(path: Path, expected_sha: str, job: Job) -> None:
    """Reject an absent, malformed, dirty, or incorrectly seeded result record."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProvenanceError(f"expected result record is missing: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError(f"cannot read valid JSON result record {path}: {exc}") from exc
    if not isinstance(record, dict):
        raise ProvenanceError(f"result record is not a JSON object: {path}")

    problems: list[str] = []
    if record.get("git_sha") != expected_sha:
        problems.append(f"git_sha={record.get('git_sha')!r}, expected {expected_sha!r}")
    if record.get("git_dirty") is not False:
        problems.append(f"git_dirty={record.get('git_dirty')!r}, expected false")
    if type(record.get("seed")) is not int or record.get("seed") != job.seed:
        problems.append(f"seed={record.get('seed')!r}, expected {job.seed}")
    config = record.get("config")
    train_config = config.get("train") if isinstance(config, dict) else None
    config_seed = train_config.get("seed") if isinstance(train_config, dict) else None
    if type(config_seed) is not int or config_seed != job.seed:
        problems.append(f"config.train.seed={config_seed!r}, expected {job.seed}")
    if problems:
        raise ProvenanceError(f"untrusted result record {path}: {'; '.join(problems)}")


def atomic_write_json(path: Path, payload: dict) -> None:
    """Replace a JSON status file atomically on its destination filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _write_console(chunk: bytes) -> None:
    stream = getattr(sys.stdout, "buffer", None)
    if stream is not None:
        stream.write(chunk)
        stream.flush()
    else:
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
        sys.stdout.flush()


def _read_available(stream: BinaryIO, size: int) -> bytes:
    read = getattr(stream, "read1", stream.read)
    return read(size)


def run_logged(command: Sequence[str], env: dict[str, str], log_path: Path) -> int:
    """Run one command and tee its combined output byte-for-byte to log/stdout."""
    invocation = format_invocation(command, env)
    print(f"$ {invocation}", flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        log.write(f"\n$ {invocation}\n".encode())
        log.flush()
        try:
            process = subprocess.Popen(
                list(command),
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            message = f"launcher could not start command: {exc}\n".encode()
            log.write(message)
            log.flush()
            _write_console(message)
            return 127

        if process.stdout is None:  # defensive: PIPE above must create it
            process.kill()
            process.wait()
            message = b"launcher error: subprocess stdout pipe was not created\n"
            log.write(message)
            log.flush()
            _write_console(message)
            return 127

        while chunk := _read_available(process.stdout, 8192):
            log.write(chunk)
            log.flush()
            _write_console(chunk)
        return process.wait()


def _job_record(campaign: Path, job: Job) -> dict:
    return {
        "curriculum": job.curriculum,
        "seed": job.seed,
        "run_dir": str(run_dir(campaign, job)),
        "checkpoint": str(checkpoint_path(campaign, job)),
        "training_results": str(training_results_path(campaign, job)),
        "common_results": str(common_results_path(campaign, job)),
        "log": None,
        "status": "pending",
        "started_at": None,
        "finished_at": None,
        "train_returncode": None,
        "eval_returncode": None,
        "failure": None,
    }


def _lane_record(
    lane: str,
    campaign: Path,
    expected_sha: str,
    gpu_visibility: str,
    master_port: int,
) -> dict:
    return {
        "schema_version": 1,
        "lane": lane,
        "campaign": str(campaign),
        "expected_git_sha": expected_sha,
        "gpu_visibility": gpu_visibility,
        "master_addr": MASTER_ADDR,
        "master_port": master_port,
        "effective_batch_size": 4 * 4 * 1,
        "status": "pending",
        "started_at": _now(),
        "updated_at": None,
        "finished_at": None,
        "failure": None,
        "jobs": [_job_record(campaign, job) for job in LANE_QUEUES[lane]],
    }


def _persist_status(status_path: Path, record: dict) -> None:
    record["updated_at"] = _now()
    atomic_write_json(status_path, record)


def _stop_for_provenance(
    *,
    lane: str,
    job: Job,
    job_record: dict,
    lane_record: dict,
    status_path: Path,
    message: str,
    phase: str,
    persist: bool,
) -> int:
    if persist:
        job_record["status"] = "provenance_failed"
        job_record["failure"] = message
        job_record["finished_at"] = _now()
        lane_record["status"] = "failed_provenance"
        lane_record["failure"] = message
        lane_record["finished_at"] = _now()
        _persist_status(status_path, lane_record)
    print(f"lane {lane} stopped {phase} {job.slug}: {message}", file=sys.stderr)
    return 2


def run_lane(
    *,
    lane: str,
    campaign: Path,
    expected_sha: str,
    gpu_visibility: str,
    master_port: int,
    railsem19_root: Path,
    railsem19_split_file: str,
    hf_home: Path | None,
    dry_run: bool,
) -> int:
    campaign = campaign.expanduser().resolve()
    status_path = campaign / f"lane_{lane}_status.json"
    log_root = campaign / f"lane_{lane}_logs"
    lane_record = _lane_record(lane, campaign, expected_sha, gpu_visibility, master_port)
    failures = 0

    if dry_run:
        print(f"dry-run lane {lane}: no files or directories will be created")

    for index, job in enumerate(LANE_QUEUES[lane]):
        job_record = lane_record["jobs"][index]
        target = run_dir(campaign, job)
        try:
            actual_sha = check_provenance(expected_sha, target)
        except ProvenanceError as exc:
            return _stop_for_provenance(
                lane=lane,
                job=job,
                job_record=job_record,
                lane_record=lane_record,
                status_path=status_path,
                message=str(exc),
                phase="before",
                persist=not dry_run,
            )

        env = job_environment(job, gpu_visibility, master_port, hf_home)
        train = train_command(campaign, job)
        evaluate = eval_command(campaign, job, railsem19_root, railsem19_split_file)
        if dry_run:
            print(f"$ {format_invocation(train, env)}")
            print(f"$ {format_invocation(evaluate, env)}")
            continue

        lane_record["status"] = "running"
        lane_record["current_git_sha"] = actual_sha
        job_record["status"] = "training"
        job_record["started_at"] = _now()
        log_path = log_root / f"{job.slug}.log"
        job_record["log"] = str(log_path)
        job_record["train_command"] = train
        job_record["eval_command"] = evaluate
        job_record["environment"] = {key: env[key] for key in ENV_DISPLAY_ORDER if key in env}
        _persist_status(status_path, lane_record)

        train_returncode = run_logged(train, env, log_path)
        job_record["train_returncode"] = train_returncode
        try:
            check_source_provenance(expected_sha)
        except ProvenanceError as exc:
            return _stop_for_provenance(
                lane=lane,
                job=job,
                job_record=job_record,
                lane_record=lane_record,
                status_path=status_path,
                message=str(exc),
                phase="after training",
                persist=True,
            )
        if train_returncode != 0:
            failures += 1
            job_record["status"] = "train_failed"
            job_record["failure"] = f"training exited with status {train_returncode}"
            job_record["finished_at"] = _now()
            _persist_status(status_path, lane_record)
            continue

        checkpoint = checkpoint_path(campaign, job)
        if not checkpoint.is_file():
            failures += 1
            job_record["status"] = "checkpoint_missing"
            job_record["failure"] = f"training succeeded but checkpoint is missing: {checkpoint}"
            job_record["finished_at"] = _now()
            _persist_status(status_path, lane_record)
            continue

        try:
            validate_result_record(training_results_path(campaign, job), expected_sha, job)
        except ProvenanceError as exc:
            return _stop_for_provenance(
                lane=lane,
                job=job,
                job_record=job_record,
                lane_record=lane_record,
                status_path=status_path,
                message=str(exc),
                phase="after training",
                persist=True,
            )

        job_record["status"] = "evaluating"
        _persist_status(status_path, lane_record)
        eval_returncode = run_logged(evaluate, env, log_path)
        job_record["eval_returncode"] = eval_returncode
        try:
            check_source_provenance(expected_sha)
        except ProvenanceError as exc:
            return _stop_for_provenance(
                lane=lane,
                job=job,
                job_record=job_record,
                lane_record=lane_record,
                status_path=status_path,
                message=str(exc),
                phase="after common evaluation",
                persist=True,
            )
        if eval_returncode != 0:
            failures += 1
            job_record["status"] = "eval_failed"
            job_record["failure"] = f"common evaluation exited with status {eval_returncode}"
        else:
            try:
                validate_result_record(common_results_path(campaign, job), expected_sha, job)
            except ProvenanceError as exc:
                return _stop_for_provenance(
                    lane=lane,
                    job=job,
                    job_record=job_record,
                    lane_record=lane_record,
                    status_path=status_path,
                    message=str(exc),
                    phase="after common evaluation",
                    persist=True,
                )
            job_record["status"] = "succeeded"
        job_record["finished_at"] = _now()
        _persist_status(status_path, lane_record)

    if dry_run:
        return 0

    lane_record["status"] = "complete" if failures == 0 else "complete_with_failures"
    lane_record["finished_at"] = _now()
    _persist_status(status_path, lane_record)
    print(f"lane {lane} {lane_record['status']}; status: {status_path}")
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.railsem19_root is None:
        parser.error("--railsem19-root is required when SEGMENTARY_RAILSEM19 is not set")
    try:
        return run_lane(
            lane=args.lane,
            campaign=args.campaign,
            expected_sha=args.expected_sha,
            gpu_visibility=args.gpus,
            master_port=args.master_port,
            railsem19_root=args.railsem19_root.expanduser().resolve(),
            railsem19_split_file=args.railsem19_split_file,
            hf_home=args.hf_home,
            dry_run=args.dry_run,
        )
    except OSError as exc:
        print(f"launcher filesystem error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
