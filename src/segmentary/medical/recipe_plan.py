"""Architecture-only edits to an explicitly frozen nnU-Net ResEnc plan.

No Torch import is needed in the orchestration interpreter. Geometry, sampling,
normalization, resampling and all other plan fields remain exactly unchanged.
"""

from __future__ import annotations

import copy
import math
from typing import Any

RESENC_CLASS = "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet"
HRC_CLASS = "segmentary.medical.nnunet_architectures.HRCResEncUNet"
ARCHITECTURES = ("resenc", "plainconv", "dynunet", "hrc", "starc")
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
    if options is not None and architecture not in {"hrc", "starc"}:
        raise ValueError("Architecture options are only defined for hrc and starc")
    if architecture == "starc":
        return transfer_starc_plan(plan, options)
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


# STAR-C (star-convex lesion completion; see ``star_completion``). Torch-free so
# the orchestration interpreter can validate recipes and transfer plans.
STARC_CLASS = "segmentary.medical.nnunet_architectures.StarCResEncUNet"
# Offline ray targets (``scripts/precompute_star_targets.py``): schema and manifest name.
STARC_TARGET_SCHEMA = "segmentary-starc-targets-v1"
STARC_TARGET_MANIFEST = "manifest.json"
# How targets are computed. precompute_star_targets.py writes exactly these
# manifest fields and every target check requires them, so targets computed
# with other march settings are refused even though the code hash is only recorded.
STARC_TARGET_METHOD: dict[str, Any] = {
    "connectivity": 26,
    "directions": "fibonacci_sphere_zyx",
    "centre": "maximum_position of the zero-padded mm EDT",
    "march": {
        "lookup": "nearest voxel",
        "step_fraction_of_min_spacing": 0.25,
        "bisections": 6,
        "max_mm": "component bbox diagonal + max spacing",
    },
    "crop_border_voxels": 2,
}
FUSION_MODES = ("gated", "aux_only")
# Network options become ``starc_<option>`` plan keywords; training options are
# trainer attributes. Both are bound with every default made explicit.
STARC_NETWORK_DEFAULTS: dict[str, Any] = {
    "rays": 96,
    "level": 2,
    "lesion_labels": [2],
    "fusion_channels": [1, 2],
    "fusion": "gated",
    "max_instances": 8,
    "centre_threshold": 0.15,
    "box_margin_mm": 5.0,
    "min_ray_mm": 0.5,
    "max_ray_mm": 90.0,
    "tau_init_mm": 1.5,
    "tau_min_mm": 0.5,
    "tau_max_mm": 5.0,
    "gate_bias": -2.0,
    "prior_scale": 6.0,
    "centre_hidden": 64,
    "ray_hidden": 128,
    "gate_hidden": 16,
    "ray_init_mm": 10.0,
    "centre_prior": 0.01,
    "lut_shape": [256, 512],
}
STARC_TRAINING_DEFAULTS: dict[str, Any] = {
    "centre_weight": 1.0,
    "ray_weight": 0.5,
    "teacher_probability": 0.5,
    "teacher_jitter_mm": 2.0,
    "ray_samples": 64,
    "max_gt_instances": 16,
    "core_fraction": 0.3,
    "sigma_min_mm": 3.0,
    "sigma_fraction": 0.25,
    "freeze_backbone": False,
}
STARC_DEFAULTS = {**STARC_NETWORK_DEFAULTS, **STARC_TRAINING_DEFAULTS}


def starc_target_method_problems(manifest: dict[str, Any]) -> list[str]:
    """Target-method fields of a target manifest that differ from ``STARC_TARGET_METHOD``."""
    return [key for key, value in STARC_TARGET_METHOD.items() if manifest.get(key) != value]


def _starc_positive(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value > 0


def _starc_int_list(value: Any, *, minimum: int = 0) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(type(item) is int and item >= minimum for item in value)
        and len(set(value)) == len(value)
    )


