"""Contracts for the public, incrementally generated model comparison."""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPARISON = ROOT / "docs/results/model-comparison"
PROTOCOLS = ("cityscapes", "railsem19", "cityscapes_to_railsem19")
ITERATION_STAGES = {
    "cityscapes": [("cityscapes", "Cityscapes", 40_000)],
    "railsem19": [("railsem19", "RailSem19", 40_000)],
    "cityscapes_to_railsem19": [
        ("cityscapes", "Cityscapes", 40_000),
        ("railsem19", "RailSem19", 20_000),
    ],
}
METRICS = (
    "miou",
    "macc",
    "mprecision",
    "mdice",
    "mspecificity",
    "pixel_accuracy",
    "freqw_iou",
    "boundary_macro_f1",
)


def _finite_unit(value: object) -> float:
    assert isinstance(value, int | float) and not isinstance(value, bool)
    number = float(value)
    assert math.isfinite(number) and 0.0 <= number <= 1.0
    return number


def _assert_summary(summary: dict, values: list[float | None]) -> None:
    clean = [value for value in values if value is not None]
    assert summary["count"] == len(clean)
    if not clean:
        assert summary["mean"] is None
        assert summary["sample_std"] is None
        return
    assert _finite_unit(summary["mean"]) == pytest.approx(statistics.fmean(clean))
    expected_std = statistics.stdev(clean) if len(clean) > 1 else None
    assert (
        summary["sample_std"] == pytest.approx(expected_std)
        if expected_std is not None
        else summary["sample_std"] is None
    )


def test_comparison_status_covers_every_recipe_and_only_marks_real_results_complete() -> None:
    status = json.loads((COMPARISON / "status.json").read_text(encoding="utf-8"))
    recipes = {path.stem for path in (ROOT / "configs/models").glob("*.yaml")}
    rows = status["models"]

    assert status["schema_version"] == 2
    assert status["scope"]["model_recipes"] == len(recipes) == 37
    assert status["scope"]["unique_training_choices"] == 36
    assert len(rows) == len(recipes)
    assert {row["model"] for row in rows} == recipes
    assert [row["priority"] for row in rows] == list(range(1, len(rows) + 1))
    assert [row["model"] for row in rows if row["status"] == "complete"] == ["segformer_b2"]
    assert {row["status"] for row in rows} <= {"queued", "running", "complete", "failed"}
    assert status["counts"]["complete_cells"] == 3
    assert status["counts"]["total_reported_cells"] == 37 * 3
    assert status["counts"]["physical_training_cells"] == 36 * 3
    assert status["scope"]["standardized_inference"]["status"] == "pending"
    for protocol_id, stages in ITERATION_STAGES.items():
        target = sum(stage[2] for stage in stages)
        protocol_target = status["scope"]["protocol_targets"][protocol_id]
        assert protocol_target["target_iterations"] == target
        assert [
            (item["stage"], item["dataset"], item["target_iterations"])
            for item in protocol_target["stages"]
        ] == stages

    reused = next(row for row in rows if row["model"] == "segformer_b2")
    for protocol_id, stages in ITERATION_STAGES.items():
        progress = reused["iteration_progress"][protocol_id]
        target = sum(stage[2] for stage in stages)
        assert progress["current_iterations"] == progress["target_iterations"] == target
        assert progress["final_verification"]["result_verified"] is True
    transfer_final = reused["iteration_progress"]["cityscapes_to_railsem19"]["final_verification"]
    assert transfer_final["result_total_iterations"] == 60_000
    assert transfer_final["checkpoint_global_step"] == 20_000

    with (COMPARISON / "results.csv").open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert len(csv_rows) == 37
    assert {row["model"] for row in csv_rows} == recipes
    assert all("sample_std" not in column for column in csv_rows[0])
    for row in csv_rows:
        expected_current = "40000" if row["model"] == "segformer_b2" else "0"
        assert row["cityscapes_iterations_current"] == expected_current
        assert row["railsem19_iterations_current"] == expected_current
        expected_transfer = "60000" if row["model"] == "segformer_b2" else "0"
        assert row["cityscapes_to_railsem19_iterations_current"] == expected_transfer
        assert row["cityscapes_iterations_target"] == "40000"
        assert row["railsem19_iterations_target"] == "40000"
        assert row["cityscapes_to_railsem19_iterations_target"] == "60000"
        assert row["standardized_inference_status"] == "pending"

    reused_csv = next(row for row in csv_rows if row["model"] == "segformer_b2")
    assert reused_csv["cityscapes_parameters"] == "27362772"
    assert reused_csv["railsem19_parameters"] == "27364310"
    assert reused_csv["cityscapes_final_checkpoint_bytes"] == ""
    assert reused_csv["railsem19_final_checkpoint_bytes"] == "438443635"
    assert reused_csv["cityscapes_to_railsem19_final_checkpoint_bytes"] == "438443635"


