"""Real architecture executions: no mocked forward paths or downloaded weights."""

from __future__ import annotations

import socket

import pytest
import torch
import torch.nn.functional as F

pytest.importorskip("monai")
pytest.importorskip("einops")
pytest.importorskip("ml_collections")

from segmentary.medical.models_3d import MODEL_NAMES, build_model, model_metadata


@pytest.fixture(autouse=True)
def bounded_cpu_threads():
    old = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(old)


def _smoke(name):
    metadata = model_metadata(name)
    return build_model(
        name,
        patch_size=tuple(metadata["smoke_patch_size"]),
        model_options=metadata["smoke_options"],
    )


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_actual_cpu_forward_backward_random_initialization(name, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Fresh model construction attempted weight loading or network access")

    monkeypatch.setattr(torch, "load", forbidden)
    monkeypatch.setattr(torch.hub, "load_state_dict_from_url", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(torch.nn.Module, "load_state_dict", forbidden)
    torch.manual_seed(918)
    model = _smoke(name).train()
    # Odd, unequal dimensions exercise each network's pad/crop path. They must
    # remain spatial logits, never a classifier or a probability-only model.
    image = torch.randn(1, 1, 25, 29, 31)
    label = torch.randint(0, 3, (1, 25, 29, 31))
    before = {key: value.detach().clone() for key, value in model.named_parameters()}
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    output = model(image)
    assert output.shape == (1, 3, 25, 29, 31)
    assert torch.isfinite(output).all()
    assert not torch.allclose(output.sum(dim=1), torch.ones_like(output[:, 0]))
    loss = F.cross_entropy(output, label)
    loss.backward()
    gradients = [parameter.grad for parameter in model.parameters() if parameter.grad is not None]
    assert gradients and all(torch.isfinite(gradient).all() for gradient in gradients)
    assert not [
        key
        for key, parameter in model.named_parameters()
        if parameter.requires_grad and parameter.grad is None
    ]
    assert any(torch.count_nonzero(gradient) for gradient in gradients)
    optimizer.step()
    assert any(not torch.equal(before[key], value) for key, value in model.named_parameters())
    assert model.architecture_metadata["initialization"] == "random"


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_seed_controls_fresh_architecture_weights(name):
    torch.manual_seed(1234)
    first = _smoke(name).state_dict()
    torch.manual_seed(1234)
    second = _smoke(name).state_dict()
    assert first.keys() == second.keys()
    assert all(torch.equal(first[key], second[key]) for key in first)
    torch.manual_seed(1235)
    third = _smoke(name).state_dict()
    assert any(not torch.equal(first[key], third[key]) for key in first)


@pytest.mark.parametrize(
    ("name", "mechanism"),
    [
        ("unet_3d", "UNet"),
        ("dynunet", "DynUNet"),
        ("segresnet", "SegResNet"),
        ("mednext_v1", "MedNeXtBlock"),
        ("swin_unetr", "SwinTransformerBlock"),
        ("unetr", "TransformerBlock"),
        ("medformer", "BidirectionAttention"),
        ("transunet_3d", "Transformer"),
    ],
)
def test_named_architecture_contains_its_actual_mechanism(name, mechanism):
    model = _smoke(name)
    assert mechanism in {type(module).__name__ for module in model.modules()}
    if name == "transunet_3d":
        assert model.network.is_max_bottleneck_transformer
        assert model.architecture_metadata["variant"] == "encoder_transformer"


@pytest.mark.parametrize("name", MODEL_NAMES)
@pytest.mark.parametrize("option", ["pretrained", "weights", "checkpoint", "encoder_weights"])
def test_pretrained_and_unknown_options_are_rejected(name, option):
    with pytest.raises(ValueError, match="Unsupported"):
        build_model(name, model_options={option: "imagenet"})


@pytest.mark.parametrize("name", ["unetr", "transunet_3d"])
def test_positional_models_reject_oversized_input(name):
    model = _smoke(name)
    with pytest.raises(ValueError, match="exceeds"):
        model(torch.zeros(1, 1, 33, 32, 32))


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_channel_contract_is_checked(name):
    model = _smoke(name)
    with pytest.raises(ValueError, match="Expected"):
        model(torch.zeros(1, 3, 16, 16, 16))


def test_metadata_is_independent_and_does_not_mutate_defaults():
    metadata = model_metadata("unet_3d")
    metadata["default_options"]["channels"][0] = 999
    assert model_metadata("unet_3d")["default_options"]["channels"][0] == 32
    with pytest.raises(ValueError, match="Unknown"):
        build_model("pretend_transformer")


@pytest.mark.parametrize(
    ("name", "options", "message"),
    [
        ("unet_3d", {"channels": [4, 8]}, "at least three"),
        ("dynunet", {"filters": [4, True, 16]}, "integer"),
        ("swin_unetr", {"depths": [1, 1]}, "four depths"),
        ("unetr", {"hidden_size": 47}, "divide"),
        ("segresnet", {"init_filters": 9}, "divide"),
        ("mednext_v1", {"kernel_size": 4}, "3 or 5"),
        ("medformer", {"trans_num": [0] * 8}, "retain"),
        ("transunet_3d", {"vit_depth": 0}, "positive"),
    ],
)
def test_invalid_architecture_options_fail_before_forward(name, options, message):
    with pytest.raises(ValueError, match=message):
        build_model(name, model_options=options)


def test_transunet_config_is_not_shared_between_models():
    first = _smoke("transunet_3d")
    other = model_metadata("transunet_3d")["smoke_options"]
    other["vit_hidden_size"] = 96
    second = build_model("transunet_3d", patch_size=(32, 32, 32), model_options=other)
    assert first.network.transformer.embeddings.config.hidden_size == 48
    assert second.network.transformer.embeddings.config.hidden_size == 96


def test_mednext_checkpointed_variant_has_no_dead_trainable_dummy():
    model = build_model("mednext_v1", model_options={"model_id": "M"}).train()
    assert model.network.outside_block_checkpointing
    assert "network.dummy_tensor" in dict(model.named_buffers())
    assert "network.dummy_tensor" not in dict(model.named_parameters())
    output = model(torch.randn(1, 1, 32, 32, 32))
    F.cross_entropy(output, torch.randint(3, (1, 32, 32, 32))).backward()
    assert all(
        parameter.grad is not None and torch.isfinite(parameter.grad).all()
        for parameter in model.parameters()
        if parameter.requires_grad
    )
