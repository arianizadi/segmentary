"""Contract tests for built models: output shape, head/backbone split, tuning modes.

Only two real checkpoints are downloaded (SegFormer-B0 and an smp ResNet-18); the
large and gated architectures are covered by the standalone verification script,
not by the test suite. The weight-free head arithmetic lives in test_heads.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import torch
from torch import nn

from segmentary.config import EvalConfig, ModelConfig, OptimConfig, TrainConfig
from segmentary.engine.losses import LossConfig, SegmentationLoss
from segmentary.engine.module import SegLitModule
from segmentary.models.dinov3 import load_local_dinov3_backbone, load_local_dinov3_model
from segmentary.models.factory import build_model
from segmentary.models.hrnet_ocr import HRNetOCR
from segmentary.models.tuning import apply_tuning, count_trainable
from segmentary.models.wrappers import SegmentationModel
from segmentary.taxonomy import CanonicalClass, LabelSpace

NUM_CLASSES = 21
SIZE = 128
DINOV3_SMALL = "dinov3_vits16_pretrain_lvd1689m-08c60483.pth"
DINOV3_LARGE = "dinov3_vitl16_pretrain_lvd1689m-8aa4cbdd.pth"


def _dinov3_checkpoint(filename: str) -> Path:
    root = os.environ.get("SEGMENTARY_DINOV3")
    if root is None:
        pytest.skip("set SEGMENTARY_DINOV3 to run local licensed DINOv3 checkpoint tests")
    return Path(root) / filename


def _build(arch: str, **kwargs) -> object:
    cfg = ModelConfig(arch=arch, **kwargs)
    try:
        return build_model(cfg, NUM_CLASSES)
    except ValueError as exc:  # only the download path raises ValueError here
        if "could not load" in str(exc):
            pytest.skip(f"pretrained weights unavailable: {exc}")
        raise


@pytest.fixture(scope="module")
def segformer():
    return _build("segformer_b0")


@pytest.fixture(scope="module")
def smp_model():
    # resnet18 rather than the configured resnet101: same code path, 10x smaller.
    return _build("deeplabv3plus_r101", checkpoint="resnet18")


@pytest.fixture(params=["segformer", "smp_model"])
def any_model(request):
    return request.getfixturevalue(request.param)


# ---------------------------------------------------------------- contract


def test_output_is_input_resolution_logits(any_model):
    any_model.eval()
    with torch.no_grad():
        out = any_model(torch.randn(2, 3, SIZE, SIZE))
    assert out.shape == (2, NUM_CLASSES, SIZE, SIZE)
    assert torch.isfinite(out).all()
    assert any_model.num_classes == NUM_CLASSES


def test_non_square_input_is_preserved(segformer):
    segformer.eval()
    with torch.no_grad():
        out = segformer(torch.randn(1, 3, 96, 160))
    assert out.shape == (1, NUM_CLASSES, 96, 160)


def test_head_patterns_match_real_parameters(any_model):
    names = [n for n, _ in any_model.named_parameters()]
    for pattern in any_model.head_patterns():
        assert any(pattern in n for n in names), f"{pattern!r} matches no parameter"


def test_backbone_modules_are_part_of_the_tree(any_model):
    ids = {id(m) for m in any_model.modules()}
    assert all(id(b) in ids for b in any_model.backbone_modules())
    assert any_model.supports_dense_ce is True


def test_unknown_arch_lists_valid_names():
    with pytest.raises(ValueError, match="unknown arch"):
        build_model(ModelConfig(arch="segformer_b7"), NUM_CLASSES)


# ---------------------------------------------------------------- reset_head


def _classifier_params(model) -> set[str]:
    """Parameter names under a module whose final path component is a classifier."""
    out = set()
    for name, _ in model.named_parameters():
        parts = name.split(".")
        if "classifier" in parts or "segmentation_head" in parts:
            out.add(name)
    return out


def test_reset_head_touches_only_the_classifier(any_model):
    before = {n: p.detach().clone() for n, p in any_model.named_parameters()}
    any_model.reset_head()
    changed = {n for n, p in any_model.named_parameters() if not torch.equal(p.detach(), before[n])}
    expected = _classifier_params(any_model)
    assert changed, "reset_head changed nothing"
    assert changed <= expected, f"reset_head touched non-classifier params: {changed - expected}"


def test_reset_head_keeps_the_output_contract(segformer):
    segformer.reset_head()
    segformer.eval()
    with torch.no_grad():
        out = segformer(torch.randn(1, 3, SIZE, SIZE))
    assert out.shape == (1, NUM_CLASSES, SIZE, SIZE)


# ---------------------------------------------------------------- tuning


def test_full_tuning_trains_everything():
    model = _build("segformer_b0")
    apply_tuning(model, ModelConfig(arch="segformer_b0", tuning="full"))
    trainable, total = count_trainable(model)
    assert trainable == total


def test_frozen_leaves_exactly_the_head_trainable():
    model = _build("segformer_b0")
    backbone_params = sum(p.numel() for b in model.backbone_modules() for p in b.parameters())
    _, total = count_trainable(model)
    apply_tuning(model, ModelConfig(arch="segformer_b0", tuning="frozen"))
    trainable, total_after = count_trainable(model)
    assert total_after == total
    assert trainable == total - backbone_params
    assert all(not p.requires_grad for b in model.backbone_modules() for p in b.parameters())


def test_frozen_backbone_norms_stay_in_eval():
    # Built fresh rather than taken from the module-scoped fixture: apply_tuning
    # mutates requires_grad and registers a forward pre-hook that would leak into
    # every later test sharing the object.
    model = _build("deeplabv3plus_r101", checkpoint="resnet18")
    apply_tuning(model, ModelConfig(arch="deeplabv3plus_r101", tuning="frozen"))
    norms = [
        m for b in model.backbone_modules() for m in b.modules() if isinstance(m, nn.BatchNorm2d)
    ]
    assert norms
    before = norms[0].running_mean.clone()
    model.train()
    model(torch.randn(2, 3, SIZE, SIZE))
    # Running stats must not drift, or "frozen" would quietly be a partial finetune.
    assert all(not n.training for n in norms)
    assert torch.equal(norms[0].running_mean, before)


def test_train_start_activates_pretrained_modules_but_preserves_frozen_norms():
    """Lightning no longer calls train() at fit start; our hook must do it."""
    model = _build("deeplabv3plus_r101", checkpoint="resnet18")
    apply_tuning(model, ModelConfig(arch="deeplabv3plus_r101", tuning="frozen"))
    model.eval()
    space = LabelSpace(
        name="toy",
        description="test label space",
        ignore_index=255,
        classes=tuple(CanonicalClass(i, f"c{i}", (i, i, i)) for i in range(NUM_CLASSES)),
        thin_classes=(),
    )
    lit = SegLitModule(
        model=model,
        loss_fn=SegmentationLoss(LossConfig(), NUM_CLASSES, 255),
        space=space,
        optim_cfg=OptimConfig(),
        train_cfg=TrainConfig(ema_decay=None),
        eval_cfg=EvalConfig(sliding_window=False),
    )

    lit.on_train_start()
    assert lit.training and model.training
    model(torch.randn(2, 3, 64, 64))
    norms = [
        module
        for backbone in model.backbone_modules()
        for module in backbone.modules()
        if isinstance(module, nn.BatchNorm2d)
    ]
    assert norms and all(not norm.training for norm in norms)


def test_lora_adds_adapters_and_keeps_the_head_trainable():
    model = _build("segformer_b0")
    _, total_before = count_trainable(model)
    apply_tuning(model, ModelConfig(arch="segformer_b0", tuning="lora", lora_r=8))
    trainable, total = count_trainable(model)

    adapters = [n for n, _ in model.named_parameters() if "lora_" in n]
    assert adapters, "no LoRA parameters were injected"
    assert total > total_before, "LoRA added no parameters"
    assert 0 < trainable < total
    head = [
        p for n, p in model.named_parameters() if "decode_head" in n and "original_module" not in n
    ]
    assert head and all(p.requires_grad for p in head)
    # Backbone base weights must be frozen, otherwise this is a full finetune.
    assert (
        not model.model.segformer.stages[0]
        .blocks[0]
        .attention.q_proj.base_layer.weight.requires_grad
    )

    model.eval()
    with torch.no_grad():
        out = model(torch.randn(1, 3, SIZE, SIZE))
    assert out.shape == (1, NUM_CLASSES, SIZE, SIZE)


def test_frozen_backward_gives_the_backbone_no_gradient():
    model = _build("segformer_b0")
    apply_tuning(model, ModelConfig(arch="segformer_b0", tuning="frozen"))
    model.train()
    model(torch.randn(1, 3, 64, 64)).square().mean().backward()
    backbone = [p for module in model.backbone_modules() for p in module.parameters()]
    assert backbone and all(parameter.grad is None for parameter in backbone)
    head = [
        parameter
        for name, parameter in model.named_parameters()
        if parameter.requires_grad and "decode_head" in name
    ]
    assert head and any(parameter.grad is not None for parameter in head)


def test_lora_backward_reaches_adapters_and_full_head():
    model = _build("segformer_b0")
    apply_tuning(model, ModelConfig(arch="segformer_b0", tuning="lora", lora_r=4))
    trainable, total = count_trainable(model)
    assert trainable / total < 0.2
    model.train()
    model(torch.randn(1, 3, 64, 64)).square().mean().backward()
    lora = [parameter for name, parameter in model.named_parameters() if "lora_" in name]
    assert lora and all(parameter.requires_grad for parameter in lora)
    # PEFT initialises B to zero, so A can legitimately get zero gradient on the
    # first backward, but both matrices must be connected to the graph.
    assert all(parameter.grad is not None for parameter in lora)
    assert any(bool(torch.count_nonzero(parameter.grad)) for parameter in lora)
    head = [
        parameter
        for name, parameter in model.named_parameters()
        if "decode_head" in name and "original_module" not in name
    ]
    assert head and all(
        parameter.requires_grad and parameter.grad is not None for parameter in head
    )


def test_lora_with_bogus_targets_fails_loudly():
    model = _build("segformer_b0")
    cfg = ModelConfig(arch="segformer_b0", tuning="lora", lora_targets=["not_a_layer"])
    with pytest.raises(ValueError, match=r"zero modules|Target modules"):
        apply_tuning(model, cfg)


def test_lora_on_a_convolutional_backbone_fails_loudly():
    model = _build("deeplabv3plus_r101", checkpoint="resnet18")
    cfg = ModelConfig(arch="deeplabv3plus_r101", tuning="lora")
    with pytest.raises(ValueError, match="could not infer LoRA targets"):
        apply_tuning(model, cfg)


class _NestedHead(SegmentationModel):
    """head_patterns whose match set contains a module and one of its descendants."""

    def __init__(self) -> None:
        super().__init__(4)
        self.trunk = nn.Sequential(nn.Linear(4, 4))
        self.head = nn.Module()
        self.head.aux_head = nn.Conv2d(4, 4, 1)
        self.head.classifier = nn.Conv2d(4, 4, 1)

    def forward(self, pixel_values):  # pragma: no cover - never called
        raise NotImplementedError

    def head_patterns(self):
        return ("head.",)

    def backbone_modules(self):
        return [self.trunk]

    def reset_head(self):  # pragma: no cover - never called
        raise NotImplementedError


def test_head_patterns_matching_a_descendant_are_rejected():
    # PEFT matches modules_to_save with key.endswith(), so "head" also selects
    # "head.aux_head" and freezes it inside a nested wrapper.
    with pytest.raises(ValueError, match="descendant"):
        apply_tuning(_NestedHead(), ModelConfig(arch="x", tuning="lora", lora_targets=["0"]))


def test_lora_on_hrnet_ocr_leaves_no_head_parameter_frozen():
    # hrnet_w18_small: same code path as hrnet_w48, 1.6M params instead of 73M.
    model = HRNetOCR(
        NUM_CLASSES,
        backbone_name="hrnet_w18_small",
        pretrained=False,
        ocr_channels=32,
        key_channels=16,
    )
    apply_tuning(
        model, ModelConfig(arch="hrnet_w48_ocr", tuning="lora", lora_targets=["conv1"], lora_r=4)
    )
    assert any("lora_A" in n for n, _ in model.named_parameters())
    frozen_head = [
        n
        for n, p in model.named_parameters()
        if not p.requires_grad and "original_module" not in n and "head." in n
    ]
    assert not frozen_head, frozen_head
    model.train()
    model(torch.randn(2, 3, 64, 64)).sum().backward()


def test_drop_path_is_rejected_where_it_would_be_ignored():
    # timm's HighResolutionNet absorbs drop_path_rate into **kwargs and builds no
    # DropPath modules, so accepting it would log regularisation nobody applied.
    with pytest.raises(ValueError, match="no stochastic depth"):
        build_model(ModelConfig(arch="hrnet_w48_ocr", drop_path=0.2), NUM_CLASSES)


@pytest.mark.slow
def test_local_dinov3_conversion_matches_meta_checkpoint_and_plain_model():
    checkpoint = _dinov3_checkpoint(DINOV3_SMALL)
    if not checkpoint.is_file():
        pytest.skip(f"DINOv3 checkpoint unavailable: {checkpoint}")
    raw = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
    backbone = load_local_dinov3_backbone(checkpoint)
    direct = load_local_dinov3_model(checkpoint)

    assert torch.equal(backbone.embeddings.cls_token, raw["cls_token"])
    assert torch.equal(backbone.embeddings.register_tokens, raw["storage_tokens"])
    q, k, v = raw["blocks.0.attn.qkv.weight"].chunk(3, dim=0)
    attention = backbone.model.layer[0].attention
    assert torch.equal(attention.q_proj.weight, q)
    assert torch.equal(attention.k_proj.weight, k)
    assert torch.equal(attention.v_proj.weight, v)
    assert torch.equal(attention.q_proj.weight, direct.model.layer[0].attention.q_proj.weight)
    expected_inv_freq = raw["rope_embed.periods"].to(torch.float32).reciprocal()
    assert torch.equal(backbone.rope_embeddings.inv_freq, expected_inv_freq)
    assert torch.equal(direct.rope_embeddings.inv_freq, expected_inv_freq)


@pytest.mark.slow
def test_local_dinov3_vitl_default_checkpoint_maps_first_and_last_blocks():
    checkpoint = _dinov3_checkpoint(DINOV3_LARGE)
    if not checkpoint.is_file():
        pytest.skip(f"DINOv3 checkpoint unavailable: {checkpoint}")
    raw = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
    backbone = load_local_dinov3_backbone(checkpoint)

    assert backbone.config.hidden_size == 1024
    assert backbone.config.intermediate_size == 4096
    assert backbone.config.num_hidden_layers == 24
    assert backbone.config.num_attention_heads == 16
    assert backbone.out_indices == [6, 12, 18, 24]
    assert torch.equal(backbone.embeddings.cls_token, raw["cls_token"])
    assert torch.equal(
        backbone.model.layer[-1].mlp.down_proj.weight,
        raw["blocks.23.mlp.fc2.weight"],
    )
    assert torch.equal(backbone.norm.weight, raw["norm.weight"])


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (
            {
                "blocks.0.mlp.w1.weight": torch.zeros(1),
                "blocks.0.attn.qkv.bias": torch.zeros(3),
            },
            "SwiGLU MLP",
        ),
        (
            {"blocks.0.mlp.w1.weight": torch.zeros(1)},
            "SwiGLU MLP and biasless QKV",
        ),
        (
            {"local_cls_norm.weight": torch.zeros(1)},
            "local-crop CLS norm",
        ),
    ],
)
def test_local_dinov3_rejects_unsupported_checkpoint_schemas(tmp_path, state, message):
    checkpoint = tmp_path / "unsupported.pth"
    torch.save(state, checkpoint)
    with pytest.raises(ValueError, match=message):
        load_local_dinov3_model(checkpoint)


def test_mask2former_dinov3_is_blocked_until_the_adapter_is_implemented():
    with pytest.raises(
        ValueError,
        match=r"DINOv3_Adapter.*SpatialPriorModule.*feature pyramid",
    ):
        build_model(ModelConfig(arch="mask2former_dinov3"), NUM_CLASSES)


@pytest.mark.gpu
@pytest.mark.slow
@pytest.mark.parametrize(
    ("arch", "size", "dense_ce"),
    [
        ("eomt_large", (96, 128), False),
        ("eomt_dinov3_large", (96, 128), False),
        ("upernet_convnext", (96, 128), True),
        ("upernet_r101", (96, 128), True),
    ],
)
def test_real_unverified_model_arms_construct_and_forward(arch, size, dense_ce):
    if not torch.cuda.is_available():
        pytest.skip("CUDA is required for the real large-model integrations")
    model = build_model(ModelConfig(arch=arch), NUM_CLASSES).eval().cuda()
    height, width = size
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        output = model(torch.randn(1, 3, height, width, device="cuda"))
    assert output.shape == (1, NUM_CLASSES, height, width)
    assert bool(torch.isfinite(output).all())
    assert model.supports_dense_ce is dense_ce


def test_mask_classification_model_emits_dense_ce_warning(taxonomy_root):
    class _MaskClassificationStub(nn.Module):
        supports_dense_ce = False

    from segmentary.taxonomy import load_space

    space = load_space(taxonomy_root, "rail_union")
    with pytest.warns(UserWarning, match="Hungarian-matching"):
        SegLitModule(
            model=_MaskClassificationStub(),
            loss_fn=SegmentationLoss(LossConfig(), space.num_classes, space.ignore_index),
            space=space,
            optim_cfg=OptimConfig(),
            train_cfg=TrainConfig(ema_decay=None),
            eval_cfg=EvalConfig(),
        )
