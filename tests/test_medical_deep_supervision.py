"""Exercise real auxiliary heads, trunk identity, inference and resume behavior."""

import copy

import pytest
import torch

pytest.importorskip("monai")

from segmentary.medical.model_registry import build_model, model_metadata
from segmentary.medical.torch_data import training_loss


@pytest.fixture(autouse=True)
def bounded_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


def model(enabled):
    return build_model(
        "dynunet",
        patch_size=(32, 32, 32),
        model_options={"filters": [4, 8, 16, 32], "deep_supervision": enabled},
    )


def batch():
    images = torch.randn(2, 1, 32, 32, 32)
    labels = torch.zeros(2, 32, 32, 32, dtype=torch.long)
    labels[:, 6:26, 8:24, 4:28] = 1
    labels[:, 12:20, 12:20, 12:20] = 2
    return images, labels


def test_identical_primary_initialization_rng_and_inference():
    torch.manual_seed(381)
    control = model(False)
    after_control = torch.get_rng_state().clone()
    torch.manual_seed(381)
    supervised = model(True)
    assert torch.equal(after_control, torch.get_rng_state())
    assert control.state_dict().keys() == supervised.primary.state_dict().keys()
    for key, value in control.state_dict().items():
        assert torch.equal(value, supervised.primary.state_dict()[key]), key
    control.eval()
    supervised.eval()
    images = torch.randn(1, 1, 25, 29, 31)

    def forbidden(*args):
        raise AssertionError("Inference executed a training-only auxiliary head")

    handles = [head.register_forward_hook(forbidden) for head in supervised.auxiliary_heads]
    try:
        with torch.no_grad():
            assert torch.equal(control(images), supervised(images))
    finally:
        for handle in handles:
            handle.remove()


def test_real_auxiliary_and_encoder_gradients_and_hook_cleanup():
    torch.manual_seed(29)
    supervised = model(True).train()
    images, labels = batch()
    original = labels.clone()
    loss = training_loss(supervised, images, labels)
    assert torch.isfinite(loss)
    loss.backward()
    for name, parameter in supervised.named_parameters():
        assert parameter.grad is not None, name
        assert torch.isfinite(parameter.grad).all(), name
    for head in supervised.auxiliary_heads:
        assert torch.count_nonzero(head.weight.grad) > 0
    assert torch.equal(original, labels)
    assert all(not block._forward_hooks for block in supervised.primary.network.upsamples)


def test_failed_forward_removes_capture_hooks(monkeypatch):
    supervised = model(True).train()

    def fail(*args):
        raise RuntimeError("injected forward failure")

    monkeypatch.setattr(supervised.primary, "forward", fail)
    with pytest.raises(RuntimeError, match="injected"):
        training_loss(supervised, *batch())
    assert all(not block._forward_hooks for block in supervised.primary.network.upsamples)


def test_training_rejects_implicit_padding_and_eval_loss():
    supervised = model(True).train()
    with pytest.raises(ValueError, match="align to the DynUNet grid"):
        training_loss(
            supervised,
            torch.zeros(1, 1, 31, 32, 32),
            torch.zeros(1, 31, 32, 32, dtype=torch.long),
        )
    supervised.eval()
    with pytest.raises(ValueError, match="training mode"):
        training_loss(supervised, *batch())


def test_optimizer_resume_retains_auxiliary_and_primary_state():
    torch.manual_seed(193)
    uninterrupted = model(True).train()
    optimizer = torch.optim.AdamW(uninterrupted.parameters(), lr=0.001)
    images, labels = batch()

    def step(network, opt):
        opt.zero_grad(set_to_none=True)
        training_loss(network, images, labels).backward()
        opt.step()

    step(uninterrupted, optimizer)
    weights, state = (
        copy.deepcopy(uninterrupted.state_dict()),
        copy.deepcopy(optimizer.state_dict()),
    )
    step(uninterrupted, optimizer)
    resumed = model(True).train()
    resumed.load_state_dict(weights, strict=True)
    resumed_optimizer = torch.optim.AdamW(resumed.parameters(), lr=0.001)
    resumed_optimizer.load_state_dict(state)
    step(resumed, resumed_optimizer)
    for name, value in uninterrupted.state_dict().items():
        assert torch.equal(value, resumed.state_dict()[name]), name


def test_resolved_metadata_describes_actual_objective():
    metadata = model_metadata("dynunet", model_options={"deep_supervision": True})
    assert "auxiliary" in metadata["objective"]
    assert metadata["deep_supervision"]["auxiliary_scales"] == [2, 4]
    assert model_metadata("dynunet")["objective"] == "dense_ce_dice_no_auxiliary_heads"
    with pytest.raises(ValueError, match="boolean"):
        model_metadata("dynunet", model_options={"deep_supervision": 1})
    with pytest.raises(ValueError, match="four DynUNet levels"):
        model_metadata("dynunet", model_options={"filters": [4, 8, 16], "deep_supervision": True})
