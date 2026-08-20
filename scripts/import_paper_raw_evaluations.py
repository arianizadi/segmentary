#!/usr/bin/env python3
"""Publish a uniform raw-weight paper view from verified evaluation-only results."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from scripts import run_benchmark_campaign as campaign

EXPECTED_EVALUATION_SHA = "a1a85ebcd593a1eeb3ad2e2445c14bbe6f5c5270"
TRAINING_SOURCE_SHA = "b9eb3e1f390b70aad63e78b2e723bd79b5266471"
COMPARISON_ROOT = campaign.REPO_ROOT / "docs/results/model-comparison"

RESUMED_CELLS: dict[tuple[str, str], list[int]] = {
    ("native_resnet18_fpn_fcn", "cityscapes"): [12_008, 20_013],
    ("native_mobilenetv3_large_lraspp", "cityscapes"): [24_016],
    ("smp_pspnet_mobilenet_v2", "cityscapes_to_railsem19"): [16_000],
    ("smp_pan_resnext50", "cityscapes_to_railsem19"): [4_000],
    ("native_mobilenetv3_large_lraspp", "railsem19"): [28_000],
    ("hf_auto_mobilenetv2_deeplabv3", "railsem19"): [24_000],
    ("hf_auto_mobilevitv2_deeplabv3", "cityscapes"): [4_002],
    ("smp_unetplusplus_efficientnet_b0", "railsem19"): [32_000],
}

BN_RECALIBRATIONS: dict[str, dict[str, Any]] = {
    "cityscapes": {
        "bn_modules": 55,
        "recalibration_batches": 371,
        "training_images": 2968,
        "old_miou": 0.31455687106804364,
        "corrected_miou": 0.6774129638222623,
        "source_checkpoint_sha256": "dfe1a70fe765b643b09f89d66ca21e6a3b19f0ef7bddeda0a7fc097bb5050895",
        "corrected_checkpoint_sha256": "4f3711930ae1df9eaa26a222ba7652799b210f3a244770289a5e58a1c8bf3aa5",
        "source_result_sha256": "05dac80e6c8f14234dce1100994d246c8b09dbbed21e3667e0726f07c5ea8c8a",
        "corrected_result_sha256": "b135e1a1431f6d1c8639912b3f32e5e7f051675cd8c3ce454fce63f0d88ade20",
    },
    "railsem19": {
        "bn_modules": 55,
        "recalibration_batches": 850,
        "training_images": 6800,
        "old_miou": 0.14359671156058598,
        "corrected_miou": 0.579339803923551,
        "source_checkpoint_sha256": "10a45b97af1d179af6b60ad8506b4fdda99d8f3e8afe82eee14b657116447550",
        "corrected_checkpoint_sha256": "79a6185e64264a8fa64a4bca840b7536c498c9e989fae15c821957420f97e768",
        "source_result_sha256": "dfe8cc318739fd431ed7fd437ed8f505a6ed388ad2608bf2d3e6489e6ba7e9c1",
        "corrected_result_sha256": "6471ff61acc59206881bb5cd5a1bf1796cb56848011692340e9fcc5d5f953203",
        "corrected_performance_sha256": "beaf184afa64d20b744bcb3635e510e65729054a98d1769841682bfc22574dff",
    },
    "cityscapes_to_railsem19": {
        "bn_modules": 55,
        "recalibration_batches": 850,
        "training_images": 6800,
        "old_miou": 0.1185908977098898,
        "corrected_miou": 0.5328885396125134,
        "source_checkpoint_sha256": "1df464b560c05d155838961097dc9cc70a00a519d867ffc5130b266f18f2b286",
        "corrected_checkpoint_sha256": "2671491cfd7ee6602687c37110da7b0e85183c7fe0bb5aa429ca8541f2a7ce35",
        "source_result_sha256": "b050c7ae581b8b94d62b56d702b0e259b3b3dcc3631e2242f9d74cd55c553979",
        "corrected_result_sha256": "04da05647559dcda3ce9494ee043f2f2fcd2ac17005e04d41f1f7bc6ac633a6c",
    },
}


def _append_caveat(protocol: dict[str, Any], text: str) -> None:
    caveats = protocol.setdefault("caveats", [])
    if text not in caveats:
        caveats.append(text)


def _remove_caveats_containing(protocol: dict[str, Any], marker: str) -> None:
    protocol["caveats"] = [caveat for caveat in protocol.get("caveats", []) if marker not in caveat]


def _post_resume_segments(
    protocol: dict[str, Any], resume_steps: list[int]
) -> list[dict[str, Any]]:
    segments = []
    for individual in protocol.get("individual", []):
        stages = []
        for original in individual.get("source", {}).get("training_stages", []):
            stage = copy.deepcopy(original)
            stage["timing_scope"] = "post_resume_segment_only"
            stage["resume_checkpoint_steps"] = resume_steps
            stages.append(stage)
        if stages:
            segments.append(
                {
                    "stages": stages,
                    "note": "These values cover only the final post-resume segment, not the total.",
                }
            )
    return segments


def _apply_review_corrections(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Fail closed on partial resume timing and retain exceptional BN provenance."""
    for (model_id, protocol_id), resume_steps in RESUMED_CELLS.items():
        record = records[model_id]
        variants = [record["protocols"].get(protocol_id)]
        variants.append(record.get("paper_raw_protocols", {}).get(protocol_id))
        for protocol in (item for item in variants if isinstance(item, dict)):
            training = protocol["resource_evidence"]["training"]
            segments = _post_resume_segments(protocol, resume_steps)
            if segments:
                training["post_resume_segments"] = segments
            training.pop("post_resume_segment_only", None)
            training.update(
                {
                    "seed_count": 0,
                    "wall_clock_s_mean": None,
                    "gpu_hours_mean": None,
                    "peak_vram_bytes_per_device": None,
                    "total_timing_status": "not_retained_due_to_resume",
                }
            )
            for individual in protocol.get("individual", []):
                for stage in individual.get("source", {}).get("training_stages", []):
                    stage["timing_scope"] = "post_resume_segment_only"
                    stage["resume_checkpoint_steps"] = resume_steps
            _remove_caveats_containing(protocol, "retained across interruption recovery")
            _append_caveat(
                protocol,
                campaign.RESUME_TIMING_CAVEAT,
            )

    mobile = records["hf_auto_mobilenetv2_deeplabv3"]
    for protocol_id, correction in BN_RECALIBRATIONS.items():
        public = {
            "kind": "batchnorm_running_statistics_recalibration",
            "reason": "correct an upstream TensorFlow-to-PyTorch momentum-convention error",
            "data_scope": "training split only; no validation images",
            "parameters_changed": 0,
            **correction,
        }
        variants = [mobile["protocols"][protocol_id]]
        raw = mobile.get("paper_raw_protocols", {}).get(protocol_id)
        if isinstance(raw, dict):
            variants.append(raw)
        for protocol in variants:
            protocol["evaluation_correction"] = public
            for individual in protocol.get("individual", []):
                individual.setdefault("source", {})["evaluation_correction"] = public
            _remove_caveats_containing(
                protocol, "BatchNorm running-statistics buffers were recalibrated"
            )
            _append_caveat(protocol, campaign._bn_recalibration_caveat(public))
    transfer_variants = [mobile["protocols"]["cityscapes_to_railsem19"]]
    raw_transfer = mobile.get("paper_raw_protocols", {}).get("cityscapes_to_railsem19")
    if isinstance(raw_transfer, dict):
        transfer_variants.append(raw_transfer)
    for transfer in transfer_variants:
        _remove_caveats_containing(transfer, "Transfer warm-started from the pre-recalibration")
        _append_caveat(
            transfer,
            "Transfer warm-started from the pre-recalibration Cityscapes checkpoint; only "
            "BatchNorm buffers differ from the published Cityscapes endpoint. Training-mode "
            "BatchNorm uses batch statistics, so those initial buffers did not affect gradient "
            "calculations; the transfer endpoint received its own disclosed recalibration "
            "before evaluation.",
        )
    missing_transfer_sources = []
    for model_id, record in records.items():
        variants = [record["protocols"].get("cityscapes_to_railsem19")]
        variants.append(record.get("paper_raw_protocols", {}).get("cityscapes_to_railsem19"))
        protocols = [item for item in variants if isinstance(item, dict)]
        if not protocols or all(
            campaign._transfer_source_provenance_retained(protocol) for protocol in protocols
        ):
            continue
        for protocol in protocols:
            if campaign._transfer_source_provenance_retained(protocol):
                continue
            _append_caveat(
                protocol,
                "The transfer endpoint is complete, but its City40 source-checkpoint hash was "
                "not retained, so the warm-start link cannot be independently audited.",
            )
        missing_transfer_sources.append(model_id)
    pan = records["smp_pan_resnext50"]
    pan_variants = [pan["protocols"]["cityscapes"]]
    raw_pan = pan.get("paper_raw_protocols", {}).get("cityscapes")
    if isinstance(raw_pan, dict):
        pan_variants.append(raw_pan)
    for protocol in pan_variants:
        _append_caveat(
            protocol,
            "The retained historical endpoint label conflicts with the fresh paired "
            "measurement; the paper-primary value is the independently verified raw "
            "evaluation.",
        )
    return {
        "schema_version": 2,
        "resumed_cells": [
            {
                "model_id": model_id,
                "protocol": protocol_id,
                "resume_checkpoint_steps": steps,
                "publication_action": "total timing and whole-run peak marked not retained",
            }
            for (model_id, protocol_id), steps in RESUMED_CELLS.items()
        ],
        "batchnorm_recalibrations": [
            {"model_id": "hf_auto_mobilenetv2_deeplabv3", "protocol": protocol_id, **value}
            for protocol_id, value in BN_RECALIBRATIONS.items()
        ],
        "transfer_source_provenance_missing": sorted(missing_transfer_sources),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise campaign.CampaignError(f"{path} must contain a JSON object")
    return value


def _finite_tree(value: Any) -> bool:
    if value is None or isinstance(value, str | bool):
        return True
    if isinstance(value, int | float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_tree(item) for item in value)
    if isinstance(value, dict):
        return all(_finite_tree(item) for item in value.values())
    return False


def _raw_individual(
    *,
    original: dict[str, Any],
    result: dict[str, Any],
    result_sha256: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    metrics = result["metrics"]
    boundary = metrics.get("boundary") or {}
    names = list(original["metrics"]["per_class_iou"])
    if set(metrics["per_class_iou"]) != set(names) or set(metrics["support"]) != set(names):
        raise campaign.CampaignError(f"{target['job_id']}: class metric keys changed")
    individual = copy.deepcopy(original)
    individual["metrics"] = {
        **{key: metrics.get(key) for key, _ in campaign.AGGREGATE_METRICS},
        "boundary_macro_f1": boundary.get("macro_f1"),
        "per_class_iou": {name: metrics["per_class_iou"].get(name) for name in names},
        "support": {name: metrics["support"].get(name) for name in names},
    }
    source = individual["source"]
    source.update(
        {
            "result_sha256": result_sha256,
            "git_sha": result["git_sha"],
            "git_dirty": False,
            "checkpoint_available": True,
            "checkpoint_sha256": target["checkpoint_sha256"],
            "checkpoint_step": target["checkpoint_step"],
            "checkpoint_size_bytes": target["checkpoint_size_bytes"],
            "full_validation_pipeline": {
                "images": result["dataset_sizes"]["eval"],
                "wall_clock_s": result["wall_clock_s"],
                "images_per_s": result["dataset_sizes"]["eval"] / result["wall_clock_s"],
                "scope": "loader, sliding-window inference, and metrics",
            },
        }
    )
    individual["milestones"] = {}
    return individual


def _validate_result(
    target: dict[str, Any], result_path: Path, original: dict[str, Any], *, weights: str
) -> tuple[dict[str, Any], str]:
    result = _load_object(result_path)
    result_hash = _sha256(result_path)
    evaluation = result.get("config", {}).get("evaluation", {})
    if evaluation.get("weights") != weights:
        raise campaign.CampaignError(f"{result_path}: evaluation weights are not {weights}")
    if result.get("git_sha") != EXPECTED_EVALUATION_SHA or result.get("git_dirty") is not False:
        raise campaign.CampaignError(f"{result_path}: source is not exact and clean")
    if result.get("seed") != target["seed"]:
        raise campaign.CampaignError(f"{result_path}: seed changed")
    if result.get("dataset_sizes", {}).get("eval") != target["images"]:
        raise campaign.CampaignError(f"{result_path}: validation image count changed")
    if not str(result.get("stage", "")).startswith("eval:"):
        raise campaign.CampaignError(f"{result_path}: not a standalone evaluation record")
    if target["checkpoint"] not in str(result.get("notes", "")):
        raise campaign.CampaignError(f"{result_path}: checkpoint provenance changed")
    if not isinstance(result.get("wall_clock_s"), int | float) or result["wall_clock_s"] <= 0:
        raise campaign.CampaignError(f"{result_path}: invalid evaluation duration")
    if not _finite_tree(result.get("metrics")):
        raise campaign.CampaignError(f"{result_path}: non-finite metrics")
    source = original.get("source", {})
    for key in ("checkpoint_sha256", "checkpoint_step", "checkpoint_size_bytes"):
        if source.get(key) != target[key]:
            raise campaign.CampaignError(f"{target['job_id']}: published {key} changed")
    return result, result_hash


def _comparison_markdown(rows: list[dict[str, Any]]) -> str:
    raw_wins = sum(row["delta_miou_points"] > 0 for row in rows)
    ema_wins = sum(row["delta_miou_points"] < 0 for row in rows)
    ties = len(rows) - raw_wins - ema_wins
    mean_delta = sum(row["delta_miou_points"] for row in rows) / len(rows)
    mean_summary = (
        f"{('raw' if mean_delta > 0 else 'EMA')} averaged {abs(mean_delta):.2f} mIoU "
        "percentage points higher"
        if mean_delta
        else "the two endpoints had the same mean mIoU"
    )
    rail_rows = [row for row in rows if row["protocol"] == "railsem19"]
    raw_rail_order = [
        row["model_id"] for row in sorted(rail_rows, key=lambda row: -row["raw_miou"])
    ]
    ema_rail_order = [
        row["model_id"] for row in sorted(rail_rows, key=lambda row: -row["ema_miou"])
    ]
    labels = {
        "cityscapes": "Cityscapes",
        "railsem19": "RailSem19",
        "cityscapes_to_railsem19": "Cityscapes to RailSem19",
    }
    lines = [
        "# Raw versus EMA checkpoint weights",
        "",
        "This paired analysis evaluates raw and exponential-moving-average (EMA) weights "
        "from the same final checkpoint. Dataset, validation split, seed, taxonomy, sliding "
        "window, stride, precision, and no-TTA policy are identical; only the selected weight "
        "set changes.",
        "",
        "The main [model comparison](README.md) uses raw weights for every quality cell so the "
        "paper compares architectures under one uniform rule. Standardized FPS and memory are "
        "not repeated because raw and EMA use the same model graph and tensor shapes.",
        "",
        "These are single-seed descriptive differences, not confidence intervals or evidence "
        "of statistical significance. The higher-endpoint column carries the direction so the "
        "human-facing table does not use signed or error-bar notation.",
        "The 36 paired cells are a selected subset: they are endpoints previously admitted "
        "with EMA, generally architectures without running-stat BatchNorm. They do not form a "
        "random sample of all 111 quality cells.",
        "",
        "## Summary",
        "",
        f"- Paired cells: {len(rows)}.",
        f"- Raw higher: {raw_wins}; EMA higher: {ema_wins}; exact ties: {ties}.",
        f"- Across these cells, {mean_summary}.",
        *(
            [
                f"- Raw and EMA give the same rank order across all {len(rail_rows)} paired RailSem19 cells."
            ]
            if rail_rows and raw_rail_order == ema_rail_order
            else []
        ),
        "",
        "## Paired results",
        "",
        "| model | protocol | raw mIoU | EMA mIoU | absolute difference (points) | higher endpoint |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in sorted(rows, key=lambda item: (item["protocol"], item["model_id"])):
        delta = row["delta_miou_points"]
        higher = "raw" if delta > 0 else "EMA" if delta < 0 else "tie"
        lines.append(
            f"| `{row['model_id']}` | {labels[row['protocol']]} | "
            f"{row['raw_miou'] * 100:.2f} | {row['ema_miou'] * 100:.2f} | "
            f"{abs(delta):.2f} | {higher} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "EMA smooths parameter updates and can improve validation quality, but it is not "
            "universally better. Architectures with running-stat BatchNorm can be especially "
            "sensitive because parameter EMA does not automatically provide matching averaged "
            "running buffers. Raw-only reporting avoids architecture-dependent endpoint selection "
            "and avoids choosing the better endpoint on the same validation set.",
            "",
            "Machine-readable hashes, metrics, and provenance are retained in "
            "[`raw-evaluation-manifest.json`](raw-evaluation-manifest.json) and each model's "
            "record under [`records/`](records/).",
            "",
        ]
    )
    output = "\n".join(lines)
    if "±" in output:
        raise campaign.CampaignError("raw/EMA analysis contains forbidden dispersion formatting")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--ema-results-root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    preflight = _load_object(args.preflight)
    if preflight.get("failures") or preflight.get("verified_count") != 36:
        raise campaign.CampaignError("preflight must verify all 36 paired cells")

    records = campaign._load_existing_records(campaign.REPO_ROOT)
    rows: list[dict[str, Any]] = []
    planned: dict[Path, str] = {}
    for target in preflight["targets"]:
        model_id = target["model_id"]
        protocol_id = target["protocol"]
        record = records[model_id]
        protocol = record["protocols"][protocol_id]
        if str(protocol["evaluation"]["weights"]).lower() != "ema":
            raise campaign.CampaignError(f"{target['job_id']}: baseline is no longer EMA")
        matches = [item for item in protocol["individual"] if item["seed"] == target["seed"]]
        if len(matches) != 1:
            raise campaign.CampaignError(f"{target['job_id']}: expected exactly one retained seed")
        original = matches[0]
        result_path = args.results_root / target["job_id"] / "results.json"
        result, result_hash = _validate_result(target, result_path, original, weights="raw")
        ema_result_path = args.ema_results_root / target["job_id"] / "results.json"
        ema_result, ema_result_hash = _validate_result(
            target, ema_result_path, original, weights="ema"
        )
        raw_config = copy.deepcopy(result["config"])
        ema_config = copy.deepcopy(ema_result["config"])
        raw_config["evaluation"].pop("weights", None)
        ema_config["evaluation"].pop("weights", None)
        if raw_config != ema_config:
            raise campaign.CampaignError(
                f"{target['job_id']}: paired evaluator configs differ beyond weights"
            )
        if (
            result["stage"] != ema_result["stage"]
            or result["dataset_sizes"] != ema_result["dataset_sizes"]
        ):
            raise campaign.CampaignError(
                f"{target['job_id']}: paired stage or dataset size changed"
            )
        if result["metrics"].get("support") != ema_result["metrics"].get("support"):
            raise campaign.CampaignError(f"{target['job_id']}: paired validation support changed")
        raw = copy.deepcopy(protocol)
        raw["evaluation"]["weights"] = "raw"
        raw["individual"] = [
            _raw_individual(
                original=original,
                result=result,
                result_sha256=result_hash,
                target=target,
            )
        ]
        raw["milestones"] = {}
        campaign._aggregate_protocol(raw)
        pipeline = raw["individual"][0]["source"]["full_validation_pipeline"]
        raw["resource_evidence"]["full_validation_pipeline"] = {
            "seed_count": 1,
            "images": pipeline["images"],
            "wall_clock_s_mean": pipeline["wall_clock_s"],
            "images_per_s_mean": pipeline["images_per_s"],
            "scope": pipeline["scope"],
        }
        record.setdefault("paper_raw_protocols", {})[protocol_id] = raw
        record["paper_quality_policy"] = {
            "primary_weights": "raw",
            "evaluation_source_git_sha": EXPECTED_EVALUATION_SHA,
            "paired_analysis": "../RAW_VS_EMA.md",
        }
        raw_miou = float(result["metrics"]["miou"])
        ema_miou = float(ema_result["metrics"]["miou"])
        rows.append(
            {
                "job_id": target["job_id"],
                "model_id": model_id,
                "protocol": protocol_id,
                "seed": target["seed"],
                "images": target["images"],
                "checkpoint_sha256": target["checkpoint_sha256"],
                "checkpoint_step": target["checkpoint_step"],
                "resolved_config_sha256": target["config_sha256"],
                "raw_result_sha256": result_hash,
                "raw_result_git_sha": result["git_sha"],
                "raw_result_config_hash": result["config_hash"],
                "raw_wall_clock_s": result["wall_clock_s"],
                "raw_miou": raw_miou,
                "ema_result_sha256": ema_result_hash,
                "ema_result_git_sha": ema_result["git_sha"],
                "ema_result_config_hash": ema_result["config_hash"],
                "ema_wall_clock_s": ema_result["wall_clock_s"],
                "ema_miou": ema_miou,
                "delta_miou_points": (raw_miou - ema_miou) * 100,
                "paired_config_equal_except_weights": True,
            }
        )

    if len(rows) != 36:
        raise campaign.CampaignError(f"expected 36 paired rows, found {len(rows)}")
    review_corrections = _apply_review_corrections(records)
    for record in records.values():
        for protocol_id, protocol in campaign._primary_protocols(record).items():
            if (
                protocol_id in campaign.REQUIRED_PROTOCOLS
                and protocol["evaluation"]["weights"] != "raw"
            ):
                raise campaign.CampaignError(
                    f"{record['model_id']} {protocol_id}: paper-primary endpoint is not raw"
                )

    manifest_payload = {
        "schema_version": 1,
        "policy": "raw checkpoint weights for every paper-primary quality cell",
        "evaluation_source_git_sha": EXPECTED_EVALUATION_SHA,
        "paired_cell_count": len(rows),
        "targets": rows,
    }
    manifest_path = COMPARISON_ROOT / "raw-evaluation-manifest.json"
    analysis_path = COMPARISON_ROOT / "RAW_VS_EMA.md"
    planned[manifest_path] = json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n"
    planned[analysis_path] = _comparison_markdown(rows)
    planned[COMPARISON_ROOT / "paper-review-corrections.json"] = (
        json.dumps(review_corrections, indent=2, sort_keys=True) + "\n"
    )
    corrected_models = {model_id for model_id, _ in RESUMED_CELLS} | {
        "hf_auto_mobilenetv2_deeplabv3",
        "smp_pan_resnext50",
    }
    for model_id, record in records.items():
        if "paper_raw_protocols" not in record and model_id not in corrected_models:
            continue
        path = COMPARISON_ROOT / "records" / f"{model_id}.json"
        planned[path] = json.dumps(record, indent=2) + "\n"

    status_path = COMPARISON_ROOT / "status.json"
    status = _load_object(status_path)
    status["scope"]["quality_weight_policy"] = "raw checkpoint weights for every model and protocol"
    status["scope"]["paired_raw_ema_cells"] = len(rows)
    status["scope"]["statistical_scope"] = (
        "single seed 0; descriptive values and ranks; no significance claim"
    )
    status["scope"]["transfer_cost_scope"] = (
        "reported transfer training is Rail20 adaptation-only; cumulative fields add reused "
        "City40 when exact totals are retained"
    )
    status["scope"]["resource_corrections"] = "paper-review-corrections.json"
    status["scope"]["training"]["evaluation"] = (
        "paper-primary raw checkpoint weights for every model, BF16 autocast, batch 1, "
        "1024x1024 sliding window, stride 768, no TTA"
    )
    for row in status["models"]:
        record = records[row["alias_of"] or row["model"]]
        for protocol_id in campaign.REQUIRED_PROTOCOLS:
            value = campaign._record_metric(record, protocol_id, "miou")
            row[f"{protocol_id}_miou"] = campaign._number(
                value * 100 if isinstance(value, int | float) else None
            )
    planned[status_path] = json.dumps(status, indent=2) + "\n"
    planned[COMPARISON_ROOT / "results.csv"] = campaign._comparison_csv(status, records)
    campaign_manifest = campaign.load_campaign_manifest()
    planned[COMPARISON_ROOT / "README.md"] = campaign._central_readme(
        campaign_manifest, status, records, TRAINING_SOURCE_SHA
    )
    by_model = {model.id: model for model in campaign_manifest.models}
    for model_id, record in records.items():
        model = by_model[model_id]
        path = campaign.REPO_ROOT / model.readme
        planned[path] = campaign._replace_generated_section(
            path.read_text(), campaign._model_generated_section(record)
        )
    campaign._public_privacy_check(planned)
    if any("±" in content for path, content in planned.items() if path.suffix == ".md"):
        raise campaign.CampaignError("generated Markdown contains forbidden plus-minus notation")
    if args.write:
        for path, content in planned.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(content)
            os.replace(temporary, path)
    print(
        json.dumps(
            {
                "paired_cells": len(rows),
                "planned_files": len(planned),
                "write": args.write,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
