"""Direct coverage for every typed configuration validation rule.

These tests deliberately construct the dataclasses instead of exercising a
trainer side effect.  A malformed experiment should fail while its YAML is
being parsed, before data, model weights, or a GPU are touched.
"""

from __future__ import annotations

from typing import Any

import pytest

from segmentary.config import (
    AugConfigSpec,
    ConfigError,
    DataConfig,
    EvalConfig,
    ExperimentConfig,
    ModelConfig,
    StageConfig,
    from_dict,
)


def _data(name: str = "dataset") -> DataConfig:
    return DataConfig(name=name, root="/data")


def _stage(**changes: Any) -> StageConfig:
    values: dict[str, Any] = {"name": "stage", "data": [_data()]}
    values.update(changes)
    return StageConfig(**values)


def _experiment(**changes: Any) -> ExperimentConfig:
    values: dict[str, Any] = {
        "name": "experiment",
        "space": "classes",
        "model": ModelConfig(arch="toy"),
        "stages": [_stage()],
    }
    values.update(changes)
    return ExperimentConfig(**values)


@pytest.mark.parametrize("field_name", ["name", "root", "train_split", "val_split"])
@pytest.mark.parametrize("invalid", [" ", 7], ids=["blank", "not-string"])
def test_data_required_strings_are_nonempty_strings(field_name: str, invalid: Any) -> None:
    values: dict[str, Any] = {"name": "dataset", "root": "/data"}
    values[field_name] = invalid
    with pytest.raises(ConfigError, match=rf"data\.{field_name} must be a non-empty string"):
        DataConfig(**values)


@pytest.mark.parametrize("field_name", ["loader", "mapping"])
@pytest.mark.parametrize("invalid", [" ", 7], ids=["blank", "not-string"])
def test_data_optional_names_reject_blank_or_nonstring_values(
    field_name: str, invalid: Any
) -> None:
    with pytest.raises(ConfigError, match=rf"data\.{field_name} cannot be empty"):
        DataConfig(name="dataset", root="/data", **{field_name: invalid})


@pytest.mark.parametrize("loader_options", [[], {"": 1}, {1: "value"}])
def test_data_loader_options_require_a_mapping_with_named_string_keys(
    loader_options: Any,
) -> None:
    with pytest.raises(ConfigError, match="loader_options must be a mapping"):
        DataConfig(name="dataset", root="/data", loader_options=loader_options)


def test_data_limit_must_be_positive_when_present() -> None:
    with pytest.raises(ConfigError, match="limit must be at least 1"):
        DataConfig(name="dataset", root="/data", limit=0)


@pytest.mark.parametrize("crop", [(32,), (32, 0)])
def test_augmentation_crop_has_two_positive_dimensions(crop: tuple[int, ...]) -> None:
    with pytest.raises(ConfigError, match="crop must contain two positive sizes"):
        AugConfigSpec(crop=crop)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("scale_min", "scale_max"),
    [(0.0, 1.0), (1.1, 1.0)],
    ids=["nonpositive-minimum", "reversed-range"],
)
def test_augmentation_scale_range_is_positive_and_ordered(
    scale_min: float, scale_max: float
) -> None:
    with pytest.raises(ConfigError, match="0 < scale_min <= scale_max"):
        AugConfigSpec(scale_min=scale_min, scale_max=scale_max)


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [("hflip_p", -0.1), ("hflip_p", 1.1), ("color_jitter_p", -0.1), ("color_jitter_p", 1.1)],
)
def test_augmentation_probabilities_stay_in_closed_unit_interval(
    field_name: str, invalid: float
) -> None:
    with pytest.raises(ConfigError, match=rf"aug\.{field_name} must be in \[0, 1\]"):
        AugConfigSpec(**{field_name: invalid})


@pytest.mark.parametrize("invalid", [" ", 7], ids=["blank", "not-string"])
def test_model_arch_is_a_nonempty_string(invalid: Any) -> None:
    with pytest.raises(ConfigError, match=r"model\.arch must be a non-empty string"):
        ModelConfig(arch=invalid)


@pytest.mark.parametrize("invalid", [" ", 7], ids=["blank", "not-string"])
def test_model_checkpoint_rejects_blank_or_nonstring_values(invalid: Any) -> None:
    with pytest.raises(ConfigError, match=r"model\.checkpoint cannot be empty"):
        ModelConfig(arch="toy", checkpoint=invalid)


