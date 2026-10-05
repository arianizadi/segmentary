"""Profile completed RTIS checkpoints only on an idle, worker-locked GPU."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_rtis_campaign as runtime

from segmentary import gpu_policy


def occupied_uuids():
    return {gpu_policy.normalize_uuid(uuid) for _, uuid in gpu_policy.compute_apps()}


def measure(root, name):
    # Cheap gate before any model code; run_benchmark repeats it with CUDA up.
    gpu_policy.enforce_from_env(init_cuda=False)
    from segmentary.performance import build_parser, run_benchmark

    campaign = runtime.read(root / "campaign.json")
    job = next(j for j in runtime.read(root / "plan.json")["jobs"] if j["name"] == name)
    state = runtime.read(root / "state" / f"{name}.json")
    best = state["checkpoints"]["best"]
    if runtime.digest(best["path"]) != best["sha256"]:
        raise RuntimeError("Best checkpoint hash changed")
    result = Path(best["path"]).parent / "best-val.json"
    temporary = root / "performance" / f".{name}.pending.json"
    args = build_parser().parse_args(
        [
            job["config"],
            "--model-id",
            job["model"],
            "--measured-job-id",
            name,
            "--applies-to",
            name,
            "--ckpt",
            best["path"],
            "--result",
            str(result),
            "--out",
            str(temporary),
            "--expected-git-sha",
            campaign["code_sha"],
            "--expected-result-git-sha",
            state["evaluation"]["git_sha"],
            "--expected-result-stage",
            state["evaluation"]["stage"],
            "--expected-seed",
            str(job["seed"]),
            "--checkpoint-global-step",
            str(best["global_step"]),
            "--auto-weights",
        ]
    )
    payload = run_benchmark(args)
    payload["benchmark_scope"] = "rtis_selected_checkpoint_model_only"
    payload["status"] = "complete"
    runtime.write(root / "performance" / f"{name}.json", payload)
    temporary.unlink()


def watch(root, repo):
    with runtime.lock(root / "locks/performance.lock") as acquired:
        if not acquired:
            raise RuntimeError("Performance collector already running")
        while not (root / "STOP_PERFORMANCE").exists():
            jobs = runtime.read(root / "plan.json")["jobs"]
            pending = [
                j
                for j in jobs
                if runtime.read(root / "state" / f"{j['name']}.json")["status"] == "completed"
                and not (root / "performance" / f"{j['name']}.json").exists()
            ]
            if pending:
                policy = gpu_policy.load(runtime.verify_frozen(root, repo))
                for entry in policy["allowed"]:
                    index, uuid = int(entry["index"]), gpu_policy.normalize_uuid(entry["uuid"])
                    with runtime.lock(root / "locks" / f"gpu-{index}.lock") as available:
                        if not available or uuid in occupied_uuids():
                            continue
                        job = pending[0]
                        env = gpu_policy.child_env(
                            {
                                **os.environ,
                                "PYTHONPATH": str(repo / "src"),
                                "HF_HUB_OFFLINE": "1",
                                "TRANSFORMERS_OFFLINE": "1",
                                "OMP_NUM_THREADS": "4",
                            },
                            policy,
                            index,
                            root / "campaign.json",
                        )
                        log = root / "service-logs/performance.log"
                        with log.open("a") as stream:
                            result = subprocess.run(
                                [
                                    sys.executable,
                                    str(Path(__file__).resolve()),
                                    "--campaign",
                                    str(root),
                                    "--repo",
                                    str(repo),
                                    "--measure",
                                    job["name"],
                                ],
                                cwd=repo,
                                env=env,
                                stdout=stream,
                                stderr=subprocess.STDOUT,
                            )
                        if result.returncode:
                            runtime.write(
                                root / "performance" / f"{job['name']}.json",
                                {
                                    "status": "failed",
                                    "exit_code": result.returncode,
                                    "log": str(log),
                                    "at": runtime.now(),
                                },
                            )
                        break
            runtime.write(
                root / "performance-status.json",
                {
                    "at": runtime.now(),
                    "pending_completed_jobs": len(pending),
                    "policy": "Wait for a released GPU worker lock and no existing CUDA processes; no training preemption",
                },
            )
            time.sleep(30)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--measure")
    args = ap.parse_args()
    if args.measure:
        measure(args.campaign, args.measure)
    else:
        watch(args.campaign, args.repo)


if __name__ == "__main__":
    main()
