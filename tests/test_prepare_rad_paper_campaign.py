"""CPU preparation binds explicit matrix/split choices and GT-only panel selection."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
import yaml
from PIL import Image
from scripts import prepare_rad_finalfit
from scripts import prepare_rad_paper_campaign as paper

import test_prepare_rad_finalfit as fixture_module


@pytest.fixture
def inputs(tmp_path):
    source, _, splits, samples = fixture_module.parent.__wrapped__(tmp_path)
    classes = paper.read(source / "classes.json")
    classes["classes"][13]["name"] = "mud-pumping"
    paper.write(source / "classes.json", classes)
    sample = samples[-1]
    mask = source / "masks/test" / (sample["key"] + ".png")
    label = np.arange(21, dtype=np.uint8).reshape(1, 21)
    label[0, 13] = 0
    Image.fromarray(label).save(mask)
    sample["mask_file_sha256"] = paper.digest(mask)
    sample["mask_sha256"] = hashlib.sha256(label.tobytes()).hexdigest()
    sample["class_pixels"].pop("13")
    sample["class_pixels"]["0"] = 2
    paper.write(source / "audit/samples.json", samples)
    validation = paper.read(source / "audit/validation.json")
    validation["samples_sha256"] = paper.digest(source / "audit/samples.json")
    paper.write(source / "audit/validation.json", validation)
    scores = {
        "class_order": [row["name"] for row in classes["classes"]],
        "campaign_code_sha": "a" * 40,
        "jobs": [],
    }
    for model_index, model in enumerate(paper.ACCURACY + paper.FAST[:2]):
        for arm_index, arm in enumerate(paper.ARM_ORDER):
            scores["jobs"].append(
                {
                    "model": model,
                    "protocol": arm,
                    "seed": 0,
                    "status": "completed",
                    "positive_image_miou": 0.8 - model_index * 0.05 - arm_index * 0.005,
                    "positive_image_class_count": 21,
                    "validation_images": 68,
                }
            )
    score_path = tmp_path / "scores.json"
    paper.write(score_path, scores)
    sources = tmp_path / "qualified-sources.json"
    sources.write_bytes(b"[]\n")
    return source, splits, samples, score_path, sources


@pytest.mark.parametrize("matrix,count", [("focused60", 60), ("nested69", 69), ("full96", 96)])
def test_explicit_matrix_prepares_seed_major_priority_and_frozen_protocol(
    inputs, tmp_path, matrix, count
):
    source, splits, samples, scores, sources = inputs
    before = sources.read_bytes()
    out = tmp_path / "prepared"
    result = paper.prepare(
        matrix=matrix,
        split_policy="development",
        dataset_root=source,
        source_checkpoints=sources,
        development_scores=scores,
        out=out,
    )
    assert result["jobs"] == count and result["gpu_jobs_started"] == 0
    manifest = yaml.safe_load((out / "manifest.yaml").read_text())
    dataset = yaml.safe_load((out / "dataset.yaml").read_text())
    protocol = json.loads((out / "research-protocol.json").read_text())
    priority = json.loads((out / "training-priority.json").read_text())
    paper.validate_seed_priority(priority)
    assert [row["seed"] for row in priority["jobs"]] == sorted(
        row["seed"] for row in priority["jobs"]
    )
    assert manifest["research_protocol"] == protocol
    assert protocol["primary_models"] == paper.PRIMARY
    assert protocol["headline_protocol"] == paper.ARM_ORDER[0]
    assert protocol["source_training_seeds"] == [0] and protocol["rad_adaptation_seeds"] == [
        0,
        1,
        2,
    ]
    assert protocol["qualitative_seed"] == 0
    assert len(protocol["qualitative_keys"]) <= 6
    assert samples[-1]["key"] in protocol["qualitative_keys"]
    assert set(protocol["qualitative_keys"]) <= set(splits["test"])
    assert manifest["launch_requirements"]["expected_gpu_allowlist"] == list(range(10))
    assert dataset["stages"][0]["data"][0]["mapping"] == "paul-test-rtis"
    assert dataset["train"]["precision"] == "bf16-mixed"
    assert manifest["seeds"] == [0, 1, 2] and manifest["validation_enabled"]
    assert protocol["source_checkpoint_manifest"]["sha256"] == paper.digest(sources)
    assert sources.read_bytes() == before
    assert set(path.name for path in out.iterdir()) == {
        "manifest.yaml",
        "dataset.yaml",
        "training-priority.json",
        "research-protocol.json",
    }
    if matrix == "nested69":
        for model in paper.FAST[1:]:
            assert manifest["model_protocols"][model] == paper.ARM_ORDER[:1]
    if matrix == "full96":
        assert all(arms == paper.ARM_ORDER for arms in manifest["model_protocols"].values())


def test_finalfit_materializer_prepares_the_final_only_collection_contract(inputs, tmp_path):
    source, _, _, scores, sources = inputs
    final = tmp_path / "final"
    prepare_rad_finalfit.prepare(source, final, paper.digest(source / "splits.json"))
    out = tmp_path / "prepared"
    source_stage_spec = tmp_path / "source-stage-spec.json"
    source_stage_spec.write_text(
        '{"schema_version": 1, "source_stage_evaluation_authorized": true}\n'
    )
    source_spec_bytes = source_stage_spec.read_bytes()
    result = paper.prepare(
        matrix="staged24",
        split_policy="finalfit",
        dataset_root=final,
        source_checkpoints=sources,
        development_scores=scores,
        out=out,
        source_stage_spec=source_stage_spec,
    )
    manifest = yaml.safe_load((out / "manifest.yaml").read_text())
    assert manifest["validation_enabled"] is False
    assert manifest["collection_contract"] == "rtis-final-train-statistics-v2"
    assert manifest["primary_checkpoint"] == "final"
    assert result["jobs"] == 24
    assert len(manifest["models"]) == 8
    assert all(arms == paper.ARM_ORDER[:1] for arms in manifest["model_protocols"].values())
    assert manifest["research_protocol"]["primary_models"] == manifest["models"]
    assert manifest["research_protocol"]["initialization_ablation_protocols"] == []
    assert [
        row["evaluation_dataset"] for row in manifest["research_protocol"]["source_stage_reporting"]
    ] == ["Cityscapes", "RailSem19", "RAD"]
    priority = paper.read(out / "training-priority.json")
    assert len(priority["jobs"]) == 24
    assert {row["protocol"] for row in priority["jobs"]} == {paper.ARM_ORDER[0]}
    assert {row["seed"] for row in priority["jobs"]} == {0, 1, 2}
    assert list(manifest["protocols"]) == paper.ARM_ORDER[:1]
    assert manifest["research_protocol"]["source_stage_reports"] == {
        "spec": str(source_stage_spec.resolve()),
        "spec_sha256": hashlib.sha256(source_spec_bytes).hexdigest(),
    }
    assert source_stage_spec.read_bytes() == source_spec_bytes


def test_qualitative_selection_is_stable_and_covers_classes_groups_and_negative():
    names = ["mud-pumping", "rail"]
    samples = [
        {"key": "a", "group": "group-a", "class_pixels": {"0": 1, "1": 1}},
        {"key": "b", "group": "group-b", "class_pixels": {"1": 1}},
        {"key": "c", "group": "group-b", "class_pixels": {"0": 1}},
    ]
    splits = {"test": ["c", "b", "a"], "groups": {row["key"]: row["group"] for row in samples}}
    assert paper.qualitative_keys(samples, splits, names, 2) == ["a", "b"]
    assert paper.qualitative_keys(list(reversed(samples)), splits, names, 2) == ["a", "b"]
    with pytest.raises(ValueError, match="does not fit"):
        paper.qualitative_keys(samples, splits, names, 1)


@pytest.mark.parametrize("change", ["unknown-matrix", "wrong-split", "missing-score"])
def test_invalid_choice_or_missing_development_evidence_writes_nothing(inputs, tmp_path, change):
    source, _, _, scores, sources = inputs
    matrix, split = "nested69", "development"
    if change == "unknown-matrix":
        matrix = "auto"
    elif change == "wrong-split":
        split = "finalfit"
    else:
        evidence = paper.read(scores)
        evidence["jobs"].pop(0)
        paper.write(scores, evidence)
    out = tmp_path / "prepared"
    with pytest.raises(ValueError):
        paper.prepare(
            matrix=matrix,
            split_policy=split,
            dataset_root=source,
            source_checkpoints=sources,
            development_scores=scores,
            out=out,
        )
    assert not out.exists() and not out.with_name(out.name + ".preparing").exists()
