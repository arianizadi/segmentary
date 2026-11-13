#!/usr/bin/env python3
"""Freeze historical-mIoU job order in a new, uninitialized RAD plan.

Only plan.json is reordered. Model configs, checkpoint identities and the priority
source are never changed. Refuses any initialized campaign/state tree. This is CPU
preparation only: it does not launch a campaign, initialize CUDA or touch a GPU.

Example:
    python scripts/prioritize_rad_plan.py --plan /new/campaign/plan.json \
        --priority tmp/rad-restart-20261113/training-priority.json
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

EXPECTED_MODELS = 41
EXPECTED_JOBS = 149
PROTOCOLS = {
    "rtis_only",
    "cityscapes_to_rtis",
    "railsem19_to_rtis",
    "cityscapes_to_railsem19_to_rtis",
}


class PriorityError(ValueError):
    """A planned queue cannot safely match its frozen historical priority."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError) as error:
        raise PriorityError(f"Invalid {label} JSON: {error}") from error
    if not isinstance(value, dict):
        raise PriorityError(f"{label} must contain a JSON object")
    return value


def ensure_uninitialized(root: Path) -> None:
    # lexists also refuses broken symlinks rather than treating them as absent.
    for name in ("campaign.json", "state"):
        if os.path.lexists(root / name):
            raise PriorityError(f"Refusing initialized/live campaign: {root / name} exists")


def job_key(row: Any, label: str) -> tuple[str, str]:
    if not isinstance(row, dict):
        raise PriorityError(f"{label} row must be an object")
    model, protocol = row.get("model"), row.get("protocol")
    if not isinstance(model, str) or not model or Path(model).name != model:
        raise PriorityError(f"{label} model must be a nonempty safe name")
    if protocol not in PROTOCOLS:
        raise PriorityError(f"{label} has unknown protocol {protocol!r}")
    return model, protocol


