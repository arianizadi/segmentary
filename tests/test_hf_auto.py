"""Focused, download-free tests for the generic Hugging Face model path."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
import torch
from torch import nn

from segmentary.config import AugConfigSpec, ConfigError, ModelConfig, from_dict
from segmentary.data.loaders import aug_from_spec
from segmentary.models import hf_auto as hf_auto_module
from segmentary.models.factory import build_model
from segmentary.models.hf_auto import HFAutoDenseWrapper
from segmentary.models.tuning import apply_tuning

NUM_CLASSES = 3
SOURCE_CLASSES = 5


class TinyAttention(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        self.q_proj = nn.Linear(channels, channels)
        self.k_proj = nn.Linear(channels, channels)
        self.v_proj = nn.Linear(channels, channels)
        self.o_proj = nn.Linear(channels, channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x.permute(0, 2, 3, 1)
        x = self.o_proj(self.q_proj(x) + self.k_proj(x) + self.v_proj(x))
        return x.permute(0, 3, 1, 2)


class TinyBackbone(nn.Module):
    def __init__(self, channels: int = 8) -> None:
        super().__init__()
        self.stem = nn.Conv2d(3, channels, kernel_size=3, stride=2, padding=1)
        self.norm = nn.BatchNorm2d(channels, momentum=0.997)
        self.attention = TinyAttention(channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.attention(self.norm(self.stem(x)))


class TinyDecodeHead(nn.Module):
    def __init__(self, channels: int, num_labels: int) -> None:
        super().__init__()
        self.projection = nn.Conv2d(channels, channels, kernel_size=1)
        self.classifier = nn.Conv2d(channels, num_labels, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(torch.relu(self.projection(x)))


class TinyHFSegmentationModel(nn.Module):
    base_model_prefix = "encoder"

    def __init__(
        self,
        config: Any,
        *,
        base_model_prefix: str = "encoder",
        output_kind: str = "logits",
    ) -> None:
        super().__init__()
        self.base_model_prefix = base_model_prefix
        self.config = config
        self.encoder = TinyBackbone()
        self.decode_head = TinyDecodeHead(8, config.num_labels)
        self.output_kind = output_kind

    def forward(self, *, pixel_values: torch.Tensor) -> Any:
        logits = self.decode_head(self.encoder(pixel_values))
        if self.output_kind == "logits":
            return SimpleNamespace(logits=logits)
        if self.output_kind == "rank3":
            return SimpleNamespace(logits=logits.flatten(2))
        return SimpleNamespace(scores=logits)


InfoMutator = Callable[[dict[str, Any], TinyHFSegmentationModel, int, int], None]


def _install_fake_transformers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_classes: int = SOURCE_CLASSES,
    base_model_prefix: str = "encoder",
    output_kind: str = "logits",
    set_diagnostics: bool = False,
    mutate_info: InfoMutator | None = None,
    processor_mean: tuple[float, float, float] = (0.485, 0.456, 0.406),
    processor_std: tuple[float, float, float] = (0.229, 0.224, 0.225),
    rescale_factor: float = 1.0 / 255.0,
    processor_flip_channel_order: bool = False,
    processor_do_normalize: bool | None = True,
    processor_missing_fields: tuple[str, ...] = (),
) -> list[tuple[str, str, dict[str, Any]]]:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    class FakeConfig:
        def __init__(self) -> None:
            self.num_labels = source_classes
            self.original_num_labels = source_classes
            self.use_auxiliary_head = True

    class AutoConfig:
        @classmethod
        def from_pretrained(cls, model_id: str, **kwargs: Any) -> FakeConfig:
            calls.append(("config", model_id, deepcopy(kwargs)))
            return FakeConfig()

    class AutoModelForSemanticSegmentation:
        @classmethod
        def from_pretrained(cls, model_id: str, **kwargs: Any) -> Any:
            calls.append(("model", model_id, deepcopy(kwargs)))
            config = kwargs["config"]
            model = TinyHFSegmentationModel(
                config,
                base_model_prefix=base_model_prefix,
                output_kind=output_kind,
            )
            target = config.num_labels
            if source_classes == target:
                mismatched: list[Any] = []
            else:
                mismatched = [
                    (
                        "decode_head.classifier.weight",
                        (source_classes, 8, 1, 1),
                        tuple(model.decode_head.classifier.weight.shape),
                    ),
                    (
                        "decode_head.classifier.bias",
                        (source_classes,),
                        tuple(model.decode_head.classifier.bias.shape),
                    ),
                ]
            info = {
                "missing_keys": [],
                "unexpected_keys": [],
                "mismatched_keys": mismatched,
                "error_msgs": [],
            }
            if mutate_info is not None:
                mutate_info(info, model, source_classes, target)
            if set_diagnostics:
                info = {
                    key: set(value) if key != "error_msgs" else value for key, value in info.items()
                }
            return model, info

    class AutoImageProcessor:
        @classmethod
        def from_pretrained(cls, model_id: str, **kwargs: Any) -> Any:
            calls.append(("processor", model_id, deepcopy(kwargs)))
            fields = {
                "do_rescale": True,
                "rescale_factor": rescale_factor,
                "do_normalize": processor_do_normalize,
                "image_mean": processor_mean,
                "image_std": processor_std,
                "do_flip_channel_order": processor_flip_channel_order,
            }
            for field in processor_missing_fields:
                fields.pop(field)
            return SimpleNamespace(**fields)

    monkeypatch.setattr(
        hf_auto_module,
        "_transformers_auto_classes",
        lambda: (AutoConfig, AutoImageProcessor, AutoModelForSemanticSegmentation),
    )
    return calls


def _cfg(**changes: Any) -> ModelConfig:
    values: dict[str, Any] = {
        "arch": "hf_auto",
        "checkpoint": "org/semantic-model",
    }
    values.update(changes)
    return ModelConfig(**values)


def test_hf_auto_config_is_typed_and_requires_a_checkpoint() -> None:
    with pytest.raises(ConfigError, match="checkpoint is required"):
        ModelConfig(arch="hf_auto")
    with pytest.raises(ConfigError, match="trust_remote_code must stay false"):
        ModelConfig(
            arch="hf_auto",
            checkpoint="org/model",
            trust_remote_code=True,  # type: ignore[arg-type]
        )
    with pytest.raises(ConfigError, match="all-or-nothing"):
        _cfg(backbone_path="encoder")
    with pytest.raises(ConfigError, match="apply only to arch='hf_auto'"):
        ModelConfig(arch="segformer_b0", revision="deadbeef")
    with pytest.raises(ConfigError, match=r"must be finite and in \(0, 1\]"):
        _cfg(batch_norm_momentum=0.0)
    with pytest.raises(ConfigError, match=r"must be finite and in \(0, 1\]"):
        _cfg(batch_norm_momentum=float("nan"))
    with pytest.raises(ConfigError, match="apply only to arch='hf_auto'"):
        ModelConfig(arch="segformer_b0", batch_norm_momentum=0.003)
    with pytest.raises(ConfigError, match=r"must be finite and in \(0, 1\]"):
        ModelConfig(arch="segformer_b0", batch_norm_momentum=0.0)

    parsed = from_dict(
        ModelConfig,
        {
            "arch": "hf_auto",
            "checkpoint": "org/model",
            "revision": "deadbeef",
            "subfolder": "weights",
            "local_files_only": True,
            "trust_remote_code": False,
            "backbone_path": "encoder",
            "head_paths": ["decode_head"],
            "classifier_path": "decode_head.classifier",
            "batch_norm_momentum": 0.003,
        },
        "model",
    )
    assert parsed.revision == "deadbeef"
    assert parsed.subfolder == "weights"
    assert parsed.local_files_only is True
    assert parsed.head_paths == ["decode_head"]
    assert parsed.batch_norm_momentum == pytest.approx(0.003)


def test_hf_auto_applies_explicit_pytorch_batch_norm_momentum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transformers(monkeypatch)
    model = build_model(_cfg(batch_norm_momentum=0.003), NUM_CLASSES)

    batch_norms = [
        module for module in model.modules() if isinstance(module, nn.modules.batchnorm._BatchNorm)
    ]
    assert len(batch_norms) == 1
    assert batch_norms[0].momentum == pytest.approx(0.003)


def test_hf_auto_preserves_upstream_batch_norm_momentum_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transformers(monkeypatch)
    model = build_model(_cfg(), NUM_CLASSES)

    batch_norms = [
        module for module in model.modules() if isinstance(module, nn.modules.batchnorm._BatchNorm)
    ]
    assert len(batch_norms) == 1
    assert batch_norms[0].momentum == pytest.approx(0.997)


def test_batch_norm_momentum_override_requires_batch_norm() -> None:
    with pytest.raises(ValueError, match="has no PyTorch BatchNorm modules"):
        hf_auto_module._apply_batch_norm_momentum(nn.Conv2d(3, 4, 1), 0.003)


def test_auto_layout_load_audit_and_output_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fake_transformers(monkeypatch)
    cfg = _cfg(
        revision="immutable-sha",
        subfolder="model",
        local_files_only=True,
    )
    model = build_model(cfg, NUM_CLASSES)

    assert isinstance(model, HFAutoDenseWrapper)
    assert model.layout.backbone_path == "encoder"
    assert model.layout.head_paths == ("decode_head",)
    assert model.layout.classifier_path == "decode_head.classifier"
    assert model.source_num_labels == SOURCE_CLASSES
    assert model.model.config.use_auxiliary_head is False

    for kind, model_id, kwargs in calls:
        assert model_id == "org/semantic-model"
        assert kwargs["revision"] == "immutable-sha"
        assert kwargs["subfolder"] == "model"
        assert kwargs["local_files_only"] is True
        assert kwargs["trust_remote_code"] is False
        if kind == "model":
            assert kwargs["ignore_mismatched_sizes"] is True
            assert kwargs["output_loading_info"] is True

    image = torch.randn(2, 3, 17, 23)
    logits = model(image)
    assert logits.shape == (2, NUM_CLASSES, 17, 23)


def test_audited_inactive_backbone_module_stays_frozen_under_full_tuning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transformers(monkeypatch)
    cfg = _cfg(revision="a" * 40, inactive_parameter_paths=["encoder.attention"])
    model = apply_tuning(build_model(cfg, NUM_CLASSES), cfg)
    frozen = {name for name, parameter in model.named_parameters() if not parameter.requires_grad}

    assert frozen
    assert all(name.startswith("model.encoder.attention.") for name in frozen)
    assert any(
        name.startswith("model.encoder.stem.") and parameter.requires_grad
        for name, parameter in model.named_parameters()
    )
    assert all(parameter.requires_grad for parameter in model.model.decode_head.parameters())


@pytest.mark.parametrize("path", ["encoder.missing", "decode_head.projection", "encoder"])
def test_inactive_parameter_path_must_resolve_inside_the_backbone(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    _install_fake_transformers(monkeypatch)
    with pytest.raises(ValueError, match="inactive parameter path"):
        build_model(_cfg(revision="a" * 40, inactive_parameter_paths=[path]), NUM_CLASSES)


def test_transformers_set_loading_diagnostics_are_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transformers(monkeypatch, set_diagnostics=True)
    model = build_model(_cfg(), NUM_CLASSES)
    assert model.layout.classifier_path == "decode_head.classifier"


def test_only_a_deliberately_dropped_auxiliary_head_may_be_unexpected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def dropped_aux(info: dict[str, Any], *_args: Any) -> None:
        info["unexpected_keys"] = [
            "auxiliary_head.convs.0.convolution.weight",
            "auxiliary_head.classifier.weight",
        ]

    _install_fake_transformers(monkeypatch, mutate_info=dropped_aux)
    model = build_model(_cfg(), NUM_CLASSES)
    assert model.model.config.use_auxiliary_head is False


def test_dropped_auxiliary_head_is_allowed_when_label_count_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def dropped_aux(info: dict[str, Any], *_args: Any) -> None:
        info["unexpected_keys"] = ["auxiliary_head.classifier.weight"]

    _install_fake_transformers(
        monkeypatch,
        source_classes=NUM_CLASSES,
        mutate_info=dropped_aux,
    )
    model = build_model(_cfg(), NUM_CLASSES)
    assert model.source_num_labels == NUM_CLASSES


def test_unexpected_weight_outside_dropped_auxiliary_head_still_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unrelated(info: dict[str, Any], *_args: Any) -> None:
        info["unexpected_keys"] = ["decode_head.unaccounted.weight"]

    _install_fake_transformers(monkeypatch, mutate_info=unrelated)
    with pytest.raises(ValueError, match="partial pretrained load"):
        build_model(_cfg(), NUM_CLASSES)


def test_image_processor_normalization_is_applied_to_data_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transformers(
        monkeypatch,
        processor_mean=(0.5, 0.5, 0.5),
        processor_std=(0.5, 0.5, 0.5),
        processor_flip_channel_order=True,
    )
    model = build_model(_cfg(), NUM_CLASSES)
    aug = aug_from_spec(AugConfigSpec(), model)

    assert model.input_mean == (0.5, 0.5, 0.5)
    assert model.input_std == (0.5, 0.5, 0.5)
    assert model.input_channel_order == "bgr"
    assert aug.mean == model.input_mean
    assert aug.std == model.input_std
    assert aug.channel_order == "bgr"


def test_nonstandard_processor_rescaling_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transformers(monkeypatch, rescale_factor=1.0 / 127.5)
    with pytest.raises(ValueError, match="rescale_factor"):
        build_model(_cfg(), NUM_CLASSES)


@pytest.mark.parametrize("field", ["do_rescale", "rescale_factor", "do_normalize"])
def test_missing_processor_contract_field_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    _install_fake_transformers(monkeypatch, processor_missing_fields=(field,))
    with pytest.raises(ValueError, match=field):
        build_model(_cfg(), NUM_CLASSES)


def test_processor_without_normalization_uses_rescaled_pixels_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transformers(
        monkeypatch,
        processor_do_normalize=None,
        processor_flip_channel_order=True,
    )
    model = build_model(_cfg(), NUM_CLASSES)
    assert model.input_mean == (0.0, 0.0, 0.0)
    assert model.input_std == (1.0, 1.0, 1.0)
    assert model.input_channel_order == "bgr"


def test_explicit_advanced_layout_bypasses_unavailable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_transformers(monkeypatch, base_model_prefix="")
    model = build_model(
        _cfg(
            backbone_path="encoder",
            head_paths=["decode_head"],
            classifier_path="decode_head.classifier",
        ),
        NUM_CLASSES,
    )
    assert model.layout == model.layout.__class__(
        "encoder", ("decode_head",), "decode_head.classifier"
    )


def test_unsupported_layout_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_transformers(monkeypatch, base_model_prefix="")
    with pytest.raises(ValueError, match="advanced hf_auto layout"):
        build_model(_cfg(), NUM_CLASSES)


def test_only_classifier_shape_mismatch_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def add_backbone_gap(
        info: dict[str, Any], _model: TinyHFSegmentationModel, _source: int, _target: int
    ) -> None:
        info["missing_keys"].append("encoder.stem.weight")

    _install_fake_transformers(monkeypatch, mutate_info=add_backbone_gap)
    with pytest.raises(ValueError, match=r"partial pretrained load.*encoder\.stem\.weight"):
        build_model(_cfg(), NUM_CLASSES)


def test_classifier_mismatch_must_change_only_label_axis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def alter_kernel_shape(
        info: dict[str, Any], _model: TinyHFSegmentationModel, source: int, target: int
    ) -> None:
        info["mismatched_keys"][0] = (
            "decode_head.classifier.weight",
            (source, 8, 3, 3),
            (target, 8, 1, 1),
        )

    _install_fake_transformers(monkeypatch, mutate_info=alter_kernel_shape)
    with pytest.raises(ValueError, match="not a classifier-only label-axis change"):
        build_model(_cfg(), NUM_CLASSES)


def test_label_count_change_requires_every_classifier_tensor_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def drop_bias_mismatch(
        info: dict[str, Any], _model: TinyHFSegmentationModel, _source: int, _target: int
    ) -> None:
        info["mismatched_keys"].pop()

    _install_fake_transformers(monkeypatch, mutate_info=drop_bias_mismatch)
    with pytest.raises(ValueError, match="not exactly final classifier parameters"):
        build_model(_cfg(), NUM_CLASSES)


def test_equal_label_count_requires_an_exact_load(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_transformers(monkeypatch, source_classes=NUM_CLASSES)
    model = build_model(_cfg(), NUM_CLASSES)
    assert model.layout.classifier_path == "decode_head.classifier"


def test_reset_head_changes_only_exact_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_transformers(monkeypatch)
    model = build_model(_cfg(), NUM_CLASSES)
    before = {name: value.detach().clone() for name, value in model.named_parameters()}
    model.reset_head()
    changed = {
        name for name, value in model.named_parameters() if not torch.equal(value, before[name])
    }
    assert changed == {
        "model.decode_head.classifier.weight",
        "model.decode_head.classifier.bias",
    }


@pytest.mark.parametrize("mode", ["full", "frozen"])
def test_full_and_frozen_tuning_contracts(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    _install_fake_transformers(monkeypatch)
    cfg = _cfg(tuning=mode)
    model = apply_tuning(build_model(cfg, NUM_CLASSES), cfg)
    backbone = [
        parameter for module in model.backbone_modules() for parameter in module.parameters()
    ]
    heads = [
        parameter
        for name, parameter in model.named_parameters()
        if any(path in name for path in model.head_patterns())
    ]
    assert backbone and heads
    if mode == "full":
        assert all(parameter.requires_grad for parameter in model.parameters())
    else:
        assert all(not parameter.requires_grad for parameter in backbone)
        assert all(parameter.requires_grad for parameter in heads)


def test_lora_is_scoped_to_backbone_and_keeps_head_trainable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("peft")
    _install_fake_transformers(monkeypatch)
    cfg = _cfg(tuning="lora", lora_r=2)
    model = apply_tuning(build_model(cfg, NUM_CLASSES), cfg)

    lora = [name for name, _ in model.named_parameters() if "lora_" in name]
    assert lora and all("model.encoder" in name for name in lora)
    head_params = [
        parameter
        for name, parameter in model.named_parameters()
        if "decode_head" in name and "original_module" not in name
    ]
    assert head_params and all(parameter.requires_grad for parameter in head_params)
    assert model(torch.randn(1, 3, 12, 14)).shape == (1, NUM_CLASSES, 12, 14)


def test_inactive_paths_cannot_freeze_every_lora_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("peft")
    _install_fake_transformers(monkeypatch)
    cfg = _cfg(
        tuning="lora",
        lora_r=2,
        revision="a" * 40,
        inactive_parameter_paths=["encoder.attention"],
    )
    with pytest.raises(ValueError, match="froze every LoRA adapter"):
        apply_tuning(build_model(cfg, NUM_CLASSES), cfg)


@pytest.mark.parametrize(
    ("output_kind", "message"),
    [("missing", "output.logits"), ("rank3", "expected \\(N, C, H, W\\)")],
)
def test_non_dense_auto_outputs_fail_at_the_contract_boundary(
    monkeypatch: pytest.MonkeyPatch, output_kind: str, message: str
) -> None:
    _install_fake_transformers(monkeypatch, output_kind=output_kind)
    model = build_model(_cfg(), NUM_CLASSES)
    with pytest.raises(ValueError, match=message):
        model(torch.randn(1, 3, 8, 10))
