"""Publish aggregate pancreas reports from a separate checkout every 30 minutes.

The frozen training checkout provides the reporter code; only generated report
files are staged in the dedicated publisher checkout. No image, annotation,
checkpoint, patient identifier, or runtime path is copied into Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import report_medical_campaign as reports
from scripts.run_medical_campaign import read_json, singleton, utc_now, write_json


def git(checkout: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), *args], capture_output=True, text=True, timeout=120
    )
    if result.returncode:
        # Remote errors can echo credential-bearing URLs. Keep tool errors local
        # and structural instead of copying stderr into logs or generated files.
        raise RuntimeError(
            f"Git {args[0]} failed with exit {result.returncode}; checkout preserved"
        )
    return result.stdout.strip()


def report_path(checkout: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        path.is_absolute()
        or ".." in path.parts
        or len(path.parts) < 3
        or path.parts[:2] != ("docs", "results")
        or ".git" in path.parts
    ):
        raise ValueError("report-dir must be a relative directory beneath docs/results")
    destination = checkout / str(path)
    component = checkout
    for part in path.parts:
        component /= part
        if component.is_symlink():
            raise ValueError("Report directory must not contain symlink components")
    if not destination.resolve().is_relative_to(checkout.resolve()):
        raise ValueError("Report directory escapes its checkout through a symlink")
    return destination


def stable_fingerprint(snapshot: dict[str, Any]) -> str:
    def stable(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: stable(item)
                for key, item in value.items()
                if key
                not in {"generated_at", "last_update", "active_stage_allocated_hours_estimate"}
            }
        return [stable(item) for item in value] if isinstance(value, list) else value

    return hashlib.sha256(
        json.dumps(stable(snapshot), sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def terminal(campaign: Path, state_dir: Path) -> bool:
    runs = read_json(campaign)["runs"]
    if not runs:
        return False
    for run in runs:
        path = state_dir / "runs" / f"{run['id']}.json"
        if not path.is_file() or read_json(path).get("status") not in {
            "completed",
            "failed",
            "cancelled",
            "abandoned",
        }:
            return False
    return True


def changed_paths(checkout: Path) -> set[str]:
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only", "-z"),
        ("diff", "--cached", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        paths.update(filter(None, git(checkout, *args).split("\0")))
    return paths


def sync_and_push(checkout: Path, allowed: set[str]) -> str:
    """Preserve unpublished report commits and handle one push race explicitly."""
    for attempt in range(2):
        git(checkout, "fetch", "origin", "main")
        ahead = git(checkout, "rev-list", "origin/main..HEAD").splitlines()
        for commit in ahead:
            names = set(
                filter(
                    None,
                    git(
                        checkout,
                        "diff-tree",
                        "--root",
                        "--no-commit-id",
                        "--name-only",
                        "-r",
                        "-z",
                        commit,
                    ).split("\0"),
                )
            )
            if names - allowed:
                raise RuntimeError(
                    "Unpublished commits contain unrelated changes; preserving checkout"
                )
        if not ahead:
            git(checkout, "merge", "--ff-only", "origin/main")
            return git(checkout, "rev-parse", "HEAD")
        git(checkout, "rebase", "origin/main")
        try:
            git(checkout, "push", "origin", "HEAD:main")
            return git(checkout, "rev-parse", "HEAD")
        except RuntimeError:
            if attempt:
                raise
    raise AssertionError("Unreachable push retry state")


def publish_once(campaign: Path, state_dir: Path, checkout: Path, report_dir: str) -> dict:
    campaign, state_dir, checkout = campaign.resolve(), state_dir.resolve(), checkout.resolve()
    spec = read_json(campaign)
    if checkout in {Path(__file__).resolve().parents[1], Path(spec["source_root"]).resolve()}:
        raise ValueError("Publisher requires a separate checkout from frozen training source")
    if git(checkout, "rev-parse", "--show-toplevel") != str(checkout):
        raise ValueError("checkout must be a Git checkout root")
    if git(checkout, "branch", "--show-current") != "main":
        raise ValueError("Dedicated publisher checkout must be on main")
    destination = report_path(checkout, report_dir)
    terminal_before_snapshot = terminal(campaign, state_dir)
    snapshot = reports.collect(campaign, state_dir)
    files = reports.render(snapshot)
    allowed = set()
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("Reporter emitted an unsafe filename")
        output = destination / name
        component = destination
        symlink_component = False
        for part in path.parts:
            component /= part
            symlink_component |= component.is_symlink()
        if not output.resolve().is_relative_to(destination.resolve()) or symlink_component:
            raise ValueError("Generated output escapes its report directory")
        allowed.add(str(output.relative_to(checkout)))
    if changed_paths(checkout) - allowed:
        raise RuntimeError("Publisher checkout has unrelated edits; leaving them intact")
    status_path = state_dir / "publisher-status.json"
    previous = read_json(status_path) if status_path.exists() else {}
    fingerprint = stable_fingerprint(snapshot)
    meaningful = fingerprint != previous.get("snapshot_fingerprint")
    if meaningful or changed_paths(checkout):
        for name, contents in files.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.publisher.tmp")
            temporary.write_text(contents)
            temporary.replace(path)
        git(checkout, "add", "--", *sorted(allowed))
        staged = set(git(checkout, "diff", "--cached", "--name-only", "-z").split("\0")) - {""}
        if staged - allowed:
            raise RuntimeError("Staging includes unrelated files; preserving checkout")
        if staged:
            git(checkout, "commit", "-m", f"Update pancreas comparison: {spec['campaign_id']}")
    commit = sync_and_push(checkout, allowed)
    result = {
        "last_success": utc_now(),
        "commit": commit,
        "snapshot_fingerprint": fingerprint,
        "campaign_id": spec["campaign_id"],
        "terminal": terminal_before_snapshot and terminal(campaign, state_dir),
        "meaningful_change": meaningful,
        "status_counts": snapshot["status_counts"],
    }
    write_json(status_path, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--interval-seconds", type=int, default=1800)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.interval_seconds < 1:
        parser.error("interval-seconds must be positive")
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda _sig, _frame: stop.set())
    with singleton(args.state_dir / ".publisher.lock"):
        while not stop.is_set():
            try:
                result = publish_once(args.campaign, args.state_dir, args.checkout, args.report_dir)
                if result["meaningful_change"] or result["terminal"]:
                    print(json.dumps(result), flush=True)
                if args.once or result["terminal"]:
                    return 0
            except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                error = {"time": utc_now(), "error_type": type(exc).__name__, "error": str(exc)}
                write_json(args.state_dir / "publisher-error.json", error)
                print(json.dumps(error), file=sys.stderr, flush=True)
                if args.once:
                    return 1
            # A terminal transition is picked up within a minute, even when the
            # normal publication interval is thirty minutes.
            deadline = time.monotonic() + args.interval_seconds
            while not stop.wait(min(60, max(0, deadline - time.monotonic()))):
                if time.monotonic() >= deadline or terminal(args.campaign, args.state_dir):
                    break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
