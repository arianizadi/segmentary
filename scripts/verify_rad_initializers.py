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
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def reject_rad(value, label):
    if isinstance(value, dict):
        for child in value.values():
            reject_rad(child, label)
    elif isinstance(value, (list, tuple)):
        for child in value:
            reject_rad(child, label)
    elif isinstance(value, str) and FORBIDDEN.search(value):
        raise ValueError(f"RAD/RTIS provenance is forbidden in source {label}")


def verify_chain_initializer(actual, city, cache):
    """A path alias is valid only when its actual bytes match the approved City endpoint."""
    if not isinstance(actual, str) or not Path(actual).is_absolute():
        raise ValueError("City-to-Rail initializer must be an absolute checkpoint path")
    reject_rad(actual, "City-to-Rail initializer")
    path = Path(actual)
    reject_rad(str(path.resolve()), "resolved City-to-Rail initializer")
    if actual == city["checkpoint"]:
        return {
            "path": actual,
            "sha256": city["recorded_sha256"],
            "path_matches_manifest": True,
            "alias_bytes_hashed": False,
        }
    if not path.is_file():
        raise ValueError(f"City-to-Rail alias is not an existing file: {actual}")
    before = path.stat()
    identity = (
        str(path.resolve()),
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if identity not in cache:
        cache[identity] = digest(path)
        after = path.stat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("City-to-Rail alias changed while it was hashed")
    actual_sha = cache[identity]
    if actual_sha != city["recorded_sha256"]:
        raise ValueError(f"City-to-Rail alias bytes differ from approved City checkpoint: {actual}")
    return {
        "path": actual,
        "sha256": actual_sha,
        "path_matches_manifest": False,
        "alias_bytes_hashed": True,
    }


def verify_qualified_city(lineage, row, stage, source_cfg, cache):
    """Verify an explicitly recorded historical City predecessor, including its receipt."""
    if (
        not isinstance(lineage, dict)
        or lineage.get("model") != row["model"]
        or lineage.get("protocol") != "cityscapes"
    ):
        raise ValueError("Qualified City predecessor has wrong model/protocol")
    if lineage.get("declared_init_from") != stage.get("init_from"):
        raise ValueError("Qualified predecessor does not match the declared historical initializer")
    reject_rad(lineage.get("declared_init_from"), "qualified declared initializer")
    for field in ("checkpoint", "config"):
        if not isinstance(lineage.get(field), str) or not Path(lineage[field]).is_absolute():
            raise ValueError("Qualified City predecessor requires absolute checkpoint/config paths")
        reject_rad(lineage[field], "qualified City " + field)
        reject_rad(str(Path(lineage[field]).resolve()), "qualified resolved City " + field)
    if not HEX.fullmatch(lineage.get("recorded_sha256", "")) or not HEX.fullmatch(
        lineage.get("config_sha256", "")
    ):
        raise ValueError("Qualified City predecessor requires checkpoint/config SHA-256")
    config_path = Path(lineage["config"])
    if digest(config_path) != lineage["config_sha256"]:
        raise ValueError("Qualified City configuration hash changed")
    cfg = yaml.safe_load(config_path.read_text())
    stages = cfg.get("stages")
    if cfg.get("space") != "cityscapes19" or not isinstance(stages, list) or len(stages) != 1:
        raise ValueError("Qualified predecessor is not a resolved Cityscapes source")
    city_stage = stages[0]
    if (
        city_stage.get("name") != "cityscapes"
        or city_stage.get("init_from") != "pretrained"
        or not city_stage.get("data")
        or any(d.get("name") != "cityscapes" for d in city_stage["data"])
    ):
        raise ValueError("Qualified City source must have only pretrained Cityscapes training")
    reject_rad(stages, "qualified City stages")
    reject_rad(cfg.get("model"), "qualified City model")
    if cfg.get("model", {}).get("checkpoint") not in APPROVED_RECIPE_CHECKPOINTS or cfg.get(
        "model", {}
    ).get("arch") != source_cfg.get("model", {}).get("arch"):
        raise ValueError("Qualified City architecture/recipe is not the same source model")
    # A qualification always verifies the actual historical input bytes, including
    # valid raw-vs-BN-recalibrated City variants, rather than trusting a filename.
    checkpoint = Path(lineage["checkpoint"])
    if not checkpoint.is_file():
        raise ValueError("Qualified City checkpoint is not a file")
    before = checkpoint.stat()
    identity = (
        str(checkpoint.resolve()),
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if identity not in cache:
        cache[identity] = digest(checkpoint)
    after = checkpoint.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError("Qualified City checkpoint changed while hashing")
    if cache[identity] != lineage["recorded_sha256"]:
        raise ValueError("Qualified City checkpoint SHA-256 differs")
    evidence = lineage.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Qualified City predecessor has no semantic training receipt")
    receipts = []
    for proof in evidence:
        path = Path(proof["path"])
        if not HEX.fullmatch(proof.get("sha256", "")) or digest(path) != proof["sha256"]:
            raise ValueError("Qualified City receipt hash changed")
        data = json.loads(path.read_text())
        if proof.get("kind") == "city_training_result":
            record_cfg = data.get("config", {})
            if data.get("stage") != "cityscapes" or not str(data.get("name", "")).startswith(
                row["model"] + "--cityscapes"
            ):
                raise ValueError("Receipt does not identify this model's City training")
            if (
                record_cfg.get("space") != "cityscapes19"
                or record_cfg.get("model", {}).get("arch") != cfg.get("model", {}).get("arch")
                or record_cfg.get("stages") != stages
            ):
                raise ValueError(
                    "City training receipt configuration differs from qualified City source"
                )
            if path.parent.resolve() != checkpoint.parent.resolve():
                raise ValueError(
                    "City training receipt does not accompany the qualified checkpoint"
                )
        elif proof.get("kind") == "transfer_inventory":
            entries = [item for item in data.get("models", []) if item.get("model") == row["model"]]
            if len(entries) != 1:
                raise ValueError("Transfer receipt does not uniquely identify the model")
            entry = entries[0]
            if (
                entry.get("city_checkpoint_path") != lineage["checkpoint"]
                or entry.get("city_checkpoint_sha256") != lineage["recorded_sha256"]
                or entry.get("checkpoint_sha256") != row["recorded_sha256"]
            ):
                raise ValueError(
                    "Transfer receipt does not bind the qualified City input to this Rail endpoint"
                )
            if row["model"] + "--cityscapes--seed-0" not in Path(lineage["checkpoint"]).parts:
                raise ValueError(
                    "Transfer receipt City checkpoint does not identify the expected City job"
                )
            result_path = path.parent / entry["result_path"]
            config_file = path.parent / entry["config_path"]
            if digest(result_path) != entry.get("result_sha256") or digest(
                config_file
            ) != entry.get("config_sha256"):
                raise ValueError("Transfer receipt's bound config/result artifacts changed")
            result = json.loads(result_path.read_text())
            transfer_cfg = result.get("config", {})
            if transfer_cfg.get("space") != "rail_union" or transfer_cfg.get("model", {}).get(
                "arch"
            ) != source_cfg.get("model", {}).get("arch"):
                raise ValueError("Bound transfer result has wrong taxonomy/model")
            transfer_stages = transfer_cfg.get("stages", [])
            if (
                len(transfer_stages) != 1
                or transfer_stages[0].get("name") != "railsem19"
                or transfer_stages[0].get("init_from") != lineage["checkpoint"]
            ):
                raise ValueError(
                    "Bound transfer result does not name the qualified City initializer"
                )
            reject_rad(transfer_stages, "bound transfer stages")
        else:
            raise ValueError("Unknown qualified City receipt kind")
        receipts.append({"kind": proof["kind"], "path": str(path), "sha256": proof["sha256"]})
    return {
        "declared_init_from": lineage["declared_init_from"],
        "path": lineage["checkpoint"],
        "sha256": lineage["recorded_sha256"],
        "qualified_historical_city_predecessor": True,
        "city_config": str(config_path),
        "city_config_sha256": lineage["config_sha256"],
        "evidence": receipts,
        "alias_bytes_hashed": True,
    }


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
    alias_hash_cache = {}
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
            if city is None:
                raise ValueError("City-to-Rail source lacks a same-model approved City checkpoint")
            chain = (
                verify_qualified_city(row["city_initializer"], row, stage, cfg, alias_hash_cache)
                if row.get("city_initializer") is not None
                else verify_chain_initializer(stage.get("init_from"), city, alias_hash_cache)
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
                "chain_initializer": chain if protocol == "cityscapes_to_railsem19" else None,
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
        "checkpoint_bytes_hashed": bool(alias_hash_cache),
        "chain_alias_files_hashed": len(alias_hash_cache),
        "checkpoint_byte_verification": "Performed separately by runtime initialization and each training job",
    }
