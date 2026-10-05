"""Smoke-backed launch validation and the planner's frozen GPU/model/dataset inputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from scripts import validate_rtis_launch as validator

from helpers_gpu_policy import patch_live, uuid_of, write_campaign
from segmentary import gpu_policy

REPO = Path(__file__).resolve().parents[1]


def _smoke_state(name, uuid, **extra):
    return {
        "name": name,
        "status": "completed",
        "gpu_uuid": uuid,
        "collection": {"verified": True},
        **extra,
    }


def _pair(tmp_path, monkeypatch, *, smoke_allowed=(2, 3), compute_apps=(), owner="me"):
    main = tmp_path / "main"
    smoke = tmp_path / "smoke"
    write_campaign(main, jobs=["a"])
    write_campaign(smoke, allowed=smoke_allowed, smoke=True)
    (smoke / "state").mkdir()
    for name, gpu in (("x", 2), ("y", 3)):
        (smoke / "state" / f"{name}.json").write_text(json.dumps(_smoke_state(name, uuid_of(gpu))))
    patch_live(monkeypatch, compute_apps)
    monkeypatch.setattr(validator, "process_owner", lambda pid: owner)
    monkeypatch.setattr(validator.getpass, "getuser", lambda: "me")
    return main, smoke


def _run(main, smoke):
    sys.argv = ["validate", "--campaign", str(main), "--smoke-campaign", str(smoke)]
    validator.main()


def test_validation_passes_and_writes_launch_record(tmp_path, monkeypatch):
    main, smoke = _pair(tmp_path, monkeypatch, compute_apps=[(5, uuid_of(0))], owner="someone")
    _run(main, smoke)
    record = json.loads((main / "launch-validation.json").read_text())
    campaign = json.loads((main / "campaign.json").read_text())
    assert record["passed"] is True
    assert record["code_sha"] == "code"
    assert record["gpu_policy_sha256"] == campaign["gpu_policy_sha256"]
    assert record["smoke_campaign"] == str(smoke)
    assert record["smoke_jobs"] == ["x", "y"]
    assert record["smoke_gpu_uuids"] == [uuid_of(2), uuid_of(3)]
    assert record["forbidden_gpu_uuids_checked"] == [uuid_of(0), uuid_of(1)]
    assert "checked_at" in record


@pytest.mark.parametrize(
    "damage,match",
    [
        ("not_smoke", "smoke: true"),
        ("code_sha", "different code revision"),
        ("superset", "not a subset"),
        ("incomplete", "not completed"),
        ("unverified", "no verified collection"),
        ("forbidden_uuid", "outside the allowlist"),
        ("missing_uuid", "outside the allowlist"),
        ("own_process_on_forbidden", "forbidden GPUs"),
        ("no_states", "no job states"),
    ],
)
def test_validation_fails_closed(tmp_path, monkeypatch, damage, match):
    apps = [(5, uuid_of(1))] if damage == "own_process_on_forbidden" else []
    main, smoke = _pair(tmp_path, monkeypatch, compute_apps=apps)
    campaign = json.loads((smoke / "campaign.json").read_text())
    if damage == "not_smoke":
        campaign["smoke"] = False
    if damage == "code_sha":
        campaign["code_sha"] = "other"
    if damage == "superset":
        campaign["gpu_policy"] = gpu_policy.freeze(
            [1, 2], validator.gpu_policy.inventory(), "fake-host"
        )
    (smoke / "campaign.json").write_text(json.dumps(campaign))
    state = json.loads((smoke / "state/x.json").read_text())
    if damage == "incomplete":
        state["status"] = "collecting"
    if damage == "unverified":
        state["collection"] = {"verified": False}
    if damage == "forbidden_uuid":
        state["gpu_uuid"] = uuid_of(0)
    if damage == "missing_uuid":
        del state["gpu_uuid"]
    (smoke / "state/x.json").write_text(json.dumps(state))
    if damage == "no_states":
        for path in (smoke / "state").glob("*.json"):
            path.unlink()
    with pytest.raises(RuntimeError, match=match):
        _run(main, smoke)
    record = json.loads((main / "launch-validation.json").read_text())
    assert record["passed"] is False
    assert "code_sha" not in record


def _plan(tmp_path, monkeypatch, manifest, *extra):
    from scripts import plan_rtis_campaign as planner

    root = tmp_path / "dataset"
    root.mkdir(parents=True, exist_ok=True)
    (root / "splits.json").write_text(json.dumps({"_grouping_status": "ok"}))
    (tmp_path / "checkpoints.json").write_text("[]")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest))
    out = tmp_path / "out"
    jobs = []

    def fake_jobs(models, spec, lookup, root, out):
        jobs.extend(m["id"] for m in models)
        return []

    monkeypatch.setattr(planner, "build_jobs", fake_jobs)
    sys.argv = [
        "plan",
        "--manifest",
        str(manifest_path),
        "--checkpoints",
        str(tmp_path / "checkpoints.json"),
        "--dataset-root",
        str(root),
        "--out",
        str(out),
        *extra,
    ]
    planner.main()
    return json.loads((out / "plan.json").read_text()), jobs


BASE_MANIFEST = {
    "dataset_config": str(REPO / "configs/datasets/paul-test-rtis.yaml"),
    "model_catalog": str(REPO / "configs/campaigns/all_models_cityscapes_railsem19.yaml"),
    "target_steps": 4,
    "protocols": {},
    "seeds": [0],
}


def test_plan_requires_gpus_and_manifest(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        _plan(tmp_path, monkeypatch, BASE_MANIFEST)
    with pytest.raises(gpu_policy.GpuPolicyError):
        _plan(tmp_path, monkeypatch, BASE_MANIFEST, "--gpus", "2,2")
    from scripts import plan_rtis_campaign as planner

    sys.argv = ["plan", "--gpus", "2", "--checkpoints", "x", "--dataset-root", "y", "--out", "z"]
    with pytest.raises(SystemExit):
        planner.main()


def test_plan_freezes_allowlist_dataset_models_smoke_and_caveats(tmp_path, monkeypatch):
    plan, jobs = _plan(tmp_path, monkeypatch, BASE_MANIFEST, "--gpus", "9,2,5")
    assert plan["gpu_allowlist"] == [2, 5, 9]
    assert plan["dataset"] == "paul-test-rtis"
    assert plan["smoke"] is False
    assert len(jobs) == 36
    assert "Original recording groups need confirmation." in plan["caveats"]
    manifest = {
        **BASE_MANIFEST,
        "dataset": "rad_9_24_2026-paul",
        "smoke": True,
        "models": ["hf_auto_beit_base_ade", "smp_fpn_resnet50"],
        "caveats": ["Smoke only."],
    }
    plan, jobs = _plan(tmp_path / "second", monkeypatch, manifest, "--gpus", "3")
    assert plan["dataset"] == "rad_9_24_2026-paul"
    assert plan["smoke"] is True
    assert plan["caveats"] == ["Smoke only."]
    assert jobs == ["hf_auto_beit_base_ade", "smp_fpn_resnet50"]
    with pytest.raises(ValueError, match="unknown"):
        _plan(tmp_path / "third", monkeypatch, {**manifest, "models": ["nope"]}, "--gpus", "3")


TOP10 = [
    "eomt_large",
    "eomt_dinov3_large",
    "segformer_b5",
    "hrnet_w48_ocr",
    "segformer_b2",
    "upernet_convnext",
    "smp_deeplabv3plus_resnet101",
    "smp_fpn_resnet50",
    "smp_upernet_resnet101",
    "native_convnext_tiny_uper",
]


def test_rad_manifests_match_the_arms_and_smoke_covers_slow_families():
    catalog = yaml.safe_load(
        (REPO / "configs/campaigns/all_models_cityscapes_railsem19.yaml").read_text()
    )
    ids = {m["id"] for m in catalog["models"] if "alias_of" not in m}
    reference = yaml.safe_load(
        (REPO / "configs/campaigns/paul-test-rtis-fullstats.yaml").read_text()
    )
    arms = ("paul", "fixed-grouped")
    assert sorted(p.name for p in (REPO / "configs/campaigns").glob("rad_9_24_2026-*.yaml")) == [
        f"rad_9_24_2026-{a}.yaml" for a in ("fixed-grouped", "paul", "smoke")
    ]
    for arm in arms:
        spec = yaml.safe_load((REPO / f"configs/campaigns/rad_9_24_2026-{arm}.yaml").read_text())
        assert spec["name"] == spec["dataset"] == f"rad_9_24_2026-{arm}"
        assert spec["dataset_config"] == f"configs/datasets/rad_9_24_2026-{arm}.yaml"
        assert spec["seeds"] == [0]
        assert spec["publisher"] is False
        assert spec["protocols"] == reference["protocols"]
        assert spec["collection_contract"] == "rtis-full-statistics-v1"
        assert spec["selection_metric"] == "val_iou/mud-pumping"
        for key in ("target_steps", "batch_size", "accumulation", "validation_interval"):
            assert spec[key] == reference[key]
        assert "smoke" not in spec and "gpus" not in spec
        assert spec["models"] == TOP10
    smoke = yaml.safe_load((REPO / "configs/campaigns/rad_9_24_2026-smoke.yaml").read_text())
    assert smoke["smoke"] is True
    assert smoke["dataset_config"] == "configs/datasets/rad_9_24_2026-paul.yaml"
    assert smoke["target_steps"] == 40
    assert smoke["validation_interval"] == smoke["checkpoint_interval"] == 20
    assert set(smoke["protocols"]) == {"rtis_only", "cityscapes_to_rtis"}
    assert set(TOP10) <= ids
    assert {"smp_fpn_resnet50", "eomt_dinov3_large", "hrnet_w48_ocr"} == set(smoke["models"])
    assert set(smoke["models"]) <= set(TOP10)
