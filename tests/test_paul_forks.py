"""Paul-fork tooling: fail-closed GPU launcher, RAD adapter, RS19 split, scorer. No GPU used."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image
from scripts.paul_forks import adapt_rad, fork_gpu_run, make_rs19_split, score_predictions
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


def make_host(tmp_path: Path, smi: FakeSmi | None = None, **overrides) -> Host:
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(exist_ok=True)
    values = {
        "smi": smi or FakeSmi(),
        "process_table": ps_table,
        "lock_dir": lock_dir,
        "environ": {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)},
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
    assert set(env) - {"__CF_USER_TEXT_ENCODING", "LC_CTYPE"} == {
        "PATH",
        "HOME",
        "CUDA_VISIBLE_DEVICES",
        "CUDA_DEVICE_ORDER",
        "OMP_NUM_THREADS",
    }
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
        f"sys.path.insert(0, {str(PAUL_FORKS)!r})\n"
        "import fork_gpu_run as f\n"
        f"sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
        "from test_paul_forks import FakeSmi, ps_table\n"
        "host = f.Host(smi=FakeSmi(), process_table=f.read_proc_table, "
        f"lock_dir=__import__('pathlib').Path({str(tmp_path)!r}), "
        "environ={'PATH': '/usr/bin:/bin'}, idle_pause_seconds=0.0, watchdog_seconds=0.1, "
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
    record = {
        "label": label,
        "owner_of_each_checkpoint_in_chain": dict(
            score_predictions.CHAINS[label.rsplit("__arm-", 1)[0]]
        )
        if "__arm-" in label and label.rsplit("__arm-", 1)[0] in score_predictions.CHAINS
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
    }
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
        if "rs19-ours" in record["label"]:
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
