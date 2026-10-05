"""The in-process GPU policy hooks (train, eval, curriculum, collector) fail closed.

These are the only layer that compares the torch-visible UUID with the frozen
policy; removing any of them must break a test here.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
import yaml

from helpers_gpu_policy import make_campaign, patch_live, pinned_env, uuid_of
from segmentary import curriculum, gpu_policy, train
from segmentary import eval as eval_module
from segmentary.gpu_policy import GpuPolicyError


def _campaign_file(tmp_path: Path) -> Path:
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(make_campaign()))
    return path


def _config(tmp_path: Path, taxonomy_root: Path) -> Path:
    config = tmp_path / "exp.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "name": "policy-hook",
                "space": "rail_union",
                "taxonomy_root": str(taxonomy_root),
                "model": {"arch": "segformer_b0"},
                "stages": [
                    {
                        "name": "stage",
                        "data": [{"name": "cityscapes", "root": "/unused", "val_split": "val"}],
                    }
                ],
            }
        )
    )
    return config


@pytest.mark.parametrize("devices", ["2", "auto", "0,1"])
def test_train_refuses_more_than_its_one_pinned_device_under_a_policy(
    tmp_path, taxonomy_root, monkeypatch, devices
):
    patch_live(monkeypatch)
    monkeypatch.setattr(train, "run_curriculum", lambda *a, **k: pytest.fail("must not train"))
    monkeypatch.setattr(gpu_policy.os, "environ", pinned_env(2, _campaign_file(tmp_path)))
    with pytest.raises(GpuPolicyError, match="exactly one device"):
        train.main([str(_config(tmp_path, taxonomy_root)), "--devices", devices])


def test_train_fails_closed_on_unpinned_env_and_passes_when_pinned(
    tmp_path, taxonomy_root, monkeypatch
):
    patch_live(monkeypatch)
    started = []
    monkeypatch.setattr(
        train, "run_curriculum", lambda cfg, **k: started.append(k["devices"]) or []
    )
    config = _config(tmp_path, taxonomy_root)
    campaign = _campaign_file(tmp_path)
    # Policy named but the process can see every GPU: refuse before seeding.
    env = pinned_env(2, campaign)
    env["CUDA_VISIBLE_DEVICES"] = "0,1,2"
    monkeypatch.setattr(gpu_policy.os, "environ", env)
    with pytest.raises(GpuPolicyError, match="CUDA_VISIBLE_DEVICES"):
        train.main([str(config), "--devices", "1"])
    # Pinned to a forbidden GPU: refused even though exactly one device is visible.
    monkeypatch.setattr(gpu_policy.os, "environ", pinned_env(0, campaign))
    with pytest.raises(GpuPolicyError, match="not in the campaign allowlist"):
        train.main([str(config), "--devices", "1"])
    assert started == []
    monkeypatch.setattr(gpu_policy.os, "environ", pinned_env(2, campaign))
    assert train.main([str(config), "--devices", "1"]) == 0
    assert started == [1]


def test_eval_refuses_cpu_or_other_device_and_checks_torch_uuid_under_a_policy(
    tmp_path, taxonomy_root, monkeypatch
):
    patch_live(monkeypatch)
    config = _config(tmp_path, taxonomy_root)
    campaign = _campaign_file(tmp_path)
    monkeypatch.setattr(eval_module, "build_model", lambda *a: pytest.fail("must not build"))
    monkeypatch.setattr(gpu_policy.os, "environ", pinned_env(2, campaign))
    ckpt = str(tmp_path / "missing.ckpt")
    for device in ("cpu", "cuda:1"):
        with pytest.raises(GpuPolicyError, match="requires --device cuda:0"):
            eval_module.main([str(config), "--ckpt", ckpt, "--device", device])
    # cuda:0 is accepted only when torch really sits on the frozen GPU (the real
    # torch must stay importable for seeding, so only the UUID probe is faked).
    monkeypatch.setattr(
        gpu_policy, "torch_visible_uuid", lambda: (1, gpu_policy.normalize_uuid(uuid_of(0)))
    )
    with pytest.raises(GpuPolicyError, match="torch is on GPU"):
        eval_module.main([str(config), "--ckpt", ckpt, "--device", "cuda:0"])

    def unavailable():
        raise GpuPolicyError("CUDA is not available to this process under a GPU policy")

    monkeypatch.setattr(gpu_policy, "torch_visible_uuid", unavailable)
    with pytest.raises(GpuPolicyError, match="CUDA is not available"):
        eval_module.main([str(config), "--ckpt", ckpt, "--device", "cuda:0"])


def test_eval_without_a_policy_still_allows_cpu(tmp_path, taxonomy_root, monkeypatch):
    patch_live(monkeypatch)
    monkeypatch.delenv("SEGMENTARY_GPU_POLICY", raising=False)
    monkeypatch.setattr(
        eval_module, "build_model", lambda *a: (_ for _ in ()).throw(RuntimeError("reached"))
    )
    with pytest.raises(RuntimeError, match="reached"):
        eval_module.main(
            [str(_config(tmp_path, taxonomy_root)), "--ckpt", "x.ckpt", "--device", "cpu"]
        )


def test_curriculum_adds_torch_uuid_check_only_under_a_policy(tmp_path, monkeypatch):
    monkeypatch.delenv("SEGMENTARY_GPU_POLICY", raising=False)
    assert curriculum._gpu_policy_callbacks() == []
    monkeypatch.setenv("SEGMENTARY_GPU_POLICY", str(tmp_path / "campaign.json"))
    callbacks = curriculum._gpu_policy_callbacks()
    assert len(callbacks) == 1 and isinstance(callbacks[0], curriculum._GpuPolicyCheck)
    calls = []
    monkeypatch.setattr(curriculum, "enforce_from_env", lambda **k: calls.append(k))
    callbacks[0].on_fit_start(trainer=None, pl_module=None)
    assert calls == [{"init_cuda": True}]
    # The trainer must actually receive the callback.
    assert "_gpu_policy_callbacks()" in inspect.getsource(curriculum.run_stage)


def test_deterministic_seeding_after_uuid_check_is_refused(monkeypatch):
    import torch

    from segmentary.utils.seed import seed_everything

    monkeypatch.setattr(torch.cuda, "is_initialized", lambda: True)
    with pytest.raises(RuntimeError, match="before the first CUDA"):
        seed_everything(0, deterministic=True)


def test_collector_and_profiler_verify_before_touching_cuda():
    from scripts import collect_rtis_statistics, profile_rtis_campaign

    from segmentary import performance

    collector = inspect.getsource(collect_rtis_statistics.main)
    assert collector.index("enforce_from_env(init_cuda=False)") < collector.index("load_experiment")
    # Deterministic seeding refuses to run once CUDA is initialized, so the UUID check
    # (which initializes CUDA) must come after it. The 2026-10-05 smoke failed on this.
    seeded = collector.index("seed_everything(cfg.train.seed, deterministic=True)")
    assert seeded < collector.index("enforce_from_env(init_cuda=True)")
    assert "enforce_from_env(init_cuda=False)" in inspect.getsource(profile_rtis_campaign.measure)
    benchmark = inspect.getsource(performance.run_benchmark)
    assert benchmark.index("enforce_from_env(init_cuda=True)") < benchmark.index("load_yaml")
