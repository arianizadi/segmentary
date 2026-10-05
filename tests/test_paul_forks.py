"""Paul-fork tooling: fail-closed GPU launcher, RAD adapter, RS19 split, scorer. No GPU used."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image
from scripts.paul_forks import (
    adapt_rad,
    fork_gpu_run,
    fork_queue,
    make_rs19_split,
    score_predictions,
)
from scripts.paul_forks.fork_gpu_run import ALLOWED, FORBIDDEN, Host, Proc

from segmentary.engine.metrics import ConfusionMatrix

PAUL_FORKS = Path(__file__).resolve().parents[1] / "scripts" / "paul_forks"
GPU0, GPU1 = FORBIDDEN[0][0], FORBIDDEN[1][0]


# --------------------------------------------------------------------------- launcher


class FakeSmi:
    """A ten-GPU HDRFS that answers the four nvidia-smi queries the launcher makes."""

    def __init__(self, apps=None):
        self.inventory = {i: list(v) for i, v in fork_gpu_run.FROZEN.items()}
        self.state = {i: [0, 0] for i in self.inventory}  # memory.used MiB, util %
        self.apps = apps or (lambda: [])
        self.calls: list[list[str]] = []

    def __call__(self, args):
        self.calls.append(args)
        query = args[0]
        if query.startswith("--query-gpu=index,uuid,pci.bus_id"):
            return "".join(f"{i}, {u}, {p}\n" for i, (u, p) in sorted(self.inventory.items()))
        if query == "--query-gpu=index,uuid,memory.used,utilization.gpu":
            return "".join(
                f"{i}, {self.inventory[i][0]}, {m}, {u}\n" for i, (m, u) in self.state.items()
            )
        if query.startswith("--query-gpu=index,uuid,memory.used,memory.total"):
            return "".join(
                f"{i}, {self.inventory[i][0]}, {m}, 46068, {u}, 30, 40.0\n"
                for i, (m, u) in self.state.items()
            )
        if query == "--query-compute-apps=gpu_uuid,pid":
            return "".join(f"{u}, {p}\n" for u, p in self.apps())
        raise AssertionError(f"unexpected nvidia-smi query {args}")


def ps_table():
    """Real process table via ps (works on macOS and Linux; /proc is tested separately)."""
    out = subprocess.check_output(["ps", "-A", "-o", "pid=,ppid=,pgid="], text=True)
    table = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            table[int(parts[0])] = Proc(int(parts[1]), int(parts[2]))
    return table


def fake_python(tmp_path: Path, body: str | None = None) -> str:
    """Stands in for the env's python in the preflight; reports what CUDA would see."""
    body = body or (
        "import json, os\n"
        "v = [u for u in os.environ['CUDA_VISIBLE_DEVICES'].split(',') if u]\n"
        "assert os.environ['CUDA_DEVICE_ORDER'] == 'PCI_BUS_ID'\n"
        "print(json.dumps({'count': len(v), 'uuids': [u[4:] for u in v]}))\n"
    )
    path = tmp_path / "fakepython"
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(0o755)
    return str(path)


