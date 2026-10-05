#!/usr/bin/env python3
"""Ordered queue of Paul-fork recipe runs on HDRFS: starts each job when its GPUs are free.

    fork_queue.py check  --queue queue/rad-9-24-paper-models.yaml      # validate, touch nothing
    fork_queue.py run    --queue queue/rad-9-24-paper-models.yaml      # the loop (run in tmux)
    fork_queue.py status
    fork_queue.py reset  <job> [<job> ...]   # failed -> pending; only once its run dir is gone

``--run-root`` (default ``$PAUL_FORK_RUN_ROOT`` or the HDRFS run root) holds ``runs/``,
``queue-state.json``, ``locks/fork-queue.lock``, ``STOP_QUEUE`` and ``queue/`` (per-job
console logs, exit files, and launch attempts refused by ``fork_gpu_run.py``).

Queue file (YAML, or JSON with the same keys)::

    min_idle_seconds: 300          # a GPU must have been seen idle this long before the check
    holds:                         # GPUs that are never used while a tmux session is alive
      - {session: pf-paper-hrnet-rs19-paul, gpus: [2, 3, 4, 5]}
    jobs:
      - name: hrnet-direct-paul    # tmux session pf-q-<name>
        label: paper-hrnet__mapcity-direct__arm-paul   # checked against recipe + args + env
        recipe: paper-hrnet.sh
        args: [--rs19, none, --arm, paul]
        env: {HRNET_RAD_RECIPE: train_2}               # optional
        gpu_groups: [[2, 3, 4, 5], [6, 7, 8, 9]]
        depends_on: [hrnet-rs19-ours]                  # optional; must have finished with exit 0
        rs19_ckpt_from: hrnet-rs19-ours                # optional; resolver, passes --rs19-ckpt

Validation at load (everything refused, nothing started): a GPU group containing 0, 1 or any
index outside 2-9, a duplicate in a group, a group size the recipe does not take, an unknown
recipe, any argument other than ``--rs19/--arm/--rs19-ckpt`` (the queue sets ``--gpus`` and
``--run-dir``), an environment variable other than the recipe selectors, a label that is not
exactly what the recipe would write for these arguments or is not in
``recipes/write_provenance.py``'s allowed set, duplicate names or labels, a ``depends_on``
that is not an earlier job, a resolver without ``--rs19 ours`` or without its dependency.

Every 60 s (one ``tick``; if ``tmux list-panes`` fails for any reason, including "no server
running", nothing starts and only exit files finalise jobs): jobs whose tmux session ended
are finalised from
``<run_dir>/gpu-assignment.json`` (``exited`` + ``exit_code`` 0 = done, anything else =
failed; failed jobs are never retried automatically). A launch that ``fork_gpu_run.py``
refused because a GPU was busy or locked (its console says so and it wrote no
``gpu-assignment.json``) goes back to pending; its never-launched run directory is moved to
``queue/refused/``. Then, unless ``STOP_QUEUE`` exists (drain: no new starts, the loop exits
when nothing runs), pending jobs are considered in file order. A job whose dependencies are not
done is skipped, and so is one whose run directory already exists without a finished launcher
record (see below); the first other ready job that finds no free group blocks the jobs after
it, so the order is kept. A group is free when every GPU in it

- is not used by a running queue job,
- is not held by another alive tmux session: one named ``*-gpu-<index>`` (the Segmentary
  campaign's per-GPU services), one named ``rad-*``, ``pf-*`` or ``rtis-*`` (not the queue's
  own ``pf-q-*``) whose start command names it (``--gpus 2,3,4,5``, ``--gpu 6``,
  ``CUDA_VISIBLE_DEVICES=6``), or one matching a ``holds`` entry (for launchers whose command
  names no GPU, e.g. ``rad-catalog-launcher``),
- has been idle (no compute app, at most 100 MiB, 0 % utilisation) on every tick for at least
  ``min_idle_seconds`` (sequential launchers leave short gaps between their runs), and
- passes ``fork_gpu_run.check_idle`` right before the start: three passes 5 s apart.

The live nvidia-smi inventory must equal ``fork_gpu_run.py``'s frozen table, otherwise
nothing starts. The queue never sets GPU visibility: each job runs in its own tmux session
``pf-q-<name>`` as ``env -u CUDA_VISIBLE_DEVICES -u CUDA_DEVICE_ORDER -u NVIDIA_VISIBLE_DEVICES
... bash <recipe> ... --gpus <group> --run-dir <run_root>/runs/<label>``, so
``fork_gpu_run.py`` (via the recipe) is the only thing that assigns GPUs. It does not use
the Segmentary ``gpu_policy`` locks (the campaign takes none on the host).

A restart is idempotent: the state is ``queue-state.json``; a job whose run directory already
holds a finished launcher record is marked done (exit 0) or failed without starting; a run
directory without one (another process may be using it) keeps the job pending and is
re-checked every tick. Only one queue runs per run root (``flock``).

``rs19_ckpt_from`` resolves the best-by-mIoU checkpoint of that finished RS19 run, exactly the
file ``recipes/_common.sh`` ``pf_check_rs19_ours`` accepts: the run's ``provenance.json`` has
the RS19 label, is not a dry run or probe, ``gpu-assignment.json`` says exited 0, and there
is exactly one ``train/best_checkpoint_ep<N>.pth`` (HRNet) or one
``ckpt/**/best_epoch_<N>_mean-iu_<x>.pth`` (SFNet) inside the run directory.

Standard library only (PyYAML is needed for a ``.yaml`` queue file).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RECIPES_DIR = HERE / "recipes"
DEFAULT_RUN_ROOT = "/data/izadia1/projects/segmentary-runs/paul-fork-rad-9-24"


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"fork_queue: cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GPU = _load("paul_fork_queue_gpu_run", HERE / "fork_gpu_run.py")
PROV = _load("paul_fork_queue_provenance", RECIPES_DIR / "write_provenance.py")

SESSION_PREFIX = "pf-q-"
TICK_SECONDS = 60.0
IDLE_PAUSE_SECONDS = 5.0
DEFAULT_MIN_IDLE_SECONDS = 300.0
STATUSES = ("pending", "running", "done", "failed")
NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
GPU_SUFFIX_SESSION = re.compile(r".*-gpu-(\d+)")
# Sessions whose start command names GPUs hold them (campaign services, other fork runs).
WATCHED_SESSIONS = ("rad-*", "pf-*", "rtis-*")
GPU_IN_COMMAND = re.compile(r"(?:--gpus?[ =]|CUDA_VISIBLE_DEVICES=)([0-9]+(?:,[0-9]+)*)")
# Recipe -> (label family or fixed RS19 label, GPU counts it accepts, recipe selector variable).
RECIPES = {
    "paper-hrnet.sh": ("paper-hrnet", (4,), "HRNET_RAD_RECIPE"),
    "paper-sfnet.sh": ("paper-sfnet", (2, 4), "SFNET_RAD_RECIPE"),
    "hrnet-rs19-ours.sh": ("hrnet-rs19-ours", (4,), "HRNET_RS19_RECIPE"),
    "sfnet-rs19-ours.sh": ("sfnet-rs19-ours", (2, 4, 8), None),
}
RS19_RUN_FOR = {"paper-hrnet.sh": "hrnet-rs19-ours", "paper-sfnet.sh": "sfnet-rs19-ours"}
JOB_KEYS = {"name", "label", "recipe", "args", "env", "gpu_groups", "depends_on", "rs19_ckpt_from"}
# The child may not inherit these from the tmux server; the job sets the selectors it needs.
UNSET = (
    "CUDA_VISIBLE_DEVICES",
    "CUDA_DEVICE_ORDER",
    "NVIDIA_VISIBLE_DEVICES",
    "PROBE_EPOCHS",
    "PAUL_FORK_DRY_RUN",
    "PAUL_FORK_PINS_FILE",
    "HRNET_RAD_RECIPE",
    "SFNET_RAD_RECIPE",
    "HRNET_RS19_RECIPE",
    # Path overrides inherited from the tmux server: the jobs use the recipes' defaults.
    "FORK_GPU_RUN",
    "PAUL_FORK_ADAPTERS",
    "PAUL_FORK_ENV",
    "PAUL_FORK_PATCHES",
    "PAUL_FORK_PYTHON",
    "PAUL_FORK_RS19_ROOT",
    "PAUL_FORK_TOOL_PYTHON",
)
# fork_gpu_run.py refusals after which the job goes back to pending (GPU taken meanwhile).
BUSY_REFUSAL = re.compile(
    r"fork_gpu_run: REFUSED: (GPU \d+ is not idle|GPU \d+ is locked by another launcher"
    r"|Cannot check that the GPUs are idle)"
)


class QueueError(Exception):
    """The queue file or state is not acceptable; nothing is started."""


def now_iso(clock: float) -> str:
    return dt.datetime.fromtimestamp(clock, dt.UTC).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


# --------------------------------------------------------------------------- queue file


@dataclass(frozen=True)
class Job:
    name: str
    label: str
    recipe: str
    args: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    gpu_groups: tuple[tuple[int, ...], ...]
    depends_on: tuple[str, ...] = ()
    rs19_ckpt_from: str | None = None

    @property
    def session(self) -> str:
        return SESSION_PREFIX + self.name

    def spec_digest(self) -> str:
        spec = [self.label, self.recipe, self.args, self.env, self.rs19_ckpt_from]
        return hashlib.sha256(json.dumps(spec).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Hold:
    session: str  # fnmatch pattern
    gpus: tuple[int, ...]


@dataclass(frozen=True)
class Spec:
    jobs: tuple[Job, ...]
    holds: tuple[Hold, ...]
    min_idle_seconds: float
    source: str
    sha256: str

    def job(self, name: str) -> Job:
        return next(job for job in self.jobs if job.name == name)


def check_group(group: Any, where: str) -> tuple[int, ...]:
    if not isinstance(group, list) or not group:
        raise QueueError(f"{where}: a GPU group is a non-empty list, got {group!r}")
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in group):
        raise QueueError(f"{where}: GPU indices must be integers, got {group!r}")
    if set(group) & set(GPU.FORBIDDEN) or set(group) & {0, 1}:
        raise QueueError(f"{where}: group {group} contains GPU 0 or 1 (reserved for others)")
    if any(i not in GPU.ALLOWED or not 2 <= i <= 9 for i in group):
        raise QueueError(f"{where}: group {group} has an index outside 2-9")
    if len(set(group)) != len(group):
        raise QueueError(f"{where}: group {group} has duplicates")
    return tuple(sorted(group))


def option(args: tuple[str, ...], flag: str) -> str | None:
    return args[args.index(flag) + 1] if flag in args else None


def expected_label(recipe: str, args: tuple[str, ...], env: dict[str, str]) -> str:
    family, _, selector = RECIPES[recipe]
    if family in PROV.RS19_LABELS:
        return family
    rs19, arm = option(args, "--rs19"), option(args, "--arm")
    chain = "mapcity-direct" if rs19 == "none" else f"rs19-{rs19}"
    variant = env.get(selector, PROV.DEFAULT_RECIPE) if selector else PROV.DEFAULT_RECIPE
    return PROV.rad_label(f"{family}__{chain}", arm, variant)


def parse_job(raw: Any, index: int, earlier: dict[str, Job]) -> Job:
    where = f"job #{index + 1}"
    if not isinstance(raw, dict):
        raise QueueError(f"{where}: must be a mapping")
    unknown = set(raw) - JOB_KEYS
    if unknown:
        raise QueueError(f"{where}: unknown keys {sorted(unknown)}")
    name = raw.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise QueueError(f"{where}: name must match {NAME.pattern}, got {name!r}")
    where = f"job {name}"
    if name in earlier:
        raise QueueError(f"{where}: duplicate name")
    recipe = raw.get("recipe")
    if recipe not in RECIPES:
        raise QueueError(f"{where}: recipe must be one of {sorted(RECIPES)}, got {recipe!r}")
    family, counts, selector = RECIPES[recipe]
    args = raw.get("args", [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args) or len(args) % 2:
        raise QueueError(f"{where}: args must be a list of '--flag value' pairs")
    args = tuple(args)
    flags = args[0::2]
    allowed = () if family in PROV.RS19_LABELS else ("--rs19", "--arm", "--rs19-ckpt")
    bad = [f for f in flags if f not in allowed]
    if bad or len(set(flags)) != len(flags):
        raise QueueError(
            f"{where}: arguments {bad or flags} not allowed (allowed once each: {list(allowed)}; "
            "the queue sets --gpus and --run-dir)"
        )
    env = raw.get("env") or {}
    if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
        raise QueueError(f"{where}: env must map names to strings")
    if set(env) - ({selector} if selector else set()):
        raise QueueError(f"{where}: env may only set {selector or 'nothing'} for {recipe}")
    if family == "hrnet-rs19-ours" and env.get(selector, PROV.DEFAULT_RECIPE) != (
        PROV.DEFAULT_RECIPE
    ):
        raise QueueError(f"{where}: RS19 recipe variants share one label; not queued")
    if family not in PROV.RS19_LABELS:
        if option(args, "--rs19") not in ("paul", "ours", "none"):
            raise QueueError(f"{where}: --rs19 must be paul, ours or none")
        if option(args, "--arm") not in PROV.ARMS:
            raise QueueError(f"{where}: --arm must be one of {list(PROV.ARMS)}")
    label = expected_label(recipe, args, env)
    if raw.get("label") != label:
        raise QueueError(f"{where}: label {raw.get('label')!r}, but the recipe would write {label}")
    if label not in PROV.ALLOWED_LABELS:
        raise QueueError(f"{where}: {label} is not an allowed label (write_provenance.py)")
    groups = raw.get("gpu_groups")
    if not isinstance(groups, list) or not groups:
        raise QueueError(f"{where}: gpu_groups must be a non-empty list of groups")
    parsed = tuple(check_group(g, where) for g in groups)
    for group in parsed:
        if len(group) not in counts:
            raise QueueError(f"{where}: {recipe} takes {counts} GPUs, group {list(group)} has not")
    depends = raw.get("depends_on") or []
    if not isinstance(depends, list) or any(d not in earlier for d in depends):
        raise QueueError(f"{where}: depends_on must name earlier jobs, got {depends!r}")
    source = raw.get("rs19_ckpt_from")
    if source is not None:
        if option(args, "--rs19") != "ours" or option(args, "--rs19-ckpt") is not None:
            raise QueueError(f"{where}: rs19_ckpt_from needs --rs19 ours and no --rs19-ckpt")
        if source not in depends or earlier[source].label != RS19_RUN_FOR[recipe]:
            raise QueueError(
                f"{where}: rs19_ckpt_from must be a {RS19_RUN_FOR[recipe]} job in depends_on"
            )
    elif option(args, "--rs19") == "ours" and option(args, "--rs19-ckpt") is None:
        raise QueueError(f"{where}: --rs19 ours needs --rs19-ckpt or rs19_ckpt_from")
    return Job(
        name=name,
        label=label,
        recipe=recipe,
        args=args,
        env=tuple(sorted(env.items())),
        gpu_groups=parsed,
        depends_on=tuple(depends),
        rs19_ckpt_from=source,
    )


def load_spec(path: Path) -> Spec:
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as error:
            raise QueueError(f"{path}: PyYAML is not installed; use a .json queue file") from error
        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    if not isinstance(raw, dict) or set(raw) - {"jobs", "holds", "min_idle_seconds", "comment"}:
        raise QueueError(f"{path}: top level must be a mapping with jobs/holds/min_idle_seconds")
    jobs: dict[str, Job] = {}
    for index, item in enumerate(raw.get("jobs") or []):
        job = parse_job(item, index, jobs)
        jobs[job.name] = job
    if not jobs:
        raise QueueError(f"{path}: no jobs")
    labels = [job.label for job in jobs.values()]
    if len(set(labels)) != len(labels):
        raise QueueError(f"{path}: two jobs write the same label (and run directory)")
    holds = []
    for item in raw.get("holds") or []:
        if not isinstance(item, dict) or not isinstance(item.get("session"), str):
            raise QueueError(f"{path}: a hold is {{session: <tmux name or glob>, gpus: [...]}}")
        gpus = item.get("gpus")
        if not isinstance(gpus, list) or not all(isinstance(i, int) and 0 <= i <= 9 for i in gpus):
            raise QueueError(f"{path}: hold {item['session']}: gpus must be indices 0-9")
        holds.append(Hold(item["session"], tuple(sorted(gpus))))
    min_idle = raw.get("min_idle_seconds", DEFAULT_MIN_IDLE_SECONDS)
    if not isinstance(min_idle, int | float) or min_idle < 0:
        raise QueueError(f"{path}: min_idle_seconds must be >= 0")
    return Spec(
        jobs=tuple(jobs.values()),
        holds=tuple(holds),
        min_idle_seconds=float(min_idle),
        source=str(path.resolve()),
        sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


# --------------------------------------------------------------------------- the machine


def run_tmux(args: list[str]) -> tuple[int, str, str]:
    try:
        done = subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        return 127, "", repr(error)
    return done.returncode, done.stdout, done.stderr


@dataclass
class Machine:
    """Everything that touches the host, injectable for tests."""

    smi: Callable[[list[str]], str] = GPU.run_nvidia_smi
    tmux: Callable[[list[str]], tuple[int, str, str]] = run_tmux
    clock: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    idle_pause_seconds: float = IDLE_PAUSE_SECONDS
    log: Callable[[str], None] = field(default=lambda m: print(m, flush=True))

    def host(self):
        return GPU.Host(smi=self.smi, sleep=self.sleep, idle_pause_seconds=self.idle_pause_seconds)


def tmux_sessions(machine: Machine) -> dict[str, str] | None:
    """Alive session -> its panes' start commands; ``None`` when tmux cannot be read.

    Any failure is ``None`` (start nothing, finalise only from exit files), including "no
    server running" / "error connecting": the queue itself runs in tmux, so those mean the
    socket is gone (e.g. a /tmp cleaner), not that the campaign and the HRNet run ended.
    Treating them as "no sessions" would drop every session-based hold at once.
    """
    code, out, _ = machine.tmux(
        ["list-panes", "-a", "-F", "#{session_name}\t#{pane_start_command}"]
    )
    if code != 0:
        return None
    sessions: dict[str, str] = {}
    for line in out.splitlines():
        name, _, command = line.partition("\t")
        if name.strip():
            sessions[name.strip()] = (sessions.get(name.strip(), "") + " " + command).strip()
    return sessions


def idle_now(machine: Machine) -> dict[int, bool] | None:
    """Per allowed GPU: idle right now. ``None`` if the inventory or a query is not right."""
    host = machine.host()
    try:
        GPU.check_inventory(host)
        text = machine.smi(
            ["--query-gpu=index,uuid,memory.used,utilization.gpu", "--format=csv,noheader,nounits"]
        )
        busy = {uuid for uuid, _ in GPU.compute_apps(host)}
    except (GPU.Refusal, OSError, subprocess.SubprocessError, RuntimeError) as error:
        machine.log(f"fork_queue: cannot read the GPUs, starting nothing: {error}")
        return None
    idle = {}
    for row in GPU._rows(text):
        if len(row) != 4 or not row[0].isdigit() or int(row[0]) not in GPU.ALLOWED:
            continue
        index, uuid, memory, util = int(row[0]), GPU.normalize_uuid(row[1]), row[2], row[3]
        idle[index] = (
            uuid == GPU.normalize_uuid(GPU.ALLOWED[index][0])
            and uuid not in busy
            and memory.isdigit()
            and util.isdigit()
            and int(memory) <= GPU.IDLE_MAX_MEMORY_MIB
            and int(util) == 0
        )
    return idle if set(idle) == set(GPU.ALLOWED) else None


# --------------------------------------------------------------------------- run records


def launcher_record(run_dir: Path) -> dict | None:
    record = read_json(run_dir / "gpu-assignment.json")
    return record if isinstance(record, dict) else None


def finished(record: dict | None) -> bool:
    return bool(record) and record.get("status") in ("exited", "violation", "launch-failed")


def resolve_rs19_checkpoint(run_dir: Path, rs19_label: str) -> Path:
    """The best-by-mIoU checkpoint of a finished RS19 run (what pf_check_rs19_ours accepts)."""
    prov = read_json(run_dir / "provenance.json")
    if not isinstance(prov, dict):
        raise QueueError(f"{run_dir}/provenance.json missing or unreadable")
    if prov.get("label") != rs19_label or prov.get("dry_run") or prov.get("probe_epochs"):
        raise QueueError(
            f"{run_dir}: label={prov.get('label')} dry_run={prov.get('dry_run')} "
            f"probe_epochs={prov.get('probe_epochs')}; not a finished {rs19_label} run"
        )
    record = launcher_record(run_dir) or {}
    if record.get("status") != "exited" or record.get("exit_code") != 0:
        raise QueueError(
            f"{run_dir}: not finished (status={record.get('status')} "
            f"exit_code={record.get('exit_code')})"
        )
    if rs19_label == "hrnet-rs19-ours":
        found = sorted((run_dir / "train").glob("best_checkpoint_ep*.pth"))
        pattern = re.compile(r"best_checkpoint_ep\d+\.pth")
    else:
        found = sorted((run_dir / "ckpt").rglob("best_epoch_*_mean-iu_*.pth"))
        pattern = re.compile(r"best_epoch_\d+_mean-iu_[0-9.]+\.pth")
    found = [p for p in found if pattern.fullmatch(p.name) and p.is_file()]
    if len(found) != 1:
        raise QueueError(
            f"{run_dir}: expected exactly one best checkpoint, found {[str(p) for p in found]}"
        )
    ckpt = found[0]
    if run_dir.resolve() not in ckpt.resolve().parents:
        raise QueueError(f"{ckpt} resolves outside {run_dir}")
    # pf_check_rs19_ours takes the nearest provenance.json above the checkpoint.
    nearest = next(p for p in ckpt.resolve().parents if (p / "provenance.json").is_file())
    if nearest != run_dir.resolve():
        raise QueueError(f"{ckpt}: nearest provenance.json is in {nearest}, not {run_dir}")
    return ckpt


# --------------------------------------------------------------------------- the queue


class Queue:
    def __init__(self, spec: Spec, run_root: Path, machine: Machine | None = None) -> None:
        self.spec, self.root = spec, run_root
        self.machine = machine or Machine()
        self.state_path = run_root / "queue-state.json"
        self.stop_path = run_root / "STOP_QUEUE"
        self.work = run_root / "queue"
        self.idle_since: dict[int, float] = {}
        self.state = self.load_state()

    # -- state

    def load_state(self) -> dict:
        state = read_json(self.state_path) if self.state_path.exists() else None
        if self.state_path.exists() and not isinstance(state, dict):
            raise QueueError(f"{self.state_path} is unreadable; fix or move it")
        state = state or {"schema_version": 1, "jobs": {}}
        names = {job.name for job in self.spec.jobs}
        for name, entry in state["jobs"].items():
            if entry.get("status") == "running" and name not in names:
                raise QueueError(f"job {name} is running but no longer in the queue file")
        for job in self.spec.jobs:
            entry = state["jobs"].setdefault(job.name, {"status": "pending"})
            if entry["status"] not in STATUSES:
                raise QueueError(f"job {job.name}: unknown status {entry['status']!r}")
            if entry["status"] != "pending" and entry.get("spec") not in (None, job.spec_digest()):
                raise QueueError(
                    f"job {job.name} ({entry['status']}) was changed in the queue file after it "
                    "started; give the changed job a new name"
                )
            entry.setdefault("label", job.label)
            entry.setdefault("run_dir", str(self.run_dir(job)))
        state.update(queue_file=self.spec.source, queue_sha256=self.spec.sha256)
        return state

    def save(self) -> None:
        self.state["updated_at"] = now_iso(self.machine.clock())
        write_json(self.state_path, self.state)

    def entry(self, job: Job) -> dict:
        return self.state["jobs"][job.name]

    def event(self, job: Job, what: str) -> None:
        entry = self.entry(job)
        entry.setdefault("events", []).append(f"{now_iso(self.machine.clock())} {what}")
        self.machine.log(f"fork_queue: {job.name}: {what}")

    def run_dir(self, job: Job) -> Path:
        return self.root / "runs" / job.label

    def exit_file(self, job: Job) -> Path:
        return self.work / f"{job.name}.exit"

    def set(self, job: Job, status: str, **fields: Any) -> None:
        entry = self.entry(job)
        entry.update(status=status, **fields)
        if status in ("done", "failed") and not entry.get("ended_at"):
            entry["ended_at"] = now_iso(self.machine.clock())

    # -- finishing

    def classify_existing(self, job: Job) -> bool:
        """A pending job whose run directory exists: adopt a finished run, else wait."""
        run_dir = self.run_dir(job)
        if not run_dir.exists() or not any(run_dir.iterdir()):
            return False
        record = launcher_record(run_dir)
        if finished(record):
            self.finish_from_record(job, record, "found an already finished run directory")
        else:
            reason = "run directory exists without a finished launcher record; not started"
            if self.entry(job).get("reason") != reason:
                self.event(job, reason)
            self.entry(job)["reason"] = reason
        return True

    def finish_from_record(self, job: Job, record: dict, why: str) -> None:
        code = record.get("exit_code")
        prov = read_json(self.run_dir(job) / "provenance.json") or {}
        if record.get("status") == "exited" and code == 0 and prov.get("label") == job.label:
            self.set(job, "done", exit_code=0, reason=None)
        else:
            reason = f"launcher status={record.get('status')} exit_code={code}"
            if prov.get("label") != job.label:
                reason += f"; provenance label {prov.get('label')!r} is not {job.label}"
            self.set(job, "failed", exit_code=code, reason=reason)
        for key in ("started_at", "ended_at"):
            stamp = record.get(key)
            if isinstance(stamp, int | float) and not self.entry(job).get(f"launcher_{key}"):
                self.entry(job)[f"launcher_{key}"] = now_iso(stamp)
        self.event(job, f"{why}: {self.entry(job)['status']} ({self.entry(job).get('reason')})")

    def finalize(self, job: Job) -> None:
        """The job's session ended: done, failed, or back to pending after a busy refusal."""
        run_dir = self.run_dir(job)
        record = launcher_record(run_dir)
        wrapper = self.exit_file(job)
        code_text = wrapper.read_text().strip() if wrapper.is_file() else ""
        wrapper_code = int(code_text) if code_text.lstrip("-").isdigit() else None
        self.entry(job)["recipe_exit_code"] = wrapper_code
        if record is not None and record.get("status") == "running":
            self.set(
                job,
                "failed",
                exit_code=None,
                reason="session ended but the launcher "
                "record still says running (launcher killed?)",
            )
            self.event(job, "failed: launcher record still 'running'")
            return
        if finished(record):
            self.finish_from_record(job, record, "session ended")
            return
        console = run_dir / "console.log"
        text = console.read_text(errors="replace") if console.is_file() else ""
        match = BUSY_REFUSAL.search(text)
        if match:
            stamp = dt.datetime.fromtimestamp(self.machine.clock(), dt.UTC).strftime(
                "%Y%m%dT%H%M%S"
            )
            aside = self.work / "refused" / f"{job.label}.{stamp}"
            aside.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(run_dir), str(aside))
            if wrapper.exists():
                wrapper.replace(aside / "queue.exit")
            entry = self.entry(job)
            entry["launch_refusals"] = entry.get("launch_refusals", 0) + 1
            self.set(
                job,
                "pending",
                gpus=None,
                reason=f"launch refused: {match.group(1)}",
                last_refusal=f"{now_iso(self.machine.clock())} {match.group(1)} -> {aside}",
            )
            self.event(
                job,
                f"fork_gpu_run refused ({match.group(1)}); pending again, run "
                f"directory moved to {aside}",
            )
            return
        self.set(
            job,
            "failed",
            exit_code=wrapper_code,
            reason=f"recipe exited {wrapper_code} before launching (see {self.log(job)})",
        )
        self.event(job, f"failed before launch (recipe exit {wrapper_code})")

    def log(self, job: Job) -> Path:
        return self.work / f"{job.name}.log"

    # -- starting

    def held(self, sessions: dict[str, str]) -> set[int]:
        """GPUs that other alive tmux sessions were started with (or are configured to hold)."""
        gpus: set[int] = set()
        own = {j.session for j in self.spec.jobs if self.entry(j)["status"] == "running"}
        for name, command in sessions.items():
            if name in own:
                continue  # the queue's running jobs are tracked by reservation
            match = GPU_SUFFIX_SESSION.fullmatch(name)
            if match:
                gpus.add(int(match.group(1)))
            if any(fnmatchcase(name, pattern) for pattern in WATCHED_SESSIONS):
                for listed in GPU_IN_COMMAND.findall(command):
                    gpus.update(int(i) for i in listed.split(","))
            for hold in self.spec.holds:
                if fnmatchcase(name, hold.session):
                    gpus.update(hold.gpus)
        return gpus

    def reserved(self) -> set[int]:
        return {
            i
            for job in self.spec.jobs
            if self.entry(job)["status"] == "running"
            for i in self.entry(job).get("gpus") or []
        }

    def free_group(self, job: Job, blocked: set[int]) -> tuple[int, ...] | None:
        now = self.machine.clock()
        for group in job.gpu_groups:
            if set(group) & blocked:
                continue
            settled = all(
                i in self.idle_since and now - self.idle_since[i] >= self.spec.min_idle_seconds
                for i in group
            )
            if not settled:
                continue
            try:
                GPU.check_idle(self.machine.host(), group)
            except GPU.Refusal as error:
                self.machine.log(f"fork_queue: {job.name}: group {list(group)} not idle: {error}")
                for i in group:
                    self.idle_since.pop(i, None)
                continue
            return group
        return None

    def dependency_state(self, job: Job) -> str:
        states = [self.state["jobs"][d]["status"] for d in job.depends_on]
        if "failed" in states:
            return "failed"
        return "ready" if all(s == "done" for s in states) else "waiting"

    def command(self, job: Job, group: tuple[int, ...], rs19_ckpt: Path | None) -> str:
        args = list(job.args)
        if rs19_ckpt is not None:
            args += ["--rs19-ckpt", str(rs19_ckpt)]
        argv = ["env"]
        for name in UNSET:
            argv += ["-u", name]
        argv += [f"PAUL_FORK_RUN_ROOT={self.root}", *(f"{k}={v}" for k, v in job.env)]
        argv += ["bash", str(RECIPES_DIR / job.recipe), *args]
        argv += ["--gpus", ",".join(map(str, group)), "--run-dir", str(self.run_dir(job))]
        exit_file = self.exit_file(job)
        tmp = exit_file.with_name(exit_file.name + ".tmp")
        script = (
            f"{shlex.join(argv)} >>{shlex.quote(str(self.log(job)))} 2>&1; "
            f"echo $? >{shlex.quote(str(tmp))} && mv {shlex.quote(str(tmp))} "
            f"{shlex.quote(str(exit_file))}"
        )
        return "bash -c " + shlex.quote(script)

    def start(self, job: Job, group: tuple[int, ...], sessions: dict[str, str]) -> bool:
        entry = self.entry(job)
        rs19_ckpt = None
        if job.rs19_ckpt_from:
            source = self.spec.job(job.rs19_ckpt_from)
            try:
                rs19_ckpt = resolve_rs19_checkpoint(self.run_dir(source), source.label)
            except QueueError as error:
                self.set(job, "failed", reason=f"rs19 checkpoint not resolved: {error}")
                self.event(job, f"failed: {error}")
                return False
            entry["rs19_ckpt"] = str(rs19_ckpt)
        if job.session in sessions:
            entry["reason"] = f"tmux session {job.session} already exists; not started"
            return False
        self.work.mkdir(parents=True, exist_ok=True)
        self.exit_file(job).unlink(missing_ok=True)
        (self.root / "runs").mkdir(parents=True, exist_ok=True)
        command = self.command(job, group, rs19_ckpt)
        code, _, err = self.machine.tmux(["new-session", "-d", "-s", job.session, command])
        if code != 0:
            entry["reason"] = f"tmux new-session failed: {err.strip()}"
            self.event(job, entry["reason"])
            return False
        self.set(
            job,
            "running",
            gpus=list(group),
            session=job.session,
            started_at=now_iso(self.machine.clock()),
            ended_at=None,
            exit_code=None,
            reason=None,
            spec=job.spec_digest(),
            command=command,
            log=str(self.log(job)),
        )
        self.event(job, f"started on GPUs {list(group)} in tmux session {job.session}")
        return True

    # -- one pass

    def tick(self) -> bool:
        """One pass. Returns False once nothing is running and nothing can start any more."""
        sessions = tmux_sessions(self.machine)
        for job in self.spec.jobs:
            if self.entry(job)["status"] != "running":
                continue
            gone = sessions is not None and job.session not in sessions
            if self.exit_file(job).is_file() or gone:
                self.finalize(job)
        stopping = self.stop_path.exists()
        if sessions is None:
            self.idle_since.clear()  # GPUs were not watched meanwhile; settle again
        if not stopping and sessions is not None:
            self.start_ready(sessions)
        self.save()
        running = any(self.entry(j)["status"] == "running" for j in self.spec.jobs)
        if stopping:
            return running
        can_start = any(
            self.entry(j)["status"] == "pending" and self.dependency_state(j) != "failed"
            for j in self.spec.jobs
        )
        return running or can_start

    def start_ready(self, sessions: dict[str, str]) -> None:
        idle = idle_now(self.machine)
        now = self.machine.clock()
        if idle is None:
            self.idle_since.clear()
            return
        for index, is_idle in idle.items():
            if is_idle:
                self.idle_since.setdefault(index, now)
            else:
                self.idle_since.pop(index, None)
        blocked = self.reserved() | self.held(sessions)
        for job in self.spec.jobs:
            entry = self.entry(job)
            if entry["status"] != "pending":
                continue
            deps = self.dependency_state(job)
            if deps != "ready":
                entry["reason"] = (
                    "a dependency failed" if deps == "failed" else "waiting for dependencies"
                )
                continue
            if self.classify_existing(job):
                continue
            group = self.free_group(job, blocked)
            if group is None:
                entry["reason"] = "waiting for a free GPU group"
                break  # keep the order: later jobs do not overtake this one
            if self.start(job, group, sessions):
                blocked |= set(group)
            elif entry["status"] == "pending":
                break  # tmux refused or the session name is taken: keep the order

    def loop(self, interval: float = TICK_SECONDS) -> int:
        while self.tick():
            self.machine.sleep(interval)
        self.machine.log("fork_queue: nothing left to run; exiting")
        return 0


