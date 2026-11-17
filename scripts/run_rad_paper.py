"""Resume a frozen RAD paper campaign through training, test, profiling and report.

The initialized training plan supplies every scientific choice. The controller
does not choose models, initialization recipes, image keys or checkpoints.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
from scripts import run_rtis_full_campaign as full
from scripts.rad_test_contract import validate_v2
from scripts.run_rad_test import digest, validate_request, write

from segmentary import gpu_policy


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def completed_jobs(root: Path, plan: dict) -> list[dict]:
    """Resolve every final endpoint before constructing any test request."""
    jobs = []
    if not plan.get("jobs"):
        raise ValueError("The paper training plan has no runs")
    for job in plan["jobs"]:
        path = root / "state" / (job["name"] + ".json")
        state = read(path) if path.is_file() else {}
        final = state.get("checkpoints", {}).get("final", {})
        if (
            state.get("status") != "completed"
            or state.get("final_step") != plan["target_steps_per_job"]
            or final.get("global_step") != plan["target_steps_per_job"]
            or not final.get("sha256")
            or not Path(final.get("path", "")).is_file()
            or state.get("collection", {}).get("verified") is not True
        ):
            raise ValueError(f"Training run lacks complete fixed-budget evidence: {job['name']}")
        jobs.append(
            {
                **job,
                "state_path": str(path.resolve()),
                "state_sha256": digest(path),
                "final_checkpoint": final["path"],
                "final_checkpoint_sha256": final["sha256"],
            }
        )
    return jobs


def train_until_complete(root: Path, plan: dict, launch) -> None:
    """Use the paper-only bounded recovery rule without changing any run identity."""
    campaign = read(root / "campaign.json")
    while True:
        try:
            completed_jobs(root, plan)
            return
        except ValueError:
            pass
        if (root / "STOP").exists() or (root / "STOP_LAUNCHER").exists():
            raise ValueError("Training campaign has a stop marker")
        for job in plan["jobs"]:
            path = root / "state" / (job["name"] + ".json")
            state = read(path) if path.exists() else {}
            if state.get("status") == "failed" and not full.recover_paper_job(root, job, campaign):
                raise ValueError(f"Training run requires intervention: {job['name']}")
        launch()
        try:
            completed_jobs(root, plan)
            return
        except ValueError as error:
            recovered = [full.recover_paper_job(root, job, campaign) for job in plan["jobs"]]
            if not any(recovered):
                raise ValueError("The complete training run set remains unavailable") from error


def protocol_before_training(plan: dict) -> dict:
    protocol = plan.get("research_protocol", {})
    required = {
        "models",
        "seeds",
        "primary_metric",
        "headline_protocol",
        "qualitative_seed",
        "qualitative_keys",
        "failure_rule",
        "split_policy",
        "source_stage_reports",
    }
    if required - set(protocol):
        raise ValueError(f"Research protocol lacks {sorted(required - set(protocol))}")
    identity = hashlib.sha256(
        json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if identity != plan.get("research_protocol_sha256"):
        raise ValueError("Research protocol hash differs from the training plan")
    if protocol["seeds"] != [0, 1, 2] or protocol["qualitative_seed"] != 0:
        raise ValueError("Freeze seeds 0, 1, 2 and qualitative seed 0 before training")
    if protocol["primary_metric"] != "pixel_pooled_miou":
        raise ValueError("The paper report requires prespecified pixel-pooled primary mIoU")
    keys = protocol["qualitative_keys"]
    if not isinstance(keys, list) or not keys or len(set(keys)) != len(keys):
        raise ValueError("Prespecify unique ground-truth-chosen qualitative keys")
    if any(
        not isinstance(key, str) or Path(key).is_absolute() or ".." in Path(key).parts
        for key in keys
    ):
        raise ValueError("Qualitative keys must be safe dataset-relative image keys")
    source_spec = protocol["source_stage_reports"]
    if digest(Path(source_spec["spec"])) != source_spec["spec_sha256"]:
        raise ValueError("Frozen source-stage request SHA-256 changed")
    return protocol


def freeze_request(root: Path, plan_path: Path, repo: Path, benchmark_gpu: int) -> Path:
    """Create an immutable complete-run request, or verify the existing request."""
    plan = read(plan_path)
    protocol = protocol_before_training(plan)
    jobs = completed_jobs(root, plan)
    training_path = root / "campaign.json"
    training = read(training_path)
    allowed = training.get("launch_requirements", {}).get("expected_gpu_allowlist", [])
    if benchmark_gpu not in allowed:
        raise ValueError("Benchmark GPU is outside the training campaign authorization")
    configured = [yaml.safe_load(Path(job["config"]).read_text()) for job in jobs]
    roots = {str(Path(cfg["stages"][0]["data"][0]["root"]).resolve()) for cfg in configured}
    if len(roots) != 1:
        raise ValueError("The paper run set must use one frozen dataset")
    dataset_root = Path(roots.pop())
    splits = read(dataset_root / "splits.json")
    if not set(protocol["qualitative_keys"]) <= set(splits["test"]):
        raise ValueError("Frozen qualitative keys must belong to the held-out test split")
    classes_path = dataset_root / "classes.json"
    classes = sorted(read(classes_path)["classes"], key=lambda value: value["id"])
    if [value["id"] for value in classes] != list(range(21)):
        raise ValueError("Dataset must carry the complete ordered 21-class taxonomy")
    output = root / "paper"
    path = output / "test-request.json"
    campaign_path = output / "campaign.json"
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
    if dirty:
        raise ValueError("Freeze test evaluation from a clean committed checkout")
    request = {
        "schema_version": 2,
        "test_evaluation_authorized": True,
        "campaign_json": str(campaign_path.resolve()),
        "training_plan": str(plan_path.resolve()),
        "training_plan_sha256": digest(plan_path),
        "training_campaign": str(training_path.resolve()),
        "training_campaign_sha256": digest(training_path),
        "training_code_sha": training["code_sha"],
        "research_protocol": protocol,
        "dataset_root": str(dataset_root),
        "split_sha256": digest(dataset_root / "splits.json"),
        "samples_sha256": digest(dataset_root / "audit/samples.json"),
        "classes_sha256": digest(classes_path),
        "class_names": [value["name"] for value in classes],
        "output_root": str((output / "test").resolve()),
        "benchmark_gpu": benchmark_gpu,
        "jobs": jobs,
    }
    policy = gpu_policy.load(training)
    source_spec = read(Path(protocol["source_stage_reports"]["spec"]))
    source_report = Path(source_spec["output_root"]) / "source-stage-reports.json"
    request["source_stage_reports"] = {"path": str(source_report), "sha256": digest(source_report)}
    campaign = {
        "schema_version": 2,
        "code_sha": head,
        "gpu_policy": policy,
        "gpu_policy_sha256": gpu_policy.policy_sha256(policy),
        "authorized_gpu_indices": allowed,
    }
    validate_v2(request, campaign)
    raw = json.dumps(request, indent=2, allow_nan=False) + "\n"
    campaign["request_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    if path.exists() and path.read_text() != raw:
        raise ValueError("Existing frozen test request differs; refusing to overwrite it")
    if campaign_path.exists() and read(campaign_path) != campaign:
        raise ValueError("Existing frozen test campaign differs; refusing to overwrite it")
    if not path.exists():
        write(path, request)
    if not campaign_path.exists():
        write(campaign_path, campaign)
    validate_request(path)
    return path


def run(args: argparse.Namespace) -> dict:
    root, repo = args.campaign.resolve(), args.repo.resolve()
    plan_path = args.plan.resolve() if args.plan else root / "plan.json"
    if plan_path != root / "plan.json":
        raise ValueError("--plan must identify this campaign's frozen plan.json")
    plan = read(plan_path)
    protocol_before_training(plan)
    if not (root / "campaign.json").is_file():
        raise ValueError("Initialize the training campaign and its launch preflight first")
    status_path = root / "paper-controller-status.json"

    def phase(name: str) -> None:
        write(status_path, {"status": "running", "phase": name})

    def command(script: str, *arguments: str) -> None:
        environment = dict(os.environ)
        if args.hf_home:
            environment["HF_HOME"] = str(args.hf_home.resolve())
        subprocess.run(
            [args.python, str(repo / "scripts" / script), *arguments],
            cwd=repo,
            env=environment,
            check=True,
        )

    with (root / ".paper-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            phase("training")
            training_arguments = ["--campaign", str(root)]
            if args.hf_home:
                training_arguments.extend(["--hf-home", str(args.hf_home.resolve())])
            train_until_complete(
                root, plan, lambda: command("launch_rtis_full_campaign.py", *training_arguments)
            )
            phase("source-stage-evaluation")
            command(
                "evaluate_rad_source_stages.py",
                "--request",
                plan["research_protocol"]["source_stage_reports"]["spec"],
                "--repo",
                str(repo),
                "--python",
                args.python,
            )
            phase("freezing-test-request")
            request = freeze_request(root, plan_path, repo, args.benchmark_gpu)
            phase("test")
            command(
                "run_rad_test.py",
                "--request",
                str(request),
                "--repo",
                str(repo),
                "--python",
                args.python,
            )
            phase("deployment-performance")
            command(
                "run_rad_test_profiles.py",
                "--request",
                str(request),
                "--repo",
                str(repo),
                "--python",
                args.python,
                "--gpu",
                str(args.benchmark_gpu),
            )
            phase("report")
            command(
                "build_rad_paper_report.py",
                "--request",
                str(request),
                "--out",
                str(root / "paper/report"),
            )
            report_root = root / "paper/report"
            for filename in ("rad-paper.json", "rad-paper.csv", "rad-paper.pdf"):
                artifact = report_root / filename
                if not artifact.is_file() or artifact.stat().st_size == 0:
                    raise ValueError(f"Report artifact is missing or empty: {artifact}")
            if read(report_root / "rad-paper.json").get("request_sha256") != digest(request):
                raise ValueError("Report belongs to a different frozen request")
        except Exception as error:
            write(status_path, {"status": "blocked", "error": str(error)})
            raise
        result = {
            "status": "completed",
            "request": str(request),
            "report": str(root / "paper/report/rad-paper.pdf"),
        }
        write(status_path, result)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--benchmark-gpu", type=int, required=True)
    parser.add_argument("--hf-home", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
