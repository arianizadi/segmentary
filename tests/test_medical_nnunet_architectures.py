"""Actual anisotropic DynUNet forwards, gradients and official loading contract."""

from __future__ import annotations

import copy
import socket

import pytest
import torch
from torch import nn
from torch.nn import functional as F

pytest.importorskip("monai")

from segmentary.medical.nnunet_architectures import PlannedDynUNet


@pytest.fixture(autouse=True)
def bounded_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


def _kwargs():
    return {
        "input_channels": 1,
        "num_classes": 3,
        "n_stages": 7,
        "features_per_stage": [2, 4, 6, 8, 8, 8, 8],
        "kernel_sizes": [[1, 3, 3], *[[3, 3, 3]] * 6],
        "strides": [[1, 1, 1], [1, 2, 2], *[[2, 2, 2]] * 3, *[[1, 2, 2]] * 2],
        "conv_op": nn.Conv3d,
        "conv_bias": False,
        "norm_op": nn.InstanceNorm3d,
        "norm_op_kwargs": {"eps": 1e-5, "affine": True},
        "dropout_op": None,
        "dropout_op_kwargs": None,
        "nonlin": nn.LeakyReLU,
        "nonlin_kwargs": {"inplace": True},
    }


def test_native_anisotropic_heads_have_correct_grids_and_gradients():
    model = PlannedDynUNet(**_kwargs()).train()
    image = torch.randn(1, 1, 8, 64, 128)
    targets = torch.randint(0, 3, (1, 8, 64, 128))
    outputs = model(image)
    assert isinstance(outputs, list)
    assert [tuple(output.shape[2:]) for output in outputs] == [
        (8, 64, 128),
        (8, 32, 64),
        (4, 16, 32),
        (2, 8, 16),
        (1, 4, 8),
        (1, 2, 4),
    ]
    losses = [
        F.cross_entropy(
            output,
            F.interpolate(targets[:, None].float(), size=output.shape[2:], mode="nearest")[
                :, 0
            ].long(),
        )
        for output in outputs
    ]
    sum(losses).backward()
    for name, parameter in model.named_parameters():
        assert parameter.grad is not None, name
        assert torch.isfinite(parameter.grad).all(), name
    for head in model.network.deep_supervision_heads:
        assert any(parameter.grad.abs().sum() > 0 for parameter in head.parameters())


def test_official_inference_constructor_loads_same_keys_and_flag_is_independent_of_eval():
    model = PlannedDynUNet(**_kwargs(), deep_supervision=True).eval()
    inference = PlannedDynUNet(**_kwargs(), deep_supervision=False).eval()
    inference.load_state_dict(model.state_dict(), strict=True)
    image = torch.randn(1, 1, 8, 64, 128)
    with torch.no_grad():
        supervised = model(image)
        ordinary = inference(image)
        assert isinstance(supervised, list) and isinstance(ordinary, torch.Tensor)
        assert torch.equal(supervised[0], ordinary)
        model.decoder.deep_supervision = False
        assert torch.equal(model(image), ordinary)
        model.decoder.deep_supervision = True
        assert torch.equal(model(image)[0], ordinary)


def test_scratch_construction_is_seeded_offline_and_does_not_mutate_plan(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Fresh architecture attempted network access or checkpoint loading")

    monkeypatch.setattr(torch, "load", forbidden)
    monkeypatch.setattr(nn.Module, "load_state_dict", forbidden)
    monkeypatch.setattr(torch.hub, "load_state_dict_from_url", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    kwargs = _kwargs()
    before = copy.deepcopy(kwargs)
    torch.manual_seed(123)
    first = PlannedDynUNet(**kwargs)
    torch.manual_seed(123)
    second = PlannedDynUNet(**kwargs)
    assert kwargs == before
    assert all(
        torch.equal(value, second.state_dict()[key]) for key, value in first.state_dict().items()
    )
    assert first.architecture_metadata["pretrained"] is False
    torch.manual_seed(124)
    third = PlannedDynUNet(**kwargs)
    assert any(
        not torch.equal(value, third.state_dict()[key]) for key, value in first.state_dict().items()
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"conv_bias": True},
        {"conv_op": nn.Conv2d},
        {"norm_op": nn.BatchNorm3d},
        {"nonlin": nn.ReLU},
        {"dropout_op": nn.Dropout3d},
        {"dropout_op_kwargs": {"p": 0}},
        {"n_stages": 2},
        {"features_per_stage": [2, 4]},
        {"deep_supervision": 1},
        {"kernel_sizes": [[2, 3, 3]] * 7},
        {"strides": [[2, 2, 2]] * 7},
        {"norm_op_kwargs": {"unexpected": True}},
    ],
)
def test_unsupported_plan_semantics_fail_closed(overrides):
    with pytest.raises(ValueError):
        PlannedDynUNet(**{**_kwargs(), **overrides})


@pytest.mark.parametrize("shape", [(1, 1, 7, 64, 128), (1, 1, 8, 64, 64), (1, 3, 8, 64, 128)])
def test_shape_errors_do_not_silently_pad_or_resample(shape):
    with pytest.raises(ValueError):
        PlannedDynUNet(**_kwargs())(torch.randn(shape))


def test_real_nnunet_dotted_loader_and_loss_contract_when_installed():
    pytest.importorskip("nnunetv2")
    from nnunetv2.training.loss.compound_losses import DC_and_CE_loss
    from nnunetv2.training.loss.deep_supervision import DeepSupervisionWrapper
    from nnunetv2.utilities.get_network_from_plans import get_network_from_plans

    kwargs = _kwargs()
    kwargs.pop("input_channels")
    kwargs.pop("num_classes")
    kwargs["conv_op"] = "torch.nn.Conv3d"
    kwargs["norm_op"] = "torch.nn.InstanceNorm3d"
    kwargs["nonlin"] = "torch.nn.LeakyReLU"
    model = get_network_from_plans(
        "segmentary.medical.nnunet_architectures.PlannedDynUNet",
        kwargs,
        ["conv_op", "norm_op", "nonlin"],
        1,
        3,
        deep_supervision=True,
    )
    assert isinstance(model, PlannedDynUNet)
    assert model.decoder.deep_supervision
    # nnU-Net's unmodified loss gives the coarsest decoder zero weight on one
    # GPU, then normalizes the exponentially decreasing remaining weights.
    weights = [1, 0.5, 0.25, 0.125, 0.0625, 0]
    loss_function = DeepSupervisionWrapper(
        DC_and_CE_loss(
            {"batch_dice": False, "smooth": 1e-5, "do_bg": False, "ddp": False},
            {},
        ),
        [value / sum(weights) for value in weights],
    )
    outputs = model(torch.randn(1, 1, 8, 64, 128))
    label = torch.randint(0, 3, (1, 1, 8, 64, 128))
    targets = [
        F.interpolate(label.float(), size=output.shape[2:], mode="nearest").long()
        for output in outputs
    ]
    loss = loss_function(outputs, targets)
    assert torch.isfinite(loss)
    loss.backward()
    assert any(parameter.grad is not None for parameter in model.parameters())
