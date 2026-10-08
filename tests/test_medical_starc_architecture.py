"""STAR-C ResEnc keeps the ResEnc L contract and is an exact copy of it at initialisation.

The geometry is the real Task07 strong-recipe ``nnUNetResEncUNetLPlans.json``
3d_fullres architecture (embedded below; set ``SEGMENTARY_TASK07_PLAN`` to read
the plan file itself) at a reduced CPU patch. Requires
dynamic-network-architectures (the nnU-Net env).
"""

from __future__ import annotations

import copy
import json
import math
import os
import pydoc
from pathlib import Path

import numpy as np
import pytest
import torch
from torch import nn

pytest.importorskip("dynamic_network_architectures")

from dynamic_network_architectures.architectures.unet import ResidualEncoderUNet

from segmentary.medical import nnunet_architectures
from segmentary.medical import star_completion as sc
from segmentary.medical.recipe_plan import RESENC_CLASS

TASK07_SPACING = [2.5, 0.8125, 0.8125]
TASK07_RESENC_L = {
    "conv_bias": True,
    "conv_op": "torch.nn.modules.conv.Conv3d",
    "dropout_op": None,
    "dropout_op_kwargs": None,
    "features_per_stage": [32, 64, 128, 256, 320, 320, 320],
    "kernel_sizes": [[1, 3, 3], [3, 3, 3], [3, 3, 3], [3, 3, 3], [3, 3, 3], [3, 3, 3], [3, 3, 3]],
    "n_blocks_per_stage": [1, 3, 4, 6, 6, 6, 6],
    "n_conv_per_stage_decoder": [1, 1, 1, 1, 1, 1],
    "n_stages": 7,
    "nonlin": "torch.nn.LeakyReLU",
    "nonlin_kwargs": {"inplace": True},
    "norm_op": "torch.nn.modules.instancenorm.InstanceNorm3d",
    "norm_op_kwargs": {"affine": True, "eps": 1e-05},
    "strides": [[1, 1, 1], [1, 2, 2], [2, 2, 2], [2, 2, 2], [2, 2, 2], [1, 2, 2], [1, 2, 2]],
}
# The real patch is 56 x 320 x 256; 16 x 128 x 128 keeps every stride and level.
PATCH = (16, 128, 128)
NARROW = {"features_per_stage": [4, 8, 8, 8, 8, 8, 8], "n_blocks_per_stage": [1] * 7}


@pytest.fixture(autouse=True)
def bounded_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(4)
    yield
    torch.set_num_threads(previous)


def _plan() -> dict:
    path = os.environ.get("SEGMENTARY_TASK07_PLAN")
    if path:
        plan = json.loads(Path(path).read_text())
        selected = plan["configurations"]["3d_fullres"]
        assert selected["architecture"]["network_class_name"] == RESENC_CLASS
        return plan
    return {
        "configurations": {
            "3d_fullres": {
                "spacing": list(TASK07_SPACING),
                "patch_size": [56, 320, 256],
                "architecture": {
                    "network_class_name": RESENC_CLASS,
                    "arch_kwargs": copy.deepcopy(TASK07_RESENC_L),
                    "_kw_requires_import": ["conv_op", "norm_op", "dropout_op", "nonlin"],
                },
            }
        },
    }


def _kwargs(plan: dict | None = None, **changes) -> dict:
    plan = plan or _plan()
    raw = copy.deepcopy(plan["configurations"]["3d_fullres"]["architecture"]["arch_kwargs"])
    for key in ("conv_op", "norm_op", "dropout_op", "nonlin"):
        if raw.get(key) is not None:
            raw[key] = pydoc.locate(raw[key])
    raw.update(input_channels=1, num_classes=3)
    raw.update(changes)
    return raw


