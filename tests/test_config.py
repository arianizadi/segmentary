"""Typed configuration loading, validation, merging, and provenance hashing."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from segmentary.config import (
    ConfigError,
    DataConfig,
    EvalConfig,
    ExperimentConfig,
    LossSpec,
    ModelConfig,
    OptimConfig,
    StageConfig,
    TrainConfig,
    config_hash,
    deep_merge,
    from_dict,
    load_experiment,
    to_dict,
)


def _data(name: str = "cityscapes") -> DataConfig:
    return DataConfig(name=name, root=f"/datasets/{name}")


def _stage(name: str = "city", *, init_from: str = "pretrained") -> StageConfig:
    return StageConfig(name=name, data=[_data()], init_from=init_from)


def _experiment() -> ExperimentConfig:
    return ExperimentConfig(
        name="test", space="toy", model=ModelConfig(arch="toy"), stages=[_stage()]
    )


def _raw_experiment() -> dict[str, Any]:
    return {
        "name": "test",
        "space": "toy",
        "model": {"arch": "toy"},
        "stages": [
            {
                "name": "city",
                "data": [{"name": "cityscapes", "root": "/datasets/cityscapes"}],
            }
        ],
    }


def test_new_generic_fields_preserve_legacy_positional_config_meaning() -> None:
    data = DataConfig("cityscapes", "data/cityscapes", "railbridge", "split.json")
    model = ModelConfig("segformer_b0", "checkpoint", "frozen", "unified_head", 8)

    assert data.variant == "railbridge"
    assert data.split_file == "split.json"
    assert data.loader is None and data.mapping is None
    assert model.tuning == "frozen"
    assert model.head == "unified_head"
    assert model.lora_r == 8
    assert model.revision is None


@pytest.mark.parametrize(
    ("container_path", "message_path"),
    [
        ((), "ExperimentConfig"),
        (("model",), "model"),
        (("optim",), "optim"),
        (("train",), "train"),
        (("eval",), "eval"),
        (("loss",), "loss"),
        (("aug",), "aug"),
        (("stages", 0), "stages[0]"),
        (("stages", 0, "data", 0), "stages[0].data[0]"),
    ],
    ids=["root", "model", "optim", "train", "eval", "loss", "aug", "stage", "data"],
)
def test_unknown_keys_are_fatal_at_every_nesting_depth(
    container_path: tuple[str | int, ...], message_path: str
) -> None:
    raw = _raw_experiment()
    # Materialise optional nested sections so each dataclass boundary is tested.
    raw.update({"optim": {}, "train": {}, "eval": {}, "loss": {}, "aug": {}})
    container: Any = raw
    for part in container_path:
        container = container[part]
    container["typo_field"] = 123

    with pytest.raises(ConfigError) as caught:
        from_dict(ExperimentConfig, raw)

    message = str(caught.value)
    assert message_path in message
    assert "typo_field" in message
    assert "unknown key" in message


@pytest.mark.parametrize(
    ("raw", "path"),
    [
        (
            {
                "name": "missing-space",
                "model": {"arch": "toy"},
                "stages": _raw_experiment()["stages"],
            },
            "ExperimentConfig",
        ),
        (
            {"name": "missing-model", "space": "toy", "stages": _raw_experiment()["stages"]},
            "ExperimentConfig",
        ),
        (
            {
                "name": "missing-arch",
                "space": "toy",
                "model": {},
                "stages": _raw_experiment()["stages"],
            },
            "model",
        ),
    ],
    ids=["space", "model", "model-arch"],
)
def test_missing_required_fields_raise_config_error(raw: dict[str, Any], path: str) -> None:
    with pytest.raises(ConfigError) as caught:
        from_dict(ExperimentConfig, raw)
    assert path in str(caught.value)
    assert "missing" in str(caught.value)


def test_yaml_values_are_coerced_recursively_to_declared_types(tmp_path) -> None:
    path = tmp_path / "experiment.yaml"
    raw = _raw_experiment()
    raw.update(
        {
            "model": {
                "arch": "toy",
                "checkpoint": None,
                "tuning": "frozen",
                "head": "per_stage_head",
                "lora_targets": ["q_proj", "v_proj"],
                "drop_path": None,
            },
            "optim": {"llrd": 1, "betas": [0.8, 0.95], "grad_clip": None},
            "train": {"ema_decay": None, "devices": 2},
            "eval": {"window": [32, 48], "stride": [16, 24], "tta_scales": [1, 1.5]},
            "aug": {"crop": [24, 40]},
        }
    )
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    cfg = load_experiment([path])

    assert isinstance(cfg.model, ModelConfig)
    assert cfg.model.tuning == "frozen"  # Literal
    assert cfg.model.head == "per_stage_head"  # Literal
    assert cfg.model.checkpoint is None  # Optional
    assert cfg.model.drop_path is None  # Optional
    assert cfg.model.lora_targets == ["q_proj", "v_proj"]  # list
    assert isinstance(cfg.stages, list) and isinstance(cfg.stages[0], StageConfig)
    assert isinstance(cfg.stages[0].data[0], DataConfig)  # nested list/dataclass
    assert cfg.optim.betas == (0.8, 0.95)  # YAML list -> tuple
    assert cfg.eval.window == (32, 48)
    assert cfg.eval.tta_scales == [1.0, 1.5]  # recursive scalar coercion
    assert cfg.aug.crop == (24, 40)
    assert cfg.train.devices == 2  # int | str


@pytest.mark.parametrize(
    ("update", "message_path"),
    [
        ({"model": "toy"}, "model"),
        ({"train": {"iters": "many"}}, "train.iters"),
        ({"eval": {"window": [32]}}, "eval.window"),
        ({"train": {"devices": True}}, "train.devices"),
        ({"model": {"tuning": "almost-full"}}, "model.tuning"),
    ],
    ids=["dataclass", "scalar", "tuple-length", "union", "literal"],
)
def test_incompatible_yaml_types_fail_at_their_dotted_path(
    update: dict[str, Any], message_path: str
) -> None:
    raw = deep_merge(_raw_experiment(), update)
    with pytest.raises(ConfigError, match=message_path.replace(".", r"\.")):
        from_dict(ExperimentConfig, raw)


@pytest.mark.parametrize("llrd", [0.0, -0.1, 1.0001])
def test_optim_rejects_llrd_outside_open_closed_unit_interval(llrd: float) -> None:
    with pytest.raises(ConfigError, match="llrd must be in"):
        OptimConfig(llrd=llrd)


def test_optim_rejects_nonpositive_backbone_lr() -> None:
    with pytest.raises(ConfigError, match="backbone_lr must be positive"):
        OptimConfig(backbone_lr=0.0)


@pytest.mark.parametrize("tuning", ["invalid", "FULL"])
def test_model_rejects_unknown_tuning_mode(tuning: str) -> None:
    with pytest.raises(ConfigError, match="tuning must be one of"):
        ModelConfig(arch="toy", tuning=tuning)  # type: ignore[arg-type]


def test_model_rejects_unknown_head_strategy() -> None:
    with pytest.raises(ConfigError, match="head must be one of"):
        ModelConfig(arch="toy", head="shared")  # type: ignore[arg-type]


def test_lora_requires_positive_rank() -> None:
    with pytest.raises(ConfigError, match="lora_r > 0"):
        ModelConfig(arch="toy", tuning="lora", lora_r=0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"checkpoint": " "}, "checkpoint"),
        ({"lora_alpha": 0}, "lora_alpha"),
        ({"lora_dropout": 1.0}, "lora_dropout"),
    ],
)
def test_model_rejects_invalid_general_fields(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        ModelConfig(arch="toy", **kwargs)


def test_auxiliary_loss_requires_positive_weight() -> None:
    with pytest.raises(ConfigError, match="has no effect"):
        LossSpec(aux="lovasz", aux_weight=0.0)


def test_none_auxiliary_loss_rejects_nonzero_weight() -> None:
    with pytest.raises(ConfigError, match="aux_weight is set"):
        LossSpec(aux="none", aux_weight=0.2)


@pytest.mark.parametrize("ce_weight", [-0.1, -1.0])
def test_loss_rejects_negative_cross_entropy_weight(ce_weight: float) -> None:
    with pytest.raises(ConfigError, match="ce_weight must be non-negative"):
        LossSpec(ce_weight=ce_weight)


def test_loss_rejects_zero_total_weight() -> None:
    with pytest.raises(ConfigError, match="zero total weight"):
        LossSpec(ce_weight=0.0)


def test_loss_rejects_unknown_auxiliary_kind() -> None:
    with pytest.raises(ConfigError, match=r"loss\.aux must be one of"):
        LossSpec(aux="boundary")  # type: ignore[arg-type]


@pytest.mark.parametrize("label_smoothing", [-0.01, 1.0])
def test_loss_rejects_label_smoothing_outside_half_open_unit_interval(
    label_smoothing: float,
) -> None:
    with pytest.raises(ConfigError, match=r"label_smoothing must be in \[0, 1\)"):
        LossSpec(label_smoothing=label_smoothing)


def test_train_requires_positive_iterations() -> None:
    with pytest.raises(ConfigError, match="iters must be positive"):
        TrainConfig(iters=0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"batch_size": 0}, "batch_size"),
        ({"accum": 0}, "accum"),
        ({"num_workers": -1}, "num_workers"),
        ({"val_every": 0}, "val_every"),
        ({"ckpt_every": 0}, "ckpt_every"),
        ({"precision": ""}, "precision"),
    ],
)
def test_train_rejects_invalid_runtime_fields(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        TrainConfig(**kwargs)


@pytest.mark.parametrize("ema_decay", [0.0, -0.1, 1.0])
def test_train_rejects_invalid_ema_decay(ema_decay: float) -> None:
    with pytest.raises(ConfigError, match="ema_decay must be in"):
        TrainConfig(ema_decay=ema_decay)


@pytest.mark.parametrize(
    ("stride", "window"),
    [((0, 8), (16, 16)), ((17, 8), (16, 16)), ((8, -1), (16, 16))],
)
def test_sliding_window_stride_must_be_positive_and_fit_window(
    stride: tuple[int, int], window: tuple[int, int]
) -> None:
    with pytest.raises(ConfigError, match="stride"):
        EvalConfig(stride=stride, window=window)


@pytest.mark.parametrize(
    ("window", "stride"),
    [((16,), (8,)), ((16, 16), (8,)), ((16,), (8, 8))],
)
def test_eval_config_constructor_requires_two_dimensional_window_and_stride(
    window: tuple[int, ...], stride: tuple[int, ...]
):
    with pytest.raises(ConfigError, match="exactly 2 values"):
        EvalConfig(window=window, stride=stride)


def test_eval_config_rejects_negative_workers() -> None:
    with pytest.raises(ConfigError, match="num_workers"):
        EvalConfig(num_workers=-1)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"batch_size": 0}, "batch_size"),
        ({"tta_scales": [0.0]}, "tta_scales"),
        ({"boundary_tolerance_frac": -0.1}, "boundary_tolerance_frac"),
    ],
)
def test_eval_rejects_invalid_general_fields(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        EvalConfig(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"root": ""}, "root"),
        ({"loader": " "}, "loader"),
        ({"mapping": ""}, "mapping"),
        ({"limit": 0}, "limit"),
        ({"loader_options": {"": True}}, "loader_options"),
    ],
)
def test_data_rejects_invalid_portable_loader_fields(kwargs: dict[str, Any], message: str) -> None:
    values: dict[str, Any] = {"name": "dataset", "root": "/data"}
    values.update(kwargs)
    with pytest.raises(ConfigError, match=message):
        DataConfig(**values)


def test_stage_requires_at_least_one_dataset() -> None:
    with pytest.raises(ConfigError, match="has no datasets"):
        StageConfig(name="empty", data=[])


def test_stage_rejects_duplicate_dataset_names() -> None:
    with pytest.raises(ConfigError, match="lists a dataset twice"):
        StageConfig(name="mixed", data=[_data(), _data()])


def test_single_dataset_stage_rejects_even_empty_sample_weights_mapping() -> None:
    with pytest.raises(ConfigError, match="sample_weights but has one dataset"):
        StageConfig(name="single", data=[_data()], sample_weights={})


def test_mixed_stage_validates_weight_identity_and_values() -> None:
    data = [_data("a"), _data("b")]
    with pytest.raises(ConfigError, match="exactly match"):
        StageConfig(name="mixed", data=data, sample_weights={"a": 1.0})
    with pytest.raises(ConfigError, match="positive numbers"):
        StageConfig(name="mixed", data=data, sample_weights={"a": 1.0, "b": 0.0})


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"iters": 0}, "iters"),
        ({"lr_scale": 0.0}, "lr_scale"),
        ({"init_from": ""}, "init_from"),
    ],
)
def test_stage_rejects_invalid_schedule_fields(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        StageConfig(name="stage", data=[_data()], **kwargs)


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf"), True, "1.0"])
def test_stage_rejects_invalid_head_group_lr_scale(value: object) -> None:
    with pytest.raises(ConfigError, match="head_group_lr_scale must be a positive finite"):
        StageConfig(
            name="stage",
            data=[_data()],
            head_group_lr_scale=value,  # type: ignore[arg-type]
        )


def test_head_group_scale_is_generic_and_has_no_classifier_only_floor() -> None:
    stage = StageConfig(
        name="target",
        data=[_data()],
        reset_head=True,
        lr_scale=0.1,
        head_group_lr_scale=0.05,
    )
    assert to_dict(stage)["head_group_lr_scale"] == pytest.approx(0.05)


def test_full_transfer_v2_has_distinct_20k_and_40k_evidence_budget() -> None:
    path = (
        Path(__file__).parents[1]
        / "configs/campaigns/experiments/city_checkpoint_rs_full_adaptation_v2.yaml"
    )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    stage = raw["stages"][0]

    assert stage["init_from"] == "/dependency/cityscapes/last.ckpt"
    assert stage["reset_head"] is True
    assert stage["iters"] == 40_000
    assert stage["lr_scale"] == pytest.approx(0.1)
    assert stage["head_group_lr_scale"] == pytest.approx(1.0)
    assert 20_000 % 4_000 == 0
    assert stage["iters"] % 4_000 == 0


def test_experiment_requires_at_least_one_stage() -> None:
    with pytest.raises(ConfigError, match="defines no stages"):
        ExperimentConfig(name="empty", space="toy", model=ModelConfig(arch="toy"))


def test_experiment_rejects_duplicate_stage_names() -> None:
    with pytest.raises(ConfigError, match="duplicate stage name"):
        ExperimentConfig(
            name="duplicate",
            space="toy",
            model=ModelConfig(arch="toy"),
            stages=[_stage("same"), _stage("same")],
        )


def test_first_stage_cannot_initialise_from_previous() -> None:
    with pytest.raises(ConfigError, match="first stage cannot"):
        ExperimentConfig(
            name="bad-chain",
            space="toy",
            model=ModelConfig(arch="toy"),
            stages=[_stage(init_from="previous")],
        )


def test_deep_merge_recurses_into_mappings_and_replaces_lists() -> None:
    base = {
        "model": {"arch": "old", "nested": {"keep": 1, "replace": 2}},
        "stages": [{"name": "old"}],
        "unchanged": True,
    }
    override = {
        "model": {"nested": {"replace": 99, "new": 3}},
        "stages": [{"name": "new"}],
    }
    original_base = copy.deepcopy(base)
    original_override = copy.deepcopy(override)

    assert deep_merge(base, override) == {
        "model": {"arch": "old", "nested": {"keep": 1, "replace": 99, "new": 3}},
        "stages": [{"name": "new"}],
        "unchanged": True,
    }
    assert base == original_base
    assert override == original_override


def _changed_leaf(value: Any) -> Any:
    if value is None:
        return "was-none"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 0.125
    if isinstance(value, str):
        return value + "-changed"
    raise AssertionError(f"unhandled config leaf {value!r}")


def _single_leaf_mutations(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Yield copies in which exactly one scalar or empty collection changed."""
    if isinstance(value, dict):
        if not value:
            yield path, {"new": 1}
            return
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            for changed_path, changed_child in _single_leaf_mutations(child, child_path):
                changed = copy.deepcopy(value)
                changed[key] = changed_child
                yield changed_path, changed
        return
    if isinstance(value, list):
        if not value:
            yield path, ["new"]
            return
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            for changed_path, changed_child in _single_leaf_mutations(child, child_path):
                changed = copy.deepcopy(value)
                changed[index] = changed_child
                yield changed_path, changed
        return
    yield path, _changed_leaf(value)


def test_config_hash_is_process_stable_and_sensitive_to_every_serialised_field() -> None:
    cfg = _experiment()
    payload = to_dict(cfg)
    expected = config_hash(cfg)

    # Key insertion order must not affect the result.
    assert config_hash(dict(reversed(list(payload.items())))) == expected
    assert config_hash(payload) == expected

    # Independent interpreters with different hash randomisation seeds must agree.
    encoded = json.dumps(payload, sort_keys=False)
    code = (
        "import json; from segmentary.config import config_hash; "
        f"print(config_hash(json.loads({encoded!r})))"
    )
    observed = []
    for seed in ("1", "987654"):
        proc = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        observed.append(proc.stdout.strip())
    assert observed == [expected, expected]

    mutations = list(_single_leaf_mutations(payload))
    assert len(mutations) >= 50, "fixture stopped exercising a meaningful share of config fields"
    for changed_path, changed_payload in mutations:
        assert config_hash(changed_payload) != expected, changed_path