def test_model_never_allows_remote_repository_code() -> None:
    with pytest.raises(ConfigError, match="trust_remote_code must stay false"):
        ModelConfig(arch="toy", trust_remote_code=True)  # type: ignore[arg-type]


def test_smp_decoder_must_be_from_the_reviewed_allowlist() -> None:
    with pytest.raises(ConfigError, match="smp_arch must be one of"):
        ModelConfig(  # type: ignore[arg-type]
            arch="smp",
            smp_arch="Unknown",
            encoder_name="resnet34",
            encoder_weights="imagenet",
        )


@pytest.mark.parametrize("field_name", ["encoder_name", "encoder_weights"])
@pytest.mark.parametrize("invalid", [" ", 7], ids=["blank", "not-string"])
def test_smp_encoder_strings_reject_blank_or_nonstring_values(
    field_name: str, invalid: Any
) -> None:
    values: dict[str, Any] = {
        "arch": "smp",
        "smp_arch": "Unet",
        "encoder_name": "resnet34",
        "encoder_weights": "imagenet",
    }
    values[field_name] = invalid
    with pytest.raises(ConfigError, match=rf"model\.{field_name} cannot be empty"):
        ModelConfig(**values)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"arch": "smp"}, "smp_arch is required"),
        ({"arch": "smp", "smp_arch": "Unet"}, "encoder_name is required"),
        (
            {"arch": "smp", "smp_arch": "Unet", "encoder_name": "resnet34"},
            "encoder_weights is required",
        ),
        (
            {
                "arch": "smp",
                "smp_arch": "Unet",
                "encoder_name": "resnet34",
                "encoder_weights": "imagenet",
                "checkpoint": "weights.pth",
            },
            "checkpoint is not used",
        ),
        (
            {
                "arch": "smp",
                "smp_arch": "Unet",
                "encoder_name": "resnet34",
                "encoder_weights": "imagenet",
                "drop_path": 0.1,
            },
            "does not expose a portable stochastic-depth option",
        ),
    ],
    ids=["decoder", "encoder", "weights", "checkpoint", "drop-path"],
)
def test_smp_requires_complete_nonambiguous_construction(
    values: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        ModelConfig(**values)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("smp_arch", "Unet"), ("encoder_name", "resnet34"), ("encoder_weights", "imagenet")],
)
def test_smp_fields_are_rejected_by_other_architectures(field_name: str, value: Any) -> None:
    with pytest.raises(ConfigError, match=r"apply only to arch='smp'"):
        ModelConfig(arch="toy", **{field_name: value})


def test_smp_accepts_explicit_pretraining_or_explicit_scratch() -> None:
    pretrained = ModelConfig(
        arch="smp", smp_arch="Unet", encoder_name="resnet34", encoder_weights="imagenet"
    )
    scratch = ModelConfig(
        arch="smp", smp_arch="Unet", encoder_name="resnet34", encoder_weights="scratch"
    )

    assert pretrained.encoder_weights == "imagenet"
    assert scratch.encoder_weights == "scratch"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("revision", "commit"),
        ("subfolder", "weights"),
        ("local_files_only", True),
        ("backbone_path", "backbone"),
        ("head_paths", ["decode_head"]),
        ("classifier_path", "decode_head.classifier"),
    ],
)
def test_hf_auto_fields_are_rejected_by_other_architectures(field_name: str, value: Any) -> None:
    with pytest.raises(ConfigError, match=r"apply only to arch='hf_auto'"):
        ModelConfig(arch="toy", **{field_name: value})


def test_inactive_parameter_paths_are_limited_to_audited_composable_recipes() -> None:
    with pytest.raises(ConfigError, match="only to audited hf_auto or smp recipes"):
        ModelConfig(arch="toy", inactive_parameter_paths=["encoder.unused"])

    cfg = ModelConfig(
        arch="smp",
        smp_arch="Unet",
        encoder_name="resnet34",
        encoder_weights="imagenet",
        inactive_parameter_paths=["encoder.unused"],
    )
    assert cfg.inactive_parameter_paths == ["encoder.unused"]


def test_hf_auto_requires_a_checkpoint_identifier() -> None:
    with pytest.raises(ConfigError, match="checkpoint is required for arch='hf_auto'"):
        ModelConfig(arch="hf_auto")


