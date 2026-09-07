"""Exercise GPU smoke architecture construction on CPU without external data."""

import importlib.util
from pathlib import Path

import pytest
import torch

SPEC = importlib.util.spec_from_file_location(
    "validate_object_gpu", Path(__file__).parents[1] / "scripts" / "validate_object_gpu.py"
)
assert SPEC is not None and SPEC.loader is not None
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


@pytest.mark.parametrize("arch", harness.FAMILIES)
def test_smoke_architecture_real_forward_backward(arch):
    from segmentary.objects.data import ObjectTarget
    from segmentary.objects.loss import ObjectQueryLoss

    model = harness.tiny_architecture(arch, 2, 16, (64, 96))
    image = torch.rand(1, 3, 64, 96)
    # Deliberately different native target size; no instance can disappear in an RGB resize.
    masks = torch.zeros(2, 96, 192, dtype=torch.bool)
    masks[0, 5:20, 8:30] = True
    masks[1, 40:60, 90:130] = True
    target = ObjectTarget(
        torch.tensor([0, 1]),
        masks,
        torch.ones(96, 192, dtype=torch.bool),
        torch.zeros(2, dtype=torch.bool),
        1,
        (96, 192),
    )
    loss = ObjectQueryLoss(2, num_points=32)(model.forward_output(image).query, [target])
    loss.backward()
    assert torch.isfinite(loss)
    assert any(p.grad is not None and p.grad.abs().sum() > 0 for p in model.parameters())


def test_published_initializer_audit_rejects_active_missing_weights():
    spec = importlib.util.spec_from_file_location(
        "benchmark_cityscapes_objects",
        Path(__file__).parents[1] / "scripts" / "benchmark_cityscapes_objects.py",
    )
    assert spec is not None and spec.loader is not None
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    info = {
        "loading_info": {
            "missing_keys": ["model.pixel_level_module.encoder.swin.layernorm.weight"],
            "unexpected_keys": [
                "model.pixel_level_module.encoder.swin.encoder.layers.0.attention.relative_position_index"
            ],
            "mismatched_keys": [],
            "error_msgs": [],
        }
    }
    assert benchmark.validate_initializer(info)["missing_final_norm"]
    info["loading_info"]["missing_keys"] = ["class_predictor.weight"]
    with pytest.raises(ValueError, match="unaudited"):
        benchmark.validate_initializer(info)
