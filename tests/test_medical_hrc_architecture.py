"""HRC-ResEnc keeps the ResEnc L contract and is an exact copy of it at initialisation.

The geometry is the real Task07 strong-recipe ``nnUNetResEncUNetLPlans.json``
3d_fullres architecture (sha256 bd1a4c42...; foreground std 71.162 HU) at a
reduced CPU patch. Requires dynamic-network-architectures (the nnU-Net env).
"""

from __future__ import annotations

import copy

import pytest
import torch
from torch import nn

pytest.importorskip("dynamic_network_architectures")

from dynamic_network_architectures.architectures.unet import ResidualEncoderUNet

from segmentary.medical import nnunet_architectures
from segmentary.medical.host_reference import REFERENCE_MODES, HostReference
from segmentary.medical.recipe_plan import HRC_CLASS, RESENC_CLASS, transfer_plan

TASK07_FOREGROUND_STD = 71.16236877441406
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
SIGMA0 = 5.0 / TASK07_FOREGROUND_STD


@pytest.fixture(autouse=True)
def bounded_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(4)
    yield
    torch.set_num_threads(previous)


def _plan() -> dict:
    return {
        "foreground_intensity_properties_per_channel": {"0": {"std": TASK07_FOREGROUND_STD}},
        "configurations": {
            "3d_fullres": {
                "normalization_schemes": ["CTNormalization"],
                "architecture": {
                    "network_class_name": RESENC_CLASS,
                    "arch_kwargs": copy.deepcopy(TASK07_RESENC_L),
                    "_kw_requires_import": ["conv_op", "norm_op", "dropout_op", "nonlin"],
                },
            }
        },
    }


def _kwargs(**changes) -> dict:
    kwargs = copy.deepcopy(TASK07_RESENC_L)
    kwargs.update(conv_op=nn.Conv3d, norm_op=nn.InstanceNorm3d, nonlin=nn.LeakyReLU)
    kwargs.update(input_channels=1, num_classes=3)
    kwargs.update(changes)
    return kwargs


# Narrow widths keep the slower CPU tests fast; grids and strides are unchanged.
NARROW = {"features_per_stage": [4, 8, 8, 8, 8, 8, 8], "n_blocks_per_stage": [1] * 7}


def _pair(deep_supervision: bool, *, narrow: bool = True, **hrc) -> tuple[nn.Module, nn.Module]:
    widths = NARROW if narrow else {}
    torch.manual_seed(0)
    base = ResidualEncoderUNet(**_kwargs(**widths), deep_supervision=deep_supervision)
    base.apply(base.initialize)
    torch.manual_seed(1)
    model = nnunet_architectures.HRCResEncUNet(
        **_kwargs(**widths), deep_supervision=deep_supervision, hrc_sigma0=SIGMA0, **hrc
    )
    model.apply(model.initialize)
    result = model.load_state_dict(base.state_dict(), strict=False)
    assert result.unexpected_keys == []
    assert result.missing_keys and all(key.startswith("hrc.") for key in result.missing_keys)
    return base.eval(), model.eval()


@pytest.mark.parametrize("deep_supervision", [True, False])
def test_zero_initialised_hrc_reproduces_resenc_l_logits_bit_for_bit(deep_supervision):
    # FiLM output is exactly 0, so F * (1 + 0) + 0 == F in IEEE fp32 and every
    # later operation sees identical inputs. On CPU this is bitwise equality.
    base, model = _pair(deep_supervision, narrow=False)
    image = torch.randn(1, 1, *PATCH, generator=torch.Generator().manual_seed(2))
    with torch.no_grad():
        expected, actual = base(image), model(image)
    if deep_supervision:
        assert isinstance(actual, list) and len(actual) == len(expected) == 6
        assert all(torch.equal(a, b) for a, b in zip(actual, expected, strict=True))
    else:
        assert isinstance(actual, torch.Tensor) and torch.equal(actual, expected)


def test_state_dict_is_a_superset_of_resenc_l_and_parameter_overhead_is_small():
    base, model = _pair(True, narrow=False)
    base_keys, keys = set(base.state_dict()), set(model.state_dict())
    assert base_keys < keys
    assert {key.split(".")[1] for key in keys - base_keys} == {"0", "1", "2"}
    base_parameters = sum(p.numel() for p in base.parameters())
    added = sum(p.numel() for p in model.parameters()) - base_parameters
    assert base_parameters == 140_989_042  # the plan's recorded ResEnc L size
    assert 0 < added < 0.001 * base_parameters
    for block in model.hrc.values():
        assert block.film.weight.abs().sum() == 0 and block.film.bias.abs().sum() == 0


