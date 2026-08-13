"""Optimiser construction: depth assignment, decay rules and the LR schedule.

The expensive assertion is the last one: a real SegFormer-B2 must yield param
groups that partition its trainable parameters exactly. A parameter silently
dropped from the optimiser trains to nothing and is nearly invisible in a loss
curve, so it is checked against the live module rather than against a fixture.
"""

from __future__ import annotations

import itertools

import pytest
import torch
from torch import nn

from segmentary.config import OptimConfig
from segmentary.engine.layer_depth import discover_layout
from segmentary.engine.optim import (
    DEFAULT_HEAD_PATTERNS,
    assign_layer_id,
    build_optimizer,
    build_param_groups,
    build_scheduler,
    describe_param_groups,
    poly_lr_lambda,
)

HEAD = DEFAULT_HEAD_PATTERNS
DIM = 8
DEPTH = 4


class ToyBlock(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(DIM)
        self.attn = nn.Linear(DIM, DIM)
        self.mlp = nn.Linear(DIM, DIM)


class ToyViT(nn.Module):
    """Plain-ViT naming: stem tensors, blocks.i, trailing norm, decode_head."""

    def __init__(self, num_classes: int = 3) -> None:
        super().__init__()
        self.cls_token = nn.Parameter(torch.zeros(1, 1, DIM))
        self.pos_embed = nn.Parameter(torch.zeros(1, 17, DIM))
        self.patch_embed = nn.Conv2d(3, DIM, kernel_size=4, stride=4)
        self.blocks = nn.ModuleList(ToyBlock() for _ in range(DEPTH))
        self.norm = nn.LayerNorm(DIM)
        self.decode_head = nn.Sequential(nn.Conv2d(DIM, num_classes, kernel_size=1))


def group_of(groups: list[dict], name: str) -> dict:
    matches = [g for g in groups if name in g["param_names"]]
    assert len(matches) == 1, f"{name} appears in {len(matches)} groups"
    return matches[0]


def test_assign_layer_id_plain_vit() -> None:
    assert assign_layer_id("patch_embed.weight", DEPTH, HEAD) == 0
    assert assign_layer_id("cls_token", DEPTH, HEAD) == 0
    assert assign_layer_id("blocks.0.attn.weight", DEPTH, HEAD) == 1
    assert assign_layer_id("blocks.3.mlp.bias", DEPTH, HEAD) == DEPTH
    assert assign_layer_id("layers.2.attn.weight", DEPTH, HEAD) == 3
    assert assign_layer_id("encoder.layer.1.output.dense.weight", DEPTH, HEAD) == 2
    assert assign_layer_id("norm.weight", DEPTH, HEAD) == DEPTH
    assert assign_layer_id("decode_head.classifier.weight", DEPTH, HEAD) == DEPTH + 1
    assert assign_layer_id("some.unrecognised.tensor", DEPTH, HEAD) == 0


def test_assign_layer_id_segformer_uses_actual_stage_counts() -> None:
    counts = (3, 4, 6, 3)  # B2; passed explicitly, discovered from the model in build_*
    total = sum(counts)
    # Stage 0 patch embedding is the stem.
    assert (
        assign_layer_id(
            "segformer.stages.0.patch_embeddings.proj.weight", total, HEAD, stage_blocks=counts
        )
        == 0
    )
    assert (
        assign_layer_id(
            "segformer.stages.0.blocks.0.mlp.fc1.weight", total, HEAD, stage_blocks=counts
        )
        == 1
    )
    # Stage 2 block 1 -> global block index 3 + 4 + 1 = 8 -> depth 9.
    assert (
        assign_layer_id(
            "segformer.stages.2.blocks.1.mlp.fc1.weight", total, HEAD, stage_blocks=counts
        )
        == 9
    )
    assert (
        assign_layer_id(
            "segformer.stages.3.blocks.2.mlp.fc2.bias", total, HEAD, stage_blocks=counts
        )
        == total
    )
    # Later stages must sort strictly after earlier ones with different counts.
    shallow = assign_layer_id(
        "segformer.stages.1.blocks.3.attention.q_proj.weight", total, HEAD, stage_blocks=counts
    )
    deep = assign_layer_id(
        "segformer.stages.2.blocks.0.attention.q_proj.weight", total, HEAD, stage_blocks=counts
    )
    assert shallow < deep


def test_assign_layer_id_requires_stage_blocks_for_hierarchical_names() -> None:
    with pytest.raises(ValueError, match="stage_blocks"):
        assign_layer_id("segformer.stages.2.blocks.1.mlp.fc1.weight", 16, HEAD)


def test_llrd_gives_deeper_layers_larger_lr() -> None:
    cfg = OptimConfig(backbone_lr=1e-4, llrd=0.8, head_lr_mult=10.0)
    groups = build_param_groups(ToyViT(), cfg, HEAD)
    lr_by_depth: dict[int, float] = {}
    for g in groups:
        depth = int(g["layer_id"])
        if g["is_head"]:
            continue
        lr_by_depth.setdefault(depth, float(g["lr"]))
        assert lr_by_depth[depth] == pytest.approx(float(g["lr"]))

    depths = sorted(lr_by_depth)
    assert depths == [0, 1, 2, 3, 4]
    lrs = [lr_by_depth[d] for d in depths]
    assert all(a < b for a, b in itertools.pairwise(lrs)), lrs

    max_depth = DEPTH + 1
    for depth in depths:
        assert lr_by_depth[depth] == pytest.approx(
            cfg.backbone_lr * cfg.llrd ** (max_depth - depth)
        )


def test_llrd_one_is_a_no_op() -> None:
    cfg = OptimConfig(backbone_lr=1e-4, llrd=1.0, head_lr_mult=10.0)
    groups = build_param_groups(ToyViT(), cfg, HEAD)
    backbone = [float(g["lr"]) for g in groups if not g["is_head"]]
    assert backbone == pytest.approx([1e-4] * len(backbone))


def test_head_gets_multiplier_and_no_layer_decay() -> None:
    cfg = OptimConfig(backbone_lr=1e-4, llrd=0.7, head_lr_mult=10.0)
    groups = build_param_groups(ToyViT(), cfg, HEAD)
    head_groups = [g for g in groups if g["is_head"]]
    assert head_groups, "no head group was produced"
    for g in head_groups:
        assert float(g["lr"]) == pytest.approx(cfg.backbone_lr * cfg.head_lr_mult)
        assert int(g["layer_id"]) == DEPTH + 1
        assert all(name.startswith("decode_head") for name in g["param_names"])
    # The head must be the fastest-moving group in the model.
    assert max(float(g["lr"]) for g in groups) == pytest.approx(cfg.backbone_lr * cfg.head_lr_mult)


def test_weight_decay_never_touches_norms_biases_or_embeddings() -> None:
    cfg = OptimConfig(weight_decay=0.05)
    model = ToyViT()
    groups = build_param_groups(model, cfg, HEAD)
    params = dict(model.named_parameters())

    for g in groups:
        for name in g["param_names"]:
            wd = float(g["weight_decay"])
            if params[name].ndim <= 1:
                assert wd == 0.0, f"{name} is 1-D but got weight_decay={wd}"

    for name in (
        "cls_token",
        "pos_embed",
        "norm.weight",
        "norm.bias",
        "blocks.0.norm1.weight",
        "blocks.0.attn.bias",
    ):
        assert float(group_of(groups, name)["weight_decay"]) == 0.0, name
    # cls_token / pos_embed are 3-D here, so only the name rule can catch them.
    assert params["cls_token"].ndim > 1 and params["pos_embed"].ndim > 1

    for name in ("patch_embed.weight", "blocks.0.attn.weight", "decode_head.0.weight"):
        assert float(group_of(groups, name)["weight_decay"]) == pytest.approx(0.05), name


def test_frozen_params_are_excluded() -> None:
    model = ToyViT()
    for param in model.blocks[0].parameters():
        param.requires_grad_(False)
    model.pos_embed.requires_grad_(False)

    groups = build_param_groups(model, OptimConfig(), HEAD)
    listed = {name for g in groups for name in g["param_names"]}
    assert not any(name.startswith("blocks.0.") for name in listed)
    assert "pos_embed" not in listed
    assert "blocks.1.attn.weight" in listed

    expected = {n for n, p in model.named_parameters() if p.requires_grad}
    assert listed == expected


def test_fully_frozen_model_fails_loudly() -> None:
    model = ToyViT()
    model.requires_grad_(False)
    with pytest.raises(ValueError, match="no trainable parameters"):
        build_param_groups(model, OptimConfig(), HEAD)


def test_empty_head_patterns_rejected() -> None:
    with pytest.raises(ValueError, match="head_patterns"):
        build_param_groups(ToyViT(), OptimConfig(), ())


def test_warmup_start_and_end() -> None:
    cfg = OptimConfig(warmup_iters=100, warmup_ratio=1e-6, poly_power=0.9, min_lr_ratio=0.0)
    lam = poly_lr_lambda(cfg, total_iters=1000)
    assert lam(0) == pytest.approx(cfg.warmup_ratio)
    assert lam(50) == pytest.approx(cfg.warmup_ratio + (1 - cfg.warmup_ratio) * 0.5)
    assert lam(100) == pytest.approx(1.0)
    ramp = [lam(i) for i in range(101)]
    assert all(a < b for a, b in itertools.pairwise(ramp))


def test_no_warmup_starts_at_full_lr() -> None:
    cfg = OptimConfig(warmup_iters=0)
    lam = poly_lr_lambda(cfg, total_iters=10)
    assert lam(0) == pytest.approx(1.0)


def test_poly_endpoint_equals_min_lr_ratio() -> None:
    for floor in (0.0, 0.05):
        cfg = OptimConfig(warmup_iters=10, poly_power=0.9, min_lr_ratio=floor)
        lam = poly_lr_lambda(cfg, total_iters=100)
        assert lam(100) == pytest.approx(floor)
        after = [lam(i) for i in range(10, 101)]
        assert all(v >= floor - 1e-12 for v in after)
        assert all(a >= b for a, b in itertools.pairwise(after)), (
            "poly phase must be non-increasing"
        )
        # Halfway through the poly phase, power 0.9 sits above the linear line.
        assert lam(55) == pytest.approx(max(0.5**0.9, floor))


def test_schedule_rejects_warmup_longer_than_run() -> None:
    with pytest.raises(ValueError, match="warmup_iters"):
        poly_lr_lambda(OptimConfig(warmup_iters=100), total_iters=100)
    with pytest.raises(ValueError, match="total_iters"):
        poly_lr_lambda(OptimConfig(warmup_iters=0), total_iters=0)


def test_scheduler_preserves_per_group_lr_ratios() -> None:
    cfg = OptimConfig(backbone_lr=1e-4, llrd=0.8, head_lr_mult=10.0, warmup_iters=10)
    model = ToyViT()
    optimizer = build_optimizer(model, cfg, HEAD)
    base = [g["lr"] for g in optimizer.param_groups]
    scheduler = build_scheduler(optimizer, cfg, total_iters=100)

    assert [g["lr"] for g in optimizer.param_groups] == pytest.approx(
        [b * cfg.warmup_ratio for b in base]
    )
    for _ in range(10):
        optimizer.step()
        scheduler.step()
    assert [g["lr"] for g in optimizer.param_groups] == pytest.approx(base)

    for _ in range(90):
        optimizer.step()
        scheduler.step()
    assert [g["lr"] for g in optimizer.param_groups] == pytest.approx([0.0] * len(base), abs=1e-12)


def test_optimizer_is_adamw_with_config_betas() -> None:
    cfg = OptimConfig(betas=(0.9, 0.98))
    optimizer = build_optimizer(ToyViT(), cfg, HEAD)
    assert isinstance(optimizer, torch.optim.AdamW)
    assert optimizer.defaults["betas"] == (0.9, 0.98)


def test_describe_param_groups_summarises() -> None:
    groups = build_param_groups(ToyViT(), OptimConfig(), HEAD)
    text = describe_param_groups(groups)
    assert f"{len(groups)} param groups" in text
    assert "decay" in text and "no_decay" in text and "head" in text
    tensors = sum(int(line.split()[1]) for line in text.splitlines()[1:3])
    assert tensors == sum(len(g["params"]) for g in groups)


@pytest.fixture(scope="module")
def segformer_b2() -> nn.Module:
    transformers = pytest.importorskip("transformers")
    try:
        return transformers.SegformerForSemanticSegmentation.from_pretrained(
            "nvidia/mit-b2", num_labels=21, ignore_mismatched_sizes=True
        )
    except OSError as exc:  # weights neither cached nor reachable
        pytest.skip(f"nvidia/mit-b2 unavailable: {exc}")


def test_segformer_b2_partitions_every_trainable_parameter(segformer_b2: nn.Module) -> None:
    cfg = OptimConfig(backbone_lr=6e-5, llrd=0.9, head_lr_mult=10.0, weight_decay=0.01)
    groups = build_param_groups(segformer_b2, cfg, HEAD)

    listed = [name for g in groups for name in g["param_names"]]
    expected = [n for n, p in segformer_b2.named_parameters() if p.requires_grad]
    assert len(listed) == len(set(listed)), "a parameter landed in more than one group"
    assert set(listed) == set(expected)
    assert len(listed) == len(expected)

    ids = [id(p) for g in groups for p in g["params"]]
    assert len(ids) == len(set(ids)) == len(expected)

    # AdamW itself rejects a parameter shared between two groups.
    optimizer = build_optimizer(segformer_b2, cfg, HEAD)
    assert sum(len(g["params"]) for g in optimizer.param_groups) == len(expected)


def test_segformer_b2_depths_come_from_the_module(segformer_b2: nn.Module) -> None:
    layout = discover_layout(segformer_b2, HEAD)
    assert layout.stage_blocks == tuple(len(s.blocks) for s in segformer_b2.segformer.stages)
    assert layout.num_layers == sum(layout.stage_blocks)

    cfg = OptimConfig(backbone_lr=6e-5, llrd=0.9, head_lr_mult=10.0)
    groups = build_param_groups(segformer_b2, cfg, HEAD)
    lr_by_depth = {int(g["layer_id"]): float(g["lr"]) for g in groups if not g["is_head"]}
    depths = sorted(lr_by_depth)
    assert depths == list(range(0, layout.num_layers + 1))
    lrs = [lr_by_depth[d] for d in depths]
    assert all(a < b for a, b in itertools.pairwise(lrs))
    assert lr_by_depth[0] == pytest.approx(cfg.backbone_lr * cfg.llrd ** (layout.num_layers + 1))

    head_lrs = [float(g["lr"]) for g in groups if g["is_head"]]
    assert head_lrs and head_lrs == pytest.approx(
        [cfg.backbone_lr * cfg.head_lr_mult] * len(head_lrs)
    )

    # Stage-crossing sanity: the first block of stage 1 is deeper than the last
    # block of stage 0, which is only true if the real per-stage counts were used.
    depth_of = {name: int(g["layer_id"]) for g in groups for name in g["param_names"]}
    first_stage = layout.stage_blocks[0]
    assert depth_of[f"segformer.stages.0.blocks.{first_stage - 1}.mlp.fc1.weight"] == first_stage
    assert depth_of["segformer.stages.1.blocks.0.mlp.fc1.weight"] == first_stage + 1


def test_segformer_b2_norms_and_biases_are_not_decayed(segformer_b2: nn.Module) -> None:
    cfg = OptimConfig(weight_decay=0.05)
    groups = build_param_groups(segformer_b2, cfg, HEAD)
    params = dict(segformer_b2.named_parameters())
    for g in groups:
        for name in g["param_names"]:
            wd = float(g["weight_decay"])
            if params[name].ndim <= 1 or "norm" in name:
                assert wd == 0.0, f"{name} should not be decayed, got {wd}"
            else:
                assert wd == pytest.approx(0.05), name


class ToyHierStage(nn.Module):
    def __init__(self, blocks: int, downsample: bool) -> None:
        super().__init__()
        if downsample:
            self.downsampling_layer = nn.Sequential(nn.Conv2d(DIM, DIM, kernel_size=1))
        self.layers = nn.ModuleList(nn.Conv2d(DIM, DIM, kernel_size=1) for _ in range(blocks))


class ToyConvNeXt(nn.Module):
    """HF-ConvNeXt naming: stages.S.layers.B, with a downsampling layer per stage."""

    def __init__(self, counts: tuple[int, ...] = (2, 3)) -> None:
        super().__init__()
        self.embeddings = nn.Sequential(nn.Conv2d(3, DIM, kernel_size=4, stride=4))
        self.encoder = nn.Module()
        self.encoder.stages = nn.ModuleList(
            ToyHierStage(c, downsample=i > 0) for i, c in enumerate(counts)
        )
        self.decode_head = nn.Sequential(nn.Conv2d(DIM, 3, kernel_size=1))


class ToyFlatViT(nn.Module):
    """EoMT/DINOv3 naming: a flat ``layers.N`` block list, no stages anywhere."""

    def __init__(self) -> None:
        super().__init__()
        self.embeddings = nn.Sequential(nn.Conv2d(3, DIM, kernel_size=4, stride=4))
        self.layers = nn.ModuleList(ToyBlock() for _ in range(DEPTH))
        self.layernorm = nn.LayerNorm(DIM)
        self.decode_head = nn.Sequential(nn.Conv2d(DIM, 3, kernel_size=1))


class ToyResNet(nn.Module):
    """CNN naming: nothing a block index can be read from."""

    def __init__(self) -> None:
        super().__init__()
        self.stem = nn.Conv2d(3, DIM, kernel_size=3)
        self.layer1 = nn.Sequential(nn.Conv2d(DIM, DIM, kernel_size=1))
        self.decode_head = nn.Sequential(nn.Conv2d(DIM, 3, kernel_size=1))


def test_convnext_style_stages_are_flattened() -> None:
    counts = (2, 3)
    model = ToyConvNeXt(counts)
    layout = discover_layout(model, HEAD)
    assert layout.stage_blocks == counts
    assert layout.num_layers == sum(counts)

    groups = build_param_groups(model, OptimConfig(llrd=0.9), HEAD)
    depth_of = {name: int(g["layer_id"]) for g in groups for name in g["param_names"]}
    assert depth_of["embeddings.0.weight"] == 0
    assert depth_of["encoder.stages.0.layers.0.weight"] == 1
    assert depth_of["encoder.stages.0.layers.1.weight"] == 2
    # The downsampling layer feeds stage 1, so it must sit at that stage's entry
    # depth -- not after its blocks, which would make depth non-monotone.
    assert depth_of["encoder.stages.1.downsampling_layer.0.weight"] == 2
    assert depth_of["encoder.stages.1.layers.0.weight"] == 3
    assert depth_of["encoder.stages.1.layers.2.weight"] == sum(counts)
    assert depth_of["decode_head.0.weight"] == sum(counts) + 1


def test_flat_layers_are_not_mistaken_for_stages() -> None:
    model = ToyFlatViT()
    layout = discover_layout(model, HEAD)
    assert layout.stage_blocks is None
    assert layout.num_layers == DEPTH

    groups = build_param_groups(model, OptimConfig(llrd=0.9), HEAD)
    depth_of = {name: int(g["layer_id"]) for g in groups for name in g["param_names"]}
    assert depth_of["layers.0.attn.weight"] == 1
    assert depth_of["layers.3.attn.weight"] == DEPTH
    assert depth_of["layernorm.weight"] == DEPTH
    assert depth_of["embeddings.0.weight"] == 0


def test_head_layer_stacks_do_not_shift_backbone_depths() -> None:
    model = ToyConvNeXt((2,))
    model.decode_head = nn.Module()
    model.decode_head.stages = nn.ModuleList([ToyHierStage(5, downsample=False)])
    assert discover_layout(model, HEAD).stage_blocks == (2,)


def test_llrd_without_discoverable_blocks_fails_loudly() -> None:
    with pytest.raises(ValueError, match="no transformer blocks"):
        build_param_groups(ToyResNet(), OptimConfig(llrd=0.9), HEAD)
    # llrd=1.0 is meaningful for a CNN: every tensor simply gets backbone_lr.
    groups = build_param_groups(ToyResNet(), OptimConfig(backbone_lr=1e-4, llrd=1.0), HEAD)
    backbone = [float(g["lr"]) for g in groups if not g["is_head"]]
    assert backbone == pytest.approx([1e-4] * len(backbone))


def test_zero_warmup_ratio_is_allowed() -> None:
    cfg = OptimConfig(warmup_iters=10, warmup_ratio=0.0)
    lam = poly_lr_lambda(cfg, total_iters=100)
    assert lam(0) == 0.0
    assert lam(10) == pytest.approx(1.0)
