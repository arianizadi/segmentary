"""Provenance verification is independent of checkpoint size and needs no GPU."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from scripts import verify_rad_initializers as guard


def setup_plan(tmp_path):
    sources = []
    for protocol in ["cityscapes", "railsem19", "cityscapes_to_railsem19"]:
        endpoint = "cityscapes" if protocol == "cityscapes" else "railsem19"
        checkpoint = tmp_path / (protocol + ".ckpt")
        cfg = {
            "space": "cityscapes19" if protocol == "cityscapes" else "rail_union",
            "model": {"arch": "model", "checkpoint": None},
            "stages": [
                {
                    "name": endpoint,
                    "data": [{"name": endpoint, "root": "/datasets/" + endpoint}],
                    "init_from": str(tmp_path / "cityscapes.ckpt")
                    if protocol == "cityscapes_to_railsem19"
                    else "pretrained",
                }
            ],
        }
        path = tmp_path / (protocol + ".yaml")
        path.write_text(yaml.safe_dump(cfg))
        sources.append(
            {
                "model": "model",
                "protocol": protocol,
                "config": str(path),
                "checkpoint": str(checkpoint),
                "recorded_sha256": "a" * 64,
            }
        )
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps(sources))
    jobs = []
    for protocol, sourceprotocol in guard.JOB_SOURCES.items():
        source = next((r for r in sources if r["protocol"] == sourceprotocol), None)
        path = tmp_path / ("adapt-" + protocol + ".yaml")
        path.write_text(
            yaml.safe_dump(
                {
                    "space": "paul-test-rtis",
                    "model": {"arch": "model", "checkpoint": None},
                    "stages": [
                        {
                            "name": "rtis",
                            "data": [{"name": "new-rad"}],
                            "init_from": "pretrained" if source is None else source["checkpoint"],
                        }
                    ],
                }
            )
        )
        jobs.append(
            {
                "name": protocol,
                "model": "model",
                "protocol": protocol,
                "config": str(path),
                "config_sha256": guard.digest(path),
                "source_checkpoint": source,
            }
        )
    return {
        "source_manifest": {"path": str(manifest), "sha256": guard.digest(manifest)},
        "jobs": jobs,
    }


def test_fresh_sources_verify_without_reading_checkpoint_files(tmp_path):
    plan = setup_plan(tmp_path)
    report = guard.verify_initializers(plan)
    assert report["passed"] and report["source_endpoints"] == 3 and report["new_jobs"] == 4
    assert report["checkpoint_bytes_hashed"] is False
    assert report == guard.verify_initializers(plan)


def test_manifest_cannot_change_after_freezing(tmp_path):
    plan = setup_plan(tmp_path)
    Path(plan["source_manifest"]["path"]).write_text("[]")
    with pytest.raises(ValueError, match="manifest hash changed"):
        guard.verify_initializers(plan)


@pytest.mark.parametrize("damage", ["rad_space", "rad_data", "rad_initializer", "wrong_chain"])
def test_forged_source_config_is_rejected(tmp_path, damage):
    plan = setup_plan(tmp_path)
    source = plan["jobs"][1]["source_checkpoint"]
    p = Path(source["config"])
    c = yaml.safe_load(p.read_text())
    if damage == "rad_space":
        c["space"] = "paul-test-rtis"
    elif damage == "rad_data":
        c["stages"][0]["data"][0]["root"] = "/datasets/rad_9_24_2026"
    elif damage == "rad_initializer":
        c["stages"][0]["init_from"] = "/old/paul-test-rtis/last.ckpt"
    else:
        c["stages"][0]["init_from"] = "/wrong/last.ckpt"
    p.write_text(yaml.safe_dump(c))
    with pytest.raises(ValueError):
        guard.verify_initializers(plan)


def test_job_cannot_masquerade_old_checkpoint_as_city_source(tmp_path):
    plan = setup_plan(tmp_path)
    plan["jobs"][1]["source_checkpoint"] = {
        **plan["jobs"][1]["source_checkpoint"],
        "checkpoint": "/old/rad/last.ckpt",
    }
    with pytest.raises(ValueError, match="differs from frozen manifest"):
        guard.verify_initializers(plan)


def test_recipe_job_cannot_load_local_rad_checkpoint(tmp_path):
    plan = setup_plan(tmp_path)
    j = plan["jobs"][0]
    p = Path(j["config"])
    c = yaml.safe_load(p.read_text())
    c["model"]["checkpoint"] = "/old/rad/last.ckpt"
    p.write_text(yaml.safe_dump(c))
    j["config_sha256"] = guard.digest(p)
    with pytest.raises(ValueError, match="untracked model checkpoint"):
        guard.verify_initializers(plan)


def test_known_public_recipe_model_identifier_is_allowed(tmp_path):
    plan = setup_plan(tmp_path)
    paths = {Path(j["config"]) for j in plan["jobs"]}
    paths.update(
        Path(j["source_checkpoint"]["config"]) for j in plan["jobs"] if j["source_checkpoint"]
    )
    for path in paths:
        cfg = yaml.safe_load(path.read_text())
        cfg["model"]["checkpoint"] = "nvidia/mit-b2"
        path.write_text(yaml.safe_dump(cfg))
    for job in plan["jobs"]:
        job["config_sha256"] = guard.digest(job["config"])
    assert guard.verify_initializers(plan)["passed"]


def test_duplicate_source_endpoint_is_rejected_even_with_new_manifest_hash(tmp_path):
    plan = setup_plan(tmp_path)
    path = Path(plan["source_manifest"]["path"])
    rows = json.loads(path.read_text())
    rows.append(rows[0])
    path.write_text(json.dumps(rows))
    plan["source_manifest"]["sha256"] = guard.digest(path)
    with pytest.raises(ValueError, match="Duplicate model/protocol"):
        guard.verify_initializers(plan)


def test_copied_city_initializer_alias_requires_matching_content_hash(tmp_path):
    plan = setup_plan(tmp_path)
    city = plan["jobs"][1]["source_checkpoint"]
    payload = b"approved city checkpoint"
    Path(city["checkpoint"]).write_bytes(payload)
    manifest = Path(plan["source_manifest"]["path"])
    rows = json.loads(manifest.read_text())
    rows[0]["recorded_sha256"] = guard.digest(city["checkpoint"])
    manifest.write_text(json.dumps(rows))
    plan["source_manifest"]["sha256"] = guard.digest(manifest)
    plan["jobs"][1]["source_checkpoint"] = rows[0]
    chain_config = Path(rows[2]["config"])
    cfg = yaml.safe_load(chain_config.read_text())
    alias = tmp_path / "copied-city.ckpt"
    alias.write_bytes(payload)
    cfg["stages"][0]["init_from"] = str(alias)
    chain_config.write_text(yaml.safe_dump(cfg))
    audit = guard.verify_initializers(plan)
    chain = next(
        x
        for x in audit["source_configuration_audits"]
        if x["protocol"] == "cityscapes_to_railsem19"
    )["chain_initializer"]
    assert chain == {
        "path": str(alias),
        "sha256": rows[0]["recorded_sha256"],
        "path_matches_manifest": False,
        "alias_bytes_hashed": True,
    }
    assert audit["chain_alias_files_hashed"] == 1


@pytest.mark.parametrize("damage", ["wrong_bytes", "missing", "rad_path"])
def test_city_initializer_alias_refuses_mismatch_missing_or_rad_path(tmp_path, damage):
    alias = tmp_path / ("old-rad/last.ckpt" if damage == "rad_path" else "alias.ckpt")
    if damage != "missing":
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.write_bytes(b"wrong")
    city = {"checkpoint": str(tmp_path / "approved.ckpt"), "recorded_sha256": "a" * 64}
    with pytest.raises(ValueError):
        guard.verify_chain_initializer(str(alias), city, {})


def qualified_plan(tmp_path):
    plan = setup_plan(tmp_path)
    manifest = Path(plan["source_manifest"]["path"])
    rows = json.loads(manifest.read_text())
    chain = rows[2]
    raw = tmp_path / "historical-city/cityscapes/last.ckpt"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw historic City weights")
    citycfg = Path(rows[0]["config"])
    cfg = yaml.safe_load(citycfg.read_text())
    receipt = raw.parent / "results.json"
    receipt.write_text(
        json.dumps({"stage": "cityscapes", "name": "model--cityscapes", "config": cfg})
    )
    path = Path(chain["config"])
    transfer = yaml.safe_load(path.read_text())
    transfer["stages"][0]["init_from"] = str(raw)
    path.write_text(yaml.safe_dump(transfer))
    chain["city_initializer"] = {
        "model": "model",
        "protocol": "cityscapes",
        "declared_init_from": str(raw),
        "checkpoint": str(raw),
        "recorded_sha256": guard.digest(raw),
        "config": str(citycfg),
        "config_sha256": guard.digest(citycfg),
        "evidence": [
            {"kind": "city_training_result", "path": str(receipt), "sha256": guard.digest(receipt)}
        ],
    }
    manifest.write_text(json.dumps(rows))
    plan["source_manifest"]["sha256"] = guard.digest(manifest)
    return plan, manifest, rows


def test_historical_raw_city_variant_needs_pinned_semantic_training_proof(tmp_path):
    plan, _, _ = qualified_plan(tmp_path)
    audit = guard.verify_initializers(plan)
    chain = next(
        x
        for x in audit["source_configuration_audits"]
        if x["protocol"] == "cityscapes_to_railsem19"
    )["chain_initializer"]
    assert (
        chain["qualified_historical_city_predecessor"]
        and chain["evidence"][0]["kind"] == "city_training_result"
    )
    assert audit["chain_alias_files_hashed"] == 1


@pytest.mark.parametrize(
    "damage",
    ["checkpoint_hash", "city_data", "receipt_changed", "missing_proof", "wrong_model_stage"],
)
def test_qualified_historical_source_fails_closed(tmp_path, damage):
    plan, manifest, rows = qualified_plan(tmp_path)
    lineage = rows[2]["city_initializer"]
    if damage == "checkpoint_hash":
        lineage["recorded_sha256"] = "f" * 64
    elif damage == "city_data":
        p = Path(lineage["config"])
        cfg = yaml.safe_load(p.read_text())
        cfg["stages"][0]["data"][0]["name"] = "rtis"
        p.write_text(yaml.safe_dump(cfg))
        lineage["config_sha256"] = guard.digest(p)
    elif damage == "receipt_changed":
        Path(lineage["evidence"][0]["path"]).write_text("{}")
    elif damage == "missing_proof":
        lineage["evidence"] = []
    else:
        p = Path(lineage["evidence"][0]["path"])
        r = json.loads(p.read_text())
        r["stage"] = "railsem19"
        p.write_text(json.dumps(r))
        lineage["evidence"][0]["sha256"] = guard.digest(p)
    manifest.write_text(json.dumps(rows))
    plan["source_manifest"]["sha256"] = guard.digest(manifest)
    with pytest.raises(ValueError):
        guard.verify_initializers(plan)


def inventory_plan(tmp_path):
    plan, manifest, rows = qualified_plan(tmp_path)
    chain = rows[2]
    lineage = chain["city_initializer"]
    city = tmp_path / "model--cityscapes--seed-0/attempt-001/cityscapes/last.ckpt"
    city.parent.mkdir(parents=True)
    city.write_bytes(Path(lineage["checkpoint"]).read_bytes())
    lineage["checkpoint"] = str(city)
    declared = "/dependency/model--cityscapes--seed-0/last.ckpt"
    lineage["declared_init_from"] = declared
    source = Path(chain["config"])
    cfg = yaml.safe_load(source.read_text())
    cfg["stages"][0]["init_from"] = declared
    source.write_text(yaml.safe_dump(cfg))
    result_path = tmp_path / "full-transfer-result.json"
    fullcfg = {**cfg, "stages": [{**cfg["stages"][0], "init_from": str(city)}]}
    result_path.write_text(json.dumps({"config": fullcfg}))
    overlay = tmp_path / "original-transfer.yaml"
    overlay.write_text(yaml.safe_dump(fullcfg))
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "model": "model",
                        "city_checkpoint_path": str(city),
                        "city_checkpoint_sha256": lineage["recorded_sha256"],
                        "checkpoint_sha256": chain["recorded_sha256"],
                        "config_path": overlay.name,
                        "config_sha256": guard.digest(overlay),
                        "result_path": result_path.name,
                        "result_sha256": guard.digest(result_path),
                    }
                ]
            }
        )
    )
    lineage["evidence"] = [
        {"kind": "transfer_inventory", "path": str(inventory), "sha256": guard.digest(inventory)}
    ]
    manifest.write_text(json.dumps(rows))
    plan["source_manifest"]["sha256"] = guard.digest(manifest)
    return plan, manifest, rows, inventory


def test_placeholder_requires_semantically_bound_transfer_receipt(tmp_path):
    plan, _, _, _ = inventory_plan(tmp_path)
    assert guard.verify_initializers(plan)["passed"]


def test_placeholder_receipt_cannot_bind_different_city_bytes(tmp_path):
    plan, manifest, rows, inventory = inventory_plan(tmp_path)
    r = json.loads(inventory.read_text())
    r["models"][0]["city_checkpoint_sha256"] = "f" * 64
    inventory.write_text(json.dumps(r))
    rows[2]["city_initializer"]["evidence"][0]["sha256"] = guard.digest(inventory)
    manifest.write_text(json.dumps(rows))
    plan["source_manifest"]["sha256"] = guard.digest(manifest)
    with pytest.raises(ValueError, match="does not bind"):
        guard.verify_initializers(plan)