GPU_VARS = ("CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "NVIDIA_VISIBLE_DEVICES")


def base_environ(home: Path) -> dict[str, str]:
    """The real environment minus GPU selection, so child interpreters still start.

    A bare PATH-only environment drops LD_LIBRARY_PATH, which CI's setup-python
    interpreter needs to load libpython.
    """
    env = {k: v for k, v in os.environ.items() if k not in GPU_VARS}
    env["HOME"] = str(home)
    return env


def make_host(tmp_path: Path, smi: FakeSmi | None = None, **overrides) -> Host:
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(exist_ok=True)
    values = {
        "smi": smi or FakeSmi(),
        "process_table": ps_table,
        "lock_dir": lock_dir,
        "environ": base_environ(tmp_path),
        "subreaper": lambda: False,  # tests run in-process; the real prctl is tested below
        "idle_pause_seconds": 0.0,
        "watchdog_seconds": 0.1,
        "kill_grace_seconds": 3.0,
    }
    values.update(overrides)
    return Host(**values)


def launch(tmp_path, host, gpus, command, python=None):
    run_dir = tmp_path / "run"
    argv = ["--gpus", gpus, "--run-dir", str(run_dir), "--python", python or fake_python(tmp_path)]
    return fork_gpu_run.main([*argv, "--", *command], host=host), run_dir


def marker_command(path: Path, code: int = 0) -> list[str]:
    script = (
        "import json, os, sys\n"
        f"open({str(path)!r}, 'w').write(json.dumps(dict(os.environ)))\n"
        f"sys.exit({code})\n"
    )
    return [sys.executable, "-c", script]


def test_frozen_tables_are_exactly_hdrfs_2_to_9_with_0_and_1_forbidden():
    assert sorted(ALLOWED) == list(range(2, 10))
    assert FORBIDDEN == {
        0: ("GPU-84f5ca4d-68db-ae98-d056-40654d859dd9", "00000000:07:00.0"),
        1: ("GPU-d411d86a-6d1d-1967-55e7-9f9ec85d13f5", "00000000:08:00.0"),
    }
    assert ALLOWED[2] == ("GPU-931d0911-fc78-1638-e3d7-1ba868cbd286", "00000000:45:00.0")
    assert ALLOWED[9] == ("GPU-c76642eb-64c1-b0ac-b051-d2efd47b32c4", "00000000:C5:00.0")
    options = {a.dest for a in fork_gpu_run.parser()._actions}
    assert options == {"help", "gpus", "run_dir", "python", "command"}  # no override flag


@pytest.mark.parametrize("gpus", ["0", "1", "0,2", "2,1", "", "2,2", "3,2,3", "10", "2,x", " 2"])
def test_refuses_forbidden_empty_duplicate_and_unlisted_gpus(tmp_path, gpus, capsys):
    host = make_host(tmp_path)
    code, run_dir = launch(tmp_path, host, gpus, marker_command(tmp_path / "ran"))
    assert code == fork_gpu_run.EXIT_REFUSED
    assert "REFUSED" in capsys.readouterr().err
    assert not (tmp_path / "ran").exists()
    assert host.smi.calls == []  # refused before touching the host
    assert not run_dir.exists()


@pytest.mark.parametrize(
    "inherited",
    [
        {"CUDA_VISIBLE_DEVICES": ""},
        {"CUDA_VISIBLE_DEVICES": "2"},
        {"CUDA_DEVICE_ORDER": "PCI_BUS_ID"},
        {"NVIDIA_VISIBLE_DEVICES": "all"},
    ],
)
def test_refuses_inherited_cuda_visibility(tmp_path, inherited):
    host = make_host(tmp_path)
    host.environ = {**host.environ, **inherited}
    code, _ = launch(tmp_path, host, "2", marker_command(tmp_path / "ran"))
    assert code == fork_gpu_run.EXIT_REFUSED
    assert not (tmp_path / "ran").exists()


@pytest.mark.parametrize(
    "edit",
    [
        lambda inv: inv[2].__setitem__(0, "GPU-00000000-0000-0000-0000-000000000000"),
        lambda inv: inv[3].__setitem__(1, "00000000:99:00.0"),
        lambda inv: inv[0].__setitem__(0, ALLOWED[2][0]),  # swapped cards
        lambda inv: inv.pop(9),
        lambda inv: inv.__setitem__(10, ["GPU-ffffffff-0000-0000-0000-000000000000", "x"]),
    ],
)
def test_refuses_when_live_uuid_or_pci_differs_from_frozen(tmp_path, edit):
    smi = FakeSmi()
    edit(smi.inventory)
    code, _ = launch(tmp_path, make_host(tmp_path, smi), "2,3", marker_command(tmp_path / "ran"))
    assert code == fork_gpu_run.EXIT_REFUSED
    assert not (tmp_path / "ran").exists()


@pytest.mark.parametrize("busy", ["memory", "util", "app"])
def test_refuses_busy_gpu(tmp_path, busy):
    smi = FakeSmi()
    if busy == "memory":
        smi.state[3] = [101, 0]
    elif busy == "util":
        smi.state[3] = [0, 1]
    else:
        smi.apps = lambda: [(ALLOWED[3][0], 4242)]
    code, _ = launch(tmp_path, make_host(tmp_path, smi), "2,3", marker_command(tmp_path / "ran"))
    assert code == fork_gpu_run.EXIT_REFUSED
    assert not (tmp_path / "ran").exists()


def test_refuses_gpu_locked_by_another_launcher(tmp_path):
    import fcntl

    host = make_host(tmp_path)
    held = (host.lock_dir / "segmentary-exclusive-gpu-4.lock").open("a")
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        code, _ = launch(tmp_path, host, "4", marker_command(tmp_path / "ran"))
    finally:
        held.close()
    assert code == fork_gpu_run.EXIT_REFUSED
    held = (host.lock_dir / f"segmentary-gpu-{ALLOWED[5][0]}.lock").open("a")
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        code, _ = launch(tmp_path, host, "5", marker_command(tmp_path / "ran"))
    finally:
        held.close()
    assert code == fork_gpu_run.EXIT_REFUSED
    assert not (tmp_path / "ran").exists()


def test_child_env_is_exact():
    env = fork_gpu_run.child_env({"PATH": "/bin", "HOME": "/h"}, (3, 2))
    assert env == {
        "PATH": "/bin",
        "HOME": "/h",
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "CUDA_VISIBLE_DEVICES": f"{ALLOWED[2][0]},{ALLOWED[3][0]}",
        "OMP_NUM_THREADS": "2",
    }
    with pytest.raises(fork_gpu_run.Refusal):
        fork_gpu_run.child_env({"CUDA_VISIBLE_DEVICES": "0"}, (2,))


def test_launch_passes_exact_env_records_assignment_and_propagates_exit_code(tmp_path):
    smi = FakeSmi()
    smi.state[0] = [30000, 90]  # someone else busy on GPU 0 does not block GPUs 2-3
    smi.apps = lambda: [(GPU0, 999999)]
    host = make_host(tmp_path, smi)
    command = [
        sys.executable,
        "-c",
        "import json,os,sys,time; time.sleep(0.4); "
        f"open({str(tmp_path / 'env.json')!r},'w').write(json.dumps(dict(os.environ))); "
        "sys.exit(7)",
    ]
    code, run_dir = launch(tmp_path, host, "3,2", command)
    assert code == 7
    env = json.loads((tmp_path / "env.json").read_text())
    assert env["CUDA_VISIBLE_DEVICES"] == f"{ALLOWED[2][0]},{ALLOWED[3][0]}"
    assert env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
    assert env["OMP_NUM_THREADS"] == "2"
    # The child gets the launcher's environment plus exactly the three GPU/thread keys.
    expected = set(host.environ) | {"CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "OMP_NUM_THREADS"}
    assert set(env) - {"__CF_USER_TEXT_ENCODING", "LC_CTYPE"} == expected - {
        "__CF_USER_TEXT_ENCODING",
        "LC_CTYPE",
    }
    assert {
        k: env[k] for k in host.environ if k not in ("__CF_USER_TEXT_ENCODING", "LC_CTYPE")
    } == {k: v for k, v in host.environ.items() if k not in ("__CF_USER_TEXT_ENCODING", "LC_CTYPE")}
    record = json.loads((run_dir / "gpu-assignment.json").read_text())
    assert record["gpus"] == [
        {"index": 2, "uuid": ALLOWED[2][0], "pci_bus_id": ALLOWED[2][1]},
        {"index": 3, "uuid": ALLOWED[3][0], "pci_bus_id": ALLOWED[3][1]},
    ]
    assert record["status"] == "exited" and record["exit_code"] == 7
    assert record["violation"] is None and record["command"] == command
    assert record["preflight"]["count"] == 2
    lines = [json.loads(x) for x in (run_dir / "gpu-telemetry.jsonl").read_text().splitlines()]
    assert lines
    assert {g["uuid"] for line in lines for g in line["gpus"]} == {ALLOWED[2][0], ALLOWED[3][0]}


@pytest.mark.parametrize(
    "report",
    [
        "{'count': 2, 'uuids': [v[0][4:], v[1][4:]]}",  # more devices than assigned
        f"{{'count': 1, 'uuids': [{GPU0[4:]!r}]}}",  # a forbidden device
        "{'count': 1, 'uuids': ['931d0911-fc78-1638-e3d7-1ba868cbd28X']}",
    ],
)
def test_preflight_refuses_unexpected_torch_devices(tmp_path, report):
    body = (
        "import json, os\n"
        "v = os.environ['CUDA_VISIBLE_DEVICES'].split(',') + ['GPU-extra-extra']\n"
        f"print(json.dumps({report}))\n"
    )
    host = make_host(tmp_path)
    code, _ = launch(
        tmp_path, host, "2", marker_command(tmp_path / "ran"), fake_python(tmp_path, body)
    )
    assert code == fork_gpu_run.EXIT_REFUSED
    assert not (tmp_path / "ran").exists()


def test_watchdog_kills_tree_when_a_descendant_lands_on_a_foreign_gpu(tmp_path):
    pid_file = tmp_path / "grandchild.pid"

    def apps():
        if pid_file.exists() and pid_file.read_text().strip():
            return [(ALLOWED[2][0], os.getpid()), (GPU1, int(pid_file.read_text()))]
        return []

    smi = FakeSmi(apps)
    # The child spawns a grandchild (like a DDP rank or a dataloader worker) and waits.
    child = (
        "import subprocess, sys, time\n"
        f"g = subprocess.Popen([{sys.executable!r}, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(g.pid))\n"
        "time.sleep(60)\n"
    )
    started = time.monotonic()
    code, run_dir = launch(tmp_path, make_host(tmp_path, smi), "2", [sys.executable, "-c", child])
    assert code == fork_gpu_run.EXIT_VIOLATION
    assert time.monotonic() - started < 20
    grandchild = int(pid_file.read_text())
    violation = json.loads((run_dir / "gpu-violation.json").read_text())
    assert violation["kind"] == "foreign-gpu-context"
    assert violation["contexts"] == [
        {"pid": grandchild, "gpu_uuid": GPU1[4:].lower(), "forbidden": True}
    ]
    assert json.loads((run_dir / "gpu-assignment.json").read_text())["status"] == "violation"
    deadline = time.monotonic() + 5
    while grandchild in ps_table() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert grandchild not in ps_table()


def test_watchdog_ignores_unrelated_processes_on_other_gpus(tmp_path):
    smi = FakeSmi(lambda: [(GPU0, 1), (ALLOWED[5][0], 2)])  # other users' processes
    command = [sys.executable, "-c", "import time; time.sleep(0.5)"]
    code, _ = launch(tmp_path, make_host(tmp_path, smi), "2", command)
    assert code == 0


def test_repeated_inspection_failure_kills_the_run(tmp_path):
    host = make_host(tmp_path, kill_grace_seconds=1.0)
    host.process_table = lambda: (_ for _ in ()).throw(OSError("no /proc"))
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    code, run_dir = launch(tmp_path, host, "2", command)
    assert code == fork_gpu_run.EXIT_VIOLATION
    assert json.loads((run_dir / "gpu-violation.json").read_text())["kind"] == "inspection-failed"


def test_sigterm_to_launcher_is_forwarded_to_child_group(tmp_path):
    marker = tmp_path / "got-term"
    child = (
        "import os, signal, sys, time\n"
        "def stop(*_):\n"
        f"    open({str(marker)!r}, 'w').write('term'); sys.exit(5)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "os.kill(os.getppid(), signal.SIGTERM)\n"
        "time.sleep(30)\n"
    )
    before = signal.getsignal(signal.SIGTERM)
    code, run_dir = launch(tmp_path, make_host(tmp_path), "2", [sys.executable, "-c", child])
    assert signal.getsignal(signal.SIGTERM) == before
    assert marker.read_text() == "term"
    assert code == 5
    assert json.loads((run_dir / "gpu-assignment.json").read_text())["stop_signal"] == 15


def test_sighup_to_launcher_terminates_the_child_instead_of_orphaning_it(tmp_path):
    marker = tmp_path / "got-term"
    child = (
        "import os, signal, sys, time\n"
        "def stop(*_):\n"
        f"    open({str(marker)!r}, 'w').write('term'); sys.exit(6)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "os.kill(os.getppid(), signal.SIGHUP)\n"
        "time.sleep(30)\n"
    )
    before = signal.getsignal(signal.SIGHUP)
    code, run_dir = launch(tmp_path, make_host(tmp_path), "2", [sys.executable, "-c", child])
    assert signal.getsignal(signal.SIGHUP) == before
    assert marker.read_text() == "term"  # forwarded as SIGTERM
    assert code == 6
    record = json.loads((run_dir / "gpu-assignment.json").read_text())
    assert record["stop_signal"] == signal.SIGHUP and record["status"] == "exited"
    assert set(fork_gpu_run.FORWARDED_SIGNALS) >= {signal.SIGHUP, signal.SIGQUIT}


def test_command_that_cannot_start_is_refused_not_a_traceback(tmp_path, capsys):
    code, run_dir = launch(tmp_path, make_host(tmp_path), "2", [str(tmp_path / "no-such-binary")])
    assert code == fork_gpu_run.EXIT_REFUSED
    assert "Cannot start" in capsys.readouterr().err
    assert json.loads((run_dir / "gpu-assignment.json").read_text())["status"] == "launch-failed"


def test_run_tree_keeps_orphans_adopted_by_the_subreaper():
    launcher, child = 50, 100
    table = {
        launcher: Proc(1, 50, 50),
        child: Proc(launcher, 100, 100),
        101: Proc(child, 100, 100),  # torchrun agent
        # workers in their own sessions whose agent died: re-parented to the launcher
        102: Proc(launcher, 102, 102),
        103: Proc(102, 102, 102),  # dataloader worker of an orphaned rank
        104: Proc(launcher, 104, 104, "Z"),
        200: Proc(1, 200, 200),
    }
    assert fork_gpu_run.run_tree(table, child, launcher, adopted=True) == {
        100,
        101,
        102,
        103,
        104,
    }
    assert fork_gpu_run.run_tree(table, child, launcher, adopted=False) == {100, 101}


def test_subreaper_is_refused_off_linux(monkeypatch):
    monkeypatch.setattr(fork_gpu_run.sys, "platform", "darwin")
    with pytest.raises(fork_gpu_run.Refusal, match="Linux"):
        fork_gpu_run.become_subreaper()
    assert Host().subreaper is fork_gpu_run.become_subreaper


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="prctl subreaper is Linux only")
def test_orphan_in_its_own_session_is_terminated_before_locks_are_released(tmp_path):
    """End to end, in a separate process so pytest itself never becomes a subreaper."""
    pid_file = tmp_path / "orphan.pid"
    driver = tmp_path / "driver.py"
    orphan = "import time; time.sleep(120)"
    child = (
        "import subprocess, sys\n"
        f"g = subprocess.Popen([sys.executable, '-c', {orphan!r}], start_new_session=True)\n"
        f"open({str(pid_file)!r}, 'w').write(str(g.pid))\n"
    )
    driver.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {str(PAUL_FORKS.parents[1])!r})\n"  # repo root: `scripts` package
        f"sys.path.insert(0, {str(PAUL_FORKS)!r})\n"
        "import fork_gpu_run as f\n"
        f"sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
        "from test_paul_forks import FakeSmi, ps_table\n"
        "host = f.Host(smi=FakeSmi(), process_table=f.read_proc_table, "
        f"lock_dir=__import__('pathlib').Path({str(tmp_path)!r}), "
        "environ={k: v for k, v in __import__('os').environ.items() "
        "if k not in ('CUDA_VISIBLE_DEVICES', 'CUDA_DEVICE_ORDER', 'NVIDIA_VISIBLE_DEVICES')}, "
        "idle_pause_seconds=0.0, watchdog_seconds=0.1, "
        "kill_grace_seconds=3.0)\n"
        f"py = {fake_python(tmp_path)!r}\n"
        f"sys.exit(f.main(['--gpus', '2', '--run-dir', {str(tmp_path / 'run')!r}, '--python', py,"
        f" '--', sys.executable, '-c', {child!r}], host=host))\n"
    )
    done = subprocess.run([sys.executable, str(driver)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    record = json.loads((tmp_path / "run" / "gpu-assignment.json").read_text())
    orphan_pid = int(pid_file.read_text())
    assert record["child_subreaper"] is True
    assert orphan_pid in record["orphans_terminated"]
    assert not Path(f"/proc/{orphan_pid}").exists()


def test_proc_table_and_tree_include_descendants_and_session_members(tmp_path):
    def stat(pid, comm, ppid, pgrp, session):
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "stat").write_text(
            f"{pid} ({comm}) S {ppid} {pgrp} {session} 0 -1 4194560 0 0\n"
        )

    stat(1, "init", 0, 1, 1)
    stat(100, "python", 1, 100, 100)  # the launched child (session leader)
    stat(101, "pt_main (x) y", 100, 100, 100)  # rank with spaces and parens in comm
    stat(102, "worker", 101, 100, 100)  # dataloader worker
    stat(103, "orphan", 1, 103, 100)  # reparented to init, still in the session
    stat(200, "other", 1, 200, 200)
    (tmp_path / "self").mkdir()
    table = fork_gpu_run.read_proc_table(tmp_path)
    assert table[101] == Proc(100, 100, 100, "S")
    assert fork_gpu_run.process_tree(table, 100) == {100, 101, 102, 103}
    apps = [("x", 102), (fork_gpu_run.normalize_uuid(ALLOWED[2][0]), 101), ("y", 200)]
    assert fork_gpu_run.foreign_contexts(apps, {100, 101, 102}, (2,)) == [
        {"pid": 102, "gpu_uuid": "x", "forbidden": False}
    ]


# --------------------------------------------------------------------------- RAD arm

CLASS_NAMES = [
    "person",
    "truck",
    "rail-track",
    "vegetation-overgrowth",
    "car",
    "on-rails",
    "traffic-sign",
    "road",
    "sidewalk",
    "construction",
    "tram-track",
    "pole",
    "traffic-light",
    "mud-pumping",
    "fence",
    "terrain",
    "sky",
    "rail-embedded",
    "rail-raised",
    "trackbed",
    "standing-water",
]
H, W = 6, 8


def mask_for(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mask = rng.integers(0, 21, size=(H, W)).astype(np.uint8)
    mask[0, :3] = 255
    mask[1, 1] = 13
    return mask


ARM_ROWS = [
    ("train", "g-a", "0001", ".png"),
    ("train", "g-a", "0002", ".jpg"),
    ("train", "g-b", "0003", ".png"),
    ("val", "g-c", "0004", ".png"),
    ("val", "g-c", "0005", ".jpg"),
    ("test", "g-d", "0006", ".png"),
]


def make_arm(root: Path, arm="fixed-grouped", rows=ARM_ROWS, grouped=True, masks=None) -> Path:
    arm_root = root / f"rad_9_24_2026-{arm}"
    samples = []
    for n, (split, group, stem, ext) in enumerate(rows):
        key = f"{group}/{stem}"
        image = arm_root / "images" / split / group / f"{stem}{ext}"
        mask_path = arm_root / "masks" / split / group / f"{stem}.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.full((H, W, 3), n * 20, np.uint8)).save(image)
        mask = (masks or {}).get(key, mask_for(n))
        Image.fromarray(mask).save(mask_path)
        counts = np.bincount(mask.ravel(), minlength=256)
        samples.append(
            {
                "key": key,
                "split": split,
                "group": group,
                "stem": stem,
                "image_extension": ext,
                "width": W,
                "height": H,
                "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "mask_sha256": hashlib.sha256(mask.tobytes()).hexdigest(),
                "class_pixels": {str(i): int(c) for i, c in enumerate(counts) if c},
            }
        )
    splits = {s: sorted(r["key"] for r in samples if r["split"] == s) for s in adapt_rad.SPLITS}
    splits["_split_method"] = "grouped" if grouped else "stratified"
    if grouped:
        splits["groups"] = {r["key"]: r["group"] for r in samples}
    (arm_root / "audit").mkdir(parents=True, exist_ok=True)
    (arm_root / "splits.json").write_text(json.dumps(splits))
    (arm_root / "audit/samples.json").write_text(json.dumps(samples))
    classes = [{"id": i, "name": n, "color": [i, i, i]} for i, n in enumerate(CLASS_NAMES)]
    (arm_root / "classes.json").write_text(json.dumps({"classes": classes, "ignore_index": 255}))
    return arm_root


def test_adapt_rad_builds_fork_layout_with_png_names_and_exact_support(tmp_path):
    arm = make_arm(tmp_path)
    out = tmp_path / "adapter"
    adapt_rad.main([str(arm), str(out), "--expect-total", "6"])
    assert sorted(p.name for p in out.iterdir()) == sorted(
        [
            "classes.json",
            "manifest.json",
            "validation-support.json",
            "test-support.json",
            *[f"{p}_{k}" for p in ("trainVal", "val", "test") for k in ("images", "masks")],
        ]
    )
    assert sorted(p.name for p in (out / "trainVal_images").iterdir()) == [
        "g-a__0001.png",
        "g-a__0002.png",
        "g-b__0003.png",
    ]
    jpg_link = out / "trainVal_images" / "g-a__0002.png"
    assert jpg_link.is_symlink() and jpg_link.resolve().suffix == ".jpg"
    assert Image.open(jpg_link).format == "JPEG"
    assert (out / "val_masks" / "g-c__0005.png").resolve() == (
        arm / "masks/val/g-c/0005.png"
    ).resolve()
    labels = json.loads((out / "classes.json").read_text())["labels"]
    assert [c["name"] for c in labels] == CLASS_NAMES and labels[13]["color"] == [13, 13, 13]
    support = json.loads((out / "validation-support.json").read_text())
    expected = sum(np.bincount(mask_for(n).ravel(), minlength=256)[:21] for n in (3, 4))
    assert support["images"] == 2 and support["class_pixel_counts"] == expected.tolist()
    test_support = json.loads((out / "test-support.json").read_text())
    assert (
        test_support["class_pixel_counts"]
        == np.bincount(mask_for(5).ravel(), minlength=256)[:21].tolist()
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["sizes"] == {"train": 3, "val": 2, "test": 1}
    assert {e["source_extension"] for e in manifest["entries"]} == {".png", ".jpg"}
    assert any("trainVal_ holds the train split only" in d for d in manifest["deviations"])
    assert not (tmp_path / "adapter.partial").exists()


def test_adapt_rad_refuses_existing_output(tmp_path):
    arm = make_arm(tmp_path)
    (tmp_path / "adapter").mkdir()
    with pytest.raises(SystemExit, match="output exists"):
        adapt_rad.adapt(arm, tmp_path / "adapter", 6)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("total", "expected 7"),
        ("group-crosses", "groups span splits"),
        ("dup-key", "is in both"),
        ("bad-mask", "outside"),
        ("mud-renamed", "mud-pumping"),
        ("image-changed", "image bytes"),
    ],
)
def test_adapt_rad_fails_closed(tmp_path, change, message):
    rows = list(ARM_ROWS)
    masks = None
    if change == "group-crosses":
        rows[5] = ("test", "g-c", "0006", ".png")  # g-c is also in val
    if change == "bad-mask":
        bad = mask_for(0)
        bad[2, 2] = 21
        masks = {"g-a/0001": bad}
    arm = make_arm(tmp_path, rows=rows, masks=masks)
    total = 6
    if change == "total":
        total = 7
    if change == "dup-key":
        splits = json.loads((arm / "splits.json").read_text())
        splits["test"].append("g-c/0004")
        (arm / "splits.json").write_text(json.dumps(splits))
    if change == "mud-renamed":
        classes = json.loads((arm / "classes.json").read_text())
        classes["classes"][13]["name"] = "mud"
        (arm / "classes.json").write_text(json.dumps(classes))
    if change == "image-changed":
        Image.fromarray(np.ones((H, W, 3), np.uint8)).save(arm / "images/val/g-c/0004.png")
    with pytest.raises(SystemExit, match=message):
        adapt_rad.adapt(arm, tmp_path / "adapter", total)
    assert not (tmp_path / "adapter").exists()
    assert not (tmp_path / "adapter.partial").exists()


def test_adapt_rad_allows_groups_across_splits_for_stratified_arms(tmp_path):
    rows = list(ARM_ROWS)
    rows[5] = ("test", "g-c", "0006", ".png")
    arm = make_arm(tmp_path, arm="fixed-stratified", rows=rows, grouped=False)
    adapt_rad.adapt(arm, tmp_path / "adapter", 6)
    assert (tmp_path / "adapter" / "test_images" / "g-c__0006.png").exists()


# --------------------------------------------------------------------------- RS19 split


def test_tracked_paul_rs19_split_files_are_pinned_and_disjoint():
    expected = {
        "train_split.txt": (
            "01a51754dfee8b6d46a83ad4a1e05f031974bd8772f1d4b2865b8ba9ebc9f436",
            6800,
        ),
        "val_split.txt": ("0cb50dc131e36a1065867af4ecdcebcf988aaff6b9924af686706349035840d4", 850),
        "test_split.txt": ("e458ba6cdfd44cce3d30f00b81233b9c4d1a7facfda752619957bdba9f8e09a7", 850),
    }
    readme = (PAUL_FORKS / "README.md").read_text()
    ids = []
    for name, (sha, count) in expected.items():
        path = PAUL_FORKS / "rs19_split" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
        assert sha in readme
        ids += make_rs19_split.read_split(path)
        assert len(make_rs19_split.read_split(path)) == count
    assert len(set(ids)) == 8500


def make_rs19(root: Path, ids: list[str], bad_mask: str | None = None) -> Path:
    (root / "jpgs/rs19_val").mkdir(parents=True)
    (root / "uint8/rs19_val").mkdir(parents=True)
    (root / "rs19-config.json").write_text(json.dumps({"labels": []}))
    for n, i in enumerate(ids):
        Image.fromarray(np.full((H, W, 3), n, np.uint8)).save(root / f"jpgs/rs19_val/{i}.jpg")
        mask = np.full((H, W), n % 19, np.uint8)
        mask[0, 0] = 255
        if i == bad_mask:
            mask[1, 1] = 19
        Image.fromarray(mask).save(root / f"uint8/rs19_val/{i}.png")
    return root


def write_split(directory: Path, train, val, test) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, ids in (("train", train), ("val", val), ("test", test)):
        (directory / f"{name}_split.txt").write_text("\n".join(ids) + "\n")
    return directory


def test_make_rs19_split_builds_both_loaders_layouts(tmp_path):
    ids = [f"rs{n:05d}" for n in range(7)]
    rs19 = make_rs19(tmp_path / "rs19", ids)
    split = write_split(tmp_path / "split", ids[:4], ids[4:6], ids[6:])
    out = tmp_path / "railsem19-paul-split"
    make_rs19_split.main(
        [
            "--rs19",
            str(rs19),
            "--split-dir",
            str(split),
            "--out",
            str(out),
            "--expect-counts",
            "4,2,1",
        ]
    )

    def listing(name):
        return sorted(p.name for p in (out / name).iterdir())

    assert listing("trainVal_images") == [f"{i}.jpg" for i in ids[:6]]
    assert listing("trainVal_masks") == [f"{i}.png" for i in ids[:6]]
    assert listing("train_images") == [f"{i}.jpg" for i in ids[:4]]
    assert listing("val_images") == [f"{i}.jpg" for i in ids[4:6]]
    assert listing("test_masks") == [f"{i}.png" for i in ids[6:]]
    assert (out / "test_images" / "rs00006.jpg").resolve() == (
        rs19 / "jpgs/rs19_val/rs00006.jpg"
    ).resolve()
    assert (out / "rs19-config.json").resolve() == (rs19 / "rs19-config.json").resolve()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["counts"] == {"trainVal": 6, "train": 4, "val": 2, "test": 1}
    assert manifest["masks_checked"] is True
    assert set(manifest["split_files"]) == {"train", "val", "test"}


@pytest.mark.parametrize("problem", ["overlap", "missing", "bad-mask", "count", "malformed"])
def test_make_rs19_split_fails_closed(tmp_path, problem):
    ids = [f"rs{n:05d}" for n in range(7)]
    rs19 = make_rs19(tmp_path / "rs19", ids, bad_mask="rs00002" if problem == "bad-mask" else None)
    train, val, test = ids[:4], ids[4:6], ids[6:]
    counts = "4,2,1"
    if problem == "overlap":
        test = [ids[0]]
    if problem == "missing":
        (rs19 / "uint8/rs19_val/rs00005.png").unlink()
    if problem == "count":
        counts = "4,2,2"
    if problem == "malformed":
        test = ["rs6"]
    split = write_split(tmp_path / "split", train, val, test)
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        make_rs19_split.build(
            rs19,
            split,
            out,
            dict(zip(("train", "val", "test"), map(int, counts.split(",")), strict=True)),
            True,
        )
    assert not out.exists()


# --------------------------------------------------------------------------- scorer


def provenance(label="paper-hrnet__rs19-paul__arm-paul", **edits) -> dict:
    hrnet = label.startswith("paper-hrnet")
    base = label.split("__arm-", 1)[0]
    recipe = label.split("__recipe-", 1)[1] if "__recipe-" in label else "paul-shared-20260923"
    record = {
        "label": label,
        "owner_of_each_checkpoint_in_chain": dict(score_predictions.CHAINS[base])
        if "__arm-" in label and base in score_predictions.CHAINS
        else {},
        "checkpoints": {
            "map_city": {
                "path": "/x/map_city.pth",
                "sha256": score_predictions.PINNED[
                    ("paper-hrnet" if hrnet else "paper-sfnet", "map_city")
                ],
            },
            "rs19": {
                "path": "/x/rs19.pth",
                "sha256": score_predictions.PINNED[("paper-hrnet", "rs19-paul")]
                if "rs19-paul" in label and hrnet
                else "a" * 64,
            },
            "rad": {"path": "/x/best_mud_epoch_3.pth", "sha256": "b" * 64},
        },
        "fork": {"name": "hrnet", "git_commit": "5e619e6", "patches": []},
        "recipe_args": ["--lr", "1e-4"],
        "deviations": [],
        "gpu_assignment": {"indices": [2, 3], "uuids": [ALLOWED[2][0], ALLOWED[3][0]]},
        "extra": {"recipe_variant": recipe},
    }
    if base.endswith("__mapcity-direct"):
        del record["checkpoints"]["rs19"]
    record.update(edits)
    return record


def write_preds(arm: Path, split: str, out: Path, seed: int = 7) -> dict[str, np.ndarray]:
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    preds = {}
    for key in json.loads((arm / "splits.json").read_text())[split]:
        pred = rng.integers(0, 21, size=(H, W)).astype(np.uint8)
        pred[1, 1] = 13
        Image.fromarray(pred).save(out / (key.replace("/", "__") + ".png"))
        preds[key] = pred
    return preds


def sha_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def make_scored_run(tmp_path, arm, split="val", label="paper-hrnet__rs19-paul__arm-paul"):
    """A finished RAD run plus one P4 dump, laid out exactly as the recipes write them."""
    adapter = tmp_path / "adapter"
    if not adapter.exists():
        adapt_rad.adapt(arm, adapter, 6)
    run = tmp_path / "run"
    dump_dir = run / "dumps" / f"{split}-single-best_mud_epoch_3"
    pred = dump_dir / "pred"
    preds = write_preds(arm, split, pred)
    ckpt = run / "train" / "best_mud_epoch_3.pth"
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    ckpt.write_bytes(b"weights")
    data = {
        "root": str(adapter),
        "resolved": str(adapter.resolve()),
        "sha256": {"manifest.json": sha_of(adapter / "manifest.json")},
    }
    training = provenance(label, stage="rad", data=data, dry_run=False, probe_epochs=None)
    training["checkpoints"]["rad"] = {"role": "this-run", "path": None, "sha256": None}
    training_path = write_json(run / "provenance.json", training)
    write_json(run / "gpu-assignment.json", {"status": "exited", "exit_code": 0})
    dump = provenance(
        label,
        stage="dump",
        data=data,
        dry_run=False,
        probe_epochs=None,
        pins_override=None,
        command=["python", "-m", "torch.distributed.run", "train.py", "--dump_preds", str(pred)],
        dump={
            "training_provenance": str(training_path),
            "training_provenance_sha256": sha_of(training_path),
        },
    )
    dump["checkpoints"]["rad"] = {
        "role": "dumped",
        "path": str(ckpt),
        "resolved_path": str(ckpt.resolve()),
        "sha256": sha_of(ckpt),
    }
    prov = write_json(dump_dir / "dump-provenance.json", dump)
    write_json(dump_dir / "gpu-assignment.json", {"status": "exited", "exit_code": 0})
    names = sorted(key.replace("/", "__") for key in preds)
    write_json(
        Path(str(pred) + ".manifest.json"),
        {
            "split": split,
            "count": len(names),
            "images": names,
            "snapshot": str(ckpt),
            "snapshot_sha256": sha_of(ckpt),
            "n_scales": [1.0],
            "single_scale_whole_image": True,
        },
    )
    write_json(
        dump_dir / "log" / "init-coverage.json",
        {"status": "ok", "skipped_tensors": 0, "source_sha256": sha_of(ckpt)},
    )
    return {"pred": pred, "prov": prov, "preds": preds, "run": run, "dump": dump_dir}


def test_score_predictions_equals_segmentary_metric_code(tmp_path):
    arm = make_arm(tmp_path, arm="paul", grouped=False)
    made = make_scored_run(tmp_path, arm)
    preds = made["preds"]
    out = tmp_path / "results.json"
    score_predictions.main(
        [
            "--pred-dir",
            str(made["pred"]),
            "--arm-root",
            str(arm),
            "--split",
            "val",
            "--provenance",
            str(made["prov"]),
            "--out",
            str(out),
        ]
    )
    result = json.loads(out.read_text())

    reference = ConfusionMatrix(21, 255, device="cpu")
    for key, pred in preds.items():
        target = np.array(Image.open(arm / "masks" / "val" / f"{key}.png"))
        reference.update(torch.from_numpy(pred.astype(np.int64)), torch.from_numpy(target))
    expected = reference.compute().as_dict(CLASS_NAMES)
    assert result["miou"] == pytest.approx(expected["miou"])
    assert result["metrics"]["per_class_iou"] == pytest.approx(expected["per_class_iou"])
    assert result["metrics"]["confusion"] == reference.mat.tolist()
    mat = reference.mat.numpy()
    tp, fp, fn = mat[13, 13], mat[:, 13].sum() - mat[13, 13], mat[13].sum() - mat[13, 13]
    assert result["mud"]["iou"] == pytest.approx(tp / (tp + fp + fn))
    assert result["mud"]["precision"] == pytest.approx(tp / (tp + fp))
    assert result["mud"]["recall"] == pytest.approx(tp / (tp + fn))
    present = [v for n, v in expected["per_class_iou"].items() if expected["support"][n] > 0]
    assert result["fixed_gt_class_miou"] == pytest.approx(sum(present) / len(present))
    assert result["label"] == "paper-hrnet__rs19-paul__arm-paul"
    assert result["provenance"]["checkpoints"]["rad"]["path"].endswith("best_mud_epoch_3.pth")
    assert result["images"] == 2 and len(result["per_image"]) == 2
    assert result["inference"] == "whole-image single-scale"
    assert any(k.endswith("validation-support.json") for k in result["support_check"])
    code = result["metric_code"]
    assert code["repo"] == str(PAUL_FORKS.parents[1].resolve())
    assert set(code["sha256"]) == set(score_predictions.METRIC_FILES)
    assert result["dump"]["training_provenance_sha256"] == sha_of(made["run"] / "provenance.json")

    # Per-image confusion beside --out, in the campaign's per-image-confusion.json.gz format.
    confusion = tmp_path / "results-per-image-confusion.json.gz"
    assert score_predictions.per_image_confusion_path(out) == confusion
    assert result["per_image_confusion"]["path"] == str(confusion.resolve())
    assert result["per_image_confusion"]["sha256"] == sha_of(confusion)
    assert confusion.read_bytes()[4:8] == b"\0\0\0\0"  # gzip mtime=0, reproducible bytes
    matrices = json.loads(gzip.decompress(confusion.read_bytes()))
    assert sorted(matrices) == sorted(preds)
    for key, pred in preds.items():
        target = np.array(Image.open(arm / "masks" / "val" / f"{key}.png"))
        one = ConfusionMatrix(21, 255, device="cpu")
        one.update(torch.from_numpy(pred.astype(np.int64)), torch.from_numpy(target))
        assert matrices[key] == one.mat.tolist()
    assert (np.sum([matrices[k] for k in matrices], axis=0) == mat).all()
    out.unlink()
    with pytest.raises(SystemExit, match=r"refusing to overwrite .*per-image-confusion"):
        score_predictions.main(
            [
                "--pred-dir",
                str(made["pred"]),
                "--arm-root",
                str(arm),
                "--split",
                "val",
                "--provenance",
                str(made["prov"]),
                "--out",
                str(out),
            ]
        )


def test_score_predictions_removes_per_image_file_when_result_write_fails(tmp_path, monkeypatch):
    arm = make_arm(tmp_path, arm="paul", grouped=False)
    made = make_scored_run(tmp_path, arm)
    out = tmp_path / "results-val.json"
    argv = [
        "--pred-dir",
        str(made["pred"]),
        "--arm-root",
        str(arm),
        "--split",
        "val",
        "--provenance",
        str(made["prov"]),
        "--out",
        str(out),
    ]
    write_text = Path.write_text

    def failing(self, *args, **kwargs):
        if self == out:
            raise OSError("disk full")
        return write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing)
    with pytest.raises(OSError, match="disk full"):
        score_predictions.main(argv)
    assert not out.exists()
    assert not score_predictions.per_image_confusion_path(out).exists()
    monkeypatch.undo()
    assert score_predictions.main(argv) == 0  # a rerun is not blocked
    assert out.is_file() and score_predictions.per_image_confusion_path(out).is_file()


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (provenance(label="paul-reference__rr22-0.8964"), "never scored"),
        (provenance(label="paper-hrnet__rs19-paul__arm-fixed-grouped"), "differs from the scored"),
        (provenance(label="paper-hrnet__rs19-paul"), "RAD-stage label"),
        (provenance(label="paper-frrn__rs19-ours__arm-paul"), "RAD-stage label"),
        (
            provenance(
                owner_of_each_checkpoint_in_chain={
                    "map_city": "nvidia",
                    "rs19": "ours",
                    "rad": "ours",
                }
            ),
            "checkpoint owners",
        ),
        (provenance(label="paper-sfnet__rs19-ours__arm-paul"), "pinned"),
        (provenance(label="paper-sfnet__mapcity-direct__arm-paul"), "pinned"),
        (provenance(label="paper-hrnet__rs19-paul__arm-paul__recipe-train_3"), "not a variant"),
        (provenance(label="paper-hrnet__mapcity-direct__arm-paul__recipe-train_2"), "variant"),
        (provenance(label="paper-hrnet__rs19-paul__recipe-train_2__arm-paul"), "RAD-stage label"),
        (provenance(label="paper-hrnet__rs19-none__arm-paul"), "RAD-stage label"),
        (
            provenance(
                label="paper-hrnet__mapcity-direct__arm-paul",
                owner_of_each_checkpoint_in_chain={
                    "map_city": "nvidia",
                    "rs19": "paul",
                    "rad": "ours",
                },
            ),
            "checkpoint owners",
        ),
        (
            provenance(
                label="paper-hrnet__mapcity-direct__arm-paul",
                checkpoints=provenance()["checkpoints"],  # an rs19 entry in a direct chain
            ),
            "exactly the chain stages",
        ),
        (provenance(label="paper-sfnet__rs19-paul__arm-paul"), "reserved"),
        (provenance(gpu_assignment={"indices": [0, 2], "uuids": []}), "within 2-9"),
        (provenance(dry_run=True), "not a scored run"),
        (provenance(probe_epochs=1), "not a scored run"),
        (provenance(pins_override="/tmp/pins.json"), "not a scored run"),
        ({"label": "paper-hrnet__rs19-paul__arm-paul"}, "lacks"),
    ],
)
def test_score_predictions_enforces_labels_and_provenance(tmp_path, record, message):
    arm = make_arm(tmp_path, arm="paul", grouped=False)
    write_preds(arm, "val", tmp_path / "preds")
    if record["label"].startswith("paper-sfnet"):
        # owners right, but the Map->City checkpoint is the HRNet one
        record["owner_of_each_checkpoint_in_chain"] = dict(
            score_predictions.CHAINS[record["label"].rsplit("__arm-", 1)[0]]
        )
        if "rs19-ours" in record["label"] or "mapcity-direct" in record["label"]:
            record["checkpoints"]["map_city"]["sha256"] = score_predictions.PINNED[
                ("paper-hrnet", "map_city")
            ]
        else:
            record["checkpoints"]["map_city"]["sha256"] = score_predictions.PINNED[
                ("paper-sfnet", "map_city")
            ]
    prov = tmp_path / "provenance.json"
    prov.write_text(json.dumps(record))
    with pytest.raises(score_predictions.ScoreError, match=message):
        score_predictions.score(tmp_path / "preds", arm, "val", prov)