# --------------------------------------------------------------------------- CLI


@contextlib.contextmanager
def single_instance(run_root: Path):
    path = run_root / "locks" / "fork-queue.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise QueueError(f"another fork_queue holds {path}") from None
    try:
        yield
    finally:
        handle.close()


def print_status(state: dict) -> None:
    for name, entry in state.get("jobs", {}).items():
        gpus = ",".join(map(str, entry.get("gpus") or [])) or "-"
        print(
            f"{entry.get('status', '?'):8} {name:32} gpus={gpus:8} exit={entry.get('exit_code')} "
            f"{entry.get('label', '')} {entry.get('reason') or ''}".rstrip()
        )


def main(argv: list[str] | None = None, machine: Machine | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("command", choices=("check", "run", "status", "reset"))
    p.add_argument("jobs", nargs="*", help="reset: the failed jobs to make pending again")
    p.add_argument("--queue", type=Path, help="queue file (.yaml/.yml or .json)")
    p.add_argument(
        "--run-root",
        type=Path,
        default=Path(os.environ.get("PAUL_FORK_RUN_ROOT", DEFAULT_RUN_ROOT)),
    )
    p.add_argument("--once", action="store_true", help="run: one pass, then exit")
    p.add_argument("--interval", type=float, default=TICK_SECONDS)
    args = p.parse_args(argv)
    root = args.run_root.resolve()
    try:
        if args.command == "status":
            print_status(read_json(root / "queue-state.json") or {})
            return 0
        if args.queue is None:
            raise QueueError("--queue is required")
        spec = load_spec(args.queue)
        if args.command == "check":
            for job in spec.jobs:
                deps = f" after {','.join(job.depends_on)}" if job.depends_on else ""
                groups = " | ".join(",".join(map(str, g)) for g in job.gpu_groups)
                env = " ".join(f"{k}={v}" for k, v in job.env)
                print(f"{job.name:32} {job.label}  [{groups}]{deps} {env}".rstrip())
            print(f"{len(spec.jobs)} jobs OK; holds: {[(h.session, h.gpus) for h in spec.holds]}")
            return 0
        with single_instance(root):
            queue = Queue(spec, root, machine)
            if args.command == "reset":
                for name in args.jobs:
                    job = spec.job(name) if name in {j.name for j in spec.jobs} else None
                    if job is None or queue.entry(job)["status"] != "failed":
                        raise QueueError(f"{name}: only a failed job of this queue can be reset")
                    if queue.run_dir(job).exists():
                        raise QueueError(f"{name}: move {queue.run_dir(job)} aside first")
                    queue.set(job, "pending", reason="reset by hand", exit_code=None, gpus=None)
                    queue.entry(job).pop("ended_at", None)
                    queue.event(job, "reset to pending by hand")
                queue.save()
                return 0
            if args.once:
                queue.tick()
                return 0
            return queue.loop(args.interval)
    except QueueError as error:
        print(f"fork_queue: REFUSED: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
