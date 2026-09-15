"""Inspectable architecture protocols and fail-closed paired failure comparisons.

No training, checkpoint loading, or reserved-test evaluation is performed here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from dataclasses import asdict
from typing import Any

from .evaluation import patient_bootstrap
from .recipe_ablation import OPERATIONAL_FIELDS, recipe_fingerprint
from .torch_config import TorchConfig

ROLES = ("baseline", "candidate", "component_off", "capacity_control")
METRICS = ("mass_dice", "pancreas_dice")
COHORT_KEYS = ("manifest_sha256", "splits_sha256", "partition", "reference_fingerprint")
LIMITATIONS = [
    "Exploratory validation comparison, not an independent test or a SOTA claim.",
    "Patient confidence intervals condition on the trained seeds; they do not include training variability.",
    "Repeated scans are averaged within patients before patient resampling.",
    "Intervals are pointwise and uncorrected for multiple comparisons or checkpoint selection.",
    "Known hashes cannot establish absence of unidentified patient/source overlap.",
]


def document_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def _hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} must be a SHA256 digest")
    return value


def _scratch(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "pretrained",
                "weights",
                "encoder_weights",
                "checkpoint",
                "pretrained_path",
                "weights_path",
                "resume",
                "resume_from_checkpoint",
                "load_from",
            } and item not in (None, False):
                raise ValueError("Study recipes cannot load external or previous weights")
            if key == "initialization" and item != "scratch":
                raise ValueError("Study recipes require scratch initialization")
            _scratch(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _scratch(item)


def build_architecture_study(
    *,
    base_recipe: dict[str, Any],
    arms: dict[str, Any],
    hypothesis: str,
    cohort: dict[str, Any],
    source_commit: str,
    workspace_root: str,
    seeds: list[int] | None = None,
    primary_endpoint: str = "mass_dice",
) -> dict[str, Any]:
    """Build a protocol with exact field deltas and matching seeds, never a campaign.

    ``arms`` maps all four roles to description and changes mappings. Changes
    replace complete top-level fields, including the whole model_options map.
    New architectures may be declared before implementation; this function
    validates TorchConfig shape, not forward passes or model-option support.
    """
    from pathlib import Path

    _text(hypothesis, "hypothesis")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source_commit must be a full pinned Git commit")
    if primary_endpoint not in METRICS:
        raise ValueError("Primary endpoint must be mass_dice or pancreas_dice")
    _validate_cohort(cohort)
    seeds = [0, 1, 2] if seeds is None else seeds
    if (
        len(seeds) < 2
        or any(type(seed) is not int or not 0 <= seed < 2**32 for seed in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise ValueError("At least two distinct uint32 training seeds are required")
    if set(arms) != set(ROLES):
        raise ValueError("Declare baseline, candidate, component_off and capacity_control")
    _scratch(base_recipe)
    base = asdict(TorchConfig(**base_recipe))
    root = Path(workspace_root).expanduser().resolve()
    declarations, recipes = {}, {}
    for role in ROLES:
        arm = arms[role]
        if not isinstance(arm, dict) or set(arm) != {"description", "changes"}:
            raise ValueError("Each arm requires exactly description and changes")
        _text(arm["description"], f"{role} description")
        changes = arm["changes"]
        if not isinstance(changes, dict) or set(changes) - set(base):
            raise ValueError("Changes must be known top-level TorchConfig fields")
        if set(changes) & (OPERATIONAL_FIELDS | {"seed", "initialization", "backend", "purpose"}):
            raise ValueError("Arm changes cannot alter operational fields, seed or initialization")
        if role == "baseline" and changes:
            raise ValueError("Baseline must preserve the supplied base recipe")
        _scratch(changes)
        # Normalize tuples/paths/defaults, then expose exact effective deltas.
        normalized = asdict(TorchConfig(**(base | changes)))
        effective = {key: normalized[key] for key in base if normalized[key] != base[key]}
        if set(effective) != set(changes):
            raise ValueError(f"{role}: declared changes include ineffective replacements")
        declarations[role] = {
            "description": arm["description"],
            "changes": effective,
            "nonarchitecture_changes": sorted(set(effective) - {"model", "model_options"}),
        }
        for seed in seeds:
            run_id = f"{role}-seed{seed}"
            recipe = asdict(
                TorchConfig(**(normalized | {"seed": seed, "workspace": str(root / run_id)}))
            )
            recipes[run_id] = {
                "role": role,
                "seed": seed,
                "recipe": recipe,
                "scientific_recipe_sha256": recipe_fingerprint(recipe),
            }
    study = {
        "kind": "medical_architecture_study",
        "schema_version": 1,
        "runnable_campaign": False,
        "status": "planned_not_launched",
        "hypothesis": hypothesis,
        "source_commit": source_commit,
        "cohort": dict(cohort),
        "base_recipe": base,
        "workspace_root": str(root),
        "seeds": list(seeds),
        "primary_endpoint": primary_endpoint,
        "secondary_endpoints": [metric for metric in METRICS if metric != primary_endpoint],
        "arms": declarations,
        "runs": recipes,
        "comparisons": [
            {"baseline": role, "candidate": "candidate", "paired_training_seeds": list(seeds)}
            for role in ("baseline", "component_off", "capacity_control")
        ],
        "comparison_policy": {
            "partition": "val",
            "prediction_space": "full_native_scan",
            "patient_unit": "equal_weight_patient_mean",
            "missing_pairs": "withhold_inference",
            "interval": "paired_patient_percentile_bootstrap_conditional_on_seeds",
            "multiplicity": "pointwise_exploratory_no_automatic_significance_claim",
            "capacity_control": "measure actual parameters, peak VRAM, inference and training compute",
            "compute": "equal updates do not imply equal compute; record both",
        },
        "launch_gates": [
            "Implement/register models and verify scratch initialization and model options.",
            "Validate source/runtime and cohort bindings, raw/cache parity and whole-scan geometry.",
            "Pass forward/backward, tiny-fit, full-batch GPU profile and resume-lineage checks.",
            "Review exact recipe deltas and capacity-control measurements before a new frozen campaign.",
            "Do not feed this protocol to run_medical_campaign.py; it is not a campaign schema.",
        ],
        "limitations": LIMITATIONS,
    }
    study["fingerprint"] = document_sha256(study)
    return study


def validate_architecture_study(study: dict[str, Any]) -> None:
    """Reconstruct every declaration; reject recipe, seed, policy or digest drift."""
    if study.get("kind") != "medical_architecture_study" or study.get("schema_version") != 1:
        raise ValueError("Unsupported architecture study schema")
    rebuilt = build_architecture_study(
        base_recipe=study["base_recipe"],
        arms={
            role: {key: value[key] for key in ("description", "changes")}
            for role, value in study["arms"].items()
        },
        hypothesis=study["hypothesis"],
        cohort=study["cohort"],
        source_commit=study["source_commit"],
        workspace_root=study["workspace_root"],
        seeds=study["seeds"],
        primary_endpoint=study["primary_endpoint"],
    )
    if document_sha256(rebuilt) != document_sha256(study):
        raise ValueError("Architecture study differs from its immutable declarations")


def _validate_cohort(cohort: Any) -> None:
    if not isinstance(cohort, dict) or not all(key in cohort for key in COHORT_KEYS):
        raise ValueError("Cohort needs manifest, split, partition and reference bindings")
    for key in COHORT_KEYS:
        if key != "partition":
            _hash(cohort[key], key)
    if cohort["partition"] != "val":
        raise ValueError(
            "Exploratory architecture tools accept validation only, never reserved test"
        )


def _report_cases(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("kind", report.get("schema_kind")) != "medical_failure_analysis":
        raise ValueError("Expected a medical_failure_analysis report")
    _validate_cohort(report.get("cohort"))
    rows = report.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Failure reports require a nonempty, explicit case inventory")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Case row must be a mapping")
        key = _text(row.get("case_key"), "case_key")
        _text(row.get("patient_key"), "patient_key")
        if key in result or not isinstance(row.get("models"), dict):
            raise ValueError("Duplicate case or missing model mapping")
        result[key] = row
    return result


def _metric(row: Any, metric: str) -> tuple[float | None, str | None]:
    if not isinstance(row, dict):
        return None, "model_missing"
    if row.get("status") not in {"completed", "ok", "success"}:
        return None, f"model_status:{row.get('status', 'missing')}"
    value = row.get(metric)
    if value is None:
        return None, "metric_missing"
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"{metric} must be finite in [0,1] or null")
    return float(value), None


def compare_failure_reports(
    pairs: list[dict[str, Any]],
    *,
    metric: str = "mass_dice",
    bootstrap_samples: int = 10000,
    bootstrap_seed: int = 0,
) -> dict[str, Any]:
    """Compare explicit seed pairs on identical cases, retaining missing outcomes.

    Each pair supplies baseline_report/candidate_report dictionaries, model IDs
    baseline_model/candidate_model, and an explicit integer training_seed.
    All seeds are averaged per case, then scans are averaged within patients.
    Inference is withheld if any required score is unavailable in any pair.
    """
    if metric not in METRICS or not pairs:
        raise ValueError("Choose a supported metric and at least one seed pair")
    if type(bootstrap_samples) is not int or not 1 <= bootstrap_samples <= 100000:
        raise ValueError("bootstrap_samples must be in [1,100000]")
    if type(bootstrap_seed) is not int or not 0 <= bootstrap_seed < 2**32:
        raise ValueError("bootstrap_seed must be a uint32")
    seeds, rows, provenance = set(), [], []
    first_report = pairs[0]["baseline_report"]
    reference_cases = _report_cases(first_report)
    cohort = first_report["cohort"]
    by_seed: dict[int, dict[str, list[float]]] = {}
    patient_seed_deltas: dict[str, list[float]] = {}
    seen_model_sources: dict[str, set[str]] = {"baseline": set(), "candidate": set()}
    missing = []
    for pair in pairs:
        seed = pair.get("training_seed")
        if type(seed) is not int or not 0 <= seed < 2**32 or seed in seeds:
            raise ValueError("Each pair needs a distinct uint32 training_seed")
        seeds.add(seed)
        cases = {}
        sources = {}
        for side in ("baseline", "candidate"):
            report = pair[f"{side}_report"]
            model = _text(pair.get(f"{side}_model"), f"{side}_model")
            cases[side] = _report_cases(report)
            if (
                {key: report["cohort"][key] for key in COHORT_KEYS}
                != {key: cohort[key] for key in COHORT_KEYS}
                or report.get("protocol") != first_report.get("protocol")
                or set(cases[side]) != set(reference_cases)
                or any(
                    cases[side][key]["patient_key"] != reference_cases[key]["patient_key"]
                    for key in reference_cases
                )
            ):
                raise ValueError("Cohort, protocol, case inventory or patient mapping mismatch")
            metadata = report.get("models", {})
            if isinstance(metadata, list):
                identifiers = [item.get("id") for item in metadata if isinstance(item, dict)]
                if len(identifiers) != len(metadata) or len(set(identifiers)) != len(identifiers):
                    raise ValueError("Model metadata must have unique IDs")
                metadata = {item["id"]: item for item in metadata}
            info = metadata.get(model, {}) if isinstance(metadata, dict) else {}
            if not isinstance(info, dict):
                raise ValueError("Model metadata must be a mapping")
            known_seed = info.get("seed")
            if known_seed is not None and (type(known_seed) is not int or known_seed != seed):
                raise ValueError("Declared training seed differs from model metadata")
            report_hash = document_sha256(report)
            checkpoint = info.get("checkpoint_sha256")
            if checkpoint is not None:
                _hash(checkpoint, "checkpoint_sha256")
            source_identity = checkpoint or f"{report_hash}:{model}"
            if source_identity in seen_model_sources[side]:
                raise ValueError(
                    "One model evidence source cannot masquerade as multiple training seeds"
                )
            seen_model_sources[side].add(source_identity)
            sources[side] = {
                "report_id": report.get("report_id"),
                "report_sha256": report_hash,
                "model": model,
                "checkpoint_sha256": checkpoint,
                "seed_verified_from_metadata": known_seed is not None,
            }
        provenance.append({"training_seed": seed, **sources})
        by_seed[seed] = {}
        for key in sorted(reference_cases):
            values, errors = {}, {}
            patient = reference_cases[key]["patient_key"]
            for side in ("baseline", "candidate"):
                values[side], errors[side] = _metric(
                    cases[side][key]["models"].get(pair[f"{side}_model"]), metric
                )
            candidate, baseline = values["candidate"], values["baseline"]
            delta = None if candidate is None or baseline is None else candidate - baseline
            row = {
                "case_key": key,
                "patient_key": patient,
                "training_seed": seed,
                **values,
                "delta": delta,
                "errors": errors,
            }
            rows.append(row)
            if delta is None:
                missing.append(row)
            else:
                by_seed[seed].setdefault(patient, []).append(delta)
    per_seed: list[dict[str, Any]] = []
    for seed in sorted(seeds):
        seed_missing = [row for row in missing if row["training_seed"] == seed]
        summary = (
            patient_bootstrap(by_seed[seed], bootstrap_samples, bootstrap_seed)
            if not seed_missing
            else None
        )
        per_seed.append(
            {
                "training_seed": seed,
                "missing_cases": len(seed_missing),
                "paired_patient_delta": summary,
            }
        )
        if not seed_missing:
            for patient, deltas in by_seed[seed].items():
                patient_seed_deltas.setdefault(patient, []).append(statistics.mean(deltas))
    complete = not missing
    aggregate = (
        patient_bootstrap(patient_seed_deltas, bootstrap_samples, bootstrap_seed)
        if complete
        else None
    )
    if aggregate is not None:
        aggregate.update(
            cases=len(reference_cases),
            training_seed_count=len(seeds),
            method="paired patient percentile bootstrap after averaging scans within patient and paired deltas across seeds",
        )
    seed_means = [
        row["paired_patient_delta"]["mean"]
        for row in per_seed
        if row["paired_patient_delta"] is not None
    ]
    return {
        "kind": "medical_failure_comparison",
        "schema_version": 1,
        "status": "completed" if complete else "incomplete_inference_withheld",
        "cohort": cohort,
        "metric": metric,
        "direction": "candidate_minus_baseline",
        "training_seeds": sorted(seeds),
        "expected_cases_per_seed": len(reference_cases),
        "expected_pairs": len(reference_cases) * len(seeds),
        "complete_pairs": len(rows) - len(missing),
        "missing_pairs": missing,
        "case_pairs": rows,
        "conditional_patient_bootstrap": aggregate,
        "per_seed": per_seed,
        "training_seed_variation": {
            "sample_sd_of_patient_mean_delta": statistics.stdev(seed_means)
            if complete and len(seed_means) > 1
            else None,
            "min": min(seed_means) if complete else None,
            "max": max(seed_means) if complete else None,
            "seeds": len(seeds),
            "is_confidence_interval": False,
        },
        "sources": provenance,
        "limitations": LIMITATIONS,
        "seed_provenance": "Unverified seeds are explicit user declarations; report metadata verification is recorded per side.",
    }
