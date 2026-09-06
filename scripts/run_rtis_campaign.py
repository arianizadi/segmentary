"""Run the frozen RTIS pilot and publish only its live report from an isolated checkout.

One worker per GPU; job locks permit safe worker restart. Failed jobs stay visible
and require explicit review. A STOP file drains workers after their current job.
No test-set evaluation is performed. Periodic snapshots are removed only after
successful training, best-checkpoint validation and durable completion evidence.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPORT = Path("docs/results/paul-test-rtis/live")
TERMINAL = {"completed", "failed"}


def now():
    return datetime.now(UTC).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with temp.open("w") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@contextlib.contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            try:
                yield True
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def verify_frozen(root, repo):
    campaign = read(root / "campaign.json")
    if git(repo, "rev-parse", "HEAD") != campaign["code_sha"]:
        raise RuntimeError("Training revision changed")
    if git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Tracked training source changed")
    if digest(root / "plan.json") != campaign["plan_sha256"]:
        raise RuntimeError("Campaign plan changed")
    return campaign


def verify_samples(data_root, samples):
    # The preparation audit hashes encoded image files but decoded uint8 mask
    # pixels, so equivalent PNG compression must not invalidate a mask.
    from PIL import Image

    for sample in samples:
        image = data_root / "images" / sample["split"] / (sample["key"] + sample["image_extension"])
        mask = data_root / "masks" / sample["split"] / (sample["key"] + ".png")
        if digest(image) != sample["image_sha256"]:
            raise RuntimeError(f"Dataset content changed: {image}")
        with Image.open(mask) as decoded:
            if decoded.mode != "L" or decoded.size != (sample["width"], sample["height"]):
                raise RuntimeError(f"Mask encoding or dimensions changed: {mask}")
            actual = hashlib.sha256(decoded.tobytes()).hexdigest()
        if actual != sample["mask_sha256"]:
            raise RuntimeError(f"Dataset content changed: {mask}")


def initialize(root, repo):
    if (root / "campaign.json").exists():
        raise RuntimeError("Campaign already initialized; use worker to resume")
    if git(repo, "status", "--porcelain"):
        raise RuntimeError("Initialize from a clean frozen checkout")
    plan = read(root / "plan.json")
    from segmentary.config import load_experiment

    data_cfg = load_experiment([Path(plan["jobs"][0]["config"])])
    data_root = Path(data_cfg.stages[0].data[0].root)
    samples = read(data_root / "audit/samples.json")
    verify_samples(data_root, samples)
    verified = {}
    for job in plan["jobs"]:
        if digest(job["config"]) != job["config_sha256"]:
            raise RuntimeError(f"Config changed: {job['name']}")
        cfg = load_experiment([Path(job["config"])])
        data_root = Path(cfg.stages[0].data[0].root)
        if digest(data_root / "splits.json") != plan["split_sha256"]:
            raise RuntimeError("Dataset split changed")
        output = Path(cfg.output_root).resolve()
        if not output.is_relative_to(root) or output == root:
            raise RuntimeError("Run outputs must be inside the new campaign directory")
        source = job["source_checkpoint"]
        if source and source["checkpoint"] not in verified:
            path = Path(source["checkpoint"])
            actual = digest(path)
            if actual != source["recorded_sha256"]:
                raise RuntimeError(f"Source hash mismatch: {path}")
            verified[str(path)] = {"sha256": actual, "size": path.stat().st_size}
            print(f"Verified source {len(verified)}: {job['name']}", flush=True)
    campaign = {
        "schema_version": 1,
        "dataset": plan["dataset"],
        "created_at": now(),
        "code_sha": git(repo, "rev-parse", "HEAD"),
        "plan_sha256": digest(root / "plan.json"),
        "selection_metric": plan.get("selection_metric", "val/miou"),
        "collection_contract": plan.get("collection_contract"),
        "split_sha256": plan["split_sha256"],
        "grouping_status": plan["grouping_status"],
        "source_checkpoints": verified,
        "dataset_samples_verified": len(samples),
        "dataset_audit_sha256": digest(data_root / "audit/samples.json"),
        "target_steps": plan["target_steps_per_job"],
        "selection": "best validation checkpoint; auto raw/EMA-safe weights; no TTA",
        "test": "held out; not evaluated",
        "retention": "Keep best and final; delete periodic snapshots only after successful validation. Keep failed-run checkpoints for recovery.",
    }
    write(root / "campaign.json", campaign)
    for job in plan["jobs"]:
        write(root / "state" / f"{job['name']}.json", {"name": job["name"], "status": "queued"})


def cleanup(run, evidence, log_path):
    """Only this run's periodic files; never follow symlinks or remove anchors."""
    run = run.resolve()
    if evidence.get("status") != "completed":
        raise RuntimeError("Cleanup requires completed evaluation evidence")
    for anchor in evidence["checkpoints"].values():
        path = Path(anchor["path"])
        if path.is_symlink() or path.parent.resolve() != run:
            raise RuntimeError("Checkpoint anchor outside run")
        if digest(path) != anchor["sha256"]:
            raise RuntimeError("Checkpoint anchor changed; refusing cleanup")
    entries = read(log_path) if log_path.exists() else []
    for path in sorted(run.glob("step-*.ckpt")):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Unexpected periodic checkpoint path")
        if path.name.removeprefix("step-").removesuffix(".ckpt").isdigit():
            entry = {
                "path": str(path),
                "sha256": digest(path),
                "bytes": path.stat().st_size,
                "reason": "Validated best and final retained",
                "deleted_at": now(),
            }
            # Record intent durably before unlink; mark outcome afterward.
            entries.append({**entry, "deleted": False})
            write(log_path, entries)
            path.unlink()
            entries[-1]["deleted"] = True
            write(log_path, entries)
    return sum(e["bytes"] for e in entries if e.get("deleted"))


