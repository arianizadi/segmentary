"""Frozen recipe transfer must not alter the development pipeline."""

import copy

import pytest

from segmentary.medical.backend import NNUNetConfig
from segmentary.medical.recipe_plan import (
    HRC_CLASS,
    HRC_DEFAULTS,
    RESENC_CLASS,
    check_hrc_dataset,
    recipe_model_name,
    transfer_plan,
    validate_hrc_options,
)


@pytest.fixture
def plan():
    return {
        "foreground_intensity_properties_per_channel": {"0": {"mean": 79.774}},
        "configurations": {
            "3d_fullres": {
                "patch_size": [56, 320, 256],
                "spacing": [2.5, 0.8125, 0.8125],
                "batch_size": 2,
                "batch_dice": False,
                "architecture": {
                    "network_class_name": RESENC_CLASS,
                    "arch_kwargs": {
                        "n_stages": 3,
                        "features_per_stage": [8, 16, 32],
                        "strides": [[1, 1, 1], [1, 2, 2], [2, 2, 2]],
                        "n_blocks_per_stage": [1, 3, 4],
                        "n_conv_per_stage_decoder": [1, 1],
                        "conv_bias": True,
                    },
                },
            },
            "2d": {"unchanged": True},
        },
    }


@pytest.mark.parametrize("architecture", ["resenc", "plainconv", "dynunet"])
def test_only_architecture_changes_and_input_is_immutable(plan, architecture):
    original = copy.deepcopy(plan)
    result, changes = transfer_plan(plan, architecture)
    assert plan == original
    before = original["configurations"]["3d_fullres"]["architecture"]
    after = result["configurations"]["3d_fullres"]["architecture"]
    assert changes["before"] == before
    assert changes["after"] == after
    assert after["arch_kwargs"]["strides"] == before["arch_kwargs"]["strides"]
    assert after["arch_kwargs"]["features_per_stage"] == before["arch_kwargs"]["features_per_stage"]
    if architecture == "resenc":
        assert before == after
    elif architecture == "plainconv":
        assert after["arch_kwargs"]["n_conv_per_stage"] == [2, 2, 2]
        assert after["arch_kwargs"]["n_conv_per_stage_decoder"] == [2, 2]
    else:
        assert after["arch_kwargs"]["conv_bias"] is False
        assert "n_blocks_per_stage" not in after["arch_kwargs"]
    result["configurations"]["3d_fullres"]["architecture"] = before
    assert result == original


def test_reference_must_be_official_resenc(plan):
    plan["configurations"]["3d_fullres"]["architecture"]["network_class_name"] = "other"
    with pytest.raises(ValueError, match="official"):
        transfer_plan(plan, "dynunet")


@pytest.mark.parametrize("architecture", ["plainconv", "dynunet"])
def test_transfer_requires_reference_and_volumetric_config(tmp_path, architecture):
    with pytest.raises(ValueError, match="reference"):
        NNUNetConfig(str(tmp_path / "run"), architecture=architecture)
    with pytest.raises(ValueError, match="3d_fullres"):
        NNUNetConfig(
            str(tmp_path / "run"),
            architecture=architecture,
            reference_workspace=str(tmp_path / "reference"),
            reference_plan_binding_sha256="a" * 64,
            configuration="2d",
        )
    config = NNUNetConfig(
        str(tmp_path / "run"),
        architecture=architecture,
        reference_workspace=str(tmp_path / "reference"),
        reference_plan_binding_sha256="a" * 64,
    )
    assert config.model == recipe_model_name({"architecture": architecture})


def test_reference_cannot_be_destination(tmp_path):
    with pytest.raises(ValueError, match="differ"):
        NNUNetConfig(str(tmp_path), reference_workspace=str(tmp_path))


def _seven_stage_plan(plan):
    kwargs = plan["configurations"]["3d_fullres"]["architecture"]["arch_kwargs"]
    kwargs.update(
        n_stages=7,
        features_per_stage=[32, 64, 128, 256, 320, 320, 320],
        strides=[[1, 1, 1], [1, 2, 2], [2, 2, 2], [2, 2, 2], [2, 2, 2], [1, 2, 2], [1, 2, 2]],
        n_blocks_per_stage=[1, 3, 4, 6, 6, 6, 6],
        n_conv_per_stage_decoder=[1] * 6,
    )
    plan["configurations"]["3d_fullres"]["normalization_schemes"] = ["CTNormalization"]
    plan["foreground_intensity_properties_per_channel"]["0"]["std"] = 71.16236877441406
    return plan


