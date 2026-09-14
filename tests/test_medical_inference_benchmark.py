"""Standalone benchmark protocol math and contention checks need no GPU."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).parents[1] / "scripts/benchmark_medical_inference.py"
SPEC = importlib.util.spec_from_file_location("medical_inference_benchmark", PATH)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_latency_summary_reports_interpolated_p95_and_preserves_units():
    samples = [50.0, 10.0, 30.0, 20.0, 40.0]
    assert benchmark.summarize_latency(samples) == {
        "mean": 30.0,
        "p50": 30.0,
        "p95": 48.0,
        "min": 10.0,
        "max": 50.0,
    }
    assert samples == [50.0, 10.0, 30.0, 20.0, 40.0]
    assert benchmark.summarize_latency([5.0])["p95"] == 5.0


@pytest.mark.parametrize("samples", [[], [0.0], [-1.0], [float("nan")], [float("inf")]])
def test_invalid_cuda_event_measurements_fail(samples):
    with pytest.raises(ValueError, match="finite and positive"):
        benchmark.summarize_latency(samples)


def test_gpu_uuid_mapping_detects_only_selected_physical_device_occupants():
    inventory = "0, GPU-a\n1, GPU-b\n2, GPU-c\n"
    processes = "GPU-b, 101\nGPU-c, 202\nGPU-b, 303\n"
    assert benchmark.occupied_gpu_processes("1", inventory, processes) == [101, 303]
    assert benchmark.occupied_gpu_processes("0", inventory, processes) == []
    assert benchmark.occupied_gpu_processes("2", inventory, "") == []


@pytest.mark.parametrize(
    "inventory,processes",
    [("N/A", ""), ("0, GPU-a", "N/A"), ("0, GPU-a", "GPU-a, N/A"), ("0, PCI-a", "")],
)
def test_unknown_gpu_telemetry_fails_closed(inventory, processes):
    with pytest.raises(ValueError, match="Malformed"):
        benchmark.occupied_gpu_processes("0", inventory, processes)


def test_missing_gpu_is_not_treated_as_idle():
    with pytest.raises(ValueError, match="absent"):
        benchmark.occupied_gpu_processes("8", "0, GPU-a", "")


def test_idle_check_rejects_existing_cuda_process(monkeypatch):
    outputs = iter(["0, GPU-a\n", "GPU-a, 4242\n"])
    monkeypatch.setattr(benchmark.subprocess, "check_output", lambda *_a, **_k: next(outputs))
    with pytest.raises(RuntimeError, match="active CUDA"):
        benchmark.check_idle("0")


def test_selection_excludes_separate_nnunet_protocol_and_validates_ids():
    spec = {
        "runs": [
            {"id": "nn", "backend": "nnunet"},
            {"id": "a", "backend": "torch"},
            {"id": "b", "backend": "torch"},
        ]
    }
    assert [run["id"] for run in benchmark.select_runs(spec, [])] == ["a", "b"]
    assert [run["id"] for run in benchmark.select_runs(spec, ["b"])] == ["b"]
    for selection in (["missing"], ["nn"], ["a", "a"]):
        with pytest.raises(ValueError):
            benchmark.select_runs(spec, selection)


def test_existing_stage_lock_prevents_benchmark(tmp_path):
    import fcntl

    path = tmp_path / ".stage.lock"
    path.touch()
    with path.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="active stage"):
            with benchmark.quiescent_workspace(tmp_path):
                pytest.fail("Benchmark entered an active workspace")


def test_quiescence_check_never_creates_a_missing_stage_lock(tmp_path):
    with pytest.raises(ValueError, match="existing stage lock"):
        with benchmark.quiescent_workspace(tmp_path):
            pytest.fail("No audited workspace exists")
    assert list(tmp_path.iterdir()) == []


def test_unfinished_stage_record_is_not_assumed_safe(tmp_path):
    (tmp_path / ".stage.lock").touch()
    (tmp_path / "active-stage.json").write_text('{"status":"running"}')
    with pytest.raises(RuntimeError, match="unfinished stage"):
        with benchmark.quiescent_workspace(tmp_path):
            pytest.fail("An active record needs reconciliation first")


def test_executing_runtime_must_match_full_recorded_package_inventory(tmp_path):
    expected = {
        "python": "version",
        "executable": str(tmp_path / "python"),
        "packages": {"torch": "pinned"},
    }
    benchmark.check_runtime(expected, expected)
    with pytest.raises(ValueError, match="recorded Python/package"):
        benchmark.check_runtime(expected, {**expected, "packages": {"torch": "different"}})


def test_new_source_uses_exact_bytes_bound_backend_loader():
    calls = []
    config = object()

    def load(cfg, alias):
        calls.append((cfg, alias))
        return {"state": "verified"}, "digest"

    assert benchmark.load_verified_checkpoint(SimpleNamespace(_load_checkpoint=load), config) == (
        {"state": "verified"},
        "digest",
    )
    assert calls == [(config, "checkpoint_best.pth")]


def test_legacy_source_fallback_deserializes_the_hashed_buffer(tmp_path, monkeypatch):
    import io

    import torch

    checkpoint = tmp_path / "generation-best.pth"
    torch.save({"model": torch.ones(2)}, checkpoint)
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    (tmp_path / "checkpoint-index.json").write_text(
        json.dumps({"files": {"checkpoint_best.pth": {"path": checkpoint.name, "sha256": digest}}})
    )
    original = torch.load

    def verify_buffer(source, **kwargs):
        assert isinstance(source, io.BytesIO)
        assert hashlib.sha256(source.getvalue()).hexdigest() == digest
        return original(source, **kwargs)

    monkeypatch.setattr(torch, "load", verify_buffer)
    state, actual = benchmark.load_verified_checkpoint(
        SimpleNamespace(_checkpoint=lambda *_: checkpoint), SimpleNamespace(root=tmp_path)
    )
    assert actual == digest
    torch.testing.assert_close(state["model"], torch.ones(2))
