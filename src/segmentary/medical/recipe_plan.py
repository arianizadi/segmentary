"""Architecture-only edits to an explicitly frozen nnU-Net ResEnc plan.

No Torch import is needed in the orchestration interpreter. Geometry, sampling,
normalization, resampling and all other plan fields remain exactly unchanged.
"""

from __future__ import annotations

import copy
from typing import Any

RESENC_CLASS = "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet"
HRC_CLASS = "segmentary.medical.nnunet_architectures.HRCResEncUNet"
ARCHITECTURES = ("resenc", "plainconv", "dynunet", "hrc")
# Option -> default. Each becomes the ``hrc_<option>`` network keyword, except
# the ``*_hu`` options, which are converted with the plan's foreground intensity
# std (``sigma0_hu`` -> ``hrc_sigma0``, ``gland_prior_sd_hu`` -> ``hrc_gland_prior_sd``).
HRC_DEFAULTS: dict[str, Any] = {
    "levels": [2, 1, 0],
    # Box sizes count cells of this decoder level, whichever blocks are enabled.
    "stats_level": 2,
    "reference_mode": "robust",
    "output_mode": "softmax",
    "host_channels": [1],
    "lesion_channels": [2],
    "image_channel": 0,
    "feature_channels": 16,
    "hidden_channels": 32,
    "outer_box": [9, 17, 17],
    "inner_box": [3, 7, 7],
    "smoothing_box": [1, 5, 5],
    "stats_smoothing_box": [1, 3, 3],
    "shrinkage_cells": 50.0,
    "gland_prior_cells": 10.0,
    "gland_prior_sd_hu": 15.0,
    "robust_loss": "huber",
    "robust_k": 1.5,
    "irls_iterations": 3,
    "sigma0_hu": 5.0,
}
_REFERENCE_MODES = (
    "robust",
    "masked_mean",
    "gland_only",
    "local_only",
    "unmasked_lcn",
    "features_only",
    "hu_only",
    "none",
)


def _integers(value: Any, *, length: int | None = None, odd: bool = False) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and (length is None or len(value) == length)
        and all(type(item) is int and item >= 0 for item in value)
        and (not odd or all(item % 2 == 1 for item in value))
    )


def _number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value >= 0