def test_reused_segformer_record_recomputes_and_labels_every_metric() -> None:
    path = COMPARISON / "records/segformer_b2.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["schema_version"] == 2
    assert record["model_id"] == "segformer_b2"
    assert record["status"] == "complete"
    assert tuple(record["protocols"]) == PROTOCOLS
    assert record["model_profile"]["parameter_count"] == {
        "cityscapes19": 27_362_772,
        "rail_union": 27_364_310,
    }
    assert record["model_profile"]["standardized_inference"]["status"] == "pending"
    assert record["model_profile"]["standardized_inference"]["fps"] is None
    assert "/data/" not in path.read_text(encoding="utf-8")
    assert "/scr/" not in path.read_text(encoding="utf-8")

    for protocol_id, protocol in record["protocols"].items():
        taxonomy = yaml.safe_load(
            (ROOT / f"taxonomy/{protocol['taxonomy']}/canonical.yaml").read_text(encoding="utf-8")
        )
        names = [item["name"] for item in taxonomy["classes"]]
        individuals = protocol["individual"]
        assert protocol["seed_count"] == len(individuals) == len(protocol["seeds"])
        assert protocol["seeds"] == [item["seed"] for item in individuals]
        assert list(protocol["aggregate"]["per_class_iou"]) == names
        assert list(protocol["support"]) == names
        assert all(item["source"]["git_dirty"] is False for item in individuals)
        assert all(len(item["source"]["result_sha256"]) == 64 for item in individuals)

        expected_stages = ITERATION_STAGES[protocol_id]
        progress = protocol["iteration_progress"]
        target = sum(item[2] for item in expected_stages)
        assert progress["target_iterations"] == progress["current_iterations"] == target
        assert [
            (
                item["stage"],
                item["dataset"],
                item["target_iterations"],
                item["current_iterations"],
            )
            for item in progress["stages"]
        ] == [(*item, item[2]) for item in expected_stages]
        assert progress["final_verification"]["result_verified"] is True
        assert progress["final_verification"]["result_total_iterations"] == target

        for metric in METRICS:
            values = [_finite_unit(item["metrics"][metric]) for item in individuals]
            _assert_summary(protocol["aggregate"][metric], values)
        for name in names:
            values = [item["metrics"]["per_class_iou"][name] for item in individuals]
            for value in values:
                if value is not None:
                    _finite_unit(value)
            _assert_summary(protocol["aggregate"]["per_class_iou"][name], values)

        expected_images = 500 if protocol_id == "cityscapes" else 850
        assert protocol["evaluation"] == {
            "images": expected_images,
            "sliding_window": [1024, 1024],
            "split": "val",
            "stride": [768, 768],
            "tta": False,
            "weights": "EMA",
        }

    city = record["protocols"]["cityscapes"]
    assert city["aggregate"]["miou"]["mean"] == pytest.approx(0.8050734617920341)
    assert city["seed_count"] == 1
    assert city["individual"][0]["source"]["checkpoint_available"] is False
    assert city["caveats"]
    assert city["iteration_progress"]["final_verification"] == {
        "result_verified": True,
        "result_total_iterations": 40_000,
        "result_final_stage_iteration": 40_000,
        "checkpoint_available": False,
        "checkpoint_verified": False,
        "checkpoint_global_step": None,
    }
    assert city["resource_evidence"]["parameter_count"] == 27_362_772
    assert city["resource_evidence"]["final_checkpoint"] == {
        "available": False,
        "size_bytes": None,
    }
    assert city["resource_evidence"]["training"]["wall_clock_s_mean"] == pytest.approx(
        5836.301588855684
    )

    rail = record["protocols"]["railsem19"]
    transfer = record["protocols"]["cityscapes_to_railsem19"]
    assert rail["aggregate"]["miou"]["mean"] == pytest.approx(0.704737023344594)
    assert transfer["aggregate"]["miou"]["mean"] == pytest.approx(0.6644080109173984)
    assert rail["seed_count"] == transfer["seed_count"] == 3
    assert all(item["source"]["checkpoint_available"] for item in rail["individual"])
    assert all(item["source"]["checkpoint_available"] for item in transfer["individual"])
    assert rail["iteration_progress"]["final_verification"]["checkpoint_global_step"] == 40_000
    assert transfer["iteration_progress"]["final_verification"] == {
        "result_verified": True,
        "result_total_iterations": 60_000,
        "result_final_stage_iteration": 20_000,
        "checkpoint_available": True,
        "checkpoint_verified": True,
        "checkpoint_global_step": 20_000,
    }
    assert rail["resource_evidence"]["final_checkpoint"]["size_bytes"] == 438_443_635
    assert transfer["resource_evidence"]["final_checkpoint"]["size_bytes"] == 438_443_635
    assert rail["resource_evidence"]["training"]["gpu_hours_mean"] == pytest.approx(
        14.211236329971364
    )
    assert transfer["resource_evidence"]["training"]["gpu_hours_mean"] == pytest.approx(
        20.936002951716933
    )


def test_segformer_readme_contains_one_generated_complete_class_report() -> None:
    readme = (ROOT / "docs/catalog/models/builtin-segformer-b2/README.md").read_text(
        encoding="utf-8"
    )
    assert readme.count("<!-- segmentary:generated-city-rail-benchmark:start -->") == 1
    assert readme.count("<!-- segmentary:generated-city-rail-benchmark:end -->") == 1
    assert "80.51" in readme
    assert "70.47" in readme
    assert "66.44" in readme
    assert "40,000 / 40,000" in readme
    assert "60,000 / 60,000" in readme
    assert "27,362,772" in readme
    assert "418.1 MiB" in readme
    assert "### Cityscapes class IoU" in readme
    assert "### RailSem19 class IoU" in readme


def test_human_comparison_surfaces_show_clean_means_and_iterations() -> None:
    paths = [
        COMPARISON / "README.md",
        COMPARISON / "results.csv",
        ROOT / "docs/catalog/models/builtin-segformer-b2/README.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "±" not in text
    assert "sample_std" not in text
    assert "80.51 (40,000)" in text
    assert "66.44 (60,000)" in text
    assert "Standardized inference FPS, latency, and inference VRAM are pending" in text
