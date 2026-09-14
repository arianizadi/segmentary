"""Portable fingerprints for declared recipe experiments, without importing Torch."""

from __future__ import annotations

import hashlib
import json
from typing import Any

# These fields locate/schedule the experiment or control telemetry/CPU overlap.
# Every remaining field participates, including new future scientific options.
OPERATIONAL_FIELDS = frozenset(
    {
        "workspace",
        "backend_python",
        "gpu",
        "cache_root",
        "workers",
        "prefetch_batches",
        "progress_interval",
    }
)
ABLATION_FIELDS = frozenset(
    {
        "foreground_probability",
        "center_probabilities",
        "class_center_weights",
        "rotation_probability",
        "rotation_degrees",
        "rotation_padding_value",
        "intensity_scale_probability",
        "intensity_scale_range",
    }
)


def scientific_recipe(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key not in OPERATIONAL_FIELDS}


def recipe_fingerprint(config: dict[str, Any]) -> str:
    encoded = json.dumps(
        scientific_recipe(config), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_declared_recipes(spec: dict, recipes: dict[str, dict]) -> None:
    """Reject undeclared recipe changes before allocating or reporting an ablation.

    Ordinary architecture campaigns retain their existing comparison rules.
    Ablation controls and all allowed ingredient deltas must be explicit.
    """
    protocol = spec.get("protocol", {})
    declaration = protocol.get("recipe_ablation")
    if declaration is None:
        if protocol.get("preset") == "task07_dynunet_recipe_ablation_v1":
            raise ValueError("Recipe ablation requires its frozen declaration")
        return
    if declaration.get("schema_version") != 1 or declaration.get("model") != "dynunet":
        raise ValueError("Unsupported recipe ablation declaration")
    arms = declaration.get("arms", {})
    if set(arms) != set(recipes):
        raise ValueError("Recipe ablation arms differ from planned run IDs")
    for identifier, config in recipes.items():
        arm = arms[identifier]
        control_id = arm.get("control_run_id", declaration.get("control_run_id"))
        if control_id not in recipes:
            raise ValueError("Recipe ablation control is missing")
        control = recipes[control_id]
        changes = arm.get("changes_from_control")
        if not isinstance(changes, dict) or set(changes) - ABLATION_FIELDS:
            raise ValueError("Recipe ablation contains undeclared scientific fields")
        if arms[control_id].get("changes_from_control") != {}:
            raise ValueError("Recipe ablation control must have no ingredient changes")
        expected = recipe_fingerprint(config)
        if (
            config.get("model") != "dynunet"
            or config.get("initialization") != "scratch"
            or arm.get("scientific_recipe_sha256") != expected
            or recipe_fingerprint({**control, **changes}) != expected
        ):
            raise ValueError("Recipe ablation differs from its declared control or fingerprint")
