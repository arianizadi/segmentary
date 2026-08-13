"""Opt-in real-GPU admission for every shipped Segmentary-native recipe."""

from __future__ import annotations

import gc
import json
import os
import time
from pathlib import Path

import pytest
import torch

from segmentary.model_catalog import ProbeOptions, list_catalog, probe_configs

REPO = Path(__file__).resolve().parents[1]


def _retain(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


@pytest.mark.gpu
def test_every_shipped_native_recipe_bf16_gpu_acceptance(tmp_path: Path) -> None:
    """Run four strict BF16 steps per dynamically discovered native recipe.

    This test is intentionally opt-in because it downloads real requested
    backbone weights and needs a CUDA device. It refuses ambiguous GPU mapping:
    the caller must expose exactly one GPU and state which visible-device value
    it expected. This keeps the reusable test cluster-neutral while making an
    accidental allocation mismatch fatal.
    """

    if os.environ.get("SEGMENTARY_RUN_NATIVE_CATALOG_GPU") != "1":
        pytest.skip("set SEGMENTARY_RUN_NATIVE_CATALOG_GPU=1 for real native-catalog admission")
    expected_visible = os.environ.get("SEGMENTARY_EXPECTED_CUDA_VISIBLE_DEVICES")
    assert expected_visible, (
        "set SEGMENTARY_EXPECTED_CUDA_VISIBLE_DEVICES to the exact single device exposed "
        "through CUDA_VISIBLE_DEVICES"
    )
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == expected_visible, (
        "CUDA_VISIBLE_DEVICES does not match SEGMENTARY_EXPECTED_CUDA_VISIBLE_DEVICES; "
        "refusing an ambiguous GPU allocation"
    )
    assert torch.cuda.is_available(), "the opt-in native catalog acceptance requires CUDA"
    assert torch.cuda.device_count() == 1, "exactly one CUDA device must be visible"
    assert torch.cuda.is_bf16_supported(), "the visible GPU must support BF16"

    catalog = list_catalog(REPO / "configs" / "models")
    catalog_root = REPO / "configs" / "models"
    native_recipes = [
        catalog_root / recipe["path"] for recipe in catalog["recipes"] if recipe["arch"] == "native"
    ]
    assert native_recipes, "the shipped catalog contains no native recipes"
    assert all(path.name.startswith("native_") for path in native_recipes)

    evidence_path = Path(
        os.environ.get(
            "SEGMENTARY_NATIVE_CATALOG_EVIDENCE",
            str(tmp_path / "native-catalog-gpu-acceptance.json"),
        )
    )
    aggregate: dict = {
        "schema_version": 1,
        "kind": "segmentary-native-catalog-gpu-acceptance",
        "status": "running",
        "started_unix_s": time.time(),
        "catalog_dir": "configs/models",
        "discovered_native_recipes": [path.name for path in native_recipes],
        "recipe_count": len(native_recipes),
        "gpu_visibility_policy": {
            "expected_cuda_visible_devices": expected_visible,
            "observed_cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
            "visible_device": "cuda:0",
            "device_name": torch.cuda.get_device_name(0),
        },
        "protocol": {
            "shapes": [[64, 96], [65, 97]],
            "batch_size": 1,
            "optimizer_steps_per_recipe": 4,
            "precision": "bf16",
            "synthetic_data": True,
            "quality_benchmark": False,
        },
        "records": [],
    }
    _retain(evidence_path, aggregate)

    options = ProbeOptions(
        shapes=((64, 96), (65, 97)),
        batch_size=1,
        steps=4,
        device="cuda:0",
        precision="bf16",
        seed=20260812,
    )
    for recipe in native_recipes:
        try:
            record = probe_configs(
                [
                    REPO / "configs" / "base.yaml",
                    recipe,
                    REPO / "configs" / "curricula" / "reference_cityscapes19.yaml",
                ],
                options=options,
            )
            assert record["status"] == "passed"
            assert record["model"]["native_components"] is not None
            assert record["protocol"]["precision"] == "bf16"
            assert len(record["shape_checks"]) == 2
            assert len(record["step_checks"]) == 4
            assert record["checks"]["all_trainable_gradients_present"] is True
            assert record["checks"]["all_trainable_gradients_finite"] is True
            assert record["checks"]["classifier_or_head_changed"] is True
            aggregate["records"].append(record)
            _retain(evidence_path, aggregate)
        except Exception as exc:
            aggregate["status"] = "failed"
            aggregate["failed_recipe"] = recipe.name
            aggregate["error_type"] = type(exc).__name__
            aggregate["error"] = str(exc)
            aggregate["finished_unix_s"] = time.time()
            _retain(evidence_path, aggregate)
            raise
        finally:
            gc.collect()
            torch.cuda.empty_cache()

    aggregate["status"] = "passed"
    aggregate["finished_unix_s"] = time.time()
    aggregate["wall_clock_s"] = aggregate["finished_unix_s"] - aggregate["started_unix_s"]
    _retain(evidence_path, aggregate)
    assert len(aggregate["records"]) == len(native_recipes)
