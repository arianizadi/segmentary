"""Use corrected collection tools while keeping the training checkout frozen.

Legacy workers drain with STOP. These replacement workers wait for their GPU lock
and honor STOP_COLLECTION_WORKERS. Only validated post-training coverage failures
are recovered; other failures remain visible. Training is never replayed during
collection recovery.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--training-repo", type=Path, required=True)
    parser.add_argument("--gpu", type=int)
    parser.add_argument("--stop-file", default="STOP_COLLECTION_WORKERS")
    parser.add_argument("--collect-only")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    root, repo = args.campaign.resolve(), args.training_repo.resolve()
    tool = Path(__file__).resolve()
    # All model, evaluation, profiling and runtime code comes from the frozen tree.
    sys.path[:0] = [str(repo), str(repo / "src")]
    from scripts import run_rtis_campaign as runtime
    from scripts import run_rtis_full_campaign as full

    from segmentary.config import load_experiment

    campaign = runtime.verify_frozen(root, repo)
    spec = importlib.util.spec_from_file_location(
        "corrected_collector", tool.with_name("collect_rtis_statistics.py")
    )
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    jobs = runtime.read(root / "plan.json")["jobs"]
    provenance = {
        "worker_sha256": runtime.digest(tool),
        "collector_sha256": runtime.digest(tool.with_name("collect_rtis_statistics.py")),
        "training_code_sha": campaign["code_sha"],
    }
    if args.collect_only:
        sys.argv = [
            str(tool.with_name("collect_rtis_statistics.py")),
            "--campaign",
            str(root),
            "--job",
            args.collect_only,
        ]
        collector.main()
        return
    if args.verify_only:
        checked = set()
        for job in jobs:
            if runtime.digest(job["config"]) != job["config_sha256"]:
                raise RuntimeError(f"Config hash mismatch: {job['name']}")
            cfg = load_experiment([Path(job["config"])])
            data_root = str(cfg.stages[0].data[0].root)
            if data_root not in checked:
                collector.validate_dataset(root, job, cfg, campaign)
                checked.add(data_root)
        print(
            f"PASS: {len(jobs)} config hashes; full file membership, image/mask hashes, dimensions, classes and split counts for {len(checked)} dataset(s)",
            flush=True,
        )
        return
    if args.gpu is None:
        parser.error("--gpu is required for a worker")
    if Path(args.stop_file).name != args.stop_file:
        parser.error("--stop-file must be a filename within the campaign")
    stop = root / args.stop_file
    original_train = runtime.run_job
    original_recorded = full.run_recorded

    def train_or_recover(root, repo, job, gpu, campaign):
        state = runtime.read(root / "state" / (job["name"] + ".json"))
        if state.get("collection_recovery") and state["status"] == "collecting":
            return
        original_train(root, repo, job, gpu, campaign)

    def recorded(command, **kwargs):
        if kwargs.get("phase") == "diagnostics":
            if (
                runtime.digest(tool) != provenance["worker_sha256"]
                or runtime.digest(tool.with_name("collect_rtis_statistics.py"))
                != provenance["collector_sha256"]
            ):
                raise RuntimeError("Collection tool source changed while worker was running")
            name = command[command.index("--job") + 1]
            command = [
                sys.executable,
                str(tool),
                "--campaign",
                str(root),
                "--training-repo",
                str(repo),
                "--collect-only",
                name,
            ]
        return original_recorded(command, **kwargs)

    runtime.run_job = train_or_recover
    full.run_recorded = recorded
    print(
        f"GPU {args.gpu}: waiting for legacy worker to drain; training SHA {campaign['code_sha']}",
        flush=True,
    )
    while not stop.exists():
        with runtime.lock(root / "locks" / f"gpu-{args.gpu}.lock") as acquired:
            if not acquired:
                time.sleep(10)
                continue
            print(f"GPU {args.gpu}: acquired worker lock", flush=True)
            for job in jobs:
                if stop.exists():
                    return
                with runtime.lock(root / "locks" / (job["name"] + ".lock")) as claimed:
                    if not claimed:
                        continue
                    state_path = root / "state" / (job["name"] + ".json")
                    state = runtime.read(state_path)
                    recover = (
                        state["status"] == "failed"
                        and state.get("collection_phase") == "diagnostics"
                    )
                    if recover:
                        log = root / "logs" / (job["name"] + ".log")
                        previous = state.get("collection_recovery", {})
                        recover = "RuntimeError: Unexpected split coverage" in log.read_text(
                            errors="replace"
                        )[-10000:] or (
                            bool(previous)
                            and previous.get("collector_sha256") != provenance["collector_sha256"]
                        )
                    if state["status"] == "completed" or (
                        state["status"] == "failed" and not recover
                    ):
                        continue
                    try:
                        runtime.verify_frozen(root, repo)
                        cfg = load_experiment([Path(job["config"])])
                        collector.validate_dataset(root, job, cfg, campaign)
                    except Exception as exc:
                        message = f"PREFLIGHT FAILED {job['name']}: {exc}"
                        state.update(status="failed", error=message, finished_at=runtime.now())
                        runtime.write(state_path, state)
                        stop.write_text(message + "\n")
                        raise RuntimeError(message) from exc
                    try:
                        if recover:
                            for anchor in state["checkpoints"].values():
                                if runtime.digest(anchor["path"]) != anchor["sha256"]:
                                    raise RuntimeError(
                                        f"Recovery checkpoint hash mismatch: {anchor['path']}"
                                    )
                            run_dir = Path(state["checkpoints"]["best"]["path"]).parent
                            if state["config_sha256"] != job["config_sha256"]:
                                raise RuntimeError("Recovery config mismatch")
                            if state["training"] != runtime.read(run_dir / "results.json") or state[
                                "evaluation"
                            ] != runtime.read(run_dir / "best-val.json"):
                                raise RuntimeError(
                                    "Recovery saved training/evaluation metadata mismatch"
                                )
                            if (
                                runtime.checkpoint_info(
                                    Path(state["checkpoints"]["final"]["path"])
                                )["global_step"]
                                != state["final_step"]
                            ):
                                raise RuntimeError("Recovery final checkpoint step mismatch")
                            runtime.validate_stop(
                                state["training"], state["final_step"], campaign["target_steps"]
                            )
                            if (
                                state["evaluation"]["git_sha"] != campaign["code_sha"]
                                or state["code_sha"] != campaign["code_sha"]
                            ):
                                raise RuntimeError("Recovery training/evaluation revision mismatch")
                            archive = root / "collection-recovery" / job["name"]
                            archive.mkdir(parents=True, exist_ok=True)
                            stamp = str(time.time_ns())
                            runtime.write(archive / (stamp + ".json"), state)
                            diagnostics = (
                                Path(state["checkpoints"]["best"]["path"]).parent / "diagnostics"
                            )
                            if diagnostics.exists():
                                diagnostics.rename(
                                    diagnostics.with_name("diagnostics-before-recovery-" + stamp)
                                )
                            state.update(
                                status="collecting",
                                gpu=args.gpu,
                                collection_recovery={
                                    **provenance,
                                    "at": runtime.now(),
                                    "reason": "legacy collector hardcoded original split size",
                                    "training_reused": True,
                                },
                            )
                            state.pop("error", None)
                            runtime.write(state_path, state)
                            print(
                                f"RECOVER COLLECTION {job['name']}; preserving trained checkpoints",
                                flush=True,
                            )
                        full.run_job(root, repo, job, args.gpu, campaign)
                        state = runtime.read(state_path)
                        state["collection_tools"] = provenance
                        runtime.write(state_path, state)
                        print(f"COMPLETE {job['name']}", flush=True)
                    except Exception as exc:
                        state = runtime.read(state_path)
                        detail = (
                            f"Process exited {exc.returncode}; see logs/{job['name']}.log"
                            if isinstance(exc, subprocess.CalledProcessError)
                            else str(exc)
                        )
                        state.update(status="failed", error=detail, finished_at=runtime.now())
                        runtime.write(state_path, state)
                        print(f"FAILED {job['name']}: {exc}", flush=True)
            return


if __name__ == "__main__":
    main()
