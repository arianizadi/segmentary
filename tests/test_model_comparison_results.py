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

    assert status["scope"]["model_recipes"] == len(recipes) == 37
    assert status["scope"]["unique_training_choices"] == 36
    assert len(rows) == len(recipes)
    assert {row["model"] for row in rows} == recipes
    assert [row["priority"] for row in rows] == list(range(1, len(rows) + 1))
    assert [row["model"] for row in rows if row["status"] == "complete (reused)"] == [
        "segformer_b2"
    ]
    assert status["counts"]["complete_cells"] == 3
    assert status["counts"]["total_reported_cells"] == 37 * 3
    assert status["counts"]["physical_training_cells"] == 36 * 3

    with (COMPARISON / "results.csv").open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert len(csv_rows) == 37
    assert {row["model"] for row in csv_rows} == recipes


def test_reused_segformer_record_recomputes_and_labels_every_metric() -> None:
    path = COMPARISON / "records/segformer_b2.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["schema_version"] == 1
    assert record["model_id"] == "segformer_b2"
    assert record["status"] == "complete"
    assert tuple(record["protocols"]) == PROTOCOLS
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

    rail = record["protocols"]["railsem19"]
    transfer = record["protocols"]["cityscapes_to_railsem19"]
    assert rail["aggregate"]["miou"]["mean"] == pytest.approx(0.704737023344594)
    assert transfer["aggregate"]["miou"]["mean"] == pytest.approx(0.6644080109173984)
    assert rail["seed_count"] == transfer["seed_count"] == 3
    assert all(item["source"]["checkpoint_available"] for item in rail["individual"])
    assert all(item["source"]["checkpoint_available"] for item in transfer["individual"])


def test_segformer_readme_contains_one_generated_complete_class_report() -> None:
    readme = (ROOT / "docs/catalog/models/builtin-segformer-b2/README.md").read_text(
        encoding="utf-8"
    )
    assert readme.count("<!-- segmentary:generated-city-rail-benchmark:start -->") == 1
    assert readme.count("<!-- segmentary:generated-city-rail-benchmark:end -->") == 1
    assert "80.51" in readme
    assert "70.47 ± 0.17" in readme
    assert "66.44 ± 0.03" in readme
    assert "### Cityscapes class IoU" in readme
    assert "### RailSem19 class IoU" in readme