def checkpoint_info(path):
    from segmentary.checkpoints import read_checkpoint

    state = read_checkpoint(path)
    step = int(state["global_step"])
    if not state.get("optimizer_states") or not state.get("lr_schedulers"):
        raise RuntimeError(f"Not a full recovery checkpoint: {path}")
    return {"path": str(path), "sha256": digest(path), "global_step": step}


def validate_stop(training, actual, maximum):
    stop = training.get("env", {}).get("training_stop", {})
    if actual == maximum:
        return stop or {
            "reason": "budget_complete",
            "actual_steps": actual,
            "maximum_steps": maximum,
        }
    if (
        not 0 < actual < maximum
        or stop.get("reason") != "validation_plateau"
        or stop.get("actual_steps") != actual
        or stop.get("maximum_steps") != maximum
        or not stop.get("patience")
        or training.get("metrics", {}).get("miou") is None
    ):
        raise RuntimeError("Training exited early without valid validation-based stopping evidence")
    return stop


def learning_curve(run):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    events = EventAccumulator(str(run / "tensorboard"), size_guidance={"scalars": 0})
    events.Reload()
    return {
        tag: [{"step": e.step, "value": e.value} for e in events.Scalars(tag)]
        for tag in ("train/loss", "val/miou")
        if tag in events.Tags()["scalars"]
    }


