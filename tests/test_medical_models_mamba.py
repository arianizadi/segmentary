"""Independent recurrence, gradients, directions and actual 3D model contracts."""

from __future__ import annotations

import contextlib
import importlib.util

import pytest
import torch
from torch import Tensor
from torch.nn import functional as F

from segmentary.medical.mamba_scan import Mamba, MambaBranch, selective_scan_torch
from segmentary.medical.models_mamba import MODEL_NAMES, build_model, model_metadata


@pytest.fixture(autouse=True)
def _small_cpu_thread_pool():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


def _serial(u, delta, a, b, c, d=None, z=None, bias=None):
    dt = F.softplus(delta + (0 if bias is None else bias[None, :, None]))
    state = u.new_zeros(u.shape[0], u.shape[1], a.shape[-1])
    outputs = []
    for index in range(u.shape[-1]):
        state = (
            torch.exp(dt[:, :, index, None] * a) * state
            + dt[:, :, index, None] * b[:, None, :, index] * u[:, :, index, None]
        )
        outputs.append((state * c[:, None, :, index]).sum(-1))
    result = torch.stack(outputs, dim=-1)
    if d is not None:
        result = result + u * d[None, :, None]
    return result if z is None else result * F.silu(z)


@pytest.mark.parametrize("chunk_size", [1, 3, 8, 40])
@pytest.mark.parametrize("checkpoint_chunks", [False, True])
def test_associative_scan_matches_independent_serial_outputs_and_gradients(
    chunk_size, checkpoint_chunks
):
    torch.manual_seed(109)
    args = [
        torch.randn(2, 3, 11, dtype=torch.double),
        torch.randn(2, 3, 11, dtype=torch.double),
        -torch.rand(3, 4, dtype=torch.double),
        torch.randn(2, 4, 11, dtype=torch.double),
        torch.randn(2, 4, 11, dtype=torch.double),
        torch.randn(3, dtype=torch.double),
        torch.randn(2, 3, 11, dtype=torch.double),
        torch.randn(3, dtype=torch.double),
    ]
    args = [item.requires_grad_() for item in args]
    actual = selective_scan_torch(*args, chunk_size=chunk_size, checkpoint_chunks=checkpoint_chunks)
    expected = _serial(*args)
    torch.testing.assert_close(actual, expected, atol=1e-10, rtol=1e-10)
    probe = torch.randn_like(actual)
    actual_grad = torch.autograd.grad((actual * probe).sum(), args)
    expected_grad = torch.autograd.grad((expected * probe).sum(), args)
    for result, reference in zip(actual_grad, expected_grad, strict=True):
        torch.testing.assert_close(result, reference, atol=1e-9, rtol=1e-9)


def test_scan_gradcheck_and_extreme_decay_are_finite():
    args = (
        torch.randn(1, 2, 3, dtype=torch.double, requires_grad=True),
        torch.randn(1, 2, 3, dtype=torch.double, requires_grad=True),
        -torch.rand(2, 2, dtype=torch.double, requires_grad=True),
        torch.randn(1, 2, 3, dtype=torch.double, requires_grad=True),
        torch.randn(1, 2, 3, dtype=torch.double, requires_grad=True),
    )
    assert torch.autograd.gradcheck(lambda *xs: selective_scan_torch(*xs, chunk_size=2), args)
    extreme = selective_scan_torch(
        args[0], args[1] + 1000, args[2] * 1000, args[3], args[4], chunk_size=2
    )
    assert torch.isfinite(extreme).all()
    torch.testing.assert_close(
        extreme, _serial(args[0], args[1] + 1000, args[2] * 1000, args[3], args[4])
    )


def _branch_reference(branch: MambaBranch, xz: Tensor) -> Tensor:
    x, gate = xz.chunk(2, 1)
    conv = branch.conv1d
    x = F.silu(
        F.conv1d(x, conv.weight, conv.bias, padding=conv.padding, groups=conv.groups)[
            ..., : x.shape[-1]
        ]
    )
    packed = F.linear(x.transpose(1, 2), branch.x_proj.weight)
    dt, b, c = packed.split([branch.dt_rank, branch.state_size, branch.state_size], -1)
    return _serial(
        x,
        F.linear(dt, branch.dt_proj.weight).transpose(1, 2),
        -branch.a_log.exp(),
        b.transpose(1, 2),
        c.transpose(1, 2),
        branch.d,
        gate,
        branch.dt_proj.bias,
    )