def _pair(deep_supervision: bool, *, narrow: bool = True, **options):
    widths = NARROW if narrow else {}
    base_kwargs = {k: v for k, v in _kwargs(**widths).items() if not k.startswith("starc_")}
    torch.manual_seed(0)
    base = ResidualEncoderUNet(**base_kwargs, deep_supervision=deep_supervision)
    base.apply(base.initialize)
    torch.manual_seed(1)
    starc_kwargs = {f"starc_{k}": v for k, v in options.items()}
    model = nnunet_architectures.StarCResEncUNet(
        **base_kwargs,
        deep_supervision=deep_supervision,
        starc_spacing=TASK07_SPACING,
        **starc_kwargs,
    )
    model.apply(model.initialize)
    result = model.load_state_dict(base.state_dict(), strict=False)
    assert result.unexpected_keys == []
    assert result.missing_keys and all(key.startswith("starc.") for key in result.missing_keys)
    return base.eval(), model.eval()


@pytest.mark.parametrize("deep_supervision", [True, False])
def test_zero_initialised_starc_reproduces_resenc_l_logits_bit_for_bit(deep_supervision):
    base, model = _pair(deep_supervision, narrow=False)
    image = torch.randn(1, 1, *PATCH, generator=torch.Generator().manual_seed(2))
    # Force rendered stars so the identity does not rely on an empty prior.
    model.set_star_instances(
        sc.StarInstances(
            centres=torch.tensor([[[8.0, 60.0, 64.0], [4.0, 20.0, 100.0]]]),
            valid=torch.tensor([[True, True]]),
        )
    )
    with torch.no_grad():
        expected, actual = base(image), model(image)
    assert model.star_aux["prior"].abs().max() > 0
    if deep_supervision:
        assert isinstance(actual, list) and len(actual) == len(expected) == 6
        assert all(torch.equal(a, b) for a, b in zip(actual, expected, strict=True))
    else:
        assert isinstance(actual, torch.Tensor) and torch.equal(actual, expected)


def test_state_dict_is_a_superset_of_resenc_l_and_overhead_is_small():
    base, model = _pair(True, narrow=False)
    base_keys, keys = set(base.state_dict()), set(model.state_dict())
    assert base_keys < keys
    assert {key.split(".")[0] for key in keys - base_keys} == {"starc"}
    base_parameters = sum(p.numel() for p in base.parameters())
    added = sum(p.numel() for p in model.parameters()) - base_parameters
    assert base_parameters == 140_989_042  # the plan's recorded ResEnc L size
    assert 0 < added < 1_000_000
    assert model.starc_stride == (2, 4, 4)
    assert model.starc.gate[-1].bias.item() == -2.0
    assert model.starc.fusion_weight.abs().sum() == 0
    assert model.starc.tau().item() == pytest.approx(1.5)
    metadata = model.architecture_metadata
    assert metadata["level_stride"] == [2, 4, 4] and metadata["options"]["rays"] == 96


def test_plan_transfer_builds_the_network_from_its_dotted_path():
    transferred, _ = sc.transfer_starc_plan(_plan(), {"max_instances": 6})
    architecture = transferred["configurations"]["3d_fullres"]["architecture"]
    cls = pydoc.locate(architecture["network_class_name"])
    assert cls is nnunet_architectures.StarCResEncUNet
    raw = copy.deepcopy(architecture["arch_kwargs"])
    raw.update(NARROW)
    for key in architecture["_kw_requires_import"]:
        if raw.get(key) is not None:
            raw[key] = pydoc.locate(raw[key])
    network = cls(input_channels=1, num_classes=3, deep_supervision=False, **raw)
    assert network.starc.max_instances == 6
    assert network.starc_spacing == TASK07_SPACING
    with pytest.raises(ValueError, match="Unknown STAR-C"):
        cls(input_channels=1, num_classes=3, **raw, starc_ray_weight=0.5)
    raw.pop("starc_spacing")
    with pytest.raises(ValueError, match="starc_spacing"):
        cls(input_channels=1, num_classes=3, **raw)