def _other_run_provenance(made, tmp_path):
    other = tmp_path / "other-run" / "dumps" / "x"
    other.mkdir(parents=True)
    return other / "dump-provenance.json", json.loads(made["prov"].read_text())


def _edit(path: Path, change) -> None:
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("provenance-of-another-dump", "not in the dump directory"),
        ("dump-preds-elsewhere", "not --pred-dir"),
        ("manifest-split", "dump, not"),
        ("manifest-checkpoint", "is not checkpoints.rad"),
        ("multi-scale", "single-scale"),
        ("coverage-skipped-head", "did not load"),
        ("training-provenance-edited", "changed since the dump"),
        ("training-unfinished", "did not finish"),
        ("dump-unfinished", "did not finish"),
        ("arm-re-prepared", "changed since adapter"),
        ("adapter-rebuilt", "differs from the run's provenance"),
        ("not-a-dump", "dump-provenance.json"),
    ],
)
def test_score_predictions_ties_predictions_to_their_run(tmp_path, tamper, message):
    arm = make_arm(tmp_path, arm="paul", grouped=False)
    made = make_scored_run(tmp_path, arm)
    prov, pred = made["prov"], made["pred"]
    manifest = Path(str(pred) + ".manifest.json")
    if tamper == "provenance-of-another-dump":
        target = tmp_path / "elsewhere" / "dump-provenance.json"
        target.parent.mkdir()
        target.write_text(prov.read_text())
        prov = target
    elif tamper == "dump-preds-elsewhere":
        _edit(prov, lambda v: v["command"].__setitem__(-1, str(made["dump"] / "other")))
    elif tamper == "manifest-split":
        _edit(manifest, lambda v: v.__setitem__("split", "test"))
    elif tamper == "manifest-checkpoint":
        _edit(manifest, lambda v: v.__setitem__("snapshot_sha256", "c" * 64))
    elif tamper == "multi-scale":
        _edit(manifest, lambda v: v.update(single_scale_whole_image=False, n_scales=[0.5, 1, 2]))
    elif tamper == "coverage-skipped-head":
        _edit(made["dump"] / "log" / "init-coverage.json", lambda v: v.update(skipped_tensors=4))
    elif tamper == "training-provenance-edited":
        _edit(made["run"] / "provenance.json", lambda v: v.update(label=v["label"]))
        (made["run"] / "provenance.json").write_text(
            (made["run"] / "provenance.json").read_text() + " "
        )
    elif tamper == "training-unfinished":
        write_json(made["run"] / "gpu-assignment.json", {"status": "running"})
    elif tamper == "dump-unfinished":
        write_json(made["dump"] / "gpu-assignment.json", {"status": "exited", "exit_code": 1})
    elif tamper == "arm-re-prepared":
        _edit(arm / "splits.json", lambda v: v.update(_note="re-prepared"))
    elif tamper == "adapter-rebuilt":
        _edit(tmp_path / "adapter" / "manifest.json", lambda v: v.update(arm_name="x"))
    elif tamper == "not-a-dump":
        _edit(prov, lambda v: v.update(stage="rad"))
    with pytest.raises(score_predictions.ScoreError, match=message):
        score_predictions.score(pred, arm, "val", prov)


