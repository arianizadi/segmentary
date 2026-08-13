"""Proofs that results.json survives a round trip and an interrupted write."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

import numpy as np
import pytest
import torch

from segmentary.utils.results import (
    RunRecord,
    RunTimer,
    collect_env,
    discover_git_root,
    git_sha,
    load_results,
    peak_vram,
    sanitise,
    write_results,
)
from segmentary.utils.seed import seed_everything, worker_init_fn

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_record(**overrides) -> RunRecord:
    base = dict(
        name="b2-frozen-lora",
        stage="stage2",
        config_hash="deadbeef1234",
        git_sha="0" * 40,
        git_dirty=False,
        seed=42,
        started_at="2026-08-12T00:00:00+00:00",
        finished_at="2026-08-12T04:30:00+00:00",
        wall_clock_s=16200.5,
        peak_vram_bytes={"cuda:0": 40_123_456},
        metrics={"miou": 0.7412, "per_class_iou": {"rail": 0.81, "sky": 0.94}},
        config={"model": {"arch": "segformer_b2", "tuning": "lora"}, "seed": 42},
        env={"torch": "2.11.0+cu128"},
        dataset_sizes={"cityscapes": 2975, "railsem19": 7000},
        notes="baseline for table 4.2",
    )
    base.update(overrides)
    return RunRecord(**base)


# ---------------------------------------------------------------- round trip


def test_round_trips_exactly(tmp_path: Path) -> None:
    record = make_record()
    path = tmp_path / "results.json"
    write_results(path, record)
    assert load_results(path) == record


def test_written_json_is_human_diffable(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    write_results(path, make_record())
    text = path.read_text()

    assert text.endswith("\n")
    assert '\n  "config": {' in text  # indent=2
    keys = list(json.loads(text).keys())
    assert keys == sorted(keys)  # sort_keys=True keeps diffs minimal


# ---------------------------------------------------------------- NaN handling


def test_nan_metrics_become_null_and_reload_as_none(tmp_path: Path) -> None:
    record = make_record(
        metrics={
            "miou": float("nan"),
            "per_class_iou": {"rail": 0.81, "never_seen": float("nan")},
        }
    )
    path = tmp_path / "results.json"
    write_results(path, record)

    # null in the file, not the bare `NaN` json.dumps would otherwise emit.
    raw = path.read_text()
    assert "NaN" not in raw
    assert '"miou": null' in raw

    loaded = load_results(path)
    assert loaded.metrics["miou"] is None
    assert loaded.metrics["per_class_iou"]["never_seen"] is None
    assert loaded.metrics["per_class_iou"]["rail"] == pytest.approx(0.81)


def test_infinities_also_become_null(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    write_results(path, make_record(metrics={"loss": float("inf")}))
    assert load_results(path).metrics["loss"] is None


def test_sanitise_unwraps_numpy_and_torch_scalars() -> None:
    out = sanitise(
        {
            "np_f": np.float32(0.5),
            "np_i": np.int64(7),
            "np_arr": np.array([1.0, np.nan]),
            "t_scalar": torch.tensor(2.5),
            "t_arr": torch.tensor([1, 2]),
            "path": Path("/data/x"),
            "tup": (1, 2),
            3: "int key",
        }
    )
    assert out == {
        "np_f": 0.5,
        "np_i": 7,
        "np_arr": [1.0, None],
        "t_scalar": 2.5,
        "t_arr": [1, 2],
        "path": "/data/x",
        "tup": [1, 2],
        "3": "int key",
    }
    for value in (out["np_f"], out["np_i"], out["t_scalar"]):
        assert type(value) in (int, float)  # plain python, not numpy/torch


def test_sanitise_unwraps_numpy_scalars_that_subclass_builtins() -> None:
    """np.float64 IS a float and np.str_ IS a str, so a naive isinstance order
    returns them unconverted and leaves numpy objects in "plain JSON" data."""
    out = sanitise({"f": np.float64(0.25), "s": np.str_("x"), "nan": np.float64("nan")})
    assert type(out["f"]) is float
    assert type(out["s"]) is str
    assert out["nan"] is None


def test_sanitise_orders_sets_deterministically() -> None:
    """Set iteration order depends on PYTHONHASHSEED; results.json must not."""
    assert sanitise({"ids": {3, 1, 2}}) == {"ids": [1, 2, 3]}
    assert sanitise({"names": {"b", "a"}}) == {"names": ["a", "b"]}
    mixed = sanitise({"k": {1, "a"}})["k"]
    assert sorted(mixed, key=repr) == mixed  # comparable or not, still stable


def test_sanitise_rejects_unserialisable_objects() -> None:
    with pytest.raises(TypeError, match="cannot serialise"):
        sanitise({"model": object()})


def test_nan_metrics_survive_a_real_metric_result(tmp_path: Path) -> None:
    """The NaN path is not hypothetical: a fully ignored batch produces it.

    as_dict already maps per-class NaN to None, so absent classes alone never
    reach the sanitiser. A batch whose labels are all ignore_index leaves *no*
    class with support, and then the aggregates themselves are raw float NaN --
    which is what json.dumps would emit as a bare, unparseable ``NaN``.
    """
    from segmentary.engine.metrics import ConfusionMatrix

    cm = ConfusionMatrix(num_classes=3)
    cm.update(
        torch.zeros(1, 4, 4, dtype=torch.long),
        torch.full((1, 4, 4), 255, dtype=torch.long),
    )
    metrics = cm.compute().as_dict(["a", "b", "c"])
    assert math.isnan(metrics["miou"]) and math.isnan(metrics["macc"])

    path = tmp_path / "results.json"
    write_results(path, make_record(metrics=metrics))
    assert "NaN" not in path.read_text()

    loaded = load_results(path).metrics
    assert loaded["miou"] is None and loaded["macc"] is None
    assert loaded["per_class_iou"]["b"] is None
    assert loaded["support"] == {"a": 0, "b": 0, "c": 0}


def test_sanitise_refuses_to_merge_keys_that_collide_as_strings() -> None:
    with pytest.raises(ValueError, match="stringify"):
        sanitise({1: "int key", "1": "str key"})
    with pytest.raises(ValueError, match="stringify"):
        sanitise({"metrics": {True: 0.1, "True": 0.2}})


def test_to_dict_does_not_copy_tensors_it_only_reads() -> None:
    """A metrics tensor must not be deep-copied on every mid-run write."""
    tensor = torch.tensor([1.0, float("nan")])
    record = make_record(metrics={"iou": tensor})
    assert record.to_dict()["metrics"]["iou"] == [1.0, None]
    assert record.metrics["iou"] is tensor  # untouched, not replaced by a copy


# ---------------------------------------------------------------- atomic write


def test_atomic_write_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "results.json"
    write_results(path, make_record())
    write_results(path, make_record(notes="second write"))

    assert sorted(p.name for p in path.parent.iterdir()) == ["results.json"]


def test_written_file_is_readable_by_others(tmp_path: Path) -> None:
    """mkstemp defaults to 0600; a runs directory has to stay readable."""
    import stat

    path = tmp_path / "results.json"
    write_results(path, make_record())
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_failed_write_cleans_up_and_keeps_previous_file(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "results.json"
    write_results(path, make_record(notes="good"))

    def boom(src, dst):
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr("segmentary.utils.results.os.replace", boom)
    with pytest.raises(OSError):
        write_results(path, make_record(notes="interrupted"))

    assert [p.name for p in tmp_path.iterdir()] == ["results.json"]
    assert load_results(path).notes == "good"  # previous file intact, not truncated


def test_unserialisable_metrics_never_touch_the_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    write_results(path, make_record(notes="good"))
    with pytest.raises(TypeError):
        write_results(path, make_record(metrics={"bad": object()}))
    assert load_results(path).notes == "good"
    assert [p.name for p in tmp_path.iterdir()] == ["results.json"]


# ---------------------------------------------------------------- loading


def test_load_rejects_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    write_results(path, make_record())
    data = json.loads(path.read_text())
    data["mystery_column"] = 1
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="unknown keys"):
        load_results(path)


def test_load_rejects_missing_required_keys(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    write_results(path, make_record())
    data = json.loads(path.read_text())
    del data["config_hash"]
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="missing required keys"):
        load_results(path)


def test_load_missing_file_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_results(tmp_path / "absent.json")


# ---------------------------------------------------------------- provenance


def test_git_sha_is_plausible_in_this_repo() -> None:
    sha, dirty = git_sha(REPO_ROOT)
    assert isinstance(dirty, bool)
    # A fresh repo with no commits legitimately yields the pessimistic fallback.
    assert sha == "unknown" or re.fullmatch(r"[0-9a-f]{40}", sha)
    if sha == "unknown":
        assert dirty is True


def test_git_sha_on_a_non_repo_degrades_instead_of_raising(tmp_path: Path) -> None:
    assert git_sha(tmp_path) == ("unknown", True)
    assert git_sha(tmp_path / "does_not_exist") == ("unknown", True)


def test_discover_git_root_follows_a_nested_config_file(tmp_path: Path) -> None:
    import subprocess

    try:
        subprocess.run(
            ["git", "-C", str(tmp_path), "init", "-q"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git unavailable")
    config = tmp_path / "experiments" / "base.yaml"
    config.parent.mkdir()
    config.write_text("name: example\n", encoding="utf-8")

    assert discover_git_root([tmp_path / "missing", config]) == tmp_path.resolve()
    assert discover_git_root([tmp_path / "missing"]) is None


def test_git_sha_reports_dirty_with_uncommitted_changes(tmp_path: Path) -> None:
    import subprocess

    def run(*args):
        subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            check=True,
            capture_output=True,
            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        )

    try:
        run("init", "-q")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git unavailable")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (tmp_path / "a.txt").write_text("one")
    run("add", "a.txt")
    run("commit", "-qm", "first")

    sha, dirty = git_sha(tmp_path)
    assert re.fullmatch(r"[0-9a-f]{40}", sha)
    assert dirty is False

    (tmp_path / "a.txt").write_text("edited")
    sha_dirty, dirty = git_sha(tmp_path)
    assert sha_dirty == sha
    assert dirty is True


def test_collect_env_captures_versions() -> None:
    env = collect_env()
    assert env["torch"] == torch.__version__
    assert env["packages"]["transformers"] is not None
    assert env["packages"]["torch"] is not None
    assert "segmentary" in env["packages"]
    assert env["python"].startswith("3.11")
    for key in ("torch_cuda", "driver_version", "gpu_count", "gpu_names", "cuda_available"):
        assert key in env


def test_collect_env_is_json_serialisable(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    write_results(path, make_record(env=collect_env()))
    assert load_results(path).env["torch"] == torch.__version__


def test_peak_vram_keys_match_visible_devices() -> None:
    vram = peak_vram()
    if not torch.cuda.is_available():
        assert vram == {}
        return
    assert list(vram) == [f"cuda:{i}" for i in range(torch.cuda.device_count())]
    assert all(isinstance(v, int) and v >= 0 for v in vram.values())
    # Reserved, not allocated: allocated understates what the run needs to fit.
    for i, value in enumerate(vram.values()):
        assert value >= torch.cuda.max_memory_allocated(i)


# ---------------------------------------------------------------- timer


def test_run_timer_measures_and_stamps() -> None:
    record = make_record(finished_at=None, wall_clock_s=None)
    with RunTimer() as timer:
        assert timer.finished_at is None  # a crashed run is distinguishable
        assert timer.wall_clock_s >= 0.0  # readable mid-run
        sum(range(100_000))
    timer.stamp(record)

    assert record.finished_at is not None
    assert record.wall_clock_s > 0.0
    assert record.started_at <= record.finished_at
    assert record.peak_vram_bytes == peak_vram()


def test_run_timer_does_not_swallow_exceptions() -> None:
    timer = RunTimer()
    with pytest.raises(RuntimeError, match="training blew up"):
        with timer:
            raise RuntimeError("training blew up")
    assert timer.finished_at is not None  # still timed the partial run


def test_run_timer_rejects_use_before_entry() -> None:
    with pytest.raises(RuntimeError):
        _ = RunTimer().wall_clock_s
    with pytest.raises(RuntimeError):
        RunTimer().stamp(make_record())


# ---------------------------------------------------------------- seeding


def test_seed_everything_makes_randn_reproducible() -> None:
    seed_everything(1234)
    first = [torch.randn(4), torch.randn(4)]
    seed_everything(1234)
    second = [torch.randn(4), torch.randn(4)]

    assert torch.equal(first[0], second[0])
    assert torch.equal(first[1], second[1])
    assert not torch.equal(first[0], first[1])  # successive draws still differ


def test_seed_everything_seeds_python_and_numpy() -> None:
    import random

    seed_everything(7)
    first = (random.random(), np.random.rand())
    seed_everything(7)
    assert (random.random(), np.random.rand()) == first


def test_different_seeds_give_different_draws() -> None:
    seed_everything(1)
    a = torch.randn(8)
    seed_everything(2)
    assert not torch.equal(a, torch.randn(8))


def test_seed_everything_updates_lightning_global_seed_for_each_call(monkeypatch) -> None:
    monkeypatch.setenv("PL_GLOBAL_SEED", "stale")

    seed_everything(1)
    assert os.environ["PL_GLOBAL_SEED"] == "1"
    seed_everything(2)
    assert os.environ["PL_GLOBAL_SEED"] == "2"


@pytest.mark.parametrize("bad", [-1, 2**32, "42", 1.5, True, None])
def test_seed_everything_rejects_invalid_seeds(bad) -> None:
    previous = os.environ.get("PL_GLOBAL_SEED")
    with pytest.raises(ValueError):
        seed_everything(bad)
    assert os.environ.get("PL_GLOBAL_SEED") == previous


def test_worker_init_fn_gives_each_worker_a_distinct_stream() -> None:
    import random

    draws = []
    for worker_id in range(4):
        torch.manual_seed(999)  # DataLoader hands every worker the same base seed
        worker_init_fn(worker_id)
        draws.append((random.random(), float(np.random.rand())))

    assert len(set(draws)) == 4


def test_deterministic_mode_sets_the_flags_it_promises() -> None:
    """Run out-of-process: use_deterministic_algorithms is process-global state
    that would otherwise slow down and constrain every later test."""
    import subprocess
    import sys

    script = """
