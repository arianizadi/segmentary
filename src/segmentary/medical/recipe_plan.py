"""Architecture-only edits to an explicitly frozen nnU-Net ResEnc plan.

No Torch import is needed in the orchestration interpreter. Geometry, sampling,
normalization, resampling and all other plan fields remain exactly unchanged.
"""

from __future__ import annotations

import copy
from typing import Any

RESENC_CLASS = "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet"


def recipe_model_name(recipe: dict[str, Any]) -> str:
    architecture = recipe.get("architecture", "resenc")
    if architecture == "resenc":
        return f"nnunet_resenc_{recipe.get('resenc', 'L').lower()}"
    return f"nnunet_planned_{architecture}"


def transfer_plan(plan: dict[str, Any], architecture: str) -> tuple[dict[str, Any], dict]:
    """Return an independent plan and an explicit record of architecture changes."""
    if architecture not in {"resenc", "plainconv", "dynunet"}:
        raise ValueError("Unsupported recipe-transfer architecture")
    result = copy.deepcopy(plan)
    old = plan["configurations"]["3d_fullres"]["architecture"]
    if old["network_class_name"] != RESENC_CLASS:
        raise ValueError("Reference must be an official ResidualEncoderUNet plan")
    new = result["configurations"]["3d_fullres"]["architecture"]
    kwargs = new["arch_kwargs"]
    if architecture == "plainconv":
        new["network_class_name"] = "dynamic_network_architectures.architectures.unet.PlainConvUNet"
        kwargs.pop("n_blocks_per_stage")
        kwargs["n_conv_per_stage"] = [2] * kwargs["n_stages"]
        kwargs["n_conv_per_stage_decoder"] = [2] * (kwargs["n_stages"] - 1)
    elif architecture == "dynunet":
        new["network_class_name"] = "segmentary.medical.nnunet_architectures.PlannedDynUNet"
        kwargs.pop("n_blocks_per_stage")
        kwargs.pop("n_conv_per_stage_decoder")
        kwargs["conv_bias"] = False
    return result, {
        "before": copy.deepcopy(old),
        "after": copy.deepcopy(new),
        "nonarchitecture_plan_fields_unchanged": True,
        "initialization": "scratch_architecture_default",
        "capacity_matching": "shared_feature_widths_and_grids_not_equal_parameters_or_flops",
    }