@pytest.mark.parametrize("field_name", ["revision", "subfolder"])
def test_hf_auto_optional_identifiers_cannot_be_blank(field_name: str) -> None:
    with pytest.raises(ConfigError, match=rf"model\.{field_name} cannot be empty"):
        ModelConfig(arch="hf_auto", checkpoint="org/model", **{field_name: " "})


def test_hf_auto_rejects_nonportable_drop_path() -> None:
    with pytest.raises(ConfigError, match="drop_path is not portable"):
        ModelConfig(arch="hf_auto", checkpoint="org/model", drop_path=0.1)


@pytest.mark.parametrize(
    "paths",
    [
        [""],
        [" encoder.unused"],
        ["encoder..unused"],
        ["encoder.unused", "encoder.unused"],
        ["encoder", "encoder.unused"],
    ],
)
def test_hf_auto_inactive_parameter_paths_are_canonical_unique_and_disjoint(
    paths: list[str],
) -> None:
    with pytest.raises(ConfigError, match=r"inactive_parameter_paths|inactive parameter path"):
        ModelConfig(
            arch="hf_auto",
            checkpoint="org/model",
            revision="a" * 40,
            inactive_parameter_paths=paths,
        )


@pytest.mark.parametrize("revision", [None, "main", "A" * 40, "g" * 40])
def test_hf_auto_inactive_paths_require_immutable_lowercase_hex_revision(
    revision: str | None,
) -> None:
    with pytest.raises(ConfigError, match="immutable 40-character lowercase hex revision"):
        ModelConfig(
            arch="hf_auto",
            checkpoint="org/model",
            revision=revision,
            inactive_parameter_paths=["encoder.unused"],
        )


@pytest.mark.parametrize(
    "layout",
    [
        {"backbone_path": "backbone"},
        {"head_paths": ["decode_head"]},
        {"classifier_path": "decode_head.classifier"},
        {"backbone_path": "backbone", "head_paths": ["decode_head"]},
        {
            "backbone_path": "backbone",
            "classifier_path": "decode_head.classifier",
        },
        {
            "head_paths": ["decode_head"],
            "classifier_path": "decode_head.classifier",
        },
    ],
)
def test_hf_auto_explicit_layout_is_all_or_nothing(layout: dict[str, Any]) -> None:
    with pytest.raises(ConfigError, match="layout overrides are all-or-nothing"):
        ModelConfig(arch="hf_auto", checkpoint="org/model", **layout)


@pytest.mark.parametrize(
    "layout",
    [
        {
            "backbone_path": "",
            "head_paths": ["decode_head"],
            "classifier_path": "decode_head.classifier",
        },
        {
            "backbone_path": " backbone",
            "head_paths": ["decode_head"],
            "classifier_path": "decode_head.classifier",
        },
        {
            "backbone_path": "backbone",
            "head_paths": [".decode_head"],
            "classifier_path": "decode_head.classifier",
        },
        {
            "backbone_path": "backbone",
            "head_paths": ["decode_head."],
            "classifier_path": "decode_head.classifier",
        },
        {
            "backbone_path": "backbone",
            "head_paths": ["decode_head"],
            "classifier_path": "decode_head..classifier",
        },
    ],
    ids=["empty", "outer-whitespace", "leading-dot", "trailing-dot", "double-dot"],
)
def test_hf_auto_explicit_layout_paths_are_canonical(layout: dict[str, Any]) -> None:
    with pytest.raises(ConfigError, match="invalid hf_auto module path"):
        ModelConfig(arch="hf_auto", checkpoint="org/model", **layout)


def test_hf_auto_explicit_layout_rejects_duplicate_heads() -> None:
    with pytest.raises(ConfigError, match="head_paths contains duplicates"):
        ModelConfig(
            arch="hf_auto",
            checkpoint="org/model",
            backbone_path="backbone",
            head_paths=["decode_head", "decode_head"],
            classifier_path="decode_head.classifier",
        )


def test_hf_auto_classifier_must_belong_to_a_selected_head() -> None:
    with pytest.raises(ConfigError, match="classifier_path must be the selected head"):
        ModelConfig(
            arch="hf_auto",
            checkpoint="org/model",
            backbone_path="backbone",
            head_paths=["decode_head"],
            classifier_path="classifier",
        )