import os, torch
from segmentary.utils.seed import seed_everything
seed_everything(3, deterministic=True)
assert os.environ["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8"
assert torch.are_deterministic_algorithms_enabled()
assert torch.backends.cudnn.deterministic and not torch.backends.cudnn.benchmark
if torch.cuda.is_available():
    torch.randn(8, device="cuda")
    try:
        seed_everything(3, deterministic=True)
    except RuntimeError as exc:
        assert "before the first CUDA call" in str(exc)
    else:
        raise AssertionError("expected a refusal once cuBLAS is already initialised")
print("ok")
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def _augmentation_stream(seed: int, epochs: int) -> list[list[float]]:
    """Sums of augmented crops, per epoch, through a real 2-worker DataLoader."""
    from torch.utils.data import DataLoader, Dataset

    from segmentary.data.transforms import AugConfig, build_train_transform
    from segmentary.utils.seed import worker_init_fn as init_fn

    image = np.arange(128 * 128 * 3, dtype=np.uint8).reshape(128, 128, 3)
    mask = np.zeros((128, 128), np.uint8)

    class _Toy(Dataset):
        def __init__(self) -> None:
            self.transform = build_train_transform(AugConfig(crop=(64, 64)))

        def __len__(self) -> int:
            return 8

        def __getitem__(self, index: int):
            return self.transform(image=image, mask=mask)["image"].sum()

    seed_everything(seed)
    dataset = _Toy()
    generator = torch.Generator()
    generator.manual_seed(seed)
    loader = DataLoader(
        dataset,
        batch_size=1,
        num_workers=2,
        shuffle=False,
        worker_init_fn=init_fn,
        generator=generator,
    )
    return [[round(float(x), 3) for x in loader] for _ in range(epochs)]


def test_workers_do_not_all_replay_one_frozen_augmentation_stream() -> None:
    """albumentations 2.x owns its RNG; random.seed() alone cannot reach it.

    Without re-seeding the Compose inside each worker, all workers emit the same
    crop for their respective samples and every epoch is byte-identical -- the
    augmentation is silently switched off while the run still looks healthy.
    """
    epochs = _augmentation_stream(seed=0, epochs=2)

    assert epochs[0] != epochs[1], "augmentation frozen: epoch 2 repeats epoch 1"
    assert epochs[0][0] != epochs[0][1], "both workers drew the same crop"
    assert len(set(epochs[0])) == len(epochs[0])


def test_augmentation_stream_is_reproducible_from_the_seed() -> None:
    assert _augmentation_stream(seed=0, epochs=2) == _augmentation_stream(seed=0, epochs=2)
    assert _augmentation_stream(seed=0, epochs=1) != _augmentation_stream(seed=1, epochs=1)


def test_in_process_loading_is_also_reproducible(monkeypatch) -> None:
    """num_workers=0 never calls worker_init_fn, so build_train_loader has to
    seed the Compose itself or the augmentation stream ignores train.seed."""
    from torch.utils.data import Dataset

    from segmentary.config import AugConfigSpec, DataConfig, StageConfig, TrainConfig
    from segmentary.data import loaders

    image = np.arange(64 * 64 * 3, dtype=np.uint8).reshape(64, 64, 3)
    mask = np.zeros((64, 64), np.uint8)

    class _Toy(Dataset):
        def __init__(self, transform) -> None:
            self.transform = transform

        def __len__(self) -> int:
            return 4

        def __getitem__(self, index: int) -> dict:
            out = self.transform(image=image, mask=mask)
            return {
                "image": out["image"],
                "mask": out["mask"].long(),
                "active": torch.ones(3, dtype=torch.bool),
                "dataset": "toy",
                "key": str(index),
            }

    monkeypatch.setattr(loaders, "build_dataset", lambda d, s, r, split, tf: _Toy(tf))
    stage = StageConfig(name="s", data=[DataConfig(name="cityscapes", root="/nonexistent")])
    train = TrainConfig(num_workers=0, batch_size=1, seed=5)

    def stream() -> list[float]:
        seed_everything(train.seed)
        loader = loaders.build_train_loader(
            stage, None, "taxonomy", AugConfigSpec(crop=(32, 32)), train
        )
        return [round(float(b["image"].sum()), 3) for b in loader]

    first = stream()
    assert first == stream()
    assert len(set(first)) > 1  # different samples still get different crops


def test_seed_transforms_rejects_a_pipeline_it_cannot_seed() -> None:
    from segmentary.utils.seed import seed_transforms

    class _Fake:
        transform = object()

    with pytest.raises(TypeError, match="set_random_seed"):
        seed_transforms(_Fake(), 0)


def test_worker_init_fn_is_reproducible_across_epochs() -> None:
    import random

    def stream(worker_id: int):
        torch.manual_seed(999)
        worker_init_fn(worker_id)
        return random.random(), float(np.random.rand())

    assert stream(2) == stream(2)
