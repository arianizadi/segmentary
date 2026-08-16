"""Contracts for the standardized model-only deployment benchmark."""

from __future__ import annotations

import pickle
import zipfile

import pytest

from segmentary import performance


def test_latency_summary_retains_raw_samples_and_defines_fps() -> None:
    summary = performance.latency_summary([1.0, 2.0, 3.0, 4.0])

    assert summary["raw_ms"] == [1.0, 2.0, 3.0, 4.0]
    assert summary["p50_ms"] == pytest.approx(2.5)
    assert summary["p95_ms"] == pytest.approx(3.85)
    assert summary["mean_ms"] == pytest.approx(2.5)
    assert summary["fps"] == pytest.approx(400.0)
    assert summary["percentile_method"] == "numpy linear interpolation"


@pytest.mark.parametrize("samples", [[], [0.0], [-1.0], [float("nan")], [float("inf")]])
def test_latency_summary_rejects_unreportable_samples(samples: list[float]) -> None:
    with pytest.raises(performance.PerformanceError):
        performance.latency_summary(samples)


def test_cli_fixes_the_public_batch_one_l40s_bf16_contract() -> None:
    args = performance.build_parser().parse_args(
        [
            "/runs/resolved.yaml",
            "--model-id",
            "segformer_b2",
            "--measured-job-id",
            "segformer_b2--cityscapes--seed-0",
            "--applies-to",
            "segformer_b2--cityscapes--seed-0",
            "segformer_b2--railsem19--seed-0",
            "segformer_b2--cityscapes_to_railsem19--seed-0",
            "--ckpt",
            "/runs/last.ckpt",
            "--result",
            "/runs/results.json",
            "--out",
            "/runs/performance.json",
            "--expected-git-sha",
            "a" * 40,
            "--expected-result-git-sha",
            "b" * 40,
            "--expected-result-stage",
            "eval:cityscapes:val",
            "--expected-seed",
            "0",
            "--checkpoint-global-step",
            "40000",
            "--ema",
        ]
    )

    assert (args.height, args.width) == (1024, 1024)
    assert args.warmup == 20
    assert args.iterations == 100
    assert args.required_gpu_name == "NVIDIA L40S"
    assert args.device == "cuda:0"
    assert args.ema is True
    assert args.auto_weights is False


def test_cli_auto_weights_is_mutually_exclusive_with_explicit_ema() -> None:
    parser = performance.build_parser()
    required = [
        "/runs/resolved.yaml",
        "--model-id",
        "model",
        "--measured-job-id",
        "job",
        "--applies-to",
        "job",
        "--ckpt",
        "/runs/last.ckpt",
        "--result",
        "/runs/results.json",
        "--out",
        "/runs/performance.json",
        "--expected-git-sha",
        "a" * 40,
        "--expected-result-git-sha",
        "b" * 40,
        "--expected-result-stage",
        "eval:railsem19:val",
        "--expected-seed",
        "0",
        "--checkpoint-global-step",
        "40000",
    ]
    assert parser.parse_args([*required, "--auto-weights"]).auto_weights is True
    with pytest.raises(SystemExit):
        parser.parse_args([*required, "--auto-weights", "--ema"])


@pytest.mark.parametrize(
    ("recorded", "expected"),
    [("raw", False), ("ema", True)],
)
def test_auto_weights_uses_the_exact_recorded_evaluation_endpoint(
    recorded: str, expected: bool
) -> None:
    result = {"config": {"evaluation": {"weights": recorded}}}

    assert (
        performance.benchmark_uses_ema(
            result,
            explicit_ema=not expected,
            auto_weights=True,
        )
        is expected
    )


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"config": None},
        {"config": {}},
        {"config": {"evaluation": None}},
        {"config": {"evaluation": {}}},
        {"config": {"evaluation": {"weights": "auto"}}},
    ],
)
def test_auto_weights_rejects_missing_or_untrusted_result_endpoint(
    result: dict[str, object],
) -> None:
    with pytest.raises(performance.PerformanceError, match=r"config\.evaluation\.weights"):
        performance.benchmark_uses_ema(result, explicit_ema=False, auto_weights=True)


def test_explicit_weight_choice_does_not_require_evaluation_metadata() -> None:
    assert performance.benchmark_uses_ema({}, explicit_ema=True, auto_weights=False)
    assert not performance.benchmark_uses_ema({}, explicit_ema=False, auto_weights=False)


@pytest.mark.parametrize("raw", [None, "", "0,1", "  "])
def test_physical_visibility_requires_one_isolated_gpu(
    monkeypatch: pytest.MonkeyPatch, raw: str | None
) -> None:
    if raw is None:
        monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    else:
        monkeypatch.setenv("CUDA_VISIBLE_DEVICES", raw)
    with pytest.raises(performance.PerformanceError, match="exactly one"):
        performance.physical_visibility_token()


def test_physical_visibility_keeps_the_actual_server_gpu_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "8")
    assert performance.physical_visibility_token() == "8"


def test_checkpoint_step_is_read_without_unpickling(tmp_path) -> None:
    checkpoint = tmp_path / "last.ckpt"
    with zipfile.ZipFile(checkpoint, "w") as archive:
        archive.writestr("archive/data.pkl", pickle.dumps({"global_step": 40_000}))
    assert performance.checkpoint_global_step(checkpoint) == 40_000


def test_gpu_uuid_must_be_nonempty(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        returncode = 0
        stdout = "\n"

    monkeypatch.setattr(performance.subprocess, "run", lambda *args, **kwargs: Completed())
    assert performance._gpu_uuid("8") is None