@pytest.mark.parametrize(
    "label",
    [
        "paper-hrnet__mapcity-direct__arm-paul",
        "paper-hrnet__rs19-paul__arm-paul__recipe-train_2",
        "paper-hrnet__rs19-paul__arm-paul__recipe-train_1",
    ],
)
def test_score_predictions_accepts_direct_chain_and_recipe_variants(tmp_path, label):
    arm = make_arm(tmp_path, arm="paul", grouped=False)
    made = make_scored_run(tmp_path, arm, label=label)
    result = score_predictions.score(made["pred"], arm, "val", made["prov"])
    assert result["label"] == label
    assert result["base_label"] == label.split("__arm-")[0]
    want = label.split("__recipe-")[1] if "__recipe-" in label else "paul-shared-20260923"
    assert result["recipe_variant"] == want
    stages = set(result["provenance"]["checkpoints"])
    assert stages == (
        {"map_city", "rad"} if "mapcity-direct" in label else {"map_city", "rs19", "rad"}
    )


@pytest.mark.parametrize(
    ("label", "recorded"),
    [
        ("paper-hrnet__rs19-paul__arm-paul", "train_2"),
        ("paper-hrnet__rs19-paul__arm-paul__recipe-train_2", "paul-shared-20260923"),
        ("paper-hrnet__rs19-paul__arm-paul", None),
    ],
)
def test_score_predictions_refuses_training_recipe_not_named_by_label(tmp_path, label, recorded):
    arm = make_arm(tmp_path, arm="paul", grouped=False)
    made = make_scored_run(tmp_path, arm, label=label)
    training = made["run"] / "provenance.json"
    _edit(training, lambda v: v.update(extra={"recipe_variant": recorded} if recorded else {}))
    _edit(made["prov"], lambda v: v["dump"].update(training_provenance_sha256=sha_of(training)))
    with pytest.raises(score_predictions.ScoreError, match="recipe_variant"):
        score_predictions.score(made["pred"], arm, "val", made["prov"])


