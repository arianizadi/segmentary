"""The Oct 9 HRC smoke script on CPU: equality, finite training and gradient-norm records.

Needs nnunetv2 (the nnU-Net backend environment). The GPU-only gates (memory,
step-time overhead) are recorded as None on CPU.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("nnunetv2")

from segmentary.gpu_policy import GpuPolicyError
from test_medical_probability_export import _tiny_plan

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "hrc_gpu_smoke_test", ROOT / "scripts/hrc_gpu_smoke.py"
)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_cpu_smoke_records_equality_finite_losses_and_gradient_groups(tmp_path, monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(_tiny_plan()))
    output = tmp_path / "smoke.json"
    arguments = ["--plan", str(plan), "--output", str(output), "--device", "cpu"]
    settings = ["--steps", "3", "--warmup", "2", "--forward-repeats", "1", "--threads", "2"]
    assert smoke.main([*arguments, *settings]) == 0
    record = json.loads(output.read_text())
    assert record["criteria"]["equality"] is True
    assert record["criteria"]["finite_losses"] is True
    assert record["criteria"]["memory_below_limit"] is None
    assert record["zero_init_equality_fp16_autocast"] is None
    assert record["hrc_options"]["levels"] == [2, 1, 0]
    hrc = record["training"]["hrc"]["gradient_norms"]
    assert set(hrc["per_group_first_step"]) == {"base", "hrc_film", "hrc_other"}
    # FiLM is zero at step 0, so the other HRC parameters receive no gradient yet.
    assert hrc["per_group_first_step"]["hrc_other"] == 0.0
    assert set(record["training"]["resenc"]["gradient_norms"]["per_group_first_step"]) == {"base"}
    assert record["training"]["hrc"]["first_loss"] == record["training"]["resenc"]["first_loss"]
    with pytest.raises(FileExistsError):
        smoke.main([*arguments, *settings])
    placed = tmp_path / "placed.json"
    smoke.main([*arguments[:3], str(placed), *arguments[4:], *settings, "--levels", "2", "1"])
    assert json.loads(placed.read_text())["hrc_options"]["levels"] == [2, 1]


def test_smoke_refuses_forbidden_gpus_and_mismatched_devices(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(_tiny_plan()))
    base = ["--plan", str(plan), "--output", str(tmp_path / "out.json")]
    with pytest.raises(ValueError, match="--device cuda"):
        smoke.main([*base, "--device", "cpu", "--gpu", "2"])
    for gpu in ("0", "1"):
        with pytest.raises(GpuPolicyError, match="forbidden"):
            smoke.main([*base, "--gpu", gpu])
    assert not (tmp_path / "out.json").exists()
