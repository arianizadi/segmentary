"""Independent CPU checks for frozen paper requests and profiling entry points."""

import contextlib
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from scripts import evaluate_rad_test as evaluator
from scripts import profile_rad_test as profiler
from scripts import rad_test_contract as contract
from scripts import run_rad_test as runner

from helpers_gpu_policy import make_policy
from segmentary import eval as eval_module
from segmentary.utils import provenance


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(bundle):
    write(bundle.request_path, bundle.request)
    bundle.campaign["request_sha256"] = sha(bundle.request_path)
    write(bundle.campaign_path, bundle.campaign)


def save_training(bundle):
    write(bundle.training_path, bundle.training)
    bundle.request["training_campaign_sha256"] = sha(bundle.training_path)
    freeze(bundle)


def save_plan(bundle):
    write(bundle.plan_path, bundle.plan)
    bundle.request["training_plan_sha256"] = sha(bundle.plan_path)
    bundle.training["plan_sha256"] = sha(bundle.plan_path)
    save_training(bundle)


@pytest.fixture
def paper_request(tmp_path):
    models = [f"model-{index}" for index in range(8)]
    arms = [
        "rtis_only",
        "cityscapes_to_rtis",
        "railsem19_to_rtis",
        "cityscapes_to_railsem19_to_rtis",
    ]
    protocol = {
        "models": models,
        "seeds": [0, 1, 2],
        "headline_protocol": "railsem19_to_rtis",
        "primary_metric": "pixel_pooled_miou",
        "qualitative_seed": 0,
        "qualitative_keys": ["scene/a"],
        "failure_rule": "fixed finite-loss and infrastructure rule",
        "split_policy": "255/0/59",
    }
    protocol_sha = hashlib.sha256(
        json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    jobs, planned = [], []
    for model in models:
        for arm in arms:
            for seed in range(3):
                name = f"{model}--{arm}--seed-{seed}"
                config = tmp_path / "configs" / f"{name}.yaml"
                config.parent.mkdir(exist_ok=True)
                config.write_text(name)
                checkpoint = tmp_path / "checkpoints" / name / "last.ckpt"
                checkpoint.parent.mkdir(parents=True)
                checkpoint.write_bytes(name.encode())
                job = {
                    "name": name,
                    "model": model,
                    "protocol": arm,
                    "seed": seed,
                    "config": str(config),
                    "config_sha256": sha(config),
                }
                planned.append(job.copy())
                state_path = tmp_path / "states" / f"{name}.json"
                write(
                    state_path,
                    {
                        "name": name,
                        "status": "completed",
                        "config_sha256": job["config_sha256"],
                        "code_sha": "training-code",
                        "final_step": 4000,
                        "checkpoints": {
                            "final": {
                                "path": str(checkpoint),
                                "sha256": sha(checkpoint),
                                "global_step": 4000,
                            }
                        },
                        "collection": {
                            "verified": True,
                            "contract": "rtis-final-train-statistics-v2",
                        },
                    },
                )
                jobs.append(
                    {
                        **job,
                        "state_path": str(state_path),
                        "state_sha256": sha(state_path),
                        "final_checkpoint": str(checkpoint),
                        "final_checkpoint_sha256": sha(checkpoint),
                    }
                )
    plan = {
        "jobs": planned,
        "target_steps_per_job": 4000,
        "research_protocol": protocol,
        "research_protocol_sha256": protocol_sha,
        "split_sha256": "split",
        "dataset_final_fit": {"parent_split_sha256": "parent"},
        "collection_contract": "rtis-final-train-statistics-v2",
        "primary_checkpoint": "final",
        "validation_enabled": False,
    }
    training = {
        "code_sha": "training-code",
        "research_protocol": protocol,
        "research_protocol_sha256": protocol_sha,
        "split_sha256": "split",
        "dataset_audit_sha256": "samples",
        "dataset_final_fit": plan["dataset_final_fit"],
        "collection_contract": plan["collection_contract"],
        "primary_checkpoint": "final",
        "validation_enabled": False,
        "launch_requirements": {"expected_gpu_allowlist": list(range(10))},
    }
    policy = make_policy(tuple(range(10)))
    campaign = {
        "schema_version": 2,
        "code_sha": "evaluation-code",
        "gpu_policy": policy,
        "gpu_policy_sha256": runner.gpu_policy.policy_sha256(policy),
        "authorized_gpu_indices": list(range(10)),
    }
    bundle = SimpleNamespace(
        plan=plan,
        training=training,
        campaign=campaign,
        plan_path=tmp_path / "training-plan.json",
        training_path=tmp_path / "training-campaign.json",
        request_path=tmp_path / "request.json",
        campaign_path=tmp_path / "paper/campaign.json",
    )
    bundle.request = {
        "schema_version": 2,
        "test_evaluation_authorized": True,
        "campaign_json": str(bundle.campaign_path),
        "training_plan": str(bundle.plan_path),
        "training_campaign": str(bundle.training_path),
        "training_code_sha": "training-code",
        "research_protocol": protocol,
        "split_sha256": "split",
        "samples_sha256": "samples",
        "dataset_root": str(tmp_path / "dataset"),
        "output_root": str(tmp_path / "test-output"),
        "class_names": [f"class-{index}" for index in range(21)],
        "benchmark_gpu": 0,
        "jobs": jobs,
    }
    save_plan(bundle)
    return bundle


def test_complete_four_recipe_eight_model_three_seed_request_is_accepted(paper_request):
    assert len(paper_request.request["jobs"]) == 96
    assert contract.validate_v2(paper_request.request, paper_request.campaign) == set(range(10))
    assert set(
        runner.gpu_policy.allowed_indices(runner.validate_request(paper_request.request_path)[1])
    ) == set(range(10))


@pytest.mark.parametrize(
    "damage", ["partial", "duplicate", "wrong_model", "wrong_arm", "wrong_seed"]
)
def test_requested_matrix_must_equal_every_prespecified_run(paper_request, damage):
    jobs = paper_request.request["jobs"]
    if damage == "partial":
        jobs.pop()
    elif damage == "duplicate":
        jobs.append(jobs[0].copy())
    else:
        field = {"wrong_model": "model", "wrong_arm": "protocol", "wrong_seed": "seed"}[damage]
        jobs[0][field] = "changed"
    with pytest.raises(ValueError):
        contract.validate_v2(paper_request.request, paper_request.campaign)


@pytest.mark.parametrize(
    "damage", ["stale_bytes", "unbound_plan", "protocol", "protocol_hash", "split", "final_fit"]
)
def test_plan_campaign_and_protocol_identities_remain_bound(paper_request, damage):
    b = paper_request
    if damage == "stale_bytes":
        b.plan_path.write_text(b.plan_path.read_text() + "\n")
    elif damage == "unbound_plan":
        b.training["plan_sha256"] = "other-plan"
        save_training(b)
    else:
        field = {
            "protocol": "research_protocol",
            "protocol_hash": "research_protocol_sha256",
            "split": "split_sha256",
            "final_fit": "dataset_final_fit",
        }[damage]
        b.training[field] = "changed"
        save_training(b)
    with pytest.raises(ValueError):
        contract.validate_v2(b.request, b.campaign)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "training"),
        ("final_step", 3999),
        ("name", "another-job"),
        ("config_sha256", "wrong"),
        ("code_sha", "other-code"),
        ("global_step", 3999),
    ],
)
def test_rehashed_incomplete_or_mismatched_state_is_rejected(paper_request, field, value):
    job = paper_request.request["jobs"][0]
    path = Path(job["state_path"])
    state = json.loads(path.read_text())
    if field == "global_step":
        state["checkpoints"]["final"][field] = value
    else:
        state[field] = value
    write(path, state)
    job["state_sha256"] = sha(path)
    with pytest.raises(ValueError, match="fixed-budget"):
        contract.validate_v2(paper_request.request, paper_request.campaign)


