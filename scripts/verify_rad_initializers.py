"""CPU-only provenance checks for fresh RAD adaptation from non-RAD sources.

The reviewed checkpoint manifest is pinned by SHA-256. This helper hashes source
configuration YAMLs, never multi-gigabyte checkpoint files; the existing runtime
still verifies actual checkpoint bytes during initialization and job execution.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml

SOURCE_PROTOCOLS = {"cityscapes", "railsem19", "cityscapes_to_railsem19"}
JOB_SOURCES = {
    "rtis_only": None,
    "cityscapes_to_rtis": "cityscapes",
    "railsem19_to_rtis": "railsem19",
    "cityscapes_to_railsem19_to_rtis": "cityscapes_to_railsem19",
}
FORBIDDEN = re.compile(
    r"(?i)(?:paul[-_]test[-_]rtis|rtisrail|(?:^|[/_\-])rtis(?:[/_\-.]|$)|(?:^|[/_\-])rad(?:[/_\-.\d]|$))"
)
HEX = re.compile(r"[0-9a-f]{64}\Z")

APPROVED_RECIPE_CHECKPOINTS = {
    None,
    "microsoft/beit-base-finetuned-ade-640-640",
    "google/deeplabv3_mobilenet_v2_1.0_513",
    "apple/deeplabv3-mobilevit-xx-small",
    "apple/mobilevitv2-1.0-voc-deeplabv3",
    "nvidia/segformer-b0-finetuned-ade-512-512",
    "openmmlab/upernet-swin-tiny",
    "nvidia/mit-b0",
    "nvidia/mit-b2",
    "nvidia/mit-b5",
    "openmmlab/upernet-convnext-small",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reject_rad(value, label):
    if isinstance(value, dict):
        for child in value.values():
            reject_rad(child, label)
    elif isinstance(value, (list, tuple)):
        for child in value:
            reject_rad(child, label)
    elif isinstance(value, str) and FORBIDDEN.search(value):
        raise ValueError(f"RAD/RTIS provenance is forbidden in source {label}")


def verify_initializers(plan: dict) -> dict:
    manifest = plan.get("source_manifest")
    if (
        not isinstance(manifest, dict)
        or not manifest.get("path")
        or not HEX.fullmatch(manifest.get("sha256", ""))
    ):
        raise ValueError("Pinned source_manifest path and SHA-256 are required")
    path = Path(manifest["path"])
    if digest(path) != manifest["sha256"]:
        raise ValueError("Source manifest hash changed")
    sources = json.loads(path.read_text())
    if not isinstance(sources, list) or not sources:
        raise ValueError("Source manifest must be a nonempty list")
    lookup = {}
    configs = {}
    audits = []
    for row in sources:
        model, protocol = row.get("model"), row.get("protocol")
        if not isinstance(model, str) or not model or protocol not in SOURCE_PROTOCOLS:
            raise ValueError("Unapproved source model/protocol")
        key = (model, protocol)
        if key in lookup:
            raise ValueError("Duplicate model/protocol in source manifest")
        if not HEX.fullmatch(row.get("recorded_sha256", "")):
            raise ValueError("Source recorded SHA-256 must be 64 lowercase hex digits")
        for field in ("checkpoint", "config"):
            if not isinstance(row.get(field), str) or not Path(row[field]).is_absolute():
                raise ValueError("Source paths must be absolute")
            reject_rad(row[field], field)
        lookup[key] = row
    for key, row in lookup.items():
        cfg_path = Path(row["config"])
        cfg = yaml.safe_load(cfg_path.read_text())
        if not isinstance(cfg, dict):
            raise ValueError("Source configuration must be an object")
        protocol = row["protocol"]
        expected_space = "cityscapes19" if protocol == "cityscapes" else "rail_union"
        if cfg.get("space") != expected_space:
            raise ValueError("Source taxonomy space does not match declared protocol")
        reject_rad(cfg.get("stages"), "stages")
        reject_rad(cfg.get("model"), "model")
        if cfg.get("model", {}).get("checkpoint") not in APPROVED_RECIPE_CHECKPOINTS:
            raise ValueError("Source config has an untracked model checkpoint override")
        stages = cfg.get("stages")
        if not isinstance(stages, list) or len(stages) != 1:
            raise ValueError("Expected one resolved source endpoint stage")
        stage = stages[0]
        expected_data = "cityscapes" if protocol == "cityscapes" else "railsem19"
        if (
            stage.get("name") != expected_data
            or not stage.get("data")
            or any(d.get("name") != expected_data for d in stage["data"])
        ):
            raise ValueError("Source stage/data names differ from declared endpoint")
        if protocol == "cityscapes_to_railsem19":
            city = lookup.get((row["model"], "cityscapes"))
            if city is None or stage.get("init_from") != city["checkpoint"]:
                raise ValueError(
                    "City-to-Rail source must initialize from same-model approved City checkpoint"
                )
        elif stage.get("init_from") != "pretrained":
            raise ValueError("Single-source endpoint must start from recipe pretrained weights")
        configs[key] = cfg
        audits.append(
            {
                "model": row["model"],
                "protocol": protocol,
                "config": str(cfg_path),
                "config_sha256": digest(cfg_path),
                "checkpoint": row["checkpoint"],
                "recorded_sha256": row["recorded_sha256"],
                "space": expected_space,
                "endpoint_data": expected_data,
            }
        )
    jobs = plan.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("Plan has no jobs")
    matched = 0
    recipes = 0
    for job in jobs:
        protocol = job.get("protocol")
        if protocol not in JOB_SOURCES:
            raise ValueError("Unknown new RAD adaptation protocol")
        source_protocol = JOB_SOURCES[protocol]
        source = job.get("source_checkpoint")
        config = Path(job["config"])
        if (
            not HEX.fullmatch(job.get("config_sha256", ""))
            or digest(config) != job["config_sha256"]
        ):
            raise ValueError("New job config hash changed")
        cfg = yaml.safe_load(config.read_text())
        stages = cfg.get("stages")
        if not isinstance(stages, list) or len(stages) != 1:
            raise ValueError("Fresh adaptation needs exactly one new-dataset stage")
        if cfg.get("model", {}).get("checkpoint") not in APPROVED_RECIPE_CHECKPOINTS:
            raise ValueError("New job has an untracked model checkpoint override")
        reject_rad(cfg.get("model"), "new-job model initializer")
        if source_protocol is None:
            if source is not None or stages[0].get("init_from") != "pretrained":
                raise ValueError("Recipe adaptation must not reuse an old RAD checkpoint")
            recipes += 1
            continue
        expected = lookup.get((job.get("model"), source_protocol))
        if expected is None or not isinstance(source, dict):
            raise ValueError("Missing approved source endpoint for new job")
        if any(
            source.get(field) != expected[field]
            for field in ("model", "protocol", "checkpoint", "recorded_sha256", "config")
        ):
            raise ValueError("New job source differs from frozen manifest record")
        if stages[0].get("init_from") != expected["checkpoint"]:
            raise ValueError("Actual new-stage initializer differs from approved source")
        if cfg.get("model", {}).get("checkpoint") != configs[(job["model"], source_protocol)].get(
            "model", {}
        ).get("checkpoint"):
            raise ValueError("New job recipe model identifier differs from approved source")
        if cfg.get("model", {}).get("arch") != configs[(job["model"], source_protocol)].get(
            "model", {}
        ).get("arch"):
            raise ValueError("New job architecture differs from source architecture")
        matched += 1
    return {
        "schema_version": 1,
        "passed": True,
        "source_manifest": {"path": str(path), "sha256": manifest["sha256"]},
        "source_endpoints": len(sources),
        "new_jobs": len(jobs),
        "recipe_jobs": recipes,
        "transfer_jobs": matched,
        "source_configuration_audits": sorted(audits, key=lambda r: (r["model"], r["protocol"])),
        "checkpoint_bytes_hashed": False,
        "checkpoint_byte_verification": "Performed separately by runtime initialization and each training job",
    }