def test_score_predictions_multi_scale_only_as_secondary(tmp_path):
    arm = make_arm(tmp_path, arm="paul", grouped=False)
    made = make_scored_run(tmp_path, arm)
    _edit(
        Path(str(made["pred"]) + ".manifest.json"),
        lambda v: v.update(single_scale_whole_image=False, n_scales=[0.5, 1.0, 2.0]),
    )
    result = score_predictions.score(made["pred"], arm, "val", made["prov"], True)
    assert result["inference"].startswith("multi-scale") and "secondary" in result["inference"]


def test_score_predictions_requires_exact_prediction_set_and_audited_masks(tmp_path):
    arm = make_arm(tmp_path, arm="paul", grouped=False)
    made = make_scored_run(tmp_path, arm)
    preds = made["pred"]
    (preds / "g-c__0005.png").unlink()
    with pytest.raises(score_predictions.ScoreError, match="exactly"):
        score_predictions.score(preds, arm, "val", made["prov"])
    write_preds(arm, "val", preds)
    Image.fromarray(np.zeros((H, W), np.uint8)).save(arm / "masks/val/g-c/0004.png")
    with pytest.raises(score_predictions.ScoreError, match="differs from the audit"):
        score_predictions.score(preds, arm, "val", made["prov"])


def test_staged_scorer_needs_a_segmentary_checkout(tmp_path):
    """A copy outside the repo (as staged on HDRFS) must use SEGMENTARY_REPO or refuse."""
    staged = tmp_path / "tools" / "paul_forks" / "score_predictions.py"
    staged.parent.mkdir(parents=True)
    staged.write_text((PAUL_FORKS / "score_predictions.py").read_text())
    env = {k: v for k, v in os.environ.items() if k not in ("SEGMENTARY_REPO", "PYTHONPATH")}
    refused = subprocess.run(
        [sys.executable, str(staged), "--help"], env=env, capture_output=True, text=True
    )
    assert refused.returncode != 0 and "SEGMENTARY_REPO" in refused.stderr
    env["SEGMENTARY_REPO"] = str(PAUL_FORKS.parents[1])
    ok = subprocess.run(
        [sys.executable, str(staged), "--help"], env=env, capture_output=True, text=True
    )
    assert ok.returncode == 0, ok.stderr
    assert "--allow-multi-scale" in ok.stdout


