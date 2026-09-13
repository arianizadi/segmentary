"""Optional CUDA parity against the independently verified portable recurrence."""

import pytest
import torch

from segmentary.medical.mamba_scan import selective_scan_torch


@pytest.mark.gpu
@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16])
def test_native_selective_scan_outputs_and_gradients_match_portable(dtype):
    if not torch.cuda.is_available():
        pytest.skip("Requires CUDA")
    native = pytest.importorskip("mamba_ssm.ops.selective_scan_interface").selective_scan_fn
    torch.manual_seed(4081)
    shapes = [(2, 8, 33), (2, 8, 33), (8, 4), (2, 4, 33), (2, 4, 33), (8,), (2, 8, 33), (8,)]
    args = []
    for index, shape in enumerate(shapes):
        item = torch.randn(shape, device="cuda", dtype=torch.float32) * 0.2
        if index == 2:
            item = -item.abs() - 0.1
        if index not in (2, 5, 7):
            item = item.to(dtype)
        args.append(item.requires_grad_())
    output = native(*args, delta_softplus=True)
    expected = selective_scan_torch(*args, chunk_size=16)
    tolerance = 0.004 if dtype == torch.bfloat16 else 2e-5
    torch.testing.assert_close(output, expected, rtol=tolerance, atol=tolerance)
    probe = torch.randn_like(output)
    grad_native = torch.autograd.grad((output * probe).float().sum(), args)
    grad_portable = torch.autograd.grad((expected * probe).float().sum(), args)
    for actual, reference in zip(grad_native, grad_portable, strict=True):
        assert torch.isfinite(actual).all()
        torch.testing.assert_close(actual, reference, rtol=tolerance, atol=tolerance)