def test_changed_state_bytes_cannot_pass_frozen_request(paper_request):
    Path(paper_request.request["jobs"][0]["state_path"]).write_text("changed")
    with pytest.raises(ValueError, match="SHA-256"):
        contract.validate_v2(paper_request.request, paper_request.campaign)


@pytest.mark.parametrize("damage", ["missing_verified", "unverified", "wrong_contract"])
def test_completed_state_requires_verified_matching_collection(paper_request, damage):
    job = paper_request.request["jobs"][0]
    path = Path(job["state_path"])
    state = json.loads(path.read_text())
    if damage == "missing_verified":
        state["collection"].pop("verified")
    elif damage == "unverified":
        state["collection"]["verified"] = False
    else:
        state["collection"]["contract"] = "rtis-full-statistics-v1"
    write(path, state)
    job["state_sha256"] = sha(path)
    with pytest.raises(ValueError, match="fixed-budget"):
        contract.validate_v2(paper_request.request, paper_request.campaign)


@pytest.mark.parametrize("head,dirty", [("other", False), ("evaluation-code", True)])
def test_evaluation_code_must_match_clean_frozen_head(monkeypatch, head, dirty):
    monkeypatch.setattr(provenance, "git_sha", lambda *a: (head, dirty))
    with pytest.raises(ValueError, match="clean HEAD"):
        contract.verify_evaluation_code({"code_sha": "evaluation-code"}, Path.cwd())


