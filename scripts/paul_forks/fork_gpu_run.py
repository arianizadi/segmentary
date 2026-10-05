#!/usr/bin/env python3
"""Fail-closed GPU launcher for the Paul-fork runs on HDRFS: GPUs 2-9 only, never 0 or 1.

    fork_gpu_run.py --gpus 2,3 --run-dir <run_dir> --python <env>/bin/python -- \\
        <env>/bin/python -m torch.distributed.run --standalone --nproc_per_node=2 train.py ...

Before the command starts, the launcher:

1. accepts only a non-empty, duplicate-free subset of the frozen allowlist (indices 2-9,
   each pinned to its full UUID and PCI bus id). GPUs 0 and 1 are named explicitly as
   forbidden. There is no override flag;
2. refuses to run if the caller's environment already sets ``CUDA_VISIBLE_DEVICES``,
   ``CUDA_DEVICE_ORDER`` or ``NVIDIA_VISIBLE_DEVICES``, even to an empty value;
3. requires the live ``nvidia-smi`` inventory to equal the frozen 10-GPU table exactly
   (index, UUID and PCI bus id), so a re-enumeration, card swap or wrong host stops it;
4. takes a non-blocking ``flock`` per GPU on ``/tmp/segmentary-exclusive-gpu-<idx>.lock``
   (the September ``idle_gpu_run.py`` name) and ``/tmp/segmentary-gpu-<uuid>.lock``.
   ``src/segmentary/gpu_policy.py`` has no host-level lock (its campaign locks are
   ``<campaign>/locks/gpu-<idx>.lock``), so the Segmentary campaign and the fork runs
   must be planned on disjoint GPU sets;
5. requires three idle passes, 1 s apart: no compute app, at most 100 MiB used and 0 %
   utilisation on every requested GPU;
6. builds the child environment with ``CUDA_DEVICE_ORDER=PCI_BUS_ID``,
   ``CUDA_VISIBLE_DEVICES=<UUIDs>`` (sorted by index, so rank 0 is the lowest index) and
   ``OMP_NUM_THREADS=2``;
7. runs a preflight with ``--python`` in exactly that environment: torch must see as many
   devices as were assigned and every device UUID must be one of the assigned UUIDs.

Before the command starts the launcher also makes itself the child subreaper
(``prctl(PR_SET_CHILD_SUBREAPER)``, Linux only; refused elsewhere). torchrun starts every
worker in its own session, so if the torchrun agent dies its workers would otherwise be
re-parented to init and leave the watched tree; as subreaper they are re-parented to the
launcher and stay watched, and they are terminated before the GPU locks are released.

The command then starts in its own session. Every 10 s a watchdog collects the process
tree (descendants by parent pid, plus every process in the child's session or process
group, plus every adopted orphan, read from ``/proc``) and compares it with
``nvidia-smi --query-compute-apps``. Any
process of the tree holding a context on an unassigned UUID gets the whole tree SIGTERM,
then SIGKILL after 30 s; the violation is recorded and the launcher exits 3. Three
consecutive failed inspections are treated the same way. SIGTERM, SIGINT, SIGHUP (closed
ssh / tmux session) or SIGQUIT sent to the launcher is forwarded to the whole tree
(SIGHUP and SIGQUIT as SIGTERM; SIGKILL after 30 s). Otherwise the child's exit code is
returned (128 + signal for a signalled child); a command that cannot be started exits 2.

``<run_dir>/gpu-assignment.json`` records indices, UUIDs, bus ids, command, the relevant
environment, git hashes and start/end times; ``<run_dir>/gpu-telemetry.jsonl`` gets one
line per 30 s for the assigned UUIDs only.

Standard library only; it never imports torch itself (the preflight is a child process).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Frozen 2026-10-04 from `nvidia-smi --query-gpu=index,uuid,pci.bus_id` on hdrfs-app-001.
ALLOWED: dict[int, tuple[str, str]] = {
    2: ("GPU-931d0911-fc78-1638-e3d7-1ba868cbd286", "00000000:45:00.0"),
    3: ("GPU-2f8008a1-9b67-11f6-987b-b393a672322c", "00000000:46:00.0"),
    4: ("GPU-fc5dde96-210d-0afa-ac74-7f88477d622b", "00000000:47:00.0"),
    5: ("GPU-1c9b612f-e0b5-fbbc-150f-8c2ef13453c9", "00000000:85:00.0"),
    6: ("GPU-804aea8b-5f62-423e-72c6-49e1ed15c4e4", "00000000:87:00.0"),
    7: ("GPU-a5ad49e5-0536-5229-ba8a-f8a902808f53", "00000000:C3:00.0"),
    8: ("GPU-e2e96741-aec9-e90b-5c46-d0d58be90a56", "00000000:C4:00.0"),
    9: ("GPU-c76642eb-64c1-b0ac-b051-d2efd47b32c4", "00000000:C5:00.0"),
}
# Reserved for other people. Never assignable, whatever the inventory says.
FORBIDDEN: dict[int, tuple[str, str]] = {
    0: ("GPU-84f5ca4d-68db-ae98-d056-40654d859dd9", "00000000:07:00.0"),
    1: ("GPU-d411d86a-6d1d-1967-55e7-9f9ec85d13f5", "00000000:08:00.0"),
}
FROZEN: dict[int, tuple[str, str]] = {**FORBIDDEN, **ALLOWED}

INHERITED_VARS = ("CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "NVIDIA_VISIBLE_DEVICES")
LOCK_PATTERNS = ("segmentary-exclusive-gpu-{index}.lock", "segmentary-gpu-{uuid}.lock")
IDLE_PASSES = 3
IDLE_MAX_MEMORY_MIB = 100
WATCHDOG_SECONDS = 10.0
KILL_GRACE_SECONDS = 30.0
TELEMETRY_EVERY = 3  # watchdog ticks, so 30 s
INSPECTION_FAILURES_ALLOWED = 2  # the third consecutive failure kills the run
EXIT_REFUSED = 2
EXIT_VIOLATION = 3
RECORDED_ENV_PREFIXES = ("CUDA_", "PAUL_", "OMP_", "NCCL_", "TORCH", "PYTHON", "MASTER_")
PR_SET_CHILD_SUBREAPER = 36
# Signals that stop the run, and what the tree receives for each.
FORWARDED_SIGNALS = {
    signal.SIGTERM: signal.SIGTERM,
    signal.SIGINT: signal.SIGINT,
    signal.SIGHUP: signal.SIGTERM,
    signal.SIGQUIT: signal.SIGTERM,
}

PREFLIGHT = """
import json, torch
count = torch.cuda.device_count()
uuids = [str(torch.cuda.get_device_properties(i).uuid) for i in range(count)]
print(json.dumps({"count": count, "uuids": uuids, "torch": torch.__version__}))
"""


class Refusal(Exception):
    """The launch would not be provably confined to the requested allowed GPUs."""


def _check_tables() -> None:
    assert not set(ALLOWED) & set(FORBIDDEN)
    assert not set(ALLOWED) & {0, 1}
    uuids = [uuid for uuid, _ in FROZEN.values()]
    assert len(set(uuids)) == len(uuids)


_check_tables()


def normalize_uuid(value: str) -> str:
    """nvidia-smi prints ``GPU-<hex>``; torch's device property omits the prefix."""
    text = str(value).strip().lower()
    for prefix in ("gpu-", "mig-"):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


