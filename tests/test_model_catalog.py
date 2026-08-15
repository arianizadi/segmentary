"""The model catalog probe is fail-closed and uses production train wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch
import yaml
from torch import Tensor, nn

from segmentary.model_catalog import (
    ModelProbeError,
    ProbeOptions,
    list_catalog,
    main,
    probe_configs,
)
from segmentary.models.outputs import QueryOutput, QueryPrediction, SegmentationOutput
from segmentary.models.wrappers import SegmentationModel, reinit_


class _TinyDenseModel(SegmentationModel):
    input_mean = (0.4, 0.5, 0.6)
    input_std = (0.2, 0.3, 0.4)
    input_channel_order = "rgb"
    input_normalization_source = "test_contract"

    def __init__(self, num_classes: int) -> None:
        super().__init__(num_classes)
        self.backbone = nn.Conv2d(3, 4, 3, padding=1)
        self.head = nn.Module()
        self.head.classifier = nn.Conv2d(4, num_classes, 1)

    def forward(self, pixel_values: Tensor) -> Tensor:
        return self._check_output(self.head.classifier(self.backbone(pixel_values)), pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return ("head.",)

    def backbone_modules(self) -> list[nn.Module]:
        return [self.backbone]

    def reset_head(self) -> None:
        assert reinit_(self.head.classifier) == 1


class _FixedSizeModel(_TinyDenseModel):
    def forward(self, pixel_values: Tensor) -> Tensor:
        if tuple(pixel_values.shape[-2:]) != (64, 96):
            raise ValueError("fixed input required")
        return super().forward(pixel_values)


class _BinaryDenseModel(SegmentationModel):
    input_mean = (0.4, 0.5, 0.6)
    input_std = (0.2, 0.3, 0.4)
    input_channel_order = "rgb"
    input_normalization_source = "test_contract"

    def __init__(self) -> None:
        super().__init__(2, output_channels=1, task="binary")
        self.backbone = nn.Conv2d(3, 4, 3, padding=1)
        self.head = nn.Module()
        self.head.classifier = nn.Conv2d(4, 1, 1)

    def forward(self, pixel_values: Tensor) -> Tensor:
        return self._check_output(self.head.classifier(self.backbone(pixel_values)), pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return ("head.",)

    def backbone_modules(self) -> list[nn.Module]:
        return [self.backbone]

    def reset_head(self) -> None:
        assert reinit_(self.head.classifier) == 1


class _QueryModel(_TinyDenseModel):
    supports_dense_ce = False
    supports_query_objective = True

    def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
        batch, _, _, _ = pixel_values.shape
        dense = self.forward(pixel_values)
        query_count = dense.shape[1]
        class_logits = dense.mean((-2, -1)).unsqueeze(1).expand(-1, query_count, -1)
        no_object = class_logits.new_zeros((batch, query_count, 1))
        return SegmentationOutput(
            query=QueryOutput(
                primary=QueryPrediction(
                    class_logits=torch.cat((class_logits, no_object), dim=-1),
                    mask_logits=dense,
                )
            )
        )


class _UnsupportedObjectiveModel(_TinyDenseModel):
    supports_dense_ce = False


def _write_yaml(path: Path, value: dict) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _experiment(tmp_path: Path, *, arch: str = "tiny") -> Path:
    taxonomy = tmp_path / "taxonomy" / "toy"
    taxonomy.mkdir(parents=True)
    _write_yaml(
        taxonomy / "canonical.yaml",
        {
            "name": "toy",
            "description": "probe test",
            "ignore_index": 255,
            "classes": [
                {"id": 0, "name": "background", "color": [0, 0, 0]},
                {"id": 1, "name": "object", "color": [255, 255, 255]},
            ],
            "thin_classes": [],
        },
    )
    config = tmp_path / "experiment.yaml"
    _write_yaml(
        config,
        {
            "name": "probe-test",
            "space": "toy",
            "taxonomy_root": str(tmp_path / "taxonomy"),
            "model": {"arch": arch},
            "optim": {
                "backbone_lr": 0.01,
                "head_lr_mult": 1.0,
                "weight_decay": 0.0,
                "llrd": 1.0,
                "grad_clip": 1.0,
            },
            "loss": {
                "task": "multiclass",
                "terms": [{"kind": "cross_entropy", "weight": 1.0}],
            },
            "stages": [
                {
                    "name": "smoke",
                    "data": [{"name": "unused", "root": "/not/opened"}],
                    "init_from": "pretrained",
                }
            ],
        },
    )
    return config


@pytest.mark.parametrize(
    "kwargs",
    [
        {"shapes": ((64, 96),)},
        {"shapes": ((64, 96), (64, 96))},
        {"shapes": ((64, 64), (65, 97))},
        {"batch_size": 0},
        {"steps": 0},
        {"precision": "fp16"},
    ],
)
def test_probe_options_reject_weak_or_ambiguous_protocols(kwargs) -> None:
    with pytest.raises(ValueError):
        ProbeOptions(**kwargs)


def test_list_catalog_type_checks_and_summarizes_recipes(tmp_path: Path) -> None:
    catalog = tmp_path / "models"
    catalog.mkdir()
    _write_yaml(catalog / "plain.yaml", {"model": {"arch": "segformer_b0"}})
    _write_yaml(
        catalog / "smp.yaml",
        {
            "model": {
                "arch": "smp",
                "smp_arch": "Unet",
                "encoder_name": "resnet34",
                "encoder_weights": "scratch",
            }
        },
    )

    record = list_catalog(catalog)

    assert record["recipe_count"] == 2
    assert record["catalog_dir"] == "models"
    assert [item["name"] for item in record["recipes"]] == ["plain", "smp"]
    assert [item["path"] for item in record["recipes"]] == ["plain.yaml", "smp.yaml"]
    assert str(tmp_path) not in json.dumps(record)
    assert record["recipes"][1]["composition"] == {
        "decoder": "Unet",
        "encoder": "resnet34",
        "encoder_weights": "scratch",
    }


def test_list_catalog_rejects_unknown_model_keys(tmp_path: Path) -> None:
    catalog = tmp_path / "models"
    catalog.mkdir()
    _write_yaml(catalog / "bad.yaml", {"model": {"arch": "segformer_b0", "typo": True}})
    with pytest.raises(ValueError, match="unknown key"):
        list_catalog(catalog)


def test_probe_runs_two_shapes_real_objective_gradients_and_optimizer(
    tmp_path: Path, monkeypatch
) -> None:
    config = _experiment(tmp_path)
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["stages"][0].update({"lr_scale": 0.1, "head_group_lr_scale": 0.5})
    _write_yaml(config, raw)
    monkeypatch.setattr(
        "segmentary.model_catalog.build_model",
        lambda _cfg, num_classes: _TinyDenseModel(num_classes),
    )
    monkeypatch.setattr(
        "segmentary.model_catalog.collect_env", lambda: {"torch": torch.__version__}
    )
    monkeypatch.setattr("segmentary.model_catalog.discover_git_root", lambda _paths: None)

    record = probe_configs(
        [config], options=ProbeOptions(shapes=((8, 12), (9, 13)), steps=2, seed=7)
    )

    assert record["status"] == "passed"
    assert [item["output"]["shape"] for item in record["shape_checks"]] == [
        [1, 2, 8, 12],
        [1, 2, 9, 13],
    ]
    assert len(record["step_checks"]) == 2
    assert all(item["gradients"]["all_present"] for item in record["step_checks"])
    assert all(item["gradients"]["all_finite"] for item in record["step_checks"])
    assert record["model"]["changed_tracked_tensors"]
    provenance = record["experiment"]["optimizer_provenance"]
    assert provenance["declared"]["backbone_lr"] == pytest.approx(0.01)
    assert provenance["stage_lr_scale"] == pytest.approx(0.1)
    assert provenance["stage_head_group_lr_scale"] == pytest.approx(0.5)
    assert provenance["effective_head_group_lr_scale"] == pytest.approx(0.5)
    assert record["experiment"]["optimizer"]["backbone_lr"] == pytest.approx(0.001)
    assert record["experiment"]["optimizer"]["head_lr_mult"] == pytest.approx(5.0)
    assert record["checks"]["production_objective_backward"] is True
    assert record["protocol"]["quality_benchmark"] is False


def test_probe_runs_explicit_dense_query_collapse_ablation(tmp_path: Path, monkeypatch) -> None:
    config = _experiment(tmp_path)
    monkeypatch.setattr(
        "segmentary.model_catalog.build_model", lambda _cfg, classes: _QueryModel(classes)
    )
    monkeypatch.setattr("segmentary.model_catalog.collect_env", lambda: {})
    monkeypatch.setattr("segmentary.model_catalog.discover_git_root", lambda _paths: None)

    record = probe_configs([config], options=ProbeOptions(shapes=((8, 12), (9, 13))))

    assert record["status"] == "passed"
    assert record["protocol"]["objective_kind"] == "dense"
    assert record["protocol"]["objective_contract"] == "experimental_dense_query_collapse"
    assert record["protocol"]["dense_query_ablation"] is True
    assert all("query_output" not in item for item in record["shape_checks"])
    assert "not native query training" in record["interpretation"]


def test_probe_rejects_model_with_no_supported_training_objective(
    tmp_path: Path, monkeypatch
) -> None:
    config = _experiment(tmp_path)
    monkeypatch.setattr(
        "segmentary.model_catalog.build_model",
        lambda _cfg, classes: _UnsupportedObjectiveModel(classes),
    )
    with pytest.raises(ModelProbeError, match="neither dense-objective nor raw-query"):
        probe_configs([config], options=ProbeOptions(shapes=((8, 12), (9, 13))))


def test_probe_dispatches_configured_query_objective(tmp_path: Path, monkeypatch) -> None:
    config = _experiment(tmp_path)
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["loss"] = {
        "task": "multiclass",
        "query": {
            "kind": "hungarian_query",
            "classification_weight": 2.0,
            "mask_bce_weight": 5.0,
            "dice_weight": 5.0,
        },
    }
    _write_yaml(config, raw)
    monkeypatch.setattr(
        "segmentary.model_catalog.build_model", lambda _cfg, classes: _QueryModel(classes)
    )
    monkeypatch.setattr("segmentary.model_catalog.collect_env", lambda: {})
    monkeypatch.setattr("segmentary.model_catalog.discover_git_root", lambda _paths: None)

    record = probe_configs(
        [config], options=ProbeOptions(shapes=((8, 12), (9, 13)), steps=2, seed=11)
    )

    assert record["status"] == "passed"
    assert record["protocol"]["objective_kind"] == "query"
    assert record["protocol"]["objective_contract"] == "native_query"
    assert record["protocol"]["dense_query_ablation"] is False
    assert record["protocol"]["objective"].endswith("query_training_objective")
    assert all("query_output" in item for item in record["shape_checks"])
    assert record["shape_checks"][0]["query_output"]["primary"]["class_logits"]["shape"] == [
        1,
        2,
        3,
    ]
    assert {"classification", "mask_bce", "dice", "total"} <= set(
        record["step_checks"][0]["loss_components"]
    )
    assert record["checks"]["all_trainable_gradients_present"] is True
    assert record["checks"]["classifier_or_head_changed"] is True


def test_probe_rejects_query_objective_for_dense_model(tmp_path: Path, monkeypatch) -> None:
    config = _experiment(tmp_path)
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["loss"] = {"task": "multiclass", "query": {"kind": "hungarian_query"}}
    _write_yaml(config, raw)
    monkeypatch.setattr(
        "segmentary.model_catalog.build_model", lambda _cfg, classes: _TinyDenseModel(classes)
    )
    with pytest.raises(ModelProbeError, match=r"requires raw QueryOutput.*dense model"):
        probe_configs([config], options=ProbeOptions(shapes=((8, 12), (9, 13))))


def test_probe_fails_loudly_for_fixed_size_model(tmp_path: Path, monkeypatch) -> None:
    config = _experiment(tmp_path)
    monkeypatch.setattr(
        "segmentary.model_catalog.build_model", lambda _cfg, classes: _FixedSizeModel(classes)
    )
    with pytest.raises(ModelProbeError, match="fixed input"):
        probe_configs([config], options=ProbeOptions(shapes=((64, 96), (65, 97))))


def test_probe_fails_loudly_for_invalid_normalization(tmp_path: Path, monkeypatch) -> None:
    config = _experiment(tmp_path)
    model = _TinyDenseModel(2)
    model.input_std = (0.2, 0.0, 0.4)
    monkeypatch.setattr("segmentary.model_catalog.build_model", lambda _cfg, _classes: model)
    with pytest.raises(ModelProbeError, match="standard deviations must be positive"):
        probe_configs([config], options=ProbeOptions(shapes=((8, 12), (9, 13))))


def test_probe_fails_loudly_for_task_and_output_channel_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    config = _experiment(tmp_path)
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["loss"] = {
        "task": "binary",
        "activation": "sigmoid",
        "terms": [{"kind": "binary_cross_entropy", "weight": 1.0}],
    }
    raw["model"] = {"arch": "native", "native": {"task": "binary"}}
    raw["taxonomy_root"] = str(tmp_path / "taxonomy")
    raw["space"] = "toy"
    taxonomy_path = tmp_path / "taxonomy" / "toy" / "canonical.yaml"
    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    taxonomy["classes"][1]["name"] = "foreground"
    _write_yaml(taxonomy_path, taxonomy)
    _write_yaml(config, raw)
    monkeypatch.setattr(
        "segmentary.model_catalog.build_model", lambda _cfg, classes: _TinyDenseModel(classes)
    )
    with pytest.raises(ModelProbeError, match=r"binary.*requires 1 model output channel"):
        probe_configs([config], options=ProbeOptions(shapes=((8, 12), (9, 13))))


def test_probe_runs_native_binary_one_logit_objective_and_optimizer(
    tmp_path: Path, monkeypatch
) -> None:
    config = _experiment(tmp_path)
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["model"] = {"arch": "native", "native": {"task": "binary"}}
    raw["loss"] = {
        "task": "binary",
        "terms": [{"kind": "binary_cross_entropy", "weight": 1.0}],
    }
    taxonomy_path = tmp_path / "taxonomy" / "toy" / "canonical.yaml"
    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    taxonomy["classes"][1]["name"] = "foreground"
    _write_yaml(taxonomy_path, taxonomy)
    _write_yaml(config, raw)
    monkeypatch.setattr(
        "segmentary.model_catalog.build_model", lambda _cfg, _classes: _BinaryDenseModel()
    )
    monkeypatch.setattr("segmentary.model_catalog.collect_env", lambda: {})
    monkeypatch.setattr("segmentary.model_catalog.discover_git_root", lambda _paths: None)

    record = probe_configs(
        [config], options=ProbeOptions(shapes=((8, 12), (9, 13)), steps=2, seed=13)
    )

    assert record["status"] == "passed"
    assert record["experiment"]["task"] == "binary"
    assert record["experiment"]["num_classes"] == 2
    assert record["experiment"]["output_channels"] == 1
    assert [item["output"]["shape"] for item in record["shape_checks"]] == [
        [1, 1, 8, 12],
        [1, 1, 9, 13],
    ]
    assert all(item["gradients"]["all_present"] for item in record["step_checks"])
    assert record["checks"]["classifier_or_head_changed"] is True


def test_cli_json_and_output_are_machine_readable(tmp_path: Path, capsys) -> None:
    catalog = tmp_path / "models"
    catalog.mkdir()
    _write_yaml(catalog / "plain.yaml", {"model": {"arch": "segformer_b0"}})
    output = tmp_path / "catalog.json"

    assert main(["list", "--config-dir", str(catalog), "--json", "--output", str(output)]) == 0
    stdout = json.loads(capsys.readouterr().out)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert stdout == saved
    assert saved["recipe_count"] == 1
    assert str(tmp_path) not in output.read_text(encoding="utf-8")


def test_cli_failure_is_nonzero_and_can_be_retained_as_json(tmp_path: Path, capsys) -> None:
    output = tmp_path / "failure.json"
    assert main(["list", "--config-dir", str(tmp_path / "missing"), "--output", str(output)]) == 1
    assert "could not locate" in capsys.readouterr().err
    failure = json.loads(output.read_text(encoding="utf-8"))
    assert failure["status"] == "failed"
    assert failure["error_type"] == "FileNotFoundError"
