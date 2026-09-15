"""Frozen recipe transfer must not alter the development pipeline."""

import copy

import pytest

from segmentary.medical.backend import NNUNetConfig
from segmentary.medical.recipe_plan import RESENC_CLASS, recipe_model_name, transfer_plan


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
