"""Real architecture/gradient and forbidden-initialization contracts for CT adapters."""

from __future__ import annotations

import gc
import socket

import pytest
import torch
import torch.nn.functional as F

from segmentary.medical.models_2d import (
    MODEL_NAMES,
    build_model,
    model_metadata,
    semantic_boundaries,
)


@pytest.fixture(autouse=True)
def bounded_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)
    gc.collect()


@pytest.fixture
def no_weight_loading(monkeypatch):
    """Even cached external checkpoints violate scratch initialization."""
    import huggingface_hub
    import transformers

    def forbidden(*args, **kwargs):
        raise AssertionError("scratch construction attempted external weight loading or networking")

    monkeypatch.setattr(torch, "load", forbidden)
    monkeypatch.setattr(torch.hub, "load_state_dict_from_url", forbidden)
    monkeypatch.setattr(torch.nn.Module, "load_state_dict", forbidden)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", forbidden)
    monkeypatch.setattr(transformers.PreTrainedModel, "from_pretrained", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_real_2d_architectures_forward_backward_offline(name, no_weight_loading):
    """Every declared family really trains with five CT slice channels."""
    torch.manual_seed(19)
    model = build_model(
        name, in_channels=5, patch_size=(64, 64), model_options={"profile": "smoke"}
    )
    images = torch.randn(2, 5, 64, 64, requires_grad=True)
    targets = torch.zeros((2, 64, 64), dtype=torch.long)
    targets[:, 16:48, 16:48] = 1
    targets[:, 28:36, 28:36] = 2
    model.train()
    if hasattr(model, "training_loss"):
        loss = model.training_loss(images, targets)
    else:
        loss = F.cross_entropy(model(images), targets)
    assert loss.ndim == 0 and torch.isfinite(loss)
    loss.backward()
    assert images.grad is not None and torch.isfinite(images.grad).all()
    assert images.grad.abs().sum() > 0
    gradients = [p.grad for p in model.parameters() if p.requires_grad]
    assert all(grad is not None and torch.isfinite(grad).all() for grad in gradients)
    assert sum(grad.abs().sum() for grad in gradients) > 0
    model.eval()
    with torch.no_grad():
        output = model(images.detach()[..., :61, :59])
    assert output.shape == (2, 3, 61, 59)
    assert torch.isfinite(output).all()


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_standard_model_actual_one_channel_construction_and_forward(name, no_weight_loading):
    """The advertised baseline capacity also constructs offline, not just smoke."""
    model = build_model(name, in_channels=1, patch_size=(128, 128)).eval()
    assert model.medical_model_metadata["profile"] == "standard"
    with torch.no_grad():
        output = model(torch.randn(1, 1, 64, 96))
    assert output.shape == (1, 3, 64, 96)
    assert torch.isfinite(output).all()


@pytest.mark.parametrize("name", ["maskformer", "mask2former"])
def test_query_models_use_native_matching_and_train_classifier(name):
    torch.manual_seed(42)
    model = build_model(name, model_options={"profile": "smoke"}, patch_size=(64, 64))
    images = torch.randn(2, 1, 64, 64)
    target = torch.zeros((2, 64, 64), dtype=torch.long)
    target[:, 12:28, 16:40] = 1
    target[:, 18:23, 20:24] = 2
    torch.manual_seed(123)
    loss = model.training_loss(images, target)
    loss.backward()
    classifier = model.model.class_predictor
    assert classifier.weight.grad is not None and classifier.weight.grad.abs().sum() > 0
    assert model_metadata(name)["training_loss"]["name"] == "native_hungarian_query_loss"
    with pytest.raises(ValueError, match="padded pixels lack annotations"):
        model.training_loss(images[..., :63, :], target[..., :63, :])


def test_boundary_targets_are_semantic_transitions_without_outer_border():
    targets = torch.tensor([[[0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 2, 2]]])
    expected = torch.tensor(
        [[[False, True, True, False], [False, True, True, True], [False, True, True, True]]]
    )
    assert torch.equal(semantic_boundaries(targets), expected)
    assert not semantic_boundaries(torch.zeros_like(targets)).any()


def test_scratch_rng_is_reproducible_but_seeds_change_encoder():
    def weight(seed):
        torch.manual_seed(seed)
        model = build_model("lraspp", in_channels=5)
        return model.model.backbone["0"][0].weight.detach().clone()

    assert torch.equal(weight(123), weight(123))
    assert not torch.equal(weight(123), weight(124))


@pytest.mark.parametrize(
    "options",
    [{"pretrained": True}, {"weights": None}, {"encoder_weights": "imagenet"}, {"profile": "tiny"}],
)
def test_unrecognized_or_pretrained_options_fail_closed(options):
    with pytest.raises(ValueError):
        build_model("unet_2d", model_options=options)


def test_unknown_architecture_and_invalid_channels_fail():
    with pytest.raises(ValueError, match="unknown 2D model"):
        build_model("made_up_network")
    with pytest.raises(ValueError, match="positive integer"):
        build_model("unet_2d", in_channels=True)


def test_pidnet_empty_boundary_patch_still_supervises_boundary_head():
    model = build_model("pidnet", model_options={"profile": "smoke"})
    images = torch.randn(2, 1, 64, 64)
    loss = model.training_loss(images, torch.zeros((2, 64, 64), dtype=torch.long))
    loss.backward()
    assert model.model.seghead_d.conv2.weight.grad.abs().sum() > 0