def test_segmamba_uses_three_independent_directions_with_exact_upstream_permutation():
    torch.manual_seed(73)
    model = Mamba(4, d_state=2, three_direction=True, nslices=3, chunk_size=4).double()
    x = torch.randn(2, 12, 4, dtype=torch.double, requires_grad=True)
    xz = F.linear(x, model.in_proj.weight).transpose(1, 2)
    forward = _branch_reference(model.forward_branch, xz)
    reverse = _branch_reference(model.reverse_branch, xz.flip(-1)).flip(-1)
    permuted = torch.stack(xz.chunk(3, dim=-1), dim=-1).flatten(-2)
    spatial = _branch_reference(model.spatial_branch, permuted)
    spatial = spatial.reshape(2, model.d_inner, 4, 3).permute(0, 1, 3, 2).flatten(-2)
    expected = F.linear((forward + reverse + spatial).transpose(1, 2), model.out_proj.weight)
    actual = model(x)
    torch.testing.assert_close(actual, expected, atol=1e-10, rtol=1e-10)
    actual.square().sum().backward()
    for branch in (model.forward_branch, model.reverse_branch, model.spatial_branch):
        assert branch.a_log.grad is not None and branch.a_log.grad.abs().sum() > 0
    assert not torch.allclose(actual, F.linear(forward.transpose(1, 2), model.out_proj.weight))


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_real_architecture_scratch_forward_backward_and_native_tensor_shape(name, monkeypatch):
    if name == "segmamba":
        pytest.importorskip("monai")

    def forbidden(*args, **kwargs):
        raise AssertionError("Scratch construction must not load checkpoints or download weights")

    monkeypatch.setattr(torch, "load", forbidden)
    monkeypatch.setattr(torch.hub, "load_state_dict_from_url", forbidden)
    metadata = model_metadata(name)
    patch = tuple(metadata["smoke_patch_size"])
    model = build_model(
        name, in_channels=2, patch_size=patch, model_options=metadata["smoke_options"]
    )
    x = torch.randn(1, 2, patch[0] - 1, patch[1], patch[2] - 2, requires_grad=True)
    logits = model(x)
    assert logits.shape == (1, 3, *x.shape[2:])
    assert torch.isfinite(logits).all()
    target = torch.randint(0, 3, (1, *x.shape[2:]))
    F.cross_entropy(logits, target).backward()
    assert x.grad is not None and torch.isfinite(x.grad).all()
    scan_parameters = [p for n, p in model.named_parameters() if n.endswith("a_log")]
    assert scan_parameters and all(
        p.grad is not None and torch.isfinite(p.grad).all() for p in scan_parameters
    )
    assert all(p.grad.abs().sum() > 0 for p in scan_parameters)
    assert model.initialization == "scratch"
    expected_branches = 12 if name == "segmamba" else 3 if name == "umamba_enc" else 1
    assert len(scan_parameters) == expected_branches


def test_umamba_encoder_uses_patch_and_channel_tokens():
    model = build_model(
        "umamba_enc", patch_size=(8, 8, 8), model_options={"features": [2, 4, 8], "d_state": 2}
    )
    layers = model.network.mixers
    assert [layer.channel_token for layer in layers] == [False, False, True]
    assert layers[-1].dim == 8


@pytest.mark.parametrize(
    "option",
    [
        {"pretrained": False},
        {"weights": None},
        {"checkpoint": "x.pt"},
        {"scan_backend": "auto"},
        {"d_state": True},
        {"features": [4]},
        {"scan_chunk_size": 0},
    ],
)
def test_forbidden_or_invalid_options_fail_loudly(option):
    with pytest.raises(ValueError):
        build_model("umamba_bot", model_options=option)


def test_segmamba_invalid_slice_plan_and_oversized_input_fail():
    with pytest.raises(ValueError, match="divisible"):
        build_model("segmamba", patch_size=(32, 32, 32), model_options={"num_slices": [3, 3, 3, 3]})
    model = build_model("umamba_bot", patch_size=(8, 8, 8), model_options={"features": [2, 4, 8]})
    with pytest.raises(ValueError, match="sliding-window"):
        model(torch.zeros(1, 1, 9, 8, 8))


def test_selected_native_backend_never_falls_back_on_cpu():
    model = Mamba(2, d_state=2, scan_backend="native")
    with pytest.raises(ValueError, match="requires CUDA"):
        model(torch.randn(1, 4, 2))


@pytest.mark.gpu
def test_optional_native_selective_scan_parity():
    if not torch.cuda.is_available() or importlib.util.find_spec("mamba_ssm") is None:
        pytest.skip("Native Mamba CUDA kernel unavailable")
    native = Mamba(4, d_state=2, scan_backend="native").cuda()
    portable = Mamba(4, d_state=2, scan_backend="torch").cuda()
    portable.load_state_dict(native.state_dict())
    x = torch.randn(1, 17, 4, device="cuda", requires_grad=True)
    with contextlib.nullcontext():
        actual, expected = portable(x), native(x)
    torch.testing.assert_close(actual, expected, atol=2e-5, rtol=2e-4)
    actual_grads = torch.autograd.grad(actual.square().sum(), tuple(portable.parameters()))
    expected_grads = torch.autograd.grad(expected.square().sum(), tuple(native.parameters()))
    for actual_grad, expected_grad in zip(actual_grads, expected_grads, strict=True):
        torch.testing.assert_close(actual_grad, expected_grad, atol=2e-5, rtol=2e-3)