def run_job(root, repo, job, gpu, campaign):
    from segmentary.config import load_experiment

    if digest(job["config"]) != job["config_sha256"]:
        raise RuntimeError("Config digest mismatch")
    cfg = load_experiment([Path(job["config"])])
    if digest(Path(cfg.stages[0].data[0].root) / "splits.json") != campaign["split_sha256"]:
        raise RuntimeError("Dataset split changed")
    source = job["source_checkpoint"]
    if source and digest(source["checkpoint"]) != source["recorded_sha256"]:
        raise RuntimeError("Source checkpoint changed")
    run = Path(cfg.output_root) / f"{cfg.name}_seed{cfg.train.seed}" / "rtis"
    run.resolve().relative_to(root)
    log_dir = root / "logs"
    log_dir.mkdir(exist_ok=True)
    state_path = root / "state" / f"{job['name']}.json"
    state = {
        "name": job["name"],
        "status": "training",
        "gpu": gpu,
        "started_at": now(),
        "config_sha256": job["config_sha256"],
        "code_sha": campaign["code_sha"],
    }
    write(state_path, state)
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": str(gpu),
        "OMP_NUM_THREADS": "4",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(repo / "src"),
    }
    command = [sys.executable, "-m", "segmentary.train", job["config"], "--devices", "1"]
    candidates = list(run.glob("step-*.ckpt")) + list(run.glob("best*.ckpt"))
    if (run / "last.ckpt").exists():
        candidates.append(run / "last.ckpt")
    valid = []
    for candidate in candidates:
        try:
            info = checkpoint_info(candidate)
            valid.append((info["global_step"], candidate))
        except Exception as error:
            print(f"Ignoring unreadable resume file {candidate}: {error}", flush=True)
    if valid:
        command += ["--resume-checkpoint", str(max(valid, key=lambda item: item[0])[1])]
    with (log_dir / f"{job['name']}.log").open("a") as log:
        if campaign.get("collection_contract"):
            from segmentary.utils.resource_tracking import run_recorded

            run_recorded(
                command,
                cwd=repo,
                env=env,
                stdout=log,
                records=root / "attempts" / job["name"],
                phase="training",
            )
        else:
            subprocess.run(
                command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT, check=True
            )
        last = checkpoint_info(run / "last.ckpt")
        training = read(run / "results.json")
        stop = validate_stop(training, last["global_step"], campaign["target_steps"])

        best_paths = list(run.glob("best*.ckpt"))
        if len(best_paths) != 1:
            raise RuntimeError(f"Expected exactly one best checkpoint: {best_paths}")
        best = checkpoint_info(best_paths[0])
        state.update(status="evaluating", final_step=last["global_step"])
        write(state_path, state)
        result_path = run / "best-val.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "segmentary.eval",
                job["config"],
                "--ckpt",
                str(best_paths[0]),
                "--auto-weights",
                "--split",
                "val",
                "--out",
                str(result_path),
                "--device",
                "cuda:0",
            ],
            cwd=repo,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    evaluation = read(result_path)
    if evaluation.get("metrics", {}).get("miou") is None:
        raise RuntimeError("Evaluation has no finite mIoU")
    state.update(
        status="collecting" if campaign.get("collection_contract") else "completed",
        finished_at=now(),
        checkpoints={"best": best, "final": last},
        evaluation=evaluation,
        training=training,
        stopping=stop,
        learning_curve=learning_curve(run),
    )
    write(state_path, state)
    if campaign.get("collection_contract"):
        return
    try:
        state["checkpoint_bytes_removed"] = cleanup(
            run, state, root / "cleanup" / f"{job['name']}.json"
        )
    except Exception as error:
        state["cleanup_error"] = str(error)
    write(state_path, state)


def worker(root, repo, gpu, run=None):
    campaign = verify_frozen(root, repo)
    with lock(root / "locks" / f"gpu-{gpu}.lock") as acquired:
        if not acquired:
            raise RuntimeError("This campaign already has a worker on that GPU")
        for job in read(root / "plan.json")["jobs"]:
            if (root / "STOP").exists():
                return
            with lock(root / "locks" / f"{job['name']}.lock") as claimed:
                if not claimed:
                    continue
                state_path = root / "state" / f"{job['name']}.json"
                if read(state_path)["status"] in TERMINAL:
                    continue
                try:
                    verify_frozen(root, repo)
                    (run or run_job)(root, repo, job, gpu, campaign)
                except Exception as error:
                    state = read(state_path)
                    detail = (
                        f"Process exited {error.returncode}; see logs/{job['name']}.log"
                        if isinstance(error, subprocess.CalledProcessError)
                        else str(error)
                    )
                    state.update(status="failed", finished_at=now(), error=detail)
                    write(state_path, state)
                    print(f"FAILED {job['name']}: {error}", flush=True)