def validate_priority(priority: dict[str, Any]) -> list[dict[str, Any]]:
    models, jobs = priority.get("models"), priority.get("jobs")
    if not isinstance(models, list) or len(models) != EXPECTED_MODELS:
        raise PriorityError(f"Priority must contain exactly {EXPECTED_MODELS} models")
    if any(not isinstance(model, str) or not model for model in models) or len(set(models)) != len(
        models
    ):
        raise PriorityError("Priority model names must be unique nonempty strings")
    if not isinstance(jobs, list) or len(jobs) != EXPECTED_JOBS:
        raise PriorityError(f"Priority must contain exactly {EXPECTED_JOBS} jobs")
    if not isinstance(priority.get("source_csv_sha256"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", priority["source_csv_sha256"]
    ):
        raise PriorityError("Priority source_csv_sha256 must be a lowercase SHA-256")
    git_sha = priority.get("source_git_sha")
    if not isinstance(git_sha, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", git_sha):
        raise PriorityError("Priority source_git_sha must be a commit hash")
    for name in ("ranking_metric", "rule"):
        if not isinstance(priority.get(name), str) or not priority[name].strip():
            raise PriorityError(f"Priority {name} must describe the frozen historical rule")
    keys = []
    ordered_models = []
    scores: dict[str, list[float]] = {model: [] for model in models}
    for index, row in enumerate(jobs, 1):
        model, protocol = job_key(row, "Priority")
        if model not in scores:
            raise PriorityError(f"Priority job has unknown model {model!r}")
        if type(row.get("priority")) is not int or row["priority"] != index:
            raise PriorityError("Priority jobs must be in consecutive 1..149 queue order")
        if (
            type(row.get("model_priority")) is not int
            or row["model_priority"] != models.index(model) + 1
        ):
            raise PriorityError(f"Priority model rank does not match model order: {model}")
        score = row.get("old_pdf_validation_miou")
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise PriorityError(
                f"Priority old validation mIoU must be finite in [0,1]: {model}/{protocol}"
            )
        keys.append((model, protocol))
        if not ordered_models or ordered_models[-1] != model:
            ordered_models.append(model)
        scores[model].append(float(score))
    if len(set(keys)) != EXPECTED_JOBS:
        raise PriorityError("Duplicate priority model/protocol pair")
    if ordered_models != models:
        raise PriorityError(
            "Priority jobs must keep every model's initializations together in model order"
        )
    if any(values != sorted(values, reverse=True) for values in scores.values()):
        raise PriorityError("Initializations must descend by old validation mIoU within each model")
    model_best = [max(scores[model]) for model in models]
    if model_best != sorted(model_best, reverse=True):
        raise PriorityError("Models must descend by their best old validation mIoU")
    return jobs


def reordered_plan(
    plan: dict[str, Any], priority: dict[str, Any], priority_path: Path, priority_sha: str
) -> dict[str, Any]:
    ordered = validate_priority(priority)
    jobs = plan.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != EXPECTED_JOBS:
        raise PriorityError(f"Plan must contain exactly {EXPECTED_JOBS} jobs")
    if plan.get("launch_status") != "not_launched":
        raise PriorityError("Plan launch_status must be not_launched")
    by_key = {}
    names = set()
    for job in jobs:
        key = job_key(job, "Plan")
        if key in by_key:
            raise PriorityError(f"Duplicate planned model/protocol pair: {key}")
        expected_name = f"{key[0]}--{key[1]}--seed-0"
        if job.get("name") != expected_name or job["name"] in names:
            raise PriorityError(f"Duplicate or unexpected planned job name: {job.get('name')!r}")
        if type(job.get("seed")) is not int or job["seed"] != 0:
            raise PriorityError("This frozen 149-job ordering requires seed 0")
        if job.get("status") != "prepared_not_launched":
            raise PriorityError(f"Planned job is not prepared_not_launched: {job['name']}")
        by_key[key] = job
        names.add(job["name"])
    wanted = {(row["model"], row["protocol"]) for row in ordered}
    if set(by_key) != wanted:
        missing, unknown = sorted(wanted - set(by_key)), sorted(set(by_key) - wanted)
        raise PriorityError(
            f"Plan/priority exact coverage differs; missing={missing}; unknown={unknown}"
        )
    result = copy.deepcopy(plan)
    result["jobs"] = []
    for source in ordered:
        key = source["model"], source["protocol"]
        job = copy.deepcopy(by_key[key])
        job["queue_priority"] = source["priority"]
        job["queue_priority_provenance"] = {
            "model_priority": source["model_priority"],
            "old_pdf_validation_miou": source["old_pdf_validation_miou"],
            "source_csv_sha256": priority["source_csv_sha256"],
        }
        result["jobs"].append(job)
    result["queue_priority_provenance"] = {
        "source_priority_file": str(priority_path.resolve()),
        "source_priority_sha256": priority_sha,
        "source_csv_sha256": priority["source_csv_sha256"],
        "source_git_sha": priority["source_git_sha"],
        "ranking_metric": priority["ranking_metric"],
        "rule": priority["rule"],
        "models": list(priority["models"]),
        "jobs": EXPECTED_JOBS,
        "old_scores_used_for_queue_only": True,
        "new_test_scores_used": False,
    }
    return result


def prioritize(plan_path: Path, priority_path: Path) -> dict[str, Any]:
    plan_path = plan_path.resolve(strict=True)
    priority_path = priority_path.resolve(strict=True)
    root = plan_path.parent
    ensure_uninitialized(root)
    # This helper is a pre-initialization step. The sidecar serializes repeated
    # preparation invocations; launch/init must not run concurrently with it.
    lock_path = root / ".prioritize-plan.lock"
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ensure_uninitialized(root)
        original_bytes = plan_path.read_bytes()
        priority_bytes = priority_path.read_bytes()
        plan = read_json(original_bytes, "Plan")
        priority = read_json(priority_bytes, "Priority")
        result = reordered_plan(plan, priority, priority_path, sha256(priority_bytes))
        payload = (json.dumps(result, indent=2) + "\n").encode()
        previous_mode = stat.S_IMODE(plan_path.stat().st_mode)
        fd, temporary = tempfile.mkstemp(prefix=".plan-priority-", suffix=".json", dir=root)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), previous_mode)
            ensure_uninitialized(root)
            if plan_path.read_bytes() != original_bytes:
                raise PriorityError("Plan changed concurrently; refusing to replace it")
            if priority_path.read_bytes() != priority_bytes:
                raise PriorityError(
                    "Priority source changed concurrently; refusing to replace plan"
                )
            os.replace(temporary_path, plan_path)
        finally:
            temporary_path.unlink(missing_ok=True)
    return {
        "plan": str(plan_path),
        "jobs": EXPECTED_JOBS,
        "models": EXPECTED_MODELS,
        "priority_sha256": sha256(priority_bytes),
        "source_csv_sha256": priority["source_csv_sha256"],
        "first_job": result["jobs"][0]["name"],
        "last_job": result["jobs"][-1]["name"],
        "campaign_initialized": False,
        "gpu_jobs_started": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--priority", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prioritize(args.plan, args.priority)
    except (PriorityError, OSError) as error:
        parser.exit(2, f"Priority refused: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
