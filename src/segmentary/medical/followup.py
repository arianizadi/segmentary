"""Immutable declarations for the bounded DynUNet budget/resolution follow-up."""

from __future__ import annotations

from typing import Any

from .recipe_ablation import recipe_fingerprint

PRESET = "task07_dynunet_followup_v1"
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


def validate_declared_followup(spec: dict, recipes: dict[str, dict]) -> None:
    """Require exact declared changes; do not relax ordinary recipe ablations.

    Groups are intentionally separate: different training budgets or voxel grids
    cannot be promoted into one ordinary equal-recipe architecture ranking.
    Planned contrasts belong in the explicit follow-up analysis instead.
    """
    protocol = spec.get("protocol", {})
    declaration = protocol.get("followup_experiments")
    if declaration is None:
        if protocol.get("preset") == PRESET:
            raise ValueError("Follow-up campaign requires its frozen declaration")
        return
    if (
        protocol.get("preset") != PRESET
        or declaration.get("schema_version") != 1
        or declaration.get("model") != "dynunet"
        or declaration.get("seed") != 0
    ):
        raise ValueError("Unsupported follow-up declaration")
    identifiers = {f"dynunet-{arm}-seed0" for arm in ARMS}
    declarations = declaration.get("arms", {})
    if set(recipes) != identifiers or set(declarations) != identifiers:
        raise ValueError("Follow-up must contain exactly its three planned run IDs")
    runs = {run["id"]: run for run in spec["runs"]}
    if set(runs) != identifiers or len(runs) != len(spec["runs"]):
        raise ValueError("Follow-up run declarations do not match its three arms")
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
    for name, expected_arm in ARMS.items():
        identifier = f"dynunet-{name}-seed0"
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