# --------------------------------------------------------------------------- queue


class FakeTmux:
    """tmux with sessions as a dict (name -> start command); records new-session calls."""

    def __init__(self, sessions=None):
        self.sessions = dict(sessions or {})
        self.started: list[tuple[str, str]] = []
        self.fail_new = False
        self.list_error = ""

    def __call__(self, args):
        if args[0] == "list-panes":
            if self.list_error:
                return 1, "", self.list_error
            return 0, "".join(f"{n}\t{c}\n" for n, c in self.sessions.items()), ""
        if args[0] == "new-session":
            if self.fail_new:
                return 1, "", "boom"
            name, command = args[args.index("-s") + 1], args[-1]
            assert name not in self.sessions
            self.sessions[name] = command
            self.started.append((name, command))
            return 0, "", ""
        raise AssertionError(f"unexpected tmux call {args}")


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def queue_job(name, label, recipe="paper-hrnet.sh", args=None, groups=None, **extra):
    job = {
        "name": name,
        "label": label,
        "recipe": recipe,
        "args": args if args is not None else label_args(label),
        "gpu_groups": groups or [[2, 3, 4, 5], [6, 7, 8, 9]],
    }
    job.update(extra)
    return job


def label_args(label):
    if "__arm-" not in label:
        return []
    base, arm = label.split("__recipe-")[0].split("__arm-")
    chain = base.split("__")[1]
    rs19 = "none" if chain == "mapcity-direct" else chain.removeprefix("rs19-")
    return ["--rs19", rs19, "--arm", arm]


def direct(arm, family="hrnet"):
    return f"paper-{family}__mapcity-direct__arm-{arm}"


def make_queue(tmp_path, jobs, smi=None, tmux=None, min_idle=0, holds=None):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"min_idle_seconds": min_idle, "holds": holds or [], "jobs": jobs}))
    root = tmp_path / "run-root"
    root.mkdir(exist_ok=True)
    logs: list[str] = []
    machine = fork_queue.Machine(
        smi=smi or FakeSmi(),
        tmux=tmux or FakeTmux(),
        clock=Clock(),
        sleep=lambda s: None,
        idle_pause_seconds=0.0,
        log=logs.append,
    )
    queue = fork_queue.Queue(fork_queue.load_spec(path), root, machine)
    return queue, path, root


def finish(queue, name, status="exited", code=0, label=None):
    """Simulate a job's session ending after fork_gpu_run wrote its record."""
    job = queue.spec.job(name)
    run = queue.run_dir(job)
    write_json(run / "provenance.json", {"label": label or job.label})
    write_json(run / "gpu-assignment.json", {"status": status, "exit_code": code})
    queue.exit_file(job).parent.mkdir(parents=True, exist_ok=True)
    queue.exit_file(job).write_text(f"{code}\n")
    queue.machine.tmux.sessions.pop(job.session)


def statuses(queue):
    return {name: entry["status"] for name, entry in queue.state["jobs"].items()}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"gpu_groups": [[0, 2, 3, 4]]}, "GPU 0 or 1"),
        ({"gpu_groups": [[2, 3, 4, 5], [1, 6, 7, 8]]}, "GPU 0 or 1"),
        ({"gpu_groups": [[2, 3, 4, 10]]}, "outside 2-9"),
        ({"gpu_groups": [[2, 2, 3, 4]]}, "duplicates"),
        ({"gpu_groups": [[2, 3]]}, "takes (4,) GPUs"),
        ({"gpu_groups": []}, "non-empty"),
        ({"args": ["--rs19", "none", "--arm", "paul", "--gpus", "2,3,4,5"]}, "not allowed"),
        ({"env": {"CUDA_VISIBLE_DEVICES": "2"}}, "env may only set"),
        ({"env": {"HRNET_RAD_RECIPE": "train_2"}}, "the recipe would write"),
        ({"label": "paper-hrnet__rs19-paul__arm-paul"}, "the recipe would write"),
        ({"recipe": "frrn.sh"}, "recipe must be"),
        ({"depends_on": ["later"]}, "earlier jobs"),
        ({"name": "Bad Name"}, "name must match"),
    ],
)
def test_queue_file_refusals(tmp_path, change, message):
    job = queue_job("a", direct("paul"))
    job.update(change)
    with pytest.raises(fork_queue.QueueError, match=re.escape(message)):
        make_queue(tmp_path, [job, queue_job("later", direct("fixed-grouped"))])


def test_queue_file_refuses_bad_resolver_and_duplicate_labels(tmp_path):
    rs19 = queue_job("rs19", "hrnet-rs19-ours", recipe="hrnet-rs19-ours.sh")
    ours = queue_job("ours", "paper-hrnet__rs19-ours__arm-paul", rs19_ckpt_from="rs19")
    with pytest.raises(fork_queue.QueueError, match="in depends_on"):
        make_queue(tmp_path, [rs19, ours])
    sfnet_rs19 = queue_job("sf", "sfnet-rs19-ours", recipe="sfnet-rs19-ours.sh")
    wrong = dict(ours, depends_on=["sf"], rs19_ckpt_from="sf")
    with pytest.raises(fork_queue.QueueError, match="hrnet-rs19-ours job"):
        make_queue(tmp_path, [sfnet_rs19, wrong])
    with pytest.raises(fork_queue.QueueError, match="needs --rs19-ckpt or rs19_ckpt_from"):
        make_queue(tmp_path, [rs19, dict(ours, rs19_ckpt_from=None)])
    with pytest.raises(fork_queue.QueueError, match="same label"):
        make_queue(tmp_path, [queue_job("a", direct("paul")), queue_job("b", direct("paul"))])


def test_tracked_queue_file_is_valid_and_ordered():
    spec = fork_queue.load_spec(PAUL_FORKS / "queue" / "rad-9-24-paper-models.yaml")
    labels = [job.label for job in spec.jobs]
    arms = ["paul", "fixed-stratified", "fixed-grouped"]
    # Our own RS19 retraining first (the work the comparison waits on), then RAD from it,
    # then the optional comparisons: Map->City direct and the checkpoint-stored HRNet recipe.
    expected = (
        ["sfnet-rs19-ours", "hrnet-rs19-ours"]
        + [f"paper-sfnet__rs19-ours__arm-{a}" for a in arms]
        + [f"paper-hrnet__rs19-ours__arm-{a}" for a in arms]
        + [direct(a, "sfnet") for a in arms]
        + [f"paper-hrnet__rs19-paul__arm-{a}__recipe-train_2" for a in arms]
        + [direct(a) for a in arms]
    )
    assert labels == expected
    # Only recipes stored in Paul's checkpoints get a recipe label (SFNet train_2 is from git).
    assert not any(dict(job.env).get("SFNET_RAD_RECIPE") for job in spec.jobs)
    assert {(h.session, h.gpus) for h in spec.holds} == {
        ("pf-paper-hrnet-rs19-paul", (2, 3, 4, 5)),
        ("rad-catalog*", (6, 7, 8, 9)),
    }
    for job in spec.jobs:
        assert all(set(g) <= set(range(2, 10)) for g in job.gpu_groups)
        assert {i for g in job.gpu_groups for i in g} == set(range(2, 10))
        if job.rs19_ckpt_from:
            assert job.depends_on == (job.rs19_ckpt_from,)
    assert spec.job("hrnet-rs19paul-train2-paul").env == (("HRNET_RAD_RECIPE", "train_2"),)


def test_queue_respects_order_depends_on_and_never_retries(tmp_path):
    jobs = [
        queue_job("x", direct("paul")),
        queue_job(
            "d",
            "paper-hrnet__rs19-paul__arm-paul__recipe-train_2",
            depends_on=["x"],
            env={"HRNET_RAD_RECIPE": "train_2"},
        ),
        queue_job("y", direct("fixed-stratified")),
        queue_job("z", direct("fixed-grouped")),
        queue_job(
            "e",
            "paper-hrnet__rs19-paul__arm-paul__recipe-train_1",
            depends_on=["z"],
            env={"HRNET_RAD_RECIPE": "train_1"},
        ),
    ]
    queue, _, _ = make_queue(tmp_path, jobs)
    tmux = queue.machine.tmux
    assert queue.tick()
    assert [n for n, _ in tmux.started] == ["pf-q-x", "pf-q-y"]  # z waits for a free quad
    assert queue.state["jobs"]["x"]["gpus"] == [2, 3, 4, 5]
    assert queue.state["jobs"]["y"]["gpus"] == [6, 7, 8, 9]
    assert queue.state["jobs"]["d"]["reason"] == "waiting for dependencies"
    finish(queue, "x")
    assert queue.tick()
    # d (now ready, earlier in the file) gets the freed GPUs before z
    assert statuses(queue)["x"] == "done" and statuses(queue)["d"] == "running"
    assert queue.state["jobs"]["d"]["gpus"] == [2, 3, 4, 5]
    assert statuses(queue)["z"] == "pending"
    finish(queue, "y", code=1)
    assert queue.tick()
    assert statuses(queue)["y"] == "failed" and queue.state["jobs"]["y"]["exit_code"] == 1
    assert statuses(queue)["z"] == "running"
    finish(queue, "z", code=1)
    finish(queue, "d")
    assert not queue.tick()  # e's dependency failed; nothing else can start
    assert statuses(queue) == {
        "x": "done",
        "d": "done",
        "y": "failed",
        "z": "failed",
        "e": "pending",
    }
    assert queue.state["jobs"]["e"]["reason"] == "a dependency failed"
    assert [n for n, _ in tmux.started] == ["pf-q-x", "pf-q-y", "pf-q-d", "pf-q-z"]
    saved = json.loads((queue.root / "queue-state.json").read_text())
    assert saved["jobs"]["y"]["status"] == "failed"


