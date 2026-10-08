"""Contract tests for the BiSeNet V1/V2, ESPNet and DenseASPP built-ins.

Everything runs on CPU without network access: recipes that request timm
ImageNet weights are built through the real config -> factory path with
``timm.create_model`` patched to ``pretrained=False``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import timm
import torch
import yaml
from torch import nn

from segmentary.config import ModelConfig, from_dict, load_yaml
from segmentary.curriculum import load_backbone_weights
from segmentary.engine.losses import LossConfig, SegmentationLoss
from segmentary.engine.module import dense_training_objective
from segmentary.models.bisenet import BiSeNetV1, BiSeNetV2Segmenter
from segmentary.models.denseaspp import DenseASPP
from segmentary.models.espnet import ESPNet
from segmentary.models.factory import CLASSIC_ARCHS, VALID_ARCHS, build_model
from segmentary.models.tuning import apply_tuning
from segmentary.models.wrappers import SegmentationModel

ROOT = Path(__file__).resolve().parents[1]
NUM_CLASSES = 21
IGNORE_INDEX = 255

# id -> (class, auxiliary names in training mode, parameter range for 21 classes)
EXPECTED: dict[str, tuple[type[SegmentationModel], tuple[str, ...], tuple[float, float]]] = {
    # Paper/reference counts: BiSeNetV1-R18 ~13M, BiSeNetV2 3.3-5M with boosters,
    # ESPNet 0.364M, DenseASPP-121 ~8-9M, DenseASPP-161 ~35.7M (142.7 MB fp32).
    "bisenetv1_r18": (BiSeNetV1, ("context_path_s8", "context_path_s16"), (12.5e6, 14.5e6)),
    "bisenetv2": (
        BiSeNetV2Segmenter,
        ("booster_s4", "booster_s8", "booster_s16", "booster_s32"),
        (3.3e6, 5.5e6),
    ),
    "espnet": (ESPNet, (), (0.30e6, 0.45e6)),
    "denseaspp121": (DenseASPP, (), (7.5e6, 9.5e6)),
    "denseaspp161": (DenseASPP, (), (33e6, 38e6)),
}
IDS = tuple(EXPECTED)


@pytest.fixture
def offline_timm(monkeypatch: pytest.MonkeyPatch) -> None:
    real = timm.create_model

    def create_model(*args, **kwargs):
        kwargs["pretrained"] = False
        return real(*args, **kwargs)

    monkeypatch.setattr(timm, "create_model", create_model)


def _recipe_model(arch_id: str, num_classes: int = NUM_CLASSES) -> SegmentationModel:
    raw = load_yaml(ROOT / "configs/models" / f"{arch_id}.yaml")
    return build_model(from_dict(ModelConfig, raw["model"]), num_classes)


_CACHE: dict[str, SegmentationModel] = {}


def _model(arch_id: str) -> SegmentationModel:
    """One offline instance per id, shared by the read-only checks below."""
    if arch_id not in _CACHE:
        with pytest.MonkeyPatch.context() as patch:
            real = timm.create_model
            patch.setattr(
                timm, "create_model", lambda *a, **k: real(*a, **{**k, "pretrained": False})
            )
            _CACHE[arch_id] = _recipe_model(arch_id)
    return _CACHE[arch_id]


def _parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


# ---------------------------------------------------------------- construction


def test_new_archs_are_valid_factory_choices() -> None:
    assert set(IDS) == set(CLASSIC_ARCHS)
    assert set(IDS) <= set(VALID_ARCHS)


@pytest.mark.parametrize("arch_id", IDS)
def test_recipe_builds_the_documented_architecture(arch_id: str, offline_timm: None) -> None:
    cls, _, (low, high) = EXPECTED[arch_id]
    model = _recipe_model(arch_id)
    assert type(model) is cls
    assert model.num_classes == model.output_channels == NUM_CLASSES
    assert model.supports_dense_ce is True
    count = _parameter_count(model)
    assert low <= count <= high, f"{arch_id}: {count:,} parameters"
    pretrained = arch_id in ("bisenetv1_r18", "denseaspp121", "denseaspp161")
    assert model.input_normalization_source == (
        "timm_pretrained_cfg" if pretrained else "imagenet_scratch_default"
    )
    assert model.input_mean == pytest.approx((0.485, 0.456, 0.406))
    assert model.input_std == pytest.approx((0.229, 0.224, 0.225))
    assert model.input_channel_order == "rgb"


def test_pretrained_recipes_pin_exact_timm_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[tuple[str, bool]] = []
    real = timm.create_model

    def create_model(name, *args, **kwargs):
        requested.append((name, kwargs.get("pretrained")))
        return real(name, *args, **{**kwargs, "pretrained": False})

    monkeypatch.setattr(timm, "create_model", create_model)
    for arch_id in ("bisenetv1_r18", "denseaspp121", "denseaspp161"):
        _recipe_model(arch_id)
    assert requested == [
        ("resnet18.tv_in1k", True),
        ("densenet121.tv_in1k", True),
        ("densenet161.tv_in1k", True),
    ]


def test_inference_parameter_counts_match_the_papers() -> None:
    v2 = _model("bisenetv2")
    boosters = sum(
        parameter.numel()
        for name, parameter in v2.named_parameters()
        if name.split(".")[1] in ("aux2", "aux3", "aux4", "aux5_4")
    )
    assert 3.2e6 <= _parameter_count(v2) - boosters <= 3.6e6
    v1 = _model("bisenetv1_r18")
    auxiliary = sum(p.numel() for n, p in v1.named_parameters() if n.startswith("aux_heads."))
    assert 12.5e6 <= _parameter_count(v1) - auxiliary <= 14e6
    # ESPNet paper: 0.364M parameters for Cityscapes' 19 classes (+ background).
    assert _parameter_count(ESPNet(20)) == pytest.approx(0.364e6, rel=0.02)


@pytest.mark.parametrize("arch_id", IDS)
def test_factory_rejects_settings_it_would_ignore(arch_id: str) -> None:
    with pytest.raises(ValueError, match="no stochastic depth"):
        build_model(ModelConfig(arch=arch_id, drop_path=0.1), NUM_CLASSES)
    with pytest.raises(ValueError, match=r"takes no model\.checkpoint"):
        build_model(ModelConfig(arch=arch_id, checkpoint="x"), NUM_CLASSES)


# ---------------------------------------------------------------- inference contract


@pytest.mark.parametrize("arch_id", IDS)
def test_public_forward_meets_the_standardized_fps_contract(arch_id: str) -> None:
    """The same output checks as performance.measure_cuda_forward, on CPU."""
    model = _model(arch_id).eval()
    image = torch.randn(1, 3, 256, 256)
    with torch.inference_mode(), torch.autocast("cpu", dtype=torch.bfloat16):
        output = model(image)
    assert isinstance(output, torch.Tensor)
    assert output.ndim == 4 and output.shape[0] == 1
    assert output.shape[-2:] == image.shape[-2:]
    assert output.shape[1] == NUM_CLASSES
    assert bool(torch.isfinite(output).all())


@pytest.mark.parametrize("arch_id", IDS)
def test_eval_mode_returns_input_resolution_logits_without_auxiliary_outputs(
    arch_id: str,
) -> None:
    model = _model(arch_id).eval()
    for shape in ((2, 3, 256, 256), (1, 3, 65, 97)):
        image = torch.randn(*shape)
        with torch.no_grad():
            logits = model(image)
            output = model.forward_output(image)
        assert logits.shape == (shape[0], NUM_CLASSES, *shape[-2:])
        assert output.dense_logits is not None
        assert output.dense_logits.shape == logits.shape
        assert output.auxiliary_dense == ()
        assert torch.allclose(output.dense_logits, logits)


# ---------------------------------------------------------------- training contract


@pytest.mark.parametrize("arch_id", IDS)
def test_training_outputs_auxiliary_heads_and_every_parameter_learns(arch_id: str) -> None:
    _, auxiliary_names, _ = EXPECTED[arch_id]
    model = _model(arch_id).train()
    loss_fn = SegmentationLoss(LossConfig(), NUM_CLASSES, IGNORE_INDEX)
    torch.manual_seed(0)
    for shape in ((2, 3, 256, 256), (2, 3, 65, 97)):
        image = torch.randn(*shape)
        target = torch.randint(0, NUM_CLASSES, (shape[0], *shape[-2:]))
        target[:, :8] = IGNORE_INDEX
        output = model.forward_output(image)
        assert output.dense_logits is not None
        assert output.dense_logits.shape == (shape[0], NUM_CLASSES, *shape[-2:])
        assert tuple(item.name for item in output.auxiliary_dense) == auxiliary_names
        for item in output.auxiliary_dense:
            assert item.logits.shape == output.dense_logits.shape
            assert item.loss_weight == pytest.approx(1.0)

        model.zero_grad(set_to_none=True)
        loss, parts = dense_training_objective(model, loss_fn, image, target)
        assert torch.isfinite(loss)
        assert {f"aux/{name}/weighted_loss" for name in auxiliary_names} <= set(parts)
        loss.backward()
        missing = [name for name, p in model.named_parameters() if p.grad is None]
        assert missing == []
        assert all(torch.isfinite(p.grad).all() for p in model.parameters())
    model.zero_grad(set_to_none=True)
    model.eval()


def test_public_forward_never_runs_auxiliary_heads_even_in_training_mode() -> None:
    model = _model("bisenetv1_r18").train()
    calls: list[str] = []
    hooks = [
        head.register_forward_hook(lambda *_args, name=name: calls.append(name))
        for name, head in model.aux_heads.items()
    ]
    try:
        model(torch.randn(2, 3, 64, 64))
        assert calls == []
        model.forward_output(torch.randn(2, 3, 64, 64))
        assert sorted(calls) == ["context_path_s16", "context_path_s8"]
    finally:
        for hook in hooks:
            hook.remove()
        model.eval()


# ---------------------------------------------------------------- head / backbone split


@pytest.mark.parametrize("arch_id", IDS)
def test_head_patterns_and_backbone_partition_every_parameter(arch_id: str) -> None:
    model = _model(arch_id)
    names = [name for name, _ in model.named_parameters()]
    patterns = model.head_patterns()
    for pattern in patterns:
        assert any(pattern in name for name in names), pattern
    backbone = {id(p) for module in model.backbone_modules() for p in module.parameters()}
    assert backbone
    for name, parameter in model.named_parameters():
        is_head = any(pattern in name for pattern in patterns)
        assert is_head != (id(parameter) in backbone), name


@pytest.mark.parametrize("arch_id", IDS)
def test_frozen_tuning_trains_exactly_the_non_backbone(arch_id: str, offline_timm: None) -> None:
    model = apply_tuning(_recipe_model(arch_id), ModelConfig(arch=arch_id, tuning="frozen"))
    backbone = {id(p) for module in model.backbone_modules() for p in module.parameters()}
    for name, parameter in model.named_parameters():
        assert parameter.requires_grad == (id(parameter) not in backbone), name


# ---------------------------------------------------------------- reset / stage hand-off


@pytest.mark.parametrize("arch_id", IDS)
def test_reset_head_touches_only_class_dependent_state(arch_id: str, offline_timm: None) -> None:
    model = _recipe_model(arch_id)
    before = {name: tensor.clone() for name, tensor in model.state_dict().items()}
    model.reset_head()
    changed = {
        name for name, tensor in model.state_dict().items() if not torch.equal(tensor, before[name])
    }
    assert changed
    if arch_id == "espnet":
        assert all(name.startswith("decoder.") for name in changed)
        assert set(model.reset_head_state_keys()) == {
            name
            for name in before
            if name.startswith("decoder.") and not name.endswith("num_batches_tracked")
        }
    else:
        assert all(".classifier." in f".{name}" or "conv_out.1." in name for name in changed)


@pytest.mark.parametrize("arch_id", IDS)
def test_stage_hand_off_to_a_different_class_count(arch_id: str, offline_timm: None) -> None:
    source = _recipe_model(arch_id, num_classes=19)
    checkpoint = {"state_dict": {f"model.{k}": v for k, v in source.state_dict().items()}}
    target = _recipe_model(arch_id, num_classes=NUM_CLASSES)
    load_backbone_weights(target, Path("source.ckpt"), True, checkpoint_state=checkpoint)
    source_state = source.state_dict()
    carried = [
        name
        for name, tensor in target.state_dict().items()
        if source_state[name].shape == tensor.shape and torch.equal(source_state[name], tensor)
    ]
    backbone_names = {
        f"{prefix}.{name}"
        for prefix, module in target.named_modules()
        if any(module is b for b in target.backbone_modules())
        for name in module.state_dict()
    }
    assert backbone_names and backbone_names <= set(carried)


def test_espnet_supports_fewer_classes_than_esp_branches() -> None:
    for classes in (2, 3, 4):
        model = ESPNet(classes).eval()
        with torch.no_grad():
            assert model(torch.randn(1, 3, 64, 96)).shape == (1, classes, 64, 96)


def test_denseaspp_runs_the_backbone_at_output_stride_eight() -> None:
    model = _model("denseaspp121")
    backbone = model.backbone
    assert isinstance(backbone.transition1.pool, nn.AvgPool2d)
    assert isinstance(backbone.transition2.pool, nn.Identity)
    assert isinstance(backbone.transition3.pool, nn.Identity)
    assert backbone.denseblock3.denselayer1.conv2.dilation == (2, 2)
    assert backbone.denseblock4.denselayer16.conv2.dilation == (4, 4)
    assert "norm5" not in dict(backbone.named_children())
    with torch.no_grad():
        assert backbone.eval()(torch.randn(1, 3, 128, 128)).shape == (1, 1024, 16, 16)


def test_bisenetv2_reuses_the_unchanged_medical_vendored_code() -> None:
    from segmentary.medical import two_d_bisenet

    model = _model("bisenetv2")
    assert type(model.model) is two_d_bisenet.BiSeNetV2
    # The medical runner binds experiments to the hash of every medical/*.py
    # file, so the shared vendored copy must stay byte-identical.
    audit = json.loads(
        (
            ROOT / "docs/results/pancreas/task07/recipe-ablation-20260914/input-audit.json"
        ).read_text()
    )
    recorded = json.dumps(audit)
    digest = hashlib.sha256(Path(two_d_bisenet.__file__).read_bytes()).hexdigest()
    assert digest in recorded


# ---------------------------------------------------------------- campaign catalog


def test_campaign_catalog_and_planner_recognise_the_new_models() -> None:
    from scripts import plan_rtis_campaign as planner
    from scripts import run_benchmark_campaign as campaign

    catalog = yaml.safe_load(
        (ROOT / "configs/campaigns/all_models_cityscapes_railsem19.yaml").read_text()
    )
    rows = {row["id"]: row for row in catalog["models"]}
    for arch_id in IDS:
        row = rows[arch_id]
        assert row["config"] == f"configs/models/{arch_id}.yaml"
        assert (ROOT / row["readme"]).is_file()
        assert "alias_of" not in row and "campaign_config" not in row
        assert arch_id in catalog["priority_order"]
        assert arch_id in campaign.MODEL_COST_WEIGHTS
    selected = planner.select_models(catalog, {"models": list(IDS)})
    assert [model["id"] for model in selected] == list(IDS)
    manifest = campaign.load_campaign_manifest()
    jobs = [job for job in campaign.campaign_jobs(manifest, (0,)) if job.model.id in IDS]
    assert len(jobs) == len(IDS) * 3
    # Only the all-model scene-grouped manifests use the new models, and only from their
    # recipe weights (no Cityscapes or RailSem19 checkpoints exist for them yet).
    for path in (ROOT / "configs/campaigns").glob("rad_9_24_2026-*.yaml"):
        spec = yaml.safe_load(path.read_text())
        used = set(spec.get("models", [])) & set(IDS)
        if path.stem.startswith("rad_9_24_2026-fixed-grouped-all"):
            assert used and spec["model_protocols"] == {m: ["rtis_only"] for m in IDS}
        else:
            assert not used