def test_v2_child_accepts_explicit_gpu_four_and_checks_current_code(paper_request, monkeypatch):
    b = paper_request
    monkeypatch.setattr(provenance, "git_sha", lambda *a: ("evaluation-code", False))
    for key, value in runner.gpu_policy.child_env(
        {}, b.campaign["gpu_policy"], 4, b.campaign_path
    ).items():
        monkeypatch.setenv(key, value)
    evaluator.validate_request(b.request_path, b.request["jobs"][0]["name"], 4)
    monkeypatch.setattr(provenance, "git_sha", lambda *a: ("evaluation-code", True))
    with pytest.raises(ValueError, match="clean HEAD"):
        evaluator.validate_request(b.request_path, b.request["jobs"][0]["name"], 4)


def test_legacy_parent_and_child_keep_seven_gpu_authorization(paper_request, monkeypatch):
    b = paper_request
    b.request["schema_version"] = 1
    freeze(b)
    for key, value in runner.gpu_policy.child_env(
        {}, b.campaign["gpu_policy"], 4, b.campaign_path
    ).items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="exceeds"):
        runner.validate_request(b.request_path)
    with pytest.raises(ValueError):
        evaluator.validate_request(b.request_path, b.request["jobs"][0]["name"], 4)
    allowed = (0, 1, 2, 3, 7, 8, 9)
    b.campaign["gpu_policy"] = make_policy(allowed)
    b.campaign["gpu_policy_sha256"] = runner.gpu_policy.policy_sha256(b.campaign["gpu_policy"])
    freeze(b)
    assert set(
        runner.gpu_policy.allowed_indices(runner.validate_request(b.request_path)[1])
    ) == set(allowed)