def test_queue_does_not_start_on_busy_held_or_unsettled_gpus(tmp_path):
    smi = FakeSmi(apps=lambda: [(ALLOWED[2][0], 4242)])
    smi.state[7] = [5000, 0]
    jobs = [
        queue_job(
            "a",
            direct("paul", "sfnet"),
            recipe="paper-sfnet.sh",
            groups=[[2, 3], [4, 5], [6, 7], [8, 9]],
        )
    ]
    tmux = FakeTmux(
        {
            "pf-paper-hrnet-rs19-paul": "for a in paul; do paper-hrnet.sh --gpus 4,5 ...; done",
            "rtis-paul-seed0-gpu-8": "python run_rtis_full_campaign.py",
            "rad-catalog-launcher": "python launch_rtis_full_campaign.py",
            "unrelated": "train.py --gpus 9",
        }
    )
    queue, _, _ = make_queue(
        tmp_path,
        jobs,
        smi=smi,
        tmux=tmux,
        holds=[{"session": "rad-catalog-*", "gpus": [9]}],
    )
    assert queue.tick()
    assert tmux.started == []  # 2 compute app, 4-5 + 8 + 9 held, 7 has memory in use
    del tmux.sessions["rad-catalog-launcher"]
    assert queue.tick() and tmux.started == []  # 8 still held by its -gpu-8 service
    del tmux.sessions["rtis-paul-seed0-gpu-8"]
    assert queue.tick()
    assert queue.state["jobs"]["a"]["gpus"] == [8, 9]


# Start commands as `tmux list-panes -F '#{pane_start_command}'` printed them on HDRFS
# (2026-10-04), shortened only in the paths: the guards must work on these, not on stand-ins.
LIVE_HRNET_SESSION = (
    '"for a in paul fixed-stratified fixed-grouped; do env -u CUDA_VISIBLE_DEVICES -u '
    "CUDA_DEVICE_ORDER -u NVIDIA_VISIBLE_DEVICES /r/tools/paul_forks/recipes/paper-hrnet.sh "
    "--rs19 paul --arm \\$a --gpus 2,3,4,5 --run-dir /r/runs/paper-hrnet__rs19-paul__arm-\\$a "
    '>> /r/logs/paper-hrnet__rs19-paul.log 2>&1 || break; done"'
)
LIVE_CAMPAIGN_SESSIONS = {
    "rad-catalog-launcher": '"cd /s && env CUDA_VISIBLE_DEVICES= PYTHONPATH=src /e/python -u '
    'scripts/launch_rtis_full_campaign.py --no-dashboard --campaign /c/paul-seed0 >> /c/l 2>&1"',
    **{
        f"rtis-paul-seed0-20261005-r2-gpu-{i}": (
            f'"cd /s && env CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES={i} /e/python -u '
            f'scripts/run_rtis_full_campaign.py --campaign /c/paul-seed0 --gpu {i} >> /c/g 2>&1"'
        )
        for i in (6, 7, 8, 9)
    },
}


def test_tracked_queue_holds_the_live_sessions_gpus(tmp_path):
    """The tracked queue file against the live session commands, every GPU idle and settled:
    nothing starts while the HRNet run and the campaign live (between their runs too)."""
    spec = fork_queue.load_spec(PAUL_FORKS / "queue" / "rad-9-24-paper-models.yaml")
    smi = FakeSmi()
    tmux = FakeTmux({"pf-paper-hrnet-rs19-paul": LIVE_HRNET_SESSION, **LIVE_CAMPAIGN_SESSIONS})
    machine = fork_queue.Machine(
        smi=smi,
        tmux=tmux,
        clock=Clock(),
        sleep=lambda s: None,
        idle_pause_seconds=0.0,
        log=lambda m: None,
    )
    root = tmp_path / "run-root"
    queue = fork_queue.Queue(spec, root, machine)
    assert queue.held(tmux.sessions) == set(range(2, 10))
    for _ in range(3):
        assert queue.tick()
        machine.clock.t += spec.min_idle_seconds
    assert tmux.started == []
    # Between campaign runs the per-GPU services may be gone; the launcher hold still covers.
    for i in (6, 7, 8, 9):
        del tmux.sessions[f"rtis-paul-seed0-20261005-r2-gpu-{i}"]
    assert queue.tick() and tmux.started == []
    # tmux unreadable (socket removed): no holds can be seen, so nothing starts.
    tmux.list_error = "error connecting to /tmp/tmux-1/default (No such file or directory)\n"
    for _ in range(3):
        assert queue.tick()
        machine.clock.t += spec.min_idle_seconds
    tmux.list_error = "no server running on /tmp/tmux-1/default\n"
    assert queue.tick() and tmux.started == []
    tmux.list_error = ""
    # The explicit hold keeps 2-5 even if the HRNet session's command named no GPU.
    assert queue.held({"pf-paper-hrnet-rs19-paul": "bash"}) == {2, 3, 4, 5}
    # The campaign ends first (~32 h): our SFNet RS19 stage takes 6-9; HRNet RS19 waits for a
    # quad and holds back the optional jobs (the dependents of the RS19 stages do not).
    del tmux.sessions["rad-catalog-launcher"]
    assert queue.tick() and tmux.started == []  # idle times restart after the tmux outage
    machine.clock.t += spec.min_idle_seconds
    assert queue.tick()
    assert [(n, queue.state["jobs"][n[5:]]["gpus"]) for n, _ in tmux.started] == [
        ("pf-q-sfnet-rs19-ours", [6, 7, 8, 9]),
    ]
    # The HRNet run ends (~72 h): our HRNet RS19 stage takes 2-5.
    del tmux.sessions["pf-paper-hrnet-rs19-paul"]
    assert queue.tick()
    assert [(n, queue.state["jobs"][n[5:]]["gpus"]) for n, _ in tmux.started] == [
        ("pf-q-sfnet-rs19-ours", [6, 7, 8, 9]),
        ("pf-q-hrnet-rs19-ours", [2, 3, 4, 5]),
    ]
    assert all("--gpus 0" not in c and "--gpus 1" not in c for _, c in tmux.started)


def test_queue_keeps_running_jobs_when_tmux_cannot_be_read(tmp_path):
    queue, _, _ = make_queue(tmp_path, [queue_job("a", direct("paul"))])
    tmux = queue.machine.tmux
    assert queue.tick() and statuses(queue)["a"] == "running"
    tmux.list_error = "no server running on /tmp/tmux-1/default\n"
    assert queue.tick() and statuses(queue)["a"] == "running"  # not finalised as gone
    assert queue.state["jobs"]["a"]["gpus"] == [2, 3, 4, 5]


def test_queue_needs_gpus_idle_for_min_idle_seconds(tmp_path):
    smi = FakeSmi()
    queue, _, _ = make_queue(tmp_path, [queue_job("a", direct("paul"))], smi=smi, min_idle=300)
    clock = queue.machine.clock
    assert queue.tick() and queue.machine.tmux.started == []
    clock.t += 200
    smi.state[6] = [0, 50]  # a short gap on 6: its idle time restarts
    assert queue.tick() and queue.machine.tmux.started == []
    smi.state[6] = [0, 0]
    clock.t += 150
    assert queue.tick()
    assert queue.state["jobs"]["a"]["gpus"] == [2, 3, 4, 5]  # 2-5 idle for 350 s, 6 for 0 s


def test_queue_command_clears_gpu_env_and_runs_the_recipe(tmp_path, monkeypatch):
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    (recipes / "paper-hrnet.sh").write_text(
        "env | grep -E '^(CUDA|NVIDIA|PROBE|HRNET|PAUL_FORK|FORK_GPU_RUN)' | sort\n"
        'printf "%s\\n" "$@"\nexit 7\n'
    )
    monkeypatch.setattr(fork_queue, "RECIPES_DIR", recipes)
    jobs = [
        queue_job(
            "t2",
            "paper-hrnet__rs19-paul__arm-paul__recipe-train_2",
            env={"HRNET_RAD_RECIPE": "train_2"},
        )
    ]
    queue, _, root = make_queue(tmp_path, jobs)
    assert queue.tick()
    name, command = queue.machine.tmux.started[0]
    assert name == "pf-q-t2"
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": "0,1",
        "CUDA_DEVICE_ORDER": "FASTEST_FIRST",
        "NVIDIA_VISIBLE_DEVICES": "all",
        "PROBE_EPOCHS": "1",
        "HRNET_RAD_RECIPE": "train_1",
        "FORK_GPU_RUN": "/tmp/other/fork_gpu_run.py",
        "PAUL_FORK_RUN_ROOT": "/elsewhere",
        **{
            f"PAUL_FORK_{name}": "/elsewhere"
            for name in ("ADAPTERS", "ENV", "PATCHES", "PYTHON", "RS19_ROOT", "TOOL_PYTHON")
        },
        "PAUL_FORK_DRY_RUN": "1",
        "PAUL_FORK_PINS_FILE": "/elsewhere/pins",
    }
    subprocess.run(["sh", "-c", command], env=env, check=True)
    job = queue.spec.job("t2")
    assert queue.exit_file(job).read_text().strip() == "7"
    out = queue.log(job).read_text().splitlines()
    assert "HRNET_RAD_RECIPE=train_2" in out
    assert f"PAUL_FORK_RUN_ROOT={root}" in out
    assert not [line for line in out if line.startswith(("CUDA", "NVIDIA", "PROBE"))]
    # Inherited path overrides are dropped: the recipes use their defaults.
    assert not [line for line in out if "/elsewhere" in line or line.startswith("FORK_GPU_RUN")]
    argv = out[out.index("--rs19") :]
    assert argv == [
        "--rs19",
        "paul",
        "--arm",
        "paul",
        "--gpus",
        "2,3,4,5",
        "--run-dir",
        str(root / "runs" / job.label),
    ]
    del queue.machine.tmux.sessions["pf-q-t2"]
    assert not queue.tick()  # the fake recipe exited 7 before launching: failed, not retried
    assert statuses(queue)["t2"] == "failed"
    assert queue.state["jobs"]["t2"]["recipe_exit_code"] == 7


