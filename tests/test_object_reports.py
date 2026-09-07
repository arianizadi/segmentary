"""Report generation uses real tiny query models, native pixels and official refs."""

import json
from dataclasses import asdict

import pytest
import torch
from PIL import Image

from segmentary.objects.checkpoint_model import model_spec
from segmentary.objects.reports import comparison, run_report
from test_object_workflow import fixture_config, tiny_model


@pytest.mark.parametrize("task", ["instance", "panoptic"])
def test_native_report_reference_provenance_resources_and_links(tmp_path, task):
    if task == "panoptic":
        pytest.importorskip("panopticapi")
    config = fixture_config(tmp_path, task)
    annotation = tmp_path / "labels.json"
    data = json.loads(annotation.read_text())
    data["images"][0]["id"] = 41
    for row in data["annotations"]:
        row["image_id"] = 41
        if task == "instance":
            row["area"] = 64
            row["bbox"] = [row["segmentation"][0][0], 4, 8, 8]
    annotation.write_text(json.dumps(data))
    # Recursive image enumeration would accidentally add this non-evaluation file.
    Image.new("RGB", (32, 32)).save(tmp_path / "images/unlisted.png")
    model = tiny_model(config.model, 1 if task == "instance" else 2)
    checkpoint = tmp_path / "checkpoint.pt"
    categories = data["categories"]
    torch.save(
        {
            "schema": "segmentary-objects-v1",
            "task": task,
            "categories": categories,
            "config": asdict(config),
            "architecture": model_spec(model),
            "model": model.state_dict(),
            "step": 7,
        },
        checkpoint,
    )
    report_dir = tmp_path / "report"
    report = run_report(config, checkpoint, report_dir, reference=True, warmup=1)
    assert report["metrics"]["images"] == 1
    assert report["reference"]["passed"]
    assert report["resources"]["peak_allocated_bytes"] is None
    assert report["resources"]["model_only"]["fps"] > 0
    assert (
        report["resources"]["end_to_end"]["total_s"] >= report["resources"]["model_only"]["total_s"]
    )
    assert report["provenance"]["checkpoint_step"] == 7
    assert len(report["provenance"]["checkpoint_sha256"]) == 64
    assert "image/unlisted.png" not in report["dataset"]["files_sha256"]
    predictions = json.loads((report_dir / "predictions/predictions.json").read_text())
    assert [row["id"] for row in predictions["images"]] == [41]
    assert all(row["image_id"] == 41 for row in predictions["annotations"])
    markdown = (report_dir / "README.md").read_text()
    assert "## Per-class results" in markdown and "PASS" in markdown
    assert "float32 evaluation" in markdown and "exclusivity was not enforced" in markdown
    assert "±" not in markdown and "(n=" not in markdown
    assert ("Mask AP" if task == "instance" else "| Group | PQ") in markdown
    output = tmp_path / "comparison/README.md"
    comparison([report_dir / "report.json"], output)
    assert "../report/README.md" in output.read_text()
    assert "—" in output.read_text()
    with pytest.raises(FileExistsError):
        run_report(config, checkpoint, report_dir)


def test_report_rejects_input_tree_output_before_loading_checkpoint(tmp_path):
    config = fixture_config(tmp_path, "instance")
    with pytest.raises(ValueError, match="outside"):
        run_report(config, tmp_path / "checkpoint.pt", tmp_path / "images/report")
    with pytest.raises(ValueError, match="warmup"):
        run_report(config, tmp_path / "checkpoint.pt", tmp_path / "report", warmup=0)


def test_comparison_separates_tasks_and_changed_dataset(tmp_path):
    from segmentary.objects.reports import comparison

    paths = []
    for index, (task, fingerprint) in enumerate(
        (("instance", "a"), ("instance", "b"), ("panoptic", "a"))
    ):
        directory = tmp_path / str(index)
        directory.mkdir()
        path = directory / "report.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "segmentary-object-report-v1",
                    "name": "model|name",
                    "task": task,
                    "dataset": {"sha256": fingerprint},
                    "metrics": {},
                    "resources": {
                        "model_only": {"fps": 1},
                        "end_to_end": {"fps": 0.5},
                        "peak_allocated_bytes": None,
                    },
                }
            )
        )
        paths.append(path)
    comparison(paths, tmp_path / "README.md")
    content = (tmp_path / "README.md").read_text()
    assert content.count("## ") == 3
    assert "model\\|name" in content


def test_cli_reports_reference_failure_after_saving_artifacts(tmp_path, monkeypatch):
    from segmentary.objects import reports

    monkeypatch.setattr(reports, "load_config", lambda _: object())
    monkeypatch.setattr(
        reports, "run_report", lambda *args, **kwargs: {"reference": {"passed": False}}
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "reports",
            "config.yaml",
            "--checkpoint",
            "checkpoint.pt",
            "--out",
            str(tmp_path / "report"),
            "--reference",
        ],
    )
    with pytest.raises(SystemExit) as failure:
        reports.main()
    assert failure.value.code == 1


def test_report_keeps_checkpoint_category_mapping_for_subset_split(tmp_path):
    config = fixture_config(tmp_path, "instance")
    model = tiny_model(config.model, 2)
    categories = [
        {"id": 2, "name": "absent", "isthing": 1},
        {"id": 7, "name": "object", "isthing": 1},
    ]
    checkpoint = tmp_path / "checkpoint.pt"
    torch.save(
        {
            "schema": "segmentary-objects-v1",
            "task": "instance",
            "categories": categories,
            "config": asdict(config),
            "architecture": model_spec(model),
            "model": model.state_dict(),
        },
        checkpoint,
    )
    report = run_report(config, checkpoint, tmp_path / "report", warmup=1)
    assert report["categories"][0]["name"] == "absent"
    assert report["metrics"]["per_class"]["0"]["support"] == 0
    assert report["metrics"]["per_class"]["1"]["support"] == 2
    assert "Checkpoint step: —" in (tmp_path / "report/README.md").read_text()


@pytest.mark.parametrize("stage", ["loading", "evaluation"])
def test_changing_checkpoint_cannot_publish_false_provenance(tmp_path, monkeypatch, stage):
    from segmentary.objects import reports

    config = fixture_config(tmp_path, "instance")
    model = tiny_model(config.model, 1)
    checkpoint = tmp_path / "checkpoint.pt"
    content = {
        "schema": "segmentary-objects-v1",
        "task": "instance",
        "categories": [{"id": 7, "name": "object", "isthing": 1}],
        "config": asdict(config),
        "architecture": model_spec(model),
        "model": model.state_dict(),
        "step": 1,
    }
    torch.save(content, checkpoint)
    original_load, original_query = reports.load_checkpoint, reports.query_output

    def replace_checkpoint():
        replacement = tmp_path / "replacement.pt"
        torch.save({**content, "step": 99}, replacement)
        replacement.replace(checkpoint)

    def load(*args, **kwargs):
        result = original_load(*args, **kwargs)
        replace_checkpoint()
        return result

    def query(*args, **kwargs):
        result = original_query(*args, **kwargs)
        replace_checkpoint()
        return result

    monkeypatch.setattr(
        reports,
        "load_checkpoint" if stage == "loading" else "query_output",
        load if stage == "loading" else query,
    )
    with pytest.raises(ValueError, match="Checkpoint changed"):
        run_report(config, checkpoint, tmp_path / "report", warmup=1)
    assert not (tmp_path / "report/report.json").exists()
    assert not (tmp_path / "report/README.md").exists()
