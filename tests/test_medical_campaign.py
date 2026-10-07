"""Durable campaign scheduling preserves patient split and scratch-run identity."""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_medical_campaign.py"
SPEC = importlib.util.spec_from_file_location("run_medical_campaign", SCRIPT)
assert SPEC and SPEC.loader
campaign = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(campaign)


@pytest.fixture
def spec_path(tmp_path, monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    for name in ("manifest", "splits"):
        campaign.write_json(tmp_path / f"{name}.json", {"fingerprint": name, "val": ["case-1"]})
    runs = []
    for index in range(7):
        config = tmp_path / f"recipe-{index}.json"
        campaign.write_json(
            config,
            {
                "backend": "torch",
                "model": "unet_3d",
                "gpu": "9",
                "workspace": str(tmp_path / "workspaces" / str(index)),
                "backend_python": sys.executable,
                "initialization": "scratch",
                "weight_decay": 1e-5,
            },
        )
        runs.append({"id": f"run-{index}", "config": str(config), "comparison_group": "common"})
    path = tmp_path / "campaign.json"
    campaign.write_json(
        path,
        {
            "schema_version": 1,
            "campaign_id": "pancreas-test",
            "source_root": str(tmp_path),
            "source_commit": "a" * 40,
            "python": sys.executable,
            "manifest": str(tmp_path / "manifest.json"),
            "splits": str(tmp_path / "splits.json"),
            "gpus": ["2", "3", "4"],
            "runs": runs,
            "evaluation": {"bootstrap_samples": 100, "seed": 0, "surface_tolerance_mm": 2.0},
        },
    )
    return path


class FakeCampaign(campaign.Campaign):
    """Simulate expensive stage processes, retaining actual durable artifacts."""

    def __init__(self, *args, fail=None, **kwargs):
        super().__init__(*args, source_check=lambda _spec: None, **kwargs)
        self.fail = fail
        self.calls = []
        self.active = Counter()
        self.peak = Counter()
        self.concurrent_peak = 0
        self.verified = []

    def verify(self, state, stage):
        self.verified.append((state["id"], stage))

    def execute(self, state, stage, argv):
        self.save(state, stage=stage, argv=argv)
        with self.mutex:
            self.calls.append((state["id"], stage, list(argv)))
            self.active[state["gpu"]] += 1
            self.peak[state["gpu"]] = max(self.peak[state["gpu"]], self.active[state["gpu"]])
            self.concurrent_peak = max(self.concurrent_peak, sum(self.active.values()))
        try:
            time.sleep(0.01)
            root = Path(state["workspace"])
            if stage == "prepare":
                campaign.write_json(root / "binding.json", {"identity": state["id"]})
            elif stage == "preprocess":
                campaign.write_json(root / "plan-binding.json", {"identity": state["id"]})
            elif stage == "train":
                campaign.write_json(root / "checkpoint-index.json", {"epoch": 1})
                if self.fail == (state["id"], stage):
                    raise RuntimeError("Training interrupted after a committed checkpoint")
                campaign.write_json(root / "training-result.json", {"completed": True})
                campaign.write_json(root / "scratch-origin.json", {"external_weight_loads": 0})
            elif stage == "predict":
                predictions = root / "predictions" / "val"
                campaign.write_json(
                    predictions / "prediction-status.json",
                    {
                        "partition": "val",
                        "checkpoint_sha256": "checkpoint-digest",
                    },
                )
                (predictions / "case-1.nii.gz").write_bytes(b"native prediction")
            elif stage == "evaluate":
                output = Path(state["evaluation"])
                campaign.write_json(
                    output / "report.json",
                    {
                        "cases": [{"case_id": "case-1", "status": "ok"}],
                        "manifest_fingerprint": "manifest",
                        "coverage": {"valid_prediction_cases": 1},
                    },
                )
                (output / "cases.csv").write_text("case_id,status\ncase-1,ok\n")
            if self.fail == (state["id"], stage):
                raise RuntimeError("Deliberate stage failure")
            return {}
        finally:
            with self.mutex:
                self.active[state["gpu"]] -= 1


def test_queue_uses_each_gpu_without_double_assigning_and_never_scores_test(spec_path, tmp_path):
    runner = FakeCampaign(spec_path, tmp_path / "state")
    assert runner.run() == 0
    assert runner.concurrent_peak == 3
    assert runner.peak == {"2": 1, "3": 1, "4": 1}
    assert len(runner.calls) == 7 * 5
    for state in runner.states.values():
        assert state["status"] == "completed"
        assert state["selected_checkpoint_sha256"] == "checkpoint-digest"
        resolved = campaign.read_json(Path(state["config"]))
        assert resolved["gpu"] == state["gpu"]
        assert resolved["weight_decay"] == 1e-5
        assert campaign.sha256(Path(state["config"])) == state["config_sha256"]
    for _, stage, argv in runner.calls:
        assert "--final-test" not in argv
        if stage in {"predict", "evaluate"}:
            assert argv[argv.index("--partition") + 1] == "val"
    assert campaign.read_json(tmp_path / "state/status.json")["status"] == "completed"


def test_dashboard_starts_after_validated_state_and_failure_does_not_stop_training(
    spec_path, tmp_path, monkeypatch
):
    calls = []

    def ensure(root, repo, python):
        assert (root / "campaign-binding.json").is_file()
        assert len(campaign.read_json(root / "status.json")["runs"]) == 7
        calls.append(root)
        return None  # A missing tmux/UI does not change the campaign result.

    monkeypatch.setattr("segmentary.campaign_dashboard.ensure_dashboard", ensure)
    runner = FakeCampaign(spec_path, tmp_path / "state")
    assert runner.run(dashboard=True) == 0
    assert calls == [tmp_path / "state"]


@pytest.mark.parametrize("opt_out", [False, True])
def test_cli_auto_dashboard_and_explicit_opt_out(spec_path, tmp_path, monkeypatch, opt_out):
    flags = []

    def run(self, *, dashboard=False):
        flags.append(dashboard)
        return 0

    monkeypatch.setattr(campaign.Campaign, "run", run)
    arguments = ["--spec", str(spec_path), "--state-dir", str(tmp_path / "state")]
    if opt_out:
        arguments.append("--no-dashboard")
    assert campaign.main(arguments) == 0
    assert flags == [not opt_out]


def test_failure_does_not_cancel_other_models_or_retry_without_explicit_flag(spec_path, tmp_path):
    first = FakeCampaign(spec_path, tmp_path / "state", fail=("run-0", "train"))
    assert first.run() == 1
    assert first.states["run-0"]["status"] == "failed"
    assert sum(s["status"] == "completed" for s in first.states.values()) == 6
    assigned = first.states["run-0"]["gpu"]
    frozen_config = Path(first.states["run-0"]["config"]).read_bytes()

    second = FakeCampaign(spec_path, tmp_path / "state")
    assert second.run() == 1
    assert not second.calls
    assert len(second.verified) == 6
    assert second.states["run-0"]["attempts"] == 1

    retry = FakeCampaign(spec_path, tmp_path / "state", retry_failed=True)
    assert retry.run() == 0
    assert [(name, stage) for name, stage, _ in retry.calls] == [
        ("run-0", "train"),
        ("run-0", "predict"),
        ("run-0", "evaluate"),
    ]
    assert "resume" in retry.calls[0][2]
    assert retry.states["run-0"]["gpu"] == assigned
    assert Path(retry.states["run-0"]["config"]).read_bytes() == frozen_config


def test_prepare_only_then_normal_run_reuses_bound_preparation(spec_path, tmp_path):
    first = FakeCampaign(spec_path, tmp_path / "state", prepare_only=True)
    assert first.run() == 0
    assert all(s["status"] == "prepared" for s in first.states.values())
    assert {stage for _, stage, _ in first.calls} == {"prepare", "preprocess"}
    assignments = {name: state["gpu"] for name, state in first.states.items()}
    second = FakeCampaign(spec_path, tmp_path / "state")
    assert second.run() == 0
    assert {stage for _, stage, _ in second.calls} == {"train", "predict", "evaluate"}
    assert {name: state["gpu"] for name, state in second.states.items()} == assignments


def test_completed_artifact_changes_fail_instead_of_silently_reusing(spec_path, tmp_path):
    first = FakeCampaign(spec_path, tmp_path / "state")
    assert first.run() == 0
    report = Path(first.states["run-0"]["evaluation"]) / "report.json"
    report.write_text('{"invented_score": 1.0}')
    second = FakeCampaign(spec_path, tmp_path / "state")
    assert second.run() == 1
    assert not second.calls
    assert "artifact changed" in second.states["run-0"]["error"]
    assert report.read_text() == '{"invented_score": 1.0}'


def test_recipe_mutation_and_resolved_config_mutation_are_rejected(spec_path, tmp_path):
    first = FakeCampaign(spec_path, tmp_path / "state", prepare_only=True)
    assert first.run() == 0
    recipe = Path(first.spec["runs"][0]["config"])
    old = recipe.read_bytes()
    recipe.write_text(recipe.read_text().replace('"9"', '"8"'))
    with pytest.raises(ValueError, match="changed"):
        FakeCampaign(spec_path, tmp_path / "state").run()
    recipe.write_bytes(old)
    resolved = Path(first.states["run-0"]["config"])
    resolved.write_text(resolved.read_text().replace('"gpu": "2"', '"gpu": "9"'))
    with pytest.raises(ValueError, match="configuration was modified"):
        FakeCampaign(spec_path, tmp_path / "state").run()


def test_running_orphan_stage_blocks_a_duplicate(spec_path, tmp_path):
    first = FakeCampaign(spec_path, tmp_path / "state", prepare_only=True)
    assert first.run() == 0
    state_path = tmp_path / "state/runs/run-0.json"
    state = campaign.read_json(state_path)
    state.update(
        status="running", cli_pid=os.getpid(), cli_process_start=campaign.process_start(os.getpid())
    )
    campaign.write_json(state_path, state)
    with pytest.raises(RuntimeError, match="live stage process"):
        FakeCampaign(spec_path, tmp_path / "state").run()


def test_singleton_prevents_second_controller(spec_path, tmp_path):
    with campaign.singleton(tmp_path / "state/.campaign.lock"):
        with pytest.raises(RuntimeError, match="Another campaign"):
            FakeCampaign(spec_path, tmp_path / "state").run()


@pytest.mark.parametrize(
    "edit",
    [
        lambda spec: spec["evaluation"].update(partition="test"),
        lambda spec: spec.update(gpus=["2", "2"]),
        lambda spec: spec["runs"][1].update(id="run-0"),
        lambda spec: spec["runs"][0].update(id="../unsafe"),
        lambda spec: spec.update(source_commit="main"),
    ],
)
def test_invalid_or_test_access_specs_fail(spec_path, edit):
    spec = campaign.read_json(spec_path)
    edit(spec)
    campaign.write_json(spec_path, spec)
    with pytest.raises(ValueError):
        campaign.load_spec(spec_path)


def test_inherited_cuda_scope_is_not_broadened(spec_path, monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2")
    with pytest.raises(ValueError, match="exceed inherited"):
        campaign.load_spec(spec_path)


def test_stderr_failure_and_json_parsing_are_observable(tmp_path, spec_path):
    runner = FakeCampaign(spec_path, tmp_path / "state")
    runner.initialize()
    runner.claimed = set()
    state = runner.claim("2")
    assert state is not None
    result = campaign.Campaign.execute(
        runner,
        state,
        "unit-stage",
        [
            sys.executable,
            "-c",
            "print('optional warning'); print('{\"complete\": true}')",
        ],
    )
    assert result == {"complete": True}
    assert state["cli_pid"] is None
    with pytest.raises(RuntimeError, match="deliberate subprocess error"):
        campaign.Campaign.execute(
            runner,
            state,
            "unit-stage",
            [
                sys.executable,
                "-c",
                "import sys; print('deliberate subprocess error'); sys.exit(3)",
            ],
        )
    assert state["returncode"] == 3
    assert Path(state["log"]).is_file()


def test_dead_stage_restart_keeps_original_gpu(spec_path, tmp_path):
    first = FakeCampaign(spec_path, tmp_path / "state", prepare_only=True)
    assert first.run() == 0
    state_path = tmp_path / "state/runs/run-0.json"
    state = campaign.read_json(state_path)
    state.update(status="running", cli_pid=None)
    assigned = state["gpu"]
    campaign.write_json(state_path, state)
    second = FakeCampaign(spec_path, tmp_path / "state")
    assert second.run() == 0
    assert second.states["run-0"]["gpu"] == assigned
    assert ("run-0", "preprocess") in second.verified


def test_successful_cli_with_failed_validation_cases_is_not_completed(spec_path, tmp_path):
    class IncompleteEvaluation(FakeCampaign):
        def execute(self, state, stage, argv):
            result = super().execute(state, stage, argv)
            if stage == "evaluate" and state["id"] == "run-0":
                path = Path(state["evaluation"]) / "report.json"
                report = campaign.read_json(path)
                report["cases"][0]["status"] = "failed_prediction"
                report["coverage"]["valid_prediction_cases"] = 0
                campaign.write_json(path, report)
            return result

    runner = IncompleteEvaluation(spec_path, tmp_path / "state")
    assert runner.run() == 1
    assert runner.states["run-0"]["status"] == "failed"
    assert "failed, missing, or unexpected cases" in runner.states["run-0"]["error"]
    assert "evaluate" in runner.states["run-0"]["completed_stages"]
    assert sum(state["status"] == "completed" for state in runner.states.values()) == 6


def test_controller_stop_terminates_stage_and_preserves_restartable_state(spec_path, tmp_path):
    runner = FakeCampaign(spec_path, tmp_path / "state")
    runner.initialize()
    runner.claimed = set()
    state = runner.claim("2")
    assert state is not None
    timer = threading.Timer(0.15, runner.stop_workers)
    timer.start()
    try:
        with pytest.raises(InterruptedError, match="last committed epoch"):
            campaign.Campaign.execute(
                runner,
                state,
                "train",
                [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(10)",
                ],
            )
    finally:
        timer.cancel()
        timer.join()
    assert state["cli_pid"] is None
    assert state["returncode"] != 0


def test_config_changed_after_assignment_is_rejected_before_stage(spec_path, tmp_path):
    runner = FakeCampaign(spec_path, tmp_path / "state")
    runner.initialize()
    runner.claimed = set()
    state = runner.claim("2")
    assert state is not None
    config = Path(state["config"])
    config.write_text(config.read_text().replace("1e-05", "0.1"))
    with pytest.raises(ValueError, match="configuration changed during"):
        campaign.Campaign.execute(runner, state, "train", [sys.executable, "-c", "print('{}')"])
    assert not runner.processes


def test_completed_scratch_continuation_reuses_training_and_executes_prediction(
    spec_path, tmp_path
):
    spec = campaign.read_json(spec_path)
    spec["runs"] = spec["runs"][:1]
    campaign.write_json(spec_path, spec)
    root = Path(campaign.read_json(Path(spec["runs"][0]["config"]))["workspace"])
    campaign.write_json(root / "binding.json", {"identity": "continued"})
    campaign.write_json(root / "continuation.json", {"action": "predict"})
    campaign.write_json(root / "training-result.json", {"completed": True})
    campaign.write_json(root / "checkpoint-index.json", {"epoch": 100})
    campaign.write_json(root / "scratch-origin.json", {"external_weight_loads": 0})
    runner = FakeCampaign(spec_path, tmp_path / "state")
    assert runner.run() == 0
    stages = [stage for _, stage, _ in runner.calls]
    assert "train" not in stages
    assert stages == ["preprocess", "predict", "evaluate"]
    assert ("run-0", "train") in runner.verified
    assert runner.states["run-0"]["completed_stages"]["train"]["recovered"]


class FakeNNUNetCampaign(FakeCampaign):
    """nnU-Net stages return the backend's prediction directory and record."""

    def execute(self, state, stage, argv):
        if stage not in {"predict", "predict_best", "evaluate_best"}:
            return super().execute(state, stage, argv)
        self.save(state, stage=stage, argv=argv)
        with self.mutex:
            self.calls.append((state["id"], stage, list(argv)))
        if stage == "evaluate_best":
            output = Path(state["secondary"]["evaluation"])
            campaign.write_json(
                output / "report.json",
                {
                    "cases": [{"case_id": "case-1", "status": "ok"}],
                    "manifest_fingerprint": "manifest",
                    "coverage": {"valid_prediction_cases": 1},
                },
            )
            (output / "cases.csv").write_text("case_id,status\ncase-1,ok\n")
            return {}
        checkpoint = argv[argv.index("--checkpoint") + 1]
        output = Path(state["workspace"]) / "predictions" / f"val-{stage}"
        campaign.write_json(
            output / "prediction-record.json",
            {"checkpoint": checkpoint, "checkpoint_sha256": f"{checkpoint}-digest"},
        )
        (output / "case-1.nii.gz").write_bytes(checkpoint.encode())
        return {"output": str(output)}


@pytest.fixture
def nnunet_spec(spec_path, tmp_path):
    cv = tmp_path / "cv.json"
    campaign.write_json(cv, {"folds": [{"val": ["case-1"]}, {"val": ["case-1"]}]})
    spec = campaign.read_json(spec_path)
    spec["gpus"] = ["2", "3", "4"]
    spec["runs"] = spec["runs"][:3]
    for index, run in enumerate(spec["runs"]):
        recipe = campaign.read_json(Path(run["config"]))
        recipe.update(
            backend="nnunet",
            resenc="L",
            fold=index % 2,
            cv_splits=str(cv),
            cv_splits_sha256=campaign.sha256(cv),
        )
        recipe.pop("model")
        campaign.write_json(Path(run["config"]), recipe)
        run["gpu"] = ["4", "2", "3"][index]
    campaign.write_json(spec_path, spec)
    return spec_path


def test_nnunet_scores_final_then_labelled_best_on_its_cv_fold(nnunet_spec, tmp_path):
    runner = FakeNNUNetCampaign(nnunet_spec, tmp_path / "state")
    assert runner.run() == 0
    assert {name: state["gpu"] for name, state in runner.states.items()} == {
        "run-0": "4",
        "run-1": "2",
        "run-2": "3",
    }
    for name, state in runner.states.items():
        stages = [stage for run, stage, _ in runner.calls if run == name]
        assert stages == [
            "prepare",
            "preprocess",
            "train",
            "predict",
            "evaluate",
            "predict_best",
            "evaluate_best",
        ]
        argv = {stage: args for run, stage, args in runner.calls if run == name}
        assert argv["predict"][argv["predict"].index("--checkpoint") + 1] == "checkpoint_final.pth"
        assert argv["predict_best"][1:4] == ["-m", "segmentary.medical.cli", "predict"]
        assert "checkpoint_best.pth" in argv["predict_best"]
        fold = str(int(name[-1]) % 2)
        assert argv["evaluate"][argv["evaluate"].index("--fold") + 1] == fold
        assert "--cv-splits" in argv["evaluate"]
        for stage in ("evaluate", "evaluate_best"):
            sha = argv[stage][argv[stage].index("--cv-splits-sha256") + 1]
            assert sha == campaign.sha256(tmp_path / "cv.json")
        assert state["checkpoint"] == "checkpoint_final.pth"
        assert state["checkpoint_policy"].startswith("terminal")
        assert state["selected_checkpoint_sha256"] == "checkpoint_final.pth-digest"
        secondary = state["secondary"]
        assert secondary["checkpoint"] == "checkpoint_best.pth"
        assert secondary["checkpoint_sha256"] == "checkpoint_best.pth-digest"
        assert "optimistic" in secondary["label"]
        assert Path(secondary["evaluation"]).parent.name == "evaluations-checkpoint-best"
        assert Path(state["evaluation"]).parent.name == "evaluations"
        assert set(state["completed_stages"]) == set(campaign.STAGES)


def test_changed_cv_manifest_stops_the_campaign_before_any_stage(nnunet_spec, tmp_path):
    cv = tmp_path / "cv.json"
    cv.write_text(cv.read_text() + " ")
    runner = FakeNNUNetCampaign(nnunet_spec, tmp_path / "state")
    with pytest.raises(ValueError, match="Cross-validation manifest changed"):
        runner.run()
    assert runner.calls == []


def test_validation_cases_refuse_a_changed_cv_manifest(nnunet_spec, tmp_path):
    runner = FakeNNUNetCampaign(nnunet_spec, tmp_path / "state")
    assert runner.run() == 0
    state = runner.states["run-1"]
    assert runner.validation_cases(state) == ["case-1"]
    cv = tmp_path / "cv.json"
    cv.write_text(cv.read_text() + " ")
    with pytest.raises(ValueError, match="Cross-validation manifest changed"):
        runner.validation_cases(state)


def test_interrupted_evaluations_are_set_aside_and_rerun(nnunet_spec, tmp_path):
    state_dir = tmp_path / "state"
    partial = {
        folder: state_dir / folder / "run-0"
        for folder in ("evaluations", "evaluations-checkpoint-best")
    }
    for path in partial.values():
        path.mkdir(parents=True)
        (path / "report.json.tmp").write_text("partial")
    runner = FakeNNUNetCampaign(nnunet_spec, state_dir)
    assert runner.run() == 0, [(s["id"], s.get("error")) for s in runner.states.values()]
    state = runner.states["run-0"]
    assert state["status"] == "completed"
    assert len(state["incomplete_evaluations"]) == 2
    for folder, path in partial.items():
        (aside,) = (state_dir / folder).glob("run-0.incomplete-*")
        assert (aside / "report.json.tmp").read_text() == "partial"
        assert str(aside) in state["incomplete_evaluations"]
        assert (path / "report.json").is_file()
        assert not (path / "report.json.tmp").exists()


def test_torch_runs_keep_a_single_best_checkpoint_evaluation(spec_path, tmp_path):
    runner = FakeCampaign(spec_path, tmp_path / "state")
    assert runner.run() == 0
    assert {stage for _, stage, _ in runner.calls} == set(campaign.STAGES[:5])
    assert all(state["checkpoint"] == "checkpoint_best.pth" for state in runner.states.values())
    assert all("secondary" not in state for state in runner.states.values())


@pytest.mark.parametrize(
    "edit, message",
    [
        (lambda spec: spec.update(gpus=["1", "2"]), "forbidden"),
        (lambda spec: spec.update(gpus=["0"]), "forbidden"),
        (lambda spec: spec["runs"][0].update(gpu="5"), "pinned run gpu"),
    ],
)
def test_forbidden_or_unlisted_gpus_are_refused_before_any_state(
    spec_path, tmp_path, edit, message
):
    spec = campaign.read_json(spec_path)
    edit(spec)
    campaign.write_json(spec_path, spec)
    with pytest.raises(ValueError, match=message):
        FakeCampaign(spec_path, tmp_path / "state")
    assert not (tmp_path / "state").exists()


def test_stage_environment_rechecks_the_forbidden_set(spec_path, tmp_path, monkeypatch):
    runner = FakeCampaign(spec_path, tmp_path / "state")
    assert runner.environment("2")["CUDA_VISIBLE_DEVICES"] == "2"
    monkeypatch.setenv("SEGMENTARY_FORBIDDEN_GPUS", "2")
    with pytest.raises(ValueError, match="forbidden"):
        runner.environment("2")
