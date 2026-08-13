"""Starter-project packaging and overwrite-safety tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from segmentary.config import ExperimentConfig, deep_merge, from_dict, load_yaml
from segmentary.init_project import create_project, main
from segmentary.taxonomy import load_mapping, load_space


def test_create_project_is_a_complete_valid_config(tmp_path: Path) -> None:
    target = create_project(tmp_path / "starter", name="animals-v1")

    expected = {
        ".gitignore",
        "README.md",
        "base.yaml",
        "experiment.yaml",
        "model.yaml",
        "taxonomy/example/canonical.yaml",
        "taxonomy/example/my_dataset.yaml",
    }
    assert {
        path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()
    } == expected

    merged: dict = {}
    for filename in ("base.yaml", "model.yaml", "experiment.yaml"):
        merged = deep_merge(merged, load_yaml(target / filename))
    config = from_dict(ExperimentConfig, merged)
    assert config.name == "animals-v1"
    assert config.model.arch == "hf_auto"
    assert config.stages[0].data[0].loader == "folder"

    ignored = (target / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {
        "data/",
        "runs/",
        "debug/",
        "resolved.json",
        "resolved.yaml",
        "*.ckpt",
        "*.safetensors",
        "events.out.tfevents.*",
        "tensorboard/",
        "campaign.json",
        "lane_*_status.json",
        "*.log",
        ".env",
        "*.pem",
    } <= set(ignored)

    space = load_space(target / "taxonomy", "example")
    mapping = load_mapping(target / "taxonomy", space, "my_dataset")
    assert mapping.active_ids == (0, 1, 2)


def test_create_project_refuses_nonempty_destination_and_bad_name(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("user data", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        create_project(occupied)
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "user data"

    with pytest.raises(ValueError, match="project name"):
        create_project(tmp_path / "bad", name="spaces are unsafe")


def test_init_cli_prints_next_steps(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "cli-project"
    assert main([str(target), "--name", "demo"]) == 0
    output = capsys.readouterr().out
    assert str(target) in output
    assert "--print-config" in output


def test_wheel_contains_starter_and_repository_examples(built_distribution: Path) -> None:
    with zipfile.ZipFile(built_distribution) as wheel:
        names = set(wheel.namelist())
    assert "segmentary/templates/project/experiment.yaml" in names
    assert "segmentary/templates/project/taxonomy/example/canonical.yaml" in names
    assert any(name.endswith("share/segmentary/configs/base.yaml") for name in names)
    assert any(name.endswith("share/segmentary/taxonomy/example/canonical.yaml") for name in names)