def test_queue_launch_refusal_returns_job_to_pending(tmp_path):
    queue, _, root = make_queue(tmp_path, [queue_job("a", direct("paul"), groups=[[2, 3, 4, 5]])])
    assert queue.tick()
    job = queue.spec.job("a")
    run = queue.run_dir(job)
    write_json(run / "provenance.json", {"label": job.label})
    (run / "centroids").mkdir()
    (run / "console.log").write_text(
        "fork_gpu_run: REFUSED: GPU 3 is not idle: ['3', 'GPU-...', '900', '0']\n"
    )
    queue.exit_file(job).write_text("2\n")
    queue.machine.tmux.sessions.pop(job.session)
    queue.machine.smi.state[3] = [900, 0]
    assert queue.tick()
    entry = queue.state["jobs"]["a"]
    assert entry["status"] == "pending" and entry["launch_refusals"] == 1
    assert "not idle" in entry["last_refusal"]
    assert not run.exists()
    moved = list((root / "queue" / "refused").iterdir())
    assert len(moved) == 1 and (moved[0] / "provenance.json").is_file()
    assert len(queue.machine.tmux.started) == 1  # GPU 3 still busy
    queue.machine.smi.state[3] = [0, 0]
    assert queue.tick()
    assert statuses(queue)["a"] == "running" and len(queue.machine.tmux.started) == 2


def test_queue_restart_is_idempotent_and_single_instance(tmp_path):
    jobs = [
        queue_job(n, direct(a))
        for n, a in (("p", "paul"), ("s", "fixed-stratified"), ("g", "fixed-grouped"))
    ]
    queue, path, root = make_queue(tmp_path, jobs)
    for name, code in (("p", 0), ("s", 1)):
        run = root / "runs" / queue.spec.job(name).label
        write_json(run / "provenance.json", {"label": queue.spec.job(name).label})
        write_json(run / "gpu-assignment.json", {"status": "exited", "exit_code": code})
    assert queue.tick()
    assert statuses(queue) == {"p": "done", "s": "failed", "g": "running"}
    assert [n for n, _ in queue.machine.tmux.started] == ["pf-q-g"]
    # A new queue process with the same state: g is still running and keeps its GPUs.
    again = fork_queue.Queue(fork_queue.load_spec(path), root, queue.machine)
    assert again.tick()
    assert statuses(again) == {"p": "done", "s": "failed", "g": "running"}
    assert len(queue.machine.tmux.started) == 1
    # Fresh state, run dir without a finished record (someone else's run): not started.
    (root / "queue-state.json").unlink()
    queue.machine.tmux.sessions.clear()
    write_json(root / "runs" / queue.spec.job("g").label / "provenance.json", {"label": "x"})
    third = fork_queue.Queue(fork_queue.load_spec(path), root, queue.machine)
    queue.machine.tmux.sessions["pf-q-old"] = "env ... paper-hrnet.sh --gpus 2,3,4,5 --run-dir x"
    assert third.held(queue.machine.tmux.sessions) == {2, 3, 4, 5}  # a queue session not ours
    assert third.tick()
    assert statuses(third)["g"] == "pending"
    assert "without a finished launcher record" in third.state["jobs"]["g"]["reason"]
    assert len(queue.machine.tmux.started) == 1
    with fork_queue.single_instance(root):
        code = fork_queue.main(
            ["run", "--once", "--queue", str(path), "--run-root", str(root)], machine=queue.machine
        )
    assert code == 2


def test_queue_reset_only_failed_jobs_without_run_dir(tmp_path, capsys):
    queue, path, root = make_queue(tmp_path, [queue_job("a", direct("paul"))])
    assert queue.tick()
    finish(queue, "a", code=1)
    assert not queue.tick() and statuses(queue)["a"] == "failed"
    argv = ["reset", "a", "--queue", str(path), "--run-root", str(root)]
    assert fork_queue.main(argv, machine=queue.machine) == 2
    assert "move" in capsys.readouterr().err
    (root / "runs" / queue.spec.job("a").label).rename(root / "aside")
    assert fork_queue.main(argv, machine=queue.machine) == 0
    assert json.loads((root / "queue-state.json").read_text())["jobs"]["a"]["status"] == "pending"


def test_stop_queue_drains(tmp_path):
    jobs = [queue_job("a", direct("paul")), queue_job("b", direct("fixed-grouped"))]
    queue, _, root = make_queue(tmp_path, jobs)
    queue.machine.smi.state[6] = [5000, 90]
    assert queue.tick() and statuses(queue)["a"] == "running"
    (root / "STOP_QUEUE").write_text("")
    queue.machine.smi.state[6] = [0, 0]
    assert queue.tick()  # a still running: keep watching it, but start nothing
    assert statuses(queue)["b"] == "pending" and len(queue.machine.tmux.started) == 1
    finish(queue, "a")
    assert not queue.tick()
    assert statuses(queue) == {"a": "done", "b": "pending"}
    assert len(queue.machine.tmux.started) == 1


def _rs19_run(root, label, files):
    run = root / "runs" / label
    write_json(run / "provenance.json", {"label": label, "dry_run": False, "probe_epochs": None})
    write_json(run / "gpu-assignment.json", {"status": "exited", "exit_code": 0})
    for rel in files:
        (run / rel).parent.mkdir(parents=True, exist_ok=True)
        (run / rel).write_bytes(b"w")
    return run


def test_rs19_resolver_picks_what_the_recipe_accepts(tmp_path):
    hr = _rs19_run(
        tmp_path,
        "hrnet-rs19-ours",
        [
            "train/best_checkpoint_ep98.pth",
            "train/last_checkpoint_ep149.pth",
        ],
    )
    sf = _rs19_run(
        tmp_path,
        "sfnet-rs19-ours",
        [
            "ckpt/sfnet-rs19-ours/railsem19-x_sbn/best_epoch_391_mean-iu_0.75268.pth",
            "ckpt/sfnet-rs19-ours/railsem19-x_sbn/last_epoch_399_mean-iu_0.74000.pth",
        ],
    )
    resolved = {
        "hrnet-rs19-ours": fork_queue.resolve_rs19_checkpoint(hr, "hrnet-rs19-ours"),
        "sfnet-rs19-ours": fork_queue.resolve_rs19_checkpoint(sf, "sfnet-rs19-ours"),
    }
    assert resolved["hrnet-rs19-ours"].name == "best_checkpoint_ep98.pth"
    assert resolved["sfnet-rs19-ours"].name == "best_epoch_391_mean-iu_0.75268.pth"
    common = PAUL_FORKS / "recipes" / "_common.sh"
    for label, ckpt in resolved.items():
        check = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{common}"; pf_check_rs19_ours "$1" "$2"',
                "x",
                str(ckpt),
                label,
            ],
            env={**os.environ, "PAUL_FORK_TOOL_PYTHON": sys.executable},
            capture_output=True,
            text=True,
        )
        assert check.returncode == 0, check.stderr
        assert check.stdout.strip().endswith(f"{label}/provenance.json")
    with pytest.raises(fork_queue.QueueError, match="not a finished hrnet-rs19-ours"):
        fork_queue.resolve_rs19_checkpoint(sf, "hrnet-rs19-ours")
    (hr / "train" / "best_checkpoint_ep120.pth").write_bytes(b"w")
    with pytest.raises(fork_queue.QueueError, match="exactly one best checkpoint"):
        fork_queue.resolve_rs19_checkpoint(hr, "hrnet-rs19-ours")
    write_json(sf / "gpu-assignment.json", {"status": "exited", "exit_code": 1})
    with pytest.raises(fork_queue.QueueError, match="not finished"):
        fork_queue.resolve_rs19_checkpoint(sf, "sfnet-rs19-ours")
    write_json(sf / "gpu-assignment.json", {"status": "exited", "exit_code": 0})
    write_json(sf / "provenance.json", {"label": "sfnet-rs19-ours", "dry_run": True})
    with pytest.raises(fork_queue.QueueError, match="dry_run=True"):
        fork_queue.resolve_rs19_checkpoint(sf, "sfnet-rs19-ours")


def test_queue_resolves_rs19_checkpoint_after_dependency(tmp_path):
    jobs = [
        queue_job("rs19", "sfnet-rs19-ours", recipe="sfnet-rs19-ours.sh"),
        queue_job(
            "rad",
            "paper-sfnet__rs19-ours__arm-paul",
            recipe="paper-sfnet.sh",
            groups=[[2, 3], [4, 5]],
            depends_on=["rs19"],
            rs19_ckpt_from="rs19",
        ),
        queue_job(
            "bad",
            "paper-sfnet__rs19-ours__arm-fixed-grouped",
            recipe="paper-sfnet.sh",
            groups=[[6, 7], [8, 9]],
            depends_on=["rs19"],
            rs19_ckpt_from="rs19",
        ),
    ]
    queue, _, root = make_queue(tmp_path, jobs)
    assert queue.tick() and statuses(queue)["rs19"] == "running"
    assert statuses(queue)["rad"] == "pending"
    queue.machine.tmux.sessions.pop("pf-q-rs19")
    best = "ckpt/sfnet-rs19-ours/x/best_epoch_391_mean-iu_0.75268.pth"
    run = _rs19_run(root, "sfnet-rs19-ours", [best])
    queue.exit_file(queue.spec.job("rs19")).write_text("0\n")
    assert queue.tick()
    assert statuses(queue)["rs19"] == "done" and statuses(queue)["rad"] == "running"
    assert queue.state["jobs"]["rad"]["rs19_ckpt"] == str(run / best)
    assert f"--rs19-ckpt {run / best}" in queue.machine.tmux.started[1][1]
    # "bad" started too (same checkpoint); a second best file would make the next one fail
    assert statuses(queue)["bad"] == "running"


def test_scorer_and_provenance_writer_share_chains_and_recipe_variants():
    # score_predictions.py and recipes/write_provenance.py keep separate copies of these
    # tables (the writer runs with the fork env's Python); they must never drift apart.
    prov = fork_queue.PROV
    assert {b: prov.CHAINS[b] for b in prov.RAD_BASES} == score_predictions.CHAINS
    assert score_predictions.RECIPE_VARIANTS == prov.RECIPE_VARIANTS
    assert score_predictions.DEFAULT_RECIPE == prov.DEFAULT_RECIPE