def test_nnunet_builds_starc_from_the_transferred_plan():
    pytest.importorskip("nnunetv2")
    from nnunetv2.utilities.get_network_from_plans import get_network_from_plans

    transferred, _ = sc.transfer_starc_plan(_plan(), None)
    architecture = transferred["configurations"]["3d_fullres"]["architecture"]
    kwargs = copy.deepcopy(architecture["arch_kwargs"]) | NARROW
    network = get_network_from_plans(
        architecture["network_class_name"],
        kwargs,
        architecture["_kw_requires_import"],
        1,
        3,
        allow_init=True,
        deep_supervision=True,
    )
    assert type(network).__name__ == "StarCResEncUNet"
    # nnU-Net's initialisation keeps the STAR-C identity state.
    assert network.starc.fusion_weight.abs().sum() == 0
    assert network.starc.gate[-1].weight.abs().sum() == 0
    assert network.starc.centre_head[-1].weight.abs().sum() == 0


def _synthetic_targets(tmp_path: Path) -> tuple[sc.StarTargetBuilder, dict]:
    """Three lesions (one cut by the patch edge) and an in-plane scaled, rotated, mirrored frame."""
    shape = (40, 260, 260)
    spacing = np.asarray(TASK07_SPACING)
    z, y, x = np.meshgrid(
        *[np.arange(n) * s for n, s in zip(shape, spacing, strict=True)], indexing="ij"
    )
    segmentation = np.zeros(shape, np.uint8)
    for centre, radius in (((20, 130, 130), 9.0), ((16, 90, 160), 6.0), ((24, 175, 95), 12.0)):
        c = np.asarray(centre) * spacing
        segmentation[(z - c[0]) ** 2 + (y - c[1]) ** 2 + (x - c[2]) ** 2 <= radius**2] = 2
    table = sc.compute_case_targets(segmentation, spacing, [2], sc.star_geometry(96))
    sc.save_case_targets(tmp_path / "case.npz", table)
    builder = sc.StarTargetBuilder(
        tmp_path,
        spacing=spacing,
        rays=96,
        patch_size=PATCH,
        cell_stride=(2, 4, 4),
        ray_samples=48,
        max_gt_instances=8,
        core_fraction=0.3,
        sigma_min_mm=3.0,
        sigma_fraction=0.25,
        min_ray_mm=0.5,
        max_ray_mm=90.0,
    )
    angle = 0.4
    rotation = 1.15 * np.array(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]
    )
    # The patch centre maps to the volume's lesion region around (130, 130) in-plane.
    middle = (np.asarray(PATCH[1:]) - 1) / 2
    spatial = sc.frame_record((1, 2), rotation, np.array([130.0, 130.0]) - 40 - rotation @ middle)
    mirror = sc.mirror_record((2,), PATCH)
    frame = sc.compose_patch_frame([12, 40, 40], [spatial, mirror])
    targets = builder.build("case", frame, np.random.default_rng(0))
    return builder, sc.collate_star_targets([targets])


