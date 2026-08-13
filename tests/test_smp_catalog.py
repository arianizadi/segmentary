"""Real contract coverage for the explicit SMP decoder/encoder catalog."""

from __future__ import annotations

import gc
import os
from pathlib import Path

import pytest
import torch
import torch.nn.functional as F
from torch import nn

from segmentary.config import (
    ConfigError,
    ModelConfig,
    OptimConfig,
    from_dict,
    load_experiment,
    load_yaml,
)
from segmentary.data.loaders import input_normalization
from segmentary.engine.optim import build_optimizer
from segmentary.models.factory import SMP_DECODERS, build_model
from segmentary.models.tuning import apply_tuning

NUM_CLASSES = 5
ROOT = Path(__file__).resolve().parents[1]
SMP_RECIPES = {
    "smp_deeplabv3_resnet50.yaml": "smp-deeplabv3-resnet50",
    "smp_deeplabv3plus_resnet101.yaml": "smp-deeplabv3plus-resnet101",
    "smp_fpn_resnet50.yaml": "smp-fpn-resnet50",
    "smp_linknet_mobilenet_v2.yaml": "smp-linknet-mobilenet-v2",
    "smp_manet_efficientnet_b0.yaml": "smp-manet-efficientnet-b0",
    "smp_pan_resnext50.yaml": "smp-pan-resnext50",
    "smp_pspnet_mobilenet_v2.yaml": "smp-pspnet-mobilenet-v2",
    "smp_unet_resnet34.yaml": "smp-unet-resnet34",
    "smp_unetplusplus_efficientnet_b0.yaml": "smp-unetplusplus-efficientnet-b0",
    "smp_upernet_mit_b0.yaml": "smp-upernet-mit-b0",
    "smp_upernet_resnet101.yaml": "smp-upernet-resnet101",
}


def _scratch_config(decoder: str, *, tuning: str = "full") -> ModelConfig:
    return ModelConfig(
        arch="smp",
        smp_arch=decoder,  # type: ignore[arg-type] -- exercised as runtime input
        encoder_name="resnet18",
        encoder_weights="scratch",
        tuning=tuning,  # type: ignore[arg-type] -- exercised as runtime input
    )


@pytest.mark.parametrize("decoder", SMP_DECODERS)
def test_every_advertised_smp_decoder_has_real_dense_backward_and_frozen_contract(
    decoder: str,
) -> None:
    """Construct the real model without downloads, then exercise tuning and gradients."""
    model = build_model(_scratch_config(decoder, tuning="frozen"), NUM_CLASSES)
    named_parameters = dict(model.named_parameters())
    module_ids = {id(module) for module in model.modules()}

    assert model.num_classes == NUM_CLASSES
    assert model.supports_dense_ce is True
    assert all(id(backbone) in module_ids for backbone in model.backbone_modules())
    for pattern in model.head_patterns():
        assert any(pattern in name for name in named_parameters), pattern

    apply_tuning(model, _scratch_config(decoder, tuning="frozen"))
    model.train()
    classifier_before = [
        parameter.detach().clone() for parameter in model.model.segmentation_head.parameters()
    ]
    optimizer = build_optimizer(model, OptimConfig(), model.head_patterns())
    optimizer.zero_grad(set_to_none=True)
    size = 128 if decoder == "PAN" else 64
    inputs = torch.randn(2, 3, size, size)
    logits = model(inputs)
    assert logits.shape == (2, NUM_CLASSES, size, size)
    assert bool(torch.isfinite(logits).all())

    logits.square().mean().backward()
    backbone_parameters = [
        parameter for backbone in model.backbone_modules() for parameter in backbone.parameters()
    ]
    head_parameters = [
        parameter
        for name, parameter in model.named_parameters()
        if any(pattern in name for pattern in model.head_patterns())
    ]
    assert backbone_parameters and all(
        not parameter.requires_grad for parameter in backbone_parameters
    )
    assert all(parameter.grad is None for parameter in backbone_parameters)
    assert head_parameters and all(parameter.requires_grad for parameter in head_parameters)
    assert all(
        parameter.grad is not None and bool(torch.isfinite(parameter.grad).all())
        for parameter in head_parameters
    )
    optimizer.step()
    assert any(
        not torch.equal(before, after)
        for before, after in zip(
            classifier_before, model.model.segmentation_head.parameters(), strict=True
        )
    )

    del logits, inputs, model
    gc.collect()