def test_hrc_keeps_every_resenc_keyword_and_adds_bound_hrc_keywords(plan):
    plan = _seven_stage_plan(plan)
    original = copy.deepcopy(plan)
    result, changes = transfer_plan(plan, "hrc", {"reference_mode": "unmasked_lcn"})
    assert plan == original
    before = original["configurations"]["3d_fullres"]["architecture"]
    after = result["configurations"]["3d_fullres"]["architecture"]
    assert after["network_class_name"] == HRC_CLASS
    added = {key: value for key, value in after["arch_kwargs"].items() if key.startswith("hrc_")}
    assert {key: after["arch_kwargs"][key] for key in before["arch_kwargs"]} == before[
        "arch_kwargs"
    ]
    assert set(after["arch_kwargs"]) == set(before["arch_kwargs"]) | set(added)
    assert added["hrc_sigma0"] == pytest.approx(5.0 / 71.16236877441406)
    assert added["hrc_reference_mode"] == "unmasked_lcn"
    assert added["hrc_levels"] == [2, 1, 0]
    assert "hrc_sigma0_hu" not in added and "hrc_gland_prior_sd_hu" not in added
    assert added["hrc_gland_prior_sd"] == pytest.approx(15.0 / 71.16236877441406)
    assert added["hrc_stats_level"] == 2
    assert changes["hrc_options"] == {**HRC_DEFAULTS, "reference_mode": "unmasked_lcn"}
    result["configurations"]["3d_fullres"]["architecture"] = before
    assert result == original
    assert recipe_model_name({"architecture": "hrc"}) == "nnunet_planned_hrc"


@pytest.mark.parametrize(
    "options, message",
    [
        ({"reference_mode": "median"}, "Invalid"),
        ({"temperature": 1}, "Unknown"),
        ({"outer_box": [9, 16, 17]}, "Invalid"),
        ({"inner_box": [11, 7, 7]}, "inner box"),
        ({"host_channels": [2]}, "differ"),
        ({"levels": [5]}, "Invalid"),  # above the statistics level
        ({"levels": [3], "stats_level": 2}, "Invalid"),
        ({"levels": [5], "stats_level": 5}, "next-coarser"),
        ({"gland_prior_sd_hu": 0}, "Invalid"),
        ({"host_channels": [0]}, "foreground"),
        ({"output_mode": "regions"}, "declare host_channels"),
        (
            {"output_mode": "regions", "host_channels": [0, 1], "lesion_channels": [2]},
            "exactly one",
        ),
        (
            {"output_mode": "regions", "host_channels": [1, 3], "lesion_channels": [2]},
            "exactly one",
        ),
        ({"sigma0_hu": 0}, "Invalid"),
        ({"irls_iterations": True}, "Invalid"),
    ],
)
def test_invalid_hrc_options_fail_closed(plan, options, message):
    with pytest.raises(ValueError, match=message):
        transfer_plan(_seven_stage_plan(plan), "hrc", options)


def test_hrc_sigma0_requires_ct_normalisation_and_a_foreground_std(plan):
    plan = _seven_stage_plan(plan)
    plan["configurations"]["3d_fullres"]["normalization_schemes"] = ["ZScoreNormalization"]
    with pytest.raises(ValueError, match="CTNormalization"):
        transfer_plan(plan, "hrc")
    plan = _seven_stage_plan(plan)
    plan["configurations"]["3d_fullres"]["normalization_schemes"] = ["CTNormalization"]
    del plan["foreground_intensity_properties_per_channel"]["0"]["std"]
    with pytest.raises(ValueError, match="std"):
        transfer_plan(plan, "hrc")
    with pytest.raises(ValueError, match="only defined for hrc"):
        transfer_plan(plan, "dynunet", {"reference_mode": "robust"})


TASK07 = {"labels": {"background": 0, "pancreas": 1, "mass": 2}}
# nnU-Net's KiTS23 region layout: heads are kidney+masses, masses, tumor.
KITS = {
    "labels": {"background": 0, "kidney": [1, 2, 3], "masses": [2, 3], "tumor": 2},
    "regions_class_order": [1, 3, 2],
}


def test_hrc_outputs_must_mean_host_and_lesion_for_the_dataset():
    softmax = validate_hrc_options({})
    assert check_hrc_dataset(softmax, TASK07) == {
        "output_mode": "softmax",
        "host": ["pancreas"],
        "lesion": ["mass"],
    }
    with pytest.raises(ValueError, match="region dataset"):
        check_hrc_dataset(softmax, KITS)
    with pytest.raises(ValueError, match="exceed"):
        check_hrc_dataset(validate_hrc_options({"lesion_channels": [3]}), TASK07)
    regions = validate_hrc_options(
        {"output_mode": "regions", "host_channels": [1], "lesion_channels": [2]}
    )
    assert check_hrc_dataset(regions, KITS) == {
        "output_mode": "regions",
        "host": ["masses"],
        "lesion": ["tumor"],
    }
    with pytest.raises(ValueError, match="regions_class_order"):
        check_hrc_dataset(regions, TASK07)
    # The host region must strictly contain the lesion region.
    inverted = validate_hrc_options(
        {"output_mode": "regions", "host_channels": [2], "lesion_channels": [1]}
    )
    with pytest.raises(ValueError, match="strictly contain"):
        check_hrc_dataset(inverted, KITS)


def test_validated_options_are_complete_and_independent():
    resolved = validate_hrc_options({"levels": [2]})
    assert resolved == {**HRC_DEFAULTS, "levels": [2]}
    resolved["outer_box"].append(1)
    assert HRC_DEFAULTS["outer_box"] == [9, 17, 17]
