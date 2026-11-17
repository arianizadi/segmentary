"""A deterministic CPU builder preserves qualified source identities and receipts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from scripts import evaluate_rad_source_stages as evaluator
from scripts import prepare_rad_source_stages as builder

import test_evaluate_rad_source_stages as fixture_module


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    request_path, source_request, _ = fixture_module.prepared.__wrapped__(tmp_path, monkeypatch)
    models = source_request["models"]
    monkeypatch.setattr(builder, "ACCURACY", models[:4])
    monkeypatch.setattr(builder, "FAST", models[4:])
    monkeypatch.setattr(
        builder,
        "load_space",
        lambda root, taxonomy: SimpleNamespace(
            names=[f"class-{index}" for index in range(19 if taxonomy == "city19" else 21)]
        ),
    )
    qualified, metadata, public = [], [], []
    for job in source_request["jobs"]:
        row = {
            "model": job["model"],
            "protocol": job["stage"],
            "config": job["config"],
            "checkpoint": job["checkpoint"],
            "recorded_sha256": job["checkpoint_sha256"],
        }
        qualified.append(row)
        metadata.append(
            {
                "approved_manifest_row": row,
                "config_record": yaml.safe_load(Path(job["config"]).read_text()),
                "config": {"sha256": job["config_sha256"]},
                "checkpoint_metadata": {"global_step": job["checkpoint_global_step"]},
                "training_receipt": {
                    key: job["training_receipt"][key] for key in ("path", "sha256")
                },
                "complete_training_record": job["training_receipt"]["record"],
            }
        )
        if job["stage"] == "cityscapes":
            public.append({"model": job["model"], **job["public_pretraining"]})
    paths = {
        "qualified_sources": tmp_path / "qualified.json",
        "source_metadata": tmp_path / "metadata.json",
        "source_provenance": tmp_path / "provenance.json",
    }
    paths["qualified_sources"].write_text(json.dumps(qualified))
    paths["source_metadata"].write_text(json.dumps(metadata))
    evaluator.write(paths["source_provenance"], {"reproducibility_table": public})
    rail = source_request["jobs"][1]["evaluation_data"]
    arguments = {
        **paths,
        "campaign_json": Path(source_request["campaign_json"]),
        "code_sha": source_request["code_sha"],
        "output_root": Path(source_request["output_root"]),
        "rail_split_file": Path(rail["split_file"]),
        "rail_split_sha256": rail["split_file_sha256"],
    }
    return request_path, source_request, arguments


def test_builder_produces_full_accepted_request_deterministically(inputs, tmp_path):
    _, source, arguments = inputs
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    result = builder.prepare(**arguments, out=first)
    builder.prepare(**arguments, out=second)
    assert first.read_bytes() == second.read_bytes()
    assert len(result["jobs"]) == 16
    assert {(job["model"], job["stage"]) for job in result["jobs"]} == {
        (job["model"], job["stage"]) for job in source["jobs"]
    }
    assert all(job["training_receipt"]["record"]["seed"] == 0 for job in result["jobs"])
    fixture_module.bind_request(first, result)
    accepted, _, _ = evaluator.validate_request(first, first.parent)
    for job in accepted["jobs"]:
        evaluator.verify_source(job)
    before = first.read_bytes()
    with pytest.raises(FileExistsError):
        builder.prepare(**arguments, out=first)
    assert first.read_bytes() == before


def test_changed_pinned_split_and_missing_endpoint_refused(inputs, tmp_path):
    _, _, arguments = inputs
    out = tmp_path / "new-source-request.json"
    Path(arguments["rail_split_file"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="split SHA-256"):
        builder.prepare(**arguments, out=out)
    arguments["rail_split_sha256"] = evaluator.digest(arguments["rail_split_file"])
    rows = json.loads(arguments["qualified_sources"].read_text())
    arguments["qualified_sources"].write_text(json.dumps(rows[:-1]))
    with pytest.raises(ValueError, match="both qualified source stages"):
        builder.prepare(**arguments, out=out)
    assert not out.exists()