ALLOWED_UUIDS = {normalize_uuid(uuid) for uuid, _ in ALLOWED.values()}
FORBIDDEN_UUIDS = {normalize_uuid(uuid) for uuid, _ in FORBIDDEN.values()}


@dataclass(frozen=True)
class Proc:
    ppid: int
    pgrp: int | None = None
    session: int | None = None
    state: str | None = None  # "Z" for a zombie (exited, holds nothing)


def run_nvidia_smi(args: list[str]) -> str:
    return subprocess.check_output(["nvidia-smi", *args], text=True, timeout=30)


def read_proc_table(proc_root: Path = Path("/proc")) -> dict[int, Proc]:
    """``pid -> (ppid, pgrp, session)`` from ``<proc_root>/<pid>/stat``."""
    table = {}
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            text = (entry / "stat").read_text()
        except OSError:
            continue  # exited while listing
        # "pid (comm) state ppid pgrp session ..."; comm may contain spaces and parens.
        fields = text[text.rfind(")") + 2 :].split()
        if len(fields) < 4:
            continue
        table[int(entry.name)] = Proc(int(fields[1]), int(fields[2]), int(fields[3]), fields[0])
    return table


def become_subreaper() -> bool:
    """Adopt orphaned descendants (Linux ``prctl``); refuse where that is impossible."""
    if not sys.platform.startswith("linux"):
        raise Refusal(f"PR_SET_CHILD_SUBREAPER needs Linux, this is {sys.platform}")
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        raise Refusal(f"prctl(PR_SET_CHILD_SUBREAPER) failed, errno {ctypes.get_errno()}")
    return True