def validate_hrc_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """Return the complete, explicit HRC option set; unknown keys fail closed."""
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("hrc_options must be a mapping")
    unknown = set(options) - set(HRC_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown HRC options: {sorted(unknown)}")
    resolved = copy.deepcopy(HRC_DEFAULTS) | copy.deepcopy(options)
    checks = {
        "levels": _integers(resolved["levels"])
        and len(set(resolved["levels"])) == len(resolved["levels"])
        and type(resolved["stats_level"]) is int
        and max(resolved["levels"]) <= resolved["stats_level"],
        "stats_level": type(resolved["stats_level"]) is int and resolved["stats_level"] >= 0,
        "reference_mode": resolved["reference_mode"] in _REFERENCE_MODES,
        "output_mode": resolved["output_mode"] in {"softmax", "regions"},
        "host_channels": _integers(resolved["host_channels"]),
        "lesion_channels": _integers(resolved["lesion_channels"]),
        "image_channel": type(resolved["image_channel"]) is int and resolved["image_channel"] >= 0,
        "feature_channels": type(resolved["feature_channels"]) is int
        and resolved["feature_channels"] > 0,
        "hidden_channels": type(resolved["hidden_channels"]) is int
        and resolved["hidden_channels"] > 0,
        "outer_box": _integers(resolved["outer_box"], length=3, odd=True),
        "inner_box": _integers(resolved["inner_box"], length=3, odd=True),
        "smoothing_box": _integers(resolved["smoothing_box"], length=3, odd=True),
        "stats_smoothing_box": _integers(resolved["stats_smoothing_box"], length=3, odd=True),
        "shrinkage_cells": _number(resolved["shrinkage_cells"]),
        "gland_prior_cells": _number(resolved["gland_prior_cells"]),
        "gland_prior_sd_hu": _number(resolved["gland_prior_sd_hu"])
        and resolved["gland_prior_sd_hu"] > 0,
        "robust_loss": resolved["robust_loss"] in {"huber", "tukey"},
        "robust_k": _number(resolved["robust_k"]) and resolved["robust_k"] > 0,
        "irls_iterations": type(resolved["irls_iterations"]) is int
        and resolved["irls_iterations"] >= 0,
        "sigma0_hu": _number(resolved["sigma0_hu"]) and resolved["sigma0_hu"] > 0,
    }
    invalid = sorted(name for name, valid in checks.items() if not valid)
    if invalid:
        raise ValueError(f"Invalid HRC options: {invalid}")
    if set(resolved["host_channels"]) & set(resolved["lesion_channels"]):
        raise ValueError("HRC host and lesion channels must differ")
    if resolved["output_mode"] == "softmax" and 0 in (
        resolved["host_channels"] + resolved["lesion_channels"]
    ):
        # Softmax channel 0 is background; region head 0 is a foreground region.
        raise ValueError("Softmax HRC host and lesion channels must be foreground, not channel 0")
    if resolved["output_mode"] == "regions":
        # Softmax defaults mean something else for region heads; never assume them.
        if "host_channels" not in options or "lesion_channels" not in options:
            raise ValueError("Region-mode HRC must declare host_channels and lesion_channels")
        if len(resolved["host_channels"]) != 1 or len(resolved["lesion_channels"]) != 1:
            raise ValueError("Region-mode HRC needs exactly one host and one lesion region")
    if any(i > o for i, o in zip(resolved["inner_box"], resolved["outer_box"], strict=True)):
        raise ValueError("The HRC inner box must fit inside the outer box")
    return resolved


def _label_set(value: Any) -> frozenset[int]:
    values = value if isinstance(value, (list, tuple)) else [value]
    if not values or any(type(item) is not int or item < 0 for item in values):
        raise ValueError("dataset.json labels must be non-negative integers or lists of them")
    return frozenset(values)


def check_hrc_dataset(options: dict[str, Any], dataset_json: dict[str, Any]) -> dict[str, Any]:
    """Check that HRC's output mode and channels mean host and lesion for this dataset.

    Softmax mode needs a label (not region) dataset whose channel indices are
    label values. Region mode needs nnU-Net regions (``regions_class_order``);
    output channel ``i`` is the ``i``-th foreground region in ``labels`` order,
    and the host region must strictly contain the lesion region, as
    ``p_host = sigmoid(R) * (1 - sigmoid(M))`` assumes.
    """
    labels = dataset_json.get("labels")
    if not isinstance(labels, dict) or not labels:
        raise ValueError("dataset.json has no labels")
    # nnU-Net never predicts its optional ignore label.
    labels = {name: value for name, value in labels.items() if name != "ignore"}
    regions = "regions_class_order" in dataset_json
    host, lesion = options["host_channels"], options["lesion_channels"]
    if options["output_mode"] == "softmax":
        if regions:
            raise ValueError("Softmax-mode HRC on a region dataset; use output_mode=regions")
        values = list(labels.values())
        if any(type(value) is not int for value in values) or sorted(values) != list(
            range(len(values))
        ):
            raise ValueError("Softmax-mode HRC needs consecutive integer labels")
        if max(host + lesion) >= len(values):
            raise ValueError("HRC channels exceed the dataset's softmax outputs")
        names = {value: name for name, value in labels.items()}
        return {
            "output_mode": "softmax",
            "host": [names[c] for c in host],
            "lesion": [names[c] for c in lesion],
        }
    if not regions:
        raise ValueError("Region-mode HRC needs a dataset with regions_class_order")
    foreground = [
        (name, _label_set(value))
        for name, value in labels.items()
        if _label_set(value) != frozenset({0})
    ]
    if max(host + lesion) >= len(foreground):
        raise ValueError("HRC channels exceed the dataset's region outputs")
    host_name, host_labels = foreground[host[0]]
    lesion_name, lesion_labels = foreground[lesion[0]]
    if not lesion_labels < host_labels:
        raise ValueError(
            f"Host region {host_name!r} must strictly contain lesion region {lesion_name!r}"
        )
    return {"output_mode": "regions", "host": [host_name], "lesion": [lesion_name]}


def recipe_model_name(recipe: dict[str, Any]) -> str:
    architecture = recipe.get("architecture", "resenc")
    if architecture == "resenc":
        return f"nnunet_resenc_{recipe.get('resenc', 'L').lower()}"
    return f"nnunet_planned_{architecture}"


def _hrc_kwargs(plan: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    selected = plan["configurations"]["3d_fullres"]
    channel = options["image_channel"]
    schemes = selected.get("normalization_schemes", [])
    if channel >= len(schemes) or schemes[channel] != "CTNormalization":
        raise ValueError("HRC sigma0 conversion requires CTNormalization on its image channel")
    try:
        std = plan["foreground_intensity_properties_per_channel"][str(channel)]["std"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Plan has no foreground intensity std for the HRC image channel") from exc
    if isinstance(std, bool) or not isinstance(std, (int, float)) or not std > 0:
        raise ValueError("Plan foreground intensity std must be positive")
    converted = {"sigma0_hu", "gland_prior_sd_hu"}
    kwargs = {f"hrc_{key}": value for key, value in options.items() if key not in converted}
    kwargs["hrc_sigma0"] = options["sigma0_hu"] / std
    kwargs["hrc_gland_prior_sd"] = options["gland_prior_sd_hu"] / std
    return kwargs


def transfer_plan(
    plan: dict[str, Any], architecture: str, options: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict]:
    """Return an independent plan and an explicit record of architecture changes."""
    if architecture not in ARCHITECTURES:
        raise ValueError("Unsupported recipe-transfer architecture")
    if options is not None and architecture != "hrc":
        raise ValueError("Architecture options are only defined for hrc")
    result = copy.deepcopy(plan)
    old = plan["configurations"]["3d_fullres"]["architecture"]
    if old["network_class_name"] != RESENC_CLASS:
        raise ValueError("Reference must be an official ResidualEncoderUNet plan")
    new = result["configurations"]["3d_fullres"]["architecture"]
    kwargs = new["arch_kwargs"]
    record: dict[str, Any] = {}
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
    elif architecture == "hrc":
        resolved = validate_hrc_options(options)
        if any(key.startswith("hrc_") for key in kwargs):
            raise ValueError("Reference plan already contains HRC keywords")
        if resolved["stats_level"] + 1 > kwargs["n_stages"] - 2:
            raise ValueError("The HRC statistics level needs a next-coarser decoder head")
        # Every ResEnc keyword is kept; only the class and hrc_* keywords change.
        new["network_class_name"] = HRC_CLASS
        kwargs.update(_hrc_kwargs(plan, resolved))
        record = {"hrc_options": resolved, "hrc_sigma0_normalized": kwargs["hrc_sigma0"]}
    return result, {
        "before": copy.deepcopy(old),
        "after": copy.deepcopy(new),
        "nonarchitecture_plan_fields_unchanged": True,
        # Construction only: the backend binds any initial checkpoint separately
        # (binding.json ``initialization`` and ``initial_checkpoint``).
        "network_construction": "architecture_default_initialization",
        "capacity_matching": "shared_feature_widths_and_grids_not_equal_parameters_or_flops",
        **record,
    }