@pytest.mark.parametrize(
    ("backbone_path", "head_path"),
    [
        ("module", "module"),
        ("module", "module.decode_head"),
        ("module.backbone", "module"),
    ],
    ids=["equal", "head-under-backbone", "backbone-under-head"],
)
def test_hf_auto_backbone_and_head_paths_cannot_overlap(backbone_path: str, head_path: str) -> None:
    with pytest.raises(ConfigError, match="overlaps head path"):
        ModelConfig(
            arch="hf_auto",
            checkpoint="org/model",
            backbone_path=backbone_path,
            head_paths=[head_path],
            classifier_path=f"{head_path}.classifier",
        )


def test_hf_auto_accepts_discovery_or_a_complete_disjoint_layout() -> None:
    discovered = ModelConfig(arch="hf_auto", checkpoint="org/model")
    explicit = ModelConfig(
        arch="hf_auto",
        checkpoint="org/model",
        backbone_path="backbone",
        head_paths=["decode_head"],
        classifier_path="decode_head.classifier",
    )

    assert discovered.backbone_path is None
    assert explicit.classifier_path == "decode_head.classifier"


@pytest.mark.parametrize(
    ("arch", "base", "field_name", "invalid"),
    [
        ("hf_auto", {"checkpoint": "org/model"}, "revision", 1),
        ("hf_auto", {"checkpoint": "org/model"}, "subfolder", 1),
        ("hf_auto", {"checkpoint": "org/model"}, "local_files_only", "yes"),
        ("hf_auto", {"checkpoint": "org/model"}, "backbone_path", 1),
        ("hf_auto", {"checkpoint": "org/model"}, "head_paths", "decode_head"),
        ("hf_auto", {"checkpoint": "org/model"}, "classifier_path", 1),
        (
            "smp",
            {"smp_arch": "Unet", "encoder_name": "resnet34", "encoder_weights": "imagenet"},
            "encoder_name",
            1,
        ),
        (
            "smp",
            {"smp_arch": "Unet", "encoder_name": "resnet34", "encoder_weights": "imagenet"},
            "encoder_weights",
            1,
        ),
    ],
)
def test_new_model_fields_reject_incompatible_yaml_types(
    arch: str, base: dict[str, Any], field_name: str, invalid: Any
) -> None:
    raw = {"arch": arch, **base, field_name: invalid}
    with pytest.raises(ConfigError, match=rf"model\.{field_name}"):
        from_dict(ModelConfig, raw, "model")


def test_eval_can_disable_sliding_window_without_fake_window_constraints() -> None:
    cfg = EvalConfig(sliding_window=False, window=(), stride=())  # type: ignore[arg-type]
    assert not cfg.sliding_window


@pytest.mark.parametrize("invalid", [" ", 7], ids=["blank", "not-string"])
def test_stage_name_is_a_nonempty_string(invalid: Any) -> None:
    with pytest.raises(ConfigError, match=r"stage\.name must be a non-empty string"):
        StageConfig(name=invalid, data=[_data()])


@pytest.mark.parametrize("invalid", [7, " "], ids=["not-string", "blank"])
def test_stage_init_source_is_a_nonempty_string(invalid: Any) -> None:
    with pytest.raises(ConfigError, match="init_from must be a non-empty string"):
        _stage(init_from=invalid)


@pytest.mark.parametrize("invalid", [True, "heavy", 0.0])
def test_stage_sample_weights_are_positive_real_numbers(invalid: Any) -> None:
    with pytest.raises(ConfigError, match="sample_weights must all be positive numbers"):
        StageConfig(
            name="mixed",
            data=[_data("a"), _data("b")],
            sample_weights={"a": 1.0, "b": invalid},
        )


def test_stage_accepts_complete_positive_mixed_dataset_weights() -> None:
    cfg = StageConfig(
        name="mixed",
        data=[_data("a"), _data("b")],
        sample_weights={"a": 1, "b": 0.5},
    )
    assert cfg.sample_weights == {"a": 1, "b": 0.5}


@pytest.mark.parametrize("field_name", ["name", "space", "taxonomy_root", "output_root"])
@pytest.mark.parametrize("invalid", [" ", 7], ids=["blank", "not-string"])
def test_experiment_required_strings_are_nonempty_strings(field_name: str, invalid: Any) -> None:
    with pytest.raises(ConfigError, match=rf"experiment {field_name} must be a non-empty string"):
        _experiment(**{field_name: invalid})