@dataclass
class Host:
    """Everything that touches the machine, injectable for tests."""

    smi: Callable[[list[str]], str] = run_nvidia_smi
    process_table: Callable[[], dict[int, Proc]] = read_proc_table
    lock_dir: Path = Path("/tmp")
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    subreaper: Callable[[], bool] = become_subreaper
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    idle_pause_seconds: float = 1.0
    watchdog_seconds: float = WATCHDOG_SECONDS
    kill_grace_seconds: float = KILL_GRACE_SECONDS


def parse_gpus(text: str) -> tuple[int, ...]:
    """Distinct allowlisted indices, sorted; anything else is refused."""
    if not re.fullmatch(r"\d+(,\d+)*", text or ""):
        raise Refusal(f"--gpus must be a non-empty comma-separated list of indices, got {text!r}")
    values = [int(token) for token in text.split(",")]
    if len(set(values)) != len(values):
        raise Refusal(f"--gpus contains duplicates: {text!r}")
    forbidden = sorted(set(values) & set(FORBIDDEN))
    if forbidden:
        raise Refusal(f"GPU(s) {forbidden} are reserved for other people and are never used")
    outside = sorted(set(values) - set(ALLOWED))
    if outside:
        raise Refusal(f"GPU(s) {outside} are not in the allowlist {sorted(ALLOWED)}")
    return tuple(sorted(values))


def check_inherited(environ: Mapping[str, str]) -> None:
    present = [name for name in INHERITED_VARS if name in environ]
    if present:
        raise Refusal(
            f"Refusing inherited {', '.join(present)}; launch from a clean environment "
            "so only this launcher decides GPU visibility"
        )


def _rows(text: str) -> list[list[str]]:
    return [
        [item.strip() for item in line.split(",")] for line in text.splitlines() if line.strip()
    ]


def check_inventory(host: Host) -> None:
    """The live 10-GPU table must equal the frozen one, index by index."""
    try:
        text = host.smi(["--query-gpu=index,uuid,pci.bus_id", "--format=csv,noheader"])
    except (OSError, subprocess.SubprocessError) as error:
        raise Refusal(f"Cannot read the GPU inventory: {error}") from error
    live = {}
    for row in _rows(text):
        if len(row) != 3 or not row[0].isdigit():
            raise Refusal(f"Unexpected nvidia-smi inventory row: {row}")
        if int(row[0]) in live:
            raise Refusal(f"nvidia-smi reported index {row[0]} twice")
        live[int(row[0])] = (normalize_uuid(row[1]), row[2].upper())
    frozen = {i: (normalize_uuid(uuid), pci.upper()) for i, (uuid, pci) in FROZEN.items()}
    if live != frozen:
        diff = {
            i: {"frozen": frozen.get(i), "live": live.get(i)}
            for i in sorted(set(live) | set(frozen))
            if live.get(i) != frozen.get(i)
        }
        raise Refusal(f"Live GPU inventory differs from the frozen table: {diff}")


def acquire_locks(indices: tuple[int, ...], lock_dir: Path) -> list:
    handles: list = []
    try:
        for index in indices:
            for pattern in LOCK_PATTERNS:
                path = lock_dir / pattern.format(index=index, uuid=ALLOWED[index][0])
                handle = path.open("a")
                handles.append(handle)
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise Refusal(f"GPU {index} is locked by another launcher: {path}") from error
    except BaseException:
        for handle in handles:
            handle.close()
        raise
    return handles


def compute_apps(host: Host) -> list[tuple[str, int]]:
    """``(normalised gpu uuid, pid)`` for every compute process on the host."""
    text = host.smi(["--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader,nounits"])
    apps = []
    for row in _rows(text):
        if len(row) < 2 or not row[1].isdigit():
            raise RuntimeError(f"Unexpected nvidia-smi compute-apps row: {row}")
        apps.append((normalize_uuid(row[0]), int(row[1])))
    return apps