def validate_starc_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """Return the complete, explicit STAR-C option set; unknown keys fail closed."""
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("starc_options must be a mapping")
    unknown = set(options) - set(STARC_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown STAR-C options: {sorted(unknown)}")
    resolved = copy.deepcopy(STARC_DEFAULTS) | copy.deepcopy(options)
    invalid = []
    for key in ("rays", "max_instances", "centre_hidden", "ray_hidden", "gate_hidden"):
        if type(resolved[key]) is not int or resolved[key] < 1:
            invalid.append(key)
    for key in ("ray_samples", "max_gt_instances", "level"):
        if type(resolved[key]) is not int or resolved[key] < 0:
            invalid.append(key)
    if type(resolved["rays"]) is int and resolved["rays"] < 12:
        invalid.append("rays")
    for key in (
        "box_margin_mm",
        "min_ray_mm",
        "max_ray_mm",
        "tau_init_mm",
        "tau_min_mm",
        "tau_max_mm",
        "prior_scale",
        "ray_init_mm",
        "sigma_min_mm",
        "teacher_jitter_mm",
    ):
        if not _starc_positive(resolved[key]) and not (
            key == "teacher_jitter_mm" and resolved[key] == 0
        ):
            invalid.append(key)
    for key in ("centre_threshold", "centre_prior", "teacher_probability", "core_fraction"):
        value = resolved[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            invalid.append(key)
    if "centre_prior" not in invalid and not 0 < resolved["centre_prior"] < 1:
        invalid.append("centre_prior")
    for key in ("gate_bias", "centre_weight", "ray_weight", "sigma_fraction"):
        value = resolved[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            invalid.append(key)
    for key in ("centre_weight", "ray_weight", "sigma_fraction"):
        if key not in invalid and resolved[key] < 0:
            invalid.append(key)
    if not _starc_int_list(resolved["lesion_labels"], minimum=1):
        invalid.append("lesion_labels")
    if not _starc_int_list(resolved["fusion_channels"]):
        invalid.append("fusion_channels")
    if resolved["fusion"] not in FUSION_MODES:
        invalid.append("fusion")
    if not _starc_int_list(resolved["lut_shape"], minimum=8) or len(resolved["lut_shape"]) != 2:
        invalid.append("lut_shape")
    if type(resolved["freeze_backbone"]) is not bool:
        invalid.append("freeze_backbone")
    if invalid:
        raise ValueError(f"Invalid STAR-C options: {sorted(set(invalid))}")
    if not resolved["tau_min_mm"] < resolved["tau_init_mm"] < resolved["tau_max_mm"]:
        raise ValueError("STAR-C needs tau_min_mm < tau_init_mm < tau_max_mm")
    if not resolved["min_ray_mm"] < resolved["ray_init_mm"] < resolved["max_ray_mm"]:
        raise ValueError("STAR-C needs min_ray_mm < ray_init_mm < max_ray_mm")
    return resolved


def network_options(options: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(options[key]) for key in STARC_NETWORK_DEFAULTS}


def training_options(options: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(options[key]) for key in STARC_TRAINING_DEFAULTS}


def check_starc_dataset(options: dict[str, Any], dataset_json: dict[str, Any]) -> dict[str, Any]:
    """Check lesion labels and fusion channels against ``dataset.json``; return their names.

    ``lesion_labels`` are voxel labels of the segmentation, which nnU-Net keeps
    in label form on disk in both modes. A region dataset's voxel labels are the
    union of its region label sets (``_label_set``); a lesion label is named by
    the region that is exactly that label, if any. Fusion channels are softmax
    label values or, for regions, region heads in ``labels`` order.
    """
    labels = dataset_json.get("labels")
    if not isinstance(labels, dict) or not labels:
        raise ValueError("dataset.json has no label mapping")
    labels = {name: value for name, value in labels.items() if name != "ignore"}
    regions = "regions_class_order" in dataset_json
    sets = {name: _label_set(value) for name, value in labels.items()}
    if regions:
        voxel_labels = set().union(*sets.values())
        heads = [name for name in labels if sets[name] != frozenset({0})]
    else:
        values = list(labels.values())
        if any(type(value) is not int for value in values) or sorted(values) != list(
            range(len(values))
        ):
            raise ValueError("Softmax STAR-C needs consecutive integer labels")
        voxel_labels = set(values)
        heads = sorted(labels, key=lambda name: labels[name])
        if 0 in options["fusion_channels"]:
            raise ValueError("Softmax STAR-C fusion channels exclude background (channel 0)")
    if any(label not in voxel_labels or label == 0 for label in options["lesion_labels"]):
        raise ValueError("STAR-C lesion_labels must be foreground voxel labels of this dataset")
    if max(options["fusion_channels"]) >= len(heads):
        raise ValueError("STAR-C fusion channels exceed the dataset's outputs")
    exact = {next(iter(found)): name for name, found in sets.items() if len(found) == 1}
    return {
        "lesion_labels": [exact.get(label, f"label {label}") for label in options["lesion_labels"]],
        "fusion_channels": [heads[channel] for channel in options["fusion_channels"]],
    }


def starc_plan_kwargs(plan: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    """Network keywords for a frozen 3d_fullres ResEnc plan (spacing comes from the plan)."""
    selected = plan["configurations"]["3d_fullres"]
    spacing = selected.get("spacing")
    if (
        not isinstance(spacing, list)
        or len(spacing) != 3
        or not all(_starc_positive(value) for value in spacing)
    ):
        raise ValueError("STAR-C needs the plan's positive 3D 3d_fullres spacing")
    n_stages = selected["architecture"]["arch_kwargs"]["n_stages"]
    if not 0 <= options["level"] <= n_stages - 2:
        raise ValueError("STAR-C level must be a decoder level of this plan")
    kwargs = {f"starc_{key}": value for key, value in network_options(options).items()}
    kwargs["starc_spacing"] = [float(value) for value in spacing]
    return kwargs


def transfer_starc_plan(
    plan: dict[str, Any], options: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The ``recipe_plan.transfer_plan`` branch for ``architecture: starc``."""
    resolved = validate_starc_options(options)
    result = copy.deepcopy(plan)
    old = plan["configurations"]["3d_fullres"]["architecture"]
    if old["network_class_name"] != RESENC_CLASS:
        raise ValueError("Reference must be an official ResidualEncoderUNet plan")
    new = result["configurations"]["3d_fullres"]["architecture"]
    if any(key.startswith("starc_") for key in new["arch_kwargs"]):
        raise ValueError("Reference plan already contains STAR-C keywords")
    new["network_class_name"] = STARC_CLASS
    new["arch_kwargs"].update(starc_plan_kwargs(plan, resolved))
    return result, {
        "before": copy.deepcopy(old),
        "after": copy.deepcopy(new),
        "nonarchitecture_plan_fields_unchanged": True,
        "network_construction": "architecture_default_initialization",
        "capacity_matching": "shared_feature_widths_and_grids_not_equal_parameters_or_flops",
        "starc_options": resolved,
    }


# ``StarCPredictor`` settings: two-pass case-level rendering, case NMS radius and cap.
STARC_INFERENCE_DEFAULTS: dict[str, Any] = {
    "two_pass": True,
    "nms_radius_mm": 5.0,
    "max_case_instances": 32,
}


def validate_starc_inference(options: dict[str, Any] | None) -> dict[str, Any]:
    """Return the complete, explicit STAR-C inference settings; unknown keys fail closed."""
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("starc_inference must be a mapping")
    unknown = set(options) - set(STARC_INFERENCE_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown STAR-C inference options: {sorted(unknown)}")
    resolved = copy.deepcopy(STARC_INFERENCE_DEFAULTS) | copy.deepcopy(options)
    invalid = []
    if type(resolved["two_pass"]) is not bool:
        invalid.append("two_pass")
    if not _starc_positive(resolved["nms_radius_mm"]):
        invalid.append("nms_radius_mm")
    if type(resolved["max_case_instances"]) is not int or resolved["max_case_instances"] < 1:
        invalid.append("max_case_instances")
    if invalid:
        raise ValueError(f"Invalid STAR-C inference options: {invalid}")
    resolved["nms_radius_mm"] = float(resolved["nms_radius_mm"])
    return resolved
