"""The declared primary checkpoint aligns quality, diagnostic matching and profiling."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import collect_rtis_statistics as collector
from scripts import profile_rtis_campaign as profiler
from scripts import run_rtis_campaign as runtime
from scripts.run_rtis_full_campaign import validate_collection

from helpers_gpu_policy import write_campaign


@pytest.mark.parametrize("primary", [None, "best", "final"])
def test_run_job_standalone_eval_uses_primary_checkpoint(tmp_path, monkeypatch, primary):
    campaign = write_campaign(tmp_path, jobs=["job"], collection_contract="full-statistics")
    if primary is not None:
        campaign["primary_checkpoint"] = primary
    data = tmp_path / "data"
    data.mkdir()
    (data / "splits.json").write_text("split")
    campaign.update(split_sha256=runtime.digest(data / "splits.json"), target_steps=4000)
    config = tmp_path / "job.yaml"
    config.write_text("config")
    job = {
        "name": "job",
        "config": str(config),
        "config_sha256": runtime.digest(config),
        "source_checkpoint": None,
    }
    cfg = SimpleNamespace(
        stages=[SimpleNamespace(data=[SimpleNamespace(root=str(data))])],
        output_root=str(tmp_path / "future-runs"),
        name="job",
        train=SimpleNamespace(seed=0),
    )
    run = tmp_path / "future-runs/job_seed0/rtis"
    run.mkdir(parents=True)
    for name in ["last.ckpt", "best.ckpt"]:
        (run / name).write_text(name)
    runtime.write(run / "results.json", {"metrics": {"miou": 0.4}})
    monkeypatch.setitem(
        sys.modules, "segmentary.config", SimpleNamespace(load_experiment=lambda layers: cfg)
    )
    monkeypatch.setitem(
        sys.modules,
        "segmentary.utils.resource_tracking",
        SimpleNamespace(run_recorded=lambda *a, **k: None),
    )
    monkeypatch.setattr(runtime, "learning_curve", lambda path: {})
    monkeypatch.setattr(
        runtime,
        "checkpoint_info",
        lambda path: {
            "path": str(path),
            "sha256": runtime.digest(path),
            "global_step": 4000 if path.name == "last.ckpt" else 2000,
        },
    )
    commands = []

    def fake_eval(command, **kwargs):
        commands.append(command)
        output = Path(command[command.index("--out") + 1])
        ckpt = command[command.index("--ckpt") + 1]
        runtime.write(output, {"metrics": {"miou": 0.5}, "checkpoint_path": ckpt})

    monkeypatch.setattr(runtime.subprocess, "run", fake_eval)
    runtime.run_job(tmp_path, tmp_path, job, 2, campaign)
    anchor = primary or "best"
    expected = run / ("last.ckpt" if anchor == "final" else "best.ckpt")
    assert commands[0][commands[0].index("--ckpt") + 1] == str(expected)
    assert commands[0][commands[0].index("--out") + 1] == str(run / f"{anchor}-val.json")
    state = runtime.read(tmp_path / "state/job.json")
    assert state["evaluation_checkpoint"] == anchor
    assert state["evaluation"]["checkpoint_path"] == str(expected)


@pytest.mark.parametrize("primary", [None, "final"])
def test_profiler_uses_same_primary_checkpoint_and_result(tmp_path, monkeypatch, primary):
    from segmentary import performance

    campaign = {"code_sha": "code"}
    if primary:
        campaign["primary_checkpoint"] = primary
    runtime.write(tmp_path / "campaign.json", campaign)
    runtime.write(
        tmp_path / "plan.json",
        {"jobs": [{"name": "job", "config": "config.yaml", "model": "model", "seed": 0}]},
    )
    checkpoints = {}
    for anchor, name, step in [("best", "best.ckpt", 100), ("final", "last.ckpt", 4000)]:
        path = tmp_path / name
        path.write_text(name)
        checkpoints[anchor] = {
            "path": str(path),
            "sha256": runtime.digest(path),
            "global_step": step,
        }
    runtime.write(
        tmp_path / "state/job.json",
        {"checkpoints": checkpoints, "evaluation": {"git_sha": "eval-code", "stage": "rtis"}},
    )
    monkeypatch.setattr(profiler.gpu_policy, "enforce_from_env", lambda **kwargs: None)
    seen = []

    def benchmark(args):
        seen.append(args)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("pending")
        return {"source": {"checkpoint_sha256": runtime.digest(args.ckpt)}}

    monkeypatch.setattr(performance, "run_benchmark", benchmark)
    profiler.measure(tmp_path, "job")
    anchor = primary or "best"
    assert seen[0].ckpt == Path(checkpoints[anchor]["path"])
    assert seen[0].result == tmp_path / f"{anchor}-val.json"
    assert seen[0].checkpoint_global_step == checkpoints[anchor]["global_step"]
    stored = runtime.read(tmp_path / "performance/job.json")
    assert stored["primary_checkpoint"] == anchor
    assert stored["source"]["checkpoint_sha256"] == checkpoints[anchor]["sha256"]


@pytest.mark.parametrize("primary", [None, "final"])
def test_collector_matches_standalone_primary_matrix(tmp_path, monkeypatch, primary):
    # Best and final deliberately disagree, so matching the wrong reference fails.
    campaign = {} if primary is None else {"primary_checkpoint": primary}
    best = {"path": str(tmp_path / "best.ckpt"), "sha256": "best"}
    final = {"path": str(tmp_path / "last.ckpt"), "sha256": "final"}
    anchor = primary or "best"
    reference = 2 if anchor == "best" else 3
    state = {
        "checkpoints": {"best": best, "final": final},
        "evaluation": {"metrics": {"confusion": [[reference]]}},
    }
    runtime.write(tmp_path / "campaign.json", campaign)
    runtime.write(tmp_path / "state/job.json", state)
    runtime.write(tmp_path / "plan.json", {"jobs": [{"name": "job", "config": "unused"}]})
    cfg = SimpleNamespace(model=None, train=SimpleNamespace(seed=0), taxonomy_root=None, space=None)
    monkeypatch.setattr(sys, "argv", ["collector", "--campaign", str(tmp_path), "--job", "job"])
    monkeypatch.setattr(collector, "load_experiment", lambda *a: cfg)
    monkeypatch.setattr(
        collector, "load_space", lambda *a: SimpleNamespace(names=["class"], num_classes=1)
    )
    monkeypatch.setattr(
        collector, "validate_dataset", lambda *a: ({"train": ["a"], "val": ["b"]}, [])
    )
    monkeypatch.setattr(
        collector.runtime, "digest", lambda p: "best" if Path(p).name == "best.ckpt" else "final"
    )
    monkeypatch.setattr(collector, "seed_everything", lambda *a, **k: None)
    monkeypatch.setattr(collector, "ema_evaluation_safe", lambda *a: True)

    class Model:
        anchor = ""

        def cuda(self):
            return self

        def eval(self):
            return self

    monkeypatch.setattr(collector, "build_model", lambda *a: Model())

    def load(model, cfg, path, use_ema):
        model.anchor = "best" if path.name == "best.ckpt" else "final"
        return model

    monkeypatch.setattr(collector, "load_configured_checkpoint", load)
    monkeypatch.setattr(
        collector,
        "collect",
        lambda model, *a: {
            "images": 1,
            "metrics": {"confusion": [[2 if model.anchor == "best" else 3]]},
        },
    )
    collector.main()
    summary = runtime.read(tmp_path / "diagnostics/summary.json")
    assert summary["primary_checkpoint"] == anchor
    assert summary["standalone_variant"] == f"{anchor}-auto-val"
    assert summary["standalone_confusion_exact_match"] is True
    assert set(summary["results"]) == {
        "best-auto-train",
        "best-auto-val",
        "best-alternate-val",
        "final-auto-val",
    }
    assert summary["test_evaluated"] is False


def test_collection_validation_requires_primary_profile_hash():
    state = {"checkpoints": {"best": {"sha256": "best"}, "final": {"sha256": "final"}}}
    diagnostics = {
        "test_evaluated": False,
        "standalone_confusion_exact_match": True,
        "results": {
            k: {}
            for k in ["best-auto-train", "best-auto-val", "best-alternate-val", "final-auto-val"]
        },
    }
    performance = {
        "status": "complete",
        "source": {"checkpoint_sha256": "final"},
        "model": {"parameter_count": 1},
        "measurements": {"latency": {"fps": 1}, "peak_reserved_bytes": 1},
    }
    attempts = [
        {"phase": p, "status": "completed", "wall_clock_s": 1}
        for p in ["training", "diagnostics", "performance"]
    ]
    validate_collection(state, diagnostics, performance, attempts, primary_checkpoint="final")
    with pytest.raises(RuntimeError, match="primary checkpoint"):
        validate_collection(state, diagnostics, performance, attempts)
    performance["source"]["checkpoint_sha256"] = "best"
    validate_collection(state, diagnostics, performance, attempts)
    with pytest.raises(RuntimeError, match="primary checkpoint"):
        validate_collection(state, diagnostics, performance, attempts, primary_checkpoint="final")
