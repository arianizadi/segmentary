"""Common-mask summary uses pixel-weighted native-resolution denominators."""

import json

import numpy as np
import pytest
from PIL import Image
from scripts.summarize_rtis_masks import summarize


def test_common_mask_summary(tmp_path):
    (tmp_path / "audit").mkdir()
    (tmp_path / "masks/train").mkdir(parents=True)
    (tmp_path / "classes.json").write_text(json.dumps({"name": "test", "classes": [{"id": 0}]}))
    masks = [np.array([[0, 255], [0, 250]], dtype=np.uint8), np.full((2, 3), 255, dtype=np.uint8)]
    rows = []
    for i, mask in enumerate(masks):
        Image.fromarray(mask).save(tmp_path / f"masks/train/{i}.png")
        rows.append(
            {"key": str(i), "split": "train", "height": mask.shape[0], "width": mask.shape[1]}
        )
    (tmp_path / "audit/samples.json").write_text(json.dumps(rows))
    summary = summarize(tmp_path)
    train = summary["splits"]["train"]
    assert train["images"] == 2
    assert train["pixels"] == 10
    assert train["ignore_pixels"] == 7
    assert train["ignore_fraction"] == 0.7
    assert train["all_ignore_images"] == 1
    assert train["dominant_class_images"] == 0
    assert train["invalid_id_images"] == 1
    assert train["invalid_ids"] == [250]
    assert train["boundary_pairs"] == 3
    assert train["neighbor_pairs"] == 11
    assert train["boundary_fraction"] == 3 / 11
    rows[0]["height"] = 10
    (tmp_path / "audit/samples.json").write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="shape"):
        summarize(tmp_path)