def test_deep_supervision_contract_and_coarse_heads_without_supervision():
    _, model = _pair(False)
    calls: list[int] = []
    for index, head in enumerate(model.decoder.seg_layers):
        head.register_forward_hook(lambda *_args, index=index: calls.append(index))
    image = torch.randn(1, 1, *PATCH)
    with torch.no_grad():
        output = model(image)
    assert output.shape == (1, 3, *PATCH)
    # Decoder stage 2 is level 3 and stage 3 is level 2 (the statistics level).
    assert sorted(calls) == [2, 3, 5]
    model.decoder.deep_supervision = True
    with torch.no_grad():
        outputs = model(image)
    divisors = [(1, 1, 1), (1, 2, 2), (2, 4, 4), (4, 8, 8), (8, 16, 16), (8, 32, 32)]
    assert [tuple(o.shape[2:]) for o in outputs] == [
        tuple(size // d for size, d in zip(PATCH, divisor, strict=True)) for divisor in divisors
    ]


def _activate(model: nn.Module, seed: int = 3) -> None:
    generator = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for block in model.hrc.values():
            block.film.weight.normal_(0, 0.05, generator=generator)


def test_trained_hrc_has_finite_gradients_under_autocast_and_differs_from_resenc():
    base, model = _pair(True)
    _activate(model)
    model.train()
    image = torch.randn(1, 1, 16, 64, 64)
    with torch.autocast("cpu", dtype=torch.bfloat16):
        outputs = model(image)
    with torch.no_grad():
        reference = base(image)
    assert not torch.equal(outputs[0].float(), reference[0])
    sum(output.float().square().mean() for output in outputs).backward()
    for name, parameter in model.hrc.named_parameters():
        assert parameter.grad is not None and torch.isfinite(parameter.grad).all(), name
    assert all(
        parameter.grad is None or torch.isfinite(parameter.grad).all()
        for parameter in model.parameters()
    )


def test_reference_override_and_capture_are_inference_only():
    _, model = _pair(False)
    _activate(model)
    image = torch.randn(1, 1, *PATCH)
    model.capture_reference = True
    with torch.no_grad():
        ordinary = model(image)
    assert set(model.captured_references) == {"coarse", "refined"}
    assert model.captured_references["coarse"].gland_mean.shape == (1, 1, 1, 1, 1)

    def shift(_name: str, reference: HostReference) -> HostReference:
        return HostReference(
            **{**vars(reference), "gland_mean": reference.gland_mean + 1.0}  # +71 HU
        )

    model.reference_override = shift
    with torch.no_grad():
        swapped = model(image)
    assert not torch.equal(swapped, ordinary)
    model.train()
    with pytest.raises(RuntimeError, match="inference-only"):
        model(image)


@pytest.mark.parametrize("mode", REFERENCE_MODES)
def test_every_ablation_mode_builds_and_is_identity_at_initialisation(mode):
    kwargs = _kwargs(**NARROW)
    torch.manual_seed(0)
    base = ResidualEncoderUNet(**kwargs, deep_supervision=False)
    model = nnunet_architectures.HRCResEncUNet(
        **kwargs, deep_supervision=False, hrc_sigma0=SIGMA0, hrc_reference_mode=mode
    )
    model.load_state_dict(base.state_dict(), strict=False)
    image = torch.randn(1, 1, *PATCH)
    with torch.no_grad():
        assert torch.equal(model(image), base(image))
    assert model.architecture_metadata["reference_mode"] == mode


def test_region_mode_and_placement_subsets():
    kwargs = _kwargs(**NARROW, num_classes=2)
    model = nnunet_architectures.HRCResEncUNet(
        **kwargs,
        deep_supervision=True,
        hrc_sigma0=SIGMA0,
        hrc_output_mode="regions",
        hrc_host_channels=[0],
        hrc_lesion_channels=[1],
        hrc_levels=[2],
    )
    assert set(model.hrc) == {"2"}
    _activate(model)
    with torch.no_grad():
        outputs = model(torch.randn(1, 1, *PATCH))
    assert len(outputs) == 6 and outputs[0].shape == (1, 2, *PATCH)
    assert all(torch.isfinite(o).all() for o in outputs)


def test_statistics_grid_stays_at_level_two_without_a_level_two_block():
    """Boxes count level-2 cells whichever blocks run (the [1, 0] placement ablation)."""
    base, model = _pair(False, hrc_levels=[1, 0])
    assert model.hrc_stats_level == 2 and set(model.hrc) == {"1", "0"}
    assert model._stats_stride(1) == (2, 2, 2) and model._stats_stride(0) == (2, 4, 4)
    assert all(block.smoothing_box == (1, 5, 5) for block in model.hrc.values())
    assert model.architecture_metadata["statistics_level"] == 2
    image = torch.randn(1, 1, *PATCH)
    with torch.no_grad():
        assert torch.equal(model(image), base(image))
    model.capture_reference = True
    _activate(model)
    with torch.no_grad():
        model(image)
    # Both blocks share one reference from the (unmodified) level-2 head on G.
    assert set(model.captured_references) == {"refined"}
    assert model.captured_references["refined"].gland_mean.shape == (1, 1, 1, 1, 1)
    assert model.captured_references["refined"].local_mean.shape[2:] == (8, 32, 32)


@pytest.mark.parametrize(
    "changes",
    [
        {"hrc_sigma0": None},
        {"hrc_levels": [5]},
        {"hrc_levels": [3]},  # above the statistics level
        {"hrc_stats_level": 5},
        {"hrc_gland_prior_sd": 0.0},
        {"hrc_levels": []},
        {"hrc_reference_mode": "median"},
        {"hrc_host_channels": [2]},
        {"hrc_lesion_channels": [3]},
        {"hrc_output_mode": "sigmoid"},
        {"hrc_robust_loss": "cauchy"},
    ],
)
def test_invalid_hrc_settings_fail_closed(changes):
    kwargs = _kwargs(**NARROW)
    settings = {"hrc_sigma0": SIGMA0, **changes}
    with pytest.raises(ValueError):
        nnunet_architectures.HRCResEncUNet(**kwargs, **settings)


def test_unknown_module_attribute_still_raises():
    with pytest.raises(AttributeError):
        _ = nnunet_architectures.NotAnArchitecture  # type: ignore[attr-defined]


def test_real_nnunet_dotted_loader_builds_hrc_from_the_transferred_plan():
    pytest.importorskip("nnunetv2")
    from nnunetv2.utilities.get_network_from_plans import get_network_from_plans

    plan, changes = transfer_plan(_plan(), "hrc", {"reference_mode": "unmasked_lcn"})
    architecture = plan["configurations"]["3d_fullres"]["architecture"]
    assert architecture["network_class_name"] == HRC_CLASS
    assert changes["hrc_sigma0_normalized"] == pytest.approx(SIGMA0)
    for official in (False, True):
        model = get_network_from_plans(
            architecture["network_class_name"],
            architecture["arch_kwargs"],
            architecture["_kw_requires_import"],
            1,
            3,
            allow_init=True,
            deep_supervision=official,
        )
        assert type(model).__name__ == "HRCResEncUNet"
        assert isinstance(model, ResidualEncoderUNet)
        assert model.decoder.deep_supervision is official
        assert model.hrc_reference_mode == "unmasked_lcn"
        assert model.hrc_sigma0 == pytest.approx(SIGMA0)
        # nnU-Net's He initialisation must not touch the zero FiLM layer.
        assert all(block.film.weight.abs().sum() == 0 for block in model.hrc.values())


def test_same_seed_gives_hrc_exactly_the_resenc_l_initialisation():
    """Paired arms (for example nnFoundation vs nnFoundation+HRC) differ only by ``hrc.*``."""
    pytest.importorskip("nnunetv2")
    from nnunetv2.utilities.get_network_from_plans import get_network_from_plans

    base = _plan()
    base["configurations"]["3d_fullres"]["architecture"]["arch_kwargs"].update(NARROW)
    hrc_plan, _ = transfer_plan(base, "hrc")
    states = []
    for plan in (base, hrc_plan):
        architecture = plan["configurations"]["3d_fullres"]["architecture"]
        torch.manual_seed(11)
        model = get_network_from_plans(
            architecture["network_class_name"],
            architecture["arch_kwargs"],
            architecture["_kw_requires_import"],
            1,
            3,
            allow_init=True,
            deep_supervision=True,
        )
        states.append(model.state_dict())
    resenc, hrc = states
    assert set(resenc) < set(hrc)
    assert {key.split(".")[0] for key in set(hrc) - set(resenc)} == {"hrc"}
    assert all(torch.equal(resenc[key], hrc[key]) for key in resenc)
