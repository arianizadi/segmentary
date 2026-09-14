"""Immutable declarations for the bounded DynUNet budget/resolution follow-up."""

from __future__ import annotations

from typing import Any

from .recipe_ablation import recipe_fingerprint

PRESET = "task07_dynunet_followup_v1"
DEEP_PRESET = "task07_dynunet_deep_supervision_v1"
DEEP_ARMS: dict[str, dict[str, Any]] = {
    "control10k": {
        "description": "Fresh 10,000-update DynUNet without auxiliary decoder losses",
        "changes": {},
        "group": "dynunet_deep_supervision_seed0_control_10000_steps",
    },
    "deep10k": {
        "description": "Matched 10,000-update DynUNet with two native decoder auxiliary losses",
        "changes": {
            "model_options": {
                "filters": [32, 64, 128, 256, 320],
                "res_block": False,
                "deep_supervision": True,
            }
        },
        "group": "dynunet_deep_supervision_seed0_auxiliary_10000_steps",
    },
}
ARMS: dict[str, dict[str, Any]] = {
    "control10k": {
        "description": "Fresh original control with a 10,000-update polynomial schedule",
        "changes": {},
        "group": "dynunet_followup_seed0_control_10000_steps_coarse",
    },
    "long30k": {
        "description": "Fresh original control with a 30,000-update polynomial schedule",
        "changes": {"epochs": 300},
        "group": "dynunet_followup_seed0_budget_30000_steps_coarse",
    },
    "fine10k": {
        "description": "Finer in-plane sampling with matched nominal physical crop extent",
        "changes": {"spacing_mm": [1.0, 1.0, 2.5], "patch_size": [96, 144, 144]},
        "group": "dynunet_followup_seed0_resolution_10000_steps_fine",
    },
}


RECIPE_PRESET = "task07_recipe_explorations_v1"
CASCADE_PRESET = "task07_predicted_roi_cascade_v1"
PRESETS = {PRESET, DEEP_PRESET, RECIPE_PRESET, CASCADE_PRESET}
RECIPE_ARMS = {
    **DEEP_ARMS,
    "focal05": {
        "description": "Foreground Dice + 0.5 times multiclass focal, gamma 2",
        "changes": {"loss": "dice_focal", "focal_coefficient": 0.5},
        "group": "recipe_focal05",
    },
    "focal10": {
        "description": "Foreground Dice + 1.0 times multiclass focal, gamma 2",
        "changes": {"loss": "dice_focal"},
        "group": "recipe_focal10",
    },
    "window": {
        "description": "Wider fixed HU window [-175,250], scaled to [0,1]",
        "changes": {"hu_window": [-175.0, 250.0]},
        "group": "recipe_hu_window",
    },
    "minmax": {
        "description": "Full-volume image-only raw min/max to [0,1], without HU clipping",
        "changes": {"normalization": "volume_minmax"},
        "group": "recipe_volume_minmax",
    },
    "isotropic": {
        "description": "Isotropic 1.5 mm grid, matched 144x144x240 mm nominal crop",
        "changes": {"spacing_mm": [1.5, 1.5, 1.5], "patch_size": [160, 96, 96]},
        "group": "recipe_isotropic",
    },
    "swin24": {
        "description": "Scratch shifted-window Swin UNETR, feature width 24",
        "changes": {"model": "swin_unetr", "model_options": {"feature_size": 24}},
        "group": "recipe_swin24",
    },
    "swin48": {
        "description": "Scratch shifted-window Swin UNETR, feature width 48",
        "changes": {
            "model": "swin_unetr",
            "model_options": {"feature_size": 48, "use_checkpoint": True},
        },
        "group": "recipe_swin48",
    },
}


def arm_id(name: str, arm: dict) -> str:
    return f"{arm['changes'].get('model', 'dynunet')}-{name}-seed0"


