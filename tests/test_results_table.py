"""Benchmark tables must be derived from result files, including seed variance."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from segmentary import results_table as make_results_table
from segmentary.config import config_hash


def _write_result(
    root: Path,
    seed: int,
    *,
    miou: float | None,
    boundary_f1: float,
    rail_iou: float,
    rail_raised_iou: float | None = None,
    run_id: str | None = None,
    tuning: str = "full",
    git_sha: str = "a" * 40,
    git_dirty: bool = False,
    config_seed: int | None = None,
    input_mean: list[float] | None = None,
    stage: str = "railsem19",
    name: str = "synthetic-curriculum",
) -> Path:
    path = root / (run_id or f"seed{seed}") / "results.json"
    path.parent.mkdir(parents=True)
    config = {
        "name": name,
        "model": {"arch": "segformer_b2", "tuning": tuning},
        "train": {"seed": seed if config_seed is None else config_seed},
        "optim": {"backbone_lr": 6e-5},
    }
    path.write_text(
        json.dumps(
            {
                "name": name,
                "stage": stage,
                "seed": seed,
                "config_hash": config_hash(config),
                "metrics": {
                    "miou": miou,
                    "macc": None if miou is None else min(1.0, miou + 0.1),
                    "pixel_accuracy": None if miou is None else min(1.0, miou + 0.15),
                    "boundary": {"macro_f1": boundary_f1},
                    "per_class_iou": {
                        "rail-track": rail_iou,
                        # This dataset/mapping cannot produce rail-raised.
                        "rail-raised": rail_raised_iou,
                    },
                },
                "config": config,
                "wall_clock_s": (seed + 1) * 3600,
                "peak_vram_bytes": {"cuda:0": (seed + 1) * 2**30},
                "git_sha": git_sha,
                "git_dirty": git_dirty,
                "env": {
                    "input_normalization": {
                        "mean": input_mean or [0.485, 0.456, 0.406],
                        "std": [0.229, 0.224, 0.225],
                        "channel_order": "rgb",
                        "source": "test",
                    }
                },
            }
        )
    )
    return path


def _run_table(runs: Path, out: Path) -> int:
    return make_results_table.main(
        [
            "--runs",
            str(runs),
            "--out",
            str(out),
            "--classes",
            "rail-track",
            "rail-raised",
        ]
    )


def test_table_aggregates_seed_mean_and_sample_std_and_marks_unavailable(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    out = tmp_path / "tables"
    for seed, values in enumerate(
        [
            (0.60, 0.40, 0.30),
            (0.70, 0.50, 0.50),
            (0.80, 0.60, 0.70),
        ]
    ):
        _write_result(
            runs,
            seed,
            miou=values[0],
            boundary_f1=values[1],
            rail_iou=values[2],
        )

    assert _run_table(runs, out) == 0

    with (out / "results.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    row = rows[0]
    assert row["seeds"] == "3"
    assert row["miou"] == "70.00 ± 10.00"
    assert row["macc"] == "80.00 ± 10.00"
    assert row["pixel_accuracy"] == "85.00 ± 10.00"
    assert row["boundary_f1"] == "50.00 ± 10.00"
    assert row["rail-track"] == "50.00 ± 20.00"
    assert row["rail-raised"] == "--"
    assert row["wall_clock_h"] == "2.00"
    assert row["peak_vram_gb"] == "3.0"

    markdown = (out / "results.md").read_text()
    assert "70.00 ± 10.00" in markdown
    assert "| -- |" in markdown
    assert "not total curriculum training costs" in markdown


def test_table_rejects_a_record_that_fails_results_schema(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    path = _write_result(runs, 0, miou=0.6, boundary_f1=0.4, rail_iou=0.3)
    record = json.loads(path.read_text())
    record.pop("config_hash")
    path.write_text(json.dumps(record))

    with pytest.raises(
        SystemExit, match=r"invalid result record.*missing required keys.*config_hash"
    ):
        _run_table(runs, tmp_path / "out")


def test_table_rejects_a_tampered_embedded_config(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    path = _write_result(runs, 0, miou=0.6, boundary_f1=0.4, rail_iou=0.3)
    record = json.loads(path.read_text())
    record["config"]["optim"]["backbone_lr"] = 1e-3
    path.write_text(json.dumps(record))

    with pytest.raises(SystemExit, match=r"config_hash.*does not match the embedded config"):
        _run_table(runs, tmp_path / "out")


def test_table_rejects_record_seed_that_disagrees_with_config(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_result(
        runs,
        0,
        miou=0.6,
        boundary_f1=0.4,
        rail_iou=0.3,
        config_seed=7,
    )

    with pytest.raises(SystemExit, match=r"record seed 0 does not match config\.train\.seed 7"):
        _run_table(runs, tmp_path / "out")


def test_table_rejects_duplicate_records_for_one_seed(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    for run_id, miou in (("copy-a", 0.1), ("copy-b", 0.9)):
        _write_result(
            runs,
            0,
            miou=miou,
            boundary_f1=0.4,
            rail_iou=0.3,
            run_id=run_id,
        )

    with pytest.raises(SystemExit, match=r"duplicate seed 0.*copy-a.*copy-b"):
        _run_table(runs, tmp_path / "out")


def test_table_rejects_configs_that_differ_beyond_seed(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_result(runs, 0, miou=0.6, boundary_f1=0.4, rail_iou=0.3, tuning="full")
    _write_result(runs, 1, miou=0.7, boundary_f1=0.5, rail_iou=0.4, tuning="frozen")

    with pytest.raises(SystemExit, match=r"configs differ beyond train\.seed"):
        _run_table(runs, tmp_path / "out")


def test_table_rejects_mixed_git_provenance(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_result(runs, 0, miou=0.6, boundary_f1=0.4, rail_iou=0.3, git_sha="a" * 40)
    _write_result(runs, 1, miou=0.7, boundary_f1=0.5, rail_iou=0.4, git_sha="b" * 40)

    with pytest.raises(SystemExit, match="git provenance differs"):
        _run_table(runs, tmp_path / "out")


def test_table_rejects_replicates_with_different_effective_normalization(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    _write_result(runs, 0, miou=0.6, boundary_f1=0.4, rail_iou=0.3)
    _write_result(
        runs,
        1,
        miou=0.7,
        boundary_f1=0.5,
        rail_iou=0.4,
        input_mean=[0.5, 0.5, 0.5],
    )

    with pytest.raises(SystemExit, match="effective input normalization differs"):
        _run_table(runs, tmp_path / "out")


def test_table_refuses_to_aggregate_dirty_replicates(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    for seed in (0, 1):
        _write_result(
            runs,
            seed,
            miou=0.6 + seed / 10,
            boundary_f1=0.4,
            rail_iou=0.3,
            git_dirty=True,
        )

    with pytest.raises(SystemExit, match="dirty runs do not prove"):
        _run_table(runs, tmp_path / "out")


def test_table_rejects_a_missing_headline_metric(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_result(runs, 0, miou=None, boundary_f1=0.4, rail_iou=0.3)

    with pytest.raises(SystemExit, match=r"metrics\.miou must be a finite number"):
        _run_table(runs, tmp_path / "out")


@pytest.mark.parametrize("field", ["macc", "pixel_accuracy"])
def test_table_rejects_missing_accuracy_metrics(tmp_path: Path, field: str) -> None:
    runs = tmp_path / "runs"
    path = _write_result(runs, 0, miou=0.6, boundary_f1=0.4, rail_iou=0.3)
    record = json.loads(path.read_text())
    record["metrics"][field] = None
    path.write_text(json.dumps(record))

    with pytest.raises(SystemExit, match=rf"metrics\.{field} must be a finite number"):
        _run_table(runs, tmp_path / "out")


def test_table_rejects_a_class_present_for_only_some_seeds(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_result(
        runs,
        0,
        miou=0.6,
        boundary_f1=0.4,
        rail_iou=0.3,
        rail_raised_iou=None,
    )
    _write_result(
        runs,
        1,
        miou=0.7,
        boundary_f1=0.5,
        rail_iou=0.4,
        rail_raised_iou=0.2,
    )

    with pytest.raises(SystemExit, match=r"class 'rail-raised' is missing for only seeds \[0\]"):
        _run_table(runs, tmp_path / "out")


def test_table_marks_a_class_absent_from_every_seed_unavailable(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    for seed in (0, 1):
        path = _write_result(
            runs,
            seed,
            miou=0.6 + seed / 10,
            boundary_f1=0.4,
            rail_iou=0.3,
        )
        record = json.loads(path.read_text())
        record["metrics"]["per_class_iou"].pop("rail-raised")
        path.write_text(json.dumps(record))

    out = tmp_path / "out"
    assert _run_table(runs, out) == 0
    with (out / "results.csv").open(newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["rail-raised"] == "--"


def test_table_filters_exact_stage_and_experiment_after_validating_every_record(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    _write_result(
        runs,
        0,
        miou=0.6,
        boundary_f1=0.4,
        rail_iou=0.3,
        run_id="native",
    )
    _write_result(
        runs,
        0,
        miou=0.7,
        boundary_f1=0.5,
        rail_iou=0.4,
        run_id="common",
        stage="eval:railsem19:val",
        name="target-curriculum",
    )
    out = tmp_path / "out"

    assert (
        make_results_table.main(
            [
                "--runs",
                str(runs),
                "--out",
                str(out),
                "--stage",
                "eval:railsem19:val",
                "--experiment",
                "target-curriculum",
            ]
        )
        == 0
    )
    with (out / "results.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(row["experiment"], row["stage"], row["miou"]) for row in rows] == [
        ("target-curriculum", "eval:railsem19:val", "70.00")
    ]
