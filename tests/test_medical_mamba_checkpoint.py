"""Activation recomputation preserves Mamba weights, outputs and gradients."""

from __future__ import annotations

import pytest
import torch

from segmentary.medical import mamba_scan
from segmentary.medical.mamba_scan import Mamba
from segmentary.medical.models_mamba import MODEL_NAMES, build_model, model_metadata


@pytest.fixture(autouse=True)
def _threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


@pytest.mark.parametrize("three_direction", [False, True])
@pytest.mark.parametrize("input_grad", [False, True])
def test_checkpoint_preserves_initialization_output_and_every_parameter_gradient(
    three_direction, input_grad
):
    models = []
    for enabled in (False, True):
        torch.manual_seed(782)
        models.append(
            Mamba(
                4,
                d_state=2,
                expand=2,
                three_direction=three_direction,
                nslices=3,
                chunk_size=5,
                checkpoint_mamba=enabled,
            ).double()
        )
    for key, value in models[0].state_dict().items():
        torch.testing.assert_close(value, models[1].state_dict()[key], atol=0, rtol=0)
    source = torch.randn(2, 12, 4, dtype=torch.float64)
    inputs = [source.clone().requires_grad_(input_grad) for _ in models]
    outputs = [model(x) for model, x in zip(models, inputs, strict=True)]
    torch.testing.assert_close(outputs[0], outputs[1], atol=0, rtol=0)
    for output in outputs:
        output.square().mean().backward()
    for first, second in zip(models[0].parameters(), models[1].parameters(), strict=True):
        assert first.grad is not None and second.grad is not None
        torch.testing.assert_close(first.grad, second.grad, atol=1e-12, rtol=1e-12)
    if input_grad:
        torch.testing.assert_close(inputs[0].grad, inputs[1].grad, atol=1e-12, rtol=1e-12)


def test_checkpoint_scope_recomputes_mixer_but_never_runs_during_eval_or_no_grad(monkeypatch):
    calls = []
    original = mamba_scan.checkpoint

    def traced(function, *args, **kwargs):
        if getattr(function, "__name__", "") == "_forward":
            calls.append(kwargs)
        return original(function, *args, **kwargs)

    monkeypatch.setattr(mamba_scan, "checkpoint", traced)
    model = Mamba(4, d_state=2, checkpoint_mamba=True)
    model(torch.randn(2, 5, 4)).sum().backward()
    assert calls == [{"use_reentrant": False, "preserve_rng_state": True}]
    model.eval()
    model(torch.randn(2, 5, 4))
    model.train()
    with torch.no_grad():
        model(torch.randn(2, 5, 4))
    assert len(calls) == 1


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_all_architectures_expose_explicit_checkpoint_flag_without_reduced_capacity(name):
    if name == "segmamba":
        pytest.importorskip("monai")
    metadata = model_metadata(name)
    assert metadata["default_options"]["checkpoint_mamba"] is False
    assert "checkpoint_mamba" in metadata["allowed_options"]
    options = {**metadata["smoke_options"], "checkpoint_mamba": True}
    model = build_model(name, patch_size=metadata["smoke_patch_size"], model_options=options)
    mixers = [module for module in model.modules() if isinstance(module, Mamba)]
    assert mixers and all(module.checkpoint_mamba for module in mixers)
    assert model.resolved_model_options["checkpoint_mamba"] is True
    with pytest.raises(ValueError, match="checkpoint_mamba must be boolean"):
        build_model(name, model_options={"checkpoint_mamba": 1})
