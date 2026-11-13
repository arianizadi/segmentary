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