def snapshot(root):
    plan = read(root / "plan.json")
    rows = []
    for job in plan["jobs"]:
        state = read(root / "state" / f"{job['name']}.json")
        rows.append(
            {
                **{
                    k: job[k]
                    for k in (
                        "name",
                        "model",
                        "protocol",
                        "seed",
                        "config_sha256",
                        "source_checkpoint",
                        "reset_head",
                    )
                },
                **state,
            }
        )
    return {"campaign": read(root / "campaign.json"), "jobs": rows}


def render(data):
    campaign = data["campaign"]
    jobs = data["jobs"]
    completed = sum(row["status"] == "completed" for row in jobs)
    failed = sum(row["status"] == "failed" for row in jobs)
    lines = [
        "# paul-test-rtis live pilot",
        "",
        f"**{completed}/{len(jobs)} completed · {failed} failed**",
        "",
        "36 model recipes x four initialization paths x seed 0. Each run trains for at most 4,000 optimizer steps on the same 220 training images, with validation-based early stopping.",
        "",
        "Validation: 37 images; best validation checkpoint, native RTIS classes, no TTA. Test: 50 held-out images, not evaluated. Recording groups are provisional; validation lacks person, truck and on-rails. These single-seed pilot results do not establish independent-recording generalization.",
        "",
        f"Frozen training code: `{campaign['code_sha']}`. Split SHA-256: `{campaign['split_sha256']}`.",
        "",
        "Initialization: `rtis_only` = pretrained backbone; `cityscapes_to_rtis` = Cityscapes endpoint; `railsem19_to_rtis` = RailSem19 endpoint; `cityscapes_to_railsem19_to_rtis` = Cityscapes → RailSem19 endpoint. All transferred classifiers are reset.",
        "",
        "[Complete results, per-class metrics, checkpoint hashes and provenance](status.json). Source diagnostics remain [separate](../README.md). Values below are **validation mIoU (%)**, not the coarse source-only diagnostic scores.",
        "",
        "Validation every 250 steps; stop after three checks without a 0.2-point mIoU improvement. Keep the best validation checkpoint. An early stop is a completed run, not a failed run. Training and validation curves are in the linked JSON.",
        "",
        "| Model | Initialization path | Status | Steps | Best step | Val mIoU (%) |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in jobs:
        score = row.get("evaluation", {}).get("metrics", {}).get("miou")
        shown = f"{100 * score:.2f}" if score is not None else "—"
        lines.append(
            f"| {row['model']} | {row['protocol']} | {row['status']} | {row.get('final_step', '—')} | {row.get('checkpoints', {}).get('best', {}).get('global_step', '—')} | {shown} |"
        )
    lines += [
        "",
        "After successful evaluation, periodic checkpoints are removed with a deletion audit. Best and final checkpoints, full metrics, configs and logs remain on HDRFS. Failed-run checkpoints remain available for recovery. Historical source checkpoints are preserved.",
        "",
    ]
    return "\n".join(lines)


def publish_once(root, checkout):
    data = snapshot(root)
    checkout = checkout.resolve()
    if checkout == Path.cwd().resolve():
        raise RuntimeError("Publisher requires a separate checkout")
    allowed = {str(REPORT / "README.md"), str(REPORT / "status.json")}
    changed = set(git(checkout, "diff", "--name-only").splitlines())
    staged = set(git(checkout, "diff", "--cached", "--name-only").splitlines())
    untracked = set(git(checkout, "ls-files", "--others", "--exclude-standard").splitlines())
    if (changed | staged | untracked) - allowed:
        raise RuntimeError("Publisher checkout has unrelated edits; leaving them intact")
    # Only our own generated files may be regenerated after an interrupted publish.
    for path in changed | staged:
        git(checkout, "restore", "--source=HEAD", "--staged", "--worktree", "--", path)
    git(checkout, "fetch", "origin", "main")
    # Recover an accepted push whose response was lost, or an unpublished report
    # commit after a network failure, without rewriting main or a training tree.
    ahead = git(checkout, "rev-list", "origin/main..HEAD")
    if ahead:
        names = set(git(checkout, "diff", "--name-only", "origin/main...HEAD").splitlines())
        if names - allowed:
            raise RuntimeError("Unpublished commits include unrelated changes")
        git(checkout, "rebase", "origin/main")
        git(checkout, "push", "origin", "HEAD:main")
    else:
        git(checkout, "merge", "--ff-only", "origin/main")
    target = checkout / REPORT
    target.mkdir(parents=True, exist_ok=True)
    write(target / "status.json", data)
    (target / "README.md").write_text(render(data))
    git(checkout, "add", "--", *sorted(allowed))
    if not git(checkout, "diff", "--cached", "--name-only"):
        return
    done = sum(r["status"] == "completed" for r in data["jobs"])
    git(
        checkout, "commit", "-m", f"Update RTIS pilot results: {done}/{len(data['jobs'])} completed"
    )
    git(checkout, "push", "origin", "HEAD:main")
    write(
        root / "publisher-status.json",
        {"last_success": now(), "commit": git(checkout, "rev-parse", "HEAD"), "completed": done},
    )


def publisher(root, checkout, once=False):
    with lock(root / "locks" / "publisher.lock") as acquired:
        if not acquired:
            raise RuntimeError("Publisher already running")
        while True:
            try:
                publish_once(root, checkout)
                if once:
                    return
            except Exception as error:
                print(f"Publish failed; will retry: {error}", flush=True)
                write(root / "publisher-error.json", {"at": now(), "error": str(error)})
                if once:
                    raise
            if (root / "STOP_PUBLISHER").exists():
                return
            time.sleep(30)


def launch(root, repo, checkout, gpus):
    verify_frozen(root, repo)
    processes = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True
    ).strip()
    if processes:
        raise RuntimeError("GPU compute processes already active; inspect before launch")
    if not checkout or checkout.resolve() == repo:
        raise RuntimeError("A separate publisher checkout is required")
    logdir = root / "service-logs"
    logdir.mkdir(exist_ok=True)
    sessions = []
    commands = [("publisher", ["publish", "--checkout", str(checkout)])]
    commands += [(f"gpu-{gpu}", ["worker", "--gpu", str(gpu)]) for gpu in gpus]
    for suffix, arguments in commands:
        session = f"rtis-{root.name}-{suffix}"
        command = [
            sys.executable,
            "-u",
            str(repo / "scripts/run_rtis_campaign.py"),
            *arguments,
            "--campaign",
            str(root),
        ]
        shell = (
            f"cd {shlex.quote(str(repo))} && "
            f"PYTHONPATH={shlex.quote(str(repo / 'src'))} "
            f"{shlex.join(command)} >> {shlex.quote(str(logdir / (suffix + '.log')))} 2>&1"
        )
        subprocess.run(["tmux", "new-session", "-d", "-s", session, shell], check=True)
        sessions.append(session)
        write(
            root / "services.json",
            {
                "started_at": now(),
                "sessions": sessions,
                "publisher_checkout": str(checkout),
                "gpus": gpus,
            },
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["init", "launch", "worker", "publish"])
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--gpu", type=int)
    ap.add_argument("--gpus", default="0,1,2,3,4,5,6,7,8,9")
    ap.add_argument("--checkout", type=Path)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    root = args.campaign.resolve()
    repo = Path(__file__).resolve().parents[1]
    if args.action == "init":
        initialize(root, repo)
    elif args.action == "launch":
        launch(root, repo, args.checkout, [int(gpu) for gpu in args.gpus.split(",")])
    elif args.action == "worker":
        if args.gpu is None:
            ap.error("worker requires --gpu")
        worker(root, repo, args.gpu)
    else:
        if args.checkout is None:
            ap.error("publish requires --checkout")
        publisher(root, args.checkout, args.once)


if __name__ == "__main__":
    main()
