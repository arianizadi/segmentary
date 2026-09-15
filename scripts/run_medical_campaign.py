#!/usr/bin/env python3
"""Run an explicit scratch medical campaign, one immutable experiment per GPU.

Run with ``--spec campaign.json --state-dir /data/campaign-state`` inside a
durable terminal session. Restart the same command after interruption. A failed
run is retried only with ``--retry-failed``; existing partial artifacts are never
removed. ``--prepare-only`` prepares and caches every experiment without training.

The campaign spec declares schema_version=1, campaign_id, source_root,
source_commit, python (harness interpreter), manifest, splits, gpus, and runs.
Each run declares id and config (an existing JSON/YAML recipe with explicit
workspace/backend_python). Optional model/backend/workspace/comparison_group
fields are descriptive only. The runner freezes a resolved JSON config when it
assigns a GPU; that assignment persists across restarts. Optional evaluation
contains bootstrap_samples, seed, surface_tolerance_mm, lesion_iou_threshold,
and review_overlays. All scoring uses validation. Test access is not implemented.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

STAGES = ("prepare", "preprocess", "train", "predict", "evaluate")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


@contextlib.contextmanager
def singleton(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another campaign runner holds this state directory") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def absolute_path(value: Any, name: str) -> Path:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError(f"{name} must be an absolute path")
    return Path(value).resolve()


def load_recipe(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        recipe = read_json(path)
    else:
        import yaml

        recipe = yaml.safe_load(path.read_text())
    if not isinstance(recipe, dict):
        raise ValueError("Recipe must be a mapping")
    if recipe.get("backend", "nnunet") not in {"torch", "nnunet"}:
        raise ValueError("Only torch and nnunet backends are supported")
    absolute_path(recipe.get("workspace"), "recipe workspace")
    absolute_path(recipe.get("backend_python"), "recipe backend_python")
    if recipe.get("initialization", "scratch") != "scratch":
        raise ValueError("Campaigns must initialize from scratch")
    return recipe


def nnunet_model_name(recipe: dict[str, Any]) -> str:
    architecture = recipe.get("architecture", "resenc")
    if architecture == "resenc":
        return f"nnunet_resenc_{recipe.get('resenc', 'L').lower()}"
    return f"nnunet_planned_{architecture}"


def load_spec(path: Path) -> dict[str, Any]:
    spec = read_json(path)
    required = {
        "schema_version",
        "campaign_id",
        "source_root",
        "source_commit",
        "python",
        "manifest",
        "splits",
        "gpus",
        "runs",
    }
    allowed = required | {"evaluation", "protocol", "created_at_utc", "description"}
    if set(spec) - allowed or required - set(spec):
        raise ValueError(
            f"Invalid campaign fields: missing={required - set(spec)}, extra={set(spec) - allowed}"
        )
    if spec["schema_version"] != 1 or not IDENTIFIER.fullmatch(str(spec["campaign_id"])):
        raise ValueError("Invalid campaign schema or id")
    if not re.fullmatch(r"[0-9a-f]{40}", str(spec["source_commit"])):
        raise ValueError("source_commit must be a full lowercase Git SHA")
    for name in ("source_root", "python", "manifest", "splits"):
        absolute_path(spec[name], name)
    gpus = spec["gpus"]
    if (
        not isinstance(gpus, list)
        or not gpus
        or any(not isinstance(gpu, str) or not re.fullmatch(r"0|[1-9][0-9]*", gpu) for gpu in gpus)
        or len(set(gpus)) != len(gpus)
    ):
        raise ValueError("gpus must contain unique physical numeric GPU strings")
    inherited = os.environ.get("CUDA_VISIBLE_DEVICES")
    if inherited is not None and not set(gpus).issubset(inherited.split(",")):
        raise ValueError("Campaign GPUs exceed inherited CUDA_VISIBLE_DEVICES")
    if not isinstance(spec["runs"], list) or not spec["runs"]:
        raise ValueError("runs must be a nonempty explicit list")
    ids: set[str] = set()
    workspaces: set[Path] = set()
    recipes: dict[str, dict[str, Any]] = {}
    for run in spec["runs"]:
        if not isinstance(run, dict) or set(run) - {
            "id",
            "config",
            "model",
            "backend",
            "workspace",
            "comparison_group",
            "description",
        }:
            raise ValueError("Invalid run fields")
        name = run.get("id", "")
        if not isinstance(name, str) or not IDENTIFIER.fullmatch(name) or name in ids:
            raise ValueError("Run ids must be unique filesystem-safe names")
        ids.add(name)
        recipe = load_recipe(absolute_path(run.get("config"), "run config"))
        recipes[name] = recipe
        workspace = absolute_path(recipe["workspace"], "workspace")
        if workspace in workspaces:
            raise ValueError("Each run must own a distinct immutable workspace")
        workspaces.add(workspace)
        for key in ("workspace", "backend", "model"):
            expected = recipe.get(
                key,
                {
                    "backend": "nnunet",
                    "model": nnunet_model_name(recipe),
                }.get(key),
            )
            if key in run and run[key] != expected:
                raise ValueError(f"Run metadata {key} disagrees with recipe")
    evaluation = spec.get("evaluation", {})
    if not isinstance(evaluation, dict) or set(evaluation) - {
        "bootstrap_samples",
        "seed",
        "surface_tolerance_mm",
        "lesion_iou_threshold",
        "review_overlays",
    }:
        raise ValueError("Unknown evaluation option; campaign scoring supports validation only")
    protocol = spec.get("protocol", {})
    if protocol.get("followup_experiments") is not None or protocol.get("preset") in {
        "task07_dynunet_followup_v1",
        "task07_dynunet_deep_supervision_v1",
        "task07_recipe_explorations_v1",
        "task07_predicted_roi_cascade_v1",
    }:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from segmentary.medical.followup import validate_declared_followup

        validate_declared_followup(spec, recipes)
        for key in ("manifest", "splits"):
            if protocol.get(f"{key}_sha256") != sha256(Path(spec[key])):
                raise ValueError("Follow-up manifest or splits changed after planning")
    if (
        protocol.get("recipe_ablation") is not None
        or protocol.get("preset") == "task07_dynunet_recipe_ablation_v1"
    ):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from segmentary.medical.recipe_ablation import validate_declared_recipes

        validate_declared_recipes(spec, recipes)
        for key in ("manifest", "splits"):
            if protocol.get(f"{key}_sha256") != sha256(Path(spec[key])):
                raise ValueError("Recipe ablation manifest or splits changed after planning")
    return spec


def check_source(spec: dict[str, Any]) -> None:
    root = spec["source_root"]
    commit = subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(
        ["git", "-C", root, "status", "--porcelain", "--untracked-files=all"], text=True
    ).strip()
    if commit != spec["source_commit"] or dirty:
        raise ValueError("Campaign source must be a clean checkout of the pinned source_commit")


def make_binding(spec_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "spec": spec,
        "spec_sha256": sha256(spec_path),
        "manifest_sha256": sha256(Path(spec["manifest"])),
        "splits_sha256": sha256(Path(spec["splits"])),
        "recipes": {run["id"]: sha256(Path(run["config"])) for run in spec["runs"]},
        "runner_sha256": sha256(Path(__file__)),
    }


def process_start(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
    except (FileNotFoundError, IndexError, PermissionError):
        return None


def process_alive(pid: Any, started: str | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    current = process_start(pid)
    return started is None or current is None or current == started


def output_json(path: Path) -> dict[str, Any]:
    content = path.read_text(errors="replace")
    decoder = json.JSONDecoder()
    for offset, char in enumerate(content):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(content, offset)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and not content[end:].strip():
            return value
    raise ValueError(f"Command did not return a final JSON object: {path}")


def verify_workspace(config_path: Path, stage: str) -> None:
    """Run in the pinned harness interpreter, including its backend guards."""
    from segmentary.medical import backend, torch_backend
    from segmentary.medical.cli import _config
    from segmentary.medical.torch_config import TorchConfig

    config = _config(config_path)
    implementation = torch_backend if isinstance(config, TorchConfig) else backend
    implementation._binding(config, verify_development=False)
    if STAGES.index(stage) >= 1:
        if isinstance(config, TorchConfig):
            torch_backend._plan(config)
        else:
            backend._plan_binding(config)
    if STAGES.index(stage) >= 2:
        implementation._checkpoint(config, "checkpoint_final.pth")
    if STAGES.index(stage) >= 3:
        implementation._checkpoint(config, "checkpoint_best.pth")


class Campaign:
    def __init__(
        self,
        spec_path: Path,
        state_dir: Path,
        *,
        prepare_only: bool = False,
        retry_failed: bool = False,
        source_check: Callable[[dict[str, Any]], None] = check_source,
    ) -> None:
        self.spec_path = spec_path.resolve()
        self.root = state_dir.resolve()
        self.spec = load_spec(self.spec_path)
        self.prepare_only = prepare_only
        self.retry_failed = retry_failed
        self.source_check = source_check
        self.mutex = threading.RLock()
        self.stop = threading.Event()
        self.states: dict[str, dict[str, Any]] = {}
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self.input_hashes: dict[str, str] = {}

    def initialize(self) -> None:
        self.source_check(self.spec)
        binding = make_binding(self.spec_path, self.spec)
        path = self.root / "campaign-binding.json"
        if path.exists():
            if read_json(path) != binding:
                raise ValueError("Campaign, data, source, or recipes changed; use a new campaign")
        else:
            write_json(path, binding)
        self.input_hashes = {
            str(self.spec_path): binding["spec_sha256"],
            self.spec["manifest"]: binding["manifest_sha256"],
            self.spec["splits"]: binding["splits_sha256"],
            **{run["config"]: binding["recipes"][run["id"]] for run in self.spec["runs"]},
        }
        for run in self.spec["runs"]:
            name = run["id"]
            path = self.root / "runs" / f"{name}.json"
            if path.exists():
                state = read_json(path)
                if state["id"] != name:
                    raise ValueError("Run state identity changed")
                if process_alive(state.get("cli_pid"), state.get("cli_process_start")):
                    raise RuntimeError(
                        f"Run {name} still has a live stage process; do not launch a duplicate"
                    )
                if state.get("gpu") not in self.spec["gpus"]:
                    raise ValueError("Persisted GPU assignment is outside the campaign")
                if sha256(Path(state["config"])) != state["config_sha256"]:
                    raise ValueError("Resolved configuration was modified")
                expected = load_recipe(Path(run["config"])) | {"gpu": state["gpu"]}
                if read_json(Path(state["config"])) != expected:
                    raise ValueError("Resolved configuration no longer matches its frozen recipe")
                if state["status"] == "running":
                    state["status"] = "interrupted"
            else:
                recipe = load_recipe(Path(run["config"]))
                state = {
                    **run,
                    "id": name,
                    "recipe": run["config"],
                    "status": "queued",
                    "workspace": recipe["workspace"],
                    "backend": recipe.get("backend", "nnunet"),
                    "model": recipe.get("model", nnunet_model_name(recipe)),
                    "completed_stages": {},
                    "attempts": 0,
                }
            self.states[name] = state
        self.publish("running")

    def publish(self, status: str = "running") -> None:
        with self.mutex:
            write_json(
                self.root / "status.json",
                {
                    "schema_version": 1,
                    "campaign_id": self.spec["campaign_id"],
                    "source_commit": self.spec["source_commit"],
                    "pid": os.getpid(),
                    "process_start": process_start(os.getpid()),
                    "status": status,
                    "updated_at": utc_now(),
                    "runs": list(self.states.values()),
                },
            )

    def save(self, state: dict[str, Any], **changes: Any) -> None:
        with self.mutex:
            state.update(changes, updated_at=utc_now())
            write_json(self.root / "runs" / f"{state['id']}.json", state)
            self.publish()

    def claim(self, gpu: str) -> dict[str, Any] | None:
        with self.mutex:
            eligible = {"queued", "interrupted", "prepared", "completed"}
            if self.retry_failed:
                eligible.add("failed")
            for state in self.states.values():
                if state["id"] in self.claimed or state["status"] not in eligible:
                    continue
                if self.prepare_only and state["status"] == "prepared":
                    continue
                if state.get("gpu", gpu) != gpu:
                    continue
                self.claimed.add(state["id"])
                if "gpu" not in state:
                    recipe = load_recipe(Path(state["recipe"])) | {"gpu": gpu}
                    config = self.root / "configs" / f"{state['id']}.json"
                    if config.exists() and read_json(config) != recipe:
                        raise ValueError(
                            "An existing resolved config has a different GPU or recipe"
                        )
                    write_json(config, recipe)
                    state.update(gpu=gpu, config=str(config), config_sha256=sha256(config))
                self.save(
                    state,
                    status="running",
                    started_at=utc_now(),
                    attempts=state["attempts"] + 1,
                    error=None,
                    finished_at=None,
                )
                return state
        return None

    def environment(self, gpu: str) -> dict[str, str]:
        return dict(os.environ) | {
            "PYTHONPATH": str(Path(self.spec["source_root"]) / "src"),
            "PYTHONUNBUFFERED": "1",
            "PYTHONNOUSERSITE": "1",
            "CUDA_VISIBLE_DEVICES": gpu,
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
            "HF_HUB_OFFLINE": "1",
            "WANDB_MODE": "disabled",
        }

    def command(self, state: dict[str, Any], stage: str) -> list[str]:
        argv = [self.spec["python"], "-m", "segmentary.medical.cli"]
        config = state["config"]
        if stage == "prepare":
            return [
                *argv,
                stage,
                "--config",
                config,
                "--manifest",
                self.spec["manifest"],
                "--splits",
                self.spec["splits"],
            ]
        if stage == "evaluate":
            argv += [
                stage,
                "--manifest",
                self.spec["manifest"],
                "--splits",
                self.spec["splits"],
                "--predictions",
                state["predictions"],
                "--output",
                state["evaluation"],
                "--partition",
                "val",
            ]
            for key, value in self.spec.get("evaluation", {}).items():
                if key == "review_overlays":
                    if value:
                        argv.append("--review-overlays")
                else:
                    argv += ["--" + key.replace("_", "-"), str(value)]
            return argv
        if stage == "train":
            index = Path(state["workspace"]) / "checkpoint-index.json"
            stage = "resume" if index.exists() else "train"
        argv += [stage, "--config", config]
        if stage == "predict":
            argv += ["--partition", "val", "--checkpoint", "checkpoint_best.pth"]
        return argv

    def execute(self, state: dict[str, Any], stage: str, argv: list[str]) -> dict[str, Any]:
        if self.stop.is_set():
            raise InterruptedError("Campaign stop requested")
        for path, expected in self.input_hashes.items():
            if sha256(Path(path)) != expected:
                raise ValueError(f"Campaign input changed during execution: {path}")
        if sha256(Path(state["config"])) != state["config_sha256"]:
            raise ValueError("Resolved configuration changed during execution")
        log = self.root / "logs" / state["id"] / f"{stage}-{time.time_ns()}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        self.save(state, stage=stage, log=str(log), argv=argv, cli_pid=None)
        with log.open("wb") as stream:
            process = subprocess.Popen(
                argv,
                env=self.environment(state["gpu"]),
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            with self.mutex:
                self.processes[state["id"]] = process
            self.save(state, cli_pid=process.pid, cli_process_start=process_start(process.pid))
            returncode = process.wait()
        with self.mutex:
            self.processes.pop(state["id"], None)
        self.save(state, cli_pid=None, cli_process_start=None, returncode=returncode)
        if self.stop.is_set():
            raise InterruptedError("Campaign stop requested; resume from the last committed epoch")
        if returncode:
            tail = log.read_bytes()[-4000:].decode(errors="replace")
            raise RuntimeError(f"{stage} exited {returncode}; {log}\n{tail}")
        return output_json(log)

    def verify(self, state: dict[str, Any], stage: str) -> None:
        argv = [
            self.spec["python"],
            str(Path(self.spec["source_root"]) / "scripts/run_medical_campaign.py"),
            "_verify",
            "--config",
            state["config"],
            "--stage",
            stage,
        ]
        self.execute(state, f"verify-{stage}", argv)

    def stage_artifacts(self, state: dict[str, Any], stage: str) -> dict[str, str]:
        root = Path(state["workspace"])
        paths: list[Path] = []
        if stage == "prepare":
            paths = [root / "binding.json"]
        elif stage == "preprocess":
            paths = [root / "plan-binding.json"]
        elif stage == "train":
            paths = [
                root / "checkpoint-index.json",
                root / "scratch-origin.json",
                root / "training-result.json",
            ]
        elif stage == "predict":
            prediction = Path(state["predictions"])
            paths = sorted(prediction.glob("*.nii.gz"))
            paths += [
                prediction
                / (
                    "prediction-status.json"
                    if state["backend"] == "torch"
                    else "prediction-record.json"
                )
            ]
        elif stage == "evaluate":
            paths = [Path(state["evaluation"]) / name for name in ("report.json", "cases.csv")]
        return {str(path): sha256(path) for path in paths}

    def complete_stage(self, state: dict[str, Any], stage: str, *, recovered: bool = False) -> None:
        state["completed_stages"][stage] = {
            "completed_at": utc_now(),
            "recovered": recovered,
            "artifacts": self.stage_artifacts(state, stage),
        }
        self.save(state)

    def check_evaluation(self, state: dict[str, Any]) -> None:
        report = read_json(Path(state["evaluation"]) / "report.json")
        expected = read_json(Path(self.spec["splits"]))["val"]
        cases = report["cases"]
        if (
            len(cases) != len(expected)
            or {row["case_id"] for row in cases} != set(expected)
            or any(row["status"] != "ok" for row in cases)
            or report["coverage"]["valid_prediction_cases"] != len(expected)
            or report["manifest_fingerprint"]
            != read_json(Path(self.spec["manifest"]))["fingerprint"]
        ):
            raise ValueError(
                "Native validation evaluation has failed, missing, or unexpected cases"
            )

    def run_one(self, state: dict[str, Any]) -> None:
        root = Path(state["workspace"])
        try:
            self.source_check(self.spec)
            completed = state["completed_stages"]
            for record in completed.values():
                for path, expected in record["artifacts"].items():
                    if sha256(Path(path)) != expected:
                        raise ValueError(f"Completed stage artifact changed: {path}")
            if completed:
                last = max(completed, key=STAGES.index)
                self.verify(state, last)
            stages = STAGES[:2] if self.prepare_only else STAGES
            for stage in stages:
                if stage in completed:
                    continue
                if stage in {"prepare", "preprocess"}:
                    artifact = root / (
                        "binding.json" if stage == "prepare" else "plan-binding.json"
                    )
                    if artifact.exists():
                        self.verify(state, stage)
                        self.complete_stage(state, stage, recovered=True)
                        continue
                if stage == "train" and (root / "continuation.json").is_file():
                    continuation = read_json(root / "continuation.json")
                    if continuation.get("action") == "predict":
                        training_result = read_json(root / "training-result.json")
                        if training_result.get("completed") is not True:
                            raise ValueError(
                                "Prediction continuation has no completed parent training"
                            )
                        self.verify(state, stage)
                        self.complete_stage(state, stage, recovered=True)
                        continue
                if stage == "evaluate":
                    self.save(state, evaluation=str(self.root / "evaluations" / state["id"]))
                result = self.execute(state, stage, self.command(state, stage))
                if stage == "predict":
                    predictions = (
                        str(root / "predictions" / "val")
                        if state["backend"] == "torch"
                        else result["output"]
                    )
                    evidence = Path(predictions) / (
                        "prediction-status.json"
                        if state["backend"] == "torch"
                        else "prediction-record.json"
                    )
                    self.save(
                        state,
                        predictions=predictions,
                        checkpoint="checkpoint_best.pth",
                        selection_evidence=str(evidence),
                        selected_checkpoint_sha256=read_json(evidence)["checkpoint_sha256"],
                    )
                self.complete_stage(state, stage)
            if "evaluate" in completed:
                self.check_evaluation(state)
            self.save(
                state,
                status="prepared"
                if self.prepare_only and "evaluate" not in completed
                else "completed",
                stage=None,
                finished_at=utc_now(),
            )
        except InterruptedError as exc:
            self.save(state, status="interrupted", error=str(exc), finished_at=utc_now())
        except Exception as exc:
            self.save(state, status="failed", error=str(exc), finished_at=utc_now())

    def worker(self, gpu: str) -> None:
        try:
            while not self.stop.is_set():
                state = self.claim(gpu)
                if state is None:
                    return
                self.run_one(state)
        except Exception as exc:
            with self.mutex:
                self.worker_errors.append(f"GPU {gpu}: {exc}")
            self.stop_workers()

    def stop_workers(self) -> None:
        self.stop.set()
        with self.mutex:
            for process in self.processes.values():
                if process.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)

    def run(self, *, dashboard: bool = False) -> int:
        with singleton(self.root / ".campaign.lock"):
            self.initialize()
            if dashboard:
                # The driver can use stdlib Python while backends are isolated;
                # load monitoring code from this launcher checkout explicitly.
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
                from segmentary.campaign_dashboard import ensure_dashboard

                ensure_dashboard(self.root, Path(__file__).resolve().parents[1], sys.executable)
            self.claimed: set[str] = set()
            self.worker_errors: list[str] = []
            previous: dict[int, Any] = {}
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGTERM, signal.SIGINT):
                    previous[sig] = signal.getsignal(sig)
                    signal.signal(sig, lambda _sig, _frame: self.stop_workers())
            workers = [
                threading.Thread(target=self.worker, args=(gpu,), name=f"gpu-{gpu}")
                for gpu in self.spec["gpus"]
            ]
            try:
                for worker in workers:
                    worker.start()
                while any(worker.is_alive() for worker in workers):
                    for worker in workers:
                        worker.join(timeout=0.2)
                    self.publish()
                if self.worker_errors:
                    write_json(self.root / "worker-errors.json", {"errors": self.worker_errors})
                success = {"prepared", "completed"} if self.prepare_only else {"completed"}
                complete = all(state["status"] in success for state in self.states.values())
                status = (
                    "failed"
                    if self.worker_errors
                    else "completed"
                    if complete
                    else "interrupted"
                    if self.stop.is_set()
                    else "failed"
                )
                self.publish(status)
                return (
                    1 if self.worker_errors else 0 if complete else 130 if self.stop.is_set() else 1
                )
            finally:
                self.stop_workers()
                for sig, handler in previous.items():
                    signal.signal(sig, handler)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    if argv and argv[0] == "_verify":
        parser.add_argument("_verify")
        parser.add_argument("--config", type=Path, required=True)
        parser.add_argument("--stage", choices=STAGES, required=True)
        args = parser.parse_args(argv)
        verify_workspace(args.config, args.stage)
        print(json.dumps({"verified": args.stage}))
        return 0
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Do not start the shared tmux progress dashboard",
    )
    args = parser.parse_args(argv)
    try:
        return Campaign(
            args.spec,
            args.state_dir,
            prepare_only=args.prepare_only,
            retry_failed=args.retry_failed,
        ).run(dashboard=not args.no_dashboard)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"medical campaign: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