def check_idle(host: Host, indices: tuple[int, ...]) -> None:
    wanted = {normalize_uuid(ALLOWED[i][0]): i for i in indices}
    for attempt in range(IDLE_PASSES):
        try:
            text = host.smi(
                [
                    "--query-gpu=index,uuid,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ]
            )
            busy = {uuid for uuid, _ in compute_apps(host)}
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            raise Refusal(f"Cannot check that the GPUs are idle: {error}") from error
        seen = set()
        for row in _rows(text):
            uuid = normalize_uuid(row[1]) if len(row) == 4 else None
            if uuid not in wanted:
                continue
            seen.add(uuid)
            memory, util = row[2], row[3]
            if (
                uuid in busy
                or not memory.isdigit()
                or not util.isdigit()
                or int(memory) > IDLE_MAX_MEMORY_MIB
                or int(util) > 0
            ):
                raise Refusal(f"GPU {wanted[uuid]} is not idle: {row} (compute apps: {busy})")
        if seen != set(wanted):
            raise Refusal(f"nvidia-smi did not report GPU(s) {sorted(set(wanted) - seen)}")
        if attempt < IDLE_PASSES - 1:
            host.sleep(host.idle_pause_seconds)


def child_env(base: Mapping[str, str], indices: tuple[int, ...]) -> dict[str, str]:
    check_inherited(base)
    return {
        **base,
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "CUDA_VISIBLE_DEVICES": ",".join(ALLOWED[i][0] for i in sorted(indices)),
        "OMP_NUM_THREADS": "2",
    }


def preflight(python: str, env: Mapping[str, str], indices: tuple[int, ...]) -> dict[str, Any]:
    """In the child's environment, torch must see exactly the assigned devices."""
    try:
        done = subprocess.run(
            [python, "-c", PREFLIGHT],
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise Refusal(f"Preflight could not run {python}: {error}") from error
    if done.returncode != 0:
        raise Refusal(f"Preflight failed ({done.returncode}): {done.stderr.strip()[-2000:]}")
    try:
        result = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as error:
        raise Refusal(f"Preflight printed no result: {done.stdout!r}") from error
    assigned = {normalize_uuid(ALLOWED[i][0]) for i in indices}
    seen = [normalize_uuid(uuid) for uuid in result.get("uuids", [])]
    if result.get("count") != len(indices) or len(seen) != len(indices):
        raise Refusal(
            f"Preflight: torch sees {result.get('count')} devices, expected {len(indices)}"
        )
    if not set(seen) <= assigned or len(set(seen)) != len(seen):
        raise Refusal(
            f"Preflight: torch device UUIDs {seen} are not the assigned {sorted(assigned)}"
        )
    return result


def descendants(table: dict[int, Proc], root: int) -> set[int]:
    """``root`` and everything below it by parent pid."""
    children: dict[int, list[int]] = {}
    for pid, info in table.items():
        children.setdefault(info.ppid, []).append(pid)
    tree, pending = {root}, [root]
    while pending:
        for child in children.get(pending.pop(), []):
            if child not in tree:
                tree.add(child)
                pending.append(child)
    return tree


def process_tree(table: dict[int, Proc], root: int) -> set[int]:
    """``root``, its descendants, and every process still in its session or group."""
    tree = descendants(table, root)
    for pid, info in table.items():
        if root in (info.pgrp, info.session):
            tree |= descendants(table, pid)
    return tree


def run_tree(table: dict[int, Proc], child: int, launcher: int, adopted: bool) -> set[int]:
    """The child's tree plus, as subreaper, every orphan re-parented to the launcher.

    The launcher itself is never part of it. Its synchronous helpers (nvidia-smi, git)
    have exited before the tree is read.
    """
    tree = process_tree(table, child)
    if adopted:
        tree |= descendants(table, launcher)
    tree.discard(launcher)
    return tree


def foreign_contexts(
    apps: list[tuple[str, int]], tree: set[int], indices: tuple[int, ...]
) -> list[dict[str, Any]]:
    assigned = {normalize_uuid(ALLOWED[i][0]) for i in indices}
    return [
        {"pid": pid, "gpu_uuid": uuid, "forbidden": uuid in FORBIDDEN_UUIDS}
        for uuid, pid in apps
        if pid in tree and uuid not in assigned
    ]


def telemetry(host: Host, indices: tuple[int, ...]) -> list[dict[str, Any]]:
    text = host.smi(
        [
            "--query-gpu=index,uuid,memory.used,memory.total,utilization.gpu,"
            "temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ]
    )
    assigned = {normalize_uuid(ALLOWED[i][0]) for i in indices}
    keys = ("index", "uuid", "memory_used_mib", "memory_total_mib", "util_pct", "temp_c", "power_w")
    return [
        dict(zip(keys, row, strict=False))
        for row in _rows(text)
        if len(row) == 7 and normalize_uuid(row[1]) in assigned
    ]


def write_json(path: Path, value: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def git_head(path: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


class Run:
    """The launched child plus the bookkeeping for stopping it."""

    def __init__(self, host: Host, indices: tuple[int, ...], run_dir: Path) -> None:
        self.host, self.indices, self.run_dir = host, indices, run_dir
        self.proc: subprocess.Popen | None = None
        self.stop_signal: int | None = None
        self.stop_at: float | None = None
        self.killed = False
        self.last_tree: set[int] = set()
        self.adopted = False  # True once the launcher is the child subreaper
        self.pid = os.getpid()

    def on_signal(self, signum, _frame) -> None:
        if self.stop_signal is None:
            self.stop_signal, self.stop_at = signum, self.host.clock()
            if self.proc is not None:
                self.signal_tree(FORWARDED_SIGNALS.get(signum, signal.SIGTERM))

    def signal_tree(self, signum: int) -> None:
        assert self.proc is not None
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(self.proc.pid, signum)
        for pid in self.last_tree:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signum)

    def refresh_tree(self) -> set[int]:
        assert self.proc is not None
        table = self.host.process_table()
        self.last_tree = run_tree(table, self.proc.pid, self.pid, self.adopted)
        return self.last_tree

    def reap(self, table: dict[int, Proc]) -> None:
        """Collect exited adopted orphans (never the main child, which Popen owns)."""
        for pid, info in table.items():
            if info.ppid == self.pid and pid != getattr(self.proc, "pid", None):
                with contextlib.suppress(ChildProcessError, OSError):
                    os.waitpid(pid, os.WNOHANG)

    def terminate(self) -> None:
        """SIGTERM the whole tree, SIGKILL whatever is left after the grace period."""
        assert self.proc is not None
        with contextlib.suppress(Exception):
            self.refresh_tree()
        self.signal_tree(signal.SIGTERM)
        deadline = self.host.clock() + self.host.kill_grace_seconds
        while self.host.clock() < deadline:
            if self.proc.poll() is not None and not self.alive():
                return
            self.host.sleep(0.2)
        self.killed = True
        with contextlib.suppress(Exception):
            self.refresh_tree()
        self.signal_tree(signal.SIGKILL)
        self.proc.wait()

    def alive(self) -> bool:
        """Is any non-zombie process of the tree (adopted orphans included) still there?"""
        assert self.proc is not None
        try:
            table = self.host.process_table()
            if self.adopted:
                self.reap(table)
                table = self.host.process_table()
        except Exception:
            return True
        tree = run_tree(table, self.proc.pid, self.pid, self.adopted)
        return any(table[pid].state != "Z" for pid in tree if pid in table)


def run(args: argparse.Namespace, host: Host) -> int:
    indices = parse_gpus(args.gpus)
    if not args.command:
        raise Refusal("No command given after --")
    check_inherited(host.environ)
    check_inventory(host)
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    locks = acquire_locks(indices, host.lock_dir)
    try:
        check_idle(host, indices)
        env = child_env(host.environ, indices)
        evidence = preflight(args.python, env, indices)
        adopted = host.subreaper()
        return launch(args, host, indices, run_dir, env, evidence, locks, adopted)
    finally:
        for handle in locks:
            handle.close()


def launch(args, host, indices, run_dir, env, evidence, locks, adopted=False) -> int:
    assignment_path = run_dir / "gpu-assignment.json"
    if assignment_path.exists():
        stamp = int(assignment_path.stat().st_mtime)
        assignment_path.replace(run_dir / f"gpu-assignment.previous-{stamp}.json")
    here = Path(__file__).resolve()
    record: dict[str, Any] = {
        "schema_version": 1,
        "hostname": socket.gethostname(),
        "gpus": [{"index": i, "uuid": ALLOWED[i][0], "pci_bus_id": ALLOWED[i][1]} for i in indices],
        "forbidden_uuids": sorted(uuid for uuid, _ in FORBIDDEN.values()),
        "command": list(args.command),
        "cwd": os.getcwd(),
        "preflight_python": args.python,
        "preflight": evidence,
        "env": {k: v for k, v in sorted(env.items()) if k.startswith(RECORDED_ENV_PREFIXES)},
        "launcher": {
            "path": str(here),
            "sha256": hashlib.sha256(here.read_bytes()).hexdigest(),
            "git_head": git_head(here.parent),
        },
        "cwd_git_head": git_head(Path.cwd()),
        "child_subreaper": bool(adopted),
        "started_at": time.time(),
        "status": "running",
    }
    current = Run(host, indices, run_dir)
    current.adopted = bool(adopted)
    previous = {sig: signal.signal(sig, current.on_signal) for sig in FORWARDED_SIGNALS}
    returncode, violation = None, None
    try:
        try:
            current.proc = subprocess.Popen(
                list(args.command),
                env=env,
                start_new_session=True,
                pass_fds=[handle.fileno() for handle in locks],
            )
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            record.update({"status": "launch-failed", "error": repr(error)})
            write_json(assignment_path, record)
            raise Refusal(f"Cannot start {args.command[0]!r}: {error}") from error
        if current.stop_signal is not None:  # arrived while the child was being spawned
            current.signal_tree(current.stop_signal)
        record["pid"] = current.proc.pid
        write_json(assignment_path, record)
        failures, ticks = 0, 0
        next_check = host.clock() + host.watchdog_seconds
        while current.proc.poll() is None:
            now = host.clock()
            if current.stop_at is not None and now - current.stop_at > host.kill_grace_seconds:
                current.killed = True
                current.signal_tree(signal.SIGKILL)
                current.proc.wait()
                break
            if now >= next_check:
                next_check = now + host.watchdog_seconds
                ticks += 1
                try:
                    tree = current.refresh_tree()
                    foreign = foreign_contexts(compute_apps(host), tree, indices)
                    failures = 0
                except Exception as error:
                    failures += 1
                    foreign = []
                    if failures > INSPECTION_FAILURES_ALLOWED:
                        violation = {"kind": "inspection-failed", "error": repr(error)}
                if foreign:
                    violation = {"kind": "foreign-gpu-context", "contexts": foreign}
                if violation is not None:
                    violation["detected_at"] = time.time()
                    print(f"fork_gpu_run: VIOLATION {violation}", file=sys.stderr, flush=True)
                    current.terminate()
                    break
                if ticks % TELEMETRY_EVERY == 1:
                    with contextlib.suppress(Exception):
                        append_jsonl(
                            run_dir / "gpu-telemetry.jsonl",
                            {"t": time.time(), "gpus": telemetry(host, indices)},
                        )
            host.sleep(min(0.5, host.watchdog_seconds))
        returncode = current.proc.wait()
        # Ranks or workers that outlived the child would keep holding the GPUs.
        if violation is None and current.alive():
            with contextlib.suppress(Exception):
                current.refresh_tree()
            record["orphans_terminated"] = sorted(current.last_tree - {current.proc.pid})
            current.terminate()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    record.update(
        {
            "ended_at": time.time(),
            "child_returncode": returncode,
            "stop_signal": current.stop_signal,
            "sigkill_used": current.killed,
            "violation": violation,
        }
    )
    if violation is not None:
        record["status"] = "violation"
        write_json(assignment_path, record)
        write_json(run_dir / "gpu-violation.json", violation)
        return EXIT_VIOLATION
    code = returncode if returncode >= 0 else 128 - returncode
    record["status"] = "exited"
    record["exit_code"] = code
    write_json(assignment_path, record)
    return code


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--gpus", required=True, help=f"subset of {sorted(ALLOWED)}, e.g. 2,3")
    p.add_argument("--run-dir", required=True, help="gets gpu-assignment.json and telemetry")
    p.add_argument("--python", required=True, help="interpreter used for the torch preflight")
    p.add_argument("command", nargs=argparse.REMAINDER, help="-- <command ...>")
    return p


def main(argv: list[str] | None = None, host: Host | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    try:
        return run(args, host or Host())
    except Refusal as error:
        print(f"fork_gpu_run: REFUSED: {error}", file=sys.stderr, flush=True)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
