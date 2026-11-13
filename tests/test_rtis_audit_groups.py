"""Group diagnostics follow audited merged recording blocks without changing pixels."""

import contextlib
import csv
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from PIL import Image
from scripts import collect_rtis_statistics as collector


def test_merged_51_image_block_preserves_per_image_predictions(tmp_path, monkeypatch):
    samples = []
    target = np.array([[0, 1], [0, 1]], dtype=np.uint8)
    for group, count in [
        ("sunny-mountain-cab-view", 34),
        ("sunny-mountain-stations", 12),
        ("new-unmatched-2026", 5),
    ]:
        for index in range(count):
            key = f"{group}/{index:04}"
            rgb = tmp_path / "images/val" / (key + ".png")
            mask = tmp_path / "masks/val" / (key + ".png")
            rgb.parent.mkdir(parents=True, exist_ok=True)
            mask.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (2, 2), "gray").save(rgb)
            Image.fromarray(target).save(mask)
            samples.append(
                {
                    "key": key,
                    "split": "val",
                    "image_extension": ".png",
                    "group": "sunny-mountain-recording-conservative-block",
                    "image_sha256": collector.runtime.digest(rgb),
                    "mask_sha256": hashlib.sha256(target.tobytes()).hexdigest(),
                }
            )
    cfg = SimpleNamespace(
        stages=[SimpleNamespace(data=[SimpleNamespace(root=tmp_path)])],
        aug=None,
        eval=SimpleNamespace(sliding_window=False, window=(2, 2), stride=(2, 2)),
    )
    logits = torch.tensor([[[[2.0, 0.0], [2.0, 0.0]], [[0.0, 2.0], [0.0, 2.0]]]])
    monkeypatch.setattr(collector, "aug_from_spec", lambda *args: None)
    monkeypatch.setattr(
        collector,
        "build_eval_transform",
        lambda *args, **kwargs: lambda **item: {"image": torch.zeros(3, 2, 2)},
    )
    monkeypatch.setattr(collector, "inference", lambda *args: logits)
    monkeypatch.setattr(torch.Tensor, "cuda", lambda self: self)
    monkeypatch.setattr(torch, "autocast", lambda *args, **kwargs: contextlib.nullcontext())
    merged = tmp_path / "merged"
    old = tmp_path / "old"
    merged_result = collector.collect(None, cfg, samples, "val", merged, ["terrain", "mud-pumping"])
    legacy = [{k: v for k, v in sample.items() if k != "group"} for sample in samples]
    old_result = collector.collect(None, cfg, legacy, "val", old, ["terrain", "mud-pumping"])
    assert merged_result["images"] == old_result["images"] == 51
    assert merged_result["group_names"] == ["sunny-mountain-recording-conservative-block"]
    assert len(old_result["group_names"]) == 3
    assert merged_result["metrics"] == old_result["metrics"]
    assert json.loads((merged / "per-image-confusion.json").read_text()) == json.loads(
        (old / "per-image-confusion.json").read_text()
    )
    with (merged / "per-image.csv").open() as stream:
        new_rows = list(csv.DictReader(stream))
    with (old / "per-image.csv").open() as stream:
        old_rows = list(csv.DictReader(stream))
    assert len(new_rows) == 51
    for new, prior in zip(new_rows, old_rows, strict=True):
        assert new["group"] == "sunny-mountain-recording-conservative-block"
        assert {k: v for k, v in new.items() if k != "group"} == {
            k: v for k, v in prior.items() if k != "group"
        }


def test_audit_group_metadata_must_agree_with_split_groups():
    samples = [{"key": "old-prefix/a", "group": "merged"}]
    collector.validate_audit_groups(samples, {"groups": {"old-prefix/a": "merged"}})
    collector.validate_audit_groups([{"key": "legacy/a"}], {})
    with pytest.raises(RuntimeError, match="differs"):
        collector.validate_audit_groups(samples, {"groups": {"old-prefix/a": "old-prefix"}})
    with pytest.raises(RuntimeError, match="exactly"):
        collector.validate_audit_groups(samples, {"groups": {}})
    with pytest.raises(RuntimeError, match="Invalid audited"):
        collector.validate_audit_groups([{"key": "a", "group": 1}], {})
