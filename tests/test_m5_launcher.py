"""Fail-closed orchestration tests for the two-lane Milestone 5 launcher."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from scripts import run_m5_lane as launcher

EXPECTED_SHA = "a" * 40
RAILSEM19_ROOT = Path("/datasets/railsem19")
HF_HOME = Path("/cache/huggingface")


class GitStub:
    def __init__(self, *, sha: str = EXPECTED_SHA, dirty: str | list[str] = "") -> None:
        self.sha = sha
        self.dirty = dirty if isinstance(dirty, str) else None
        self.dirty_sequence = list(dirty) if isinstance(dirty, list) else []
        self.calls: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[1:] == ["rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout=f"{self.sha}\n", stderr="")
        if command[1:] == ["status", "--porcelain=v1", "--untracked-files=all"]:
            dirty = self.dirty_sequence.pop(0) if self.dirty_sequence else self.dirty
            return subprocess.CompletedProcess(command, 0, stdout=dirty or "", stderr="")
        raise AssertionError(f"unexpected git command: {command}")


def _args(campaign: Path, lane: str = "a", *, dry_run: bool = False) -> list[str]:
    args = [
        "--lane",
        lane,
        "--campaign",
        str(campaign),
        "--expected-sha",
        EXPECTED_SHA,
        "--gpus",
        "0,1,2,3" if lane == "a" else "4,5,6,7",
        "--master-port",
        "29501" if lane == "a" else "29502",
        "--railsem19-root",
        str(RAILSEM19_ROOT),
        "--hf-home",
        str(HF_HOME),
    ]
    if dry_run:
        args.append("--dry-run")
    return args


def _option(command: list[str], option: str) -> str:
    return command[command.index(option) + 1]


def _set_values(command: list[str]) -> list[str]:
    return [command[index + 1] for index, item in enumerate(command) if item == "--set"]


def _job_from_command(command: list[str]) -> launcher.Job:
    curriculum = Path(next(item for item in command if item.startswith("configs/curricula/"))).stem
    seed = int(_option(command, "--seed"))
    return next(
        job
        for queue in launcher.LANE_QUEUES.values()
        for job in queue
        if (job.curriculum, job.seed) == (curriculum, seed)
    )


def _result_payload(
    job: launcher.Job,
    *,
    sha: str = EXPECTED_SHA,
    dirty: bool = False,
    seed: int | None = None,
    config_seed: int | None = None,
) -> dict:
    recorded_seed = job.seed if seed is None else seed
    embedded_seed = job.seed if config_seed is None else config_seed
    return {
        "git_sha": sha,
        "git_dirty": dirty,
        "seed": recorded_seed,
        "config": {"train": {"seed": embedded_seed}},
    }


def _successful_runner(campaign: Path, calls: list[tuple[list[str], dict[str, str], Path]]):
    def run(command, env, log_path):
        command = list(command)
        calls.append((command, env, log_path))
        job = _job_from_command(command)
        module = command[command.index("-m") + 1]
        if module == "segmentary.train":
            checkpoint = launcher.checkpoint_path(campaign.resolve(), job)
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_bytes(b"checkpoint")
            launcher.training_results_path(campaign.resolve(), job).write_text(
                json.dumps(_result_payload(job)), encoding="utf-8"
            )
        else:
            output = Path(_option(command, "--out"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(_result_payload(job)), encoding="utf-8")
        return 0

    return run


def test_fixed_queues_are_balanced_complete_and_unique() -> None:
    assert [(job.curriculum, job.seed) for job in launcher.LANE_QUEUES["a"]] == [
        ("cs_only", 0),
        ("joint_cs_rs", 1),
        ("cs_rs", 2),
        ("rs_only", 1),
        ("cs_only", 2),
        ("cs_rs", 0),
    ]
    assert [(job.curriculum, job.seed) for job in launcher.LANE_QUEUES["b"]] == [
        ("rs_only", 0),
        ("cs_rs", 1),
        ("joint_cs_rs", 2),
        ("cs_only", 1),
        ("rs_only", 2),
        ("joint_cs_rs", 0),
    ]

    jobs = [job for queue in launcher.LANE_QUEUES.values() for job in queue]
    assert len(launcher.LANE_QUEUES["a"]) == len(launcher.LANE_QUEUES["b"]) == 6
    assert Counter(job.curriculum for job in jobs) == {
        "cs_only": 3,
        "rs_only": 3,
        "cs_rs": 3,
        "joint_cs_rs": 3,
    }
    assert len({(job.curriculum, job.seed) for job in jobs}) == 12


def test_commands_record_effective_batch_16_unique_outputs_and_common_eval(tmp_path: Path) -> None:
    campaign = tmp_path.resolve()
    jobs = [job for queue in launcher.LANE_QUEUES.values() for job in queue]
    outputs = set()

    for job in jobs:
        train = launcher.train_command(campaign, job)
        evaluate = launcher.eval_command(campaign, job, RAILSEM19_ROOT)
        overrides = _set_values(train)
        assert train[:3] == [sys.executable, "-m", "segmentary.train"]
        assert overrides == [
            "train.devices=4",
            "train.batch_size=4",
            "train.accum=1",
            f"output_root={campaign}",
        ]
        values = {key: int(value) for key, value in (item.split("=") for item in overrides[:3])}
        assert values["train.devices"] * values["train.batch_size"] * values["train.accum"] == 16

        assert evaluate[:3] == [sys.executable, "-m", "segmentary.eval"]
        assert "--ema" in evaluate
        assert _set_values(evaluate) == overrides
        assert _option(evaluate, "--dataset") == "railsem19"
        assert _option(evaluate, "--root") == str(RAILSEM19_ROOT)
        assert _option(evaluate, "--split-file") == "splits/railsem19_seed0.json"
        assert _option(evaluate, "--split") == "val"
        assert _option(evaluate, "--device") == "cuda:0"
        assert Path(_option(evaluate, "--ckpt")) == launcher.checkpoint_path(campaign, job)
        output = Path(_option(evaluate, "--out"))
        assert output == launcher.common_results_path(campaign, job)
        outputs.add(output)

    assert len(outputs) == 12


def test_job_environment_is_explicit_and_gpu_ids_are_site_configurable() -> None:
    job = launcher.LANE_QUEUES["b"][0]
    env = launcher.job_environment(job, "4,5,6,7", 29502, HF_HOME)
    assert {key: env[key] for key in launcher.ENV_DISPLAY_ORDER} == {
        "PL_GLOBAL_SEED": "0",
        "CUDA_VISIBLE_DEVICES": "4,5,6,7",
        "HF_HOME": str(HF_HOME),
        "PYTHONPATH": str(launcher.REPO_ROOT / "src"),
        "MASTER_ADDR": "127.0.0.1",
        "MASTER_PORT": "29502",
    }
    assert launcher._gpu_visibility("11,10,9,8") == "11,10,9,8"

    for invalid in ("8", "0,1,2,2", "4,5,6,7,8", "3,2,1,-1", "0,1,2,x"):
        with pytest.raises(argparse.ArgumentTypeError, match="exactly four distinct"):
            launcher._gpu_visibility(invalid)


def test_dry_run_is_mutation_free_and_prints_all_exact_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    campaign = tmp_path / "new-campaign"
    git = GitStub()
    monkeypatch.setattr(launcher.subprocess, "run", git)
    monkeypatch.setattr(
        launcher,
        "run_logged",
        lambda *args, **kwargs: pytest.fail("dry-run started a subprocess"),
    )

    assert launcher.main(_args(campaign, dry_run=True)) == 0
    lines = [
        line.removeprefix("$ ")
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("$ ")
    ]
    expected = []
    for job in launcher.LANE_QUEUES["a"]:
        env = launcher.job_environment(job, "0,1,2,3", 29501, HF_HOME)
        expected.extend(
            [
                launcher.format_invocation(launcher.train_command(campaign.resolve(), job), env),
                launcher.format_invocation(
                    launcher.eval_command(campaign.resolve(), job, RAILSEM19_ROOT), env
                ),
            ]
        )
    assert lines == expected
    assert not campaign.exists()
    assert len(git.calls) == 12


@pytest.mark.parametrize(
    ("sha", "dirty", "collision", "message"),
    [
        ("b" * 40, "", False, "HEAD is"),
        (EXPECTED_SHA, " M tracked.py\n?? untracked.py\n", False, "worktree is dirty"),
        (EXPECTED_SHA, "", True, "target run directory already exists"),
    ],
    ids=["sha", "dirty", "collision"],
)
def test_sha_dirty_and_collision_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sha: str,
    dirty: str,
    collision: bool,
    message: str,
) -> None:
    campaign = tmp_path / "campaign"
    if collision:
        launcher.run_dir(campaign, launcher.LANE_QUEUES["a"][0]).mkdir(parents=True)
    monkeypatch.setattr(launcher.subprocess, "run", GitStub(sha=sha, dirty=dirty))
    monkeypatch.setattr(
        launcher,
        "run_logged",
        lambda *args, **kwargs: pytest.fail("a provenance failure launched work"),
    )

    assert launcher.main(_args(campaign)) == 2
    status = json.loads((campaign / "lane_a_status.json").read_text())
    assert status["status"] == "failed_provenance"
    assert status["jobs"][0]["status"] == "provenance_failed"
    assert message in status["failure"]


def test_git_cleanliness_includes_all_untracked_but_not_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git = GitStub()
    monkeypatch.setattr(launcher.subprocess, "run", git)
    assert launcher.check_provenance(EXPECTED_SHA, tmp_path / "absent") == EXPECTED_SHA
    assert git.calls[-1] == ["git", "status", "--porcelain=v1", "--untracked-files=all"]
    assert "--ignored" not in git.calls[-1]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"git_sha": "b" * 40}, "git_sha"),
        ({"git_dirty": True}, "git_dirty"),
        ({"seed": 99}, "seed=99"),
        ({"config": {"train": {"seed": 99}}}, "config.train.seed=99"),
    ],
)
def test_result_records_must_match_sha_cleanliness_and_both_seed_fields(
    tmp_path: Path, payload: dict, message: str
) -> None:
    job = launcher.LANE_QUEUES["a"][0]
    record = _result_payload(job)
    record.update(payload)
    path = tmp_path / "results.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(launcher.ProvenanceError, match=message):
        launcher.validate_result_record(path, EXPECTED_SHA, job)


def test_source_is_rechecked_after_training_before_eval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    calls: list[tuple[list[str], dict[str, str], Path]] = []
    monkeypatch.setattr(launcher.subprocess, "run", GitStub(dirty=["", " M changed.py\n"]))
    monkeypatch.setattr(launcher, "run_logged", _successful_runner(campaign, calls))

    assert launcher.main(_args(campaign)) == 2
    assert [command[command.index("-m") + 1] for command, _, _ in calls] == ["segmentary.train"]
    status = json.loads((campaign / "lane_a_status.json").read_text())
    assert status["status"] == "failed_provenance"
    assert status["jobs"][0]["status"] == "provenance_failed"
    assert "changed.py" in status["failure"]


def test_source_is_rechecked_after_eval_before_accepting_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    calls: list[tuple[list[str], dict[str, str], Path]] = []
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        GitStub(dirty=["", "", "?? changed_during_eval.py\n"]),
    )
    monkeypatch.setattr(launcher, "run_logged", _successful_runner(campaign, calls))

    assert launcher.main(_args(campaign)) == 2
    assert [command[command.index("-m") + 1] for command, _, _ in calls] == [
        "segmentary.train",
        "segmentary.eval",
    ]
    status = json.loads((campaign / "lane_a_status.json").read_text())
    assert status["status"] == "failed_provenance"
    assert "changed_during_eval.py" in status["failure"]


def test_training_failure_is_recorded_and_next_independent_jobs_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    campaign = tmp_path / "campaign"
    calls: list[tuple[list[str], dict[str, str], Path]] = []
    success = _successful_runner(campaign, calls)
    failed_once = False

    def runner(command, env, log_path):
        nonlocal failed_once
        if command[command.index("-m") + 1] == "segmentary.train" and not failed_once:
            failed_once = True
            calls.append((list(command), env, log_path))
            return 17
        return success(command, env, log_path)

    git = GitStub()
    monkeypatch.setattr(launcher.subprocess, "run", git)
    monkeypatch.setattr(launcher, "run_logged", runner)

    assert launcher.main(_args(campaign)) == 1
    commands = [command for command, _, _ in calls]
    assert sum("segmentary.train" in command for command in commands) == 6
    assert sum("segmentary.eval" in command for command in commands) == 5
    status = json.loads((campaign / "lane_a_status.json").read_text())
    assert status["status"] == "complete_with_failures"
    assert [job["status"] for job in status["jobs"]] == ["train_failed"] + ["succeeded"] * 5
    assert status["jobs"][0]["train_returncode"] == 17
    # Each successful job checks before train, after train, and after eval; the
    # failed training job still checks before and after its process.
    assert len(git.calls) == 34


def test_logged_subprocess_output_is_complete_in_console_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    payload = b"stdout line\nstderr line\nprogress\rcomplete\n"

    class Process:
        stdout = io.BytesIO(payload)

        def wait(self):
            return 0

    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: Process())
    job = launcher.LANE_QUEUES["a"][0]
    env = launcher.job_environment(job, "0,1,2,3", 29501, HF_HOME)
    log = tmp_path / "job.log"

    assert launcher.run_logged([sys.executable, "-c", "print('unused')"], env, log) == 0
    assert payload.decode() in capsys.readouterr().out
    assert log.read_bytes().endswith(payload)