@pytest.mark.parametrize("heights", [(3,), (3, 33)])
def test_native_pipeline_profile_restores_narrow_shapes_on_cpu(tmp_path, monkeypatch, heights):
    import segmentary.performance as performance

    samples = [{"key": f"narrow-{height}", "width": 5, "height": height} for height in heights]
    monkeypatch.setattr(profiler.test_eval, "validate_dataset", lambda *a: samples)
    monkeypatch.setattr(
        profiler.test_eval,
        "load_test_image",
        lambda root, sample, n: (
            np.zeros((sample["height"], 5, 3), np.uint8),
            np.zeros((sample["height"], 5), np.uint8),
        ),
    )
    monkeypatch.setattr(torch.Tensor, "cuda", lambda self: self)
    monkeypatch.setattr(torch, "autocast", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setattr(torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    monkeypatch.setattr(torch.cuda, "reset_peak_memory_stats", lambda: None)
    monkeypatch.setattr(torch.cuda, "max_memory_reserved", lambda: 100)
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda: 80)
    monkeypatch.setattr(performance, "process_gpu_used_bytes", lambda *a: 120)
    import segmentary.engine.inference as infer_module

    sizes = []

    def inference(model, image, *args):
        sizes.append(tuple(image.shape[-2:]))
        return torch.zeros((1, 2, *image.shape[-2:]))

    monkeypatch.setattr(infer_module, "inference", inference)
    from segmentary.config import AugConfigSpec

    cfg = SimpleNamespace(
        aug=AugConfigSpec(),
        eval=SimpleNamespace(sliding_window=True, window=(32, 32), stride=(32, 32)),
    )
    result = profiler.native_pipeline_profile(
        object(), cfg, {"dataset_root": str(tmp_path)}, ["a", "b"], "GPU-fake"
    )
    expected_shapes = [((height + 31) // 32 * 32, 32) for height in heights]
    assert sizes == [shape for shape in expected_shapes for _ in range(2)] + expected_shapes
    assert result["contract"]["warmup_padded_shapes_hw"] == [
        list(shape) for shape in expected_shapes
    ]
    assert result["contract"]["measured_images"] == len(heights)
    assert result["measurements"]["per_image"][0]["width"] == 5
    assert result["measurements"]["peak_allocated_bytes"] == 80


def test_eval_cli_stride_padding_excludes_added_pixels(tmp_path, monkeypatch, taxonomy_root):
    import yaml

    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "name": "narrow",
                "space": "rail_union",
                "taxonomy_root": str(taxonomy_root),
                "model": {"arch": "segformer_b0"},
                "eval": {"num_workers": 0, "sliding_window": False},
                "stages": [{"name": "train", "data": [{"name": "cityscapes", "root": "/unused"}]}],
            }
        )
    )
    checkpoint = tmp_path / "last.ckpt"
    checkpoint.write_bytes(b"fake")
    space = SimpleNamespace(num_classes=2, ignore_index=255, names=("a", "b"))
    monkeypatch.setattr(eval_module, "load_space", lambda *a: space)
    monkeypatch.setattr(
        eval_module,
        "load_data_mapping",
        lambda *a: SimpleNamespace(active_mask=lambda: np.ones(2, np.bool_)),
    )
    monkeypatch.setattr(eval_module, "build_model", lambda *a: torch.nn.Identity())
    monkeypatch.setattr(eval_module, "load_configured_checkpoint", lambda model, *a: model)
    monkeypatch.setattr(eval_module, "collect_env", lambda: {})
    monkeypatch.setattr(eval_module, "peak_vram", lambda: {})
    monkeypatch.setattr(eval_module, "git_sha", lambda *a: ("code", False))
    monkeypatch.setattr(eval_module, "enforce_from_env", lambda **k: None)
    monkeypatch.setattr(eval_module, "seed_everything", lambda *a, **k: None)

    def dataset(data, space, taxonomy, split, transform):
        assert split == "train"
        item = transform(image=np.zeros((3, 5, 3), np.uint8), mask=np.zeros((3, 5), np.uint8))

        class Dataset:
            def __len__(self):
                return 1

            def describe(self):
                return "narrow"

        result = Dataset()
        result.item = item
        return result

    monkeypatch.setattr(eval_module, "build_dataset", dataset)
    monkeypatch.setattr(
        eval_module,
        "DataLoader",
        lambda data, **k: [
            {"image": data.item["image"].unsqueeze(0), "mask": data.item["mask"].unsqueeze(0)}
        ],
    )
    monkeypatch.setattr(
        eval_module, "inference", lambda model, image, *a: torch.zeros((1, 2, *image.shape[-2:]))
    )
    records = []
    monkeypatch.setattr(eval_module, "write_results", lambda path, record: records.append(record))
    assert (
        eval_module.main(
            [
                str(config),
                "--ckpt",
                str(checkpoint),
                "--split",
                "train",
                "--pad-to-multiple",
                "32",
                "--device",
                "cpu",
                "--out",
                str(tmp_path / "result.json"),
            ]
        )
        == 0
    )
    assert np.asarray(records[0].metrics["confusion"]).sum() == 15
    assert records[0].config["evaluation"]["padding"]["padded_pixels_scored"] is False
