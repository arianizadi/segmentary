"""CPU contract tests for independently composable native segmentation parts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import pytest
import torch
import torch.distributed as dist
import torch.nn.functional as F
from torch import Tensor, nn

from segmentary.models.backbones import TimmBackbone
from segmentary.models.components import build_head, build_native_model
from segmentary.models.features import (
    FeatureBackbone,
    FeatureMaps,
    FeatureSpec,
    require_increasing_reductions,
    validate_feature_maps,
)
from segmentary.models.layers import LayerNorm2d, build_activation, build_norm
from segmentary.models.native import AuxiliaryHeadBinding, NativeDenseSegmenter
from segmentary.models.native_heads import DPTHead, FCNHead, OCRHead
from segmentary.models.necks import ChannelMapper, FPNNeck, IdentityNeck
from segmentary.models.outputs import (
    AuxiliaryDenseOutput,
    QueryOutput,
    QueryPrediction,
    SegmentationOutput,
)

NUM_CLASSES = 5
SPECS = (
    FeatureSpec("s4", 8, 4),
    FeatureSpec("s8", 12, 8),
    FeatureSpec("s16", 16, 16),
    FeatureSpec("s32", 24, 32),
)
MAPPED_SPECS = tuple(
    FeatureSpec(f"mapped_s{reduction}", 10, reduction) for reduction in (4, 8, 16, 32)
)


def _features(batch: int = 2) -> FeatureMaps:
    return (
        torch.randn(batch, 8, 16, 24, requires_grad=True),
        torch.randn(batch, 12, 8, 12, requires_grad=True),
        torch.randn(batch, 16, 4, 6, requires_grad=True),
        torch.randn(batch, 24, 2, 3, requires_grad=True),
    )


def _mapped_features(batch: int = 2) -> FeatureMaps:
    return (
        torch.randn(batch, 10, 16, 24, requires_grad=True),
        torch.randn(batch, 10, 8, 12, requires_grad=True),
        torch.randn(batch, 10, 4, 6, requires_grad=True),
        torch.randn(batch, 10, 2, 3, requires_grad=True),
    )


def _common(kind: str, **values):
    options = {"kind": kind, "dropout": 0.1, "norm": "group", "activation": "relu"}
    options.update(values)
    return SimpleNamespace(**options)


HEAD_SPECS = (
    _common(
        "fcn",
        in_indices=(0, 1, 2, 3),
        channels=16,
        num_convs=2,
        kernel_size=3,
        dilation=1,
    ),
    _common("segformer", in_indices=(0, 1, 2, 3), channels=16),
    _common("psp", in_index=3, channels=16, pool_bins=(1, 2, 3, 6)),
    _common("aspp", in_index=3, channels=16, dilation_rates=(1, 2, 3)),
    _common(
        "deeplabv3plus",
        low_index=0,
        high_index=3,
        channels=16,
        low_channels=8,
        dilation_rates=(1, 2, 3),
    ),
    _common("lraspp", low_index=0, high_index=3, channels=12),
    _common("uper", in_indices=(0, 1, 2, 3), channels=16, pool_bins=(1, 2, 3, 6)),
)


class ToyBackbone(FeatureBackbone):
    input_channels = 3

    def __init__(self) -> None:
        super().__init__()
        self.blocks = nn.ModuleList(
            (
                nn.Conv2d(3, 8, 3, stride=4, padding=1),
                nn.Conv2d(8, 12, 3, stride=2, padding=1),
                nn.Conv2d(12, 16, 3, stride=2, padding=1),
                nn.Conv2d(16, 24, 3, stride=2, padding=1),
            )
        )

    @property
    def output_specs(self) -> tuple[FeatureSpec, ...]:
        return SPECS

    def forward_features(self, image: Tensor) -> FeatureMaps:
        output = []
        feature = image
        for block in self.blocks:
            feature = F.relu(block(feature))
            output.append(feature)
        return validate_feature_maps(
            tuple(output),
            self.output_specs,
            where="toy backbone",
            batch_size=int(image.shape[0]),
            input_size=(int(image.shape[2]), int(image.shape[3])),
        )


def _toy_model(*, auxiliary: bool = True) -> NativeDenseSegmenter:
    backbone = ToyBackbone()
    neck = FPNNeck(SPECS, out_channels=12, norm="group")
    head = FCNHead(
        neck.output_specs,
        NUM_CLASSES,
        in_indices=(0, 1, 2, 3),
        channels=12,
        norm="group",
    )
    bindings: tuple[AuxiliaryHeadBinding, ...] = ()
    if auxiliary:
        aux = FCNHead(
            neck.output_specs,
            NUM_CLASSES,
            in_indices=(2,),
            channels=8,
            num_convs=1,
            norm="group",
        )
        bindings = (AuxiliaryHeadBinding("s16", aux, 0.4),)
    return NativeDenseSegmenter(backbone, neck, head, NUM_CLASSES, auxiliary_heads=bindings)


def _toy_dpt_model() -> NativeDenseSegmenter:
    backbone = ToyBackbone()
    neck = ChannelMapper(SPECS, out_channels=8, norm="group")
    head = DPTHead(
        neck.output_specs,
        NUM_CLASSES,
        in_indices=(0, 1, 2, 3),
        channels=8,
        dropout=0.0,
        norm="group",
    )
    return NativeDenseSegmenter(backbone, neck, head, NUM_CLASSES)


def _toy_ocr_model(*, attention_scale: int = 1) -> NativeDenseSegmenter:
    backbone = ToyBackbone()
    neck = FPNNeck(SPECS, out_channels=8, norm="group")
    head = OCRHead(
        neck.output_specs,
        NUM_CLASSES,
        in_indices=(0, 1, 2, 3),
        channels=12,
        key_channels=6,
        attention_scale=attention_scale,
        dropout=0.0,
        coarse_loss_weight=0.4,
        norm="group",
    )
    return NativeDenseSegmenter(backbone, neck, head, NUM_CLASSES)


def _dense_training_loss(model: NativeDenseSegmenter, image: Tensor, target: Tensor) -> Tensor:
    output = model.forward_output(image)
    assert output.dense_logits is not None
    loss = F.cross_entropy(output.dense_logits, target)
    for auxiliary in output.auxiliary_dense:
        loss = loss + auxiliary.loss_weight * F.cross_entropy(auxiliary.logits, target)
    return loss


def test_feature_contract_accepts_odd_rounding_and_rejects_wrong_channels():
    features = (
        torch.randn(2, 8, 17, 25),
        torch.randn(2, 12, 9, 13),
        torch.randn(2, 16, 5, 7),
        torch.randn(2, 24, 3, 4),
    )
    checked = validate_feature_maps(
        features, SPECS, where="test", batch_size=2, input_size=(65, 97)
    )
    assert all(left is right for left, right in zip(checked, features, strict=True))
    wrong = list(features)
    wrong[2] = torch.randn(2, 15, 5, 7)
    with pytest.raises(ValueError, match="declared 16"):
        validate_feature_maps(tuple(wrong), SPECS, where="test")


def test_pyramid_consumers_reject_equal_stride_features():
    equal_stride = (FeatureSpec("a", 8, 16), FeatureSpec("b", 8, 16))
    with pytest.raises(ValueError, match="strictly increasing"):
        require_increasing_reductions(equal_stride, where="test")
    with pytest.raises(ValueError, match="strictly increasing"):
        FPNNeck(equal_stride, out_channels=8)


def test_identity_neck_preserves_tensor_identity():
    features = _features()
    output = IdentityNeck(SPECS)(features)
    assert all(left is right for left, right in zip(features, output, strict=True))


@pytest.mark.parametrize(
    "kind",
    ["relu", "relu6", "leaky_relu", "gelu", "silu", "elu", "mish", "hardswish"],
)
def test_every_native_activation_is_finite_and_differentiable(kind):
    values = torch.linspace(-3.0, 3.0, 48).reshape(2, 3, 2, 4).requires_grad_()
    output = build_activation(kind)(values)
    assert output.shape == values.shape
    assert torch.isfinite(output).all()
    output.sum().backward()
    assert values.grad is not None and torch.isfinite(values.grad).all()


@pytest.mark.parametrize("kind", ["batch", "group", "instance", "layer", "none"])
def test_every_native_normalization_preserves_shape_and_backpropagates(kind):
    values = torch.randn(2, 8, 5, 7, requires_grad=True)
    output = build_norm(kind, 8)(values)
    assert output.shape == values.shape
    assert torch.isfinite(output).all()
    output.square().mean().backward()
    assert values.grad is not None and torch.isfinite(values.grad).all()


def test_layer_norm_is_per_pixel_over_channels_not_global_group_norm():
    values = torch.randn(2, 8, 5, 7)
    normalized = LayerNorm2d(8)(values)
    assert torch.allclose(normalized.mean(dim=1), torch.zeros(2, 5, 7), atol=1e-6)
    assert torch.allclose(normalized.var(dim=1, unbiased=False), torch.ones(2, 5, 7), atol=2e-4)


def test_timm_adapter_rejects_non_rgb_before_constructing_model(monkeypatch):
    called = False

    def create_model(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not construct an unusable model")

    monkeypatch.setattr("segmentary.models.backbones.timm.timm.create_model", create_model)
    with pytest.raises(ValueError, match="public image pipeline currently emits RGB"):
        TimmBackbone("fake", pretrained=False, input_channels=1)
    assert not called


def test_fpn_neck_shapes_extra_level_and_backward():
    features = _features()
    neck = FPNNeck(SPECS, out_channels=10, num_outputs=5, norm="group")
    output = neck(features)
    assert [tuple(item.shape) for item in output] == [
        (2, 10, 16, 24),
        (2, 10, 8, 12),
        (2, 10, 4, 6),
        (2, 10, 2, 3),
        (2, 10, 1, 2),
    ]
    sum(item.square().mean() for item in output).backward()
    assert all(parameter.grad is not None for parameter in neck.parameters())


def test_channel_mapper_shapes_extra_level_backward_and_level_independence():
    features = _features()
    neck = ChannelMapper(
        SPECS,
        out_channels=10,
        kernel_size=3,
        num_outputs=5,
        norm="group",
        activation="silu",
    )
    output = neck(features)
    assert neck.output_specs == (
        FeatureSpec("channel_mapper_0", 10, 4),
        FeatureSpec("channel_mapper_1", 10, 8),
        FeatureSpec("channel_mapper_2", 10, 16),
        FeatureSpec("channel_mapper_3", 10, 32),
        FeatureSpec("channel_mapper_4", 10, 64),
    )
    assert [tuple(item.shape) for item in output] == [
        (2, 10, 16, 24),
        (2, 10, 8, 12),
        (2, 10, 4, 6),
        (2, 10, 2, 3),
        (2, 10, 1, 2),
    ]
    sum(item.square().mean() for item in output).backward()
    assert all(parameter.grad is not None for parameter in neck.parameters())
    assert all(feature.grad is not None for feature in features)

    isolated = _features()
    first_only = ChannelMapper(SPECS, out_channels=10, norm="none")(isolated)[0]
    first_only.square().mean().backward()
    assert isolated[0].grad is not None
    assert all(feature.grad is None for feature in isolated[1:])


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"out_channels": 0}, "out_channels"),
        ({"out_channels": 8, "kernel_size": 2}, "positive odd"),
        ({"out_channels": 8, "num_outputs": 3}, "at least"),
    ],
)
def test_channel_mapper_rejects_invalid_runtime_contracts(kwargs, message):
    with pytest.raises(ValueError, match=message):
        ChannelMapper(SPECS, **kwargs)


def test_dpt_head_progressively_fuses_all_four_levels_at_odd_output_size():
    features = _mapped_features()
    head = DPTHead(
        MAPPED_SPECS,
        NUM_CLASSES,
        in_indices=(0, 1, 2, 3),
        channels=10,
        dropout=0.1,
        norm="group",
        activation="relu",
    )
    logits = head(features, (65, 97))
    assert logits.shape == (2, NUM_CLASSES, 65, 97)
    assert torch.isfinite(logits).all()
    logits.square().mean().backward()
    assert all(feature.grad is not None for feature in features)
    assert all(parameter.grad is not None for parameter in head.parameters())


@pytest.mark.parametrize("norm", ["batch", "group", "instance", "layer", "none"])
def test_dpt_head_supports_every_native_normalization(norm):
    head = DPTHead(
        MAPPED_SPECS,
        NUM_CLASSES,
        in_indices=(0, 1, 2, 3),
        channels=10,
        dropout=0.0,
        norm=norm,
        activation="gelu",
    ).train()
    logits = head(_mapped_features(), (64, 96))
    assert logits.shape == (2, NUM_CLASSES, 64, 96)
    logits.mean().backward()
    assert all(parameter.grad is not None for parameter in head.parameters())


def test_dpt_head_rejects_wrong_level_count_width_and_pyramid_order():
    with pytest.raises(ValueError, match="exactly four"):
        DPTHead(
            MAPPED_SPECS,
            NUM_CLASSES,
            in_indices=(0, 1, 2),
            channels=10,
        )
    with pytest.raises(ValueError, match="ChannelMapper"):
        DPTHead(SPECS, NUM_CLASSES, in_indices=(0, 1, 2, 3), channels=10)
    bad_order = (
        FeatureSpec("a", 10, 4),
        FeatureSpec("b", 10, 8),
        FeatureSpec("c", 10, 8),
        FeatureSpec("d", 10, 32),
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        DPTHead(bad_order, NUM_CLASSES, in_indices=(0, 1, 2, 3), channels=10)


def test_dpt_reset_changes_only_the_classifier():
    head = DPTHead(
        MAPPED_SPECS,
        NUM_CLASSES,
        in_indices=(0, 1, 2, 3),
        channels=10,
    )
    before = {name: parameter.detach().clone() for name, parameter in head.named_parameters()}
    head.reset_classifier()
    changed = {
        name
        for name, parameter in head.named_parameters()
        if not torch.equal(before[name], parameter.detach())
    }
    assert changed
    assert all(name.startswith("classifier.") for name in changed)


def test_ocr_head_emits_refined_primary_and_supervised_coarse_logits():
    model = _toy_ocr_model(attention_scale=2)
    image = torch.randn(2, 3, 65, 97)
    output = model.forward_output(image)
    assert output.dense_logits is not None
    assert output.dense_logits.shape == (2, NUM_CLASSES, 65, 97)
    assert len(output.auxiliary_dense) == 1
    coarse = output.auxiliary_dense[0]
    assert coarse.name == "ocr_coarse"
    assert coarse.loss_weight == pytest.approx(0.4)
    assert coarse.logits.shape == output.dense_logits.shape
    assert torch.isfinite(output.dense_logits).all()
    assert torch.isfinite(coarse.logits).all()
    torch.testing.assert_close(model(image), output.dense_logits)

    target = torch.randint(NUM_CLASSES, (2, 65, 97))
    loss = _dense_training_loss(model, image, target)
    loss.backward()
    assert all(parameter.grad is not None for parameter in model.parameters())
    assert model.head.coarse_classifier.weight.grad is not None
    assert bool(model.head.coarse_classifier.weight.grad.abs().sum() > 0)
    assert model.head.classifier.weight.grad is not None
    assert bool(model.head.classifier.weight.grad.abs().sum() > 0)


def test_ocr_gather_normalizes_each_class_region_over_space():
    features = torch.tensor([[[[1.0, 3.0]], [[2.0, 4.0]]]])
    coarse_logits = torch.tensor([[[[0.0, 0.0]], [[-20.0, 20.0]]]])
    regions = OCRHead.gather_object_regions(features, coarse_logits)
    assert regions.shape == (1, 2, 2, 1)
    torch.testing.assert_close(regions[0, :, 0, 0], torch.tensor([2.0, 3.0]))
    torch.testing.assert_close(regions[0, :, 1, 0], torch.tensor([3.0, 4.0]), atol=1e-5, rtol=0)


def test_ocr_binary_logit_builds_symmetric_probability_equivalent_regions():
    foreground_logit = torch.tensor([[[[-100.0, -4.0, 0.0, 4.0, 100.0]]]])
    region_logits = OCRHead.object_region_logits(foreground_logit)

    assert region_logits.shape == (1, 2, 1, 5)
    torch.testing.assert_close(region_logits[:, 1] - region_logits[:, 0], foreground_logit[:, 0])
    torch.testing.assert_close(region_logits.sum(dim=1), torch.zeros_like(foreground_logit[:, 0]))
    torch.testing.assert_close(
        OCRHead.object_region_logits(-foreground_logit),
        region_logits.flip(1),
    )
    torch.testing.assert_close(
        region_logits.softmax(dim=1)[:, 1],
        foreground_logit.sigmoid()[:, 0],
    )
    assert torch.isfinite(region_logits.softmax(dim=1)).all()

    random_logit = torch.tensor([0.25, -1.5, 3.0, -8.0], dtype=torch.float64)
    target = torch.tensor([0, 1, 1, 0])
    paired = OCRHead.object_region_logits(random_logit[:, None, None, None]).flatten(1)
    torch.testing.assert_close(
        F.cross_entropy(paired, target, reduction="none"),
        F.binary_cross_entropy_with_logits(
            random_logit, target.to(torch.float64), reduction="none"
        ),
    )

    nonconstant_logit = torch.tensor([[[[-4.0, 0.0, 1.0, 2.0, 4.0]]]])
    features = torch.tensor([[[[1.0, 2.0, 3.0, 5.0, 9.0]], [[2.0, 4.0, 8.0, 16.0, 32.0]]]])
    regions = OCRHead.gather_object_regions(
        features,
        OCRHead.object_region_logits(nonconstant_logit),
    )
    assert regions.shape == (1, 2, 2, 1)
    assert bool((regions[:, :, 0] != regions[:, :, 1]).any())

    multiclass_logits = torch.randn(2, NUM_CLASSES, 4, 6)
    assert OCRHead.object_region_logits(multiclass_logits) is multiclass_logits


def test_ocr_one_logit_binary_forward_trains_refined_and_coarse_classifiers():
    with torch.random.fork_rng():
        torch.manual_seed(21)
        backbone = ToyBackbone()
        neck = FPNNeck(SPECS, out_channels=8, norm="group")
        head = OCRHead(
            neck.output_specs,
            1,
            in_indices=(0, 1, 2, 3),
            channels=12,
            key_channels=6,
            dropout=0.0,
            coarse_loss_weight=0.4,
            norm="group",
        )
        model = NativeDenseSegmenter(backbone, neck, head, 2, task="binary")
        image = torch.randn(2, 3, 65, 97)
        output = model.forward_output(image)

        assert output.dense_logits is not None
        assert output.dense_logits.shape == (2, 1, 65, 97)
        assert len(output.auxiliary_dense) == 1
        assert output.auxiliary_dense[0].name == "ocr_coarse"
        assert output.auxiliary_dense[0].logits.shape == (2, 1, 65, 97)
        loss = (
            output.dense_logits.square().mean()
            + output.auxiliary_dense[0].loss_weight
            * output.auxiliary_dense[0].logits.square().mean()
        )
        loss.backward()
        assert all(
            parameter.grad is not None and bool(torch.isfinite(parameter.grad).all())
            for parameter in model.parameters()
        )
        assert bool(model.head.object_context.pixel_query[0].weight.grad.abs().sum() > 0)
        assert bool(model.head.object_context.region_key[0].weight.grad.abs().sum() > 0)
        assert bool(model.head.coarse_classifier.weight.grad.abs().sum() > 0)
        assert bool(model.head.classifier.weight.grad.abs().sum() > 0)


def test_ocr_object_context_rejects_a_single_region_before_attention_degenerates():
    head = OCRHead(
        SPECS,
        NUM_CLASSES,
        in_indices=(0, 1, 2, 3),
        channels=12,
        key_channels=6,
        dropout=0.0,
        coarse_loss_weight=0.4,
        norm="group",
    )
    with pytest.raises(ValueError, match="K>=2"):
        head.object_context(
            torch.randn(2, 12, 8, 12),
            torch.randn(2, 12, 1, 1),
        )


@pytest.mark.parametrize("norm", ["batch", "group", "instance", "layer", "none"])
def test_ocr_head_supports_every_native_normalization(norm):
    head = OCRHead(
        SPECS,
        NUM_CLASSES,
        in_indices=(0, 1, 2, 3),
        channels=12,
        key_channels=6,
        dropout=0.0,
        coarse_loss_weight=0.4,
        norm=norm,
        activation="gelu",
    ).train()
    output = head.forward_output(_features(), (64, 96))
    assert output.dense_logits is not None
    loss = output.dense_logits.square().mean()
    loss = loss + output.auxiliary_dense[0].logits.square().mean()
    loss.backward()
    assert all(parameter.grad is not None for parameter in head.parameters())


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"channels": 0, "key_channels": 6}, "channels"),
        ({"channels": 12, "key_channels": 0}, "key_channels"),
        ({"channels": 12, "key_channels": 6, "attention_scale": 0}, "attention_scale"),
        ({"channels": 12, "key_channels": 6, "coarse_loss_weight": 0.0}, "loss_weight"),
    ],
)
def test_ocr_head_rejects_invalid_runtime_contracts(kwargs, message):
    with pytest.raises(ValueError, match=message):
        OCRHead(SPECS, NUM_CLASSES, in_indices=(0, 1, 2, 3), **kwargs)


def test_ocr_head_rejects_non_pyramid_inputs_and_oversized_attention_scale():
    equal_stride = (
        FeatureSpec("a", 8, 4),
        FeatureSpec("b", 8, 4),
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        OCRHead(equal_stride, NUM_CLASSES, in_indices=(0, 1), channels=8, key_channels=4)
    model = _toy_ocr_model(attention_scale=17)
    with pytest.raises(ValueError, match="exceeds pixel feature size"):
        model(torch.randn(1, 3, 64, 96))


def test_ocr_reset_changes_exactly_both_classifiers():
    head = OCRHead(
        SPECS,
        NUM_CLASSES,
        in_indices=(0, 1, 2, 3),
        channels=12,
        key_channels=6,
    )
    before = {name: parameter.detach().clone() for name, parameter in head.named_parameters()}
    head.reset_classifier()
    changed = {
        name
        for name, parameter in head.named_parameters()
        if not torch.equal(before[name], parameter.detach())
    }
    assert changed == {
        "coarse_classifier.weight",
        "coarse_classifier.bias",
        "classifier.weight",
        "classifier.bias",
    }


def test_ocr_cannot_be_nested_or_collide_with_an_external_auxiliary_name():
    model = _toy_ocr_model()
    with pytest.raises(ValueError, match="cannot itself emit auxiliary outputs"):
        AuxiliaryHeadBinding("nested_ocr", model.head, 0.4)

    external = FCNHead(
        model.neck.output_specs,
        NUM_CLASSES,
        in_indices=(2,),
        channels=8,
        num_convs=1,
        norm="group",
    )
    with pytest.raises(ValueError, match="collide"):
        NativeDenseSegmenter(
            model.backbone,
            model.neck,
            model.head,
            NUM_CLASSES,
            auxiliary_heads=(AuxiliaryHeadBinding("ocr_coarse", external, 0.4),),
        )


@pytest.mark.parametrize("spec", HEAD_SPECS, ids=lambda spec: spec.kind)
def test_every_native_head_is_full_resolution_and_differentiable(spec):
    head = build_head(spec, SPECS, NUM_CLASSES)
    logits = head(_features(), (64, 96))
    assert logits.shape == (2, NUM_CLASSES, 64, 96)
    assert torch.isfinite(logits).all()
    logits.square().mean().backward()
    assert all(parameter.grad is not None for parameter in head.parameters())


@pytest.mark.parametrize("spec", HEAD_SPECS, ids=lambda spec: spec.kind)
def test_every_native_head_supports_one_logit_binary_output(spec):
    head = build_head(spec, SPECS, 1)
    logits = head(_features(), (64, 96))
    assert logits.shape == (2, 1, 64, 96)
    assert torch.isfinite(logits).all()
    logits.square().mean().backward()
    assert all(parameter.grad is not None for parameter in head.parameters())


def test_native_binary_primary_and_auxiliary_heads_emit_one_raw_logit():
    backbone = ToyBackbone()
    neck = FPNNeck(SPECS, out_channels=12, norm="group")
    primary = FCNHead(
        neck.output_specs,
        1,
        in_indices=(0, 1, 2, 3),
        channels=12,
        norm="group",
    )
    auxiliary = FCNHead(
        neck.output_specs,
        1,
        in_indices=(2,),
        channels=8,
        num_convs=1,
        norm="group",
    )
    model = NativeDenseSegmenter(
        backbone,
        neck,
        primary,
        2,
        task="binary",
        auxiliary_heads=(AuxiliaryHeadBinding("s16", auxiliary, 0.4),),
    )

    output = model.forward_output(torch.randn(2, 3, 64, 96))
    assert output.dense_logits is not None
    assert output.dense_logits.shape == (2, 1, 64, 96)
    assert len(output.auxiliary_dense) == 1
    assert output.auxiliary_dense[0].logits.shape == (2, 1, 64, 96)


@pytest.mark.parametrize("spec", HEAD_SPECS, ids=lambda spec: spec.kind)
def test_reset_classifier_does_not_touch_class_agnostic_head_layers(spec):
    head = build_head(spec, SPECS, NUM_CLASSES)
    before = {name: parameter.detach().clone() for name, parameter in head.named_parameters()}
    head.reset_classifier()
    changed = {
        name
        for name, parameter in head.named_parameters()
        if not torch.equal(before[name], parameter.detach())
    }
    assert changed
    assert all(name.startswith("classifier.") for name in changed)


def test_lraspp_batch_norm_path_is_valid_for_batch_one():
    spec = _common("lraspp", low_index=0, high_index=3, channels=12, norm="batch")
    head = build_head(spec, SPECS, NUM_CLASSES).train()
    logits = head(_features(batch=1), (64, 96))
    assert logits.shape == (1, NUM_CLASSES, 64, 96)
    logits.square().mean().backward()
    assert all(parameter.grad is not None for parameter in head.parameters())


@pytest.mark.parametrize(
    "spec",
    [
        _common("psp", in_index=3, channels=12, pool_bins=(1, 2), norm="batch"),
        _common("aspp", in_index=3, channels=12, dilation_rates=(1, 2), norm="batch"),
        _common(
            "deeplabv3plus",
            low_index=0,
            high_index=3,
            channels=12,
            low_channels=6,
            dilation_rates=(1, 2),
            norm="batch",
        ),
        _common(
            "uper",
            in_indices=(0, 1, 2, 3),
            channels=12,
            pool_bins=(1, 2),
            norm="batch",
        ),
    ],
    ids=lambda spec: spec.kind,
)
def test_global_context_heads_support_batch_one_with_batch_norm(spec):
    head = build_head(spec, SPECS, NUM_CLASSES).train()
    logits = head(_features(batch=1), (64, 96))
    assert logits.shape == (1, NUM_CLASSES, 64, 96)
    logits.square().mean().backward()
    assert all(parameter.grad is not None for parameter in head.parameters())


def test_query_and_dense_output_protocols_reject_ambiguous_shapes():
    dense = torch.randn(2, NUM_CLASSES, 16, 16)
    auxiliary = AuxiliaryDenseOutput("aux", dense.clone(), 0.4)
    output = SegmentationOutput(dense_logits=dense, auxiliary_dense=(auxiliary,))
    assert output.dense_logits is dense

    query_prediction = QueryPrediction(
        torch.randn(2, 10, NUM_CLASSES + 1), torch.randn(2, 10, 8, 8)
    )
    query_output = QueryOutput(query_prediction)
    assert SegmentationOutput(query=query_output).query is query_output
    with pytest.raises(ValueError, match="exactly one"):
        SegmentationOutput(dense_logits=dense, query=query_output)
    with pytest.raises(ValueError, match="batch or query count"):
        QueryPrediction(torch.randn(2, 9, 6), torch.randn(2, 10, 8, 8))


def test_timm_adapter_converts_reported_nhwc_features(monkeypatch):
    class Info:
        def channels(self):
            return [7]

        def reduction(self):
            return [4]

        def get_dicts(self):
            return [{"module": "stage"}]

    class FakeTimm(nn.Module):
        output_fmt = "NHWC"
        feature_info = Info()
        pretrained_cfg: ClassVar = {
            "mean": (0.1, 0.2, 0.3),
            "std": (0.4, 0.5, 0.6),
            "input_space": "RGB",
        }

        def forward(self, image):
            return [torch.zeros(image.shape[0], image.shape[2] // 4, image.shape[3] // 4, 7)]

    monkeypatch.setattr(
        "segmentary.models.backbones.timm.timm.create_model", lambda *a, **k: FakeTimm()
    )
    backbone = TimmBackbone("fake", pretrained=True, out_indices=(0,))
    output = backbone(torch.randn(2, 3, 64, 96))
    assert output[0].shape == (2, 7, 16, 24)
    assert backbone.input_mean == (0.1, 0.2, 0.3)
    assert backbone.input_normalization_source == "timm_pretrained_cfg"


def test_scratch_timm_uses_an_explicit_segmentary_normalization(monkeypatch):
    class Info:
        def channels(self):
            return [4]

        def reduction(self):
            return [4]

    class FakeTimm(nn.Module):
        feature_info = Info()
        pretrained_cfg: ClassVar = {
            "mean": (0.9, 0.8, 0.7),
            "std": (0.6, 0.5, 0.4),
            "input_space": "BGR",
        }

        def forward(self, image):
            return [torch.zeros(image.shape[0], 4, image.shape[2] // 4, image.shape[3] // 4)]

    monkeypatch.setattr(
        "segmentary.models.backbones.timm.timm.create_model", lambda *args, **kwargs: FakeTimm()
    )
    backbone = TimmBackbone("fake", pretrained=False, out_indices=(0,))
    assert backbone.input_mean == (0.485, 0.456, 0.406)
    assert backbone.input_std == (0.229, 0.224, 0.225)
    assert backbone.input_channel_order == "rgb"
    assert backbone.input_normalization_source == "imagenet_scratch_default"


def test_pretrained_timm_rejects_missing_processor_metadata(monkeypatch):
    class Info:
        def channels(self):
            return [4]

        def reduction(self):
            return [4]

    class FakeTimm(nn.Module):
        feature_info = Info()
        pretrained_cfg: ClassVar = {}

    monkeypatch.setattr(
        "segmentary.models.backbones.timm.timm.create_model", lambda *args, **kwargs: FakeTimm()
    )
    with pytest.raises(ValueError, match="no complete mean/std processor contract"):
        TimmBackbone("fake", pretrained=True, out_indices=(0,))


def test_real_timm_resnet18_native_builder_cpu_forward_backward():
    backbone_spec = SimpleNamespace(
        kind="timm",
        name="resnet18",
        weights="scratch",
        out_indices=(1, 2, 3, 4),
        in_channels=3,
    )
    neck_spec = SimpleNamespace(
        kind="fpn",
        out_channels=16,
        num_outputs=4,
        norm="group",
        activation="relu",
    )
    head_spec = _common("segformer", in_indices=(0, 1, 2, 3), channels=16, dropout=0.0)
    auxiliary_spec = SimpleNamespace(
        name="s16",
        loss_weight=0.4,
        head=_common(
            "fcn",
            in_indices=(2,),
            channels=8,
            num_convs=1,
            kernel_size=3,
            dilation=1,
            dropout=0.0,
        ),
    )
    model = build_native_model(backbone_spec, neck_spec, head_spec, (auxiliary_spec,), NUM_CLASSES)
    image = torch.randn(2, 3, 64, 96)
    target = torch.randint(NUM_CLASSES, (2, 64, 96))
    loss = _dense_training_loss(model, image, target)
    loss.backward()
    assert torch.isfinite(loss)
    assert model.validate_parameter_partition()["backbone"] > 0
    assert all(parameter.grad is not None for parameter in model.parameters())


def test_real_timm_convnext_channel_mapper_dpt_cpu_forward_backward():
    backbone_spec = SimpleNamespace(
        kind="timm",
        name="convnext_tiny",
        weights="scratch",
        out_indices=(0, 1, 2, 3),
        in_channels=3,
    )
    neck_spec = SimpleNamespace(
        kind="channel_mapper",
        out_channels=16,
        kernel_size=1,
        num_outputs=4,
        norm="group",
        activation="relu",
    )
    head_spec = _common("dpt", in_indices=(0, 1, 2, 3), channels=16, dropout=0.0)
    model = build_native_model(backbone_spec, neck_spec, head_spec, (), NUM_CLASSES)
    image = torch.randn(1, 3, 64, 96)
    target = torch.randint(NUM_CLASSES, (1, 64, 96))
    loss = _dense_training_loss(model, image, target)
    loss.backward()
    assert torch.isfinite(loss)
    assert model.validate_parameter_partition()["backbone"] > 0
    assert all(parameter.grad is not None for parameter in model.parameters())


def test_real_timm_resnet50_fpn_ocr_cpu_forward_backward():
    backbone_spec = SimpleNamespace(
        kind="timm",
        name="resnet50",
        weights="scratch",
        out_indices=(1, 2, 3, 4),
        in_channels=3,
    )
    neck_spec = SimpleNamespace(
        kind="fpn",
        out_channels=16,
        num_outputs=4,
        norm="group",
        activation="relu",
    )
    head_spec = _common(
        "ocr",
        in_indices=(0, 1, 2, 3),
        channels=24,
        key_channels=12,
        attention_scale=1,
        dropout=0.0,
        coarse_loss_weight=0.4,
    )
    model = build_native_model(backbone_spec, neck_spec, head_spec, (), NUM_CLASSES)
    image = torch.randn(1, 3, 64, 96)
    target = torch.randint(NUM_CLASSES, (1, 64, 96))
    loss = _dense_training_loss(model, image, target)
    loss.backward()
    assert torch.isfinite(loss)
    assert model.validate_parameter_partition()["backbone"] > 0
    assert all(parameter.grad is not None for parameter in model.parameters())


def test_native_four_step_baby_training_updates_every_component():
    torch.manual_seed(0)
    model = _toy_model()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    before = {name: parameter.detach().clone() for name, parameter in model.named_parameters()}
    losses = []
    for _ in range(4):
        image = torch.randn(2, 3, 64, 96)
        target = torch.randint(NUM_CLASSES, (2, 64, 96))
        optimizer.zero_grad(set_to_none=True)
        loss = _dense_training_loss(model, image, target)
        assert torch.isfinite(loss)
        loss.backward()
        assert all(parameter.grad is not None for parameter in model.parameters())
        optimizer.step()
        losses.append(float(loss.detach()))
    assert all(torch.isfinite(torch.tensor(losses)))
    for prefix in ("backbone.", "neck.", "head.", "auxiliary_heads."):
        assert any(
            name.startswith(prefix) and not torch.equal(before[name], parameter.detach())
            for name, parameter in model.named_parameters()
        )


def test_channel_mapper_dpt_four_step_baby_training_updates_every_component():
    torch.manual_seed(7)
    model = _toy_dpt_model()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    before = {name: parameter.detach().clone() for name, parameter in model.named_parameters()}
    losses = []
    for _ in range(4):
        image = torch.randn(2, 3, 64, 96)
        target = torch.randint(NUM_CLASSES, (2, 64, 96))
        optimizer.zero_grad(set_to_none=True)
        loss = _dense_training_loss(model, image, target)
        assert torch.isfinite(loss)
        loss.backward()
        assert all(parameter.grad is not None for parameter in model.parameters())
        optimizer.step()
        losses.append(float(loss.detach()))
    assert torch.isfinite(torch.tensor(losses)).all()
    for prefix in ("backbone.", "neck.", "head."):
        assert any(
            name.startswith(prefix) and not torch.equal(before[name], parameter.detach())
            for name, parameter in model.named_parameters()
        )


def test_ocr_four_step_baby_training_updates_both_classifiers_and_all_components():
    torch.manual_seed(11)
    model = _toy_ocr_model()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    before = {name: parameter.detach().clone() for name, parameter in model.named_parameters()}
    losses = []
    for _ in range(4):
        image = torch.randn(2, 3, 64, 96)
        target = torch.randint(NUM_CLASSES, (2, 64, 96))
        optimizer.zero_grad(set_to_none=True)
        loss = _dense_training_loss(model, image, target)
        assert torch.isfinite(loss)
        loss.backward()
        assert all(parameter.grad is not None for parameter in model.parameters())
        optimizer.step()
        losses.append(float(loss.detach()))
    assert torch.isfinite(torch.tensor(losses)).all()
    for prefix in ("backbone.", "neck.", "head."):
        assert any(
            name.startswith(prefix) and not torch.equal(before[name], parameter.detach())
            for name, parameter in model.named_parameters()
        )
    for name in (
        "head.coarse_classifier.weight",
        "head.coarse_classifier.bias",
        "head.classifier.weight",
        "head.classifier.bias",
    ):
        assert not torch.equal(before[name], dict(model.named_parameters())[name].detach())


class _TrainingView(nn.Module):
    """DDP-visible scalar that consumes primary and every auxiliary prediction."""

    def __init__(self, model: NativeDenseSegmenter) -> None:
        super().__init__()
        self.model = model

    def forward(self, image: Tensor, target: Tensor) -> Tensor:
        return _dense_training_loss(self.model, image, target)


def test_native_auxiliary_training_has_no_unused_parameters_under_gloo_ddp(tmp_path):
    if not dist.is_available():
        pytest.skip("torch.distributed unavailable")
    if dist.is_initialized():
        pytest.skip("another test already initialized torch.distributed")
    init_file = tmp_path / "gloo-init"
    dist.init_process_group("gloo", init_method=f"file://{init_file}", rank=0, world_size=1)
    try:
        wrapped = nn.parallel.DistributedDataParallel(_TrainingView(_toy_model()))
        image = torch.randn(2, 3, 64, 96)
        target = torch.randint(NUM_CLASSES, (2, 64, 96))
        loss = wrapped(image, target)
        loss.backward()
        assert torch.isfinite(loss)
        assert all(parameter.grad is not None for parameter in wrapped.parameters())
    finally:
        dist.destroy_process_group()


def test_ocr_intrinsic_auxiliary_has_no_unused_parameters_under_gloo_ddp(tmp_path):
    if not dist.is_available():
        pytest.skip("torch.distributed unavailable")
    if dist.is_initialized():
        pytest.skip("another test already initialized torch.distributed")
    init_file = tmp_path / "gloo-ocr-init"
    dist.init_process_group("gloo", init_method=f"file://{init_file}", rank=0, world_size=1)
    try:
        wrapped = nn.parallel.DistributedDataParallel(_TrainingView(_toy_ocr_model()))
        image = torch.randn(2, 3, 64, 96)
        target = torch.randint(NUM_CLASSES, (2, 64, 96))
        loss = wrapped(image, target)
        loss.backward()
        assert torch.isfinite(loss)
        assert all(parameter.grad is not None for parameter in wrapped.parameters())
    finally:
        dist.destroy_process_group()