def arms_for(preset: str, roi_manifests: dict | None = None) -> dict:
    if preset == PRESET:
        return ARMS
    if preset == DEEP_PRESET:
        return DEEP_ARMS
    if preset == RECIPE_PRESET:
        return RECIPE_ARMS
    if (
        preset != CASCADE_PRESET
        or not isinstance(roi_manifests, dict)
        or set(roi_manifests) != {"20", "40"}
    ):
        raise ValueError("Cascade requires exactly 20 and 40 mm frozen ROI manifests")
    from .torch_config import TorchConfig
    from .torch_roi import roi_document

    arms = {"control10k": DEEP_ARMS["control10k"]}
    for margin in ("20", "40"):
        roi = roi_manifests[margin]
        config = TorchConfig(
            workspace="/tmp/roi-schema", roi_manifest=roi["path"], roi_manifest_sha256=roi["sha256"]
        )
        document = roi_document(config)
        if document is None or document.get("margin_mm") != int(margin):
            raise ValueError("ROI manifest differs from the declared margin")
        arms[f"roi{margin}"] = {
            "description": f"Predicted pancreas bounding box with {margin} mm margin; full-native evaluation",
            "changes": {
                "roi_manifest": config.roi_manifest,
                "roi_manifest_sha256": config.roi_manifest_sha256,
            },
            "group": f"recipe_cascade_roi{margin}",
        }
    return arms


def validate_declared_followup(spec: dict, recipes: dict[str, dict]) -> None:
    """Require exact declared changes; do not relax ordinary recipe ablations.

    Groups are intentionally separate: different training budgets or voxel grids
    cannot be promoted into one ordinary equal-recipe architecture ranking.
    Planned contrasts belong in the explicit follow-up analysis instead.
    """
    protocol = spec.get("protocol", {})
    declaration = protocol.get("followup_experiments")
    if declaration is None:
        if protocol.get("preset") in PRESETS:
            raise ValueError("Follow-up campaign requires its frozen declaration")
        return
    if (
        protocol.get("preset") not in PRESETS
        or declaration.get("schema_version") != 1
        or declaration.get("model") != "dynunet"
        or declaration.get("seed") != 0
    ):
        raise ValueError("Unsupported follow-up declaration")
    selected_arms = arms_for(protocol["preset"], declaration.get("roi_manifests"))
    identifiers = {arm_id(name, arm) for name, arm in selected_arms.items()}
    declarations = declaration.get("arms", {})
    if set(recipes) != identifiers or set(declarations) != identifiers:
        raise ValueError("Follow-up must contain exactly its planned run IDs")
    runs = {run["id"]: run for run in spec["runs"]}
    if set(runs) != identifiers or len(runs) != len(spec["runs"]):
        raise ValueError("Follow-up run declarations do not match its planned arms")
    control_id = "dynunet-control10k-seed0"
    control = recipes[control_id]
    if declaration.get("control_run_id") != control_id or declaration.get(
        "control_scientific_recipe_sha256"
    ) != recipe_fingerprint(control):
        raise ValueError("Follow-up control differs from its frozen fingerprint")
    if (
        control.get("model") != "dynunet"
        or control.get("initialization") != "scratch"
        or control.get("seed") != 0
        or control.get("epochs") != 100
        or control.get("steps_per_epoch") != 100
        or control.get("batch_size") != 8
        or list(control.get("patch_size", [])) != [96, 96, 96]
        or list(control.get("spacing_mm", [])) != [1.5, 1.5, 2.5]
    ):
        raise ValueError("Follow-up control no longer has the declared base geometry or budget")
    if protocol["preset"] != PRESET:
        from .models_3d import _options

        if _options("dynunet", control.get("model_options", {})) != _options("dynunet", {}):
            raise ValueError("Follow-up control must retain the original default DynUNet")
    for name, expected_arm in selected_arms.items():
        identifier = arm_id(name, expected_arm)
        config, arm = recipes[identifier], declarations[identifier]
        expected = recipe_fingerprint({**control, **expected_arm["changes"]})
        if (
            arm.get("arm") != name
            or arm.get("control_run_id") != control_id
            or arm.get("changes_from_control") != expected_arm["changes"]
            or runs[identifier].get("comparison_group") != expected_arm["group"]
            or arm.get("scientific_recipe_sha256") != expected
            or recipe_fingerprint(config) != expected
        ):
            raise ValueError("Follow-up recipe or comparison group differs from its declaration")
