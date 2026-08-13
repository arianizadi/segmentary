"""Command-line parsing and configuration precedence for ``segmentary.train``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from segmentary.config import ExperimentConfig, from_dict, to_dict
from segmentary.train import main, parse_override


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("train.iters=100", {"train": {"iters": 100}}),
        ("optim.backbone_lr=0.00006", {"optim": {"backbone_lr": 0.00006}}),
        ("eval.sliding_window=true", {"eval": {"sliding_window": True}}),
        ("eval.tta_flip=false", {"eval": {"tta_flip": False}}),
        (
            'model.lora_targets=["q_proj","v_proj"]',
            {"model": {"lora_targets": ["q_proj", "v_proj"]}},
        ),
        ("train.ema_decay=null", {"train": {"ema_decay": None}}),
        ("model.arch=segformer_b2", {"model": {"arch": "segformer_b2"}}),
        ("a.b.c=7", {"a": {"b": {"c": 7}}}),
    ],
    ids=["int", "float", "true", "false", "list", "null", "bare-string", "dotted"],
)
def test_parse_override_decodes_json_scalars_and_dotted_keys(
    item: str, expected: dict[str, Any]
) -> None:
    assert parse_override(item) == expected


def test_parse_override_rejects_item_without_equals() -> None:
    with pytest.raises(ValueError, match="key=value"):
        parse_override("train.iters")


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(value), encoding="utf-8")


def _minimal_config() -> dict[str, Any]:
    return {
        "name": "first",
        "space": "example",
        "model": {"arch": "from-first", "checkpoint": "first-checkpoint"},
        "train": {"iters": 10, "batch_size": 2},
        "stages": [
            {
                "name": "city",
                "data": [{"name": "cityscapes", "root": "/datasets/cityscapes"}],
            }
        ],
    }


def test_later_files_win_then_set_overrides_win_over_all_files(tmp_path, capsys) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    _write_yaml(first, _minimal_config())
    _write_yaml(
        second,
        {
            "name": "second",
            "model": {"arch": "from-second"},
            "train": {"iters": 20},
        },
    )

    exit_code = main(
        [
            str(first),
            str(second),
            "--set",
            "train.iters=30",
            "--set",
            "model.arch=from-set",
            "--print-config",
        ]
    )
    printed = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert printed["name"] == "second"
    assert printed["model"]["arch"] == "from-set"
    assert printed["model"]["checkpoint"] == "first-checkpoint"
    assert printed["model"]["tuning"] == "full"
    assert printed["train"]["iters"] == 30
    assert printed["train"]["batch_size"] == 2
    assert printed["train"]["seed"] == 0


def test_print_config_exits_zero_and_stdout_is_exactly_one_json_document(tmp_path, capsys) -> None:
    config = tmp_path / "config.yaml"
    expected = _minimal_config()
    _write_yaml(config, expected)

    assert main([str(config), "--print-config"]) == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out) == to_dict(from_dict(ExperimentConfig, expected))
    assert captured.err == ""