def test_smp_requires_an_explicit_pretrained_or_scratch_choice() -> None:
    with pytest.raises(ConfigError, match="encoder_weights is required"):
        ModelConfig(arch="smp", smp_arch="Unet", encoder_name="resnet34")
    pretrained = ModelConfig(
        arch="smp", smp_arch="Unet", encoder_name="resnet34", encoder_weights="imagenet"
    )
    scratch = from_dict(
        ModelConfig,
        {
            "arch": "smp",
            "smp_arch": "Unet",
            "encoder_name": "resnet34",
            "encoder_weights": "scratch",
        },
    )

    assert pretrained.encoder_weights == "imagenet"
    assert scratch.encoder_weights == "scratch"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"encoder_name": "resnet18"}, "smp_arch is required"),
        ({"smp_arch": "Unet"}, "encoder_name is required"),
        ({"smp_arch": "unet", "encoder_name": "resnet18"}, "smp_arch must be one of"),
        ({"smp_arch": "Unet", "encoder_name": " "}, "encoder_name"),
        (
            {"smp_arch": "Unet", "encoder_name": "resnet18", "encoder_weights": " "},
            "encoder_weights",
        ),
        (
            {
                "smp_arch": "Unet",
                "encoder_name": "resnet18",
                "encoder_weights": "imagenet",
                "checkpoint": "resnet50",
            },
            "checkpoint is not used",
        ),
        (
            {
                "smp_arch": "Unet",
                "encoder_name": "resnet18",
                "encoder_weights": "imagenet",
                "drop_path": 0.1,
            },
            "stochastic-depth",
        ),
    ],
)
def test_invalid_smp_configurations_fail_before_model_construction(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        ModelConfig(arch="smp", **kwargs)  # type: ignore[arg-type]


def test_smp_only_yaml_keys_are_fatal_on_other_architectures() -> None:
    with pytest.raises(ConfigError, match="apply only to arch='smp'"):
        from_dict(
            ModelConfig,
            {"arch": "segformer_b0", "encoder_name": "resnet34"},
        )


def test_pretrained_weight_failure_is_not_retried_as_scratch(monkeypatch) -> None:
    import segmentation_models_pytorch as smp

    attempts: list[dict[str, object]] = []

    def fail_once(**kwargs: object) -> nn.Module:
        attempts.append(kwargs)
        raise RuntimeError("pretrained weight download failed")

    monkeypatch.setattr(smp, "Unet", fail_once)
    with pytest.raises(RuntimeError, match="pretrained weight download failed"):
        build_model(
            ModelConfig(
                arch="smp",
                smp_arch="Unet",
                encoder_name="resnet34",
                encoder_weights="imagenet",
            ),
            NUM_CLASSES,
        )

    assert len(attempts) == 1
    assert attempts[0]["encoder_weights"] == "imagenet"


class _TinyEncoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.stem = nn.Conv2d(3, 4, 1)
        self.unused = nn.Conv2d(4, 4, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.stem(inputs)


class _TinySMP(nn.Module):
    def __init__(self, classes: int) -> None:
        super().__init__()
        self.encoder = _TinyEncoder()
        self.decoder = nn.Conv2d(4, 4, 1)
        self.segmentation_head = nn.Conv2d(4, classes, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.segmentation_head(self.decoder(self.encoder(inputs)))


def test_smp_encoder_preprocessing_is_exposed_and_recordable(monkeypatch) -> None:
    import segmentation_models_pytorch as smp
    from segmentation_models_pytorch import encoders

    monkeypatch.setattr(smp, "Unet", lambda **kwargs: _TinySMP(int(kwargs["classes"])))
    monkeypatch.setattr(
        encoders,
        "get_preprocessing_params",
        lambda *_args, **_kwargs: {
            "input_space": "BGR",
            "input_range": [0, 1],
            "mean": [0.1, 0.2, 0.3],
            "std": [0.4, 0.5, 0.6],
        },
    )
    model = build_model(
        ModelConfig(
            arch="smp",
            smp_arch="Unet",
            encoder_name="audited_encoder",
            encoder_weights="audited_weights",
        ),
        NUM_CLASSES,
    )

    assert input_normalization(model) == {
        "mean": [0.1, 0.2, 0.3],
        "std": [0.4, 0.5, 0.6],
        "channel_order": "bgr",
        "source": "smp_encoder_settings",
    }


def test_smp_encoder_with_unsupported_pixel_range_fails_before_construction(monkeypatch) -> None:
    import segmentation_models_pytorch as smp
    from segmentation_models_pytorch import encoders

    constructed = False

    def construct(**kwargs: object) -> nn.Module:
        nonlocal constructed
        constructed = True
        return _TinySMP(int(kwargs["classes"]))

    monkeypatch.setattr(smp, "Unet", construct)
    monkeypatch.setattr(
        encoders,
        "get_preprocessing_params",
        lambda *_args, **_kwargs: {
            "input_space": "RGB",
            "input_range": [0, 255],
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        },
    )

    with pytest.raises(ValueError, match="unsupported input_range"):
        build_model(
            ModelConfig(
                arch="smp",
                smp_arch="Unet",
                encoder_name="unsupported_encoder",
                encoder_weights="unsupported_weights",
            ),
            NUM_CLASSES,
        )
    assert constructed is False


def test_smp_inactive_parameter_paths_are_exact_and_fail_if_stale(monkeypatch) -> None:
    import segmentation_models_pytorch as smp

    monkeypatch.setattr(smp, "Unet", lambda **kwargs: _TinySMP(int(kwargs["classes"])))
    cfg = ModelConfig(
        arch="smp",
        smp_arch="Unet",
        encoder_name="resnet34",
        encoder_weights="scratch",
        inactive_parameter_paths=["encoder.unused"],
    )
    model = apply_tuning(build_model(cfg, NUM_CLASSES), cfg)
    assert all(not parameter.requires_grad for parameter in model.model.encoder.unused.parameters())
    assert all(parameter.requires_grad for parameter in model.model.encoder.stem.parameters())
    assert all(parameter.requires_grad for parameter in model.model.decoder.parameters())

    stale = ModelConfig(
        arch="smp",
        smp_arch="Unet",
        encoder_name="resnet34",
        encoder_weights="scratch",
        inactive_parameter_paths=["encoder.missing"],
    )
    with pytest.raises(ValueError, match=r"inactive parameter path.*does not exist"):
        build_model(stale, NUM_CLASSES)

    invalid_head = ModelConfig(
        arch="smp",
        smp_arch="Unet",
        encoder_name="resnet34",
        encoder_weights="scratch",
        inactive_parameter_paths=["decoder"],
    )
    with pytest.raises(ValueError, match="strict descendant of encoder"):
        build_model(invalid_head, NUM_CLASSES)


def test_smp_scratch_mode_uses_explicit_default_preprocessing(monkeypatch) -> None:
    import segmentation_models_pytorch as smp
    from segmentation_models_pytorch import encoders

    monkeypatch.setattr(smp, "Unet", lambda **kwargs: _TinySMP(int(kwargs["classes"])))

    def unexpected(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("scratch mode must not request pretrained preprocessing")

    monkeypatch.setattr(encoders, "get_preprocessing_params", unexpected)
    model = build_model(_scratch_config("Unet"), NUM_CLASSES)
    assert input_normalization(model) == {
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "channel_order": "rgb",
        "source": "imagenet_scratch_default",
    }


@pytest.mark.parametrize(
    ("alias", "constructor_name"),
    [
        ("deeplabv3plus_r101", "DeepLabV3Plus"),
        ("upernet_r101", "UPerNet"),
    ],
)
def test_legacy_smp_aliases_keep_checkpoint_as_encoder_override(
    alias: str, constructor_name: str, monkeypatch
) -> None:
    import segmentation_models_pytorch as smp

    seen: dict[str, object] = {}

    def construct(**kwargs: object) -> nn.Module:
        seen.update(kwargs)
        return _TinySMP(int(kwargs["classes"]))

    monkeypatch.setattr(smp, constructor_name, construct)
    model = build_model(ModelConfig(arch=alias, checkpoint="resnet18"), NUM_CLASSES)

    assert model(torch.randn(1, 3, 16, 16)).shape == (1, NUM_CLASSES, 16, 16)
    assert seen == {
        "encoder_name": "resnet18",
        "encoder_weights": "imagenet",
        "in_channels": 3,
        "classes": NUM_CLASSES,
    }


def test_shipped_smp_configs_cover_the_entire_allowlist() -> None:
    config_root = Path(__file__).parents[1] / "configs" / "models"
    configs = sorted(config_root.glob("smp_*.yaml"))
    parsed = [from_dict(ModelConfig, load_yaml(path)["model"]) for path in configs]

    assert {config.smp_arch for config in parsed} == set(SMP_DECODERS)
    assert all(config.arch == "smp" for config in parsed)
    assert all(config.encoder_name for config in parsed)


def test_every_shipped_smp_recipe_has_point_of_choice_documentation() -> None:
    found = {path.name for path in (ROOT / "configs/models").glob("smp_*.yaml")}
    assert found == set(SMP_RECIPES)
    for recipe, slug in SMP_RECIPES.items():
        text = (ROOT / "docs/catalog/models" / slug / "README.md").read_text()
        assert recipe in text
        lowered = text.lower()
        assert "pros" in lowered and "cons" in lowered
        assert "benchmark" in lowered


@pytest.mark.slow
@pytest.mark.gpu
@pytest.mark.parametrize("recipe", sorted(SMP_RECIPES))
def test_real_pretrained_smp_recipe_runs_four_bf16_optimizer_steps(recipe: str) -> None:
    if os.environ.get("SEGMENTARY_RUN_SMP_CATALOG") != "1":
        pytest.skip("set SEGMENTARY_RUN_SMP_CATALOG=1 for the real SMP catalog acceptance")
    if not torch.cuda.is_available():
        pytest.skip("CUDA is required for the real SMP catalog acceptance")

    cfg = load_experiment(
        [
            ROOT / "configs/base.yaml",
            ROOT / "configs/models" / recipe,
            ROOT / "configs/curricula/reference_cityscapes19.yaml",
        ]
    )
    torch.manual_seed(20260812)
    model = apply_tuning(build_model(cfg.model, 19), cfg.model).train().cuda()
    optimizer = build_optimizer(model, cfg.optim, model.head_patterns())
    classifier_before = [
        parameter.detach().clone() for parameter in model.model.segmentation_head.parameters()
    ]
    try:
        for _ in range(4):
            images = torch.randn(2, 3, 128, 128, device="cuda")
            labels = torch.randint(0, 19, (2, 128, 128), device="cuda")
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(images)
                loss = F.cross_entropy(logits, labels)
            loss.backward()
            assert logits.shape == (2, 19, 128, 128)
            assert torch.isfinite(logits).all() and torch.isfinite(loss)
            trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
            assert trainable and all(
                parameter.grad is not None and torch.isfinite(parameter.grad).all()
                for parameter in trainable
            )
            optimizer.step()
        assert any(
            not torch.equal(before, after)
            for before, after in zip(
                classifier_before,
                model.model.segmentation_head.parameters(),
                strict=True,
            )
        )
        assert input_normalization(model)["source"] == "smp_encoder_settings"
    finally:
        del model
        gc.collect()
        torch.cuda.empty_cache()