def test_cpu_forward_backward_on_the_task07_plan_with_star_losses(tmp_path):
    _, star = _synthetic_targets(tmp_path)
    assert star["centre_valid"].sum() == 3  # several lesions in this patch
    torch.manual_seed(0)
    model = nnunet_architectures.StarCResEncUNet(
        **_kwargs(), deep_supervision=True, starc_spacing=TASK07_SPACING
    )
    model.apply(model.initialize)
    with torch.no_grad():
        model.starc.fusion_weight.fill_(0.5)  # as after some training
    model.train()
    model.set_star_instances(
        sc.StarInstances(centres=star["centres"].float(), valid=star["centre_valid"].bool())
    )
    image = torch.randn(1, 1, *PATCH, generator=torch.Generator().manual_seed(3))
    outputs = model(image)
    assert len(outputs) == 6 and outputs[0].shape == (1, 3, *PATCH)
    aux = model.star_aux
    assert aux["heat_logits"].shape == (1, 1, 8, 32, 32)
    assert aux["log_radii"].shape == (1, 96, 8, 32, 32)
    prior = aux["prior"][0, 0]
    assert (prior > 0).sum() > 0 and (prior < 0).sum() > 0 and (prior == 0).sum() > 0
    target = torch.zeros((1, *PATCH), dtype=torch.long)
    segmentation_loss = nn.functional.cross_entropy(outputs[0], target)
    centre = sc.centre_focal_loss(aux["heat_logits"], star["heatmap"])
    ray = sc.ray_l1_loss(
        aux["log_radii"], star["ray_positions"], star["ray_targets"], star["ray_mask"]
    )
    loss = segmentation_loss + centre + 0.5 * ray
    assert torch.isfinite(loss)
    loss.backward()
    grads = {name: p.grad for name, p in model.named_parameters()}
    for name in (
        "starc.fusion_weight",
        "starc.tau_logit",
        "starc.gate.2.weight",
        "starc.ray_head.3.weight",
        "starc.centre_head.3.weight",
        "encoder.stem.convs.0.conv.weight",
    ):
        assert grads[name] is not None and torch.isfinite(grads[name]).all()
        assert grads[name].abs().sum() > 0, name
    # The segmentation loss reaches the ray head only through the rendered stars.
    model.zero_grad()
    model.set_star_instances(
        sc.StarInstances(centres=star["centres"].float(), valid=star["centre_valid"].bool())
    )
    nn.functional.cross_entropy(model(image)[0], target).backward()
    assert model.starc.ray_head[3].weight.grad.abs().sum() > 0
    assert model.starc.centre_head[3].weight.grad is None or (
        model.starc.centre_head[3].weight.grad.abs().sum() == 0
    )


def test_inference_proposals_render_multiple_lesions():
    _, model = _pair(False)
    with torch.no_grad():
        model.starc.fusion_weight.fill_(1.0)
    image = torch.randn(1, 1, *PATCH)
    # A crafted heatmap with three isolated level-2 peaks.
    original = model.starc.centre_head.forward

    def peaky(features):
        heat = torch.full((features.shape[0], 1, *features.shape[2:]), -8.0)
        for cell in ((2, 10, 10), (5, 20, 25), (4, 28, 6)):
            heat[(0, 0, *cell)] = 4.0
        return heat + 0 * original(features).sum()

    model.starc.centre_head.forward = peaky
    with torch.no_grad():
        fused = model(image)
        aux = model.star_aux
        model.starc.fusion_weight.zero_()
        plain = model(image)
    instances = aux["instances"]
    assert instances.valid.sum() == 3
    voxels = sorted(instances.centres[0, instances.valid[0]].tolist())
    cells = ((2, 10, 10), (5, 20, 25), (4, 28, 6))
    expected = sorted([[2 * a + 0.5, 4 * b + 1.5, 4 * c + 1.5] for a, b, c in cells])
    assert np.allclose(voxels, expected, atol=1e-4)
    assert not torch.equal(fused, plain)
    from scipy import ndimage

    _, blobs = ndimage.label(aux["prior"][0, 0].numpy() > 0)
    assert blobs == 3


def test_same_seed_gives_starc_exactly_the_resenc_l_initialisation():
    """Paired arms differ only by ``starc.*``: building the heads draws no global RNG."""
    base_kwargs = {k: v for k, v in _kwargs(**NARROW).items() if not k.startswith("starc_")}
    torch.manual_seed(11)
    base = ResidualEncoderUNet(**base_kwargs, deep_supervision=True)
    base.apply(base.initialize)
    torch.manual_seed(11)
    model = nnunet_architectures.StarCResEncUNet(
        **base_kwargs, deep_supervision=True, starc_spacing=TASK07_SPACING
    )
    model.apply(model.initialize)
    resenc, starc = base.state_dict(), model.state_dict()
    assert set(resenc) < set(starc)
    assert {key.split(".")[0] for key in set(starc) - set(resenc)} == {"starc"}
    assert all(torch.equal(resenc[key], starc[key]) for key in resenc)
